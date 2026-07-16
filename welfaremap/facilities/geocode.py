"""Official road-address geocoding with borough validation and safe caching."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sqlite3
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Protocol

import pandas as pd
import requests
from dotenv import load_dotenv
from pyproj import Transformer
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

JUSO_SEARCH_URL = "https://business.juso.go.kr/addrlink/addrLinkApi.do"
JUSO_COORD_URL = "https://business.juso.go.kr/addrlink/addrCoordApi.do"
JUSO_WEB_SEARCH_URL = "https://www.juso.go.kr/api/solr/solrKeywordSearch"
JUSO_WEB_HEADERS = {
    "Content-Type": "application/json",
    "User-Agent": "WelfareMap-Data/0.1",
    "Referer": "https://www.juso.go.kr/map/totalMapView",
    "Origin": "https://www.juso.go.kr",
}
SECRET_PARAMETER_NAMES = frozenset({"confmKey", "serviceKey", "apiKey"})
SEOUL_BOUNDS = (126.70, 127.30, 37.40, 37.75)
TRANSFORMER = Transformer.from_crs("EPSG:5179", "EPSG:4326", always_xy=True)


def clean_text(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def normalize_borough(value: Any) -> str:
    borough = clean_text(value)
    if borough and not borough.endswith("구"):
        borough = f"{borough}구"
    return borough


def normalize_address(raw_address: Any, expected_borough: Any) -> str:
    """Create a Seoul address query while rejecting placeholder-only addresses."""
    address = clean_text(raw_address)
    borough = normalize_borough(expected_borough)
    if address in {"", "-", "서울특별시 -"}:
        return ""

    address = address.replace("보문로 29다길", "보문로29다길")
    address = re.sub(r"^서울시특별시\s*", "서울특별시 ", address)
    address = re.sub(r"^서울시\s*", "서울특별시 ", address)
    address = re.sub(r"^서울\s+", "서울특별시 ", address)
    outside_seoul = bool(
        re.match(r"^(?!서울특별시)[가-힣]+(?:도|광역시|특별자치도)\s", address)
    )
    if not outside_seoul:
        address = re.sub(r"^서울특별시\s*", "", address)
        if borough and not address.startswith(borough):
            address = f"{borough} {address}"
        address = f"서울특별시 {address}"
    address = re.sub(r"\s*,\s*", ", ", address)
    address = re.sub(
        r"(\S+(?:로\d*[가-힣]*길|길|로))(\d+(?:-\d+)?)(?=[,\s(]|$)",
        r"\1 \2",
        address,
    )
    address = re.sub(r"\s+", " ", address).strip(" ,")
    return address


def address_variants(raw_address: Any, expected_borough: Any) -> list[str]:
    """Return ordered, de-duplicated queries from detailed to road-core address."""
    normalized = normalize_address(raw_address, expected_borough)
    if not normalized:
        return []
    variants = [normalized]

    without_parentheses = re.sub(r"\s*\([^)]*\)\s*", " ", normalized)
    without_details = re.sub(
        r",?\s*(?:지하\s*)?\d+층.*$|,?\s*\d+동(?:\s+\d+호)?.*$|,?\s*관리(?:사무소|동).*$",
        "",
        without_parentheses,
    )
    variants.append(clean_text(without_details).strip(" ,"))

    road_core = re.search(
        r"^(서울특별시\s+\S+구\s+.*?(?:로\d*[가-힣]*길|길|로)\s+\d+(?:-\d+)?)",
        without_details,
    )
    if road_core:
        variants.append(clean_text(road_core.group(1)))

    return list(dict.fromkeys(query for query in variants if query))


def redact_parameters(params: dict[str, Any]) -> dict[str, Any]:
    return {
        key: "<redacted>" if key in SECRET_PARAMETER_NAMES else value
        for key, value in params.items()
    }


def request_fingerprint(service: str, params: dict[str, Any]) -> str:
    """Hash the request semantics without binding the cache to rotating API keys."""
    canonical = {
        key: value for key, value in params.items() if key not in SECRET_PARAMETER_NAMES
    }
    serialized = json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(f"{service}:{serialized}".encode()).hexdigest()


class CacheProtocol(Protocol):
    def get(self, service: str, params: dict[str, Any]) -> dict[str, Any] | None: ...

    def put_success(
        self, service: str, params: dict[str, Any], payload: dict[str, Any]
    ) -> None: ...


class ResponseCache:
    """SQLite response cache containing only redacted requests and successful payloads."""

    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path)
        self.connection.execute(
            "CREATE TABLE IF NOT EXISTS responses ("
            "fingerprint TEXT PRIMARY KEY, service TEXT NOT NULL, "
            "request_redacted TEXT NOT NULL, payload TEXT NOT NULL, "
            "retrieved_at TEXT DEFAULT CURRENT_TIMESTAMP)"
        )
        self.connection.commit()

    def get(self, service: str, params: dict[str, Any]) -> dict[str, Any] | None:
        fingerprint = request_fingerprint(service, params)
        row = self.connection.execute(
            "SELECT payload FROM responses WHERE fingerprint=? AND service=?",
            (fingerprint, service),
        ).fetchone()
        return json.loads(row[0]) if row else None

    def put_success(
        self, service: str, params: dict[str, Any], payload: dict[str, Any]
    ) -> None:
        results = payload.get("results", {})
        common = results.get("common", {})
        if str(common.get("errorCode", "")) != "0" or not results.get("juso"):
            return
        fingerprint = request_fingerprint(service, params)
        self.connection.execute(
            "INSERT OR REPLACE INTO responses "
            "(fingerprint, service, request_redacted, payload) VALUES (?, ?, ?, ?)",
            (
                fingerprint,
                service,
                json.dumps(redact_parameters(params), ensure_ascii=False, sort_keys=True),
                json.dumps(payload, ensure_ascii=False),
            ),
        )
        self.connection.commit()


@dataclass(frozen=True)
class AddressMatch:
    query: str
    road_address: str
    jibun_address: str
    adm_cd: str
    rn_mgt_sn: str
    udrt_yn: str
    building_main_number: str
    building_sub_number: str
    match_confidence: str


@dataclass(frozen=True)
class GeocodeResult:
    source_record_id: str
    latitude: float | None
    longitude: float | None
    coord_source: str
    coord_status: str
    coord_confidence: str
    coord_review_status: str
    matched_road_address: str
    matched_jibun_address: str
    matched_adm_cd: str
    query_used: str
    coord_error: str


def _candidate_borough(candidate: dict[str, Any]) -> str:
    explicit = normalize_borough(candidate.get("sggNm"))
    if explicit:
        return explicit
    road_address = clean_text(candidate.get("roadAddrPart1") or candidate.get("roadAddr"))
    match = re.search(r"서울특별시\s+(\S+구)(?:\s|$)", road_address)
    return match.group(1) if match else ""


def select_address_candidate(
    candidates: list[dict[str, Any]], query: str, expected_borough: Any
) -> AddressMatch | None:
    """Select only candidates in the expected borough; never accept a wrong first hit."""
    borough = normalize_borough(expected_borough)
    eligible = [
        candidate
        for candidate in candidates
        if not borough or _candidate_borough(candidate) == borough
    ]
    if not eligible:
        return None

    compact_query = re.sub(r"[\s,()]", "", query)

    def score(candidate: dict[str, Any]) -> tuple[int, int]:
        road = clean_text(candidate.get("roadAddrPart1") or candidate.get("roadAddr"))
        compact_road = re.sub(r"[\s,()]", "", road)
        containment = int(compact_road not in compact_query and compact_query not in compact_road)
        return containment, abs(len(compact_query) - len(compact_road))

    candidate = min(eligible, key=score)
    road_address = clean_text(candidate.get("roadAddrPart1") or candidate.get("roadAddr"))
    confidence = "HIGH" if score(candidate)[0] == 0 else "MEDIUM"
    adm_cd = clean_text(candidate.get("admCd"))
    if len(adm_cd) != 10:
        return None
    return AddressMatch(
        query=query,
        road_address=road_address,
        jibun_address=clean_text(candidate.get("jibunAddr")),
        adm_cd=adm_cd,
        rn_mgt_sn=clean_text(candidate.get("rnMgtSn")),
        udrt_yn=clean_text(candidate.get("udrtYn")) or "0",
        building_main_number=clean_text(candidate.get("buldMnnm")) or "0",
        building_sub_number=clean_text(candidate.get("buldSlno")) or "0",
        match_confidence=confidence,
    )


def coordinate_scope(longitude: float, latitude: float) -> str:
    min_lon, max_lon, min_lat, max_lat = SEOUL_BOUNDS
    if min_lon <= longitude <= max_lon and min_lat <= latitude <= max_lat:
        return "IN_SERVICE_AREA"
    return "OUTSIDE_SERVICE_AREA"


def decode_juso_web_coordinates(encoded_east: float, encoded_north: float) -> tuple[float, float]:
    """Decode the map endpoint's transformed EPSG:5179 coordinate pair."""
    east = (encoded_east - 100_000.0) / 0.3
    north = (encoded_north - 100_000.0) / 0.3
    longitude, latitude = TRANSFORMER.transform(east, north)
    return round(longitude, 7), round(latitude, 7)


