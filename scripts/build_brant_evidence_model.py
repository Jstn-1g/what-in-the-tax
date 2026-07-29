"""Build the Tier-0 County of Brant (Paris, ON) evidence receipt.

Paris is not a separate lower-tier municipality — property tax for Paris is
County of Brant (single-tier, MMAH assessment code 2920).

Rules:
- FACT: quoted from source with page + amount
- DERIVED: computed only from FACT ids with explicit formula
- every receipt-driving source and extract must match its reviewed SHA-256
- Tier 0 emits no findings or gaps; exclusions and reconciliations stay explicit
"""

from __future__ import annotations

import hashlib
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


def derived(**kwargs):
    kwargs.setdefault("kind", "DERIVED")
    return kwargs


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


SOURCE_BINDINGS = {
    "brant-2026-approved-budget": {
        "localPath": "source-pdfs/brant/2026-approved-budget-accessible.pdf",
        "sha256": "b8c622e920e82ae9c00160b730e970c39968f1a7cf6fcb522886214bfed8f5d9",
        "bytes": 1_438_059,
        "extractedText": "data/_extracts/brant/2026-approved-budget-accessible.txt",
        "extractedTextSha256": "2878a735c4d2420329a4710150905b0ac108c9330b76439cb9c5a49097c2705d",
    },
    "brant-2026-tax-rates": {
        "localPath": "source-pdfs/brant/2026-tax-rates.pdf",
        "sha256": "27d1266f0f10b52c7179806a577cd0ef45199448b9b127ee54793cf871bf3652",
        "bytes": 199_564,
        "extractedText": "data/_extracts/brant/2026-tax-rates.txt",
        "extractedTextSha256": "b4470259d7cecab15440f8f4c95b9f4747291f6d5b2512c8e9ad8b70be420af9",
    },
}


def bind_reviewed_source(source: dict) -> dict:
    source_id = source["id"]
    binding = SOURCE_BINDINGS[source_id]
    source_path = ROOT / binding["localPath"]
    extract_path = ROOT / binding["extractedText"]
    checks = (
        ("source", source_path, binding["sha256"]),
        ("extract", extract_path, binding["extractedTextSha256"]),
    )
    for label, path, expected_hash in checks:
        if not path.is_file():
            raise SystemExit(f"{source_id}: reviewed {label} bytes are missing: {path}")
        actual_hash = sha256_file(path)
        if actual_hash != expected_hash:
            raise SystemExit(
                f"{source_id}: reviewed {label} SHA-256 changed: "
                f"expected {expected_hash}, got {actual_hash}"
            )
    actual_bytes = source_path.stat().st_size
    if actual_bytes != binding["bytes"]:
        raise SystemExit(
            f"{source_id}: reviewed source byte length changed: "
            f"expected {binding['bytes']}, got {actual_bytes}"
        )
    return {**source, **binding}


