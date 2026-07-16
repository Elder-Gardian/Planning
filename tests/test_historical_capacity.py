from __future__ import annotations

import pandas as pd
import pytest

from welfaremap.facilities.historical_capacity import (
    build_historical_capacity_candidates,
    historical_capacity_profile,
)


def _master() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "source_record_id": "current:1",
                "facility_name": "한빛 경로당",
                "borough": "종로구",
                "address_search": "서울특별시 종로구 길 1",
                "p0_service_eligible": True,
            },
            {
                "source_record_id": "current:2",
                "facility_name": "푸른(아) 제1경로당",
                "borough": "종로구",
                "address_search": "서울특별시 종로구 길 2",
                "p0_service_eligible": True,
            },
            {
                "source_record_id": "current:3",
                "facility_name": "푸른(아) 제2경로당",
                "borough": "종로구",
                "address_search": "서울특별시 종로구 길 3",
                "p0_service_eligible": True,
            },
            {
                "source_record_id": "current:4",
                "facility_name": "중앙경로당",
                "borough": "종로구",
                "address_search": "서울특별시 종로구 길 4",
                "p0_service_eligible": True,
            },
            {
                "source_record_id": "current:5",
                "facility_name": "중앙경로당",
                "borough": "종로구",
                "address_search": "서울특별시 종로구 길 5",
                "p0_service_eligible": True,
            },
            {
                "source_record_id": "class:1",
                "facility_name": "교실",
                "borough": "종로구",
                "address_search": "서울특별시 종로구 길 6",
                "p0_service_eligible": False,
            },
        ]
    )


def _legacy() -> pd.DataFrame:
    base = {
        "도로명전체주소": "",
        "폐업일자": "",
        "휴업시작일자": "",
        "휴업종료일자": "",
        "재개업일자": "",
        "소재지면적": "",
        "소재지우편번호": "",
        "자격소유인원수": "",
        "영업상태명": "운영중",
        "상세영업상태명": "운영",
    }
    return pd.DataFrame(
        [
            {
                **base,
                "번호": "101",
                "사업장명": "한빛 경로당",
                "소재지전체주소": "서울특별시 종로구 종로동 1",
                "인허가일자": "20100101",
                "입소정원": "30.0",
                "총인원수": "19.0",
                "인허가번호": "3070000201000001",
            },
            {
                **base,
                "번호": "102",
                "사업장명": "푸른아파트 제1경로당",
                "소재지전체주소": "서울특별시 종로구 종로동 2",
                "인허가일자": "20100102",
                "입소정원": "42.0",
                "총인원수": "25.0",
                "인허가번호": "3070000201000002",
            },
            {
                **base,
                "번호": "103",
                "사업장명": "푸른아파트 제2경로당",
                "소재지전체주소": "서울특별시 종로구 종로동 3",
                "인허가일자": "20100103",
                "입소정원": "0.0",
                "총인원수": "",
                "인허가번호": "3070000201000003",
            },
            {
                **base,
                "번호": "104",
                "사업장명": "중앙경로당",
                "소재지전체주소": "서울특별시 종로구 종로동 4",
                "인허가일자": "20100104",
                "입소정원": "20.0",
                "총인원수": "",
                "인허가번호": "3070000201000004",
            },
        ]
    )


def test_builds_review_candidates_without_promoting_operational_capacity() -> None:
    result = build_historical_capacity_candidates(_master(), _legacy())

    assert result["source_record_id"].tolist() == ["current:1", "current:2", "current:3"]
    assert result["match_tier"].tolist() == [
        "T1_EXACT_NAME_BOROUGH_UNIQUE",
        "T2_GENERIC_ALIAS_NAME_BOROUGH_UNIQUE",
        "T2_GENERIC_ALIAS_NAME_BOROUGH_UNIQUE",
    ]
    assert result["capacity_registered_historical_candidate"].tolist()[:2] == [30, 42]
    assert pd.isna(result.iloc[2]["capacity_registered_historical_candidate"])
    assert result.iloc[2]["candidate_status"] == "ZERO_TREATED_AS_MISSING"
    assert not result["may_use_as_operational_capacity"].any()
    assert result["requires_current_register_verification"].all()
    assert result.iloc[0]["permit_number_raw"] == "3070000201000001"


def test_identity_tokens_and_duplicate_names_are_not_auto_matched() -> None:
    result = build_historical_capacity_candidates(_master(), _legacy())

    assert set(result["facility_name"]) >= {
        "푸른(아) 제1경로당",
        "푸른(아) 제2경로당",
    }
    assert not result["facility_name"].eq("중앙경로당").any()


def test_profile_reports_reference_coverage_and_zero_operational_additions() -> None:
    candidates = build_historical_capacity_candidates(_master(), _legacy())

    profile = historical_capacity_profile(_master(), _legacy(), candidates)

    assert profile["legacy_rows"] == 4
    assert profile["current_p0_rows"] == 5
    assert profile["matched_rows"] == 3
    assert profile["matched_positive_capacity_candidates"] == 2
    assert profile["matched_zero_treated_as_missing"] == 1
    assert profile["operational_capacity_rows_added"] == 0


@pytest.mark.parametrize("capacity", ["-1", "20.5", "not-a-number"])
def test_invalid_historical_capacity_fails_closed(capacity: str) -> None:
    legacy = _legacy()
    legacy.loc[0, "입소정원"] = capacity

    with pytest.raises(ValueError, match="입소정원"):
        build_historical_capacity_candidates(_master(), legacy)


def test_missing_required_column_or_duplicate_sequence_fails_closed() -> None:
    with pytest.raises(ValueError, match="필수 열 누락"):
        build_historical_capacity_candidates(_master(), _legacy().drop(columns="입소정원"))

    duplicate = pd.concat([_legacy(), _legacy().iloc[[0]]], ignore_index=True)
    with pytest.raises(ValueError, match="중복"):
        build_historical_capacity_candidates(_master(), duplicate)
