"""Canonical concurrent-capacity fields and explicit uncertainty scenarios."""

from __future__ import annotations

import math
from typing import Any

import pandas as pd

CAPACITY_MODEL_VERSION = "CAPACITY_V1_2026-07-17"
URBAN_SENIOR_CENTER_LEGAL_MIN = 20
CONSERVATIVE_UNKNOWN_ROOM_LOAD_M2 = 3.0

NUMERIC_INPUT_COLUMNS = (
    "capacity_registered",
    "capacity_fire",
    "capacity_seats",
    "peak_concurrent_observed",
    "capacity_operational_confirmed",
    "facility_net_area_m2",
)


def _number(value: Any) -> float | None:
    number = pd.to_numeric(value, errors="coerce")
    if pd.isna(number) or float(number) < 0:
        return None
    return float(number)


def _whole_people(value: float | None) -> int | None:
    if value is None:
        return None
    return math.floor(value)


def _operational_capacity(row: pd.Series) -> tuple[int | None, str, str, str]:
    confirmed = _whole_people(_number(row.get("capacity_operational_confirmed")))
    if confirmed is not None:
        return confirmed, "CONFIRMED_OPERATIONAL", "HIGH", ""

    registered = _whole_people(_number(row.get("capacity_registered")))
    if registered is None:
        return None, "UNKNOWN", "LOW", "registered,fire,seats"

    fire = _whole_people(_number(row.get("capacity_fire")))
    seats = _whole_people(_number(row.get("capacity_seats")))
    known_bounds = [registered, *(value for value in (fire, seats) if value is not None)]
    missing = [
        name
        for name, value in (("fire", fire), ("seats", seats))
        if value is None
    ]
    source = "REGISTERED_WITH_BOUNDS" if len(known_bounds) > 1 else "REGISTERED_ONLY"
    confidence = "HIGH" if not missing else "MEDIUM"
    return min(known_bounds), source, confidence, ",".join(missing)


def _area_fire_proxy(row: pd.Series) -> int | None:
    if row.get("facility_area_scope") != "FACILITY_NET_VERIFIED":
        return None
    confidence = str(row.get("facility_area_confidence", "")).upper()
    if confidence not in {"HIGH", "MEDIUM"}:
        return None
    area = _number(row.get("facility_net_area_m2"))
    if area is None or area <= 0:
        return None
    return math.floor(area / CONSERVATIVE_UNKNOWN_ROOM_LOAD_M2)


def _scenario_values(row: pd.Series) -> tuple[int, int, str]:
    eligible = bool(row.get("p0_service_eligible", False))
    availability = str(row.get("availability_status", "UNKNOWN"))
    operational = _whole_people(_number(row.get("capacity_operational")))

    if not eligible or availability == "UNAVAILABLE":
        return 0, 0, "INELIGIBLE_OR_UNAVAILABLE"

    strict = operational if availability == "AVAILABLE" and operational is not None else 0
    if operational is not None:
        nominal = operational
        nominal_source = str(row.get("capacity_source", "OBSERVED_OR_REGISTERED"))
    else:
        nominal = URBAN_SENIOR_CENTER_LEGAL_MIN
        nominal_source = "LEGAL_MIN_PROXY_STATUS_UNVERIFIED"
    return strict, nominal, nominal_source


def apply_capacity_scenarios(facilities: pd.DataFrame) -> pd.DataFrame:
    """Add capacity lineage and P0 scenarios without treating proxies as observations.

    ``STRICT_UNKNOWN`` supplies zero unless both availability and operational capacity
    are confirmed. ``LEGAL_NOMINAL`` uses the current urban senior-center statutory
    minimum only as an explicit sensitivity assumption for otherwise eligible rows.
    """
    result = facilities.copy()
    for column in NUMERIC_INPUT_COLUMNS:
        if column not in result:
            result[column] = pd.NA
        result[column] = pd.to_numeric(result[column], errors="coerce")
    for column in ("facility_area_scope", "facility_area_confidence"):
        if column not in result:
            result[column] = ""

    derived = result.apply(_operational_capacity, axis=1, result_type="expand")
    derived.columns = [
        "capacity_operational",
        "capacity_source",
        "capacity_confidence",
        "capacity_missing_bounds",
    ]
    result[derived.columns] = derived
    result["capacity_area_fire_proxy"] = [
        _area_fire_proxy(row) for _, row in result.iterrows()
    ]
    result["capacity_regulatory_min"] = result["p0_service_eligible"].map(
        {True: URBAN_SENIOR_CENTER_LEGAL_MIN, False: pd.NA}
    )

    scenarios = result.apply(_scenario_values, axis=1, result_type="expand")
    scenarios.columns = [
        "capacity_strict_unknown",
        "capacity_legal_nominal",
        "capacity_legal_nominal_source",
    ]
    result[scenarios.columns] = scenarios
    result["capacity_unit"] = "PERSONS_CONCURRENT"
    result["capacity_model_version"] = CAPACITY_MODEL_VERSION
    return result
