from __future__ import annotations

import pandas as pd
import pytest

from welfaremap.facilities.capacity import apply_capacity_scenarios
from welfaremap.facilities.overrides import apply_facility_overrides


def _master() -> pd.DataFrame:
    return apply_capacity_scenarios(
        pd.DataFrame(
            [
                {
                    "source_record_id": "center:1",
                    "p0_service_eligible": True,
                    "availability_status": "UNKNOWN",
                    "operational_status": "UNKNOWN_SOURCE_MIXED",
                    "status_note": "",
                    "latitude": pd.NA,
                    "longitude": pd.NA,
                    "coord_status": "MISSING",
                    "coord_error": "missing",
                },
                {
                    "source_record_id": "center:2",
                    "p0_service_eligible": True,
                    "availability_status": "UNKNOWN",
                    "operational_status": "UNKNOWN_SOURCE_MIXED",
                    "status_note": "",
                    "latitude": 37.5,
                    "longitude": 127.0,
                    "coord_status": "PROVISIONAL_IN_SERVICE_AREA",
                    "coord_error": "",
                },
            ]
        )
    )


def test_override_fills_missing_coordinate_and_preserves_evidence() -> None:
    overrides = pd.DataFrame(
        [
            {
                "source_record_id": "center:1",
                "latitude": 37.6,
                "longitude": 127.1,
                "coord_source": "PUBLIC_STANDARD_VILLAGE_HALL",
                "coord_confidence": "HIGH",
                "coordinate_evidence_url": "https://example.test/record",
            }
        ]
    )

    result = apply_facility_overrides(_master(), overrides).iloc[0]

    assert result["latitude"] == 37.6
    assert result["coord_status"] == "IN_SERVICE_AREA"
    assert result["coordinate_evidence_url"] == "https://example.test/record"


def test_coordinate_replacement_requires_explicit_approval() -> None:
    overrides = pd.DataFrame(
        [{"source_record_id": "center:2", "latitude": 37.6, "longitude": 127.1}]
    )

    with pytest.raises(ValueError, match="교체 승인 없음"):
        apply_facility_overrides(_master(), overrides)


def test_unavailable_status_override_recomputes_legal_nominal_to_zero() -> None:
    overrides = pd.DataFrame(
        [
            {
                "source_record_id": "center:1",
                "operational_status_override": "RECONSTRUCTION_REPORTED",
                "availability_status_override": "UNAVAILABLE",
                "status_note_override": "공식 현황 재건축중",
            }
        ]
    )

    result = apply_facility_overrides(_master(), overrides).iloc[0]

    assert result["operational_status"] == "RECONSTRUCTION_REPORTED"
    assert result["capacity_strict_unknown"] == 0
    assert result["capacity_legal_nominal"] == 0


def test_unknown_source_id_fails_closed() -> None:
    overrides = pd.DataFrame([{"source_record_id": "missing"}])

    with pytest.raises(ValueError, match="master에 없는"):
        apply_facility_overrides(_master(), overrides)
