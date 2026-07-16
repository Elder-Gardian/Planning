from __future__ import annotations

import pandas as pd

from welfaremap.facilities.geocode import (
    coordinate_scope,
    decode_juso_web_coordinates,
    merge_recovered_coordinates,
    normalize_address,
    records_needing_geocode,
    request_fingerprint,
    select_address_candidate,
    select_web_coordinate_candidate,
)


def test_address_normalization_adds_city_borough_and_number_spacing() -> None:
    assert normalize_address("다산로32, 2층", "중구") == "서울특별시 중구 다산로 32, 2층"
    assert normalize_address("왕십리로39길30", "성동구") == "서울특별시 성동구 왕십리로39길 30"
    assert normalize_address("청계천로400", "성동") == "서울특별시 성동구 청계천로 400"


def test_placeholder_address_is_rejected() -> None:
    assert normalize_address("-", "강동구") == ""
    assert normalize_address("서울특별시 -", "") == ""


def test_external_address_is_not_prefixed_with_owner_borough() -> None:
    address = normalize_address("충청남도 태안군 안면읍 중신로343", "동작구")

    assert address == "충청남도 태안군 안면읍 중신로 343"


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


def test_web_fallback_requires_exact_official_adm_code() -> None:
    candidates: list[dict[str, object]] = [
        {"admCd": "1129010100", "d": "", "k": ""},
        {"admCd": "1123010100", "d": 1, "k": 2},
        {"admCd": "1129010100", "d": 3, "k": 4},
    ]

    selected = select_web_coordinate_candidate(candidates, "1129010100")

    assert selected == candidates[2]
    assert select_web_coordinate_candidate(candidates, "1111010100") is None


def test_web_coordinate_decoder_reverses_documented_transform() -> None:
    east, north = 953_901.165, 1_952_032.542
    encoded_east = east * 0.3 + 100_000
    encoded_north = north * 0.3 + 100_000

    longitude, latitude = decode_juso_web_coordinates(encoded_east, encoded_north)

    assert 126.9 < longitude < 127.1
    assert 37.4 < latitude < 37.7


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


def test_failed_recovery_can_fill_string_lineage_read_as_float_nan() -> None:
    facilities = pd.DataFrame(
        [
            {
                "source_record_id": "a",
                "latitude": pd.NA,
                "longitude": pd.NA,
                "matched_adm_cd": float("nan"),
                "coord_error": float("nan"),
            }
        ]
    )
    recovered = pd.DataFrame(
        [
            {
                "source_record_id": "a",
                "latitude": pd.NA,
                "longitude": pd.NA,
                "matched_adm_cd": "",
                "coord_error": "주소검색 결과 없음",
            }
        ]
    )

    result = merge_recovered_coordinates(facilities, recovered)

    assert result.iloc[0]["matched_adm_cd"] == ""
    assert result.iloc[0]["coord_error"] == "주소검색 결과 없음"


def test_only_missing_records_with_valid_address_are_geocode_targets() -> None:
    facilities = pd.DataFrame(
        [
            {
                "source_record_id": "complete",
                "latitude": 37.5,
                "longitude": 127.0,
                "address_search": "서울특별시 종로구 길 1",
            },
            {
                "source_record_id": "missing",
                "latitude": pd.NA,
                "longitude": pd.NA,
                "address_search": "서울특별시 종로구 길 2",
            },
            {
                "source_record_id": "invalid",
                "latitude": pd.NA,
                "longitude": pd.NA,
                "address_search": "",
            },
        ]
    )

    targets = records_needing_geocode(facilities)

    assert targets["source_record_id"].tolist() == ["missing"]
