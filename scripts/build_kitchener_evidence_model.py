"""Build City of Kitchener 2026 evidence ledger + taxpayer receipt.

Lower-tier in Region of Waterloo (same bill shape as North Dumfries):
City portion + Region portion + Education.

Rules:
- FACT: quoted from source with page + amount
- DERIVED: computed only from FACT ids with explicit formula
- GAP: missing evidence — never invent amounts
- JUDGMENT: interpretive; billImpactCad always null
"""

from __future__ import annotations

import json
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "kitchener"
WEB_DATA = ROOT / "web" / "src" / "data" / "kitchener"
REGION_SCHEDULE = (
    ROOT / "corpus" / "region-of-waterloo-on" / "schedules" / "household-tax-supported-2026.yaml"
)
DATA.mkdir(parents=True, exist_ok=True)
WEB_DATA.mkdir(parents=True, exist_ok=True)


def load_region_urban_schedule() -> dict:
    """Load urban HH schedule from the shared Region pack YAML."""
    if yaml is None:
        raise SystemExit("PyYAML required (pip install pyyaml)")
    if not REGION_SCHEDULE.exists():
        raise SystemExit(
            f"missing {REGION_SCHEDULE}\n"
            "Run: python scripts/parse_row_household_schedule.py"
        )
    doc = yaml.safe_load(REGION_SCHEDULE.read_text(encoding="utf-8"))
    urban = doc["areas"]["urban"]
    return {
        "source": doc["source"],
        "urban": urban,
        "assessmentCad": doc["source"]["assessmentCad"],
        "page": doc["source"]["pdfPage"],
        "extractPath": doc["source"]["extractPath"],
    }


def fact(**kwargs):
    kwargs.setdefault("kind", "FACT")
    return kwargs


def gap(**kwargs):
    kwargs.setdefault("kind", "GAP")
    return kwargs


def derived(**kwargs):
    kwargs.setdefault("kind", "DERIVED")
    return kwargs


# --- Control totals from 2026 Budget Summary + Appendix B ---
LEVY_2026 = 171_432_000  # published net tax levy (Budget at a Glance)
# Department net expenditures (Appendix B) — allocation base for city-share pro-rata
ALLOC_BASE = 170_039_303
AVG_ASSESSMENT = 326_000
CITY_TAX_INCREASE_PCT = 2.2
CITY_TAX_INCREASE_CAD = 29  # published average-home impact (city portion only)

# RT Residential from 2026 Final Tax Rates PDF
RATE_CITY = 0.00411164
RATE_REGION = 0.00841834
RATE_EDUCATION = 0.00153000
RATE_TOTAL = 0.01405998

# Appendix B department totals (2026 Annual Budget column)
DEPTS = [
    ("KIT-DEPT-CAO-2026", "Chief Administrator's Office", 1_443_066, 2),
    ("KIT-DEPT-CSD-2026", "Community Services", 66_995_305, 2),
    ("KIT-DEPT-FIN-2026", "Financial Services", 5_390_745, 2),
    ("KIT-DEPT-COR-2026", "Corporate Services", 19_607_218, 2),
    ("KIT-DEPT-DSD-2026", "Development Services", 17_106_029, 2),
    ("KIT-DEPT-INS-2026", "Infrastructure Services", 59_496_940, 3),
]

assert sum(d[2] for d in DEPTS) == ALLOC_BASE

# Fire sits inside Community Services — disclosure subline only
FIRE_2026 = 44_407_986

CITY_PORTION = round(AVG_ASSESSMENT * RATE_CITY, 2)
REGION_PORTION = round(AVG_ASSESSMENT * RATE_REGION, 2)
EDUCATION_PORTION = round(AVG_ASSESSMENT * RATE_EDUCATION, 2)
COMBINED_TOTAL = round(CITY_PORTION + REGION_PORTION + EDUCATION_PORTION, 2)
assert COMBINED_TOTAL == round(AVG_ASSESSMENT * RATE_TOTAL, 2)

