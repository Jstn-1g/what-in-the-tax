"""Build evidence-first ledger + honest taxpayer receipt prototype.

Rules:
- FACT: quoted from source with page + amount
- DERIVED: computed only from FACT ids with explicit formula
- GAP: missing evidence — never invent amounts
- JUDGMENT: interpretive finding; may cite facts but billImpactCad is null unless formula exists
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"


def fact(**kwargs):
    kwargs.setdefault("kind", "FACT")
    return kwargs


def gap(**kwargs):
    kwargs.setdefault("kind", "GAP")
    return kwargs


def derived(**kwargs):
    kwargs.setdefault("kind", "DERIVED")
    return kwargs


# --- Region rural household table (Region Budget Book p.12) ---
# Rural column = Wellesley + North Dumfries; assessment $354,500 (2016 CVA)
REGION_RURAL_HH = [
    ("Police Service", 900, 298_907_000, 272_610_000),
    ("Public Transit (area-rated; rural)", 63, 231_203_000, 156_402_000),
    ("Housing Services", 429, 178_544_000, 129_992_000),
    ("Roads / Design & Construction / Engineering", 240, 78_529_000, 72_779_000),
    ("Waste Management", 213, 80_797_000, 64_596_000),
    ("Financial Expenses", 89, 29_630_000, 26_969_000),
    ("Paramedic Services", 134, 86_447_000, 40_575_000),
    ("Employment / Income Support", 53, 144_080_000, 16_098_000),
    ("Seniors' Services", 51, 54_042_000, 15_597_000),
    ("Human Resources", 39, 13_269_000, 11_955_000),
    ("Information Technology Services", 49, 14_979_000, 14_979_000),
    ("Public Health", 45, 45_222_000, 13_561_000),
    ("Facilities & Fleet Management", 24, 10_196_000, 7_189_000),
    ("Cultural Services", 33, 11_722_000, 10_060_000),
    ("Children's Services", 30, 245_740_000, 9_143_000),
    ("Elected Offices & Office of the CAO", 17, 5_256_000, 5_256_000),
    ("Resident Experience, Strategy and Communications", 19, 5_869_000, 5_855_000),
    ("Airport", 31, 19_855_000, 9_281_000),
    ("Planning, Development & Legislative Services", 21, 34_909_000, 6_510_000),
    ("Finance", 24, 7_524_000, 7_369_000),
    ("Regional Library (area-rated; rural)", 79, 3_809_000, 3_314_000),
    ("Build Waterloo Region", 16, 6_277_000, 4_925_000),
    ("Strategy, Performance and Partnerships", 20, 5_952_000, 5_952_000),
]

rural_service_sum = sum(x[1] for x in REGION_RURAL_HH)


facts = [
    fact(
        id="ND-LEVY-2026",
        sourceId="nd-2026-draft",
        page=8,
        label="North Dumfries 2026 draft municipal levy requirement",
        amountCad=9_002_499,
        excerpt="2026 LEVY REQUIREMENT = $9,002,499",
        status="draft",
    ),
    fact(
        id="ND-LEVY-2025",
        sourceId="nd-2026-draft",
        page=8,
        label="North Dumfries 2025 levy requirement (comparator)",
        amountCad=8_427_827,
        excerpt="2025 LEVY REQUIREMENT = $8,427,827",
        status="approved_prior_year",
    ),
    fact(
        id="ND-LEVY-INCREASE-2026",
        sourceId="nd-2026-draft",
        page=8,
        label="Year-over-year levy increase (draft)",
        amountCad=574_672,
        excerpt="Levy Increase $574,672",
        status="draft",
    ),
    fact(
        id="ND-TAXRATE-RURAL-2026",
        sourceId="nd-2026-draft",
        page=8,
        label="2026 draft rural residential township tax rate",
        value=0.00315303,
        excerpt="Residential Township Tax Rate 0.00315303 (2026 Rural)",
        status="draft",
    ),
    fact(
        id="ND-AVG-ASSESSMENT",
        sourceId="nd-2026-draft",
        page=8,
        label="Average residential assessment used by Township",
        amountCad=455_000,
        excerpt="Average Residential Assessment for the Township of North Dumfries 455,000",
        status="draft",
    ),
    fact(
        id="ND-TOWNSHIP-TAX-RURAL-AVG-2026",
        sourceId="nd-2026-draft",
        page=8,
        label="2026 draft township taxes — rural average assessment",
        amountCad=1434.63,
        excerpt="Township Taxes Annually $1,434.63 at $455,000 assessment (Rural; TOWNSHIP PORTION ONLY)",
        status="draft",
        note="Computed check: 455000 * 0.00315303 = 1434.629 ≈ 1434.63",
    ),
    fact(
        id="ND-TOWNSHIP-TAX-URBAN-AVG-2026",
        sourceId="nd-2026-draft",
        page=8,
        label="2026 draft township taxes — urban average assessment",
        amountCad=1505.47,
        excerpt="Township Taxes Annually $1,505.47 at $455,000 assessment (Urban; TOWNSHIP PORTION ONLY)",
        status="draft",
    ),
    fact(
        id="ND-DEPT-CORPORATE-2026",
        sourceId="nd-2026-draft",
        page=9,
        label="TOTAL CORPORATE SERVICES 2026 draft",
        amountCad=2_091_306,
        excerpt="TOTAL CORPORATE SERVICES ... 2,091,306",
        status="draft",
    ),
    fact(
        id="ND-DEPT-FIRE-2026",
        sourceId="nd-2026-draft",
        page=9,
        label="TOTAL FIRE 2026 draft",
        amountCad=1_182_646,
        excerpt="TOTAL FIRE ... 1,182,646",
        status="draft",
    ),
    fact(
        id="ND-DEPT-PROTECTIVE-2026",
        sourceId="nd-2026-draft",
        page=9,
        label="TOTAL PROTECTIVE SERVICES 2026 draft (includes Fire)",
        amountCad=1_554_793,
        excerpt="TOTAL PROTECTIVE SERVICES ... 1,554,793",
        status="draft",
    ),
    fact(
        id="ND-DEPT-PW-2026",
        sourceId="nd-2026-draft",
        page=9,
        label="TOTAL PUBLIC WORKS 2026 draft",
        amountCad=2_477_423,
        excerpt="TOTAL PUBLIC WORKS ... 2,477,423",
        status="draft",
    ),
    fact(
        id="ND-DEPT-REC-2026",
        sourceId="nd-2026-draft",
        page=9,
        label="TOTAL RECREATION SERVICES 2026 draft",
        amountCad=1_867_455,
        excerpt="TOTAL RECREATION SERVICES ... 1,867,455",
        status="draft",
    ),
    fact(
        id="ND-DEPT-REC-OVERHEAD-2026",
        sourceId="nd-2026-draft",
        page=9,
        label="Recreation and Cultural Services Overhead 2026 draft",
        amountCad=1_468_430,
        excerpt="Total Recreation and Cultural Services Overhead ... 1,468,430",
        status="draft",
    ),
    fact(
        id="ND-DEPT-PW-OVERHEAD-2026",
        sourceId="nd-2026-draft",
        page=9,
        label="Transportation Services Overhead 2026 draft",
        amountCad=1_466_225,
        excerpt="Total Transportation Services - Overhead ... 1,466,225",
        status="draft",
    ),
    fact(
        id="ND-DEPT-PLANNING-2026",
        sourceId="nd-2026-draft",
        page=9,
        label="TOTAL PLANNING 2026 draft",
        amountCad=451_372,
        excerpt="TOTAL PLANNING ... 451,372",
        status="draft",
    ),
    fact(
        id="ND-CAPITAL-TAX-RESERVE-XFER-2026",
        sourceId="nd-2026-draft",
        page=43,
        label="Tax levy funding for Capital Reserve Transfers 2026",
        amountCad=1_625_000,
        excerpt="tax levy funding for Capital Reserve Transfers ... in 2026 totals $1,625,000",
        status="draft",
    ),
    fact(
        id="ND-CAPITAL-PROGRAM-2026",
        sourceId="nd-2026-draft",
        page=57,
        label="2026 draft capital program total",
        amountCad=31_192_121,
        excerpt="TOTAL $31,192,121",
        status="draft",
    ),
    fact(
        id="ND-CAP-ARENA-2026",
        sourceId="nd-2026-draft",
        page=53,
        label="NDCC Twin Pad / Net Zero Arena construction phase",
        amountCad=16_190_160,
        excerpt="construction phase of the project is estimated at a cost of $16,190,160",
        status="draft",
        funding=[
            {"source": "Federal Net Zero grant", "amountCad": 5_000_000},
            {"source": "Debt financing", "amountCad": 5_000_000},
            {"source": "Centre for the Community Group fundraising", "amountCad": 2_121_360},
            {"source": "Development Charges", "amountCad": 520_000},
        ],
        note="Capital table (p.57) also lists additional reserve/boundary/fundraising columns totaling $16,190,160. Debt P&I begins 2027 (p.43).",
    ),
    fact(
        id="ND-CAP-DEBT-TWINPAD",
        sourceId="nd-2026-draft",
        page=43,
        label="New debt proposed for Twin Pad",
        amountCad=5_000_000,
        excerpt="new debt financing proposed [$5 million] to finance the Twin Pad Project ... first installment ... commence in fiscal year 2027 ... 20 year term",
        status="draft",
    ),
    fact(
        id="ND-CAP-ACC-EXTERIOR-2026",
        sourceId="nd-2026-draft",
        page=52,
        label="Ayr Community Centre major exterior rehabilitation",
        amountCad=3_500_000,
        excerpt="projected cost for this work program is $3,500,000. Funding is derived from a Grant of $1 million ... residual drawn from Reserve Accounts",
        status="draft",
    ),
    fact(
        id="ND-CAP-PUMPTRACK-2026",
        sourceId="nd-2026-draft",
        page=54,
        label="Pump Track at Jim Schmidt Memorial Park",
        amountCad=568_756,
        excerpt="estimated value of $568,756 ... fundraising and donations ... $498,756 ... Township is funding $70,000",
        status="draft",
        funding=[
            {"source": "Fundraising/donations (incl. Trillium $200k, Hallman $100k)", "amountCad": 498_756},
            {"source": "Township cash", "amountCad": 70_000},
        ],
    ),
    fact(
        id="ND-CAP-CLYDE-PARK-2026",
        sourceId="nd-2026-draft",
        page=54,
        label="Clyde Park Phase I",
        amountCad=185_500,
        excerpt="project cost is estimated at $185,500 and is funded from Grandbridge Energy Reserve Account and Parkland Trust Account",
        status="draft",
    ),
    fact(
        id="ND-CAP-BROADBAND-2026",
        sourceId="nd-2026-draft",
        page=45,
        label="Broadband Enhancement Strategy Phase 1",
        amountCad=150_000,
        excerpt="project is estimated at $150,000 with funding through the Broadband Reserve Account",
        status="draft",
    ),
    fact(
        id="ND-CAP-OFFICIAL-PLAN-2026",
        sourceId="nd-2026-draft",
        page=46,
        label="Official Plan comprehensive update / conformity exercise",
        amountCad=405_000,
        excerpt="project has an estimated cost of $405,000 and is funded through the Planning Studies Reserve Account, Development Charges Reserve Account and funding from Waterloo Economic Development Corporation",
        status="draft",
    ),
    fact(
        id="ND-LEGAL-ADMIN-2026",
        sourceId="nd-2026-draft",
        page=18,
        label="Administration Legal Expense 2026 draft",
        amountCad=27_000,
        excerpt="Administration - Legal Expense ... 27,000",
        status="draft",
    ),
    fact(
        id="ND-LEGAL-TAX-SALE-2026",
        sourceId="nd-2026-draft",
        page=18,
        label="Administration Tax Sale Legal & Other Costs 2026 draft",
        amountCad=22_000,
        excerpt="Administration - Tax Sale - Legal & Other Costs ... 22,000",
        status="draft",
    ),
    fact(
        id="ND-LEGAL-BUILDING-2026",
        sourceId="nd-2026-draft",
        page=24,
        label="Building Services Legal Expense 2026 draft",
        amountCad=12_000,
        excerpt="Building Services - Legal Expense ... 12,000",
        status="draft",
    ),
    fact(
        id="ND-LEGAL-BYLAW-2026",
        sourceId="nd-2026-draft",
        page=26,
        label="By-Law Legal Expense 2026 draft",
        amountCad=25_000,
        excerpt="By-Law - Legal Expense ... 25,000",
        status="draft",
    ),
    fact(
        id="ND-LEGAL-PLANNING-2026",
        sourceId="nd-2026-draft",
        page=41,
        label="Planning Legal Expense 2026 draft",
        amountCad=8_000,
        excerpt="Planning - Legal Expense ... 8,000",
        status="draft",
    ),
    fact(
        id="ND-GRANTS-COMMUNITY-2026",
        sourceId="nd-2026-draft",
        page=14,
        label="Tax-funded community grants 2026",
        amountCad=40_000,
        excerpt="The 2026 tax funded community grants are $40,000",
        status="draft",
    ),
    fact(
        id="ND-GRANT-AYR-CEMETERY-2026",
        sourceId="nd-2026-draft",
        page=14,
        label="Ayr Cemetery grant",
        amountCad=10_000,
        excerpt="allocations to the Ayr Cemetery, in the amount of $10,000",
        status="draft",
    ),
    fact(
        id="ND-GRANT-SHEFFIELD-LIONS-2026",
        sourceId="nd-2026-draft",
        page=14,
        label="Sheffield Lions / Scott Women’s Institute Building",
        amountCad=3_500,
        excerpt="$3,500 to the Sheffield Lions Club for the maintenance of the Scott Women’s Institute Building",
        status="draft",
    ),
    fact(
        id="ND-RECORDS-MGMT-2026",
        sourceId="nd-2026-draft",
        page=16,
        label="Records Management Services",
        amountCad=8_500,
        excerpt="Administration - Records Management Services ... 8,500",
        status="draft",
    ),
    fact(
        id="ND-WREDC-2026",
        sourceId="nd-2026-draft",
        page=41,
        label="Waterloo Region Economic Development Corporation fee",
        amountCad=20_000,
        excerpt="Waterloo Region Economic Development Corporation ($20,000)",
        status="draft",
    ),
    fact(
        id="ND-TOURISM-2026",
        sourceId="nd-2026-draft",
        page=41,
        label="Waterloo Region Tourism & Marketing Corporation fee",
        amountCad=5_000,
        excerpt="Waterloo Region Tourism & Marketing Corporation ($5,000)",
        status="draft",
    ),
    fact(
        id="ND-SUSTAINABLE-WR-2026",
        sourceId="nd-2026-draft",
        page=41,
        label="Sustainable Waterloo Region levy",
        amountCad=1_725,
        excerpt="Sustainable Waterloo Levy ($1,725)",
        status="draft",
    ),
    fact(
        id="ND-HERITAGE-SOFTWARE-2026",
        sourceId="nd-2026-draft",
        page=41,
        label="Heritage annual software licensing",
        amountCad=5_000,
        excerpt="Heritage -Annual Licencing of Software ... 5,000",
        status="draft",
    ),
    fact(
        id="ND-ANIMAL-CONTROL-2026",
        sourceId="nd-2026-draft",
        page=9,
        label="Total Animal Control 2026 draft",
        amountCad=10_875,
        excerpt="Total Animal Control ... 10,875",
        status="draft",
    ),
    fact(
        id="ND-POP-CENSUS-2021",
        sourceId="statcan-2021",
        page=None,
        label="North Dumfries population (2021 Census)",
        amountCad=None,
        value=10_619,
        excerpt="Statistics Canada 2021 Census: North Dumfries population 10,619",
        status="external",
        url="https://www12.statcan.gc.ca/census-recensement/2021/dp-pd/prof/index.cfm?Lang=E",
    ),
    fact(
        id="ROW-LEVY-2026",
        sourceId="row-2026-book",
        page=12,
        label="Region of Waterloo 2026 property tax levy",
        amountCad=887_329_000,
        excerpt="Regional Tax Levy ... $887,329 ($000's)",
        status="approved",
    ),
    fact(
        id="ROW-WRPS-LEVY-2026",
        sourceId="row-2026-book",
        page=12,
        label="WRPS 2026 property tax levy",
        amountCad=272_610_000,
        excerpt="Police Service ... Property Tax Levy ($000's) 272,610",
        status="approved",
    ),
    fact(
        id="ROW-RURAL-HH-TOTAL-2026",
        sourceId="row-2026-book",
        page=12,
        label="Tax-supported regional services cost per average rural household (N. Dumfries / Wellesley)",
        amountCad=2543,
        excerpt="Rural ... Regional Tax Levy ... $2,543 ... Based on an average residential property valued at $354,500",
        status="approved",
        assessmentBasisCad=354_500,
        note="Rural column explicitly includes Wellesley and North Dumfries.",
    ),
    fact(
        id="ROW-SUMMARY-OP-FUNDING-TAX-2026",
        sourceId="row-2026-summary",
        page=6,
        label="Summary booklet — property tax funding of operating budget",
        amountCad=887_000_000,
        excerpt="Property Taxes $887 M",
        status="summary",
    ),
    fact(
        id="ROW-SUMMARY-CAPITAL-2026",
        sourceId="row-2026-summary",
        page=7,
        label="Summary booklet — 2026 capital budget",
        amountCad=772_000_000,
        excerpt="$772 M 2026 Capital Budget Funding and Financing",
        status="summary",
    ),
    fact(
        id="ROW-SUMMARY-AVG-IMPACT-2026",
        sourceId="row-2026-summary",
        page=4,
        label="Summary booklet — average property impact",
        amountCad=142,
        excerpt="5.1% ... $142 for an average property, or $12 per month",
        status="summary",
    ),
]

# Region rural household service lines as facts
for i, (label, hh, net_exp, levy) in enumerate(REGION_RURAL_HH, start=1):
    facts.append(
        fact(
            id=f"ROW-RURAL-HH-{i:02d}",
            sourceId="row-2026-book",
            page=12,
            label=f"Rural household — {label}",
            amountCad=hh,
            regionalNetExpenditure000s=net_exp // 1000,
            regionalPropertyTaxLevy000s=levy // 1000,
            excerpt=f"{label} ... Rural ${hh}",
            status="approved",
            assessmentBasisCad=354_500,
        )
    )

# Derived
dept_ids = [
    "ND-DEPT-CORPORATE-2026",
    "ND-DEPT-PROTECTIVE-2026",
    "ND-DEPT-PW-2026",
    "ND-DEPT-REC-2026",
    "ND-DEPT-PLANNING-2026",
    "ND-CAPITAL-TAX-RESERVE-XFER-2026",
]
dept_amounts = {f["id"]: f["amountCad"] for f in facts if f["id"] in dept_ids}
dept_sum = sum(dept_amounts.values())

township_avg = 1434.63
derived_rows = [
    derived(
        id="DRV-ND-DEPT-SUM",
        label="Sum of township draft dept nets used for allocation base",
        amountCad=dept_sum,
        formula="CORPORATE + PROTECTIVE + PW + REC + PLANNING + CAPITAL_RESERVE_XFER",
        inputs=dept_ids,
    ),
]

township_alloc = []
for did, amt in dept_amounts.items():
    share = amt / dept_sum
    dollars = round(township_avg * share, 2)
    derived_rows.append(
        derived(
            id=f"DRV-ALLOC-{did}",
            label=f"Rural avg township bill share — {did}",
            amountCad=dollars,
            formula=f"{township_avg} * ({amt} / {dept_sum})",
            inputs=["ND-TOWNSHIP-TAX-RURAL-AVG-2026", did, "DRV-ND-DEPT-SUM"],
            shareOfTownshipBill=round(share, 6),
        )
    )
    township_alloc.append({"factId": did, "amountCad": dollars, "share": round(share, 6)})

legal_ids = [
    "ND-LEGAL-ADMIN-2026",
    "ND-LEGAL-TAX-SALE-2026",
    "ND-LEGAL-BUILDING-2026",
    "ND-LEGAL-BYLAW-2026",
    "ND-LEGAL-PLANNING-2026",
]
legal_sum = sum(next(f["amountCad"] for f in facts if f["id"] == i) for i in legal_ids)
derived_rows.append(
    derived(
        id="DRV-ND-LEGAL-STACK-2026",
        label="Sum of identified 2026 draft legal expense lines",
        amountCad=legal_sum,
        formula="ADMIN + TAX_SALE + BUILDING + BYLAW + PLANNING legal lines",
        inputs=legal_ids,
    )
)

corp = 2_091_306
pop = 10_619
derived_rows.append(
    derived(
        id="DRV-ND-CORP-PER-CAPITA",
        label="Corporate Services $ per 2021 census capita",
        amountCad=round(corp / pop, 2),
        formula="ND-DEPT-CORPORATE-2026 / ND-POP-CENSUS-2021",
        inputs=["ND-DEPT-CORPORATE-2026", "ND-POP-CENSUS-2021"],
    )
)
derived_rows.append(
    derived(
        id="DRV-ND-ARENA-PER-CAPITA",
        label="Arena project $ per 2021 census capita",
        amountCad=round(16_190_160 / pop, 2),
        formula="ND-CAP-ARENA-2026 / ND-POP-CENSUS-2021",
        inputs=["ND-CAP-ARENA-2026", "ND-POP-CENSUS-2021"],
    )
)
derived_rows.append(
    derived(
        id="DRV-ND-ARENA-SHARE-OF-CAPITAL",
        label="Arena share of 2026 capital program",
        value=round(16_190_160 / 31_192_121, 4),
        formula="ND-CAP-ARENA-2026 / ND-CAPITAL-PROGRAM-2026",
        inputs=["ND-CAP-ARENA-2026", "ND-CAPITAL-PROGRAM-2026"],
    )
)

# Gaps
gaps = [
    gap(
        id="GAP-5000-BILL",
        title="No source supports a single accurate $5,000 combined tax bill composition",
        detail="Township average assessment ($455,000) and Region household table assessment ($354,500) differ. No extracted 2026 final combined township+region+education tax rate schedule for North Dumfries at one assessment was used.",
        blocks=["hypothetical_$5000_receipt_allocation"],
        neededEvidence=[
            "2026 final North Dumfries tax rate by-law (township + region + education)",
            "OR a sample final tax bill for a North Dumfries residential property totaling ~$5,000",
        ],
    ),
    gap(
        id="GAP-EDUCATION-2026",
        title="2026 education portion for North Dumfries not extracted",
        detail="Education rates are set provincially. Not pulled from a 2026 ND final tax schedule in this ledger.",
        blocks=["education_share_of_bill"],
        neededEvidence=["2026 education tax rate applicable to North Dumfries residential"],
    ),
    gap(
        id="GAP-ND-FINAL-BUDGET",
        title="North Dumfries 2026 figures are DRAFT (Dec 8, 2025 binder)",
        detail="Operating and capital amounts may change after January/February 2026 budget meetings and final adoption.",
        blocks=["treat_nd_amounts_as_final"],
        neededEvidence=["Adopted 2026 North Dumfries budget / final tax rate by-law"],
    ),
    gap(
        id="GAP-FLAGGED-DOLLARS-ON-BILL",
        title="Cannot allocate 'flagged/inefficient' dollars on a household bill without an explicit rule set",
        detail="Budget books do not label lines as inefficient. Any necessary-vs-flagged split is interpretive. Do not invent billImpactCad for judgment flags.",
        blocks=["flagged_share_of_5000_bill"],
        neededEvidence=[
            "User-approved classification rules (e.g. which object codes count as overhead)",
            "Optional peer benchmarks with citations",
        ],
    ),
    gap(
        id="GAP-ARENA-2026-TAX-IMPACT",
        title="2026 tax-bill impact of Twin Pad debt service not stated",
        detail="Debt P&I begins 2027. 2026 capital is funded by grant/debt/fundraising/DCs/reserves — not a stated 2026 operating levy line equal to $16.19M.",
        blocks=["arena_dollars_on_2026_tax_bill"],
        neededEvidence=["Debt amortization schedule / 2027+ levy impact estimate from Township"],
    ),
    gap(
        id="GAP-BEAVER-LINE-AMOUNT",
        title="Beaver extraction spend not isolated as its own budget line amount",
        detail="Narrative mentions external contractors for beaver extraction; no discrete dollar line extracted.",
        blocks=["beaver_extraction_amount"],
        neededEvidence=["Invoice/contract line or GL detail"],
    ),
]

findings = [
    {
        "id": "FIND-ADMIN-CORP-SCALE",
        "kind": "JUDGMENT",
        "category": "administrative_bloat",
        "title": "Corporate Services is a large share of the township draft budget",
        "severitySeverity": "needs_review",
        "citedFactIds": ["ND-DEPT-CORPORATE-2026", "ND-LEVY-2026", "DRV-ND-CORP-PER-CAPITA", "ND-POP-CENSUS-2021"],
        "evidenceSummary": "Corporate Services draft $2,091,306 vs municipal levy $9,002,499; ≈$197/capita at 2021 population.",
        "billImpactCad": None,
        "gapIds": ["GAP-FLAGGED-DOLLARS-ON-BILL"],
    },
    {
        "id": "FIND-ADMIN-LEGAL-STACK",
        "kind": "JUDGMENT",
        "category": "administrative_bloat",
        "title": "Multiple legal expense lines across departments",
        "opportunitySeverity": "needs_review",
        "citedFactIds": ["DRV-ND-LEGAL-STACK-2026", *legal_ids],
        "evidenceSummary": f"Identified legal lines sum to ${legal_sum:,}.",
        "billImpactCad": None,
        "gapIds": ["GAP-FLAGGED-DOLLARS-ON-BILL"],
    },
    {
        "id": "FIND-CAP-ARENA",
        "kind": "JUDGMENT",
        "category": "questionable_capital",
        "title": "Net Zero Twin Pad dominates 2026 capital program",
        "opportunitySeverity": "high_attention",
        "citedFactIds": [
            "ND-CAP-ARENA-2026",
            "ND-CAPITAL-PROGRAM-2026",
            "ND-CAP-DEBT-TWINPAD",
            "DRV-ND-ARENA-PER-CAPITA",
            "DRV-ND-ARENA-SHARE-OF-CAPITAL",
        ],
        "evidenceSummary": "$16,190,160 of $31,192,121 capital (~51.9%); $5M new debt; debt service starts 2027.",
        "billImpactCad": None,
        "gapIds": ["GAP-ARENA-2026-TAX-IMPACT", "GAP-FLAGGED-DOLLARS-ON-BILL"],
    },
    {
        "id": "FIND-CAP-DUAL-FACILITY",
        "kind": "JUDGMENT",
        "category": "questionable_capital",
        "title": "ACC $3.5M exterior rehab concurrent with new Twin Pad",
        "opportunitySeverity": "high_attention",
        "citedFactIds": ["ND-CAP-ACC-EXTERIOR-2026", "ND-CAP-ARENA-2026"],
        "evidenceSummary": "ACC exterior rehab $3,500,000 ($1M Ontario grant) while Twin Pad under construction; ACC ice to be decommissioned on Twin Pad opening.",
        "billImpactCad": None,
        "gapIds": ["GAP-FLAGGED-DOLLARS-ON-BILL"],
    },
    {
        "id": "FIND-CAP-PUMPTRACK",
        "kind": "JUDGMENT",
        "category": "questionable_capital",
        "title": "Pump track amenity — mostly externally funded",
        "opportunitySeverity": "watch",
        "citedFactIds": ["ND-CAP-PUMPTRACK-2026"],
        "evidenceSummary": "$568,756 total; Township cash $70,000; donations/fundraising $498,756.",
        "billImpactCad": None,
        "gapIds": [],
    },
    {
        "id": "FIND-UNUSUAL-GRANTS",
        "kind": "JUDGMENT",
        "category": "unusual_line_items",
        "title": "Community grants and cemetery/service-club transfers",
        "opportunitySeverity": "watch",
        "citedFactIds": [
            "ND-GRANTS-COMMUNITY-2026",
            "ND-GRANT-AYR-CEMETERY-2026",
            "ND-GRANT-SHEFFIELD-LIONS-2026",
        ],
        "evidenceSummary": "Community grants $40,000; Ayr Cemetery $10,000; Sheffield Lions $3,500.",
        "billImpactCad": None,
        "gapIds": ["GAP-FLAGGED-DOLLARS-ON-BILL"],
    },
    {
        "id": "FIND-UNUSUAL-PARTNERSHIP-FEES",
        "kind": "JUDGMENT",
        "category": "unusual_line_items",
        "title": "Economic development / tourism / sustainability fees",
        "opportunitySeverity": "watch",
        "citedFactIds": ["ND-WREDC-2026", "ND-TOURISM-2026", "ND-SUSTAINABLE-WR-2026"],
        "evidenceSummary": "WREDC $20,000; Tourism $5,000; Sustainable WR $1,725.",
        "billImpactCad": None,
        "gapIds": [],
    },
    {
        "id": "FIND-UNUSUAL-HERITAGE-SOFTWARE",
        "kind": "JUDGMENT",
        "category": "unusual_line_items",
        "title": "Heritage software licensing",
        "opportunitySeverity": "watch",
        "citedFactIds": ["ND-HERITAGE-SOFTWARE-2026"],
        "evidenceSummary": "Heritage annual software licensing $5,000.",
        "billImpactCad": None,
        "gapIds": [],
    },
]

sources = [
    {
        "id": "nd-2026-draft",
        "title": "Township of North Dumfries 2026 Municipal Draft Budget Binder",
        "url": "https://www.northdumfries.ca/media/csjjshvf/2026-draft-budget-binder.pdf",
        "localPath": "source-pdfs/2026-draft-budget-binder.pdf",
        "extractedText": "data/_extracts/2026-draft-budget-binder.txt",
        "asOf": "2025-12-08",
        "authority": "draft",
    },
    {
        "id": "row-2026-book",
        "title": "Region of Waterloo 2026 Final Budget Book",
        "url": "https://www.regionofwaterloo.ca/media/ynro4cd2/2026_final_budget_book.pdf",
        "localPath": "source-pdfs/2026_final_budget_book_region.pdf",
        "extractedText": "data/_extracts/2026_final_budget_book_region.pdf".replace(".pdf", ".txt"),
        "authority": "final",
    },
    {
        "id": "row-2026-summary",
        "title": "Region of Waterloo 2026 Plan and Budget Summary Booklet",
        "url": "https://www.regionofwaterloo.ca/media/3two5ebp/2026-plan-and-budget-summary-booklet.pdf",
        "localPath": "source-pdfs/2026-plan-and-budget-summary-booklet.pdf",
        "extractedText": "data/_extracts/2026-plan-and-budget-summary-booklet.txt",
        "authority": "summary",
    },
    {
        "id": "statcan-2021",
        "title": "Statistics Canada 2021 Census Profile — North Dumfries",
        "url": "https://www12.statcan.gc.ca/census-recensement/2021/dp-pd/prof/index.cfm?Lang=E",
        "authority": "external",
    },
]

ledger = {
    "schemaVersion": "2.0.0",
    "artifact": "EvidenceLedger",
    "evidencePolicy": {
        "rules": [
            "FACT: must include sourceId, excerpt, and page when from PDF.",
            "DERIVED: must include formula and input ids; no new external numbers.",
            "GAP: record missing evidence; never invent amounts to fill UI.",
            "JUDGMENT: interpretive only; billImpactCad null unless a cited formula exists.",
            "Draft vs final: North Dumfries 2026 amounts are draft until adopted budget is ingested.",
        ]
    },
    "sources": sources,
    "facts": facts,
    "derived": derived_rows,
    "gaps": gaps,
    "findings": findings,
}

# Honest receipt: only what we can support
region_lines = [
    {
        "id": f["id"],
        "label": f["label"].replace("Rural household — ", ""),
        "amountCad": f["amountCad"],
        "classification": "region_tax_supported",
        "evidenceStatus": "FACT",
        "sourceFactId": f["id"],
    }
    for f in facts
    if re.fullmatch(r"ROW-RURAL-HH-\d{2}", f["id"])
]
region_sum = sum(x["amountCad"] for x in region_lines)
region_lines.append(
    {
        "id": "ROW-PIL-OFFSET",
        "label": "Less: Payments in Lieu & Supplementary Taxes (household share)",
        "amountCad": -78,
        "classification": "region_tax_supported",
        "evidenceStatus": "FACT",
        "sourceFactId": "ROW-RURAL-HH-TOTAL-2026",
        "note": "Source reduces rural household to $2,543 after PIL/supplementary taxes.",
    }
)
# Extracted service lines sum to $2,619; source subtotal prints $2,621 before -$78 PIL.
# Keep authoritative total $2,543; surface $2 as explicit reconciling gap — do not invent service attribution.
region_lines.append(
    {
        "id": "ROW-TABLE-ROUNDING",
        "label": "Unallocated table-rounding difference (source total vs summed lines)",
        "amountCad": 2,
        "classification": "reconciling_item",
        "evidenceStatus": "GAP",
        "gapId": "GAP-RURAL-HH-LINE-SUM",
        "note": "Do not treat as a service. Needed so line items reconcile to published rural total $2,543.",
    }
)

township_lines = []
label_map = {
    "ND-DEPT-CORPORATE-2026": "Corporate Services",
    "ND-DEPT-PROTECTIVE-2026": "Protective Services (incl. Fire)",
    "ND-DEPT-PW-2026": "Public Works",
    "ND-DEPT-REC-2026": "Recreation Services",
    "ND-DEPT-PLANNING-2026": "Planning",
    "ND-CAPITAL-TAX-RESERVE-XFER-2026": "Capital reserve transfers (tax-funded)",
}
for row in township_alloc:
    township_lines.append(
        {
            "id": row["factId"],
            "label": label_map[row["factId"]],
            "amountCad": row["amountCad"],
            "classification": "township_draft_allocated",
            "evidenceStatus": "DERIVED",
            "sourceFactId": row["factId"],
            "note": "Pro-rata of draft department nets against rural average township tax $1,434.63",
        }
    )

receipt = {
    "schemaVersion": "2.0.0",
    "artifact": "TaxpayerReceipt",
    "status": "partial_evidence_based",
    "purpose": "UI data model using only supported allocations. Hypothetical $5,000 combined bill is NOT fully allocatable — see gaps.",
    "evidencePolicyRef": "data/evidence-ledger.json",
    "profiles": {
        "supportedAverageHousehold": {
            "description": "Best evidence-based profile without inventing a $5,000 bill.",
            "township": {
                "basis": "ND 2026 draft rural average at $455,000 assessment — TOWNSHIP PORTION ONLY",
                "amountCad": 1434.63,
                "assessmentCad": 455_000,
                "evidenceStatus": "FACT",
                "sourceFactId": "ND-TOWNSHIP-TAX-RURAL-AVG-2026",
                "lineItems": township_lines,
            },
            "region": {
                "basis": "Region 2026 Budget Book p.12 Rural column (North Dumfries + Wellesley) at $354,500 assessment",
                "amountCad": 2543,
                "assessmentCad": 354_500,
                "evidenceStatus": "FACT",
                "sourceFactId": "ROW-RURAL-HH-TOTAL-2026",
                "lineItems": region_lines,
                "lineItemsSumCheckCad": region_sum - 78,
            },
            "education": {
                "amountCad": None,
                "evidenceStatus": "GAP",
                "gapId": "GAP-EDUCATION-2026",
            },
            "combinedTotalCad": None,
            "combinedTotalNote": "Not summed: township and region use different assessment bases ($455k vs $354.5k). See GAP-5000-BILL.",
            "warnings": [
                "Do not add township $1,434.63 + region $2,543 and call it a real bill — assessment bases differ.",
                "North Dumfries operating amounts are DRAFT.",
            ],
        },
        "hypothetical5000": {
            "amountCad": 5000,
            "evidenceStatus": "GAP",
            "gapId": "GAP-5000-BILL",
            "allocatable": False,
            "receiptLineItems": [],
            "receiptTotals": None,
            "message": "No evidence-complete allocation for a $5,000 combined bill is published in this dataset. UI should show an incomplete state and list gaps, not filler percentages.",
        },
    },
    "findings": findings,
    "uiModelHints": {
        "screen": "TaxReceipt",
        "defaultProfile": "supportedAverageHousehold",
        "showGapsAsFirstClassUi": True,
        "forbidFillerAllocation": True,
        "marqueeFindings": ["FIND-CAP-ARENA", "FIND-CAP-DUAL-FACILITY", "FIND-ADMIN-CORP-SCALE"],
    },
}

# Fix rural sum assertion - source says 2621, our sum 2619 (likely PDF column rounding). Record gap/note.
if region_sum != 2621:
    gaps.append(
        gap(
            id="GAP-RURAL-HH-LINE-SUM",
            title="Rural household service lines sum does not exactly match source subtotal",
            detail=f"Extracted rural service lines sum to ${region_sum}; source subtotal shown as $2,621 before -$78 PIL. Difference ${2621 - region_sum}. Likely PDF table parsing/rounding; kept source total $2,543 as authoritative.",
            blocks=[],
            neededEvidence=["Re-verify page 12 table digits against PDF"],
        )
    )
    ledger["gaps"] = gaps

(DATA / "evidence-ledger.json").write_text(json.dumps(ledger, indent=2), encoding="utf-8")
(DATA / "taxpayer-receipt.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")

print("facts", len(facts))
print("derived", len(derived_rows))
print("gaps", len(gaps))
print("findings", len(findings))
print("region rural lines sum", region_sum, "after PIL", region_sum - 78)
print("township alloc sum", round(sum(x["amountCad"] for x in township_lines), 2))
print("wrote evidence-ledger.json and taxpayer-receipt.json")
