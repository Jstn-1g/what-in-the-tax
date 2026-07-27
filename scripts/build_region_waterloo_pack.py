"""Build the locked Region of Waterloo 2026 shared upper-tier source pack.

The build is deterministic and uses no model or network access.  It verifies
the official PDF, page-marked extract, all five household columns, every
service-row binding, and both household and program-basis control totals before
emitting the evidence ledger, receipt, and source lock.

Usage:
  python scripts/build_region_waterloo_pack.py
  python scripts/build_region_waterloo_pack.py --sync-web  # explicit legacy copy
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None

try:
    from scripts.lib.region_schedule import (
        AREA_KEYS,
        AREA_LABELS,
        CURRENCY,
        FISCAL_YEAR,
        JURISDICTION_SLUG,
        MUNICIPALITY_AREA_KEYS,
        SOURCE_ID,
        SOURCE_LOCK_SCHEMA_VERSION,
        RegionScheduleError,
        sha256_file,
        validate_schedule_document,
    )
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    from lib.region_schedule import (  # type: ignore
        AREA_KEYS,
        AREA_LABELS,
        CURRENCY,
        FISCAL_YEAR,
        JURISDICTION_SLUG,
        MUNICIPALITY_AREA_KEYS,
        SOURCE_ID,
        SOURCE_LOCK_SCHEMA_VERSION,
        RegionScheduleError,
        sha256_file,
        validate_schedule_document,
    )

ROOT = Path(__file__).resolve().parents[1]
PACK_PATH = ROOT / "corpus" / "region-of-waterloo-on" / "pack.yaml"
SCHEDULE = (
    ROOT
    / "corpus"
    / "region-of-waterloo-on"
    / "schedules"
    / "household-tax-supported-2026.yaml"
)
SOURCE_LOCK = ROOT / "corpus" / "region-of-waterloo-on" / "sources.lock.json"
DATA = ROOT / "data" / "region-waterloo"
WEB_DATA = ROOT / "web" / "src" / "data" / "region-waterloo"

SCHEMA_VERSION = "2.0.0"
LEDGER_REL = "data/region-waterloo/evidence-ledger.json"
RECEIPT_REL = "data/region-waterloo/taxpayer-receipt.json"
PACK_REL = "corpus/region-of-waterloo-on/pack.yaml"
SCHEDULE_REL = (
    "corpus/region-of-waterloo-on/schedules/household-tax-supported-2026.yaml"
)


def _decimal(value: Any) -> Decimal:
    return Decimal(str(value))


def _whole(value: Any) -> int:
    result = _decimal(value)
    if result != result.to_integral_value():
        raise RegionScheduleError(f"expected whole-dollar value, got {value!r}")
    return int(result)


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _json_bytes(value: dict[str, Any]) -> bytes:
    """Canonical project JSON: deterministic ordering, indentation, and LF."""

    return (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def _artifact_lock(path: str, content: bytes | None = None) -> dict[str, Any]:
    resolved = ROOT / path
    payload = content if content is not None else resolved.read_bytes()
    if b"\r\n" in payload:
        raise RegionScheduleError(f"locked text artifact is not LF-normalized: {path}")
    return {
        "path": path,
        "sha256": _sha256_bytes(payload),
        "bytes": len(payload),
        "lineEndings": "LF",
    }


def fact(**kwargs: Any) -> dict[str, Any]:
    kwargs.setdefault("kind", "FACT")
    kwargs.setdefault("fiscalYear", FISCAL_YEAR)
    kwargs.setdefault("currency", CURRENCY)
    return kwargs


def derived(**kwargs: Any) -> dict[str, Any]:
    kwargs.setdefault("kind", "DERIVED")
    kwargs.setdefault("fiscalYear", FISCAL_YEAR)
    kwargs.setdefault("currency", CURRENCY)
    kwargs.setdefault("calculationMethod", "Decimal")
    return kwargs


def _binding(
    *,
    row: str,
    column: str,
    printed_value: str,
    method: str = "deterministic-table-row-and-column",
) -> dict[str, Any]:
    return {
        "documentId": SOURCE_ID,
        "page": 12,
        "table": "Annual Average Cost Per Household for Regional Services",
        "row": row,
        "column": column,
        "printedValue": printed_value,
        "method": method,
    }


def load_schedule(path: Path = SCHEDULE) -> tuple[dict[str, Any], dict[str, Any]]:
    if yaml is None:
        raise SystemExit("PyYAML required (pip install pyyaml)")
    if not path.exists():
        raise SystemExit(
            f"missing schedule {path}\n"
            "Run: python scripts/parse_row_household_schedule.py, then review metadata"
        )
    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
        validation = validate_schedule_document(
            loaded,
            root=ROOT,
            schedule_path=path,
            verify_source_files=True,
        )
    except (OSError, RegionScheduleError) as exc:
        raise SystemExit(f"invalid regional schedule: {exc}") from exc
    source_table = validation["sourceTable"]
    if not isinstance(source_table, dict):  # pragma: no cover - verified above
        raise SystemExit("regional source table was not parsed")
    return loaded, source_table


def _source_record(schedule: dict[str, Any]) -> dict[str, Any]:
    source = schedule["source"]
    return {
        "id": source["id"],
        "title": source["title"],
        "url": source["url"],
        "publisher": source["publisher"],
        "authority": source["adoptionStatus"],
        "documentKind": source["documentKind"],
        "adoptionStatus": source["adoptionStatus"],
        "fiscalYear": source["fiscalYear"],
        "currency": source["currency"],
        "publicationDate": source["publicationDate"],
        "retrievedAt": source["retrievedAt"],
        "retrievalStatus": source["retrievalStatus"],
        "license": source["license"],
        "localPath": source["localPath"],
        "sha256": source["sha256"],
        "bytes": source["bytes"],
        "extractedText": source["extractPath"],
        "extractedTextSha256": source["extractedTextSha256"],
        "extractedTextBytes": source["extractedTextBytes"],
        "pageCount": source["pdfPageCount"],
        "citedPages": source["citedPages"],
        "note": (
            "Final Budget Book page 12, Annual Average Cost Per Household. "
            f"Household amounts use the Region-published ${source['assessmentCad']:,} "
            "average assessment and are printed to whole dollars."
        ),
    }


def _area_prefix(area_key: str) -> str:
    return area_key.upper()


def _area_total_fact_id(area_key: str) -> str:
    return f"ROW-{_area_prefix(area_key)}-HH-TOTAL-2026"


def _area_subtotal_fact_id(area_key: str) -> str:
    return f"ROW-{_area_prefix(area_key)}-HH-SUBTOTAL-2026"


def _area_line_sum_derived_id(area_key: str) -> str:
    return f"DRV-HH-{_area_prefix(area_key)}-LINE-SUM-2026"


def _area_rounding_derived_id(area_key: str) -> str:
    return f"DRV-HH-{_area_prefix(area_key)}-ROUNDING-2026"


def build_ledger(
    schedule: dict[str, Any], source_table: dict[str, Any]
) -> dict[str, Any]:
    source = schedule["source"]
    page = source["pdfPage"]
    assessment = _whole(source["assessmentCad"])
    footer_excerpt = source_table["footerExcerpt"]
    source_rows = source_table["serviceRows"]
    facts: list[dict[str, Any]] = []
    calculations: list[dict[str, Any]] = []

    facts.append(
        fact(
            id="ROW-HH-ASSESSMENT-2026",
            sourceId=SOURCE_ID,
            page=page,
            label=(
                "Region-published average residential assessment for the "
                "household cost table"
            ),
            amountCad=assessment,
            unit="CAD assessment",
            excerpt="per $354,500 Residential Assessment Value",
            status="final-budget",
            binding=_binding(
                row="Table header",
                column="Residential Assessment Value",
                printed_value="$354,500",
            ),
        )
    )
    facts.append(
        fact(
            id="ROW-HH-PIL-2026",
            sourceId=SOURCE_ID,
            page=page,
            label=(
                "Payments in Lieu and Supplementary Taxes household offset "
                "(identical in all five area columns)"
            ),
            amountCad=_whole(source_table["householdPilCad"]),
            unit="CAD per average household",
            excerpt=footer_excerpt,
            status="final-budget",
            binding=_binding(
                row="Less: Payments in Lieu & Supplementary Taxes",
                column="Blended / Urban / Rural / Woolwich / Wilmot",
                printed_value="($78) in each area column",
                method="deterministic-footer-column-sequence",
            ),
        )
    )

    program_control_specs = (
        (
            "ROW-PROGRAM-NET-SUBTOTAL-2026",
            "Tax-supported service net-expenditure subtotal",
            "publishedNetExpenditureSubtotal000Cad",
            "Net Expenditure ($000's)",
        ),
        (
            "ROW-PROGRAM-LEVY-SUBTOTAL-2026",
            "Tax-supported service property-tax-levy subtotal before general revenues",
            "publishedPropertyTaxLevySubtotal000Cad",
            "Property Tax Levy ($000's)",
        ),
        (
            "ROW-PROGRAM-GENERAL-REVENUE-OFFSET-2026",
            "Payments in Lieu and Supplementary Taxes general-revenue offset",
            "generalRevenueOffset000Cad",
            "Net Expenditure / Property Tax Levy ($000's)",
        ),
        (
            "ROW-PROGRAM-REGIONAL-TAX-LEVY-2026",
            "Published Regional Tax Levy after general revenues",
            "publishedRegionalTaxLevy000Cad",
            "Property Tax Levy ($000's)",
        ),
    )
    for fact_id, label, field, column in program_control_specs:
        value = _whole(source_table[field])
        facts.append(
            fact(
                id=fact_id,
                sourceId=SOURCE_ID,
                page=page,
                label=label,
                value=value,
                unit="CAD thousands",
                excerpt=footer_excerpt,
                status="final-budget",
                binding=_binding(
                    row=(
                        "Less: Payments in Lieu & Supplementary Taxes"
                        if field == "generalRevenueOffset000Cad"
                        else (
                            "Regional Tax Levy"
                            if field == "publishedRegionalTaxLevy000Cad"
                            else "Subtotal"
                        )
                    ),
                    column=column,
                    printed_value=f"{'(' if value < 0 else ''}{abs(value):,}"
                    f"{')' if value < 0 else ''} ($000)",
                    method="deterministic-footer-column-sequence",
                ),
            )
        )

    program_net_ids: list[str] = []
    program_levy_ids: list[str] = []
    for index, source_row in enumerate(source_rows, start=1):
        net_id = f"ROW-PROGRAM-NET-{index:02d}-2026"
        levy_id = f"ROW-PROGRAM-LEVY-{index:02d}-2026"
        program_net_ids.append(net_id)
        program_levy_ids.append(levy_id)
        facts.extend(
            [
                fact(
                    id=net_id,
                    sourceId=SOURCE_ID,
                    page=page,
                    label=f"{source_row['label']} — net expenditure",
                    value=_whole(source_row["netExpenditure000Cad"]),
                    unit="CAD thousands",
                    excerpt=source_row["sourceRow"],
                    status="final-budget",
                    binding=_binding(
                        row=source_row["sourceLabel"],
                        column="Net Expenditure ($000's)",
                        printed_value=f"{source_row['netExpenditure000Cad']:,}",
                    ),
                ),
                fact(
                    id=levy_id,
                    sourceId=SOURCE_ID,
                    page=page,
                    label=f"{source_row['label']} — property tax levy",
                    value=_whole(source_row["propertyTaxLevy000Cad"]),
                    unit="CAD thousands",
                    excerpt=source_row["sourceRow"],
                    status="final-budget",
                    binding=_binding(
                        row=source_row["sourceLabel"],
                        column="Property Tax Levy ($000's)",
                        printed_value=f"{source_row['propertyTaxLevy000Cad']:,}",
                    ),
                ),
            ]
        )

    reconciliation = schedule["programBasisReconciliation"]
    program_net_sum = _whole(reconciliation["serviceLineNetExpenditureSum000Cad"])
    program_levy_sum = _whole(reconciliation["serviceLinePropertyTaxLevySum000Cad"])
    net_rounding = _whole(reconciliation["netExpenditureRoundingAdjustment000Cad"])
    levy_rounding = _whole(
        reconciliation["regionalTaxLevyRoundingAdjustment000Cad"]
    )
    calculations.extend(
        [
            derived(
                id="DRV-PROGRAM-NET-LINE-SUM-2026",
                label="Sum of the 23 printed service net-expenditure rows",
                value=program_net_sum,
                unit="CAD thousands",
                formula=" + ".join(program_net_ids),
                inputs=program_net_ids,
            ),
            derived(
                id="DRV-PROGRAM-NET-ROUNDING-2026",
                label=(
                    "Printed net-expenditure subtotal less the sum of printed "
                    "service rows"
                ),
                value=net_rounding,
                unit="CAD thousands",
                formula=(
                    "ROW-PROGRAM-NET-SUBTOTAL-2026 - "
                    "DRV-PROGRAM-NET-LINE-SUM-2026"
                ),
                inputs=[
                    "ROW-PROGRAM-NET-SUBTOTAL-2026",
                    "DRV-PROGRAM-NET-LINE-SUM-2026",
                ],
                note="The source prints program values in $000 and has a 2-unit row-rounding difference.",
            ),
            derived(
                id="DRV-PROGRAM-NET-SUBTOTAL-CHECK-2026",
                label="Net-expenditure service rows reconcile to the published subtotal",
                value=_whole(reconciliation["publishedNetExpenditureSubtotal000Cad"]),
                unit="CAD thousands",
                formula=(
                    "sum(DRV-PROGRAM-NET-LINE-SUM-2026, "
                    "DRV-PROGRAM-NET-ROUNDING-2026) == "
                    "ROW-PROGRAM-NET-SUBTOTAL-2026"
                ),
                inputs=[
                    "DRV-PROGRAM-NET-LINE-SUM-2026",
                    "DRV-PROGRAM-NET-ROUNDING-2026",
                    "ROW-PROGRAM-NET-SUBTOTAL-2026",
                ],
            ),
            derived(
                id="DRV-PROGRAM-LEVY-LINE-SUM-2026",
                label="Sum of the 23 printed service property-tax-levy rows",
                value=program_levy_sum,
                unit="CAD thousands",
                formula=" + ".join(program_levy_ids),
                inputs=program_levy_ids,
            ),
            derived(
                id="DRV-PROGRAM-LEVY-SUBTOTAL-CHECK-2026",
                label="Service property-tax-levy rows reconcile to the published subtotal",
                value=_whole(
                    reconciliation["publishedPropertyTaxLevySubtotal000Cad"]
                ),
                unit="CAD thousands",
                formula=(
                    "sum(DRV-PROGRAM-LEVY-LINE-SUM-2026) == "
                    "ROW-PROGRAM-LEVY-SUBTOTAL-2026"
                ),
                inputs=[
                    "DRV-PROGRAM-LEVY-LINE-SUM-2026",
                    "ROW-PROGRAM-LEVY-SUBTOTAL-2026",
                ],
            ),
            derived(
                id="DRV-PROGRAM-REGIONAL-LEVY-ROUNDING-2026",
                label=(
                    "Printed Regional Tax Levy less subtotal plus general-revenue "
                    "offset"
                ),
                value=levy_rounding,
                unit="CAD thousands",
                formula=(
                    "ROW-PROGRAM-REGIONAL-TAX-LEVY-2026 - "
                    "(ROW-PROGRAM-LEVY-SUBTOTAL-2026 + "
                    "ROW-PROGRAM-GENERAL-REVENUE-OFFSET-2026)"
                ),
                inputs=[
                    "ROW-PROGRAM-REGIONAL-TAX-LEVY-2026",
                    "ROW-PROGRAM-LEVY-SUBTOTAL-2026",
                    "ROW-PROGRAM-GENERAL-REVENUE-OFFSET-2026",
                ],
                note="The $000 printed controls differ by one unit because source values are rounded.",
            ),
            derived(
                id="DRV-PROGRAM-REGIONAL-LEVY-CHECK-2026",
                label=(
                    "Property-tax-levy subtotal plus general revenues and printed "
                    "rounding reconciles to the Regional Tax Levy"
                ),
                value=_whole(reconciliation["publishedRegionalTaxLevy000Cad"]),
                unit="CAD thousands",
                formula=(
                    "sum(ROW-PROGRAM-LEVY-SUBTOTAL-2026, "
                    "ROW-PROGRAM-GENERAL-REVENUE-OFFSET-2026, "
                    "DRV-PROGRAM-REGIONAL-LEVY-ROUNDING-2026) == "
                    "ROW-PROGRAM-REGIONAL-TAX-LEVY-2026"
                ),
                inputs=[
                    "ROW-PROGRAM-LEVY-SUBTOTAL-2026",
                    "ROW-PROGRAM-GENERAL-REVENUE-OFFSET-2026",
                    "DRV-PROGRAM-REGIONAL-LEVY-ROUNDING-2026",
                    "ROW-PROGRAM-REGIONAL-TAX-LEVY-2026",
                ],
            ),
        ]
    )

    for area_key in AREA_KEYS:
        area = schedule["areas"][area_key]
        prefix = _area_prefix(area_key)
        facts.extend(
            [
                fact(
                    id=_area_subtotal_fact_id(area_key),
                    sourceId=SOURCE_ID,
                    page=page,
                    label=(
                        f"{AREA_LABELS[area_key]} household service subtotal "
                        "before the general-revenue offset"
                    ),
                    amountCad=_whole(area["publishedServicesSubtotalCad"]),
                    unit="CAD per average household",
                    excerpt=footer_excerpt,
                    status="final-budget",
                    assessmentBasisCad=assessment,
                    basis="printed service subtotal before household PIL/general-revenue offset",
                    binding=_binding(
                        row="Subtotal",
                        column=AREA_LABELS[area_key],
                        printed_value=f"${area['publishedServicesSubtotalCad']:,}",
                        method="deterministic-footer-column-sequence",
                    ),
                ),
                fact(
                    id=_area_total_fact_id(area_key),
                    sourceId=SOURCE_ID,
                    page=page,
                    label=(
                        f"{AREA_LABELS[area_key]} tax-supported regional services "
                        "cost per average household"
                    ),
                    amountCad=_whole(area["taxSupportedTotalCad"]),
                    unit="CAD per average household",
                    excerpt=footer_excerpt,
                    status="final-budget",
                    assessmentBasisCad=assessment,
                    basis="printed Regional Tax Levy after household PIL/general-revenue offset",
                    binding=_binding(
                        row="Regional Tax Levy",
                        column=AREA_LABELS[area_key],
                        printed_value=f"${area['taxSupportedTotalCad']:,}",
                        method="deterministic-footer-column-sequence",
                    ),
                ),
            ]
        )
        line_ids: list[str] = []
        for index, line in enumerate(area["lines"]):
            source_row = source_rows[index]
            line_ids.append(line["id"])
            facts.append(
                fact(
                    id=line["id"],
                    sourceId=SOURCE_ID,
                    page=page,
                    label=f"{AREA_LABELS[area_key]} household — {line['label']}",
                    amountCad=_whole(line["amountCad"]),
                    unit="CAD per average household",
                    regionalNetExpenditure000Cad=_whole(
                        line["netExpenditure000Cad"]
                    ),
                    regionalPropertyTaxLevy000Cad=_whole(
                        line["propertyTaxLevy000Cad"]
                    ),
                    excerpt=source_row["sourceRow"],
                    status="final-budget",
                    assessmentBasisCad=assessment,
                    basis="service allocation before household PIL/general-revenue offset",
                    binding=_binding(
                        row=source_row["sourceLabel"],
                        column=AREA_LABELS[area_key],
                        printed_value=f"${line['amountCad']:,}",
                    ),
                )
            )

        line_sum = _whole(area["servicesSubtotalCad"])
        rounding = _whole(area["roundingAdjustmentCad"])
        published_subtotal = _whole(area["publishedServicesSubtotalCad"])
        after_pil = _whole(area["taxSupportedTotalCad"])
        calculations.extend(
            [
                derived(
                    id=_area_line_sum_derived_id(area_key),
                    label=f"Sum of {AREA_LABELS[area_key]} printed service lines",
                    amountCad=line_sum,
                    formula=" + ".join(line_ids),
                    inputs=line_ids,
                    unit="CAD per average household",
                ),
                derived(
                    id=_area_rounding_derived_id(area_key),
                    label=(
                        f"{AREA_LABELS[area_key]} source-table line-rounding "
                        "adjustment"
                    ),
                    amountCad=rounding,
                    formula=(
                        f"{_area_subtotal_fact_id(area_key)} - "
                        f"{_area_line_sum_derived_id(area_key)}"
                    ),
                    inputs=[
                        _area_subtotal_fact_id(area_key),
                        _area_line_sum_derived_id(area_key),
                    ],
                    unit="CAD per average household",
                    note=(
                        f"Printed service rows sum ${line_sum:,}; the source prints "
                        f"a ${published_subtotal:,} subtotal."
                    ),
                ),
                derived(
                    id=f"DRV-HH-{prefix}-SUBTOTAL-CHECK-2026",
                    label=(
                        f"{AREA_LABELS[area_key]} service lines plus rounding "
                        "reconcile to the published subtotal"
                    ),
                    amountCad=published_subtotal,
                    formula=(
                        f"sum({_area_line_sum_derived_id(area_key)}, "
                        f"{_area_rounding_derived_id(area_key)}) == "
                        f"{_area_subtotal_fact_id(area_key)}"
                    ),
                    inputs=[
                        _area_line_sum_derived_id(area_key),
                        _area_rounding_derived_id(area_key),
                        _area_subtotal_fact_id(area_key),
                    ],
                    unit="CAD per average household",
                ),
                derived(
                    id=f"DRV-HH-{prefix}-AFTER-PIL-CHECK-2026",
                    label=(
                        f"{AREA_LABELS[area_key]} subtotal plus PIL/general "
                        "revenue reconciles to the published Regional Tax Levy"
                    ),
                    amountCad=after_pil,
                    formula=(
                        f"sum({_area_subtotal_fact_id(area_key)}, ROW-HH-PIL-2026) "
                        f"== {_area_total_fact_id(area_key)}"
                    ),
                    inputs=[
                        _area_subtotal_fact_id(area_key),
                        "ROW-HH-PIL-2026",
                        _area_total_fact_id(area_key),
                    ],
                    unit="CAD per average household",
                ),
            ]
        )

    coverage = schedule["coverage"]
    return {
        "schemaVersion": SCHEMA_VERSION,
        "artifact": "EvidenceLedger",
        "fiscalYear": FISCAL_YEAR,
        "currency": CURRENCY,
        "jurisdiction": {
            "slug": JURISDICTION_SLUG,
            "name": "Region of Waterloo",
            "aliases": ["Waterloo Region", "Regional Municipality of Waterloo"],
            "level": "upper-tier",
            "upperTier": [],
            "assessmentCode": None,
            "note": (
                "Shared upper-tier household schedule. Lower tiers select the "
                "verified area key declared in coverage.municipalityAreaKeys."
            ),
        },
        "evidencePolicy": {
            "rules": [
                "FACT requires the locked official source, a valid cited page, and a deterministic row/column binding.",
                "DERIVED calculations use Decimal and declare only FACT/DERIVED input ids.",
                "Household service lines are before the common general-revenue offset; published Regional Tax Levy totals are after it.",
                "Program-basis amounts are CAD thousands and must never be read as household dollars.",
                "Never rescale the $354,500 household illustration to a different property without an explicit rate-and-assessment derivation.",
            ]
        },
        "sources": [_source_record(schedule)],
        "facts": facts,
        "derived": calculations,
        "coverage": {
            "status": "complete-for-declared-tax-supported-household-scope",
            "sourcePage": page,
            "areaKeys": list(AREA_KEYS),
            "municipalityAreaKeys": MUNICIPALITY_AREA_KEYS,
            "serviceRows": coverage["serviceRows"],
            "householdAllocations": coverage["householdAllocations"],
            "factBindings": len(facts),
            "programBasis": "CAD thousands",
            "householdBasis": f"CAD per average household at ${assessment:,}",
            "included": coverage["included"],
            "excluded": coverage["excluded"],
            "limitations": coverage["limitations"],
        },
        "basisReconciliation": {
            **schedule["programBasisReconciliation"],
            "householdAreas": {
                key: {
                    "serviceLineSumCad": schedule["areas"][key][
                        "servicesSubtotalCad"
                    ],
                    "publishedServicesSubtotalCad": schedule["areas"][key][
                        "publishedServicesSubtotalCad"
                    ],
                    "lineRoundingAdjustmentCad": schedule["areas"][key][
                        "roundingAdjustmentCad"
                    ],
                    "generalRevenueOffsetCad": schedule["areas"][key][
                        "pilAndSupplementaryCad"
                    ],
                    "publishedRegionalTaxLevyCad": schedule["areas"][key][
                        "taxSupportedTotalCad"
                    ],
                }
                for key in AREA_KEYS
            },
        },
        "gaps": [
            {
                "id": "GAP-ROW-SOURCE-RETRIEVAL-TIMESTAMP",
                "title": "Original source retrieval timestamp was not recorded",
                "detail": (
                    "The official PDF URL, exact PDF bytes, exact extract bytes, "
                    "and hashes are locked. The original retrieval timestamp is "
                    "not independently documented and remains null rather than "
                    "being reconstructed."
                ),
                "blocks": ["claiming a precise source retrieval timestamp"],
                "neededEvidence": [
                    "Contemporaneous acquisition log for these exact PDF bytes"
                ],
                "kind": "GAP",
            }
        ],
        "closedGaps": [
            {
                "id": "GAP-ROW-HH-SCHEDULE-TRANSCRIBE",
                "title": "All five Region household tax-supported columns transcribed",
                "resolvedAt": "2026-07-25",
                "resolution": (
                    "The 23 service rows, five published subtotals, five common "
                    "household offsets, five after-offset controls, and program "
                    "gross-to-net controls are bound to Final Budget Book page 12."
                ),
            }
        ],
        "findings": [],
    }


def _profile_key(area_key: str) -> str:
    return f"{area_key}AverageHousehold"


def _municipalities_for_area(area_key: str) -> list[str]:
    return [
        slug
        for slug, mapped_area in MUNICIPALITY_AREA_KEYS.items()
        if mapped_area == area_key
    ]


def build_receipt(
    schedule: dict[str, Any],
    ledger: dict[str, Any],
) -> dict[str, Any]:
    """Build a complete declared-scope receipt model for the validation gate."""

    del ledger  # Fact ids are deterministic and checked by validate_pack.py.
    assessment = _whole(schedule["source"]["assessmentCad"])
    page = schedule["source"]["pdfPage"]
    profiles: dict[str, Any] = {}

    for area_key in AREA_KEYS:
        area = schedule["areas"][area_key]
        lines: list[dict[str, Any]] = [
            {
                "id": line["id"],
                "label": line["label"],
                "amountCad": _whole(line["amountCad"]),
                "classification": "region_tax_supported_before_general_revenue",
                "evidenceStatus": "FACT",
                "sourceFactId": line["id"],
            }
            for line in area["lines"]
        ]
        rounding = _whole(area["roundingAdjustmentCad"])
        if rounding:
            lines.append(
                {
                    "id": f"ROW-HH-{area_key.upper()}-ROUNDING",
                    "label": (
                        "Source table rounding: published service subtotal less "
                        "the sum of printed service lines"
                    ),
                    "amountCad": rounding,
                    "classification": "reconciling_item",
                    "evidenceStatus": "DERIVED",
                    "sourceFactId": _area_rounding_derived_id(area_key),
                    "note": (
                        f"Printed lines sum ${area['servicesSubtotalCad']:,}; "
                        f"printed subtotal ${area['publishedServicesSubtotalCad']:,}."
                    ),
                }
            )
        lines.append(
            {
                "id": f"ROW-HH-{area_key.upper()}-GENERAL-REVENUE-OFFSET",
                "label": "Less: Payments in Lieu and Supplementary Taxes",
                "amountCad": _whole(area["pilAndSupplementaryCad"]),
                "classification": "region_general_revenue_offset",
                "evidenceStatus": "FACT",
                "sourceFactId": "ROW-HH-PIL-2026",
            }
        )
        line_sum = sum((_decimal(item["amountCad"]) for item in lines), Decimal("0"))
        total = _whole(area["taxSupportedTotalCad"])
        if line_sum != Decimal(total):
            raise RegionScheduleError(
                f"{area_key} receipt line sum {line_sum} does not equal {total}"
            )

        profiles[_profile_key(area_key)] = {
            "description": (
                f"Region-published {AREA_LABELS[area_key]} household illustration "
                f"at ${assessment:,}."
            ),
            "areaKey": area_key,
            "applicableMunicipalitySlugs": _municipalities_for_area(area_key),
            "region": {
                "basis": (
                    f"Region 2026 Final Budget Book p.{page} "
                    f"{AREA_LABELS[area_key]} column at ${assessment:,}; "
                    "after the common general-revenue offset"
                ),
                "amountCad": total,
                "assessmentCad": assessment,
                "fiscalYear": FISCAL_YEAR,
                "currency": CURRENCY,
                "evidenceStatus": "FACT",
                "sourceFactId": _area_total_fact_id(area_key),
                "uiLabel": f"Region tax-supported ({area_key})",
                "lineItems": lines,
                "lineItemsSumCheckCad": int(line_sum),
                "controlReconciliation": {
                    "serviceLineSumCad": _whole(area["servicesSubtotalCad"]),
                    "publishedServiceSubtotalCad": _whole(
                        area["publishedServicesSubtotalCad"]
                    ),
                    "lineRoundingAdjustmentCad": rounding,
                    "generalRevenueOffsetCad": _whole(
                        area["pilAndSupplementaryCad"]
                    ),
                    "publishedRegionalTaxLevyCad": total,
                },
            },
        }

    coverage = schedule["coverage"]
    return {
        "schemaVersion": SCHEMA_VERSION,
        "artifact": "TaxpayerReceipt",
        "status": "partial_evidence_based",
        "fiscalYear": FISCAL_YEAR,
        "currency": CURRENCY,
        "purpose": (
            "Region of Waterloo 2026 shared upper-tier household schedule. "
            "It illustrates the five published tax-supported area columns at "
            "$354,500 and is not a combined lower-tier property-tax bill."
        ),
        "evidencePolicyRef": LEDGER_REL,
        "jurisdiction": {
            "slug": JURISDICTION_SLUG,
            "displayName": "Region of Waterloo",
            "level": "upper-tier",
            "aliases": ["Waterloo Region"],
        },
        "allocationBasis": schedule["allocationBasis"],
        "coverage": {
            "status": "complete-for-declared-tax-supported-household-scope",
            "areaKeys": list(AREA_KEYS),
            "municipalityAreaKeys": MUNICIPALITY_AREA_KEYS,
            "serviceRows": coverage["serviceRows"],
            "householdAllocations": coverage["householdAllocations"],
            "included": coverage["included"],
            "excluded": coverage["excluded"],
            "limitations": coverage["limitations"],
        },
        "profiles": profiles,
        "findings": [],
        "uiModelHints": {
            "regionBucketLabel": "Region tax-supported",
            "heroLabel": "Region household schedule · $354,500 average · 2026",
            "publishedFindingIds": [],
            "marqueeFindings": [],
        },
        "warnings": [
            "This is a shared upper-tier household illustration, not a City or Township bill.",
            "Service lines are before the common $78 general-revenue offset; the profile total is after it.",
            "Program totals are printed in CAD thousands and are not household-dollar amounts.",
            "Do not rescale these $354,500 household dollars to another assessment without an explicit rate-and-assessment derivation.",
        ],
    }


def build_source_lock(
    schedule: dict[str, Any],
    *,
    ledger_bytes: bytes,
    receipt_bytes: bytes,
) -> dict[str, Any]:
    source = schedule["source"]
    source_path = ROOT / source["localPath"]
    extract_path = ROOT / source["extractPath"]
    source_entry = {
        "id": source["id"],
        "title": source["title"],
        "url": source["url"],
        "publisher": source["publisher"],
        "documentKind": source["documentKind"],
        "adoptionStatus": source["adoptionStatus"],
        "fiscalYear": source["fiscalYear"],
        "currency": source["currency"],
        "publicationDate": source["publicationDate"],
        "retrievedAt": source["retrievedAt"],
        "retrievalStatus": source["retrievalStatus"],
        "license": source["license"],
        "localPath": source["localPath"],
        "sha256": sha256_file(source_path),
        "bytes": source_path.stat().st_size,
        "extractedText": source["extractPath"],
        "extractedTextSha256": sha256_file(extract_path),
        "extractedTextBytes": extract_path.stat().st_size,
        "pageCount": source["pdfPageCount"],
        "citedPages": source["citedPages"],
        "lockStatus": "source-extract-pages-and-generated-artifacts",
    }
    artifacts = {
        "pack": _artifact_lock(PACK_REL),
        "schedule": _artifact_lock(SCHEDULE_REL),
        "ledger": _artifact_lock(LEDGER_REL, ledger_bytes),
        "receipt": _artifact_lock(RECEIPT_REL, receipt_bytes),
    }
    return {
        "schemaVersion": SOURCE_LOCK_SCHEMA_VERSION,
        "artifact": "SourceLock",
        "jurisdictionSlug": JURISDICTION_SLUG,
        "fiscalYear": FISCAL_YEAR,
        "currency": CURRENCY,
        "ledgerPath": LEDGER_REL,
        "ledgerSha256": artifacts["ledger"]["sha256"],
        "sources": [source_entry],
        "artifacts": artifacts,
        "hashScope": {
            "algorithm": "SHA-256",
            "bytePolicy": "Raw bytes; all locked text artifacts are UTF-8 with LF line endings.",
            "includes": [
                "official source PDF",
                "page-marked source extract",
                "pack descriptor",
                "household schedule",
                "evidence ledger",
                "taxpayer receipt",
            ],
            "excludes": [
                "this self-referential lock file",
                "timestamped validation reports",
                "citation audit regenerated deterministically from the locked ledger and extract",
            ],
        },
        "coverage": {
            "sourceCount": 1,
            "citedPages": source["citedPages"],
            "areaKeys": list(AREA_KEYS),
            "serviceRows": schedule["coverage"]["serviceRows"],
            "householdAllocations": schedule["coverage"][
                "householdAllocations"
            ],
        },
        "generatedBy": "scripts/build_region_waterloo_pack.py",
    }


def write_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


def build_artifacts() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    schedule, source_table = load_schedule(SCHEDULE)
    ledger = build_ledger(schedule, source_table)
    receipt = build_receipt(schedule, ledger)
    ledger_bytes = _json_bytes(ledger)
    receipt_bytes = _json_bytes(receipt)
    source_lock = build_source_lock(
        schedule,
        ledger_bytes=ledger_bytes,
        receipt_bytes=receipt_bytes,
    )
    return ledger, receipt, source_lock


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sync-web",
        action="store_true",
        help=(
            "also update the legacy web/src/data copy; omitted by default so "
            "source-pack builds do not mutate public/frontend artifacts"
        ),
    )
    args = parser.parse_args(argv)

    try:
        ledger, receipt, source_lock = build_artifacts()
    except (OSError, RegionScheduleError, SystemExit) as exc:
        if isinstance(exc, SystemExit):
            raise
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    ledger_bytes = _json_bytes(ledger)
    receipt_bytes = _json_bytes(receipt)
    lock_bytes = _json_bytes(source_lock)
    write_bytes(DATA / "evidence-ledger.json", ledger_bytes)
    write_bytes(DATA / "taxpayer-receipt.json", receipt_bytes)
    write_bytes(SOURCE_LOCK, lock_bytes)
    print(f"wrote {DATA}")
    print(f"wrote {SOURCE_LOCK}")

    if args.sync_web:
        write_bytes(WEB_DATA / "evidence-ledger.json", ledger_bytes)
        write_bytes(WEB_DATA / "taxpayer-receipt.json", receipt_bytes)
        print(f"wrote {WEB_DATA}")

    controls = " · ".join(
        f"{key} ${schedule_total:,}"
        for key, schedule_total in (
            (key, ledger["basisReconciliation"]["householdAreas"][key][
                "publishedRegionalTaxLevyCad"
            ])
            for key in AREA_KEYS
        )
    )
    print(f"{controls} @ ${ledger['facts'][0]['amountCad']:,}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
