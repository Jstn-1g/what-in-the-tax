"""Build Region of Waterloo shared upper-tier pack artifacts from the household schedule YAML.

Deterministic — no LLM. Consumes the schedule written by
``parse_row_household_schedule.py`` and emits an evidence ledger (plus a thin
receipt) that lower-tier packs can cite without copying service lines.

Usage:
  python scripts/parse_row_household_schedule.py
  python scripts/build_region_waterloo_pack.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None

ROOT = Path(__file__).resolve().parents[1]
SCHEDULE = (
    ROOT / "corpus" / "region-of-waterloo-on" / "schedules" / "household-tax-supported-2026.yaml"
)
DATA = ROOT / "data" / "region-waterloo"
WEB_DATA = ROOT / "web" / "src" / "data" / "region-waterloo"


def fact(**kwargs):
    kwargs.setdefault("kind", "FACT")
    return kwargs


def load_schedule(path: Path) -> dict:
    if yaml is None:
        raise SystemExit("PyYAML required (pip install pyyaml)")
    if not path.exists():
        raise SystemExit(
            f"missing schedule {path}\n"
            "Run: python scripts/parse_row_household_schedule.py"
        )
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def build_ledger(schedule: dict) -> dict:
    src = schedule["source"]
    page = src["pdfPage"]
    assessment = src["assessmentCad"]
    extract = src["extractPath"]

    sources = [
        {
            "id": "row-2026-book",
            "title": src["title"],
            "url": "https://www.regionofwaterloo.ca/",
            "localPath": "source-pdfs/2026_final_budget_book_region.pdf",
            "extractedText": extract,
            "asOf": "2026",
            "authority": "Region of Waterloo",
            "note": (
                "Annual Average Cost Per Household — Tax Supported Services. "
                f"Assessment basis ${assessment:,}."
            ),
        }
    ]

    facts: list[dict] = [
        fact(
            id="ROW-HH-ASSESSMENT-2026",
            sourceId="row-2026-book",
            page=page,
            label="Region-published average residential assessment for household cost table",
            amountCad=assessment,
            excerpt="per $354,500 Residential Assessment Value",
            status="approved",
        ),
        fact(
            id="ROW-HH-PIL-2026",
            sourceId="row-2026-book",
            page=page,
            label="Payments in Lieu & Supplementary Taxes (household share)",
            amountCad=schedule["areas"]["urban"]["pilAndSupplementaryCad"],
            excerpt="Less: Payments in Lieu & Supplementary Taxes(3) ($78)",
            status="approved",
            note="Same PIL offset applied to blended / urban / rural / woolwich / wilmot columns.",
        ),
    ]

    for area_key in ("urban", "rural"):
        area = schedule["areas"][area_key]
        prefix = "URBAN" if area_key == "urban" else "RURAL"
        facts.append(
            fact(
                id=f"ROW-{prefix}-HH-TOTAL-2026",
                sourceId="row-2026-book",
                page=page,
                label=f"Tax-supported regional services cost per average {area_key} household",
                amountCad=area["taxSupportedTotalCad"],
                excerpt=(
                    f"{area['label']} ... Regional Tax Levy ... "
                    f"${area['taxSupportedTotalCad']:,} ... Based on an average residential "
                    f"property valued at ${assessment:,}"
                ),
                status="approved",
                assessmentBasisCad=assessment,
                note=(
                    f"Authoritative after-PIL total. Sum of rounded lines = "
                    f"${area['servicesSubtotalCad']:,}; published services subtotal = "
                    f"${area['publishedServicesSubtotalCad']:,}; "
                    f"roundingAdjustmentCad = {area['roundingAdjustmentCad']}."
                ),
            )
        )
        for line in area["lines"]:
            facts.append(
                fact(
                    id=line["id"],
                    sourceId="row-2026-book",
                    page=page,
                    label=f"{area_key.capitalize()} household — {line['label']}",
                    amountCad=line["amountCad"],
                    regionalNetExpenditure000s=line["netExpenditure000Cad"],
                    regionalPropertyTaxLevy000s=line["propertyTaxLevy000Cad"],
                    excerpt=f"{line['label']} ... {area_key.capitalize()} ${line['amountCad']}",
                    status="approved",
                    assessmentBasisCad=assessment,
                )
            )

    return {
        "schemaVersion": "2.0.0",
        "artifact": "EvidenceLedger",
        "jurisdiction": {
            "slug": "region-of-waterloo-on",
            "name": "Region of Waterloo",
            "aliases": ["Waterloo Region", "Regional Municipality of Waterloo"],
            "level": "upper-tier",
            "upperTier": [],
            "assessmentCode": None,
            "note": (
                "Shared upper-tier household schedule pack. Lower tiers import by area key "
                "(urban / rural / woolwich / wilmot) — do not copy amounts into a differently "
                "assessed municipal bill without an explicit rate×assessment DERIVED path."
            ),
        },
        "evidencePolicy": {
            "rules": [
                "FACT requires a published source, page, and excerpt or numeric binding.",
                "DERIVED requires an explicit formula over FACT/DERIVED ids only.",
                "Never invent bill dollars to fill a GAP.",
                "JUDGMENT billImpactCad is always null until a formula is approved.",
                "Household schedule dollars are at Region average assessment $354,500.",
            ]
        },
        "sources": sources,
        "facts": facts,
        "derived": [],
        "gaps": [],
        "closedGaps": [
            {
                "id": "GAP-ROW-HH-SCHEDULE-TRANSCRIBE",
                "title": "Region household tax-supported schedule transcribed",
                "resolvedAt": "2026-07-25",
                "resolution": (
                    "Parsed from 2026 Final Budget Book page 12 via "
                    "scripts/parse_row_household_schedule.py into "
                    "corpus/region-of-waterloo-on/schedules/household-tax-supported-2026.yaml. "
                    "Published after-PIL totals are authoritative; line-sum vs published "
                    "subtotal differences are recorded as roundingAdjustmentCad."
                ),
            }
        ],
        "findings": [],
    }


def build_receipt(schedule: dict, ledger: dict) -> dict:
    """Thin receipt so validate_pack.py can gate the upper-tier pack."""
    urban = schedule["areas"]["urban"]
    rural = schedule["areas"]["rural"]
    assessment = schedule["source"]["assessmentCad"]
    page = schedule["source"]["pdfPage"]

    def area_lines(area: dict, area_key: str) -> list[dict]:
        lines = [
            {
                "id": line["id"],
                "label": line["label"],
                "amountCad": line["amountCad"],
                "classification": "region_tax_supported",
                "evidenceStatus": "FACT",
                "sourceFactId": line["id"],
            }
            for line in area["lines"]
        ]
        if area["roundingAdjustmentCad"]:
            lines.append(
                {
                    "id": f"ROW-HH-{area_key.upper()}-ROUNDING",
                    "label": "Unallocated table-rounding difference (source total vs summed lines)",
                    "amountCad": area["roundingAdjustmentCad"],
                    "classification": "reconciling_item",
                    "evidenceStatus": "RECONCILING",
                    "note": (
                        f"Printed lines sum ${area['servicesSubtotalCad']:,}; "
                        f"printed subtotal ${area['publishedServicesSubtotalCad']:,}."
                    ),
                }
            )
        lines.append(
            {
                "id": "ROW-HH-PIL-2026",
                "label": "Less: Payments in Lieu & Supplementary Taxes (household share)",
                "amountCad": area["pilAndSupplementaryCad"],
                "classification": "region_tax_supported",
                "evidenceStatus": "FACT",
                "sourceFactId": "ROW-HH-PIL-2026",
            }
        )
        return lines

    urban_lines = area_lines(urban, "urban")
    rural_lines = area_lines(rural, "rural")

    return {
        "schemaVersion": "2.0.0",
        "artifact": "TaxpayerReceipt",
        "status": "partial_evidence_based",
        "purpose": (
            "Region of Waterloo 2026 shared upper-tier household schedule. "
            "Illustrates published urban and rural tax-supported costs at $354,500 — "
            "not a combined municipal bill."
        ),
        "evidencePolicyRef": "data/region-waterloo/evidence-ledger.json",
        "jurisdiction": {
            "slug": "region-of-waterloo-on",
            "displayName": "Region of Waterloo",
            "level": "upper-tier",
            "aliases": ["Waterloo Region"],
        },
        "profiles": {
            "urbanAverageHousehold": {
                "description": (
                    f"Region-published urban (Kitchener / Waterloo / Cambridge) "
                    f"average at ${assessment:,}."
                ),
                "region": {
                    "basis": (
                        f"Region 2026 Budget Book p.{page} Urban column at ${assessment:,}"
                    ),
                    "amountCad": urban["taxSupportedTotalCad"],
                    "assessmentCad": assessment,
                    "evidenceStatus": "FACT",
                    "sourceFactId": "ROW-URBAN-HH-TOTAL-2026",
                    "uiLabel": "Region tax-supported (urban)",
                    "lineItems": urban_lines,
                    "lineItemsSumCheckCad": sum(x["amountCad"] for x in urban_lines),
                },
            },
            "ruralAverageHousehold": {
                "description": (
                    f"Region-published rural (North Dumfries / Wellesley) "
                    f"average at ${assessment:,}."
                ),
                "region": {
                    "basis": (
                        f"Region 2026 Budget Book p.{page} Rural column at ${assessment:,}"
                    ),
                    "amountCad": rural["taxSupportedTotalCad"],
                    "assessmentCad": assessment,
                    "evidenceStatus": "FACT",
                    "sourceFactId": "ROW-RURAL-HH-TOTAL-2026",
                    "uiLabel": "Region tax-supported (rural)",
                    "lineItems": rural_lines,
                    "lineItemsSumCheckCad": sum(x["amountCad"] for x in rural_lines),
                },
            },
        },
        "findings": [],
        "uiModelHints": {
            "regionBucketLabel": "Region tax-supported",
            "heroLabel": "Region household schedule · $354,500 average · 2026",
            "publishedFindingIds": [],
            "marqueeFindings": [],
        },
        "warnings": [
            "This pack is the shared upper-tier schedule only — not a City/Township bill.",
            "Do not add these $354,500 household dollars into a lower-tier rate×assessment "
            "bill without an explicit DERIVED path.",
        ],
    }


def write_json(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    schedule = load_schedule(SCHEDULE)
    ledger = build_ledger(schedule)
    receipt = build_receipt(schedule, ledger)

    for dest in (DATA, WEB_DATA):
        write_json(dest / "evidence-ledger.json", ledger)
        write_json(dest / "taxpayer-receipt.json", receipt)
        print(f"wrote {dest}")

    urban = schedule["areas"]["urban"]
    rural = schedule["areas"]["rural"]
    print(
        f"urban after-PIL ${urban['taxSupportedTotalCad']:,} · "
        f"rural after-PIL ${rural['taxSupportedTotalCad']:,} @ "
        f"${schedule['source']['assessmentCad']:,}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