sources = [
    {
        "id": "kit-2026-budget-summary",
        "title": "City of Kitchener 2026 Budget Summary — Affordable Today, Ready for Tomorrow",
        "url": "https://www.kitchener.ca/media/2mxbmlay/cok_fin_budget_2026.pdf",
        "localPath": "source-pdfs/kitchener/2026-budget-summary.pdf",
        "extractedText": "data/_extracts/kitchener/2026-budget-summary.txt",
        "asOf": "2025-12",
        "authority": "City of Kitchener",
        "note": "Approved budget summary; net tax levy and average-home impact.",
    },
    {
        "id": "kit-2026-appendix-b",
        "title": "City of Kitchener 2026 Budget — Appendix B Operating Budget",
        "url": "https://www.kitchener.ca/media/kzxdj3nt/cok_fin_budget_2026_appendix-b-operating.pdf",
        "localPath": "source-pdfs/kitchener/2026-appendix-b-operating.pdf",
        "extractedText": "data/_extracts/kitchener/2026-appendix-b-operating.txt",
        "asOf": "2025-12",
        "authority": "City of Kitchener",
        "note": "Comparative budget by division; department net expenditure totals.",
    },
    {
        "id": "kit-2026-tax-rates",
        "title": "City of Kitchener 2026 Final Tax Rates",
        "url": "https://kitchener-ca.govstack.com/media/1itfipd0/2026-rates-remediated.pdf",
        "localPath": "source-pdfs/kitchener/2026-final-tax-rates.pdf",
        "extractedText": "data/_extracts/kitchener/2026-final-tax-rates.txt",
        "asOf": "2026",
        "authority": "City of Kitchener",
        "note": "City, Region, and education rates by tax class (RT residential).",
    },
]

# Shared Region urban household schedule ($354,500) — informational only vs $326k bill.
_region_sched = load_region_urban_schedule()
_urban = _region_sched["urban"]
REGION_HH_ASSESSMENT = _region_sched["assessmentCad"]
REGION_HH_PAGE = _region_sched["page"]
REGION_URBAN_AFTER_PIL = _urban["taxSupportedTotalCad"]

sources.append(
    {
        "id": "row-2026-book",
        "title": _region_sched["source"]["title"],
        "url": "https://www.regionofwaterloo.ca/",
        "localPath": "source-pdfs/2026_final_budget_book_region.pdf",
        "extractedText": _region_sched["extractPath"],
        "asOf": "2026",
        "authority": "Region of Waterloo",
        "note": (
            "Shared pack schedule: corpus/region-of-waterloo-on/schedules/"
            "household-tax-supported-2026.yaml (urban column). "
            f"Dollars are at Region average ${REGION_HH_ASSESSMENT:,} — not the "
            f"City average ${AVG_ASSESSMENT:,}."
        ),
    }
)

