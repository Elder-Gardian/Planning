"""Validate district capacity-register responses and merge them by stable source ID."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd

from welfaremap.facilities.capacity import apply_capacity_scenarios
from welfaremap.facilities.sources import clean_text

PENDING_STATUS = "PENDING_DISTRICT_REGISTER"
APPLY_STATUSES = frozenset(
    {
        "PARTIAL_VERIFIED",
        "VERIFIED_DISTRICT_REGISTER",
        "VERIFIED_SITE_VISIT",
    }
)
ALLOWED_REQUEST_STATUSES = APPLY_STATUSES | {PENDING_STATUS}

OPERATIONAL_STATUS_MAP = {
    "ACTIVE": ("ACTIVE_CONFIRMED", "AVAILABLE"),
    "TEMPORARILY_CLOSED": ("TEMPORARILY_CLOSED_CONFIRMED", "UNAVAILABLE"),
    "CLOSED": ("CLOSED_CONFIRMED", "UNAVAILABLE"),
    "RELOCATED": ("RELOCATED_CONFIRMED", "UNAVAILABLE"),
    "UNDER_CONSTRUCTION": ("UNDER_CONSTRUCTION_CONFIRMED", "UNAVAILABLE"),
}

PERSON_COLUMNS = (
    "capacity_operational_confirmed",
    "capacity_registered",
    "capacity_fire",
    "capacity_seats",
    "peak_concurrent_observed",
)
NUMERIC_COLUMNS = (*PERSON_COLUMNS, "facility_net_area_m2")
DIRECT_COLUMNS = (
    *NUMERIC_COLUMNS,
    "facility_area_scope",
    "facility_area_confidence",
    "peak_observation_period",
    "opening_hours",
)
EVIDENCE_COLUMN_MAP = {
    "register_as_of": "capacity_register_as_of",
    "source_document_id": "capacity_source_document_id",
    "source_document_url": "capacity_source_document_url",
    "verified_by": "capacity_verified_by",
    "verification_note": "capacity_verification_note",
    "request_status": "capacity_response_status",
}
REQUIRED_COLUMNS = {
    "source_record_id",
    "register_as_of",
    "operational_status_confirmed",
    "source_document_id",
    "source_document_url",
    "verified_by",
    "request_status",
    *DIRECT_COLUMNS,
}


def _has_value(value: Any) -> bool:
    if value is None or pd.isna(value):
        return False
    return bool(clean_text(value))


def _optional_text(value: Any) -> str:
    return clean_text(value) if _has_value(value) else ""


def _validated_responses(master: pd.DataFrame, responses: pd.DataFrame) -> pd.DataFrame:
    missing_columns = sorted(REQUIRED_COLUMNS - set(responses.columns))
    if missing_columns:
        raise ValueError(f"capacity response 필수 열 누락: {missing_columns}")
    if responses["source_record_id"].duplicated().any():
        raise ValueError("capacity response에 중복 source_record_id 존재")

    known_ids = set(master["source_record_id"].astype(str))
    response_ids = set(responses["source_record_id"].astype(str))
    unknown_ids = sorted(response_ids - known_ids)
    if unknown_ids:
        raise ValueError(f"master에 없는 capacity response ID: {unknown_ids[:10]}")

    result = responses.copy()
    result["request_status"] = result["request_status"].map(_optional_text)
    unsupported = sorted(
        set(result.loc[result["request_status"].ne(""), "request_status"])
        - ALLOWED_REQUEST_STATUSES
    )
    if unsupported:
        raise ValueError(f"지원하지 않는 request_status: {unsupported}")

    verified_mask = result["request_status"].isin(APPLY_STATUSES)
    verified = result.loc[verified_mask].copy()
    if verified.empty:
        return verified

    parsed_dates = pd.to_datetime(verified["register_as_of"], errors="coerce")
    missing_dates = verified.loc[parsed_dates.isna(), "source_record_id"].tolist()
    if missing_dates:
        raise ValueError(f"검증 회신의 register_as_of 누락 또는 오류: {missing_dates[:10]}")

    missing_verifier = verified.loc[
        ~verified["verified_by"].map(_has_value), "source_record_id"
    ].tolist()
    if missing_verifier:
        raise ValueError(f"검증 회신의 verified_by 누락: {missing_verifier[:10]}")

    has_evidence = verified["source_document_id"].map(_has_value) | verified[
        "source_document_url"
    ].map(_has_value)
    missing_evidence = verified.loc[~has_evidence, "source_record_id"].tolist()
    if missing_evidence:
        raise ValueError(f"검증 회신의 근거 문서 누락: {missing_evidence[:10]}")

    statuses = verified["operational_status_confirmed"].map(_optional_text)
    invalid_statuses = sorted(set(statuses[statuses.ne("")]) - OPERATIONAL_STATUS_MAP.keys())
    if invalid_statuses:
        raise ValueError(f"지원하지 않는 operational_status_confirmed: {invalid_statuses}")
    verified["operational_status_confirmed"] = statuses

    for column in NUMERIC_COLUMNS:
        raw = verified[column]
        present = raw.map(_has_value)
        numeric = pd.to_numeric(raw, errors="coerce")
        invalid_ids = verified.loc[present & numeric.isna(), "source_record_id"].tolist()
        if invalid_ids:
            raise ValueError(f"{column} 숫자 형식 오류: {invalid_ids[:10]}")
        negative_ids = verified.loc[numeric.lt(0).fillna(False), "source_record_id"].tolist()
        if negative_ids:
            raise ValueError(f"{column} 음수 값: {negative_ids[:10]}")
        if column in PERSON_COLUMNS:
            fractional = numeric.notna() & numeric.mod(1).ne(0)
            fractional_ids = verified.loc[fractional, "source_record_id"].tolist()
            if fractional_ids:
                raise ValueError(f"{column} 인원 값은 정수여야 함: {fractional_ids[:10]}")
        verified[column] = numeric

    has_area = verified["facility_net_area_m2"].notna()
    area_scope = verified["facility_area_scope"].map(_optional_text)
    area_confidence = verified["facility_area_confidence"].map(_optional_text).str.upper()
    invalid_area = has_area & (
        area_scope.ne("FACILITY_NET_VERIFIED")
        | ~area_confidence.isin({"HIGH", "MEDIUM"})
    )
    invalid_area_ids = verified.loc[invalid_area, "source_record_id"].tolist()
    if invalid_area_ids:
        raise ValueError(
            "facility_net_area_m2에는 FACILITY_NET_VERIFIED와 HIGH/MEDIUM 근거 필요: "
            f"{invalid_area_ids[:10]}"
        )
    verified["facility_area_scope"] = area_scope
    verified["facility_area_confidence"] = area_confidence
    verified["register_as_of"] = parsed_dates.dt.strftime("%Y-%m-%d")
    return verified


def apply_capacity_responses(
    master: pd.DataFrame, responses: pd.DataFrame
) -> pd.DataFrame:
    """Apply only evidence-backed response rows and recompute all capacity scenarios."""
    verified = _validated_responses(master, responses)
    result = master.copy()
    for column in (*DIRECT_COLUMNS, *EVIDENCE_COLUMN_MAP.values()):
        if column not in result:
            result[column] = pd.NA
    if "capacity_response_applied" not in result:
        result["capacity_response_applied"] = False

    result_index = pd.Series(result.index, index=result["source_record_id"].astype(str))
    for response in verified.to_dict("records"):
        source_record_id = str(response["source_record_id"])
        index = int(result_index[source_record_id])
        for column in DIRECT_COLUMNS:
            value = response.get(column)
            if _has_value(value):
                result.at[index, column] = value
        for source_column, target_column in EVIDENCE_COLUMN_MAP.items():
            value = response.get(source_column)
            if _has_value(value):
                result.at[index, target_column] = _optional_text(value)

        confirmed_status = _optional_text(response.get("operational_status_confirmed"))
        if confirmed_status:
            operational_status, availability_status = OPERATIONAL_STATUS_MAP[confirmed_status]
            result.at[index, "operational_status"] = operational_status
            result.at[index, "availability_status"] = availability_status
            note = _optional_text(response.get("verification_note"))
            if note:
                result.at[index, "status_note"] = note
        result.at[index, "capacity_response_applied"] = True

    return apply_capacity_scenarios(result)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--master", type=Path, required=True)
    parser.add_argument("--responses", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--profile-output", type=Path, required=True)
    args = parser.parse_args()

    master = pd.read_csv(args.master, encoding="utf-8-sig")
    responses = pd.read_csv(args.responses, encoding="utf-8-sig")
    merged = apply_capacity_responses(master, responses)

    from welfaremap.facilities.master import facility_profile, validate_master

    validate_master(merged)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    merged.to_csv(args.output, index=False, encoding="utf-8-sig")
    args.profile_output.parent.mkdir(parents=True, exist_ok=True)
    args.profile_output.write_text(
        json.dumps(facility_profile(merged), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    applied = int(merged["capacity_response_applied"].eq(True).sum())
    print(f"capacity responses applied: {applied:,} -> {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
