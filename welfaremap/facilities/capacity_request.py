"""Prepare a prefilled district-register request table for P0 senior centers."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

REQUEST_COLUMNS = [
    "source_record_id",
    "facility_name",
    "borough",
    "current_address",
    "current_operational_status",
    "current_availability_status",
    "register_as_of",
    "operational_status_confirmed",
    "capacity_operational_confirmed",
    "capacity_registered",
    "capacity_fire",
    "capacity_seats",
    "facility_net_area_m2",
    "facility_area_scope",
    "facility_area_confidence",
    "peak_concurrent_observed",
    "peak_observation_period",
    "opening_hours",
    "source_document_id",
    "source_document_url",
    "verified_by",
    "verification_note",
    "request_status",
]


def build_capacity_request(master: pd.DataFrame) -> pd.DataFrame:
    """Export one request row per P0 service record without using legacy proxies."""
    p0 = master[master["p0_service_eligible"].astype(bool)].copy()
    result = pd.DataFrame(
        {
            "source_record_id": p0["source_record_id"],
            "facility_name": p0["facility_name"],
            "borough": p0["borough"],
            "current_address": p0["matched_road_address"].fillna(p0["address_search"]),
            "current_operational_status": p0["operational_status"],
            "current_availability_status": p0["availability_status"],
        }
    )
    for column in REQUEST_COLUMNS[6:-1]:
        result[column] = ""
    result["request_status"] = "PENDING_DISTRICT_REGISTER"
    if result["source_record_id"].duplicated().any():
        raise ValueError("capacity request에 중복 source_record_id 존재")
    return result[REQUEST_COLUMNS].sort_values(["borough", "source_record_id"])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    master = pd.read_csv(args.input, encoding="utf-8-sig")
    request = build_capacity_request(master)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    request.to_csv(args.output, index=False, encoding="utf-8-sig")
    print(f"capacity register request: {len(request):,} -> {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
