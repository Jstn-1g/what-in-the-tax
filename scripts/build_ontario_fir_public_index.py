"""Build the static Ontario FIR search index without network or AI calls.

The public index is an identity/search aid. It deliberately contains no tax
amounts, findings, receipt routes, personal contact fields, or local paths.
The exact 2023 archive is hash-pinned because Ontario may revise FIR data after
its initial publication.

Usage:
    python scripts/build_ontario_fir_public_index.py
    python scripts/build_ontario_fir_public_index.py --check
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import sys
import zipfile
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "source-pdfs" / "fir" / "fir_data_2023.zip"
DEFAULT_OUTPUT = ROOT / "web" / "public" / "registry" / "ontario-fir-2023.json"

SCHEMA_VERSION = "ontario-fir-public-index-1.0.0"
FISCAL_YEAR = "2023"
EXPECTED_ZIP_SHA256 = (
    "30c84a4c8af73ddd56e1414e01cae3246a22af305fce1e519db202e907cfeddf"
)
EXPECTED_CSV_MEMBER = "fir_data_2023.csv"
EXPECTED_ROW_COUNT = 682_127
EXPECTED_RECORD_COUNT = 436
EXPECTED_TIER_COUNTS = {"lower-tier": 238, "single-tier": 168, "upper-tier": 30}
EXPECTED_ONTARIO_RETURN_COUNT = 444

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

TIER_LABELS = {
    "LT": "lower-tier",
    "ST": "single-tier",
    "UT": "upper-tier",
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

# The only explicitly ordered current-year receipt cohort in the project plan.
# These remain registry records until their separate receipt evidence gates pass.
ROLLOUT_COHORT = [
    {"order": 1, "assessmentCode": "3001", "label": "North Dumfries"},
    {"order": 2, "assessmentCode": "3024", "label": "Wellesley"},
    {"order": 3, "assessmentCode": "3018", "label": "Wilmot"},
    {"order": 4, "assessmentCode": "3029", "label": "Woolwich"},
]

SOURCE = {
    "publisher": "Government of Ontario, Ministry of Municipal Affairs and Housing",
    "title": "Financial Information Return (FIR) — data by year",
    "officialIndexUrl": "https://efis.fma.csc.gov.on.ca/fir/MultiYearReport/MYCIndex.html",
    "downloadUrl": "https://efis.fma.csc.gov.on.ca/fir/MultiYearReport/fir_data_2023.zip",
    "dataCatalogueUrl": (
        "https://data.ontario.ca/en/dataset/"
        "financial-information-return-fir-for-municipalities"
    ),
    "licenceUrl": "https://www.ontario.ca/page/open-government-licence-ontario",
    "licenceAttribution": (
        "Contains information licensed under the Open Government Licence – Ontario."
    ),
}

ASSESSMENT_CODE_RE = re.compile(r"^\d{4}$")
SOURCE_DATE_RE = re.compile(r"^\d{8}$")


class IndexBuildError(ValueError):
    """Raised when locked source bytes fail an index gate."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _identity_value(row: dict[str, str | None], field: str) -> str:
    return (row.get(field) or "").strip()


def _display_parts(source_name: str) -> tuple[str, str]:
    """Return a readable name and an explicit source-published entity type."""

    if " " not in source_name:
        raise IndexBuildError(f"FIR name has no entity suffix: {source_name!r}")
    stem, suffix = source_name.rsplit(" ", 1)
    type_label = ENTITY_TYPE_LABELS.get(suffix)
    if type_label is None:
        raise IndexBuildError(
            f"unsupported FIR municipality suffix {suffix!r} in {source_name!r}"
        )
    # "Brant County" is already the readable official name.
    display_name = source_name if suffix == "County" else stem
    return display_name, type_label


def _format_source_date(value: str) -> str:
    if not SOURCE_DATE_RE.fullmatch(value):
        raise IndexBuildError(f"invalid FIR LAST_UPDATE_DATE {value!r}")
    return f"{value[0:4]}-{value[4:6]}-{value[6:8]}"


def _read_identity_records(zip_path: Path) -> tuple[list[dict[str, str]], int]:
    identities: dict[str, dict[str, str]] = {}
    row_count = 0

    try:
        archive = zipfile.ZipFile(zip_path)
    except (OSError, zipfile.BadZipFile) as exc:
        raise IndexBuildError(f"cannot open FIR archive: {exc}") from exc

    with archive:
        members = archive.namelist()
        if members != [EXPECTED_CSV_MEMBER]:
            raise IndexBuildError(
                f"FIR archive members are {members!r}; expected [{EXPECTED_CSV_MEMBER!r}]"
            )
        with archive.open(EXPECTED_CSV_MEMBER) as raw:
            text = io.TextIOWrapper(
                raw,
                encoding="utf-8",
                errors="strict",
                newline="",
            )
            reader = csv.DictReader(text)
            if reader.fieldnames != EXPECTED_HEADERS:
                raise IndexBuildError(
                    "FIR CSV headers changed; refusing to infer the new schema"
                )

            for row in reader:
                row_count += 1
                if _identity_value(row, "MARSYEAR") != FISCAL_YEAR:
                    raise IndexBuildError(
                        f"unexpected MARSYEAR at CSV row {row_count + 1}"
                    )

                assessment_code = _identity_value(row, "ASSESSMENT_CODE")
                source_name = _identity_value(row, "MUNICIPALITY_DESC")
                munid = _identity_value(row, "MUNID")
                sgc_code = _identity_value(row, "SGC_CODE")
                mtype_code = _identity_value(row, "MTYPE_CODE")
                tier_code = _identity_value(row, "TIER_CODE")
                last_update_date = _identity_value(row, "LAST_UPDATE_DATE")

                if not ASSESSMENT_CODE_RE.fullmatch(assessment_code):
                    raise IndexBuildError(
                        f"invalid ASSESSMENT_CODE {assessment_code!r}"
                    )
                if not source_name or not munid or not sgc_code or not mtype_code:
                    raise IndexBuildError(
                        f"{assessment_code}: incomplete FIR identity fields"
                    )
                tier = TIER_LABELS.get(tier_code)
                if tier is None:
                    raise IndexBuildError(
                        f"{assessment_code}: unsupported TIER_CODE {tier_code!r}"
                    )
                display_name, type_label = _display_parts(source_name)
                formatted_update = _format_source_date(last_update_date)

                identity = {
                    "assessmentCode": assessment_code,
                    "displayName": display_name,
                    "sourceName": source_name,
                    "typeLabel": type_label,
                    "tier": tier,
                    "lastUpdated": formatted_update,
                    "_munid": munid,
                    "_sgcCode": sgc_code,
                    "_mtypeCode": mtype_code,
                }
                prior = identities.setdefault(assessment_code, identity)
                if prior != identity:
                    raise IndexBuildError(
                        f"{assessment_code}: conflicting identity rows in FIR CSV"
                    )

    records = [
        {
            field: value
            for field, value in identities[code].items()
            if not field.startswith("_")
        }
        for code in sorted(identities)
    ]
    return records, row_count