facts = [
    fact(
        id="KIT-LEVY-2026",
        sourceId="kit-2026-budget-summary",
        page=4,
        label="City of Kitchener 2026 published net tax levy",
        amountCad=LEVY_2026,
        excerpt="• Net tax levy:  $171,432,000",
        status="approved",
    ),
    fact(
        id="KIT-AVG-ASSESSMENT-2026",
        sourceId="kit-2026-budget-summary",
        page=4,
        label="Average assessed value used for residential impact illustrations",
        amountCad=AVG_ASSESSMENT,
        excerpt="Property Taxes 2.20% $29 Assessment of $326,000",
        status="approved",
    ),
    fact(
        id="KIT-TAX-INCREASE-PCT-2026",
        sourceId="kit-2026-budget-summary",
        page=4,
        label="2026 property tax rate increase (city)",
        amountCad=CITY_TAX_INCREASE_PCT,
        unit="percent",
        excerpt="Property Taxes 2.20% $29 Assessment of $326,000",
        status="approved",
    ),
    fact(
        id="KIT-TAX-INCREASE-CAD-2026",
        sourceId="kit-2026-budget-summary",
        page=4,
        label="2026 average-home city tax increase dollars",
        amountCad=CITY_TAX_INCREASE_CAD,
        excerpt="Property Taxes 2.20% $29 Assessment of $326,000",
        status="approved",
    ),
    fact(
        id="KIT-TAXRATE-RES-CITY-2026",
        sourceId="kit-2026-tax-rates",
        page=1,
        label="RT Residential City tax rate 2026",
        amountCad=RATE_CITY,
        unit="rate",
        excerpt=(
            "Residential R T Residential / Farm Taxable: Full "
            "0.00411164 0.00841834 0.00153000 0.01405998"
        ),
        status="final",
    ),
    fact(
        id="KIT-TAXRATE-RES-REGION-2026",
        sourceId="kit-2026-tax-rates",
        page=1,
        label="RT Residential Region tax rate 2026 (as printed on City rates sheet)",
        amountCad=RATE_REGION,
        unit="rate",
        excerpt=(
            "Residential R T Residential / Farm Taxable: Full "
            "0.00411164 0.00841834 0.00153000 0.01405998"
        ),
        status="final",
    ),
    fact(
        id="KIT-TAXRATE-RES-EDUCATION-2026",
        sourceId="kit-2026-tax-rates",
        page=1,
        label="RT Residential Education tax rate 2026",
        amountCad=RATE_EDUCATION,
        unit="rate",
        excerpt=(
            "Residential R T Residential / Farm Taxable: Full "
            "0.00411164 0.00841834 0.00153000 0.01405998"
        ),
        status="final",
    ),
    fact(
        id="KIT-TAXRATE-RES-TOTAL-2026",
        sourceId="kit-2026-tax-rates",
        page=1,
        label="RT Residential total tax rate 2026",
        amountCad=RATE_TOTAL,
        unit="rate",
        excerpt=(
            "Residential R T Residential / Farm Taxable: Full "
            "0.00411164 0.00841834 0.00153000 0.01405998"
        ),
        status="final",
    ),
    fact(
        id="KIT-NET-DEPT-EXP-2026",
        sourceId="kit-2026-appendix-b",
        page=3,
        label="Net departmental expenditures 2026 (allocation base)",
        amountCad=ALLOC_BASE,
        excerpt=(
            "NET DEPARTMENTAL EXPENDITURES 159,337,333    162,901,333        "
            "170,039,303    10,701,970        6.72%"
        ),
        status="approved",
    ),
    fact(
        id="KIT-FIRE-2026",
        sourceId="kit-2026-appendix-b",
        page=2,
        label="Fire division net expenditure 2026 (inside Community Services)",
        amountCad=FIRE_2026,
        excerpt="FIRE 43,031,547      42,862,547          44,407,986      1,376,439           3.20%",
        status="approved",
    ),
]

DEPT_EXCERPTS = {
    "KIT-DEPT-CAO-2026": (
        "CHIEF ADMINISTRATOR'S OFFICE TOTAL 1,356,709        1,364,709            "
        "1,443,066        86,357                6.37%"
    ),
    "KIT-DEPT-CSD-2026": (
        "COMMUNITY SERVICES DEPT TOTAL 63,211,539      63,660,539          "
        "66,995,305      3,783,766          5.99%"
    ),
    "KIT-DEPT-FIN-2026": (
        "FINANCIAL SERVICES DEPT TOTAL 4,950,985        4,876,985            "
        "5,390,745        439,760              8.88%"
    ),
    "KIT-DEPT-COR-2026": (
        "CORPORATE SERVICES DEPT TOTAL 18,732,881      18,874,881          "
        "19,607,218      874,337              4.67%"
    ),
    "KIT-DEPT-DSD-2026": (
        "DEVELOPMENT SERVICES DEPT TOTAL 16,140,126      17,681,126          "
        "17,106,029      965,903              5.98%"
    ),
    "KIT-DEPT-INS-2026": (
        "INFRASTRUCTURE SERVICES DEPARTMENT TOTAL 54,945,093      56,443,093          "
        "59,496,940      4,551,847          8.28%"
    ),
}

for fact_id, label, amount, page in DEPTS:
    facts.append(
        fact(
            id=fact_id,
            sourceId="kit-2026-appendix-b",
            page=page,
            label=f"{label} — 2026 department total",
            amountCad=amount,
            excerpt=DEPT_EXCERPTS[fact_id],
            status="approved",
        )
    )