def select_web_coordinate_candidate(
    candidates: list[dict[str, Any]], expected_adm_cd: str
) -> dict[str, Any] | None:
    """Require the official address match's admCd; never fall back to the first row."""
    for candidate in candidates:
        if clean_text(candidate.get("admCd")) != expected_adm_cd:
            continue
        try:
            float(clean_text(candidate.get("d")))
            float(clean_text(candidate.get("k")))
        except (TypeError, ValueError):
            continue
        return candidate
    return None


class OfficialJusoClient:
    def __init__(
        self,
        search_key: str,
        coordinate_key: str,
        cache: CacheProtocol,
        *,
        interval_seconds: float = 0.05,
        timeout_seconds: float = 20,
        allow_web_fallback: bool = False,
        session: requests.Session | None = None,
    ):
        self.search_key = search_key
        self.coordinate_key = coordinate_key
        self.cache = cache
        self.interval_seconds = interval_seconds
        self.timeout_seconds = timeout_seconds
        self.allow_web_fallback = allow_web_fallback
        self.session = session or self._session_with_retries()

    @staticmethod
    def _session_with_retries() -> requests.Session:
        session = requests.Session()
        retry = Retry(
            total=4,
            connect=4,
            read=4,
            backoff_factor=0.7,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset({"GET"}),
        )
        session.mount("https://", HTTPAdapter(max_retries=retry))
        return session

    def _get(self, service: str, url: str, params: dict[str, Any]) -> dict[str, Any]:
        cached = self.cache.get(service, params)
        if cached is not None:
            return cached
        time.sleep(self.interval_seconds)
        response = self.session.get(url, params=params, timeout=self.timeout_seconds)
        response.raise_for_status()
        payload: dict[str, Any] = response.json()
        common = payload.get("results", {}).get("common", {})
        if str(common.get("errorCode", "")) != "0":
            raise RuntimeError(f"{service} {common.get('errorCode')}: {common.get('errorMessage')}")
        self.cache.put_success(service, params, payload)
        return payload

    def search(self, query: str, expected_borough: Any) -> AddressMatch | None:
        params = {
            "confmKey": self.search_key,
            "currentPage": 1,
            "countPerPage": 10,
            "keyword": query,
            "resultType": "json",
            "hstryYn": "Y",
            "firstSort": "road",
            "addInfoYn": "Y",
        }
        payload = self._get("juso-search", JUSO_SEARCH_URL, params)
        candidates = payload.get("results", {}).get("juso") or []
        return select_address_candidate(candidates, query, expected_borough)

    def coordinate(self, match: AddressMatch) -> tuple[float, float]:
        params = {
            "confmKey": self.coordinate_key,
            "admCd": match.adm_cd,
            "rnMgtSn": match.rn_mgt_sn,
            "udrtYn": match.udrt_yn,
            "buldMnnm": match.building_main_number,
            "buldSlno": match.building_sub_number,
            "resultType": "json",
        }
        payload = self._get("juso-coordinate", JUSO_COORD_URL, params)
        candidates = payload.get("results", {}).get("juso") or []
        if not candidates:
            raise RuntimeError("좌표 결과 없음")
        east = float(candidates[0]["entX"])
        north = float(candidates[0]["entY"])
        longitude, latitude = TRANSFORMER.transform(east, north)
        return round(longitude, 7), round(latitude, 7)

    def web_fallback_coordinate(self, match: AddressMatch) -> tuple[float, float]:
        payload = {
            "strSearchType": "HSTRY",
            "strFirstSort": "none",
            "strAblYn": "N",
            "strAotYn": "N",
            "strSynnYn": None,
            "strHstryYn": "Y",
            "reqFrom": "RN_SEARCH_KOR_MAP",
            "checkMoblieYn": "N",
            "strFunctionName": "Y",
            "keyword": match.road_address,
            "pageable": {
                "page": 0,
                "size": 10,
                "sort": [{"property": "", "direction": ""}],
            },
        }
        time.sleep(self.interval_seconds)
        response = self.session.post(
            JUSO_WEB_SEARCH_URL,
            json=payload,
            headers=JUSO_WEB_HEADERS,
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        body: dict[str, Any] = response.json()
        if body.get("status") != 200:
            raise RuntimeError(f"juso-web {body.get('status')}: {body.get('message')}")
        results = body.get("results") or {}
        candidates = results.get("content") or [] if isinstance(results, dict) else []
        candidate = select_web_coordinate_candidate(candidates, match.adm_cd)
        if candidate is None:
            raise RuntimeError("공식 주소 admCd와 같은 웹 좌표 후보 없음")
        encoded_east = float(candidate["d"])
        encoded_north = float(candidate["k"])
        return decode_juso_web_coordinates(encoded_east, encoded_north)

    def geocode(
        self, source_record_id: str, raw_address: Any, expected_borough: Any
    ) -> GeocodeResult:
        variants = address_variants(raw_address, expected_borough)
        if not variants:
            return GeocodeResult(
                source_record_id,
                None,
                None,
                "JUSO_OFFICIAL",
                "INVALID_INPUT",
                "NONE",
                "REVIEW_REQUIRED",
                "",
                "",
                "",
                "",
                "유효한 주소 없음",
            )

        errors: list[str] = []
        for query in variants:
            try:
                validation_borough = expected_borough if query.startswith("서울특별시") else ""
                match = self.search(query, validation_borough)
                if match is None:
                    errors.append(f"후보 없음 또는 자치구 불일치: {query}")
                    continue
                coord_source = "JUSO_OFFICIAL"
                review_status = "VERIFIED"
                coordinate_confidence = match.match_confidence
                try:
                    longitude, latitude = self.coordinate(match)
                except (KeyError, TypeError, ValueError, requests.RequestException, RuntimeError):
                    if not self.allow_web_fallback:
                        raise
                    longitude, latitude = self.web_fallback_coordinate(match)
                    coord_source = "JUSO_WEB_FALLBACK_OFFICIAL_ADDRESS_VALIDATED"
                    review_status = "REVIEW_REQUIRED"
                    coordinate_confidence = "MEDIUM"
                scope = coordinate_scope(longitude, latitude)
                return GeocodeResult(
                    source_record_id,
                    latitude,
                    longitude,
                    coord_source,
                    scope,
                    coordinate_confidence,
                    review_status,
                    match.road_address,
                    match.jibun_address,
                    match.adm_cd,
                    match.query,
                    "",
                )
            except (
                KeyError,
                TypeError,
                ValueError,
                requests.RequestException,
                RuntimeError,
            ) as exc:
                errors.append(str(exc))

        return GeocodeResult(
            source_record_id,
            None,
            None,
            "JUSO_OFFICIAL",
            "NO_VALIDATED_MATCH",
            "NONE",
            "REVIEW_REQUIRED",
            "",
            "",
            "",
            variants[-1],
            " | ".join(dict.fromkeys(errors)),
        )


def geocode_results_frame(results: list[GeocodeResult]) -> pd.DataFrame:
    return pd.DataFrame.from_records(asdict(result) for result in results)


def merge_recovered_coordinates(
    facilities: pd.DataFrame, recovered: pd.DataFrame
) -> pd.DataFrame:
    """Fill missing coordinates by source ID without replacing existing coordinates."""
    if recovered.empty:
        return facilities.copy()
    if recovered["source_record_id"].duplicated().any():
        raise ValueError("복구 좌표에 중복 source_record_id 존재")

    result = facilities.copy()
    recovery = recovered.set_index("source_record_id")
    numeric_columns = {"latitude", "longitude"}
    for column in recovered.columns:
        if column == "source_record_id":
            continue
        if column not in result:
            result[column] = pd.NA
        if column not in numeric_columns:
            result[column] = result[column].astype("object")
    for index, row in result.iterrows():
        source_record_id = row["source_record_id"]
        if source_record_id not in recovery.index:
            continue
        existing_latitude = clean_text(row.get("latitude"))
        existing_longitude = clean_text(row.get("longitude"))
        if existing_latitude and existing_longitude:
            continue
        recovered_row = recovery.loc[source_record_id]
        for column in recovered.columns:
            if column != "source_record_id":
                result.at[index, column] = recovered_row[column]
    return result


def records_needing_geocode(facilities: pd.DataFrame) -> pd.DataFrame:
    """Select records with no complete coordinate pair and a non-empty address."""
    latitude = pd.to_numeric(facilities["latitude"], errors="coerce")
    longitude = pd.to_numeric(facilities["longitude"], errors="coerce")
    address_present = facilities["address_search"].map(clean_text).ne("")
    return facilities[(latitude.isna() | longitude.isna()) & address_present].copy()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--recovery-output", type=Path, required=True)
    parser.add_argument("--profile-output", type=Path)
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument(
        "--cache",
        type=Path,
        default=Path("data/facilities/cache/juso-official.sqlite3"),
    )
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--interval", type=float, default=0.05)
    parser.add_argument("--allow-web-fallback", action="store_true")
    args = parser.parse_args()

    load_dotenv(args.env_file)
    search_key = clean_text(os.getenv("JUSO_API_KEY"))
    coordinate_key = clean_text(os.getenv("JUSO_COORD_API_KEY"))
    if not search_key or not coordinate_key:
        parser.error("JUSO_API_KEY와 JUSO_COORD_API_KEY가 필요함")

    facilities = pd.read_csv(args.input, encoding="utf-8-sig")
    targets = records_needing_geocode(facilities)
    if args.limit:
        targets = targets.head(args.limit)
    client = OfficialJusoClient(
        search_key,
        coordinate_key,
        ResponseCache(args.cache),
        interval_seconds=args.interval,
        allow_web_fallback=args.allow_web_fallback,
    )

    results: list[GeocodeResult] = []
    for count, row in enumerate(targets.itertuples(index=False), start=1):
        result = client.geocode(
            str(row.source_record_id),
            row.address_search,
            row.borough,
        )
        results.append(result)
        if count % 25 == 0 or count == len(targets):
            complete = sum(item.latitude is not None for item in results)
            print(f"official geocode {count:,}/{len(targets):,} / success {complete:,}", flush=True)

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
