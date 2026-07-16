from __future__ import annotations

from pathlib import Path

import pytest

from welfaremap.facilities.osm_geocode import (
    MINIMUM_INTERVAL_SECONDS,
    NominatimCache,
    NominatimClient,
    select_nominatim_candidate,
)


def test_exact_facility_name_candidate_is_accepted() -> None:
    candidate = {
        "display_name": "아름경로당, 78, 휘경로, 동대문구, 서울특별시, 대한민국",
        "lat": "37.5",
        "lon": "127.0",
    }

    result = select_nominatim_candidate(
        [candidate],
        facility_name="아름경로당",
        expected_borough="동대문구",
        normalized_address="서울특별시 동대문구 휘경로 78",
    )

    assert result == (candidate, "HIGH")


def test_exact_road_number_is_accepted_but_road_only_is_rejected() -> None:
    road_only = {
        "display_name": "섬밭로, 하계동, 노원구, 서울특별시, 대한민국",
        "lat": "37.5",
        "lon": "127.0",
    }
    exact = {
        "display_name": "64, 삼성로147길, 강남구, 서울특별시, 대한민국",
        "lat": "37.5",
        "lon": "127.0",
    }

    assert (
        select_nominatim_candidate(
            [road_only],
            facility_name="현우경로당",
            expected_borough="노원구",
            normalized_address="서울특별시 노원구 섬밭로 272",
        )
        is None
    )
    assert select_nominatim_candidate(
        [exact],
        facility_name="재너머",
        expected_borough="강남구",
        normalized_address="서울특별시 강남구 삼성로147길 64",
    ) == (exact, "MEDIUM")


def test_public_service_rate_limit_cannot_be_disabled(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match=r"1\.05초"):
        NominatimClient(
            NominatimCache(tmp_path / "cache.sqlite3"),
            user_agent="test",
            interval_seconds=MINIMUM_INTERVAL_SECONDS - 0.01,
        )