# Region urban household schedule FACTS (informational @ $354,500 — not the $326k bill)
facts.append(
    fact(
        id="ROW-URBAN-HH-TOTAL-2026",
        sourceId="row-2026-book",
        page=REGION_HH_PAGE,
        label="Tax-supported regional services cost per average urban household",
        amountCad=REGION_URBAN_AFTER_PIL,
        excerpt=(
            f"Urban ... Regional Tax Levy ... ${REGION_URBAN_AFTER_PIL:,} ... "
            f"Based on an average residential property valued at ${REGION_HH_ASSESSMENT:,}"
        ),
        status="approved",
        assessmentBasisCad=REGION_HH_ASSESSMENT,
        note=(
            f"Imported from shared region-of-waterloo-on schedule. "
            f"Do not add to the City rate×${AVG_ASSESSMENT:,} Region portion "
            f"(DRV-KIT-BILL-REGION-326K = ${REGION_PORTION:,.2f})."
        ),
    )
)
facts.append(
    fact(
        id="ROW-HH-PIL-2026",
        sourceId="row-2026-book",
        page=REGION_HH_PAGE,
        label="Payments in Lieu & Supplementary Taxes (household share)",
        amountCad=_urban["pilAndSupplementaryCad"],
        excerpt="Less: Payments in Lieu & Supplementary Taxes(3) ($78)",
        status="approved",
    )
)
for line in _urban["lines"]:
    facts.append(
        fact(
            id=line["id"],
            sourceId="row-2026-book",
            page=REGION_HH_PAGE,
            label=f"Urban household — {line['label']}",
            amountCad=line["amountCad"],
            regionalNetExpenditure000s=line["netExpenditure000Cad"],
            regionalPropertyTaxLevy000s=line["propertyTaxLevy000Cad"],
            excerpt=f"{line['label']} ... Urban ${line['amountCad']}",
            status="approved",
            assessmentBasisCad=REGION_HH_ASSESSMENT,
        )
    )

derived_rows = [
    derived(
        id="DRV-KIT-ALLOCATION-BASE-2026",
        label="Department net-expenditure allocation base",
        amountCad=ALLOC_BASE,
        formula="sum(department totals) == KIT-NET-DEPT-EXP-2026",
        inputs=[d[0] for d in DEPTS] + ["KIT-NET-DEPT-EXP-2026"],
        note=(
            "Pro-rata uses Appendix B net departmental expenditures. "
            "Published net tax levy (KIT-LEVY-2026) differs — see GAP-KIT-LEVY-VS-DEPTS."
        ),
    ),
    derived(
        id="DRV-KIT-BILL-CITY-326K",
        label="City portion at average assessment",
        amountCad=CITY_PORTION,
        formula="KIT-AVG-ASSESSMENT-2026 * KIT-TAXRATE-RES-CITY-2026",
        inputs=["KIT-AVG-ASSESSMENT-2026", "KIT-TAXRATE-RES-CITY-2026"],
    ),
    derived(
        id="DRV-KIT-BILL-REGION-326K",
        label="Region portion at average assessment",
        amountCad=REGION_PORTION,
        formula="KIT-AVG-ASSESSMENT-2026 * KIT-TAXRATE-RES-REGION-2026",
        inputs=["KIT-AVG-ASSESSMENT-2026", "KIT-TAXRATE-RES-REGION-2026"],
    ),
    derived(
        id="DRV-KIT-BILL-EDUCATION-326K",
        label="Education portion at average assessment",
        amountCad=EDUCATION_PORTION,
        formula="KIT-AVG-ASSESSMENT-2026 * KIT-TAXRATE-RES-EDUCATION-2026",
        inputs=["KIT-AVG-ASSESSMENT-2026", "KIT-TAXRATE-RES-EDUCATION-2026"],
    ),
    derived(
        id="DRV-KIT-BILL-COMBINED-326K",
        label="Combined RT bill at average assessment",
        amountCad=COMBINED_TOTAL,
        formula="city + region + education",
        inputs=[
            "DRV-KIT-BILL-CITY-326K",
            "DRV-KIT-BILL-REGION-326K",
            "DRV-KIT-BILL-EDUCATION-326K",
            "KIT-TAXRATE-RES-TOTAL-2026",
        ],
    ),
]

