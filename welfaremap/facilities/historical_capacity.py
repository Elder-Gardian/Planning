"""Match a stale legacy register to current P0 facilities without promoting supply."""

from __future__ import annotations

import argparse
import json
import re
import unicodedata
from pathlib import Path
from typing import Any

import pandas as pd

LEGACY_DATASET_ID = "OA-15052_LEGACY_LICENSE_MIRROR"
LEGACY_SOURCE_AS_OF_UPPER_BOUND = "2024-05-24"
LEGACY_SOURCE_URL = (
    "https://raw.githubusercontent.com/jaewonE/"
    "Selecting-the-optimal-hydrogen-charging-station-location/"
    "87794733a9c74eb36e0da3b0f6d4be7d92e2e5ac/"
    "trans_data/elderly_center.csv"
)
CAPACITY_SEMANTICS = "REGISTERED_ADMISSION_STALE_REFERENCE"

MASTER_REQUIRED_COLUMNS = {
    "source_record_id",
    "facility_name",
    "borough",
    "address_search",
    "p0_service_eligible",
}
LEGACY_REQUIRED_COLUMNS = {
    "번호",
    "사업장명",
    "소재지전체주소",
    "인허가일자",
    "영업상태명",
    "입소정원",
    "총인원수",
    "인허가번호",
    "상세영업상태명",
}

CANDIDATE_COLUMNS = [
    "source_record_id",
    "historical_source_record_id",
    "facility_name",
    "historical_facility_name",
    "borough",
    "current_address",
    "historical_address",
    "permit_date_raw",
    "permit_number_raw",
    "historical_operational_status_raw",
    "historical_detail_status_raw",
    "capacity_registered_historical_raw",
    "capacity_registered_historical_candidate",
    "historical_total_people_raw",
    "match_tier",
    "candidate_status",
    "capacity_semantics",
    "source_dataset",
    "source_as_of_upper_bound",
    "source_url",
    "requires_current_register_verification",
    "may_use_as_operational_capacity",
]


def _text(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def _identity_name(value: Any) -> str:
    text = unicodedata.normalize("NFKC", _text(value)).lower()
    return re.sub(r"[^0-9a-z가-힣]", "", text)


def _canonical_name(value: Any) -> str:
    """Remove generic type aliases but preserve gender, number, block and building tokens."""
    text = unicodedata.normalize("NFKC", _text(value)).lower()
    text = re.sub(r"a\s*/\s*p|\bapt\.?\b", "", text)
    text = re.sub(r"\(\s*아\s*\)|\[\s*아\s*\]", "", text)
    text = re.sub(r"아파트|경로당|경노당|노인정", "", text)
    return re.sub(r"[^0-9a-z가-힣]", "", text)


def _borough_from_address(value: Any) -> str:
    match = re.search(r"서울(?:특별시)?\s+([^\s,]+구)", _text(value))
    return match.group(1) if match else ""


def _validate_columns(frame: pd.DataFrame, required: set[str], label: str) -> None:
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"{label} 필수 열 누락: {missing}")


def _prepare_legacy(legacy: pd.DataFrame) -> pd.DataFrame:
    _validate_columns(legacy, LEGACY_REQUIRED_COLUMNS, "historical capacity")
    result = legacy.copy()
    for column in LEGACY_REQUIRED_COLUMNS:
        result[column] = result[column].map(_text)

    if result["번호"].eq("").any() or result["번호"].duplicated().any():
        raise ValueError("historical capacity 번호는 비어 있거나 중복될 수 없음")

    result["borough"] = result["소재지전체주소"].map(_borough_from_address)
    missing_borough = result.loc[result["borough"].eq(""), "번호"].tolist()
    if missing_borough:
        raise ValueError(f"historical capacity 주소에서 자치구 추출 실패: {missing_borough[:10]}")

    raw_capacity = result["입소정원"]
    present = raw_capacity.ne("")
    parsed = pd.to_numeric(raw_capacity, errors="coerce")
    invalid = result.loc[present & parsed.isna(), "번호"].tolist()
    if invalid:
        raise ValueError(f"historical capacity 입소정원 숫자 형식 오류: {invalid[:10]}")
    negative = result.loc[parsed.lt(0).fillna(False), "번호"].tolist()
    if negative:
        raise ValueError(f"historical capacity 입소정원 음수 값: {negative[:10]}")
    fractional = parsed.notna() & parsed.mod(1).ne(0)
    fractional_ids = result.loc[fractional, "번호"].tolist()
    if fractional_ids:
        raise ValueError(f"historical capacity 입소정원은 정수여야 함: {fractional_ids[:10]}")

    result["_capacity_parsed"] = parsed.astype("Int64")
    result["_capacity_candidate"] = parsed.where(parsed.gt(0)).astype("Int64")
    result["_identity_name"] = result["사업장명"].map(_identity_name)
    result["_canonical_name"] = result["사업장명"].map(_canonical_name)
    result["historical_source_record_id"] = result["번호"].map(
        lambda value: f"seoul-senior-center-license-legacy:2024-05:{value}"
    )
    result["_historical_row_id"] = range(len(result))
    return result


