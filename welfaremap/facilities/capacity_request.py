"""Prepare a prefilled district-register request table for P0 senior centers."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

REQUEST_COLUMNS = [
    "source_record_id",
    "facility_name",
    "borough",
    "current_address",
    "current_operational_status",
    "current_availability_status",
    "historical_source_record_id",
    "historical_permit_number_raw",
    "historical_capacity_registered_candidate",
    "historical_capacity_match_tier",
    "historical_capacity_candidate_status",
    "historical_capacity_source_as_of_upper_bound",
    "historical_capacity_review_note",
    "register_as_of",
    "operational_status_confirmed",
    "capacity_operational_confirmed",
    "capacity_registered",
    "capacity_fire",
    "capacity_seats",
    "facility_net_area_m2",
    "facility_area_scope",
    "facility_area_confidence",
    "peak_concurrent_observed",
    "peak_observation_period",
    "opening_hours",
    "source_document_id",
    "source_document_url",
    "verified_by",
    "verification_note",
    "request_status",
]

HISTORICAL_REQUIRED_COLUMNS = {
    "source_record_id",
    "historical_source_record_id",
    "permit_number_raw",
    "capacity_registered_historical_candidate",
    "match_tier",
    "candidate_status",
    "source_as_of_upper_bound",
    "requires_current_register_verification",
    "may_use_as_operational_capacity",
}
HISTORICAL_COLUMN_MAP = {
    "historical_source_record_id": "historical_source_record_id",
    "permit_number_raw": "historical_permit_number_raw",
    "capacity_registered_historical_candidate": (
        "historical_capacity_registered_candidate"
    ),
    "match_tier": "historical_capacity_match_tier",
    "candidate_status": "historical_capacity_candidate_status",
    "source_as_of_upper_bound": "historical_capacity_source_as_of_upper_bound",
}


def _attach_historical_references(
    request: pd.DataFrame, candidates: pd.DataFrame
) -> pd.DataFrame:
    missing = sorted(HISTORICAL_REQUIRED_COLUMNS - set(candidates.columns))
    if missing:
        raise ValueError(f"historical capacity candidate 필수 열 누락: {missing}")
    if candidates["source_record_id"].duplicated().any():
        raise ValueError("historical capacity candidate에 중복 source_record_id 존재")

    request_ids = set(request["source_record_id"].astype(str))
    candidate_ids = set(candidates["source_record_id"].astype(str))
    unknown_ids = sorted(candidate_ids - request_ids)
    if unknown_ids:
        raise ValueError(f"P0 request에 없는 historical candidate ID: {unknown_ids[:10]}")

    requires_verification = candidates["requires_current_register_verification"].fillna(
        False
    )
    may_use_operational = candidates["may_use_as_operational_capacity"].fillna(True)
    unsafe = candidates.loc[
        ~requires_verification.astype(bool) | may_use_operational.astype(bool),
        "source_record_id",
    ].tolist()
    if unsafe:
        raise ValueError(f"운영 공급으로 오인 가능한 historical candidate: {unsafe[:10]}")

    result = request.copy()
    request_index = pd.Series(result.index, index=result["source_record_id"].astype(str))
    for row in candidates.to_dict("records"):
        index = int(request_index[str(row["source_record_id"])])
        for source_column, target_column in HISTORICAL_COLUMN_MAP.items():
            value = row[source_column]
            if pd.isna(value):
                rendered = ""
            elif source_column == "capacity_registered_historical_candidate":
                rendered = str(int(value))
            else:
                rendered = str(value)
            result.at[index, target_column] = rendered
        result.at[index, "historical_capacity_review_note"] = (
            "과거 신고정원 참고값이며 최신 자치구 대장 확인 전 공급 사용 금지"
        )
    return result


def build_capacity_request(
    master: pd.DataFrame, historical_candidates: pd.DataFrame | None = None
) -> pd.DataFrame:
    """Export one request row per P0 service record without using legacy proxies."""
    p0 = master[master["p0_service_eligible"].astype(bool)].copy()
    result = pd.DataFrame(index=p0.index)
    for column in REQUEST_COLUMNS:
        result[column] = ""
    result["source_record_id"] = p0["source_record_id"]
    result["facility_name"] = p0["facility_name"]
    result["borough"] = p0["borough"]
    result["current_address"] = p0["matched_road_address"].fillna(p0["address_search"])
    result["current_operational_status"] = p0["operational_status"]
    result["current_availability_status"] = p0["availability_status"]
    result["request_status"] = "PENDING_DISTRICT_REGISTER"
    if result["source_record_id"].duplicated().any():
        raise ValueError("capacity request에 중복 source_record_id 존재")
    if historical_candidates is not None:
        result = _attach_historical_references(result, historical_candidates)
    return result[REQUEST_COLUMNS].sort_values(["borough", "source_record_id"])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--historical-candidates", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    master = pd.read_csv(args.input, encoding="utf-8-sig")
    historical_candidates = (
        pd.read_csv(args.historical_candidates, encoding="utf-8-sig")
        if args.historical_candidates
        else None
    )
    request = build_capacity_request(master, historical_candidates)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    request.to_csv(args.output, index=False, encoding="utf-8-sig")
    print(f"capacity register request: {len(request):,} -> {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
