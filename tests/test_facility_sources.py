from __future__ import annotations

from pathlib import Path

import pandas as pd

from welfaremap.facilities.sources import (
    build_source_records,
    parse_senior_centers,
    parse_senior_classes,
    parse_social_facilities,
)


def _write_center_workbook(path: Path) -> None:
    rows: list[list[object]] = [[None] * 9 for _ in range(8)]
    rows[6] = [
        1,
        "서울",
        "종로구",
        "노인여가복지시설",
        "가 경로당",
        "종로구 길 1",
        "종로구",
        "과",
        "1",
    ]
    rows[7] = [
        2,
        "서울",
        "종로구",
        "노인여가복지시설",
        "나 경로당",
        "종로구 길 1",
        "종로구",
        "과",
        "2",
    ]
    pd.DataFrame(rows).to_excel(path, header=False, index=False)


def _write_class_workbook(path: Path) -> None:
    rows: list[list[object]] = [[None] * 9 for _ in range(8)]
    rows[5][2:9] = [1, "종로", "운영 교실", "종로구 길 2", "2020", "1", None]
    rows[6][2:9] = [2, None, "휴지 교실", "종로구 길 3", "2020", "2", "(휴지중)"]
    rows[7][2:9] = [3, None, "폐지 교실", "-", "2020", "3", "폐지"]
    pd.DataFrame(rows).to_excel(path, header=False, index=False)


def _write_social_csv(path: Path) -> None:
    pd.DataFrame(
        [
            {
                "시설명": "운영 교실",
                "시설코드": "A001",
                "시설종류명(시설유형)": "노인복지시설",
                "시설종류상세명(시설종류)": "노인교실",
                "자치구(시)구분": "자치구",
                "시군구코드": "1111000000",
                "시군구명": "종로구",
                "시설주소": "서울특별시 종로구 길 2",
                "전화번호": "1",
                "우편번호": "00000",
            }
        ]
    ).to_csv(path, encoding="cp949", index=False)


def test_center_rows_keep_distinct_source_and_physical_ids(tmp_path: Path) -> None:
    path = tmp_path / "centers.xlsx"
    _write_center_workbook(path)

    result = parse_senior_centers(path)

    assert result["source_record_id"].tolist() == [
        "seoul-senior-center:2025-06:0001",
        "seoul-senior-center:2025-06:0002",
    ]
    assert result["physical_facility_id"].nunique() == 2
    assert result["address_search"].eq("서울특별시 종로구 길 1").all()
    assert result["availability_status"].eq("UNKNOWN").all()


def test_class_status_and_forward_filled_borough_are_retained(tmp_path: Path) -> None:
    path = tmp_path / "classes.xlsx"
    _write_class_workbook(path)

    result = parse_senior_classes(path)

    assert result["borough"].tolist() == ["종로구", "종로구", "종로구"]
    assert result["operational_status"].tolist() == [
        "ACTIVE_REPORTED",
        "SUSPENDED_REPORTED",
        "CLOSED_REPORTED",
    ]
    assert result["availability_status"].tolist() == [
        "AVAILABLE",
        "UNAVAILABLE",
        "UNAVAILABLE",
    ]
    assert result.iloc[2]["address_search"] == ""


def test_social_facility_code_is_not_lost(tmp_path: Path) -> None:
    path = tmp_path / "social.csv"
    _write_social_csv(path)

    result = parse_social_facilities(path)

    assert result.iloc[0]["source_record_id"] == "seoul-social-facility:A001"
    assert result.iloc[0]["source_facility_code"] == "A001"


def test_cross_source_same_place_is_not_automatically_merged(tmp_path: Path) -> None:
    center_path = tmp_path / "centers.xlsx"
    class_path = tmp_path / "classes.xlsx"
    social_path = tmp_path / "social.csv"
    _write_center_workbook(center_path)
    _write_class_workbook(class_path)
    _write_social_csv(social_path)

    result = build_source_records(center_path, social_path, class_path)
    matching = result[result["facility_name"] == "운영 교실"]

    assert len(result) == 6
    assert len(matching) == 2
    assert matching["physical_facility_id"].nunique() == 2
    assert matching["physical_link_status"].eq("UNRESOLVED").all()
    assert result.loc[result["facility_type"] == "SENIOR_CENTER", "p0_service_eligible"].all()
    assert not result.loc[result["facility_type"] != "SENIOR_CENTER", "p0_service_eligible"].any()