def _prepare_current(master: pd.DataFrame) -> pd.DataFrame:
    _validate_columns(master, MASTER_REQUIRED_COLUMNS, "facility master")
    if master["source_record_id"].duplicated().any():
        raise ValueError("facility master에 중복 source_record_id 존재")
    result = master.loc[master["p0_service_eligible"].fillna(False).astype(bool)].copy()
    result["borough"] = result["borough"].map(_text)
    result["_identity_name"] = result["facility_name"].map(_identity_name)
    result["_canonical_name"] = result["facility_name"].map(_canonical_name)
    result["_current_row_id"] = range(len(result))
    return result


def _unique_matches(
    current: pd.DataFrame,
    legacy: pd.DataFrame,
    *,
    key: str,
    match_tier: str,
    used_current: set[int],
    used_legacy: set[int],
) -> pd.DataFrame:
    current_remaining = current.loc[~current["_current_row_id"].isin(used_current)].copy()
    legacy_remaining = legacy.loc[~legacy["_historical_row_id"].isin(used_legacy)].copy()
    match_columns = ["borough", key]
    current_unique = current_remaining.loc[
        current_remaining[key].ne("")
        & ~current_remaining.duplicated(match_columns, keep=False)
    ]
    legacy_unique = legacy_remaining.loc[
        legacy_remaining[key].ne("")
        & ~legacy_remaining.duplicated(match_columns, keep=False)
    ]
    matches = current_unique.merge(
        legacy_unique,
        on=match_columns,
        how="inner",
        suffixes=("_current", "_historical"),
        validate="one_to_one",
    )
    matches["match_tier"] = match_tier
    used_current.update(matches["_current_row_id"].astype(int).tolist())
    used_legacy.update(matches["_historical_row_id"].astype(int).tolist())
    return matches


def _candidate_status(parsed: Any, candidate: Any) -> str:
    if not pd.isna(candidate):
        return "REVIEW_REQUIRED_STALE_POSITIVE"
    if not pd.isna(parsed) and int(parsed) == 0:
        return "ZERO_TREATED_AS_MISSING"
    return "VALUE_MISSING"