def build_index(
    zip_path: Path,
    *,
    enforce_release_lock: bool = True,
) -> dict[str, Any]:
    observed_hash = sha256_file(zip_path)
    if enforce_release_lock and observed_hash != EXPECTED_ZIP_SHA256:
        raise IndexBuildError(
            "FIR archive SHA-256 changed; review and pin a new release before publishing"
        )

    records, row_count = _read_identity_records(zip_path)
    tier_counts = Counter(record["tier"] for record in records)
    source_names = {record["sourceName"] for record in records}
    if enforce_release_lock:
        if row_count != EXPECTED_ROW_COUNT:
            raise IndexBuildError(
                f"FIR row count is {row_count}; expected {EXPECTED_ROW_COUNT}"
            )
        if len(records) != EXPECTED_RECORD_COUNT:
            raise IndexBuildError(
                f"FIR record count is {len(records)}; expected {EXPECTED_RECORD_COUNT}"
            )
        if len(source_names) != len(records):
            raise IndexBuildError("FIR assessment codes do not map one-to-one to names")
        if dict(tier_counts) != EXPECTED_TIER_COUNTS:
            raise IndexBuildError(
                f"FIR tier counts are {dict(tier_counts)!r}; "
                f"expected {EXPECTED_TIER_COUNTS!r}"
            )

    records_by_code = {record["assessmentCode"]: record for record in records}
    missing_cohort = [
        item["assessmentCode"]
        for item in ROLLOUT_COHORT
        if item["assessmentCode"] not in records_by_code
    ]
    if missing_cohort:
        raise IndexBuildError(
            f"documented rollout cohort missing from FIR source: {missing_cohort}"
        )

    source_last_updated = max(record["lastUpdated"] for record in records)
    index = {
        "schemaVersion": SCHEMA_VERSION,
        "artifactKind": "historical-financial-return-directory",
        "jurisdiction": "CA-ON",
        "fiscalYear": int(FISCAL_YEAR),
        "isReceipt": False,
        "source": {
            **SOURCE,
            "sha256": observed_hash,
            "lastUpdated": source_last_updated,
        },
        "coverage": {
            "recordsPresent": len(records),
            "expectedOntarioReturns": EXPECTED_ONTARIO_RETURN_COUNT,
            "recordsNotPresent": EXPECTED_ONTARIO_RETURN_COUNT - len(records),
            "tierCounts": {
                "lowerTier": tier_counts["lower-tier"],
                "singleTier": tier_counts["single-tier"],
                "upperTier": tier_counts["upper-tier"],
            },
            "status": "incomplete",
        },
        "method": {
            "primaryKey": "assessmentCode",
            "runtimeAiRequired": False,
            "runtimeGovernmentRequestsRequired": False,
            "containsFinancialMetrics": False,
            "currentTaxBylaw": False,
            "findingsSupported": False,
        },
        "rolloutPlan": {
            "basis": "First current-year receipt cohort in the project generalization plan",
            "sharedUpperTierAssessmentCode": "3000",
            "cohort": ROLLOUT_COHORT,
        },
        "caveat": (
            "These are municipality-submitted 2023 Financial Information Return "
            "records. Ontario says FIR data can be incomplete and previously posted "
            "years can be revised. A directory match is not a current tax bill, "
            "tax by-law, receipt, finding, or publication approval."
        ),
        "records": records,
    }
    return index


def render_index(index: dict[str, Any]) -> str:
    return json.dumps(index, indent=2, ensure_ascii=False) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build the hash-pinned Ontario FIR public search index (0 AI)"
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail if the checked-in public index is not fresh",
    )
    args = parser.parse_args(argv)

    if not args.input.is_file():
        print(f"ERROR: missing locked FIR archive: {args.input}", file=sys.stderr)
        return 1
    try:
        rendered = render_index(build_index(args.input))
    except (IndexBuildError, OSError) as exc:
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
                "ERROR: public Ontario FIR index is stale; rebuild it before publishing",
                file=sys.stderr,
            )
            return 1
        print(
            f"Ontario FIR public index is fresh: "
            f"{EXPECTED_RECORD_COUNT} records, AI tokens 0"
        )
        return 0

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered, encoding="utf-8")
    print(
        f"Wrote {args.output.relative_to(ROOT)}: "
        f"{EXPECTED_RECORD_COUNT} records, AI tokens 0"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
