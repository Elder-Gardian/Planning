from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import requests

from welfaremap.facilities.collect import collect_seoul_senior_centers, sha256_bytes


class FakeResponse:
    def __init__(self, content: bytes):
        self.content = content

    def raise_for_status(self) -> None:
        return None


class FakeSession:
    def __init__(self, content: bytes):
        self.content = content
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def post(self, url: str, **kwargs: Any) -> requests.Response:
        self.calls.append((url, kwargs))
        return FakeResponse(self.content)  # type: ignore[return-value]


def test_collection_writes_xlsx_and_deterministic_manifest(tmp_path: Path) -> None:
    content = b"PK" + b"x" * 1_000
    session = FakeSession(content)
    destination = tmp_path / "centers.xlsx"

    result = collect_seoul_senior_centers(
        destination,
        session=session,
        retrieved_at=datetime(2026, 7, 17, tzinfo=UTC),
    )

    assert destination.read_bytes() == content
    assert result.sha256 == sha256_bytes(content)
    assert result.source_as_of == "2025-06-30"
    assert result.retrieved_at == "2026-07-17T00:00:00+00:00"
    assert session.calls[0][1]["data"]["infId"] == "OA-15052"


def test_collection_rejects_non_xlsx_response(tmp_path: Path) -> None:
    session = FakeSession(b"error page")

    try:
        collect_seoul_senior_centers(tmp_path / "bad.xlsx", session=session)
    except RuntimeError as exc:
        assert "유효한 XLSX" in str(exc)
    else:
        raise AssertionError("invalid response must fail")
