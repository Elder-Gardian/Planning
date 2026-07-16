"""Apply evidence-backed facility corrections by stable source record ID."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd

from welfaremap.facilities.capacity import apply_capacity_scenarios
from welfaremap.facilities.geocode import clean_text, coordinate_scope

COORDINATE_OVERRIDE_COLUMNS = (
    "latitude",
    "longitude",
    "coord_source",
    "coord_confidence",
    "coord_review_status",
    "matched_road_address",
    "coordinate_evidence_dataset",
    "coordinate_evidence_url",
    "coordinate_evidence_as_of",
    "coordinate_note",
)


def _truthy(value: Any) -> bool:
    return clean_text(value).lower() in {"1", "true", "yes", "y"}


def _optional_text(value: Any) -> str:
    return clean_text(value)


def _float_or_none(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return None if pd.isna(number) else number


def apply_facility_overrides(
    master: pd.DataFrame, overrides: pd.DataFrame
) -> pd.DataFrame:
    """Apply reviewed corrections and recompute capacity scenarios after status changes."""
    if overrides["source_record_id"].duplicated().any():
        raise ValueError("override에 중복 source_record_id 존재")
    known_ids = set(master["source_record_id"])
    unknown_ids = set(overrides["source_record_id"]) - known_ids
    if unknown_ids:
        raise ValueError(f"master에 없는 override ID: {sorted(unknown_ids)}")

    result = master.copy()
    for column in COORDINATE_OVERRIDE_COLUMNS:
        if column not in result:
            result[column] = pd.NA
        if column not in {"latitude", "longitude"}:
            result[column] = result[column].astype("object")

    result_index = pd.Series(result.index, index=result["source_record_id"])
    for override in overrides.to_dict("records"):
        source_record_id = str(override["source_record_id"])
        index = int(result_index[source_record_id])
        latitude = _float_or_none(override.get("latitude"))
        longitude = _float_or_none(override.get("longitude"))
        if latitude is not None and longitude is not None:
            existing = _float_or_none(result.at[index, "latitude"]) is not None
            if existing and not _truthy(override.get("allow_coordinate_replace")):
                raise ValueError(f"기존 좌표 교체 승인 없음: {source_record_id}")
            result.at[index, "latitude"] = latitude
            result.at[index, "longitude"] = longitude
            result.at[index, "coord_status"] = coordinate_scope(longitude, latitude)
            for column in COORDINATE_OVERRIDE_COLUMNS[2:]:
                value = _optional_text(override.get(column))
                if value:
                    result.at[index, column] = value
            result.at[index, "coord_error"] = ""

        operational_status = _optional_text(override.get("operational_status_override"))
        availability_status = _optional_text(override.get("availability_status_override"))
        status_note = _optional_text(override.get("status_note_override"))
        if operational_status:
            result.at[index, "operational_status"] = operational_status
        if availability_status:
            result.at[index, "availability_status"] = availability_status
        if status_note:
            result.at[index, "status_note"] = status_note

    return apply_capacity_scenarios(result)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--overrides", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--profile-output", type=Path)
    args = parser.parse_args()

    master = pd.read_csv(args.input, encoding="utf-8-sig")
    overrides = pd.read_csv(args.overrides, encoding="utf-8-sig")
    corrected = apply_facility_overrides(master, overrides)

    from welfaremap.facilities.master import facility_profile, validate_master

    validate_master(corrected)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    corrected.to_csv(args.output, index=False, encoding="utf-8-sig")
    if args.profile_output:
        args.profile_output.parent.mkdir(parents=True, exist_ok=True)
        args.profile_output.write_text(
            json.dumps(facility_profile(corrected), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