city_lines = []
for fact_id, label, amount, _page in DEPTS:
    share = amount / ALLOC_BASE
    line_amt = round(CITY_PORTION * share, 2)
    derived_id = f"DRV-{fact_id}-HH"
    derived_rows.append(
        derived(
            id=derived_id,
            label=f"Household share — {label}",
            amountCad=line_amt,
            formula=f"DRV-KIT-BILL-CITY-326K * ({fact_id} / DRV-KIT-ALLOCATION-BASE-2026)",
            inputs=["DRV-KIT-BILL-CITY-326K", fact_id, "DRV-KIT-ALLOCATION-BASE-2026"],
        )
    )
    city_lines.append(
        {
            "id": fact_id,
            "label": label,
            "amountCad": line_amt,
            "classification": "city_levy_allocated",
            "evidenceStatus": "DERIVED",
            "sourceFactId": derived_id,
            "note": (
                f"Pro-rata of Appendix B net departmental expenditures (${ALLOC_BASE:,}) "
                f"against city tax ${CITY_PORTION:,.2f}"
            ),
        }
    )

lines_sum = sum(x["amountCad"] for x in city_lines)
residual = round(CITY_PORTION - lines_sum, 2)
if residual != 0:
    city_lines.append(
        {
            "id": "KIT-ALLOC-ROUNDING",
            "label": "Allocation rounding",
            "amountCad": residual,
            "classification": "reconciling_item",
            "evidenceStatus": "RECONCILING",
            "note": "Cent rounding so department shares sum to the city portion.",
        }
    )

# Fire disclosure inside Community Services
for line in city_lines:
    if line["id"] == "KIT-DEPT-CSD-2026":
        fire_share = round(CITY_PORTION * (FIRE_2026 / ALLOC_BASE), 2)
        derived_rows.append(
            derived(
                id="DRV-KIT-FIRE-SUBLINE",
                label="of which Fire (inside Community Services)",
                amountCad=fire_share,
                formula="DRV-KIT-BILL-CITY-326K * (KIT-FIRE-2026 / DRV-KIT-ALLOCATION-BASE-2026)",
                inputs=["DRV-KIT-BILL-CITY-326K", "KIT-FIRE-2026", "DRV-KIT-ALLOCATION-BASE-2026"],
            )
        )
        line["subLines"] = [
            {
                "id": "KIT-FIRE-SUBLINE",
                "label": "of which Fire",
                "amountCad": fire_share,
                "classification": "disclosure_subline",
                "evidenceStatus": "DERIVED",
                "sourceFactId": "DRV-KIT-FIRE-SUBLINE",
                "note": "Already included in Community Services above; not added to any total.",
            }
        ]

region_lines = [
    {
        "id": "KIT-REGION-RATE-PORTION",
        "label": "Region of Waterloo (combined — rate × City average assessment)",
        "amountCad": REGION_PORTION,
        "classification": "region_tax_supported",
        "evidenceStatus": "DERIVED",
        "sourceFactId": "DRV-KIT-BILL-REGION-326K",
        "note": (
            f"Printed REGION rate on the City's 2026 Final Tax Rates sheet × ${AVG_ASSESSMENT:,}. "
            f"This is the bill-stack Region total. Region-published urban service lines at "
            f"${REGION_HH_ASSESSMENT:,} are under regionIllustrationAt354500 — not added here."
        ),
    }
]

# Informational illustration only — sums to published urban after-PIL, NOT to REGION_PORTION.
region_illustration_lines = [
    {
        "id": line["id"],
        "label": line["label"],
        "amountCad": line["amountCad"],
        "classification": "region_schedule_illustration",
        "evidenceStatus": "FACT",
        "sourceFactId": line["id"],
        "note": f"Region-published at ${REGION_HH_ASSESSMENT:,}; not part of the ${AVG_ASSESSMENT:,} bill.",
    }
    for line in _urban["lines"]
]
if _urban["roundingAdjustmentCad"]:
    region_illustration_lines.append(
        {
            "id": "ROW-HH-URBAN-ROUNDING",
            "label": "Unallocated table-rounding difference (source total vs summed lines)",
            "amountCad": _urban["roundingAdjustmentCad"],
            "classification": "reconciling_item",
            "evidenceStatus": "RECONCILING",
            "note": (
                f"Printed lines sum ${_urban['servicesSubtotalCad']:,}; "
                f"printed subtotal ${_urban['publishedServicesSubtotalCad']:,}."
            ),
        }
    )
