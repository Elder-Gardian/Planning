from __future__ import annotations

import pandas as pd

from welfaremap.facilities.geocode import (
    coordinate_scope,
    merge_recovered_coordinates,
    normalize_address,
    request_fingerprint,
    select_address_candidate,
)


def test_address_normalization_adds_city_borough_and_number_spacing() -> None:
    assert normalize_address("다산로32, 2층", "중구") == "서울특별시 중구 다산로 32, 2층"
    assert normalize_address("왕십리로39길30", "성동구") == "서울특별시 성동구 왕십리로39길 30"
    assert normalize_address("청계천로400", "성동") == "서울특별시 성동구 청계천로 400"


def test_placeholder_address_is_rejected() -> None:
    assert normalize_address("-", "강동구") == ""
    assert normalize_address("서울특별시 -", "") == ""


def test_wrong_borough_candidate_is_never_accepted() -> None:
    candidate = {
        "roadAddrPart1": "서울특별시 동대문구 보문로 1",
        "jibunAddr": "서울특별시 동대문구 신설동 1",
        "sggNm": "동대문구",
        "admCd": "1123010100",
        "rnMgtSn": "1",
        "udrtYn": "0",
        "buldMnnm": "1",
        "buldSlno": "0",
    }

    assert select_address_candidate([candidate], "서울특별시 성북구 보문로 1", "성북구") is None


def test_api_key_rotation_does_not_invalidate_cache_fingerprint() -> None:
    before = request_fingerprint("juso-search", {"confmKey": "old", "keyword": "주소"})
    after = request_fingerprint("juso-search", {"confmKey": "new", "keyword": "주소"})

    assert before == after


def test_outside_seoul_is_classified_not_discarded() -> None:
    assert coordinate_scope(126.978, 37.566) == "IN_SERVICE_AREA"
    assert coordinate_scope(126.297, 36.746) == "OUTSIDE_SERVICE_AREA"


def test_existing_coordinates_are_not_overwritten_and_merge_is_id_based() -> None:
    facilities = pd.DataFrame(
        [
            {"source_record_id": "a", "latitude": 37.5, "longitude": 127.0},
            {"source_record_id": "b", "latitude": pd.NA, "longitude": pd.NA},
        ]
    )
    recovered = pd.DataFrame(
        [
            {
                "source_record_id": "b",
                "latitude": 37.6,
                "longitude": 127.1,
                "coord_source": "JUSO_OFFICIAL",
            },
            {
                "source_record_id": "a",
                "latitude": 1.0,
                "longitude": 1.0,
                "coord_source": "JUSO_OFFICIAL",
            },
        ]
    )

    result = merge_recovered_coordinates(facilities, recovered)

    assert result.loc[result["source_record_id"] == "a", "latitude"].item() == 37.5
    assert result.loc[result["source_record_id"] == "b", "latitude"].item() == 37.6
