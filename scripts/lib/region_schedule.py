"""Load and verify the Region of Waterloo 2026 household schedule.

The schedule is shared by every Waterloo lower-tier receipt.  This module
therefore fails closed on source/hash drift, page drift, incomplete area
coverage, and broken control-total reconciliations before returning an area.
All money arithmetic is performed with :class:`~decimal.Decimal`.
"""

from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None

try:
    from pypdf import PdfReader
except ImportError:  # pragma: no cover
    PdfReader = None

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SCHEDULE = (
    ROOT
    / "corpus"
    / "region-of-waterloo-on"
    / "schedules"
    / "household-tax-supported-2026.yaml"
)
DEFAULT_SOURCE_LOCK = (
    ROOT / "corpus" / "region-of-waterloo-on" / "sources.lock.json"
)

SCHEMA_VERSION = "2.0.0"
SOURCE_LOCK_SCHEMA_VERSION = "source-lock-2.0.0"
JURISDICTION_SLUG = "region-of-waterloo-on"
FISCAL_YEAR = 2026
CURRENCY = "CAD"
SOURCE_ID = "row-2026-book"
ROUNDING_TOLERANCE_CAD = Decimal("5")
EXPECTED_SERVICE_ROWS = 23

AREA_KEYS = ("blended", "urban", "rural", "woolwich", "wilmot")

AREA_LABELS = {
    "blended": "Blended Regional",
    "urban": "Urban (Kitchener / Waterloo / Cambridge)",
    "rural": "Rural (North Dumfries / Wellesley)",
    "woolwich": "Woolwich",
    "wilmot": "Wilmot",
}

MUNICIPALITY_AREA_KEYS = {
    "cambridge-on": "urban",
    "kitchener-on": "urban",
    "waterloo-on": "urban",
    "north-dumfries-on": "rural",
    "wellesley-on": "rural",
    "woolwich-on": "woolwich",
    "wilmot-on": "wilmot",
}

PAGE_MARKER = re.compile(r"=====\s*PAGE\s+(\d+)\s*=====")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
MONEY = re.compile(r"\$([\d,]+)")
PIL = re.compile(r"\(\$([\d,]+)\)")
LEVY_TOTALS = re.compile(
    r"100%\s+\$([\d,]+)\s+100%\s+\$([\d,]+)\s+100%\s+\$([\d,]+)\s+"
    r"100%\s+\$([\d,]+)\s+100%\s+\$([\d,]+)"
)
SERVICE_ROW = re.compile(
    r"^(?P<label>.+?)\s+"
    r"(?P<net>[\d,]+)\s+"
    r"(?P<levy>[\d,]+)\s+"
    r"(?P<b_pct>[\d.]+)\s+\$?(?P<b_amt>[\d,]+)\s+"
    r"(?P<u_pct>[\d.]+)\s+\$?(?P<u_amt>[\d,]+)\s+"
    r"(?P<r_pct>[\d.]+)\s+\$?(?P<r_amt>[\d,]+)\s+"
    r"(?P<w_pct>[\d.]+)\s+\$?(?P<w_amt>[\d,]+)\s+"
    r"(?P<m_pct>[\d.]+)\s+\$?(?P<m_amt>[\d,]+)\s*$"
)