region_illustration_lines.append(
    {
        "id": "ROW-HH-PIL-OFFSET",
        "label": "Less: Payments in Lieu & Supplementary Taxes (household share)",
        "amountCad": _urban["pilAndSupplementaryCad"],
        "classification": "region_schedule_illustration",
        "evidenceStatus": "FACT",
        "sourceFactId": "ROW-HH-PIL-2026",
    }
)

gaps = [
    gap(
        id="GAP-KIT-LEVY-VS-DEPTS",
        title="Published net tax levy differs from net departmental expenditures",
        detail=(
            f"Budget Summary prints net tax levy ${LEVY_2026:,}. Appendix B net departmental "
            f"expenditures sum to ${ALLOC_BASE:,} (delta ${LEVY_2026 - ALLOC_BASE:,}). "
            "General expenses and general revenues sit outside the department table. "
            "Household department shares use the Appendix B department base, not the levy headline."
        ),
        blocks=[],
        neededEvidence=["One-page reconciliation from levy headline to department totals"],
    ),
    gap(
        id="GAP-KIT-REGION-ASSESSMENT-BRIDGE",
        title="No DERIVED bridge from Region $354,500 urban schedule to City $326,000 rate bill",
        detail=(
            f"City bill uses REGION rate × ${AVG_ASSESSMENT:,} = ${REGION_PORTION:,.2f} "
            f"(DRV-KIT-BILL-REGION-326K). Region urban household schedule totals "
            f"${REGION_URBAN_AFTER_PIL:,} at ${REGION_HH_ASSESSMENT:,}. These are the same "
            "MPAC January 1, 2016 base but different average properties — not algebraically "
            "reconciled here. Schedule lines are informational only until an explicit "
            "rate×assessment DERIVED path is approved."
        ),
        blocks=[],
        neededEvidence=[
            "Approved formula mapping Region urban HH lines onto the City average assessment bill"
        ],
    ),
    gap(
        id="GAP-KIT-FIR-CODE-VERIFY",
        title="FIR / MAH assessment code not yet locked from Schedule 02",
        detail=(
            "Pack uses working code 3012 pending a hand-checked FIR Schedule 02 row for "
            "City of Kitchener. Do not treat as sealed identity."
        ),
        blocks=[],
        neededEvidence=["FIR Schedule 02 MAH code for City of Kitchener"],
    ),
    gap(
        id="GAP-KIT-PEER-FIR-FAIRNESS",
        title="Peer per-capita fairness check not yet run for Kitchener",
        detail="Tier 0 draft: no peer FIR findings published.",
        blocks=["findings_peer_fairness"],
        neededEvidence=["Hand-checked FIR Schedule 40 peer cohort"],
    ),
]

closed_gaps = [
    {
        "id": "GAP-KIT-REGION-SCHEDULE",
        "title": "Region of Waterloo urban household schedule imported from shared pack",
        "resolvedAt": "2026-07-25",
        "resolution": (
            "Urban column imported from corpus/region-of-waterloo-on/schedules/"
            "household-tax-supported-2026.yaml (parsed from Region Budget Book p.12). "
            f"Lines appear under regionIllustrationAt354500 at ${REGION_HH_ASSESSMENT:,}. "
            f"Bill-stack Region total remains rate × ${AVG_ASSESSMENT:,} "
            f"(${REGION_PORTION:,.2f}). Narrowed remainder: GAP-KIT-REGION-ASSESSMENT-BRIDGE."
        ),
    }
]

findings: list[dict] = []

SHARE_CITY = RATE_CITY / RATE_TOTAL
SHARE_REG = RATE_REGION / RATE_TOTAL
SHARE_EDU = RATE_EDUCATION / RATE_TOTAL
IMPLIED_5000 = round(5000 / RATE_TOTAL)

ledger = {
    "schemaVersion": "2.0.0",
    "artifact": "EvidenceLedger",
    "jurisdiction": {
        "slug": "kitchener-on",
        "name": "City of Kitchener",
        "aliases": ["Kitchener", "Kitchener ON"],
        "level": "lower-tier",
        "upperTier": ["region-of-waterloo-on"],
        "assessmentCode": "3012",
        "note": "Lower-tier in Region of Waterloo. Assessment code pending Schedule 02 lock.",
    },
    "evidencePolicy": {
        "rules": [
            "FACT requires a published source, page, and excerpt or numeric binding.",
            "DERIVED requires an explicit formula over FACT/DERIVED ids only.",
            "Never invent bill dollars to fill a GAP.",
            "JUDGMENT billImpactCad is always null until a formula is approved.",
            "Do not copy another municipality's Region household table into this pack.",
        ]
    },
    "sources": sources,
    "facts": facts,
    "derived": derived_rows,
    "gaps": gaps,
    "closedGaps": closed_gaps,
}

