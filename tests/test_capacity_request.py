from __future__ import annotations

import pandas as pd

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
    assert "legacy_capacity_proxy" not in result
    assert result.iloc[0]["request_status"] == "PENDING_DISTRICT_REGISTER"
