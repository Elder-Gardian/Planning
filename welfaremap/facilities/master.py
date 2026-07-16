"""Build the canonical facility master from source records and legacy enrichment."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from welfaremap.facilities.capacity import apply_capacity_scenarios
from welfaremap.facilities.geocode import coordinate_scope
from welfaremap.facilities.sources import build_source_records, clean_text

LEGACY_COLUMN_MAP = {
    "matched_road_address": "legacy_matched_road_address",
    "matched_jibun_address": "legacy_matched_jibun_address",
    "sigungu_cd": "legacy_sigungu_cd",
    "bjdong_cd": "legacy_bjdong_cd",
    "building_name": "legacy_building_name",
    "main_purpose": "legacy_main_purpose",
    "register_kind": "legacy_register_kind",
    "building_area_m2": "legacy_building_area_m2",
    "total_floor_area_m2": "legacy_total_floor_area_m2",
    "ground_floors": "legacy_ground_floors",
    "underground_floors": "legacy_underground_floors",
    "title_candidate_count": "legacy_title_candidate_count",
    "address_error": "legacy_address_error",
    "building_api_error": "legacy_building_api_error",
    "usable_area_m2": "legacy_usable_area_m2",
    "estimated_capacity": "legacy_capacity_proxy",
    "capacity_method": "legacy_capacity_method",
    "confidence": "legacy_capacity_confidence",
    "decision_reason": "legacy_capacity_reason",
    "capacity_imputed": "legacy_capacity_imputed",
    "area_missing": "legacy_area_missing",
    "coord_error": "legacy_coord_error",
    "coord_method": "legacy_coord_method",
}


def _normalized_entity_text(value: Any) -> str:
    return re.sub(r"[^0-9A-Za-z가-힣]", "", clean_text(value)).lower()


def _entity_key(name: Any, address: Any) -> str:
    raw = f"{_normalized_entity_text(name)}|{_normalized_entity_text(address)}"
    return hashlib.sha256(raw.encode()).hexdigest()[:20]


def _float_or_none(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return None if pd.isna(number) else number


def _numeric_column(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame:
        return pd.Series(pd.NA, index=frame.index, dtype="Float64")
    return pd.to_numeric(frame[column], errors="coerce")


def _coordinate_metadata(row: pd.Series) -> tuple[str, str, str, str]:
    latitude = _float_or_none(row.get("latitude"))
    longitude = _float_or_none(row.get("longitude"))
    if latitude is None or longitude is None:
        return "NONE", "MISSING", "NONE", "REVIEW_REQUIRED"
    scope = coordinate_scope(longitude, latitude)
    method = clean_text(row.get("legacy_coord_method"))
    if method == "주소검색":
        source = "LEGACY_JUSO_WEB_UNVERIFIED"
    elif method == "건물명검색":
        source = "LEGACY_BUILDING_NAME_UNVERIFIED"
    else:
        source = "LEGACY_UNKNOWN_UNVERIFIED"
    status = "PROVISIONAL_IN_SERVICE_AREA" if scope == "IN_SERVICE_AREA" else scope
    return source, status, "PROVISIONAL", "REVIEW_REQUIRED"


def attach_legacy_enrichment(
    source_records: pd.DataFrame, legacy_results: pd.DataFrame
) -> pd.DataFrame:
    """Attach legacy rows only after a strict name/borough order check."""
    if len(source_records) != len(legacy_results):
        raise ValueError(
            f"원천 {len(source_records):,}행과 인수 결과 {len(legacy_results):,}행의 길이가 다름"
        )
    name_match = source_records["facility_name"].map(clean_text).eq(
        legacy_results["facility_name"].map(clean_text)
    )
    borough_match = source_records["borough"].map(clean_text).eq(
        legacy_results["sigungu"].map(clean_text)
    )
    if not (name_match & borough_match).all():
        bad = source_records.loc[~(name_match & borough_match), "source_record_id"].tolist()
        raise ValueError(f"인수 결과 행 순서 불일치: {bad[:10]}")

    result = source_records.reset_index(drop=True).copy()
    legacy = legacy_results.reset_index(drop=True)
    for source_column, target_column in LEGACY_COLUMN_MAP.items():
        result[target_column] = legacy.get(source_column, pd.NA)
    result["latitude"] = _numeric_column(legacy, "위도")
    result["longitude"] = _numeric_column(legacy, "경도")

    coordinate_metadata = result.apply(_coordinate_metadata, axis=1, result_type="expand")
    coordinate_metadata.columns = [
        "coord_source",
        "coord_status",
        "coord_confidence",
        "coord_review_status",
    ]
    result[coordinate_metadata.columns] = coordinate_metadata
    result["matched_road_address"] = result["legacy_matched_road_address"]
    result["matched_jibun_address"] = result["legacy_matched_jibun_address"]
    result["matched_adm_cd"] = ""
    result["query_used"] = ""
    result["coord_error"] = result["legacy_coord_error"].fillna("")

    # The inherited area is building-level and must never become facility net area silently.
    has_legacy_area = pd.to_numeric(result["legacy_usable_area_m2"], errors="coerce").notna()
    result["facility_net_area_m2"] = pd.NA
    result["facility_area_scope"] = has_legacy_area.map(
        {True: "UNVERIFIED_BUILDING_OR_HEURISTIC", False: "UNKNOWN"}
    )
    result["facility_area_confidence"] = "NONE"
    result["legacy_capacity_excluded"] = True
    result["legacy_capacity_usage"] = "AUDIT_ONLY_DO_NOT_USE_AS_SUPPLY"

    for column in (
        "capacity_registered",
        "capacity_fire",
        "capacity_seats",
        "peak_concurrent_observed",
        "capacity_operational_confirmed",
    ):
        result[column] = pd.NA

    key_address = result["matched_road_address"].fillna(result["address_search"])
    result["entity_match_key"] = [
        _entity_key(name, address)
        for name, address in zip(result["facility_name"], key_address, strict=True)
    ]
    result["entity_review_status"] = "UNREVIEWED"
    same_entity = result["entity_match_key"].duplicated(keep=False)
    result.loc[same_entity, "entity_review_status"] = "REVIEW_POSSIBLE_CROSS_SOURCE"

    normalized_address = key_address.map(_normalized_entity_text)
    same_address = normalized_address.ne("") & normalized_address.duplicated(keep=False)
    result.loc[
        same_address & ~same_entity, "entity_review_status"
    ] = "REVIEW_SHARED_ADDRESS_DO_NOT_AUTO_MERGE"
    return apply_capacity_scenarios(result)


def validate_master(master: pd.DataFrame) -> None:
    if master["source_record_id"].duplicated().any():
        raise ValueError("facility master에 중복 source_record_id 존재")
    if master["physical_facility_id"].duplicated().any():
        raise ValueError("검토 전 physical_facility_id가 중복되어 이중집계 위험 존재")

    latitude_present = pd.to_numeric(master["latitude"], errors="coerce").notna()
    longitude_present = pd.to_numeric(master["longitude"], errors="coerce").notna()
    if not latitude_present.equals(longitude_present):
        raise ValueError("위도 또는 경도만 존재하는 불완전 좌표 쌍")

    unavailable = master["availability_status"].eq("UNAVAILABLE")
    scenario_columns = ["capacity_strict_unknown", "capacity_legal_nominal"]
    if master.loc[unavailable, scenario_columns].to_numpy().any():
        raise ValueError("비운영 시설에 0보다 큰 P0 공급량 존재")
    if not master["legacy_capacity_excluded"].all():
        raise ValueError("legacy capacity proxy가 공급량으로 허용된 행 존재")


def facility_profile(
    master: pd.DataFrame, *, generated_at: datetime | None = None
) -> dict[str, Any]:
    timestamp = generated_at or datetime.now(UTC)
    center_mask = master["p0_service_eligible"].astype(bool)
    coord_complete = pd.to_numeric(master["latitude"], errors="coerce").notna()
    return {
        "generated_at": timestamp.isoformat(),
        "readiness": "PROVISIONAL_NOT_READY_FOR_FINAL_OPTIMIZATION",
        "rows": len(master),
        "source_datasets": master["source_dataset"].value_counts().sort_index().to_dict(),
        "operational_status": master["operational_status"].value_counts().to_dict(),
        "p0_senior_centers": int(center_mask.sum()),
        "coordinates": {
            "complete": int(coord_complete.sum()),
            "missing": int((~coord_complete).sum()),
            "by_source": master["coord_source"].value_counts().to_dict(),
            "by_status": master["coord_status"].value_counts().to_dict(),
        },
        "capacity": {
            "operational_known": int(master["capacity_operational"].notna().sum()),
            "legacy_proxy_excluded": int(master["legacy_capacity_excluded"].sum()),
            "strict_unknown_total": int(master["capacity_strict_unknown"].sum()),
            "legal_nominal_total": int(master["capacity_legal_nominal"].sum()),
            "legal_nominal_center_rows": int(
                (center_mask & master["capacity_legal_nominal"].eq(20)).sum()
            ),
        },
        "entity_resolution": {
            "physical_links_resolved": int(master["physical_link_status"].eq("RESOLVED").sum()),
            "rows_requiring_review": int(
                master["entity_review_status"].ne("UNREVIEWED").sum()
            ),
        },
        "blocking_gaps": [
            "경로당 3,644곳의 행별 운영상태 미제공",
            "신고 이용정원과 실제 최대 동시이용자 미제공",
            "기존 좌표 대부분의 공식 API 재검증 미완료",
            "교차원천 physical_facility_id 확정 미완료",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--senior-centers", type=Path, required=True)
    parser.add_argument("--social-facilities", type=Path, required=True)
    parser.add_argument("--senior-classes", type=Path, required=True)
    parser.add_argument("--legacy-results", type=Path, required=True)
    parser.add_argument(
        "--source-output",
        type=Path,
        default=Path("data/facilities/processed/facility-source-records.csv"),
    )
    parser.add_argument(
        "--master-output",
        type=Path,
        default=Path("data/facilities/processed/facility-master.csv"),
    )
    parser.add_argument(
        "--profile-output",
        type=Path,
        default=Path("report/facility-data-profile.json"),
    )
    args = parser.parse_args()

    source_records = build_source_records(
        args.senior_centers,
        args.social_facilities,
        args.senior_classes,
    )
    legacy_results = pd.read_csv(args.legacy_results, encoding="utf-8-sig")
    master = attach_legacy_enrichment(source_records, legacy_results)
    validate_master(master)

    args.source_output.parent.mkdir(parents=True, exist_ok=True)
    source_records.to_csv(args.source_output, index=False, encoding="utf-8-sig")
    args.master_output.parent.mkdir(parents=True, exist_ok=True)
    master.to_csv(args.master_output, index=False, encoding="utf-8-sig")
    args.profile_output.parent.mkdir(parents=True, exist_ok=True)
    args.profile_output.write_text(
        json.dumps(facility_profile(master), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"source records: {len(source_records):,} -> {args.source_output}")
    print(f"facility master: {len(master):,} -> {args.master_output}")
    print(f"profile -> {args.profile_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