# --- Control totals from 2026 Approved Budget Operating Forecast p.1 / p.5 ---
LEVY_2026 = 92_457_575
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
    bind_reviewed_source(
        {
            "id": "brant-2026-approved-budget",
            "title": (
                "County of Brant 2026 Approved Budget — "
                "Operating Forecast (Accessible)"
            ),
            "url": (
                "https://www.brant.ca/media/0dpbiteo/"
                "2026-approved-budget-accessible.pdf"
            ),
            "landingPage": (
                "https://www.brant.ca/council-and-county-administration/"
                "budget-and-finances/budget-and-capital-forecast/"
            ),
            "asOf": "2026-02",
            "retrievedAt": "2026-07-26",
            "publisher": "County of Brant",
            "authority": "official-municipal",
            "fiscalYear": 2026,
            "currency": "CAD",
            "documentKind": "approved-operating-budget",
            "adoptionStatus": "approved",
            "license": "unspecified",
            "licenseNote": (
                "No explicit reuse licence was identified for this PDF. The source "
                "site displays © 2026 County of Brant; the project's MIT licence "
                "does not relicense the official source document."
            ),
            "coverage": {
                "role": "receipt-driving",
                "citedPages": [1, 2, 3, 4, 5],
                "scope": (
                    "2026 net levy, median-home illustration, eleven department "
                    "control rows, Legal Services, and OPP"
                ),
            },
            "note": (
                "Adopted operating forecast; net levy and department summary."
            ),
        }
    ),
    bind_reviewed_source(
        {
            "id": "brant-2026-tax-rates",
            "title": "County of Brant 2026 Tax Rates",
            "url": "https://www.brant.ca/media/wgootdma/2026-tax-rates.pdf",
            "landingPage": "https://www.brant.ca/property-taxes/tax-rates/",
            "asOf": "2026",
            "retrievedAt": "2026-07-26",
            "publisher": "County of Brant",
            "authority": "official-municipal",
            "fiscalYear": 2026,
            "currency": "CAD",
            "documentKind": "tax-rate-schedule",
            "adoptionStatus": "final",
            "license": "unspecified",
            "licenseNote": (
                "No explicit reuse licence was identified for this PDF. The source "
                "site displays © 2026 County of Brant; the project's MIT licence "
                "does not relicense the official source document."
            ),
            "coverage": {
                "role": "receipt-driving",
                "citedPages": [1],
                "scope": (
                    "RT Residential municipal, hospital, education, and total "
                    "2026 tax rates"
                ),
            },
            "note": (
                "Municipal, hospital special levy, and education rates by tax class."
            ),
        }
    ),
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
        id="DRV-BRANT-BILL-COUNTY-391K",
        label="County municipal plus hospital special levy at median assessment",
        amountCad=COUNTY_PLUS_HOSPITAL,
        formula=(
            "DRV-BRANT-BILL-MUNICIPAL-391K + "
            "DRV-BRANT-BILL-HOSPITAL-391K"
        ),
        inputs=[
            "DRV-BRANT-BILL-MUNICIPAL-391K",
            "DRV-BRANT-BILL-HOSPITAL-391K",
        ],
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
        formula=(
            "DRV-BRANT-BILL-COUNTY-391K + "
            "DRV-BRANT-BILL-EDUCATION-391K"
        ),
        inputs=[
            "DRV-BRANT-BILL-COUNTY-391K",
            "DRV-BRANT-BILL-EDUCATION-391K",
        ],
    ),
    derived(
        id="DRV-BRANT-RATE-TOTAL-CHECK-2026",
        label="RT component rates sum to the published RT total rate",
        value=RATE_TOTAL,
        formula="sum(RT component rates) == BRANT-TAXRATE-RES-TOTAL-2026",
        inputs=[
            "BRANT-TAXRATE-RES-MUNICIPAL-2026",
            "BRANT-TAXRATE-RES-HOSPITAL-2026",
            "BRANT-TAXRATE-RES-EDUCATION-2026",
            "BRANT-TAXRATE-RES-TOTAL-2026",
        ],
        note="The three published RT component rates sum exactly to 0.0125155.",
    ),
    derived(
        id="DRV-BRANT-ILLUSTRATION-DELTA-391K",
        label="Published illustration minus rate-derived County amount",
        amountCad=ILLUSTRATION_DELTA,
        formula=(
            "BRANT-ILLUSTRATED-COUNTY-BILL-2026 - "
            "DRV-BRANT-BILL-COUNTY-391K"
        ),
        inputs=[
            "BRANT-ILLUSTRATED-COUNTY-BILL-2026",
            "DRV-BRANT-BILL-COUNTY-391K",
        ],
        note=(
            "The final tax-rate schedule is authoritative for this receipt. "
            "The approved-budget illustration is retained and reconciled as a "
            "$0.02 presentation difference; no cause is inferred."
        ),
    ),
]

