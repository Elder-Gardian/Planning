from __future__ import annotations

import pandas as pd

from welfaremap.facilities.capacity import apply_capacity_scenarios


def _row(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "source_record_id": "center:1",
        "p0_service_eligible": True,
        "availability_status": "UNKNOWN",
    }
    base.update(overrides)
    return base


def test_unknown_center_is_zero_in_strict_and_twenty_only_in_nominal() -> None:
    result = apply_capacity_scenarios(pd.DataFrame([_row()])).iloc[0]

    assert result["capacity_strict_unknown"] == 0
    assert result["capacity_legal_nominal"] == 20
    assert result["capacity_legal_nominal_source"] == "LEGAL_MIN_PROXY_STATUS_UNVERIFIED"
    assert pd.isna(result["capacity_operational"])


def test_unavailable_or_ineligible_facility_never_receives_legal_proxy() -> None:
    frame = pd.DataFrame(
        [
            _row(availability_status="UNAVAILABLE"),
            _row(p0_service_eligible=False, availability_status="AVAILABLE"),
        ]
    )

    result = apply_capacity_scenarios(frame)

    assert result["capacity_strict_unknown"].tolist() == [0, 0]
    assert result["capacity_legal_nominal"].tolist() == [0, 0]


def test_registered_capacity_is_bounded_by_fire_and_seats() -> None:
    frame = pd.DataFrame(
        [
            _row(
                availability_status="AVAILABLE",
                capacity_registered=42,
                capacity_fire=36,
                capacity_seats=30,
            )
        ]
    )

    result = apply_capacity_scenarios(frame).iloc[0]

    assert result["capacity_operational"] == 30
    assert result["capacity_source"] == "REGISTERED_WITH_BOUNDS"
    assert result["capacity_confidence"] == "HIGH"
    assert result["capacity_strict_unknown"] == 30
    assert result["capacity_legal_nominal"] == 30


def test_registered_only_is_retained_with_missing_bound_warning() -> None:
    result = apply_capacity_scenarios(
        pd.DataFrame(
            [_row(availability_status="AVAILABLE", capacity_registered=35)]
        )
    ).iloc[0]

    assert result["capacity_operational"] == 35
    assert result["capacity_confidence"] == "MEDIUM"
    assert result["capacity_missing_bounds"] == "fire,seats"


def test_whole_building_area_never_becomes_capacity() -> None:
    result = apply_capacity_scenarios(
        pd.DataFrame(
            [
                _row(
                    facility_net_area_m2=45_536,
                    facility_area_scope="WHOLE_BUILDING",
                    facility_area_confidence="HIGH",
                )
            ]
        )
    ).iloc[0]

    assert pd.isna(result["capacity_area_fire_proxy"])
    assert pd.isna(result["capacity_operational"])


def test_verified_net_area_is_only_a_separate_fire_proxy() -> None:
    result = apply_capacity_scenarios(
        pd.DataFrame(
            [
                _row(
                    facility_net_area_m2=61,
                    facility_area_scope="FACILITY_NET_VERIFIED",
                    facility_area_confidence="MEDIUM",
                )
            ]
        )
    ).iloc[0]

    assert result["capacity_area_fire_proxy"] == 20
    assert pd.isna(result["capacity_operational"])
    assert result["capacity_legal_nominal"] == 20
