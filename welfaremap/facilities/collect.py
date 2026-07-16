"""Download and fingerprint the official Seoul senior-center source snapshot."""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

import requests

SEOUL_SENIOR_CENTER_DATASET_ID = "OA-15052"
SEOUL_SENIOR_CENTER_PAGE = "https://data.seoul.go.kr/dataList/OA-15052/S/1/datasetView.do"
SEOUL_BIGFILE_DOWNLOAD_URL = "https://datafile.seoul.go.kr/bigfile/iot/inf/nio_download.do"
SEOUL_SENIOR_CENTER_DOWNLOAD_FORM = {
    "infId": SEOUL_SENIOR_CENTER_DATASET_ID,
    "seq": "4",
    "infSeq": "1",
}


class PostSession(Protocol):
    def post(
        self, url: str, *, data: dict[str, str], timeout: float
    ) -> requests.Response: ...


@dataclass(frozen=True)
class CollectedFile:
    dataset_id: str
    dataset_page: str
    download_url: str
    source_as_of: str
    retrieved_at: str
    path: str
    byte_size: int
    sha256: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def collect_seoul_senior_centers(
    destination: Path,
    *,
    session: PostSession | None = None,
    timeout_seconds: float = 60,
    retrieved_at: datetime | None = None,
) -> CollectedFile:
    """Fetch the current official workbook and return reproducibility metadata."""
    http = session or requests.Session()
    response = http.post(
        SEOUL_BIGFILE_DOWNLOAD_URL,
        data=SEOUL_SENIOR_CENTER_DOWNLOAD_FORM,
        timeout=timeout_seconds,
    )
    response.raise_for_status()
    content = response.content
    if len(content) < 1_000 or not content.startswith(b"PK"):
        raise RuntimeError("서울시 경로당 배포 파일이 유효한 XLSX가 아님")

    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(content)
    timestamp = retrieved_at or datetime.now(UTC)
    return CollectedFile(
        dataset_id=SEOUL_SENIOR_CENTER_DATASET_ID,
        dataset_page=SEOUL_SENIOR_CENTER_PAGE,
        download_url=SEOUL_BIGFILE_DOWNLOAD_URL,
        source_as_of="2025-06-30",
        retrieved_at=timestamp.isoformat(),
        path=str(destination),
        byte_size=len(content),
        sha256=sha256_bytes(content),
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/facilities/raw/seoul-senior-centers-2025-06.xlsx"),
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("data/facilities/raw/seoul-senior-centers-2025-06.manifest.json"),
    )
    args = parser.parse_args()

    collected = collect_seoul_senior_centers(args.output)
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(
        json.dumps(collected.to_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(collected.to_dict(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