# Pro-rata household shares of the municipal portion only (hospital is separate)
county_lines = []
household_share_ids = []
for fact_id, label, amount, _page in DEPTS:
    share = amount / LEVY_2026
    line_amt = round(MUNICIPAL_PORTION * share, 2)
    derived_id = f"DRV-{fact_id}-HH"
    household_share_ids.append(derived_id)
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
    derived_rows.append(
        derived(
            id="DRV-BRANT-ALLOCATION-ROUNDING-391K",
            label="Department allocation cent-rounding residual",
            amountCad=residual,
            formula=(
                "DRV-BRANT-BILL-MUNICIPAL-391K - sum("
                + ", ".join(household_share_ids)
                + ")"
            ),
            inputs=[
                "DRV-BRANT-BILL-MUNICIPAL-391K",
                *household_share_ids,
            ],
            note=(
                "Explicit cent residual after independently rounding the eleven "
                "department household shares."
            ),
        )
    )
    county_lines.append(
        {
            "id": "BRANT-ALLOC-ROUNDING",
            "label": "Allocation rounding",
            "amountCad": residual,
            "classification": "reconciling_item",
            "evidenceStatus": "RECONCILING",
            "sourceFactId": "DRV-BRANT-ALLOCATION-ROUNDING-391K",
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

gaps: list[dict] = []
findings: list[dict] = []

SHARE_MUN = round(RATE_MUNICIPAL / RATE_TOTAL, 12)
SHARE_HOSP = round(RATE_HOSPITAL / RATE_TOTAL, 12)
SHARE_EDU = round(RATE_EDUCATION / RATE_TOTAL, 12)
IMPLIED_5000 = round(5000 / RATE_TOTAL)

derived_rows.extend(
    [
        derived(
            id="DRV-BRANT-IMPLIED-ASSESSMENT-5000",
            label="Assessment implied by the $5,000 RT scenario",
            amountCad=IMPLIED_5000,
            formula="5000 / BRANT-TAXRATE-RES-TOTAL-2026",
            inputs=["BRANT-TAXRATE-RES-TOTAL-2026"],
            parameters={"scenarioBillCad": 5000},
            note="Scenario parameter divided by the final published RT total rate.",
        ),
        derived(
            id="DRV-BRANT-SHARE-MUNICIPAL-2026",
            label="Municipal share of the RT total rate",
            value=SHARE_MUN,
            formula=(
                "BRANT-TAXRATE-RES-MUNICIPAL-2026 / "
                "BRANT-TAXRATE-RES-TOTAL-2026"
            ),
            inputs=[
                "BRANT-TAXRATE-RES-MUNICIPAL-2026",
                "BRANT-TAXRATE-RES-TOTAL-2026",
            ],
        ),
        derived(
            id="DRV-BRANT-SHARE-HOSPITAL-2026",
            label="Hospital special levy share of the RT total rate",
            value=SHARE_HOSP,
            formula=(
                "BRANT-TAXRATE-RES-HOSPITAL-2026 / "
                "BRANT-TAXRATE-RES-TOTAL-2026"
            ),
            inputs=[
                "BRANT-TAXRATE-RES-HOSPITAL-2026",
                "BRANT-TAXRATE-RES-TOTAL-2026",
            ],
        ),
        derived(
            id="DRV-BRANT-SHARE-EDUCATION-2026",
            label="Education share of the RT total rate",
            value=SHARE_EDU,
            formula=(
                "BRANT-TAXRATE-RES-EDUCATION-2026 / "
                "BRANT-TAXRATE-RES-TOTAL-2026"
            ),
            inputs=[
                "BRANT-TAXRATE-RES-EDUCATION-2026",
                "BRANT-TAXRATE-RES-TOTAL-2026",
            ],
        ),
    ]
)

assert round(SHARE_MUN + SHARE_HOSP + SHARE_EDU, 12) == 1

PUBLISHER = {
    "name": "What in the Tax? project",
    "role": "Independent project publisher; not the County of Brant",
    "repositoryUrl": "https://github.com/Jstn-1g/what-in-the-tax",
}

LICENSE = {
    "spdx": "MIT",
    "scope": "Project-authored receipt and evidence metadata only",
    "sourceDocuments": (
        "Official source documents are not relicensed; see each source's "
        "licence metadata"
    ),
}

CORRECTIONS_ROUTE = {
    "type": "required-before-publication",
    "url": None,
    "status": "pending-public-contact-channel",
}

PUBLICATION_APPROVAL = {
    "status": "pending-named-human-approval",
    "approvedBy": None,
    "approvedAt": None,
}

COVERAGE = {
    "status": "complete-for-declared-tier-0-scope",
    "tier": 0,
    "fiscalYear": 2026,
    "currency": "CAD",
    "geography": "County of Brant, including Paris",
    "assessmentClass": "RT Residential",
    "included": [
        "County municipal rate",
        "hospital special levy",
        "education rate",
        "eleven-department pro-rata municipal allocation",
    ],
    "excluded": [
        "parcel-specific adjustments and rebates",
        "non-RT classes and special-area charges",
        "water/wastewater and other user fees",
        "peer comparisons, findings, and judgments",
    ],
    "sourceCoverage": {
        "receiptDrivingSources": len(sources),
        "reviewedSourceAndExtractPairs": len(sources),
        "citedFacts": len(facts),
        "citationAuditExpected": {
            "verbatim": 18,
            "normalized": 2,
            "hardFailures": 0,
            "bindingIssues": 0,
        },
    },
    "findingsCount": 0,
    "openGapsCount": 0,
}

ledger = {
    "schemaVersion": "2.0.0",
    "artifact": "EvidenceLedger",
    "fiscalYear": 2026,
    "currency": "CAD",
    "publisher": PUBLISHER,
    "license": LICENSE,
    "correctionsRoute": CORRECTIONS_ROUTE,
    "publicationApproval": PUBLICATION_APPROVAL,
    "coverage": COVERAGE,
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
            "Tier 0 carries no findings, judgments, or open evidence gaps.",
        ]
    },
    "sources": sources,
    "facts": facts,
    "derived": derived_rows,
    "gaps": gaps,
    "closedGaps": [],
    "reconciliations": [
        {
            "id": "REC-BRANT-DEPARTMENT-CONTROL-2026",
            "status": "exact",
            "derivedId": "DRV-BRANT-ALLOCATION-BASE-2026",
            "controlFactId": "BRANT-LEVY-2026",
            "amountCad": LEVY_2026,
            "note": (
                "The eleven department net requirements sum exactly to the "
                "approved $92,457,575 net levy."
            ),
        },
        {
            "id": "REC-BRANT-RT-RATE-CONTROL-2026",
            "status": "exact",
            "derivedId": "DRV-BRANT-RATE-TOTAL-CHECK-2026",
            "controlFactId": "BRANT-TAXRATE-RES-TOTAL-2026",
            "value": RATE_TOTAL,
            "note": (
                "Municipal, hospital, and education rates sum exactly to the "
                "published RT total rate."
            ),
        },
        {
            "id": "REC-BRANT-BUDGET-ILLUSTRATION-2026",
            "status": "explained-difference",
            "derivedId": "DRV-BRANT-ILLUSTRATION-DELTA-391K",
            "controlFactId": "BRANT-ILLUSTRATED-COUNTY-BILL-2026",
            "amountCad": ILLUSTRATION_DELTA,
            "selectedBasis": "final-2026-tax-rate-schedule",
            "note": (
                "The approved-budget illustration is $0.02 above the final "
                "rate-derived County amount. Both values remain cited; this "
                "receipt uses the final rate schedule and does not infer a cause."
            ),
        },
    ],
}

