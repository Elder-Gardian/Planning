from __future__ import annotations

import pandas as pd
import pytest

from welfaremap.facilities.capacity import apply_capacity_scenarios
from welfaremap.facilities.capacity_response import apply_capacity_responses


def _master() -> pd.DataFrame:
    return apply_capacity_scenarios(
        pd.DataFrame(
            [
                {
                    "source_record_id": "center:1",
                    "p0_service_eligible": True,
                    "operational_status": "UNKNOWN_SOURCE_MIXED",
                    "availability_status": "UNKNOWN",
                },
                {
                    "source_record_id": "center:2",
                    "p0_service_eligible": True,
                    "operational_status": "UNKNOWN_SOURCE_MIXED",
                    "availability_status": "UNKNOWN",
                },
            ]
        )
    )


def _response(**overrides: object) -> dict[str, object]:
    response: dict[str, object] = {
        "source_record_id": "center:1",
        "register_as_of": "2026-07-17",
        "operational_status_confirmed": "ACTIVE",
        "capacity_operational_confirmed": "",
        "capacity_registered": 42,
        "capacity_fire": 36,
        "capacity_seats": 30,
        "facility_net_area_m2": "",
        "facility_area_scope": "",
        "facility_area_confidence": "",
        "peak_concurrent_observed": 22,
        "peak_observation_period": "2026-06 평일 오후",
        "opening_hours": "09:00-18:00",
        "source_document_id": "DISTRICT-REGISTER-1",
        "source_document_url": "",
        "verified_by": "자치구 담당자",
        "verification_note": "설치신고대장 확인",
        "request_status": "VERIFIED_DISTRICT_REGISTER",
    }
    response.update(overrides)
    return response


def test_verified_active_response_applies_bounded_operational_capacity() -> None:
    result = apply_capacity_responses(_master(), pd.DataFrame([_response()]))
    row = result.loc[result["source_record_id"].eq("center:1")].iloc[0]

    assert row["operational_status"] == "ACTIVE_CONFIRMED"
    assert row["availability_status"] == "AVAILABLE"
    assert row["capacity_operational"] == 30
    assert row["capacity_strict_unknown"] == 30
    assert row["capacity_legal_nominal"] == 30
    assert row["capacity_register_as_of"] == "2026-07-17"
    assert bool(row["capacity_response_applied"])


def test_confirmed_unavailable_response_forces_both_scenarios_to_zero() -> None:
    response = _response(
        operational_status_confirmed="CLOSED",
        capacity_operational_confirmed=50,
    )

    row = apply_capacity_responses(_master(), pd.DataFrame([response])).iloc[0]

    assert row["availability_status"] == "UNAVAILABLE"
    assert row["capacity_operational"] == 50
    assert row["capacity_strict_unknown"] == 0
    assert row["capacity_legal_nominal"] == 0


def test_pending_response_is_not_applied() -> None:
    response = _response(request_status="PENDING_DISTRICT_REGISTER")

    row = apply_capacity_responses(_master(), pd.DataFrame([response])).iloc[0]

    assert row["operational_status"] == "UNKNOWN_SOURCE_MIXED"
    assert row["capacity_strict_unknown"] == 0
    assert row["capacity_legal_nominal"] == 20
    assert not bool(row["capacity_response_applied"])


def test_nullable_pending_cells_are_treated_as_blank() -> None:
    response = _response(
        request_status="PENDING_DISTRICT_REGISTER",
        capacity_registered=pd.NA,
        operational_status_confirmed=pd.NA,
    )

    row = apply_capacity_responses(_master(), pd.DataFrame([response])).iloc[0]

    assert row["capacity_legal_nominal"] == 20
    assert not bool(row["capacity_response_applied"])


@pytest.mark.parametrize(
    ("overrides", "error"),
    [
        ({"capacity_registered": -1}, "음수"),
        ({"capacity_registered": 20.5}, "정수"),
        ({"operational_status_confirmed": "MAYBE"}, "operational_status_confirmed"),
        ({"register_as_of": "not-a-date"}, "register_as_of"),
        ({"source_document_id": "", "source_document_url": ""}, "근거 문서"),
        ({"verified_by": ""}, "verified_by"),
        (
            {"facility_net_area_m2": 50, "facility_area_scope": "WHOLE_BUILDING"},
            "FACILITY_NET_VERIFIED",
        ),
    ],
)
def test_invalid_verified_response_fails_closed(
    overrides: dict[str, object], error: str
) -> None:
    with pytest.raises(ValueError, match=error):
        apply_capacity_responses(_master(), pd.DataFrame([_response(**overrides)]))


def test_duplicate_or_unknown_ids_fail_closed() -> None:
    duplicate = pd.DataFrame([_response(), _response()])
    with pytest.raises(ValueError, match="중복"):
        apply_capacity_responses(_master(), duplicate)

    unknown = pd.DataFrame([_response(source_record_id="center:999")])
    with pytest.raises(ValueError, match="master에 없는"):
        apply_capacity_responses(_master(), unknown)
