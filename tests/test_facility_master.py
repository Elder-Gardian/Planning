from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd
import pytest

from welfaremap.facilities.master import (
    attach_legacy_enrichment,
    facility_profile,
    validate_master,
)


def _source_rows() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "source_record_id": "center:1",
                "physical_facility_id": "physical:1",
                "physical_link_status": "UNRESOLVED",
                "source_dataset": "centers",
                "facility_name": "가 경로당",
                "facility_type": "SENIOR_CENTER",
                "borough": "성북구",
                "address_search": "서울특별시 성북구 길 1",
                "operational_status": "UNKNOWN_SOURCE_MIXED",
                "availability_status": "UNKNOWN",
                "p0_service_eligible": True,
            },
            {
                "source_record_id": "class:1",
                "physical_facility_id": "physical:2",
                "physical_link_status": "UNRESOLVED",
                "source_dataset": "classes",
                "facility_name": "나 교실",
                "facility_type": "SENIOR_CLASS",
                "borough": "성북구",
                "address_search": "서울특별시 성북구 길 2",
                "operational_status": "SUSPENDED_REPORTED",
                "availability_status": "UNAVAILABLE",
                "p0_service_eligible": False,
            },
        ]
    )


def _legacy_rows() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "facility_name": "가 경로당",
                "sigungu": "성북구",
                "matched_road_address": "서울특별시 성북구 길 1",
                "matched_jibun_address": "",
                "usable_area_m2": 45_536,
                "estimated_capacity": 8,
                "capacity_method": "fixed_imputation",
                "confidence": "LOW",
                "위도": 37.6,
                "경도": 127.0,
                "coord_method": "주소검색",
                "coord_error": "",
            },
            {
                "facility_name": "나 교실",
                "sigungu": "성북구",
                "matched_road_address": "서울특별시 성북구 길 2",
                "matched_jibun_address": "",
                "usable_area_m2": pd.NA,
                "estimated_capacity": 90,
                "capacity_method": "area",
                "confidence": "HIGH",
                "위도": pd.NA,
                "경도": pd.NA,
                "coord_method": pd.NA,
                "coord_error": "none",
            },
        ]
    )


def test_legacy_proxy_and_building_area_stay_out_of_canonical_capacity() -> None:
    result = attach_legacy_enrichment(_source_rows(), _legacy_rows())
    center = result.iloc[0]

    assert center["legacy_capacity_proxy"] == 8
    assert center["legacy_capacity_excluded"]
    assert pd.isna(center["facility_net_area_m2"])
    assert pd.isna(center["capacity_operational"])
    assert center["capacity_strict_unknown"] == 0
    assert center["capacity_legal_nominal"] == 20
    assert center["coord_source"] == "LEGACY_JUSO_WEB_UNVERIFIED"


def test_inactive_non_p0_row_has_zero_supply_and_missing_coordinate() -> None:
    result = attach_legacy_enrichment(_source_rows(), _legacy_rows())
    inactive = result.iloc[1]

    assert inactive["capacity_strict_unknown"] == 0
    assert inactive["capacity_legal_nominal"] == 0
    assert inactive["coord_status"] == "MISSING"
    validate_master(result)


def test_legacy_row_order_mismatch_fails_closed() -> None:
    legacy = _legacy_rows().iloc[::-1].reset_index(drop=True)

    with pytest.raises(ValueError, match="행 순서 불일치"):
        attach_legacy_enrichment(_source_rows(), legacy)


def test_profile_reports_provisional_readiness_and_capacity_gap() -> None:
    master = attach_legacy_enrichment(_source_rows(), _legacy_rows())

    profile = facility_profile(
        master,
        generated_at=datetime(2026, 7, 17, tzinfo=UTC),
    )

    assert profile["readiness"] == "PROVISIONAL_NOT_READY_FOR_FINAL_OPTIMIZATION"
    assert profile["coordinates"]["complete"] == 1
    assert profile["capacity"]["operational_known"] == 0
    assert profile["capacity"]["legal_nominal_total"] == 20