def build_historical_capacity_candidates(
    master: pd.DataFrame, legacy: pd.DataFrame
) -> pd.DataFrame:
    """Return one-to-one legacy matches as review candidates, never operational supply."""
    current = _prepare_current(master)
    historical = _prepare_legacy(legacy)
    used_current: set[int] = set()
    used_legacy: set[int] = set()
    matched_frames = [
        _unique_matches(
            current,
            historical,
            key="_identity_name",
            match_tier="T1_EXACT_NAME_BOROUGH_UNIQUE",
            used_current=used_current,
            used_legacy=used_legacy,
        ),
        _unique_matches(
            current,
            historical,
            key="_canonical_name",
            match_tier="T2_GENERIC_ALIAS_NAME_BOROUGH_UNIQUE",
            used_current=used_current,
            used_legacy=used_legacy,
        ),
    ]
    matched = pd.concat(matched_frames, ignore_index=True)
    if matched.empty:
        return pd.DataFrame(columns=CANDIDATE_COLUMNS)

    result = pd.DataFrame(
        {
            "source_record_id": matched["source_record_id"],
            "historical_source_record_id": matched["historical_source_record_id"],
            "facility_name": matched["facility_name"],
            "historical_facility_name": matched["사업장명"],
            "borough": matched["borough"],
            "current_address": matched["address_search"],
            "historical_address": matched["소재지전체주소"],
            "permit_date_raw": matched["인허가일자"],
            "permit_number_raw": matched["인허가번호"],
            "historical_operational_status_raw": matched["영업상태명"],
            "historical_detail_status_raw": matched["상세영업상태명"],
            "capacity_registered_historical_raw": matched["입소정원"],
            "capacity_registered_historical_candidate": matched["_capacity_candidate"],
            "historical_total_people_raw": matched["총인원수"],
            "match_tier": matched["match_tier"],
        }
    )
    result["candidate_status"] = [
        _candidate_status(parsed, candidate)
        for parsed, candidate in zip(
            matched["_capacity_parsed"], matched["_capacity_candidate"], strict=True
        )
    ]
    result["capacity_semantics"] = CAPACITY_SEMANTICS
    result["source_dataset"] = LEGACY_DATASET_ID
    result["source_as_of_upper_bound"] = LEGACY_SOURCE_AS_OF_UPPER_BOUND
    result["source_url"] = LEGACY_SOURCE_URL
    result["requires_current_register_verification"] = True
    result["may_use_as_operational_capacity"] = False

    if result["source_record_id"].duplicated().any():
        raise ValueError("historical capacity candidate가 current 시설에 중복 매칭됨")
    if result["historical_source_record_id"].duplicated().any():
        raise ValueError("historical capacity candidate가 legacy 시설에 중복 매칭됨")
    return result[CANDIDATE_COLUMNS].sort_values(
        ["borough", "source_record_id"], ignore_index=True
    )


def historical_capacity_profile(
    master: pd.DataFrame, legacy: pd.DataFrame, candidates: pd.DataFrame
) -> dict[str, Any]:
    current_count = int(master["p0_service_eligible"].fillna(False).astype(bool).sum())
    prepared_legacy = _prepare_legacy(legacy)
    positive = candidates["capacity_registered_historical_candidate"].notna()
    return {
        "readiness": "REFERENCE_ONLY_NOT_APPLIED_TO_OPERATIONAL_SUPPLY",
        "source_dataset": LEGACY_DATASET_ID,
        "source_as_of_upper_bound": LEGACY_SOURCE_AS_OF_UPPER_BOUND,
        "legacy_rows": len(prepared_legacy),
        "legacy_positive_registered_capacity_rows": int(
            prepared_legacy["_capacity_candidate"].notna().sum()
        ),
        "current_p0_rows": current_count,
        "matched_rows": len(candidates),
        "matched_positive_capacity_candidates": int(positive.sum()),
        "matched_zero_treated_as_missing": int(
            candidates["candidate_status"].eq("ZERO_TREATED_AS_MISSING").sum()
        ),
        "matched_value_missing": int(
            candidates["candidate_status"].eq("VALUE_MISSING").sum()
        ),
        "positive_candidate_current_coverage": (
            float(positive.sum() / current_count) if current_count else 0.0
        ),
        "match_tier": candidates["match_tier"].value_counts().sort_index().to_dict(),
        "operational_capacity_rows_added": 0,
        "warning": (
            "과거 신고정원 후보는 현행 운영상태·동시수용량이 아니며, "
            "자치구 최신 신고대장 확인 전 공급량으로 사용할 수 없음"
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--master", type=Path, required=True)
    parser.add_argument("--historical", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--profile-output", type=Path, required=True)
    args = parser.parse_args()

    master = pd.read_csv(args.master, encoding="utf-8-sig", low_memory=False)
    legacy = pd.read_csv(args.historical, encoding="utf-8", dtype=str)
    candidates = build_historical_capacity_candidates(master, legacy)
    profile = historical_capacity_profile(master, legacy, candidates)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    candidates.to_csv(args.output, index=False, encoding="utf-8-sig")
    args.profile_output.parent.mkdir(parents=True, exist_ok=True)
    args.profile_output.write_text(
        json.dumps(profile, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    positive = int(candidates["capacity_registered_historical_candidate"].notna().sum())
    print(
        f"historical capacity matches: {len(candidates):,}; "
        f"positive review candidates: {positive:,} -> {args.output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