receipt = {
    "schemaVersion": "2.0.0",
    "artifact": "TaxpayerReceipt",
    "fiscalYear": 2026,
    "currency": "CAD",
    "status": "partial_evidence_based",
    "publisher": PUBLISHER,
    "license": LICENSE,
    "correctionsRoute": CORRECTIONS_ROUTE,
    "publicationApproval": PUBLICATION_APPROVAL,
    "coverage": COVERAGE,
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
                "sourceFactId": "DRV-BRANT-BILL-COUNTY-391K",
                "citedFactIds": [
                    "DRV-BRANT-ILLUSTRATION-DELTA-391K",
                ],
                "lineItems": county_lines,
                "uiLabel": "County portion",
                "note": (
                    f"Rate-derived municipal+hospital ${COUNTY_PLUS_HOSPITAL:,.2f}; "
                    f"the approved-budget illustration prints "
                    f"${ILLUSTRATED_COUNTY_BILL:,.2f}, a cited $0.02 difference. "
                    "The receipt uses the final tax-rate schedule."
                ),
            },
            "region": {
                "basis": "Not applicable — County of Brant is single-tier (no upper-tier Region)",
                "amountCad": None,
                "evidenceStatus": "NOT_APPLICABLE",
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
            "sourceFactId": "DRV-BRANT-BILL-COMBINED-391K",
            # The bill as a list of bodies with declared roles. Brant is the
            # case that proves why the three fixed slots had to go: it is
            # single-tier, so there is no upper tier to put in the middle slot,
            # and it charges a hospital special levy that had nowhere to go and
            # was being folded into the municipal portion. Both are now what
            # they are - two roles, plus a declared absence.
            #
            # Roles are stated here rather than inferred downstream, because a
            # reader of the artifact cannot recover them: the labels are the
            # only clue and this receipt's own disclaimer forbids using display
            # names to guess a role.
            "taxingBodies": [
                {
                    "id": "brant-county",
                    "role": "local",
                    "label": "County of Brant",
                    "order": 0,
                    "amountCad": MUNICIPAL_PORTION,
                    "basis": "County of Brant 2026 Tax Rates — CODE RT Residential, municipal rate",
                    "evidenceStatus": "DERIVED",
                    "assessmentCad": MEDIAN_ASSESSMENT,
                    "sourceFactId": "DRV-BRANT-BILL-MUNICIPAL-391K",
                },
                {
                    "id": "brant-hospital",
                    "role": "special-area",
                    "label": "Hospital special levy",
                    "order": 1,
                    "amountCad": HOSPITAL_PORTION,
                    "basis": "County of Brant 2026 Tax Rates — CODE RT Residential, hospital levy rate",
                    "evidenceStatus": "DERIVED",
                    "assessmentCad": MEDIAN_ASSESSMENT,
                    "sourceFactId": "DRV-BRANT-BILL-HOSPITAL-391K",
                    "note": (
                        "A separate levy on the same assessment, shown on its own line rather "
                        "than inside the County portion."
                    ),
                },
                {
                    "id": "brant-education",
                    "role": "education",
                    "label": "Education (Province of Ontario)",
                    "order": 2,
                    "amountCad": EDUCATION_PORTION,
                    "basis": "County of Brant 2026 Tax Rates — CODE RT Residential education rate",
                    "evidenceStatus": "DERIVED",
                    "assessmentCad": MEDIAN_ASSESSMENT,
                    "sourceFactId": "DRV-BRANT-BILL-EDUCATION-391K",
                },
            ],
            "inapplicableBodies": [
                {
                    "role": "upper-tier",
                    "reason": (
                        "County of Brant is a single-tier municipality. There is no upper tier "
                        "to levy a share, which is a fact about the jurisdiction rather than "
                        "evidence we are missing."
                    ),
                },
            ],
            "combinedAtAssessment": {
                "assessmentCad": MEDIAN_ASSESSMENT,
                "basis": "County of Brant 2026 Tax Rates — CODE RT Residential",
                "evidenceStatus": "DERIVED",
                "sourceFactId": "DRV-BRANT-BILL-COMBINED-391K",
                "citedFactIds": [
                    "DRV-BRANT-RATE-TOTAL-CHECK-2026",
                ],
                "components": [
                    {
                        "label": "County of Brant (municipal)",
                        "amountCad": MUNICIPAL_PORTION,
                        "rate": RATE_MUNICIPAL,
                        "sourceFactId": "DRV-BRANT-BILL-MUNICIPAL-391K",
                    },
                    {
                        "label": "Hospital special levy",
                        "amountCad": HOSPITAL_PORTION,
                        "rate": RATE_HOSPITAL,
                        "sourceFactId": "DRV-BRANT-BILL-HOSPITAL-391K",
                    },
                    {
                        "label": "Education (Province of Ontario)",
                        "amountCad": EDUCATION_PORTION,
                        "rate": RATE_EDUCATION,
                        "sourceFactId": "DRV-BRANT-BILL-EDUCATION-391K",
                    },
                ],
                "totalCad": COMBINED_TOTAL,
                "totalRate": RATE_TOTAL,
            },
            "combinedTotalNote": (
                f"Built from the 2026 Tax Rates RT row applied to the County's published median "
                f"assessment (${MEDIAN_ASSESSMENT:,}). Municipal + hospital = ${COUNTY_PLUS_HOSPITAL:,.2f}, "
                f"while the approved budget's illustrated residential impact is "
                f"${ILLUSTRATED_COUNTY_BILL:,.2f} (a cited $0.02 presentation "
                f"difference; education excluded). Full bill including education "
                f"is ${COMBINED_TOTAL:,.2f}."
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
            "sourceFactId": "DRV-BRANT-IMPLIED-ASSESSMENT-5000",
            "compositionShares": [
                {
                    "label": "County of Brant (municipal)",
                    "share": SHARE_MUN,
                    "sourceFactId": "DRV-BRANT-SHARE-MUNICIPAL-2026",
                },
                {
                    "label": "Hospital special levy",
                    "share": SHARE_HOSP,
                    "sourceFactId": "DRV-BRANT-SHARE-HOSPITAL-2026",
                },
                {
                    "label": "Education (Province of Ontario)",
                    "share": SHARE_EDU,
                    "sourceFactId": "DRV-BRANT-SHARE-EDUCATION-2026",
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
        "showGapsAsFirstClassUi": False,
        "forbidFillerAllocation": True,
        "publishedFindingIds": [],
        "marqueeFindings": [],
        "municipalBucketLabel": "County portion",
        "regionBucketLabel": "Upper-tier (n/a)",
        "heroLabel": "Total residential bill · median · 2026 tax rates",
    },
}


def collect_receipt_evidence_ids(value) -> set[str]:
    references: set[str] = set()
    if isinstance(value, list):
        for child in value:
            references.update(collect_receipt_evidence_ids(child))
    elif isinstance(value, dict):
        source_fact_id = value.get("sourceFactId")
        if isinstance(source_fact_id, str):
            references.add(source_fact_id)
        for cited_id in value.get("citedFactIds", []) or []:
            if isinstance(cited_id, str):
                references.add(cited_id)
        for child in value.values():
            references.update(collect_receipt_evidence_ids(child))
    return references


facts_by_id = {item["id"]: item for item in facts}
derived_by_id = {item["id"]: item for item in derived_rows}
load_bearing_ids = collect_receipt_evidence_ids(receipt)
pending_ids = list(load_bearing_ids)
while pending_ids:
    evidence_id = pending_ids.pop()
    node = derived_by_id.get(evidence_id)
    if not node:
        continue
    for input_id in node["inputs"]:
        if input_id not in load_bearing_ids:
            load_bearing_ids.add(input_id)
            pending_ids.append(input_id)

load_bearing_fact_ids = load_bearing_ids & set(facts_by_id)
assert load_bearing_fact_ids == set(facts_by_id)
assert len(facts) == 20
assert not gaps
assert not findings
assert receipt["findings"] == []
assert round(sum(item["amountCad"] for item in county_lines), 2) == COUNTY_PLUS_HOSPITAL
assert (
    round(
        sum(
            item["amountCad"]
            for item in receipt["profiles"]["supportedAverageHousehold"][
                "combinedAtAssessment"
            ]["components"]
        ),
        2,
    )
    == COMBINED_TOTAL
)
assert all(
    fact_row.get("sourceId")
    and fact_row.get("page")
    and fact_row.get("excerpt")
    for fact_row in facts
)
COVERAGE["sourceCoverage"]["loadBearingFacts"] = len(load_bearing_fact_ids)

for target in (DATA, WEB_DATA):
    (target / "evidence-ledger.json").write_text(
        json.dumps(ledger, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    (target / "taxpayer-receipt.json").write_text(
        json.dumps(receipt, indent=2) + "\n", encoding="utf-8", newline="\n"
    )

print("facts", len(facts))
print("derived", len(derived_rows))
print("gaps", len(gaps))
print("findings", len(findings))
print("municipal", MUNICIPAL_PORTION, "hospital", HOSPITAL_PORTION, "edu", EDUCATION_PORTION)
print("combined", COMBINED_TOTAL, "county+hosp", COUNTY_PLUS_HOSPITAL)
print("county lines sum", round(sum(x["amountCad"] for x in county_lines), 2))
print("wrote", DATA)
