"""One-time, policy-compliant Nominatim recovery for residual coordinate gaps."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
import time
from pathlib import Path
from typing import Any

import pandas as pd
import requests

from welfaremap.facilities.geocode import (
    GeocodeResult,
    clean_text,
    coordinate_scope,
    geocode_results_frame,
    merge_recovered_coordinates,
    normalize_address,
    normalize_borough,
    records_needing_geocode,
)

NOMINATIM_SEARCH_URL = "https://nominatim.openstreetmap.org/search"
NOMINATIM_POLICY_URL = "https://operations.osmfoundation.org/policies/nominatim/"
OSM_COPYRIGHT_URL = "https://www.openstreetmap.org/copyright"
MINIMUM_INTERVAL_SECONDS = 1.05


def _compact(value: Any) -> str:
    return re.sub(r"[^0-9A-Za-z가-힣]", "", clean_text(value)).lower()


def _road_and_number(address: str) -> tuple[str, str] | None:
    match = re.search(
        r"(\S+(?:로\d*[가-힣]*길|길|로))\s+(\d+(?:-\d+)?)",
        address,
    )
    return (match.group(1), match.group(2)) if match else None


def select_nominatim_candidate(
    candidates: list[dict[str, Any]],
    *,
    facility_name: Any,
    expected_borough: Any,
    normalized_address: str,
) -> tuple[dict[str, Any], str] | None:
    """Accept exact facility-name or road-and-building-number evidence only."""
    borough = _compact(normalize_borough(expected_borough))
    facility = _compact(facility_name)
    road_number = _road_and_number(normalized_address)
    for candidate in candidates:
        display = clean_text(candidate.get("display_name"))
        compact_display = _compact(display)
        if borough and borough not in compact_display:
            continue
        if "서울특별시" not in display and "서울" not in display:
            continue
        if facility and facility in compact_display:
            return candidate, "HIGH"
        if road_number:
            road, number = road_number
            number_match = bool(re.search(rf"(?:^|\D){re.escape(number)}(?:\D|$)", display))
            if _compact(road) in compact_display and number_match:
                return candidate, "MEDIUM"
    return None


class NominatimCache:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path)
        self.connection.execute(
            "CREATE TABLE IF NOT EXISTS searches ("
            "query_hash TEXT PRIMARY KEY, query TEXT NOT NULL, payload TEXT NOT NULL, "
            "retrieved_at TEXT DEFAULT CURRENT_TIMESTAMP)"
        )
        self.connection.commit()

    def get(self, query: str) -> list[dict[str, Any]] | None:
        query_hash = hashlib.sha256(query.encode()).hexdigest()
        row = self.connection.execute(
            "SELECT payload FROM searches WHERE query_hash=?", (query_hash,)
        ).fetchone()
        return json.loads(row[0]) if row else None

    def put(self, query: str, payload: list[dict[str, Any]]) -> None:
        query_hash = hashlib.sha256(query.encode()).hexdigest()
        self.connection.execute(
            "INSERT OR REPLACE INTO searches(query_hash, query, payload) VALUES (?, ?, ?)",
            (query_hash, query, json.dumps(payload, ensure_ascii=False)),
        )
        self.connection.commit()


class NominatimClient:
    def __init__(
        self,
        cache: NominatimCache,
        *,
        user_agent: str,
        interval_seconds: float = MINIMUM_INTERVAL_SECONDS,
        session: requests.Session | None = None,
    ):
        if interval_seconds < MINIMUM_INTERVAL_SECONDS:
            raise ValueError("Nominatim 공개 서비스는 요청 간격 1.05초 이상 필요")
        self.cache = cache
        self.user_agent = user_agent
        self.interval_seconds = interval_seconds
        self.session = session or requests.Session()
        self.last_request_at = 0.0

    def search(self, query: str) -> list[dict[str, Any]]:
        cached = self.cache.get(query)
        if cached is not None:
            return cached
        elapsed = time.monotonic() - self.last_request_at
        if elapsed < self.interval_seconds:
            time.sleep(self.interval_seconds - elapsed)
        params: dict[str, str | int] = {
            "q": query,
            "format": "jsonv2",
            "limit": 5,
            "countrycodes": "kr",
            "addressdetails": 1,
        }
        response = self.session.get(
            NOMINATIM_SEARCH_URL,
            params=params,
            headers={"User-Agent": self.user_agent},
            timeout=30,
        )
        self.last_request_at = time.monotonic()
        response.raise_for_status()
        payload: list[dict[str, Any]] = response.json()
        self.cache.put(query, payload)
        return payload

    def geocode(
        self,
        source_record_id: str,
        facility_name: Any,
        raw_address: Any,
        expected_borough: Any,
    ) -> GeocodeResult:
        normalized = normalize_address(raw_address, expected_borough)
        facility_query = (
            f"{clean_text(facility_name)}, "
            f"{normalize_borough(expected_borough)}, 서울특별시"
        )
        queries = list(
            dict.fromkeys(
                query
                for query in (
                    normalized,
                    facility_query,
                )
                if clean_text(query)
            )
        )
        errors: list[str] = []
        for query in queries:
            try:
                candidates = self.search(query)
                selected = select_nominatim_candidate(
                    candidates,
                    facility_name=facility_name,
                    expected_borough=expected_borough,
                    normalized_address=normalized,
                )
                if selected is None:
                    errors.append(f"엄격 일치 후보 없음: {query}")
                    continue
                candidate, confidence = selected
                latitude = round(float(candidate["lat"]), 7)
                longitude = round(float(candidate["lon"]), 7)
                return GeocodeResult(
                    source_record_id,
                    latitude,
                    longitude,
                    "OPENSTREETMAP_NOMINATIM_VALIDATED",
                    coordinate_scope(longitude, latitude),
                    confidence,
                    "REVIEW_REQUIRED",
                    clean_text(candidate.get("display_name")),
                    "",
                    "",
                    query,
                    "",
                )
            except (KeyError, TypeError, ValueError, requests.RequestException) as exc:
                errors.append(str(exc))
        return GeocodeResult(
            source_record_id,
            None,
            None,
            "OPENSTREETMAP_NOMINATIM",
            "NO_VALIDATED_MATCH",
            "NONE",
            "REVIEW_REQUIRED",
            "",
            "",
            "",
            queries[-1] if queries else "",
            " | ".join(dict.fromkeys(errors)),
        )


def main() -> int:
    parser = argparse.ArgumentParser(
        epilog=f"정책 확인 필수: {NOMINATIM_POLICY_URL} / attribution: {OSM_COPYRIGHT_URL}"
    )
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--recovery-output", type=Path, required=True)
    parser.add_argument("--profile-output", type=Path)
    parser.add_argument(
        "--cache",
        type=Path,
        default=Path("data/facilities/cache/nominatim.sqlite3"),
    )
    parser.add_argument(
        "--user-agent",
        default="WelfareMap-AI-facility-recovery/0.1 (one-time research dataset repair)",
    )
    parser.add_argument("--accept-osm-policy", action="store_true")
    args = parser.parse_args()
    if not args.accept_osm_policy:
        parser.error(f"--accept-osm-policy 필요: {NOMINATIM_POLICY_URL}")

    facilities = pd.read_csv(args.input, encoding="utf-8-sig")
    targets = records_needing_geocode(facilities)
    targets = targets[targets["p0_service_eligible"].astype(bool)]
    client = NominatimClient(NominatimCache(args.cache), user_agent=args.user_agent)
    results: list[GeocodeResult] = []
    for count, row in enumerate(targets.itertuples(index=False), start=1):
        result = client.geocode(
            str(row.source_record_id),
            row.facility_name,
            row.address_search,
            row.borough,
        )
        results.append(result)
        complete = sum(item.latitude is not None for item in results)
        print(f"Nominatim {count:,}/{len(targets):,} / success {complete:,}", flush=True)

    recovery = geocode_results_frame(results)
    args.recovery_output.parent.mkdir(parents=True, exist_ok=True)
    recovery.to_csv(args.recovery_output, index=False, encoding="utf-8-sig")
    merged = merge_recovered_coordinates(facilities, recovery)

    from welfaremap.facilities.master import facility_profile, validate_master

    validate_master(merged)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    merged.to_csv(args.output, index=False, encoding="utf-8-sig")
    if args.profile_output:
        args.profile_output.parent.mkdir(parents=True, exist_ok=True)
        args.profile_output.write_text(
            json.dumps(facility_profile(merged), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
