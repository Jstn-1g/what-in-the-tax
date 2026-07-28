"""Build the current Ontario municipality directory with FIR year history.

This artifact keeps three different ideas separate:

* the current 444-municipality identity list;
* the newest FIR year present for each municipality; and
* every retained FIR year (2025, 2024, and 2023) for later comparison.

It contains no financial amounts and makes no receipt or audit claim. All
selection and entity matching is deterministic; runtime AI is not required.

Usage:
    python scripts/build_ontario_municipal_history.py
    python scripts/build_ontario_municipal_history.py --check
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import sys
import unicodedata
import zipfile
from collections import Counter
from dataclasses import dataclass
from datetime import date
from html.parser import HTMLParser
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MUNICIPALITIES_INPUT = (
    ROOT / "source-pdfs" / "fir" / "municipalities_-_en_2026-0526.csv"
)
DEFAULT_OUTPUT = (
    ROOT / "web" / "public" / "registry" / "ontario-municipal-history.json"
)

SCHEMA_VERSION = "ontario-municipal-history-index-2.0.0"
JURISDICTION = "CA-ON"
EXPECTED_MUNICIPALITY_COUNT = 444
EXPECTED_CURRENT_TIER_COUNTS = {
    "lower-tier": 241,
    "single-tier": 173,
    "upper-tier": 30,
}
EXPECTED_MUNICIPALITIES_SHA256 = (
    "5370b4e1b3804d10059c67513db9ea59d61bba964096f8e5b35f4a8afd973196"
)

EXPECTED_HEADERS = [
    "MARSYEAR",
    "ASSESSMENT_CODE",
    "MUNICIPALITY_DESC",
    "MUNID",
    "MSO_NUMBER",
    "SGC_CODE",
    "UT_NUMBER",
    "MTYPE_CODE",
    "TIER_CODE",
    "LAST_UPDATE_DATE",
    "SCHEDULE_DESC",
    "SUB_SCHEDULE_DESC",
    "SCHEDULE_LINE_DESC",
    "SCHEDULE_COLUMN_DESC",
    "SLC",
    "DATATYPE_DESC",
    "AMOUNT",
    "VALUE_TEXT",
]
EXPECTED_MUNICIPALITY_HEADERS = [
    "Municipality",
    "Municipal status",
    "Geographic area",
]

TIER_LABELS = {
    "LT": "lower-tier",
    "ST": "single-tier",
    "UT": "upper-tier",
}
CURRENT_TIER_LABELS = {
    "Lower Tier": "lower-tier",
    "Single Tier": "single-tier",
    "Upper Tier": "upper-tier",
}
ENTITY_TYPE_LABELS = {
    "C": "City",
    "Co": "County",
    "County": "County",
    "D": "District Municipality",
    "M": "Municipality",
    "R": "Regional Municipality",
    "ST": "Separated Town",
    "T": "Town",
    "Tp": "Township",
    "UCo": "United Counties",
    "V": "Village",
}
CURRENT_NAME_SUFFIXES = (
    "District Municipality",
    "Regional Municipality",
    "United Counties",
    "Municipality",
    "Township",
    "Village",
    "County",
    "City",
    "Town",
)

ASSESSMENT_CODE_RE = re.compile(r"^\d{4}$")
SOURCE_DATE_RE = re.compile(r"^\d{8}$")
NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")


@dataclass(frozen=True)
class FirReleaseLock:
    year: int
    sha256: str
    member_sha256: str
    row_count: int
    record_count: int
    tier_counts: dict[str, int]
    posted_date: str

    @property
    def path(self) -> Path:
        return ROOT / "source-pdfs" / "fir" / f"fir_data_{self.year}.zip"

    @property
    def member(self) -> str:
        return f"fir_data_{self.year}.csv"

    @property
    def download_url(self) -> str:
        return (
            "https://efis.fma.csc.gov.on.ca/fir/MultiYearReport/"
            f"fir_data_{self.year}.zip"
        )


FIR_RELEASES = {
    2025: FirReleaseLock(
        year=2025,
        sha256="6e731d2e4a22ef8c9da470bbaf07a2e72d716b5cfdc34f3fc25593104ac3a29d",
        member_sha256="8e33c7ed5045a72d15ecdda6fa570164faa34517dc08eafc7bec24a3d5b86416",
        row_count=205_342,
        record_count=130,
        tier_counts={"lower-tier": 75, "single-tier": 40, "upper-tier": 15},
        posted_date="2026-07-28",
    ),
    2024: FirReleaseLock(
        year=2024,
        sha256="b3ed998b1a8b2de8f33220d24b4edfae6ae8c1ce4dca52a45ef6aa7c8387af5f",
        member_sha256="2b345692617a30abd3bfec6ac16f10fae3eb7dd6c6b7dc0be4e8ed934ccdaee4",
        row_count=629_192,
        record_count=403,
        tier_counts={"lower-tier": 220, "single-tier": 153, "upper-tier": 30},
        posted_date="2026-07-28",
    ),
    2023: FirReleaseLock(
        year=2023,
        sha256="30c84a4c8af73ddd56e1414e01cae3246a22af305fce1e519db202e907cfeddf",
        member_sha256="e41731b62a252ac7cb894d0f091af57a6660ba945dc86f5cdbeb62558bc40eef",
        row_count=682_127,
        record_count=436,
        tier_counts={"lower-tier": 238, "single-tier": 168, "upper-tier": 30},
        posted_date="2026-07-24",
    ),
}
FIR_YEARS = tuple(sorted(FIR_RELEASES, reverse=True))

# Ontario's current-name list and the FIR names use different but stable forms
# for these municipalities. Keep the exceptional crosswalk explicit and tested;
# do not ask an AI model to infer it.
CURRENT_NAME_TO_ASSESSMENT_CODE = {
    "Brant, County of": "2920",
    "Charlton and Dack, Municipality of": "5447",
    "Macdonald, Meredith and Aberdeen Additional, Township of": "5751",
    "Mattice-Val Côté, Township of": "5677",
    "Northeastern Manitoulin and The Islands, Town of": "5119",
    "Prince Edward, County of": "1350",
    "South Bruce Peninsula, Town of": "4102",
    "The Nation Municipality": "0212",
}

# These current municipalities have no row in any locked 2023–2025 bulk file.
# The current identity remains searchable, but no FIR year is invented.
EXPECTED_WITHOUT_FIR_HISTORY = {
    "Hamilton, City of",
    "Ignace, Township of",
    "Madoc, Township of",
    "Markstay-Warren, Municipality of",
    "Midland, Town of",
    "Nipigon, Township of",
    "Tay, Township of",
    "Tehkummah, Township of",
}

class HistoryBuildError(ValueError):
    """Raised when a locked input or deterministic crosswalk fails a gate."""


class _MunicipalityAnchorParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.href: str | None = None
        self.title: str | None = None
        self.text_parts: list[str] = []
        self.anchor_count = 0

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        if tag.casefold() != "a":
            return
        self.anchor_count += 1
        values = dict(attrs)
        self.href = values.get("href")
        self.title = values.get("title")

    def handle_data(self, data: str) -> None:
        if data.strip():
            self.text_parts.append(data.strip())


def sha256_archive_member(path: Path, member: str, year: int) -> str:
    """Digest the data inside the archive rather than the archive itself."""
    digest = hashlib.sha256()
    try:
        with zipfile.ZipFile(path) as archive, archive.open(member) as raw:
            for chunk in iter(lambda: raw.read(1 << 20), b""):
                digest.update(chunk)
    except (OSError, KeyError, zipfile.BadZipFile) as exc:
        raise HistoryBuildError(
            f"cannot read {member} from the {year} FIR archive: {exc}"
        ) from exc
    return digest.hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _identity_value(row: dict[str, str | None], field: str) -> str:
    return (row.get(field) or "").strip()


def _display_parts(source_name: str) -> tuple[str, str]:
    if " " not in source_name:
        raise HistoryBuildError(f"FIR name has no entity suffix: {source_name!r}")
    stem, suffix = source_name.rsplit(" ", 1)
    type_label = ENTITY_TYPE_LABELS.get(suffix)
    if type_label is None:
        raise HistoryBuildError(
            f"unsupported FIR municipality suffix {suffix!r} in {source_name!r}"
        )
    return (source_name if suffix == "County" else stem), type_label


def _format_source_date(value: str) -> str:
    if not SOURCE_DATE_RE.fullmatch(value):
        raise HistoryBuildError(f"invalid FIR LAST_UPDATE_DATE {value!r}")
    formatted = f"{value[0:4]}-{value[4:6]}-{value[6:8]}"
    try:
        date.fromisoformat(formatted)
    except ValueError as exc:
        raise HistoryBuildError(
            f"invalid FIR LAST_UPDATE_DATE {value!r}"
        ) from exc
    return formatted


def _normalize_name(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value.casefold())
    without_marks = "".join(
        character
        for character in normalized
        if not unicodedata.combining(character)
    )
    return NON_ALNUM_RE.sub("", without_marks.replace("&", " and "))


def _parse_current_name(official_name: str) -> tuple[str, str]:
    for type_label in CURRENT_NAME_SUFFIXES:
        suffix = f", {type_label} of"
        if official_name.endswith(suffix):
            return official_name[: -len(suffix)], type_label
    if official_name in {"Haldimand County", "Norfolk County"}:
        return official_name, "County"
    if official_name == "The Nation Municipality":
        return "The Nation", "Municipality"
    raise HistoryBuildError(
        f"unsupported current municipality name form: {official_name!r}"
    )


def _parse_municipality_anchor(value: str) -> tuple[str, str | None]:
    parser = _MunicipalityAnchorParser()
    parser.feed(value)
    text = " ".join(parser.text_parts).strip()
    # The June 2026 source CSV contains two UTF-8 sequences represented as
    # Latin-1 code points in the Mattice-Val Côté row. Repair only those exact
    # observed sequences; the source hash above keeps this exception bounded.
    text = text.replace("\u00c3\u00b4", "ô").replace("\u00c3\u00a9", "é")
    title = (
        parser.title.replace("\u00c3\u00b4", "ô").replace("\u00c3\u00a9", "é")
        if parser.title
        else None
    )
    if (
        parser.anchor_count != 1
        or not text
        or title != text
    ):
        raise HistoryBuildError(
            f"invalid municipality link cell in current directory: {value!r}"
        )
    return text, parser.href


def _read_current_municipalities(path: Path) -> list[dict[str, str]]:
    try:
        handle = path.open("r", encoding="utf-8-sig", newline="")
    except OSError as exc:
        raise HistoryBuildError(f"cannot open current municipality source: {exc}") from exc

    records: list[dict[str, str]] = []
    with handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != EXPECTED_MUNICIPALITY_HEADERS:
            raise HistoryBuildError(
                "current municipality CSV headers changed; refusing to infer schema"
            )
        for row_number, row in enumerate(reader, start=2):
            official_name, _website_url = _parse_municipality_anchor(
                _identity_value(row, "Municipality")
            )
            status = _identity_value(row, "Municipal status")
            tier = CURRENT_TIER_LABELS.get(status)
            geographic_area = _identity_value(row, "Geographic area")
            if tier is None or not geographic_area:
                raise HistoryBuildError(
                    f"current municipality row {row_number} has invalid tier or area"
                )
            display_name, type_label = _parse_current_name(official_name)
            records.append(
                {
                    "officialName": official_name,
                    "displayName": display_name,
                    "typeLabel": type_label,
                    "tier": tier,
                    "geographicArea": geographic_area,
                }
            )

    official_names = [record["officialName"] for record in records]
    if len(set(official_names)) != len(official_names):
        raise HistoryBuildError("current municipality official names are not unique")
    return records


def _read_fir_release(
    zip_path: Path,
    release: FirReleaseLock,
    *,
    enforce_release_lock: bool,
) -> tuple[dict[str, dict[str, Any]], int, str, str]:
    # The container digest changes whenever Ontario re-zips identical data, so
    # the payload is what gets verified and what the artifact varies with.
    observed_member_hash = sha256_archive_member(zip_path, release.member, release.year)
    if enforce_release_lock and observed_member_hash != release.member_sha256:
        raise HistoryBuildError(
            f"{release.year} FIR archive payload SHA-256 changed; review and pin it first"
        )
    observed_hash = release.sha256

    identities: dict[str, dict[str, Any]] = {}
    row_count = 0
    try:
        archive = zipfile.ZipFile(zip_path)
    except (OSError, zipfile.BadZipFile) as exc:
        raise HistoryBuildError(
            f"cannot open {release.year} FIR archive: {exc}"
        ) from exc

    with archive:
        if archive.namelist() != [release.member]:
            raise HistoryBuildError(
                f"{release.year} FIR archive members changed"
            )
        with archive.open(release.member) as raw:
            reader = csv.DictReader(
                io.TextIOWrapper(
                    raw,
                    encoding="utf-8",
                    errors="strict",
                    newline="",
                )
            )
            if reader.fieldnames != EXPECTED_HEADERS:
                raise HistoryBuildError(
                    f"{release.year} FIR CSV headers changed"
                )
            for row in reader:
                row_count += 1
                if _identity_value(row, "MARSYEAR") != str(release.year):
                    raise HistoryBuildError(
                        f"{release.year} FIR contains another fiscal year"
                    )
                assessment_code = _identity_value(row, "ASSESSMENT_CODE")
                source_name = _identity_value(row, "MUNICIPALITY_DESC")
                tier_code = _identity_value(row, "TIER_CODE")
                tier = TIER_LABELS.get(tier_code)
                if not ASSESSMENT_CODE_RE.fullmatch(assessment_code):
                    raise HistoryBuildError(
                        f"{release.year}: invalid assessment code {assessment_code!r}"
                    )
                if tier is None:
                    raise HistoryBuildError(
                        f"{release.year} {assessment_code}: invalid tier {tier_code!r}"
                    )
                display_name, type_label = _display_parts(source_name)
                identity = {
                    "assessmentCode": assessment_code,
                    "sourceName": source_name,
                    "displayName": display_name,
                    "typeLabel": type_label,
                    "tier": tier,
                    "lastUpdated": _format_source_date(
                        _identity_value(row, "LAST_UPDATE_DATE")
                    ),
                    "_munid": _identity_value(row, "MUNID"),
                    "_sgcCode": _identity_value(row, "SGC_CODE"),
                    "_mtypeCode": _identity_value(row, "MTYPE_CODE"),
                }
                if not all(
                    identity[field]
                    for field in ("sourceName", "_munid", "_sgcCode", "_mtypeCode")
                ):
                    raise HistoryBuildError(
                        f"{release.year} {assessment_code}: incomplete identity"
                    )
                prior = identities.setdefault(assessment_code, identity)
                if prior != identity:
                    raise HistoryBuildError(
                        f"{release.year} {assessment_code}: conflicting identity rows"
                    )

    tier_counts = Counter(record["tier"] for record in identities.values())
    if enforce_release_lock:
        if row_count != release.row_count:
            raise HistoryBuildError(
                f"{release.year} FIR row count is {row_count}; "
                f"expected {release.row_count}"
            )
        if len(identities) != release.record_count:
            raise HistoryBuildError(
                f"{release.year} FIR record count is {len(identities)}; "
                f"expected {release.record_count}"
            )
        if dict(tier_counts) != release.tier_counts:
            raise HistoryBuildError(
                f"{release.year} FIR tier counts changed: {dict(tier_counts)!r}"
            )
    return identities, row_count, observed_hash, observed_member_hash


def _fallback_reason(latest_year: int | None) -> str | None:
    if latest_year == 2025:
        return None
    if latest_year == 2024:
        return "No 2025 record in the locked 2025 FIR bulk file."
    if latest_year == 2023:
        return "No 2025 or 2024 record in the corresponding locked FIR bulk files."
    return "No 2023–2025 record in the locked FIR bulk files."


def _directory_id(
    assessment_code: str | None,
    display_name: str,
    type_label: str,
) -> str:
    if assessment_code:
        return f"on-{assessment_code}"
    slug_source = f"{display_name}-{type_label}"
    normalized = unicodedata.normalize("NFKD", slug_source.casefold())
    ascii_value = "".join(
        character
        for character in normalized
        if not unicodedata.combining(character) and character.isascii()
    )
    slug = NON_ALNUM_RE.sub("-", ascii_value).strip("-")
    if not slug:
        raise HistoryBuildError("cannot build a stable municipality directory ID")
    return f"on-{slug}"


def build_index(
    municipalities_path: Path,
    fir_paths: dict[int, Path],
    *,
    enforce_release_locks: bool = True,
) -> dict[str, Any]:
    if set(fir_paths) != set(FIR_RELEASES):
        raise HistoryBuildError(f"FIR inputs must contain years {list(FIR_YEARS)}")

    observed_municipalities_hash = sha256_file(municipalities_path)
    if (
        enforce_release_locks
        and observed_municipalities_hash != EXPECTED_MUNICIPALITIES_SHA256
    ):
        raise HistoryBuildError(
            "current municipality CSV SHA-256 changed; review and pin it first"
        )
    current_records = _read_current_municipalities(municipalities_path)

    fir_by_year: dict[int, dict[str, dict[str, Any]]] = {}
    fir_sources: list[dict[str, Any]] = []
    for year in FIR_YEARS:
        release = FIR_RELEASES[year]
        records, row_count, observed_hash, observed_member_hash = _read_fir_release(
            fir_paths[year],
            release,
            enforce_release_lock=enforce_release_locks,
        )
        fir_by_year[year] = records
        fir_sources.append(
            {
                "fiscalYear": year,
                "downloadUrl": release.download_url,
                "sha256": observed_hash,
                "archiveMemberSha256": observed_member_hash,
                "postedDate": release.posted_date,
                "sourceLastUpdated": max(
                    record["lastUpdated"] for record in records.values()
                ),
                "rowCount": row_count,
                "uniqueAssessmentCodes": len(records),
                "coverageBasis": (
                    "Unique assessment codes in this hash-pinned bulk file; "
                    "Ontario's webpage file count can differ."
                ),
            }
        )

    history_by_code: dict[str, dict[int, dict[str, Any]]] = {}
    for year, records in fir_by_year.items():
        for assessment_code, record in records.items():
            history_by_code.setdefault(assessment_code, {})[year] = record

    candidates: dict[tuple[str, str], list[str]] = {}
    for assessment_code, history in history_by_code.items():
        newest = history[max(history)]
        key = (_normalize_name(newest["displayName"]), newest["tier"])
        candidates.setdefault(key, []).append(assessment_code)

    used_assessment_codes: set[str] = set()
    public_records: list[dict[str, Any]] = []
    without_history: set[str] = set()
    for current in current_records:
        official_name = current["officialName"]
        explicit_code = CURRENT_NAME_TO_ASSESSMENT_CODE.get(official_name)
        if explicit_code:
            assessment_code = explicit_code
            if assessment_code not in history_by_code:
                raise HistoryBuildError(
                    f"explicit crosswalk {official_name!r} points outside FIR history"
                )
        else:
            key = (_normalize_name(current["displayName"]), current["tier"])
            matches = candidates.get(key, [])
            if len(matches) > 1:
                raise HistoryBuildError(
                    f"ambiguous current/FIR match for {official_name!r}: {matches}"
                )
            assessment_code = matches[0] if matches else None

        if assessment_code is None:
            without_history.add(official_name)
            history: dict[int, dict[str, Any]] = {}
        else:
            if assessment_code in used_assessment_codes:
                raise HistoryBuildError(
                    f"assessment code {assessment_code} maps to multiple current names"
                )
            used_assessment_codes.add(assessment_code)
            history = history_by_code[assessment_code]

        years = sorted(history, reverse=True)
        latest_year = years[0] if years else None
        source_names = list(
            dict.fromkeys(history[year]["sourceName"] for year in years)
        )
        public_records.append(
            {
                "directoryId": _directory_id(
                    assessment_code,
                    current["displayName"],
                    current["typeLabel"],
                ),
                "assessmentCode": assessment_code,
                "displayName": current["displayName"],
                "officialName": official_name,
                "sourceNameAliases": source_names,
                "typeLabel": current["typeLabel"],
                "tier": current["tier"],
                "geographicArea": current["geographicArea"],
                "latestFirYear": latest_year,
                "firYears": [
                    {
                        "fiscalYear": year,
                        "lastUpdated": history[year]["lastUpdated"],
                        "sourceName": history[year]["sourceName"],
                    }
                    for year in years
                ],
                "fallbackReason": _fallback_reason(latest_year),
            }
        )

    orphan_fir_codes = set(history_by_code) - used_assessment_codes
    if orphan_fir_codes:
        raise HistoryBuildError(
            f"FIR codes do not map to the current directory: {sorted(orphan_fir_codes)}"
        )

    if enforce_release_locks:
        if len(current_records) != EXPECTED_MUNICIPALITY_COUNT:
            raise HistoryBuildError(
                f"current municipality count is {len(current_records)}; "
                f"expected {EXPECTED_MUNICIPALITY_COUNT}"
            )
        observed_current_tiers = Counter(
            record["tier"] for record in current_records
        )
        if dict(observed_current_tiers) != EXPECTED_CURRENT_TIER_COUNTS:
            raise HistoryBuildError(
                f"current municipality tier counts changed: "
                f"{dict(observed_current_tiers)!r}"
            )
        if without_history != EXPECTED_WITHOUT_FIR_HISTORY:
            raise HistoryBuildError(
                "municipalities without 2023–2025 FIR history changed: "
                f"{sorted(without_history)!r}"
            )

    public_records.sort(
        key=lambda record: (
            record["displayName"].casefold(),
            record["typeLabel"].casefold(),
            record["directoryId"],
        )
    )
    directory_ids = [record["directoryId"] for record in public_records]
    if len(set(directory_ids)) != len(directory_ids):
        raise HistoryBuildError("generated current municipality IDs are not unique")

    latest_counts = Counter(
        str(record["latestFirYear"]) if record["latestFirYear"] else "unavailable"
        for record in public_records
    )
    current_tier_counts = Counter(record["tier"] for record in public_records)

    return {
        "schemaVersion": SCHEMA_VERSION,
        "artifactKind": "current-municipality-directory-with-fir-history",
        "jurisdiction": JURISDICTION,
        "sourceSnapshotDate": max(
            source["postedDate"] for source in fir_sources
        ),
        "isReceipt": False,
        "sources": {
            "currentMunicipalities": {
                "publisher": (
                    "Government of Ontario, Ministry of Municipal Affairs "
                    "and Housing"
                ),
                "title": "Municipalities — current Ontario directory",
                "dataCatalogueUrl": "https://data.ontario.ca/dataset/municipalities",
                "downloadUrl": (
                    "https://data.ontario.ca/dataset/"
                    "62e83cbc-0731-4d66-abdc-2f2b31bcd76c/resource/"
                    "6783a586-6b05-4a73-9663-e60a6963c91e/download/"
                    "municipalities_-_en_2026-0526.csv"
                ),
                "sha256": observed_municipalities_hash,
                "lastUpdated": "2026-06-03",
            },
            "fir": {
                "publisher": (
                    "Government of Ontario, Ministry of Municipal Affairs "
                    "and Housing"
                ),
                "title": "Financial Information Return (FIR) — data by year",
                "officialIndexUrl": (
                    "https://efis.fma.csc.gov.on.ca/fir/MultiYearReport/"
                    "MYCIndex.html"
                ),
                "dataCatalogueUrl": (
                    "https://data.ontario.ca/en/dataset/"
                    "financial-information-return-fir-for-municipalities"
                ),
                "releases": fir_sources,
            },
            "licenceUrl": (
                "https://www.ontario.ca/page/open-government-licence-ontario"
            ),
            "licenceAttribution": (
                "Contains information licensed under the Open Government "
                "Licence – Ontario."
            ),
        },
        "coverage": {
            "currentMunicipalities": len(public_records),
            "withFirHistory": len(public_records) - len(without_history),
            "withoutFirHistory": len(without_history),
            "latestFirYearCounts": {
                "2025": latest_counts["2025"],
                "2024": latest_counts["2024"],
                "2023": latest_counts["2023"],
                "unavailable": latest_counts["unavailable"],
            },
            "firYearRecordCounts": {
                str(year): len(fir_by_year[year]) for year in FIR_YEARS
            },
            "tierCounts": {
                "lowerTier": current_tier_counts["lower-tier"],
                "singleTier": current_tier_counts["single-tier"],
                "upperTier": current_tier_counts["upper-tier"],
            },
            "status": "complete-current-directory",
        },
        "method": {
            "currentIdentitySource": "Ontario municipalities dataset",
            "firSelectionOrder": list(FIR_YEARS),
            "selectionGrain": "municipality",
            "runtimeAiRequired": False,
            "runtimeGovernmentRequestsRequired": False,
            "containsFinancialMetrics": False,
            "currentTaxBylaw": False,
            "findingsSupported": False,
            "mixedYearFinancialComparisonsSupported": False,
        },
        "caveat": (
            "The municipality identity list is current to June 3, 2026. FIR "
            "years are municipality-submitted historical filings selected "
            "independently per municipality from the locked 2025, 2024, and "
            "2023 bulk files. FIR data may be incomplete or revised and is "
            "not a current tax bill, tax-rate by-law, receipt, formal audit, "
            "finding, or publication approval. Years are never blended."
        ),
        "records": public_records,
    }


def render_index(index: dict[str, Any]) -> str:
    return json.dumps(index, indent=2, ensure_ascii=False) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Build the hash-pinned current Ontario municipality directory "
            "and multi-year FIR history (0 AI)"
        )
    )
    parser.add_argument(
        "--municipalities-input",
        type=Path,
        default=DEFAULT_MUNICIPALITIES_INPUT,
    )
    for year in FIR_YEARS:
        parser.add_argument(
            f"--fir-{year}",
            type=Path,
            default=FIR_RELEASES[year].path,
        )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail if the checked-in public artifact is not fresh",
    )
    args = parser.parse_args(argv)

    fir_paths = {year: getattr(args, f"fir_{year}") for year in FIR_YEARS}
    missing = [
        path
        for path in [args.municipalities_input, *fir_paths.values()]
        if not path.is_file()
    ]
    if missing:
        print(
            f"ERROR: missing locked Ontario input(s): {missing}",
            file=sys.stderr,
        )
        return 1
    try:
        rendered = render_index(
            build_index(args.municipalities_input, fir_paths)
        )
    except (HistoryBuildError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if args.check:
        try:
            existing = args.output.read_text(encoding="utf-8")
        except OSError as exc:
            print(f"ERROR: cannot read public index: {exc}", file=sys.stderr)
            return 1
        if existing != rendered:
            print(
                "ERROR: Ontario municipal history artifact is stale",
                file=sys.stderr,
            )
            return 1
        print(
            "Ontario municipal history artifact is fresh: "
            "444 current municipalities, 2025->2024->2023 FIR selection, "
            "AI tokens 0"
        )
        return 0

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered, encoding="utf-8", newline="\n")
    print(
        f"Wrote {args.output.relative_to(ROOT)}: "
        "444 current municipalities, 2025->2024->2023 FIR selection, "
        "AI tokens 0"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
