"""Build County of Brant (Paris, ON) evidence ledger + taxpayer receipt.

Paris is not a separate lower-tier municipality — property tax for Paris is
County of Brant (single-tier, MMAH assessment code 2920).

Rules (same grammar as North Dumfries):
- FACT: quoted from source with page + amount
- DERIVED: computed only from FACT ids with explicit formula
- GAP: missing evidence — never invent amounts
- JUDGMENT: interpretive; billImpactCad always null
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "brant"
WEB_DATA = ROOT / "web" / "src" / "data" / "brant"
DATA.mkdir(parents=True, exist_ok=True)
WEB_DATA.mkdir(parents=True, exist_ok=True)


def fact(**kwargs):
    kwargs.setdefault("kind", "FACT")
    return kwargs


def gap(**kwargs):
    kwargs.setdefault("kind", "GAP")
    return kwargs


def derived(**kwargs):
    kwargs.setdefault("kind", "DERIVED")
    return kwargs


# --- Control totals from 2026 Approved Budget Operating Forecast p.1 / p.5 ---
LEVY_2026 = 92_457_575
LEVY_2025 = 85_371_329
MEDIAN_ASSESSMENT = 391_000
ILLUSTRATED_COUNTY_BILL = 4_295.35  # municipal + hospital special; excludes education

# RT Residential from 2026 Tax Rates PDF (single page)
RATE_MUNICIPAL = 0.0107859
RATE_HOSPITAL = 0.0001996
RATE_EDUCATION = 0.0015300
RATE_TOTAL = 0.0125155  # printed Total column

# Department net levy requirements — Approved Budget department summary pp.2–5
# These sum exactly to LEVY_2026.
DEPTS = [
    ("BRANT-DEPT-MAYOR-COUNCIL-2026", "Mayor and Council", 831_756, 2),
    ("BRANT-DEPT-CAO-2026", "Office of the CAO", 371_386, 2),
    ("BRANT-DEPT-CORPORATE-2026", "Corporate Services", 9_888_051, 2),
    ("BRANT-DEPT-TAXATION-CORP-FIN-2026", "Taxation & Corporate Finances", -4_255_210, 3),
    ("BRANT-DEPT-CAPITAL-FINANCING-2026", "Capital Financing", 18_654_825, 3),
    ("BRANT-DEPT-DEVELOPMENT-2026", "Development Services", 1_914_300, 3),
    ("BRANT-DEPT-STRATEGIC-2026", "Strategic Initiatives", 4_593_918, 3),
    ("BRANT-DEPT-OPERATIONS-2026", "Operations", 20_718_721, 4),
    ("BRANT-DEPT-COMMUNITY-2026", "Community Services", 10_441_749, 4),
    ("BRANT-DEPT-EPS-2026", "Emergency & Protective Services", 9_497_822, 5),
    ("BRANT-DEPT-EXTERNAL-2026", "External Agencies", 19_800_257, 5),
]

assert sum(d[2] for d in DEPTS) == LEVY_2026

MUNICIPAL_PORTION = round(MEDIAN_ASSESSMENT * RATE_MUNICIPAL, 2)
HOSPITAL_PORTION = round(MEDIAN_ASSESSMENT * RATE_HOSPITAL, 2)
EDUCATION_PORTION = round(MEDIAN_ASSESSMENT * RATE_EDUCATION, 2)
COUNTY_PLUS_HOSPITAL = round(MUNICIPAL_PORTION + HOSPITAL_PORTION, 2)
COMBINED_TOTAL = round(MUNICIPAL_PORTION + HOSPITAL_PORTION + EDUCATION_PORTION, 2)
# County prints $4,295.35; rate×assessment rounds to $4,295.33 (2¢). Prefer rates.
ILLUSTRATION_DELTA = round(ILLUSTRATED_COUNTY_BILL - COUNTY_PLUS_HOSPITAL, 2)
assert ILLUSTRATION_DELTA == 0.02

sources = [
    {
        "id": "brant-2026-approved-budget",
        "title": "County of Brant 2026 Approved Budget — Operating Forecast (Accessible)",
        "url": "https://www.brant.ca/media/0dpbiteo/2026-approved-budget-accessible.pdf",
        "localPath": "source-pdfs/brant/2026-approved-budget-accessible.pdf",
        "extractedText": "data/_extracts/brant/2026-approved-budget-accessible.txt",
        "asOf": "2026-02",
        "authority": "County of Brant",
        "note": "Adopted operating forecast; net levy and department summary.",
    },
    {
        "id": "brant-2026-budget-overview",
        "title": "County of Brant 2026 Budget Overview (Accessible)",
        "url": "https://www.brant.ca/media/njpawe0j/1-budget-overview-accessible.pdf",
        "localPath": "source-pdfs/brant/1-budget-overview-accessible.pdf",
        "extractedText": "data/_extracts/brant/1-budget-overview-accessible.txt",
        "asOf": "2026-02",
        "authority": "County of Brant",
        "note": "Proposed/overview narrative; levy drivers and median home illustration.",
    },
    {
        "id": "brant-2026-tax-rates",
        "title": "County of Brant 2026 Tax Rates",
        "url": "https://www.brant.ca/media/wgootdma/2026-tax-rates.pdf",
        "localPath": "source-pdfs/brant/2026-tax-rates.pdf",
        "extractedText": "data/_extracts/brant/2026-tax-rates.txt",
        "asOf": "2026",
        "authority": "County of Brant",
        "note": "Municipal, hospital special levy, and education rates by tax class.",
    },
]

facts = [
    fact(
        id="BRANT-LEVY-2026",
        sourceId="brant-2026-approved-budget",
        page=1,
        label="County of Brant 2026 approved net levy",
        amountCad=LEVY_2026,
        excerpt="NET LEVY $85,371,329 $92,457,575 $101,524,129 $110,139,523 $115,787,940",
        status="approved",
    ),
    fact(
        id="BRANT-LEVY-2025",
        sourceId="brant-2026-approved-budget",
        page=1,
        label="County of Brant 2025 reorganized net levy (comparator)",
        amountCad=LEVY_2025,
        excerpt="NET LEVY $85,371,329 $92,457,575 $101,524,129 $110,139,523 $115,787,940",
        status="approved_prior_year",
    ),
    fact(
        id="BRANT-MEDIAN-ASSESSMENT-2026",
        sourceId="brant-2026-approved-budget",
        page=1,
        label="2026 median residential assessment used in County tax illustration",
        amountCad=MEDIAN_ASSESSMENT,
        excerpt="Residential Home $4,089.07 $4,295.35 $4,521.72 $4,816.39 $4,972.40 assessed at $391,000 (2026 median)",
        status="approved",
    ),
    fact(
        id="BRANT-ILLUSTRATED-COUNTY-BILL-2026",
        sourceId="brant-2026-approved-budget",
        page=1,
        label="2026 illustrated residential county tax at median assessment (excludes education)",
        amountCad=ILLUSTRATED_COUNTY_BILL,
        excerpt="Residential Home $4,089.07 $4,295.35 $4,521.72 $4,816.39 $4,972.40 assessed at $391,000 (2026 median)",
        status="approved",
        note="Equals Municipal Tax Rate + Special Levy Hospital Funding Rate × $391,000. Education is billed separately.",
    ),
    fact(
        id="BRANT-TAXRATE-RES-MUNICIPAL-2026",
        sourceId="brant-2026-tax-rates",
        page=1,
        label="2026 RT Residential municipal tax rate",
        value=RATE_MUNICIPAL,
        excerpt="RT Residential 0.0107859 0.0001996 0.0015300 0.0125155",
        status="final",
    ),
    fact(
        id="BRANT-TAXRATE-RES-HOSPITAL-2026",
        sourceId="brant-2026-tax-rates",
        page=1,
        label="2026 RT Residential hospital special levy rate",
        value=RATE_HOSPITAL,
        excerpt="RT Residential 0.0107859 0.0001996 0.0015300 0.0125155",
        status="final",
    ),
    fact(
        id="BRANT-TAXRATE-RES-EDUCATION-2026",
        sourceId="brant-2026-tax-rates",
        page=1,
        label="2026 RT Residential education tax rate",
        value=RATE_EDUCATION,
        excerpt="RT Residential 0.0107859 0.0001996 0.0015300 0.0125155",
        status="final",
    ),
    fact(
        id="BRANT-TAXRATE-RES-TOTAL-2026",
        sourceId="brant-2026-tax-rates",
        page=1,
        label="2026 RT Residential total tax rate",
        value=RATE_TOTAL,
        excerpt="RT Residential 0.0107859 0.0001996 0.0015300 0.0125155",
        status="final",
    ),
    fact(
        id="BRANT-LEGAL-SERVICES-2026",
        sourceId="brant-2026-approved-budget",
        page=2,
        label="Legal Services net levy requirement 2026",
        amountCad=1_181_990,
        excerpt="Legal Services 1,085,551 1,181,990 1,235,620 1,281,457 1,336,006",
        status="approved",
        note="Already included inside Corporate Services total; surfaced for transparency.",
    ),
    fact(
        id="BRANT-OPP-2026",
        sourceId="brant-2026-approved-budget",
        page=5,
        label="OPP (External Agencies) net levy requirement 2026",
        amountCad=6_918_936,
        excerpt="OPP 6,240,609 6,918,936 7,602,629 8,361,947 9,176,681",
        status="approved",
        note="Single-tier: policing appears on the County levy, not a separate Region column.",
    ),
]

# Department FACT rows — excerpts must co-occur with amounts on cited pages
for fact_id, label, amount, page in DEPTS:
    # Use Total row wording where present
    if label == "Mayor and Council":
        excerpt = "Total  Mayor and Council 784,005 831,756 851,225 857,115 878,591"
    elif label == "Office of the CAO":
        excerpt = "Total  Office of the CAO 335,862 371,386 387,464 405,932 425,361"
    elif label == "Corporate Services":
        excerpt = "Total  Corporate Services 9,158,981 9,888,051 10,393,442 10,858,769 11,353,939"
    elif label == "Taxation & Corporate Finances":
        excerpt = "Total  Taxation & Corporate Finances (4,786,602)      (4,255,210) (1,291,074)       1,372,533 2,403,799"
    elif label == "Capital Financing":
        excerpt = "Total  Capital Financing 17,157,663 18,654,825 21,233,332 23,555,543 24,352,606"
    elif label == "Development Services":
        excerpt = "Total  Development Services 1,561,325 1,914,300 2,114,846 2,213,858 2,334,160"
    elif label == "Strategic Initiatives":
        excerpt = "Total  Strategic Initiatives 4,463,800 4,593,918 4,727,218 4,813,293 4,978,118"
    elif label == "Operations":
        excerpt = "Total  Operations 19,927,005 20,718,721 21,093,413 21,501,332 21,985,300"
    elif label == "Community Services":
        excerpt = "Total  Community Services 9,814,091 10,441,749 10,666,648 11,049,942 11,442,869"
    elif label == "Emergency & Protective Services":
        excerpt = "Total  Emergency & Protective Services 8,741,506 9,497,822 10,207,277 10,951,982 11,602,000"
    elif label == "External Agencies":
        excerpt = "Total  External Agencies 18,213,693 19,800,257 21,140,338 22,559,224 24,031,197"
    else:
        excerpt = f"{label} {amount}"
    facts.append(
        fact(
            id=fact_id,
            sourceId="brant-2026-approved-budget",
            page=page,
            label=f"{label} net levy requirement 2026",
            amountCad=amount,
            excerpt=excerpt,
            status="approved",
        )
    )

derived_rows = [
    derived(
        id="DRV-BRANT-ALLOCATION-BASE-2026",
        label="Department net-levy allocation base (sums to approved net levy)",
        amountCad=LEVY_2026,
        formula="sum(department net levy requirements) == BRANT-LEVY-2026",
        inputs=[d[0] for d in DEPTS] + ["BRANT-LEVY-2026"],
        note="Single-tier control total: department summary totals already equal the net levy.",
    ),
    derived(
        id="DRV-BRANT-BILL-MUNICIPAL-391K",
        label="Municipal portion at median assessment",
        amountCad=MUNICIPAL_PORTION,
        formula="BRANT-MEDIAN-ASSESSMENT-2026 * BRANT-TAXRATE-RES-MUNICIPAL-2026",
        inputs=["BRANT-MEDIAN-ASSESSMENT-2026", "BRANT-TAXRATE-RES-MUNICIPAL-2026"],
    ),
    derived(
        id="DRV-BRANT-BILL-HOSPITAL-391K",
        label="Hospital special levy at median assessment",
        amountCad=HOSPITAL_PORTION,
        formula="BRANT-MEDIAN-ASSESSMENT-2026 * BRANT-TAXRATE-RES-HOSPITAL-2026",
        inputs=["BRANT-MEDIAN-ASSESSMENT-2026", "BRANT-TAXRATE-RES-HOSPITAL-2026"],
    ),
    derived(
        id="DRV-BRANT-BILL-EDUCATION-391K",
        label="Education portion at median assessment",
        amountCad=EDUCATION_PORTION,
        formula="BRANT-MEDIAN-ASSESSMENT-2026 * BRANT-TAXRATE-RES-EDUCATION-2026",
        inputs=["BRANT-MEDIAN-ASSESSMENT-2026", "BRANT-TAXRATE-RES-EDUCATION-2026"],
    ),
    derived(
        id="DRV-BRANT-BILL-COMBINED-391K",
        label="Combined RT bill at median assessment",
        amountCad=COMBINED_TOTAL,
        formula="municipal + hospital special + education",
        inputs=[
            "DRV-BRANT-BILL-MUNICIPAL-391K",
            "DRV-BRANT-BILL-HOSPITAL-391K",
            "DRV-BRANT-BILL-EDUCATION-391K",
            "BRANT-TAXRATE-RES-TOTAL-2026",
        ],
        note="Cross-check: rates sum to printed Total 0.0125155.",
    ),
]

# Pro-rata household shares of the municipal portion only (hospital is separate)
county_lines = []
for fact_id, label, amount, _page in DEPTS:
    share = amount / LEVY_2026
    line_amt = round(MUNICIPAL_PORTION * share, 2)
    derived_id = f"DRV-{fact_id}-HH"
    derived_rows.append(
        derived(
            id=derived_id,
            label=f"Household share — {label}",
            amountCad=line_amt,
            formula=f"DRV-BRANT-BILL-MUNICIPAL-391K * ({fact_id} / DRV-BRANT-ALLOCATION-BASE-2026)",
            inputs=["DRV-BRANT-BILL-MUNICIPAL-391K", fact_id, "DRV-BRANT-ALLOCATION-BASE-2026"],
        )
    )
    county_lines.append(
        {
            "id": fact_id,
            "label": label,
            "amountCad": line_amt,
            "classification": "county_levy_allocated",
            "evidenceStatus": "DERIVED",
            "sourceFactId": derived_id,
            "note": (
                f"Pro-rata of approved net levy base (${LEVY_2026:,}) against "
                f"median municipal tax ${MUNICIPAL_PORTION:,.2f}"
            ),
        }
    )

# Tie-out residual to municipal portion (cent rounding)
lines_sum = sum(x["amountCad"] for x in county_lines)
residual = round(MUNICIPAL_PORTION - lines_sum, 2)
if residual != 0:
    county_lines.append(
        {
            "id": "BRANT-ALLOC-ROUNDING",
            "label": "Allocation rounding",
            "amountCad": residual,
            "classification": "reconciling_item",
            "evidenceStatus": "RECONCILING",
            "note": "Cent rounding so department shares sum to the municipal portion.",
        }
    )

# Surface Legal Services + OPP as disclosure sublines (not additive)
for line in county_lines:
    if line["id"] == "BRANT-DEPT-CORPORATE-2026":
        legal_share = round(MUNICIPAL_PORTION * (1_181_990 / LEVY_2026), 2)
        derived_rows.append(
            derived(
                id="DRV-BRANT-LEGAL-SUBLINE",
                label="of which Legal Services (inside Corporate)",
                amountCad=legal_share,
                formula="DRV-BRANT-BILL-MUNICIPAL-391K * (BRANT-LEGAL-SERVICES-2026 / BRANT-LEVY-2026)",
                inputs=["DRV-BRANT-BILL-MUNICIPAL-391K", "BRANT-LEGAL-SERVICES-2026", "BRANT-LEVY-2026"],
            )
        )
        line["subLines"] = [
            {
                "id": "BRANT-LEGAL-SUBLINE",
                "label": "of which Legal Services",
                "amountCad": legal_share,
                "classification": "disclosure_subline",
                "evidenceStatus": "DERIVED",
                "sourceFactId": "DRV-BRANT-LEGAL-SUBLINE",
                "note": "Already included in Corporate Services above; not added to any total.",
            }
        ]
    if line["id"] == "BRANT-DEPT-EXTERNAL-2026":
        opp_share = round(MUNICIPAL_PORTION * (6_918_936 / LEVY_2026), 2)
        derived_rows.append(
            derived(
                id="DRV-BRANT-OPP-SUBLINE",
                label="of which OPP (inside External Agencies)",
                amountCad=opp_share,
                formula="DRV-BRANT-BILL-MUNICIPAL-391K * (BRANT-OPP-2026 / BRANT-LEVY-2026)",
                inputs=["DRV-BRANT-BILL-MUNICIPAL-391K", "BRANT-OPP-2026", "BRANT-LEVY-2026"],
            )
        )
        line["subLines"] = [
            {
                "id": "BRANT-OPP-SUBLINE",
                "label": "of which OPP",
                "amountCad": opp_share,
                "classification": "disclosure_subline",
                "evidenceStatus": "DERIVED",
                "sourceFactId": "DRV-BRANT-OPP-SUBLINE",
                "note": "Already included in External Agencies above; not added to any total.",
            }
        ]

# Hospital as its own receipt line under county bucket (not in dept pro-rata)
county_lines.append(
    {
        "id": "BRANT-HOSPITAL-SPECIAL-2026",
        "label": "Hospital special levy",
        "amountCad": HOSPITAL_PORTION,
        "classification": "special_levy",
        "evidenceStatus": "DERIVED",
        "sourceFactId": "DRV-BRANT-BILL-HOSPITAL-391K",
        "note": "Special Levy Hospital Funding Rate × median assessment; not part of the department net-levy base.",
    }
)

gaps = [
    gap(
        id="GAP-BRANT-NO-UPPER-TIER",
        title="No separate upper-tier Region column",
        detail=(
            "County of Brant is single-tier. Services that appear under Region of Waterloo for "
            "North Dumfries (police contract, paramedics share, etc.) sit inside the County levy "
            "(External Agencies / Emergency & Protective Services). There is no Region household table to cite."
        ),
        blocks=["region_bucket"],
        neededEvidence=[],
    ),
    gap(
        id="GAP-BRANT-PEER-FIR-FAIRNESS",
        title="Peer per-capita fairness check not yet run for Brant",
        detail=(
            "North Dumfries gold pack includes MMAH FIR Schedule 40 peer benchmarks. "
            "Brant has a fleet FIR stub (code 2920) but this gold receipt has not yet published a "
            "hand-checked peer fairness finding."
        ),
        blocks=["findings_peer_fairness"],
        neededEvidence=["Hand-checked FIR Schedule 40 peer cohort + population basis disclosure"],
    ),
    gap(
        id="GAP-PARIS-ALIAS",
        title="Paris is an alias for County of Brant billing",
        detail=(
            "Searching for 'Paris, Ontario' should resolve to Brant County assessment code 2920. "
            "There is no separate Town of Paris lower-tier tax by-law in this model."
        ),
        blocks=[],
        neededEvidence=[],
    ),
    gap(
        id="GAP-BRANT-ILLUSTRATION-2CENTS",
        title="County illustration is 2¢ above rate × assessment",
        detail=(
            f"Approved budget prints residential impact ${ILLUSTRATED_COUNTY_BILL:,.2f} at $391,000. "
            f"Municipal rate {RATE_MUNICIPAL} + hospital {RATE_HOSPITAL} × $391,000 rounds to "
            f"${COUNTY_PLUS_HOSPITAL:,.2f} (delta ${ILLUSTRATION_DELTA:,.2f}). This receipt uses the "
            "tax-rate arithmetic; the printed illustration remains cited as FACT."
        ),
        blocks=[],
        neededEvidence=["County clarification of rounding on the Property Tax Impact table"],
    ),
]

findings: list[dict] = []  # Tier 0 — findings rare; audit this pack before promoting

SHARE_MUN = RATE_MUNICIPAL / RATE_TOTAL
SHARE_HOSP = RATE_HOSPITAL / RATE_TOTAL
SHARE_EDU = RATE_EDUCATION / RATE_TOTAL
IMPLIED_5000 = round(5000 / RATE_TOTAL)

ledger = {
    "schemaVersion": "2.0.0",
    "artifact": "EvidenceLedger",
    "jurisdiction": {
        "slug": "brant-county-on",
        "name": "County of Brant",
        "aliases": ["Paris, Ontario", "Paris ON"],
        "level": "single-tier",
        "assessmentCode": "2920",
        "note": "Paris residents are billed by County of Brant (single-tier).",
    },
    "evidencePolicy": {
        "rules": [
            "FACT requires a published source, page, and excerpt or numeric binding.",
            "DERIVED requires an explicit formula over FACT/DERIVED ids only.",
            "Never invent bill dollars to fill a GAP.",
            "JUDGMENT billImpactCad is always null until a formula is approved.",
            "Single-tier packs must not fabricate a Region column.",
        ]
    },
    "sources": sources,
    "facts": facts,
    "derived": derived_rows,
    "gaps": gaps,
    "closedGaps": [],
}

receipt = {
    "schemaVersion": "2.0.0",
    "artifact": "TaxpayerReceipt",
    "status": "partial_evidence_based",
    "purpose": (
        "Paris / County of Brant 2026 taxpayer receipt. Single-tier: County municipal + "
        "hospital special levy + education. No Region column."
    ),
    "evidencePolicyRef": "data/brant/evidence-ledger.json",
    "jurisdiction": {
        "slug": "brant-county-on",
        "displayName": "County of Brant (Paris)",
        "level": "single-tier",
        "aliases": ["Paris"],
    },
    "profiles": {
        "supportedAverageHousehold": {
            "description": "County-published median residential assessment ($391,000).",
            "township": {
                "basis": (
                    "County of Brant 2026 approved net levy allocated at median assessment — "
                    "MUNICIPAL PORTION + hospital special levy (education separate)"
                ),
                "amountCad": COUNTY_PLUS_HOSPITAL,
                "assessmentCad": MEDIAN_ASSESSMENT,
                "evidenceStatus": "DERIVED",
                "sourceFactId": "DRV-BRANT-BILL-MUNICIPAL-391K",
                "lineItems": county_lines,
                "uiLabel": "County portion",
                "note": (
                    f"Rate-derived municipal+hospital ${COUNTY_PLUS_HOSPITAL:,.2f}; "
                    f"County illustration prints ${ILLUSTRATED_COUNTY_BILL:,.2f} (see GAP-BRANT-ILLUSTRATION-2CENTS)."
                ),
            },
            "region": {
                "basis": "Not applicable — County of Brant is single-tier (no upper-tier Region)",
                "amountCad": None,
                "evidenceStatus": "GAP",
                "gapId": "GAP-BRANT-NO-UPPER-TIER",
                "lineItems": [],
                "uiLabel": "Upper-tier Region",
                "note": "Policing (OPP), paramedics, and related costs appear inside the County levy lines above.",
            },
            "education": {
                "basis": "2026 Tax Rates — RT Residential Education Rate 0.0015300 at $391,000",
                "amountCad": EDUCATION_PORTION,
                "assessmentCad": MEDIAN_ASSESSMENT,
                "evidenceStatus": "DERIVED",
                "sourceFactId": "DRV-BRANT-BILL-EDUCATION-391K",
                "note": "Province sets this rate; the County collects it.",
                "uiLabel": "Education",
            },
            "combinedTotalCad": COMBINED_TOTAL,
            "combinedAtAssessment": {
                "assessmentCad": MEDIAN_ASSESSMENT,
                "basis": "County of Brant 2026 Tax Rates — CODE RT Residential",
                "evidenceStatus": "DERIVED",
                "components": [
                    {
                        "label": "County of Brant (municipal)",
                        "amountCad": MUNICIPAL_PORTION,
                        "rate": RATE_MUNICIPAL,
                        "sourceFactId": "BRANT-TAXRATE-RES-MUNICIPAL-2026",
                    },
                    {
                        "label": "Hospital special levy",
                        "amountCad": HOSPITAL_PORTION,
                        "rate": RATE_HOSPITAL,
                        "sourceFactId": "BRANT-TAXRATE-RES-HOSPITAL-2026",
                    },
                    {
                        "label": "Education (Province of Ontario)",
                        "amountCad": EDUCATION_PORTION,
                        "rate": RATE_EDUCATION,
                        "sourceFactId": "BRANT-TAXRATE-RES-EDUCATION-2026",
                    },
                ],
                "totalCad": COMBINED_TOTAL,
                "totalRate": RATE_TOTAL,
            },
            "combinedTotalNote": (
                f"Built from the 2026 Tax Rates RT row applied to the County's published median "
                f"assessment (${MEDIAN_ASSESSMENT:,}). Municipal + hospital = ${COUNTY_PLUS_HOSPITAL:,.2f}, "
                f"matching the approved budget's illustrated residential impact ${ILLUSTRATED_COUNTY_BILL:,.2f} "
                f"(which excludes education). Full bill including education is ${COMBINED_TOTAL:,.2f}."
            ),
            "warnings": [
                "County budget illustrations of $4,295.35 exclude education; this receipt shows the full RT total.",
                "Rate × $391,000 yields $4,295.33 for municipal+hospital; the budget table prints $4,295.35 (2¢).",
                "Department shares are a pro-rata model over the net levy — not a published per-household split.",
                "Paris is billed as County of Brant (single-tier FIR 2920); there is no separate Town of Paris pack.",
            ],
        },
        "hypothetical5000": {
            "amountCad": 5000,
            "evidenceStatus": "DERIVED",
            "allocatable": True,
            "impliedAssessmentCad": IMPLIED_5000,
            "compositionShares": [
                {
                    "label": "County of Brant (municipal)",
                    "share": SHARE_MUN,
                    "sourceFactId": "BRANT-TAXRATE-RES-MUNICIPAL-2026",
                },
                {
                    "label": "Hospital special levy",
                    "share": SHARE_HOSP,
                    "sourceFactId": "BRANT-TAXRATE-RES-HOSPITAL-2026",
                },
                {
                    "label": "Education (Province of Ontario)",
                    "share": SHARE_EDU,
                    "sourceFactId": "BRANT-TAXRATE-RES-EDUCATION-2026",
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
        "screen": "TaxReceipt",
        "defaultProfile": "supportedAverageHousehold",
        "showGapsAsFirstClassUi": True,
        "forbidFillerAllocation": True,
        "flaggedDefinition": (
            "Flagged means this line needs an explanation. It does not mean the money was wasted."
        ),
        "publishedFindingIds": [],
        "marqueeFindings": [],
        "municipalBucketLabel": "County portion",
        "regionBucketLabel": "Upper-tier (n/a)",
        "heroLabel": "Total residential bill · median · 2026 tax rates",
    },
}

for target in (DATA, WEB_DATA):
    (target / "evidence-ledger.json").write_text(
        json.dumps(ledger, indent=2) + "\n", encoding="utf-8"
    )
    (target / "taxpayer-receipt.json").write_text(
        json.dumps(receipt, indent=2) + "\n", encoding="utf-8"
    )

print("facts", len(facts))
print("derived", len(derived_rows))
print("gaps", len(gaps))
print("findings", len(findings))
print("municipal", MUNICIPAL_PORTION, "hospital", HOSPITAL_PORTION, "edu", EDUCATION_PORTION)
print("combined", COMBINED_TOTAL, "county+hosp", COUNTY_PLUS_HOSPITAL)
print("county lines sum", round(sum(x["amountCad"] for x in county_lines), 2))
print("wrote", DATA)
