from __future__ import annotations

import pandas as pd
import pytest

from welfaremap.facilities.capacity_request import REQUEST_COLUMNS, build_capacity_request


def test_request_contains_only_p0_records_and_no_legacy_capacity() -> None:
    master = pd.DataFrame(
        [
            {
                "source_record_id": "center:1",
                "facility_name": "가 경로당",
                "borough": "종로구",
                "matched_road_address": "서울특별시 종로구 길 1",
                "address_search": "서울특별시 종로구 옛길 1",
                "operational_status": "UNKNOWN_SOURCE_MIXED",
                "availability_status": "UNKNOWN",
                "p0_service_eligible": True,
                "legacy_capacity_proxy": 8,
            },
            {
                "source_record_id": "class:1",
                "facility_name": "나 교실",
                "borough": "종로구",
                "matched_road_address": pd.NA,
                "address_search": "서울특별시 종로구 길 2",
                "operational_status": "ACTIVE_REPORTED",
                "availability_status": "AVAILABLE",
                "p0_service_eligible": False,
                "legacy_capacity_proxy": 90,
            },
        ]
    )

    result = build_capacity_request(master)

    assert result.columns.tolist() == REQUEST_COLUMNS
    assert result["source_record_id"].tolist() == ["center:1"]
    assert result.iloc[0]["current_address"] == "서울특별시 종로구 길 1"
    assert result.iloc[0]["capacity_operational_confirmed"] == ""
    assert result.iloc[0]["capacity_registered"] == ""
    assert result.iloc[0]["historical_capacity_registered_candidate"] == ""
    assert "legacy_capacity_proxy" not in result
    assert result.iloc[0]["request_status"] == "PENDING_DISTRICT_REGISTER"


def test_request_prefills_stale_reference_without_promoting_it() -> None:
    master = pd.DataFrame(
        [
            {
                "source_record_id": "center:1",
                "facility_name": "가 경로당",
                "borough": "종로구",
                "matched_road_address": "서울특별시 종로구 길 1",
                "address_search": "서울특별시 종로구 옛길 1",
                "operational_status": "UNKNOWN_SOURCE_MIXED",
                "availability_status": "UNKNOWN",
                "p0_service_eligible": True,
            }
        ]
    )
    candidates = pd.DataFrame(
        [
            {
                "source_record_id": "center:1",
                "historical_source_record_id": "legacy:1",
                "permit_number_raw": "3070000201000001",
                "capacity_registered_historical_candidate": 36,
                "match_tier": "T1_EXACT_NAME_BOROUGH_UNIQUE",
                "candidate_status": "REVIEW_REQUIRED_STALE_POSITIVE",
                "source_as_of_upper_bound": "2024-05-24",
                "requires_current_register_verification": True,
                "may_use_as_operational_capacity": False,
            }
        ]
    )

    row = build_capacity_request(master, candidates).iloc[0]

    assert row["historical_source_record_id"] == "legacy:1"
    assert row["historical_permit_number_raw"] == "3070000201000001"
    assert row["historical_capacity_registered_candidate"] == "36"
    assert row["capacity_registered"] == ""
    assert "공급 사용 금지" in row["historical_capacity_review_note"]


def test_unsafe_duplicate_or_unknown_historical_reference_fails_closed() -> None:
    master = pd.DataFrame(
        [
            {
                "source_record_id": "center:1",
                "facility_name": "가 경로당",
                "borough": "종로구",
                "matched_road_address": "서울특별시 종로구 길 1",
                "address_search": "서울특별시 종로구 옛길 1",
                "operational_status": "UNKNOWN_SOURCE_MIXED",
                "availability_status": "UNKNOWN",
                "p0_service_eligible": True,
            }
        ]
    )
    candidate = {
        "source_record_id": "center:1",
        "historical_source_record_id": "legacy:1",
        "permit_number_raw": "3070000201000001",
        "capacity_registered_historical_candidate": 36,
        "match_tier": "T1_EXACT_NAME_BOROUGH_UNIQUE",
        "candidate_status": "REVIEW_REQUIRED_STALE_POSITIVE",
        "source_as_of_upper_bound": "2024-05-24",
        "requires_current_register_verification": True,
        "may_use_as_operational_capacity": False,
    }

    with pytest.raises(ValueError, match="중복"):
        build_capacity_request(master, pd.DataFrame([candidate, candidate]))

    with pytest.raises(ValueError, match="P0 request에 없는"):
        build_capacity_request(
            master, pd.DataFrame([{**candidate, "source_record_id": "center:999"}])
        )

    with pytest.raises(ValueError, match="운영 공급"):
        build_capacity_request(
            master,
            pd.DataFrame([{**candidate, "may_use_as_operational_capacity": True}]),
        )
