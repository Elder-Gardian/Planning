"""Normalize Seoul senior-facility source files without losing source identity."""

from __future__ import annotations

import hashlib
import math
import re
from pathlib import Path
from typing import Any

import pandas as pd

SOURCE_COLUMNS = [
    "source_record_id",
    "physical_facility_id",
    "physical_link_status",
    "source_dataset",
    "source_as_of",
    "source_sequence",
    "facility_name",
    "facility_type",
    "service_type",
    "borough",
    "address_raw",
    "address_search",
    "phone",
    "operational_status",
    "availability_status",
    "status_note",
    "installed_date_raw",
    "source_facility_code",
    "source_authority",
    "source_department",
    "p0_service_eligible",
]


def clean_text(value: Any) -> str:
    """Return a compact string while treating spreadsheet nulls as empty."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def _int_text(value: Any) -> str:
    number = pd.to_numeric(value, errors="coerce")
    if pd.isna(number):
        return ""
    return str(int(number))


def _seoul_address(address: Any) -> str:
    text = clean_text(address)
    if not text or text == "-":
        return ""
    text = re.sub(r"^서울시특별시\s*", "서울특별시 ", text)
    text = re.sub(r"^서울시\s*", "서울특별시 ", text)
    text = re.sub(r"^서울\s+", "서울특별시 ", text)
    if text.startswith("서울특별시") or re.match(r"^[가-힣]+(?:도|광역시|특별자치도)\s", text):
        return text
    return f"서울특별시 {text}"


def _unresolved_physical_id(source_record_id: str) -> str:
    digest = hashlib.sha256(source_record_id.encode("utf-8")).hexdigest()[:16]
    return f"physical:unresolved:{digest}"


def _base_record(source_record_id: str) -> dict[str, Any]:
    return {
        "source_record_id": source_record_id,
        "physical_facility_id": _unresolved_physical_id(source_record_id),
        "physical_link_status": "UNRESOLVED",
    }


def parse_senior_centers(path: Path) -> pd.DataFrame:
    """Parse the Seoul senior-center workbook (data begins at Excel row 7)."""
    raw = pd.read_excel(path, header=None, dtype=object)
    body = raw.iloc[6:, :9].copy()
    body.columns = [
        "sequence",
        "city",
        "borough",
        "source_type",
        "name",
        "address",
        "authority",
        "department",
        "phone",
    ]
    body = body[body["sequence"].notna() & body["name"].notna()]

    records: list[dict[str, Any]] = []
    for row in body.to_dict("records"):
        sequence = _int_text(row["sequence"])
        source_record_id = f"seoul-senior-center:2025-06:{int(sequence):04d}"
        record = _base_record(source_record_id)
        record.update(
            {
                "source_dataset": "SEOUL_SENIOR_CENTER_2025_06",
                "source_as_of": "2025-06-30",
                "source_sequence": sequence,
                "facility_name": clean_text(row["name"]),
                "facility_type": "SENIOR_CENTER",
                "service_type": "SENIOR_CENTER",
                "borough": clean_text(row["borough"]),
                "address_raw": clean_text(row["address"]),
                "address_search": _seoul_address(row["address"]),
                "phone": clean_text(row["phone"]),
                # The source explicitly mixes operating/planned/inactive rows but has no row status.
                "operational_status": "UNKNOWN_SOURCE_MIXED",
                "availability_status": "UNKNOWN",
                "status_note": "원천 파일이 운영·운영예정·미운영·휴지·폐지를 행별 구분 없이 포함",
                "installed_date_raw": "",
                "source_facility_code": "",
                "source_authority": clean_text(row["authority"]),
                "source_department": clean_text(row["department"]),
                "p0_service_eligible": True,
            }
        )
        records.append(record)
    return pd.DataFrame.from_records(records, columns=SOURCE_COLUMNS)


def _class_status(note: Any) -> tuple[str, str]:
    text = clean_text(note)
    if "폐지" in text:
        return "CLOSED_REPORTED", "UNAVAILABLE"
    if "미운영" in text:
        return "NOT_OPERATING_REPORTED", "UNAVAILABLE"
    if "휴지" in text:
        return "SUSPENDED_REPORTED", "UNAVAILABLE"
    if text:
        return "UNKNOWN_NOTE", "UNKNOWN"
    return "ACTIVE_REPORTED", "AVAILABLE"


def parse_senior_classes(path: Path) -> pd.DataFrame:
    """Parse the Seoul senior-class workbook and retain inactive status notes."""
    raw = pd.read_excel(path, header=None, dtype=object)
    body = raw.iloc[5:, 2:9].copy()
    body.columns = ["sequence", "borough", "name", "address", "installed", "phone", "note"]
    body = body[body["sequence"].notna() & body["name"].notna()].copy()
    body["borough"] = body["borough"].ffill()

    records: list[dict[str, Any]] = []
    for row in body.to_dict("records"):
        sequence = _int_text(row["sequence"])
        source_record_id = f"seoul-senior-class:2025-04:{int(sequence):04d}"
        operational_status, availability_status = _class_status(row["note"])
        borough = clean_text(row["borough"])
        if borough and not borough.endswith("구"):
            borough = f"{borough}구"
        record = _base_record(source_record_id)
        record.update(
            {
                "source_dataset": "SEOUL_SENIOR_CLASS_2025_04",
                "source_as_of": "2025-04-30",
                "source_sequence": sequence,
                "facility_name": clean_text(row["name"]),
                "facility_type": "SENIOR_CLASS",
                "service_type": "SENIOR_CLASS",
                "borough": borough,
                "address_raw": clean_text(row["address"]),
                "address_search": _seoul_address(row["address"]),
                "phone": clean_text(row["phone"]),
                "operational_status": operational_status,
                "availability_status": availability_status,
                "status_note": clean_text(row["note"]),
                "installed_date_raw": clean_text(row["installed"]),
                "source_facility_code": "",
                "source_authority": "서울특별시",
                "source_department": "",
                "p0_service_eligible": False,
            }
        )
        records.append(record)
    return pd.DataFrame.from_records(records, columns=SOURCE_COLUMNS)


def parse_social_facilities(path: Path) -> pd.DataFrame:
    """Parse the Seoul social-facility CSV and preserve its facility code."""
    try:
        raw = pd.read_csv(path, encoding="utf-8-sig", dtype=object)
    except UnicodeDecodeError:
        raw = pd.read_csv(path, encoding="cp949", dtype=object)

    records: list[dict[str, Any]] = []
    for index, row in enumerate(raw.to_dict("records"), start=1):
        code = clean_text(row.get("시설코드"))
        source_record_id = f"seoul-social-facility:{code or f'row-{index:04d}'}"
        record = _base_record(source_record_id)
        record.update(
            {
                "source_dataset": "SEOUL_SOCIAL_FACILITY_SNAPSHOT",
                "source_as_of": "UNKNOWN",
                "source_sequence": str(index),
                "facility_name": clean_text(row.get("시설명")),
                "facility_type": clean_text(row.get("시설종류명(시설유형)")),
                "service_type": clean_text(row.get("시설종류상세명(시설종류)")),
                "borough": clean_text(row.get("시군구명")),
                "address_raw": clean_text(row.get("시설주소")),
                "address_search": _seoul_address(row.get("시설주소")),
                "phone": clean_text(row.get("전화번호")),
                "operational_status": "UNKNOWN",
                "availability_status": "UNKNOWN",
                "status_note": "원천에 행별 운영상태 없음",
                "installed_date_raw": "",
                "source_facility_code": code,
                "source_authority": clean_text(row.get("자치구(시)구분")),
                "source_department": "",
                "p0_service_eligible": False,
            }
        )
        records.append(record)
    return pd.DataFrame.from_records(records, columns=SOURCE_COLUMNS)


def build_source_records(
    senior_center_path: Path,
    social_facility_path: Path,
    senior_class_path: Path,
) -> pd.DataFrame:
    """Build the canonical source-record table in stable source order."""
    frames = [
        parse_senior_centers(senior_center_path),
        parse_social_facilities(social_facility_path),
        parse_senior_classes(senior_class_path),
    ]
    result = pd.concat(frames, ignore_index=True)
    if result["source_record_id"].duplicated().any():
        duplicates = result.loc[result["source_record_id"].duplicated(), "source_record_id"]
        raise ValueError(f"중복 source_record_id: {duplicates.tolist()}")
    if result["physical_facility_id"].duplicated().any():
        raise ValueError("미확정 physical_facility_id가 원천 행 사이에서 중복됨")
    return result