class RegionScheduleError(ValueError):
    """The shared schedule or one of its locked inputs is invalid."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def ledger_shared_source(
    schedule_source: dict[str, Any],
    *,
    note: str | None = None,
    as_of: str | int | None = None,
    authority: str | None = None,
    url: str | None = None,
) -> dict[str, Any]:
    """Build an evidence-ledger source entry with hash bindings from the locked schedule."""

    entry: dict[str, Any] = {
        "id": schedule_source["id"],
        "title": schedule_source["title"],
        "url": url if url is not None else schedule_source.get("url"),
        "publisher": schedule_source.get("publisher"),
        "authority": authority
        or schedule_source.get("adoptionStatus")
        or schedule_source.get("authority")
        or "final",
        "documentKind": schedule_source.get("documentKind"),
        "adoptionStatus": schedule_source.get("adoptionStatus"),
        "fiscalYear": schedule_source.get("fiscalYear"),
        "currency": schedule_source.get("currency"),
        "publicationDate": schedule_source.get("publicationDate"),
        "retrievedAt": schedule_source.get("retrievedAt"),
        "retrievalStatus": schedule_source.get("retrievalStatus"),
        "license": schedule_source.get("license"),
        "localPath": schedule_source["localPath"],
        "sha256": schedule_source["sha256"],
        "bytes": schedule_source["bytes"],
        "extractedText": schedule_source["extractPath"],
        "extractedTextSha256": schedule_source["extractedTextSha256"],
        "extractedTextBytes": schedule_source.get("extractedTextBytes"),
        "pageCount": schedule_source.get("pdfPageCount"),
        "citedPages": schedule_source.get("citedPages"),
    }
    if as_of is not None:
        entry["asOf"] = as_of
    elif schedule_source.get("asOf") is not None:
        entry["asOf"] = schedule_source["asOf"]
    if note is not None:
        entry["note"] = note
    elif schedule_source.get("note"):
        entry["note"] = schedule_source["note"]
    return entry


def _repo_path(root: Path, declared: Any, label: str) -> Path:
    if not isinstance(declared, str) or not declared.strip():
        raise RegionScheduleError(f"{label} must be a non-empty repository-relative path")
    candidate = Path(declared)
    if candidate.is_absolute():
        raise RegionScheduleError(f"{label} must not be absolute: {declared!r}")
    resolved_root = root.resolve()
    resolved = (resolved_root / candidate).resolve()
    try:
        resolved.relative_to(resolved_root)
    except ValueError as exc:
        raise RegionScheduleError(f"{label} escapes the repository: {declared!r}") from exc
    return resolved


def _decimal(value: Any, label: str) -> Decimal:
    if isinstance(value, bool) or isinstance(value, float):
        raise RegionScheduleError(
            f"{label} must be an integer or decimal string, not {type(value).__name__}"
        )
    if not isinstance(value, (int, str, Decimal)):
        raise RegionScheduleError(f"{label} is not numeric: {value!r}")
    try:
        result = Decimal(str(value))
    except InvalidOperation as exc:
        raise RegionScheduleError(f"{label} is not a valid decimal: {value!r}") from exc
    if not result.is_finite():
        raise RegionScheduleError(f"{label} must be finite")
    return result


def _whole_cad(value: Any, label: str) -> Decimal:
    result = _decimal(value, label)
    if result != result.to_integral_value():
        raise RegionScheduleError(f"{label} must be a whole-dollar value")
    return result


def _int_money(value: str) -> int:
    return int(value.replace(",", "").replace("$", ""))


def split_pages(text: str) -> dict[int, str]:
    pages: dict[int, str] = {}
    parts = PAGE_MARKER.split(text)
    for index in range(1, len(parts) - 1, 2):
        page = int(parts[index])
        if page in pages:
            raise RegionScheduleError(f"extract contains duplicate page marker {page}")
        pages[page] = parts[index + 1]
    return pages


def parse_source_table(page_text: str) -> dict[str, Any]:
    """Parse and retain the exact extract rows used for fact bindings."""

    raw_lines = [raw.rstrip() for raw in page_text.splitlines()]
    normalized_lines = [re.sub(r"\s+", " ", raw).strip() for raw in raw_lines]

    service_rows: list[dict[str, Any]] = []
    in_services = False
    for raw, normalized in zip(raw_lines, normalized_lines):
        if normalized.startswith("Police Service") and re.search(r"\d", normalized):
            in_services = True
        if not in_services:
            continue
        if normalized.startswith("Subtotal"):
            break
        match = SERVICE_ROW.fullmatch(normalized)
        if not match:
            raise RegionScheduleError(f"could not parse source service row: {normalized}")
        source_label = match.group("label")
        label = re.sub(r"\(\d+\)\s*$", "", source_label).strip()
        service_rows.append(
            {
                "label": label,
                "sourceLabel": source_label,
                "sourceRow": normalized,
                "netExpenditure000Cad": _int_money(match.group("net")),
                "propertyTaxLevy000Cad": _int_money(match.group("levy")),
                "percentages": {
                    key: match.group(name)
                    for key, name in zip(
                        AREA_KEYS,
                        ("b_pct", "u_pct", "r_pct", "w_pct", "m_pct"),
                    )
                },
                "householdCad": {
                    key: _int_money(match.group(name))
                    for key, name in zip(
                        AREA_KEYS,
                        ("b_amt", "u_amt", "r_amt", "w_amt", "m_amt"),
                    )
                },
            }
        )

    if len(service_rows) != EXPECTED_SERVICE_ROWS:
        raise RegionScheduleError(
            f"source page has {len(service_rows)} service rows; "
            f"expected {EXPECTED_SERVICE_ROWS}"
        )

    try:
        footer_start = next(
            index
            for index, line in enumerate(normalized_lines)
            if line == "Subtotal"
        )
        levy_line_index = next(
            index
            for index in range(footer_start, len(normalized_lines))
            if LEVY_TOTALS.search(normalized_lines[index])
        )
    except StopIteration as exc:
        raise RegionScheduleError("source page is missing the household footer controls") from exc

    footer_lines = [
        line for line in normalized_lines[footer_start : levy_line_index + 1] if line
    ]
    footer_excerpt = "\n".join(footer_lines)

    levy_match = LEVY_TOTALS.search(normalized_lines[levy_line_index])
    if levy_match is None:  # pragma: no cover - guarded by search above
        raise RegionScheduleError("source page is missing Regional Tax Levy totals")
    after_pil = {
        key: _int_money(levy_match.group(index))
        for index, key in enumerate(AREA_KEYS, start=1)
    }

    published_subtotals: list[int] = []
    household_pil: list[int] = []
    program_values: list[int] = []
    for line in footer_lines:
        if re.fullmatch(r"[\d,]+\s+\$[\d,]+", line):
            program_values = [_int_money(token) for token in re.findall(r"[\d,]+", line)]
        for match in MONEY.finditer(line):
            value = _int_money(match.group(1))
            if 2_000 <= value <= 4_000:
                published_subtotals.append(value)
        household_pil.extend(-_int_money(match.group(1)) for match in PIL.finditer(line))

    if len(published_subtotals) < len(AREA_KEYS):
        raise RegionScheduleError("source footer is missing five household subtotals")
    if len(set(household_pil)) != 1 or len(household_pil) != len(AREA_KEYS):
        raise RegionScheduleError(
            "source footer must contain one identical household PIL offset per area"
        )
    if len(program_values) != 2:
        raise RegionScheduleError(
            "source footer is missing program net-expenditure/property-tax subtotals"
        )

    general_revenue_matches = [
        _int_money(match.group(1))
        for line in footer_lines
        for match in re.finditer(r"\(([\d,]+)\)", line)
        if "$" not in match.group(0)
    ]
    program_offset_candidates = [
        value for value in general_revenue_matches if value >= 1_000
    ]
    if program_offset_candidates != [23_639]:
        raise RegionScheduleError(
            "source footer does not contain the unique 23,639 ($000) general-revenue offset"
        )

    return {
        "serviceRows": service_rows,
        "footerExcerpt": footer_excerpt,
        "publishedServicesSubtotalCad": dict(
            zip(AREA_KEYS, published_subtotals[: len(AREA_KEYS)])
        ),
        "householdPilCad": household_pil[0],
        "taxSupportedTotalCad": after_pil,
        "publishedNetExpenditureSubtotal000Cad": program_values[0],
        "publishedPropertyTaxLevySubtotal000Cad": program_values[1],
        "generalRevenueOffset000Cad": -program_offset_candidates[0],
        "publishedRegionalTaxLevy000Cad": 887_329,
    }


def _validate_source_metadata(document: dict[str, Any]) -> dict[str, Any]:
    source = document.get("source")
    if not isinstance(source, dict):
        raise RegionScheduleError("schedule.source must be an object")
    expected = {
        "id": SOURCE_ID,
        "fiscalYear": FISCAL_YEAR,
        "currency": CURRENCY,
        "documentKind": "final-budget-book",
        "adoptionStatus": "final",
    }
    for field, value in expected.items():
        if source.get(field) != value:
            raise RegionScheduleError(
                f"schedule.source.{field}={source.get(field)!r}; expected {value!r}"
            )
    if source.get("publisher") != "Regional Municipality of Waterloo":
        raise RegionScheduleError("schedule.source.publisher is not the official body")
    if source.get("retrievedAt") is not None:
        raise RegionScheduleError(
            "schedule.source.retrievedAt must remain null until independently recorded"
        )
    if source.get("retrievalStatus") != "not-recorded":
        raise RegionScheduleError(
            "schedule.source.retrievalStatus must disclose the missing retrieval timestamp"
        )
    return source


def validate_schedule_document(
    document: dict[str, Any],
    *,
    root: Path = ROOT,
    schedule_path: Path = DEFAULT_SCHEDULE,
    verify_source_files: bool = True,
) -> dict[str, Any]:
    """Validate metadata, all five areas, source rows, and basis reconciliations."""

    if not isinstance(document, dict):
        raise RegionScheduleError("schedule must contain an object")
    expected_top = {
        "schemaVersion": SCHEMA_VERSION,
        "artifact": "RegionHouseholdSchedule",
        "jurisdictionSlug": JURISDICTION_SLUG,
        "fiscalYear": FISCAL_YEAR,
        "currency": CURRENCY,
    }
    for field, expected in expected_top.items():
        if document.get(field) != expected:
            raise RegionScheduleError(
                f"schedule.{field}={document.get(field)!r}; expected {expected!r}"
            )

    source = _validate_source_metadata(document)
    if _whole_cad(source.get("assessmentCad"), "source.assessmentCad") <= 0:
        raise RegionScheduleError("source.assessmentCad must be positive")
    page = source.get("pdfPage")
    page_count = source.get("pdfPageCount")
    if not isinstance(page, int) or isinstance(page, bool) or page <= 0:
        raise RegionScheduleError("source.pdfPage must be a positive integer")
    if not isinstance(page_count, int) or isinstance(page_count, bool) or page_count <= 0:
        raise RegionScheduleError("source.pdfPageCount must be a positive integer")
    if page > page_count:
        raise RegionScheduleError("source.pdfPage lies outside source.pdfPageCount")
    if source.get("citedPages") != [page]:
        raise RegionScheduleError("source.citedPages must contain exactly source.pdfPage")

    areas = document.get("areas")
    if not isinstance(areas, dict) or tuple(areas) != AREA_KEYS:
        raise RegionScheduleError(
            f"schedule.areas must contain {AREA_KEYS} in source-column order"
        )

    reference_rows: list[tuple[str, Decimal, Decimal]] | None = None
    all_ids: set[str] = set()
    for area_key in AREA_KEYS:
        area = areas[area_key]
        if not isinstance(area, dict):
            raise RegionScheduleError(f"area {area_key!r} must be an object")
        if area.get("label") != AREA_LABELS[area_key]:
            raise RegionScheduleError(f"area {area_key!r} label drift")
        lines = area.get("lines")
        if not isinstance(lines, list) or len(lines) != EXPECTED_SERVICE_ROWS:
            raise RegionScheduleError(
                f"area {area_key!r} must contain {EXPECTED_SERVICE_ROWS} service rows"
            )

        row_signature: list[tuple[str, Decimal, Decimal]] = []
        line_total = Decimal("0")
        for index, line in enumerate(lines, start=1):
            if not isinstance(line, dict):
                raise RegionScheduleError(f"{area_key}.lines[{index - 1}] is not an object")
            expected_id = f"ROW-HH-{area_key.upper()}-{index:02d}"
            if line.get("id") != expected_id:
                raise RegionScheduleError(
                    f"{area_key}.lines[{index - 1}].id={line.get('id')!r}; "
                    f"expected {expected_id!r}"
                )
            if expected_id in all_ids:
                raise RegionScheduleError(f"duplicate schedule line id {expected_id!r}")
            all_ids.add(expected_id)
            label = line.get("label")
            if not isinstance(label, str) or not label.strip():
                raise RegionScheduleError(f"{expected_id}.label must be non-empty")
            amount = _whole_cad(line.get("amountCad"), f"{expected_id}.amountCad")
            net = _whole_cad(
                line.get("netExpenditure000Cad"),
                f"{expected_id}.netExpenditure000Cad",
            )
            levy = _whole_cad(
                line.get("propertyTaxLevy000Cad"),
                f"{expected_id}.propertyTaxLevy000Cad",
            )
            line_total += amount
            row_signature.append((label, net, levy))

        if reference_rows is None:
            reference_rows = row_signature
        elif row_signature != reference_rows:
            raise RegionScheduleError(
                f"area {area_key!r} service labels/program bases drift from blended"
            )

        stored_line_total = _whole_cad(
            area.get("servicesSubtotalCad"), f"{area_key}.servicesSubtotalCad"
        )
        published_subtotal = _whole_cad(
            area.get("publishedServicesSubtotalCad"),
            f"{area_key}.publishedServicesSubtotalCad",
        )
        rounding = _whole_cad(
            area.get("roundingAdjustmentCad"),
            f"{area_key}.roundingAdjustmentCad",
        )
        pil = _whole_cad(
            area.get("pilAndSupplementaryCad"),
            f"{area_key}.pilAndSupplementaryCad",
        )
        after_pil = _whole_cad(
            area.get("taxSupportedTotalCad"),
            f"{area_key}.taxSupportedTotalCad",
        )
        if line_total != stored_line_total:
            raise RegionScheduleError(
                f"{area_key}: service line sum {line_total} != "
                f"stored {stored_line_total}"
            )
        if published_subtotal - line_total != rounding:
            raise RegionScheduleError(
                f"{area_key}: rounding adjustment does not bridge lines to subtotal"
            )
        if abs(rounding) > ROUNDING_TOLERANCE_CAD:
            raise RegionScheduleError(
                f"{area_key}: rounding adjustment {rounding} exceeds "
                f"{ROUNDING_TOLERANCE_CAD}"
            )
        if published_subtotal + pil != after_pil:
            raise RegionScheduleError(
                f"{area_key}: published subtotal + PIL does not equal after-PIL total"
            )

    reconciliation = document.get("programBasisReconciliation")
    if not isinstance(reconciliation, dict):
        raise RegionScheduleError("programBasisReconciliation must be an object")
    if reconciliation.get("unit") != "CAD thousands":
        raise RegionScheduleError(
            "programBasisReconciliation.unit must be 'CAD thousands'"
        )
    reference_lines = areas["blended"]["lines"]
    computed_net = sum(
        (
            _whole_cad(
                line["netExpenditure000Cad"],
                f"{line['id']}.netExpenditure000Cad",
            )
            for line in reference_lines
        ),
        Decimal("0"),
    )
    computed_levy = sum(
        (
            _whole_cad(
                line["propertyTaxLevy000Cad"],
                f"{line['id']}.propertyTaxLevy000Cad",
            )
            for line in reference_lines
        ),
        Decimal("0"),
    )
    program_values = {
        field: _whole_cad(reconciliation.get(field), field)
        for field in (
            "serviceLineNetExpenditureSum000Cad",
            "publishedNetExpenditureSubtotal000Cad",
            "netExpenditureRoundingAdjustment000Cad",
            "serviceLinePropertyTaxLevySum000Cad",
            "publishedPropertyTaxLevySubtotal000Cad",
            "generalRevenueOffset000Cad",
            "regionalTaxLevyRoundingAdjustment000Cad",
            "publishedRegionalTaxLevy000Cad",
        )
    }
    if program_values["serviceLineNetExpenditureSum000Cad"] != computed_net:
        raise RegionScheduleError("program net-expenditure line sum drift")
    if (
        program_values["publishedNetExpenditureSubtotal000Cad"] - computed_net
        != program_values["netExpenditureRoundingAdjustment000Cad"]
    ):
        raise RegionScheduleError("program net-expenditure subtotal does not reconcile")
    if program_values["serviceLinePropertyTaxLevySum000Cad"] != computed_levy:
        raise RegionScheduleError("program property-tax-levy line sum drift")
    if (
        program_values["publishedPropertyTaxLevySubtotal000Cad"]
        != program_values["serviceLinePropertyTaxLevySum000Cad"]
    ):
        raise RegionScheduleError("program property-tax-levy subtotal does not reconcile")
    if (
        program_values["publishedPropertyTaxLevySubtotal000Cad"]
        + program_values["generalRevenueOffset000Cad"]
        + program_values["regionalTaxLevyRoundingAdjustment000Cad"]
        != program_values["publishedRegionalTaxLevy000Cad"]
    ):
        raise RegionScheduleError("program gross-to-net Regional Tax Levy does not reconcile")

    coverage = document.get("coverage")
    if not isinstance(coverage, dict):
        raise RegionScheduleError("schedule.coverage must be an object")
    if coverage.get("areaKeys") != list(AREA_KEYS):
        raise RegionScheduleError("coverage.areaKeys is incomplete or reordered")
    if coverage.get("municipalityAreaKeys") != MUNICIPALITY_AREA_KEYS:
        raise RegionScheduleError("coverage.municipalityAreaKeys is incomplete")
    expected_allocations = EXPECTED_SERVICE_ROWS * len(AREA_KEYS)
    if coverage.get("serviceRows") != EXPECTED_SERVICE_ROWS:
        raise RegionScheduleError("coverage.serviceRows does not reconcile")
    if coverage.get("householdAllocations") != expected_allocations:
        raise RegionScheduleError("coverage.householdAllocations does not reconcile")
    limitations = coverage.get("limitations")
    if not isinstance(limitations, list) or not limitations:
        raise RegionScheduleError("coverage.limitations must disclose exclusions")

    source_table: dict[str, Any] | None = None
    if verify_source_files:
        source_path = _repo_path(root, source.get("localPath"), "source.localPath")
        extract_path = _repo_path(root, source.get("extractPath"), "source.extractPath")
        for path, label in ((source_path, "source PDF"), (extract_path, "source extract")):
            if not path.is_file():
                raise RegionScheduleError(f"{label} is missing: {path}")

        declared_source_hash = source.get("sha256")
        declared_extract_hash = source.get("extractedTextSha256")
        for declared, label in (
            (declared_source_hash, "source.sha256"),
            (declared_extract_hash, "source.extractedTextSha256"),
        ):
            if not isinstance(declared, str) or not SHA256.fullmatch(declared):
                raise RegionScheduleError(f"{label} must be a lowercase SHA-256")
        if sha256_file(source_path) != declared_source_hash:
            raise RegionScheduleError("source PDF SHA-256 mismatch")
        if sha256_file(extract_path) != declared_extract_hash:
            raise RegionScheduleError("source extract SHA-256 mismatch")
        if source_path.stat().st_size != source.get("bytes"):
            raise RegionScheduleError("source PDF byte-length mismatch")
        if extract_path.stat().st_size != source.get("extractedTextBytes"):
            raise RegionScheduleError("source extract byte-length mismatch")

        if PdfReader is None:
            raise RegionScheduleError("pypdf is required to check the cited PDF page")
        actual_page_count = len(PdfReader(str(source_path)).pages)
        if actual_page_count != page_count:
            raise RegionScheduleError(
                f"source PDF has {actual_page_count} pages; declared {page_count}"
            )

        extract_text = extract_path.read_text(encoding="utf-8")
        pages = split_pages(extract_text)
        if set(pages) != set(range(1, page_count + 1)):
            raise RegionScheduleError(
                "source extract page markers do not exactly cover the PDF page range"
            )
        page_text = pages.get(page)
        if page_text is None:
            raise RegionScheduleError(f"cited page {page} is missing from the extract")
        if (
            "Annual Average Cost Per Household" not in page_text
            or "Tax Supported Services" not in page_text
        ):
            raise RegionScheduleError(f"cited page {page} is not the household table")
        source_table = parse_source_table(page_text)

        for index, parsed in enumerate(source_table["serviceRows"]):
            schedule_line = areas["blended"]["lines"][index]
            if parsed["label"] != schedule_line["label"]:
                raise RegionScheduleError(
                    f"source row {index + 1} label does not bind to the schedule"
                )
            if (
                parsed["netExpenditure000Cad"]
                != schedule_line["netExpenditure000Cad"]
                or parsed["propertyTaxLevy000Cad"]
                != schedule_line["propertyTaxLevy000Cad"]
            ):
                raise RegionScheduleError(
                    f"source row {index + 1} program amounts do not bind to the schedule"
                )
            for area_key in AREA_KEYS:
                if (
                    parsed["householdCad"][area_key]
                    != areas[area_key]["lines"][index]["amountCad"]
                ):
                    raise RegionScheduleError(
                        f"source row {index + 1} {area_key} amount does not bind"
                    )

        for area_key in AREA_KEYS:
            area = areas[area_key]
            if (
                source_table["publishedServicesSubtotalCad"][area_key]
                != area["publishedServicesSubtotalCad"]
                or source_table["householdPilCad"]
                != area["pilAndSupplementaryCad"]
                or source_table["taxSupportedTotalCad"][area_key]
                != area["taxSupportedTotalCad"]
            ):
                raise RegionScheduleError(
                    f"source footer controls do not bind for area {area_key!r}"
                )
        source_program_fields = {
            "publishedNetExpenditureSubtotal000Cad",
            "publishedPropertyTaxLevySubtotal000Cad",
            "generalRevenueOffset000Cad",
            "publishedRegionalTaxLevy000Cad",
        }
        for field in source_program_fields:
            if source_table[field] != reconciliation[field]:
                raise RegionScheduleError(
                    f"source footer {field} does not bind to reconciliation"
                )

    return {
        "document": document,
        "sourceTable": source_table,
        "schedulePath": schedule_path,
    }


def verify_source_lock(
    document: dict[str, Any],
    *,
    root: Path = ROOT,
    schedule_path: Path = DEFAULT_SCHEDULE,
    source_lock_path: Path = DEFAULT_SOURCE_LOCK,
) -> dict[str, Any]:
    if not source_lock_path.is_file():
        raise RegionScheduleError(f"missing regional source lock: {source_lock_path}")
    try:
        source_lock = json.loads(source_lock_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RegionScheduleError(f"cannot read regional source lock: {exc}") from exc
    if not isinstance(source_lock, dict):
        raise RegionScheduleError("regional source lock must contain an object")

    expected = {
        "schemaVersion": SOURCE_LOCK_SCHEMA_VERSION,
        "artifact": "SourceLock",
        "jurisdictionSlug": JURISDICTION_SLUG,
        "fiscalYear": FISCAL_YEAR,
        "currency": CURRENCY,
        "ledgerPath": "data/region-waterloo/evidence-ledger.json",
    }
    for field, value in expected.items():
        if source_lock.get(field) != value:
            raise RegionScheduleError(
                f"source lock {field}={source_lock.get(field)!r}; expected {value!r}"
            )

    entries = source_lock.get("sources")
    if not isinstance(entries, list) or len(entries) != 1:
        raise RegionScheduleError("regional source lock must contain exactly one source")
    locked_source = entries[0]
    if not isinstance(locked_source, dict) or locked_source.get("id") != SOURCE_ID:
        raise RegionScheduleError("regional source lock source id drift")
    schedule_source = document["source"]
    field_pairs = {
        "localPath": "localPath",
        "extractedText": "extractPath",
        "sha256": "sha256",
        "extractedTextSha256": "extractedTextSha256",
        "bytes": "bytes",
        "extractedTextBytes": "extractedTextBytes",
        "fiscalYear": "fiscalYear",
        "currency": "currency",
        "publisher": "publisher",
        "documentKind": "documentKind",
        "adoptionStatus": "adoptionStatus",
        "retrievedAt": "retrievedAt",
        "retrievalStatus": "retrievalStatus",
        "pageCount": "pdfPageCount",
        "citedPages": "citedPages",
    }
    for lock_field, schedule_field in field_pairs.items():
        if locked_source.get(lock_field) != schedule_source.get(schedule_field):
            raise RegionScheduleError(
                f"source lock {lock_field} disagrees with schedule source metadata"
            )

    artifacts = source_lock.get("artifacts")
    if not isinstance(artifacts, dict):
        raise RegionScheduleError("source lock artifacts must be an object")
    required_artifacts = {
        "pack": "corpus/region-of-waterloo-on/pack.yaml",
        "schedule": "corpus/region-of-waterloo-on/schedules/household-tax-supported-2026.yaml",
        "ledger": "data/region-waterloo/evidence-ledger.json",
        "receipt": "data/region-waterloo/taxpayer-receipt.json",
    }
    for role, expected_path in required_artifacts.items():
        locked = artifacts.get(role)
        if not isinstance(locked, dict):
            raise RegionScheduleError(f"source lock is missing artifact {role!r}")
        if locked.get("path") != expected_path:
            raise RegionScheduleError(f"source lock {role} path drift")
        artifact_path = _repo_path(root, locked.get("path"), f"artifacts.{role}.path")
        if not artifact_path.is_file():
            raise RegionScheduleError(f"locked artifact {role!r} is missing")
        declared_hash = locked.get("sha256")
        if not isinstance(declared_hash, str) or not SHA256.fullmatch(declared_hash):
            raise RegionScheduleError(f"locked artifact {role!r} has invalid SHA-256")
        if sha256_file(artifact_path) != declared_hash:
            raise RegionScheduleError(f"locked artifact {role!r} SHA-256 mismatch")
        if artifact_path.stat().st_size != locked.get("bytes"):
            raise RegionScheduleError(f"locked artifact {role!r} byte-length mismatch")
        if locked.get("lineEndings") != "LF":
            raise RegionScheduleError(f"locked artifact {role!r} lacks LF disclosure")

    schedule_locked_path = _repo_path(
        root, artifacts["schedule"]["path"], "artifacts.schedule.path"
    )
    if schedule_locked_path.resolve() != schedule_path.resolve():
        raise RegionScheduleError("loaded schedule path does not match the locked schedule")
    if source_lock.get("ledgerSha256") != artifacts["ledger"]["sha256"]:
        raise RegionScheduleError("source lock ledgerSha256 disagrees with artifact lock")

    return source_lock


def load_region_schedule(
    area_key: str,
    schedule_path: Path | None = None,
    *,
    source_lock_path: Path | None = None,
    root: Path = ROOT,
    verify_locks: bool = True,
) -> dict[str, Any]:
    """Return one area only after the shared 2026 schedule passes every lock.

    Existing consumers retain the original keys.  Additional year, currency,
    coverage, program-basis, and lock metadata are returned for explicit
    downstream provenance.
    """

    if yaml is None:
        raise SystemExit("PyYAML required (pip install pyyaml)")
    if area_key not in AREA_KEYS:
        raise SystemExit(f"unknown regionAreaKey {area_key!r}; expected one of {AREA_KEYS}")
    path = schedule_path or DEFAULT_SCHEDULE
    lock_path = source_lock_path or DEFAULT_SOURCE_LOCK
    if not path.exists():
        raise SystemExit(
            f"missing {path}\nRun: python scripts/parse_row_household_schedule.py"
        )
    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
        validation = validate_schedule_document(
            loaded,
            root=root,
            schedule_path=path,
            verify_source_files=verify_locks,
        )
        source_lock = (
            verify_source_lock(
                loaded,
                root=root,
                schedule_path=path,
                source_lock_path=lock_path,
            )
            if verify_locks
            else None
        )
    except (OSError, RegionScheduleError, json.JSONDecodeError) as exc:
        raise SystemExit(f"invalid Region of Waterloo schedule: {exc}") from exc

    source = deepcopy(loaded["source"])
    area = deepcopy(loaded["areas"][area_key])
    return {
        "source": source,
        "area": area,
        "areaKey": area_key,
        "areaLabel": AREA_LABELS[area_key],
        "assessmentCad": source["assessmentCad"],
        "page": source["pdfPage"],
        "extractPath": source["extractPath"],
        "fiscalYear": loaded["fiscalYear"],
        "currency": loaded["currency"],
        "basis": deepcopy(loaded["allocationBasis"]),
        "coverage": deepcopy(loaded["coverage"]),
        "programBasisReconciliation": deepcopy(
            loaded["programBasisReconciliation"]
        ),
        "sourceTable": validation["sourceTable"],
        "sourceLock": source_lock,
    }