receipt = {
    "schemaVersion": "2.0.0",
    "artifact": "TaxpayerReceipt",
    "status": "partial_evidence_based",
    "purpose": (
        "City of Kitchener 2026 taxpayer receipt. Lower-tier: City + Region of Waterloo + education."
    ),
    "evidencePolicyRef": "data/kitchener/evidence-ledger.json",
    "jurisdiction": {
        "slug": "kitchener-on",
        "displayName": "City of Kitchener",
        "level": "lower-tier",
        "aliases": ["Kitchener"],
    },
    "profiles": {
        "supportedAverageHousehold": {
            "description": "City-published average residential assessment ($326,000).",
            "township": {
                "basis": (
                    "City of Kitchener 2026 Appendix B department totals allocated at average "
                    "assessment — CITY portion only (Region and education separate)"
                ),
                "amountCad": CITY_PORTION,
                "assessmentCad": AVG_ASSESSMENT,
                "evidenceStatus": "DERIVED",
                "sourceFactId": "DRV-KIT-BILL-CITY-326K",
                "lineItems": city_lines,
                "uiLabel": "City portion",
                "note": (
                    f"City rate × $326,000 = ${CITY_PORTION:,.2f}. "
                    f"Published 2.2% / ${CITY_TAX_INCREASE_CAD} city increase is city-only "
                    "(not the combined bill)."
                ),
            },
            "region": {
                "basis": (
                    "City of Kitchener 2026 Final Tax Rates — REGION column on RT Residential "
                    f"at ${AVG_ASSESSMENT:,}"
                ),
                "amountCad": REGION_PORTION,
                "assessmentCad": AVG_ASSESSMENT,
                "evidenceStatus": "DERIVED",
                "sourceFactId": "DRV-KIT-BILL-REGION-326K",
                "lineItems": region_lines,
                "uiLabel": "Region portion",
                "note": (
                    f"Bill total is rate × ${AVG_ASSESSMENT:,} = ${REGION_PORTION:,.2f}. "
                    f"Region-published urban service breakdown at ${REGION_HH_ASSESSMENT:,} "
                    f"(${REGION_URBAN_AFTER_PIL:,} after PIL) is under regionIllustrationAt354500."
                ),
            },
            "regionIllustrationAt354500": {
                "description": (
                    f"Region-published urban (Kitchener / Waterloo / Cambridge) tax-supported "
                    f"services at ${REGION_HH_ASSESSMENT:,} — INFORMATIONAL only."
                ),
                "basis": (
                    f"Region 2026 Budget Book p.{REGION_HH_PAGE} Urban column "
                    f"(shared pack schedule) at ${REGION_HH_ASSESSMENT:,}"
                ),
                "amountCad": REGION_URBAN_AFTER_PIL,
                "assessmentCad": REGION_HH_ASSESSMENT,
                "evidenceStatus": "FACT",
                "sourceFactId": "ROW-URBAN-HH-TOTAL-2026",
                "uiLabel": "Region illustration @ $354,500",
                "lineItems": region_illustration_lines,
                "lineItemsSumCheckCad": sum(x["amountCad"] for x in region_illustration_lines),
                "note": (
                    f"Do not add these dollars to the City ${AVG_ASSESSMENT:,} bill. "
                    "Same MPAC January 1, 2016 base; different average property. "
                    "See GAP-KIT-REGION-ASSESSMENT-BRIDGE."
                ),
                "gapId": "GAP-KIT-REGION-ASSESSMENT-BRIDGE",
            },
            "education": {
                "basis": "2026 Final Tax Rates — RT Residential Education Rate 0.00153000 at $326,000",
                "amountCad": EDUCATION_PORTION,
                "assessmentCad": AVG_ASSESSMENT,
                "evidenceStatus": "DERIVED",
                "sourceFactId": "DRV-KIT-BILL-EDUCATION-326K",
                "note": "Province sets this rate; the City collects it.",
                "uiLabel": "Education",
            },
            "combinedTotalCad": COMBINED_TOTAL,
            "combinedAtAssessment": {
                "assessmentCad": AVG_ASSESSMENT,
                "basis": "City of Kitchener 2026 Final Tax Rates — RT Residential / Farm Taxable: Full",
                "evidenceStatus": "DERIVED",
                "components": [
                    {
                        "label": "City of Kitchener",
                        "amountCad": CITY_PORTION,
                        "rate": RATE_CITY,
                        "sourceFactId": "KIT-TAXRATE-RES-CITY-2026",
                    },
                    {
                        "label": "Region of Waterloo",
                        "amountCad": REGION_PORTION,
                        "rate": RATE_REGION,
                        "sourceFactId": "KIT-TAXRATE-RES-REGION-2026",
                    },
                    {
                        "label": "Education (Province of Ontario)",
                        "amountCad": EDUCATION_PORTION,
                        "rate": RATE_EDUCATION,
                        "sourceFactId": "KIT-TAXRATE-RES-EDUCATION-2026",
                    },
                ],
                "totalCad": COMBINED_TOTAL,
                "totalRate": RATE_TOTAL,
            },
            "combinedTotalNote": (
                f"Built from the 2026 Final Tax Rates RT row applied to the City's published "
                f"average assessment (${AVG_ASSESSMENT:,}). City ${CITY_PORTION:,.2f} + "
                f"Region ${REGION_PORTION:,.2f} + Education ${EDUCATION_PORTION:,.2f} = "
                f"${COMBINED_TOTAL:,.2f}. The City's published ${CITY_TAX_INCREASE_CAD} / "
                f"{CITY_TAX_INCREASE_PCT}% increase is the City portion only."
            ),
            "warnings": [
                "City $29 / 2.2% impact is City portion only — not the full combined bill change.",
                "Department shares are a pro-rata model over Appendix B net departmental expenditures — not a published per-household split.",
                (
                    f"Region bill line is rate × ${AVG_ASSESSMENT:,}; Region urban schedule at "
                    f"${REGION_HH_ASSESSMENT:,} is informational only "
                    "(GAP-KIT-REGION-ASSESSMENT-BRIDGE)."
                ),
                "Utilities (water / sanitary / storm) are billed separately and are not part of this property-tax receipt.",
            ],
        },
        "hypothetical5000": {
            "amountCad": 5000,
            "evidenceStatus": "DERIVED",
            "allocatable": True,
            "impliedAssessmentCad": IMPLIED_5000,
            "compositionShares": [
                {
                    "label": "City of Kitchener",
                    "share": SHARE_CITY,
                    "sourceFactId": "KIT-TAXRATE-RES-CITY-2026",
                },
                {
                    "label": "Region of Waterloo",
                    "share": SHARE_REG,
                    "sourceFactId": "KIT-TAXRATE-RES-REGION-2026",
                },
                {
                    "label": "Education (Province of Ontario)",
                    "share": SHARE_EDU,
                    "sourceFactId": "KIT-TAXRATE-RES-EDUCATION-2026",
                },
            ],
            "message": (
                f"A $5,000 total bill implies an assessment of about ${IMPLIED_5000:,}. "
                "Shown as rate shares rather than invented department dollars."
            ),
        },
    },
    "findings": findings,
    "uiModelHints": {
        "municipalBucketLabel": "City portion",
        "regionBucketLabel": "Region portion",
        "heroLabel": "Total residential bill · average · 2026 final tax rates",
        "publishedFindingIds": [],
        "marqueeFindings": [],
    },
}

for path in (DATA, WEB_DATA):
    (path / "evidence-ledger.json").write_text(
        json.dumps(ledger, indent=2) + "\n", encoding="utf-8"
    )
    (path / "taxpayer-receipt.json").write_text(
        json.dumps(receipt, indent=2) + "\n", encoding="utf-8"
    )
    print(f"wrote {path}")

print(
    f"City ${CITY_PORTION} + Region ${REGION_PORTION} + Edu ${EDUCATION_PORTION} "
    f"= ${COMBINED_TOTAL} @ ${AVG_ASSESSMENT:,}"
)
