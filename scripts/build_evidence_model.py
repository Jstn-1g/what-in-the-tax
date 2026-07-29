"""Build evidence-first ledger + honest taxpayer receipt prototype.

Rules:
- FACT: quoted from source with page + amount
- DERIVED: computed only from FACT ids with explicit formula
- GAP: missing evidence — never invent amounts
- JUDGMENT: interpretive finding; may cite facts but billImpactCad is null unless formula exists
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
import sys

sys.path.insert(0, str(ROOT / "scripts"))

from lib.taxing_bodies import build_taxing_bodies  # noqa: E402
DATA = ROOT / "data"

# web/src/types.ts declares both of these required on TaxpayerReceipt, and
# publicPackSchema.ts cross-checks coverage.fiscalYear against receipt.fiscalYear.
# The builder had stopped emitting them, so a rebuild silently produced an
# artifact that violates the project's own schema while the checked-in copy
# still had the fields. Named here rather than inlined so the year has one home.
FISCAL_YEAR = 2026
CURRENCY = "CAD"


class EvidenceModelError(RuntimeError):
    """A build invariant failed.

    These were bare `assert`s. Python strips assert statements under -O, so the
    checks that decide whether a published receipt is arithmetically honest could
    be silently removed by a flag nobody in this repo sets deliberately. They are
    real exceptions now.
    """


def write_bytes_atomic(path: Path, payload: bytes) -> None:
    """Write via a temp file in the same directory, then replace.

    write_text truncates the destination before it writes. An interrupt midway
    leaves a short file that still parses as JSON often enough to be dangerous,
    and the UI mirror reads whatever is on disk. os.replace is atomic within a
    filesystem, so a reader sees either the old artifact or the new one.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, tmp_name = tempfile.mkstemp(
        dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp"
    )
    tmp = Path(tmp_name)
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def fact(**kwargs):
    kwargs.setdefault("kind", "FACT")
    return kwargs


def gap(**kwargs):
    kwargs.setdefault("kind", "GAP")
    return kwargs


def derived(**kwargs):
    kwargs.setdefault("kind", "DERIVED")
    return kwargs


# --- Region rural household table (shared pack YAML; Region Budget Book p.12) ---
# Rural column = Wellesley + North Dumfries; assessment $354,500 (2016 CVA)
REGION_SCHEDULE_PATH = (
    ROOT / "corpus" / "region-of-waterloo-on" / "schedules" / "household-tax-supported-2026.yaml"
)


def _load_region_rural_hh() -> list[tuple[str, int, int, int]]:
    """Load rural HH lines from shared YAML. Amounts must stay identical to sealed ND."""
    try:
        import yaml
    except ImportError as exc:  # pragma: no cover
        raise SystemExit("PyYAML required (pip install pyyaml)") from exc
    if not REGION_SCHEDULE_PATH.exists():
        raise SystemExit(
            f"missing {REGION_SCHEDULE_PATH}\n"
            "Run: python scripts/parse_row_household_schedule.py\n"
            "ND rebuild is optional after YAML exists; sealed artifacts stay until rebuild."
        )
    doc = yaml.safe_load(REGION_SCHEDULE_PATH.read_text(encoding="utf-8"))
    rural = doc["areas"]["rural"]
    rows: list[tuple[str, int, int, int]] = []
    for line in rural["lines"]:
        rows.append(
            (
                line["label"],
                int(line["amountCad"]),
                int(line["netExpenditure000Cad"]) * 1000,
                int(line["propertyTaxLevy000Cad"]) * 1000,
            )
        )
    return rows


REGION_RURAL_HH = _load_region_rural_hh()

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
        excerpt="Residential Township Tax Rate 0.00315303",
        status="draft",
        note="Matches final RT Township Rate in By-law 3637-26 Schedule A (see ND-TAXRATE-RES-TOWNSHIP-2026-FINAL).",
    ),
    fact(
        id="ND-LEVY-2026-ADOPTED",
        sourceId="nd-2026-budget-minutes",
        page=5,
        label="North Dumfries 2026 adopted municipal tax levy (By-law 3617-26)",
        amountCad=9_002_499,
        excerpt="By-law No. 3617-26, being a By-law to approve the Township of North Dumfries 2026 Budget with a tax levy of $9,002,499 plus$ 160,117 for the Ayr Special Area levy",
        status="approved",
    ),
    fact(
        id="ND-TAXRATE-RES-TOWNSHIP-2026-FINAL",
        sourceId="nd-2026-tax-rate-bylaw",
        page=103,
        label="2026 final residential township tax rate (RT)",
        value=0.00315303,
        excerpt="RT Residential     0.00315303 0.00717545 0.00153000 0.01185848",
        status="final",
        note="Schedule 'A' to By-law 3637-26 — Township Rate column for CODE RT Residential.",
    ),
    fact(
        id="ND-TAXRATE-RES-REGION-2026-FINAL",
        sourceId="nd-2026-tax-rate-bylaw",
        page=103,
        label="2026 final residential Region tax rate (RT)",
        value=0.00717545,
        excerpt="RT Residential     0.00315303 0.00717545 0.00153000 0.01185848",
        status="final",
        note="Schedule 'A' to By-law 3637-26 — Regional Rate column for CODE RT Residential.",
    ),
    fact(
        id="ND-TAXRATE-RES-EDUCATION-2026-FINAL",
        sourceId="nd-2026-tax-rate-bylaw",
        page=103,
        label="2026 final residential education tax rate (RT)",
        value=0.00153000,
        excerpt="RT Residential     0.00315303 0.00717545 0.00153000 0.01185848",
        status="final",
        note="Schedule 'A' to By-law 3637-26 — Education Rate column for CODE RT Residential.",
    ),
    fact(
        id="ND-TAXRATE-RES-AYR-SAR-2026-FINAL",
        sourceId="nd-2026-tax-rate-bylaw",
        page=103,
        label="2026 final Ayr Special Area Rate, residential (RT)",
        value=0.00015571,
        excerpt="RT Residential  0.00315303 0.00717545 0.00153000 0.01185848 0.00015571 0.01201419",
        status="final",
        note="Ayr S.A.R. column, CODE RT. Applies to the Ayr urban service area only; rural North Dumfries properties do not pay it.",
    ),
    fact(
        id="ND-TAXRATE-RES-TOTAL-2026-FINAL",
        sourceId="nd-2026-tax-rate-bylaw",
        page=103,
        label="2026 final total residential tax rate, rural (RT)",
        value=0.01185848,
        excerpt="RT Residential  0.00315303 0.00717545 0.00153000 0.01185848 0.00015571 0.01201419",
        status="final",
        note="Printed Total 2026 Rate column. Independent cross-check: township + region + education must equal this exactly.",
    ),
    fact(
        id="ND-TAXRATE-RES-TOTAL-AYR-2026-FINAL",
        sourceId="nd-2026-tax-rate-bylaw",
        page=103,
        label="2026 final total residential tax rate including Ayr S.A.R. (RT)",
        value=0.01201419,
        excerpt="RT Residential  0.00315303 0.00717545 0.00153000 0.01185848 0.00015571 0.01201419",
        status="final",
        note="Printed Total Ayr Rate column.",
    ),
    fact(
        id="ND-TAXRATE-BYLAW-ADOPTION-2026",
        sourceId="nd-2026-tax-rate-minutes",
        page=6,
        label="Council adopted By-law 3637-26 (2026 final tax rates)",
        excerpt="AND THAT Council adopt By-law No. 3637-26, being a By-law to adopt the 2026 Tax Rates By-law which includes the Township of North Dumfries Municipal Tax Rate for General and Special Area Levy, Region of Waterloo Tax Rates and the Province of Ontario School Board Tax Rates, be enacted. CARRIED",
        status="final",
    ),
    fact(
        id="ND-BUDGET-REQUIREMENT-TAXBYLAW-2026",
        sourceId="nd-2026-tax-rate-bylaw",
        page=101,
        label="Municipal budget requirement stated in By-law 3637-26",
        amountCad=9_002_462,
        excerpt="And Whereas the Municipal Budget requirement for the Township of North Dumfries amounts to $9,002,462 for 2026;",
        status="final",
        note="$37 below adopted levy $9,002,499 in By-law 3617-26; cited for transparency. Allocation base not rebuilt in this step.",
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
        excerpt="Township Taxes Annually 1,434.63$",
        status="draft",
        note="Computed check: 455000 * 0.00315303 = 1434.629 ≈ 1434.63",
    ),
    fact(
        id="ND-TOWNSHIP-TAX-URBAN-AVG-2026",
        sourceId="nd-2026-draft",
        page=8,
        label="2026 draft township taxes — urban average assessment",
        amountCad=1505.47,
        excerpt="Township Taxes Annually 1,505.47$",
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
        note="Conflicts with the p.9 summary schedule figure of $1,607,500 (ND-CAPITAL-FUNDED-BY-LEVY-2026). The p.9 figure is used for the allocation base because it is the figure that balances the published budget to Net Budget 0. Both are recorded; neither is discarded.",
        status="draft",
    ),
    fact(
        id="ND-CAPITAL-FUNDED-BY-LEVY-2026",
        sourceId="nd-2026-draft",
        page=9,
        label="Capital Funded by tax levy and building bill 2026 (summary schedule)",
        amountCad=1_607_500,
        excerpt="Capital Funded by tax levy and building bill ... 1,607,500",
        note="From the p.9 levy summary schedule (PDF index). Used as the capital component of the allocation base. Compare ND-CAPITAL-TAX-RESERVE-XFER-2026 ($1,625,000, p.43 narrative and capital table).",
    ),
    fact(
        id="ND-DEPT-ENVIRONMENTAL-2026",
        sourceId="nd-2026-draft",
        page=9,
        label="TOTAL ENVIRONMENTAL SERVICES 2026 (net credit)",
        amountCad=-225,
        excerpt="TOTAL ENVIRONMENTAL SERVICES ... (225)",
        note="Small net credit. Previously omitted from the allocation base; that omission accounted for $225 of the base discrepancy.",
    ),
    fact(
        id="ND-COUNCIL-2026",
        sourceId="nd-2026-draft",
        page=9,
        label="Total Council 2026",
        amountCad=201_669,
        excerpt="Total Council ... 201,669",
        note="COMPONENT of TOTAL CORPORATE SERVICES, not a sibling of it. Never add to the allocation base separately - that double-counts $238,703 with Elections. Detail schedule also on p.15.",
    ),
    fact(
        id="ND-ELECTIONS-2026",
        sourceId="nd-2026-draft",
        page=9,
        label="Total Elections 2026",
        amountCad=37_034,
        excerpt="Total Elections ... 37,034",
        note="COMPONENT of TOTAL CORPORATE SERVICES. See ND-COUNCIL-2026. Detail schedule also on p.15.",
    ),
    fact(
        id="ND-CORP-SERV-ADMIN-2026",
        sourceId="nd-2026-draft",
        page=9,
        label="Total Corporate Serv Admin 2026",
        amountCad=1_841_803,
        excerpt="Total Corporate Serv Admin ... 1,841,803",
        note="Council 201,669 + Elections 37,034 + this 1,841,803 + Admin Office NDCC 5,300 + Earl Thompson 5,500 = 2,091,306 = TOTAL CORPORATE SERVICES exactly. Detail also on p.18.",
    ),
    fact(
        id="ND-TAXATION-REVENUE-2026",
        sourceId="nd-2026-draft",
        page=9,
        label="Total General Revenue Taxation 2026",
        amountCad=9_182_824,
        excerpt="Total General Revenue Taxation ... (9,182,824)",
        note="Taxation revenue including supplementaries/PILs. NOT the $9,002,499 municipal levy (rate x assessment).",
    ),
    fact(
        id="ND-CORPORATE-REVENUES-2026",
        sourceId="nd-2026-draft",
        page=9,
        label="Total General Corporate Revenues 2026",
        amountCad=866_800,
        excerpt="Total General Corporate Revenues ... (866,800)",
        note="Non-tax revenue. Part of what funds the expenditure base, which is why the base exceeds the levy.",
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
        excerpt="new debt financing proposed [$5 million] to finance the Twin Pad Project",
        status="draft",
    ),
    fact(
        id="ND-CAP-ACC-EXTERIOR-2026",
        sourceId="nd-2026-draft",
        page=52,
        label="Ayr Community Centre major exterior rehabilitation",
        amountCad=3_500_000,
        excerpt="The projected cost for this work program is $3,500,000.",
        status="draft",
    ),
    fact(
        id="ND-CAP-PUMPTRACK-2026",
        sourceId="nd-2026-draft",
        page=54,
        label="Pump Track at Jim Schmidt Memorial Park",
        amountCad=568_756,
        excerpt="The project has an estimated value of $568,756",
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
        page=46,
        label="Broadband Enhancement Strategy Phase 1",
        amountCad=150_000,
        excerpt="project is estimated at $150,000 with funding through the Broadband Reserve Account",
        status="draft",
    ),
    fact(
        id="ND-CAP-OFFICIAL-PLAN-2026",
        sourceId="nd-2026-draft",
        page=47,
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
        page=16,
        label="Tax-funded community grants 2026",
        amountCad=40_000,
        excerpt="The 2026 tax funded community grants are $40,000",
        status="draft",
    ),
    fact(
        id="ND-GRANT-AYR-CEMETERY-2026",
        sourceId="nd-2026-draft",
        page=16,
        label="Ayr Cemetery grant",
        amountCad=10_000,
        excerpt="allocations to the Ayr Cemetery, in the amount of $10,000",
        status="draft",
    ),
    fact(
        id="ND-GRANT-SHEFFIELD-LIONS-2026",
        sourceId="nd-2026-draft",
        page=16,
        label="Sheffield Lions / Scott Women’s Institute Building",
        amountCad=3_500,
        excerpt="$3,500 to the Sheffield Lions Club for the maintenance of the Scott Women’s Institute Building",
        status="draft",
    ),
    fact(
        id="ND-RECORDS-MGMT-2026",
        sourceId="nd-2026-draft",
        page=18,
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
        excerpt="Planning - W. Region Ec. Dev. Comm. (WREDC) 20,000",
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
        id="ND-POP-STATCAN-2025",
        sourceId="statcan-csd-estimates",
        page=None,
        label="North Dumfries population estimate (StatCan, July 1, 2025)",
        value=13_051,
        excerpt="2025,North Dumfries (TP), Ontario,2021A00053530004,...,13051",
        status="external",
        url="https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=1710015501",
        note="Table 17-10-0155-01. Postcensal estimate adjusted for net undercoverage; not the unadjusted Census count.",
    ),
    fact(
        id="ND-POP-STATCAN-2023",
        sourceId="statcan-csd-estimates",
        page=None,
        label="North Dumfries population estimate (StatCan, July 1, 2023)",
        value=12_047,
        excerpt="2023,North Dumfries (TP), Ontario,2021A00053530004,...,12047",
        status="external",
        url="https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=1710015501",
    ),
    fact(
        id="FIR-GG-ND-2023",
        sourceId="mmah-fir-2023",
        page=None,
        label="FIR 2023 General government — Total Expenses Before Adjustments (North Dumfries)",
        amountCad=1_933_805,
        excerpt="2023,3001,North Dumfries Tp,...,General government,Total Expenses Before Adjustments,slc.40X.L0299.C01.07,1933805",
        status="external",
        url="https://efis.fma.csc.gov.on.ca/fir/MultiYearReport/fir_data_2023.zip",
        note="Schedule 40 Consolidated Statement of Operations: Expenses. Before Adjustments avoids peer differences in program-support allocation.",
    ),
    fact(
        id="FIR-GG-WELLESLEY-2023",
        sourceId="mmah-fir-2023",
        page=None,
        label="FIR 2023 General government — Total Expenses Before Adjustments (Wellesley)",
        amountCad=2_104_106,
        excerpt="2023,3024,Wellesley Tp,...,General government,Total Expenses Before Adjustments,slc.40X.L0299.C01.07,2104106",
        status="external",
        url="https://efis.fma.csc.gov.on.ca/fir/MultiYearReport/fir_data_2023.zip",
    ),
    fact(
        id="FIR-GG-WILMOT-2023",
        sourceId="mmah-fir-2023",
        page=None,
        label="FIR 2023 General government — Total Expenses Before Adjustments (Wilmot)",
        amountCad=4_008_877,
        excerpt="2023,3018,Wilmot Tp,...,General government,Total Expenses Before Adjustments,slc.40X.L0299.C01.07,4008877",
        status="external",
        url="https://efis.fma.csc.gov.on.ca/fir/MultiYearReport/fir_data_2023.zip",
    ),
    fact(
        id="FIR-GG-WOOLWICH-2023",
        sourceId="mmah-fir-2023",
        page=None,
        label="FIR 2023 General government — Total Expenses Before Adjustments (Woolwich)",
        amountCad=4_153_213,
        excerpt="2023,3029,Woolwich Tp,...,General government,Total Expenses Before Adjustments,slc.40X.L0299.C01.07,4153213",
        status="external",
        url="https://efis.fma.csc.gov.on.ca/fir/MultiYearReport/fir_data_2023.zip",
    ),
    fact(
        id="STATCAN-POP-WELLESLEY-2023",
        sourceId="statcan-csd-estimates",
        page=None,
        label="Wellesley population estimate (StatCan, July 1, 2023)",
        value=12_253,
        excerpt="2023,Wellesley (TP), Ontario,...,12253",
        status="external",
        url="https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=1710015501",
    ),
    fact(
        id="STATCAN-POP-WILMOT-2023",
        sourceId="statcan-csd-estimates",
        page=None,
        label="Wilmot population estimate (StatCan, July 1, 2023)",
        value=23_244,
        excerpt="2023,Wilmot (TP), Ontario,...,23244",
        status="external",
        url="https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=1710015501",
    ),
    fact(
        id="STATCAN-POP-WOOLWICH-2023",
        sourceId="statcan-csd-estimates",
        page=None,
        label="Woolwich population estimate (StatCan, July 1, 2023)",
        value=30_909,
        excerpt="2023,Woolwich (TP), Ontario,...,30909",
        status="external",
        url="https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=1710015501",
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
        excerpt="Tax Supported Regional Services $2,984 $2,984 $2,984 $2,543",
        status="approved",
        assessmentBasisCad=354_500,
        note="Rural column explicitly includes Wellesley and North Dumfries.",
    ),
    fact(
        # The last unbound value in the corpus. The receipt's -$78 PIL line
        # cited ROW-RURAL-HH-TOTAL-2026 ($2,543) - the total it helps reconcile,
        # not itself - so nothing could compare the printed number to anything.
        # The figure is printed on the same page 12: the rural household column
        # shows ($78) against "Less: Payments in Lieu & Supplementary Taxes(3)",
        # between the $2,621 subtotal and the $2,543 Regional Tax Levy row.
        id="ROW-PIL-SUPP-REDUCTION-2026",
        sourceId="row-2026-book",
        page=12,
        label="Less: Payments in Lieu & Supplementary Taxes, rural household share",
        amountCad=-78,
        excerpt="($78)",  # the printed rural-column cell; the label sits in a split column - see note
        status="approved",
        assessmentBasisCad=354_500,
        note="Rural column: $2,621 subtotal less ($78) PIL/supplementary equals the $2,543 Regional Tax Levy.",
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
        excerpt="This amounts to $142 for an average property, or $12 per month.",
        status="summary",
    ),
]

# Region rural household service lines as facts (amounts from shared YAML schedule)
def _row_book_page12_line(label: str, hh: int) -> str | None:
    """The literal page-12 line for a service row, if one carries both the
    label and the household dollar figure.

    The template excerpt "<label> ... Rural $N" was a reconstruction, and it
    cost tiers it did not need to: row_bound checks the excerpt's own words
    against the page line, and "Rural" is a column heading that never appears
    on the data row - so rows like Airport and Finance graded numbers-only
    while quoting a page that states them plainly. Quote the page instead;
    fall back to the reconstruction only when no single line carries both.
    """
    text = (ROOT / "data/_extracts/2026_final_budget_book_region.txt").read_text(
        encoding="utf-8", errors="replace"
    )
    parts = re.split(r"(?m)^=====\s*PAGE\s*(\d+)\s*=====\s*$", text)
    page12 = {int(parts[j]): parts[j + 1] for j in range(1, len(parts), 2)}[12]
    for line in page12.splitlines():
        if label in line and (f"${hh:,}" in line or f"${hh}" in line):
            return line.strip()
    return None


for i, (label, hh, net_exp, levy) in enumerate(REGION_RURAL_HH, start=1):
    verbatim_line = _row_book_page12_line(label, hh)
    facts.append(
        fact(
            id=f"ROW-RURAL-HH-{i:02d}",
            sourceId="row-2026-book",
            page=12,
            label=f"Rural household — {label}",
            amountCad=hh,
            regionalNetExpenditure000s=net_exp // 1000,
            regionalPropertyTaxLevy000s=levy // 1000,
            excerpt=verbatim_line or f"{label} ... Rural ${hh}",
            status="approved",
            assessmentBasisCad=354_500,
            note="Source: corpus/region-of-waterloo-on/schedules/household-tax-supported-2026.yaml rural area.",
        )
    )

# Derived
dept_ids = [
    "ND-DEPT-CORPORATE-2026",
    "ND-DEPT-PROTECTIVE-2026",
    "ND-DEPT-PW-2026",
    "ND-DEPT-ENVIRONMENTAL-2026",
    "ND-DEPT-REC-2026",
    "ND-DEPT-PLANNING-2026",
    "ND-CAPITAL-FUNDED-BY-LEVY-2026",
]
dept_amounts = {f["id"]: f["amountCad"] for f in facts if f["id"] in dept_ids}
dept_sum = sum(dept_amounts.values())
_by_id = {f["id"]: f.get("amountCad") for f in facts}
REVENUE_TOTAL = _by_id["ND-TAXATION-REVENUE-2026"] + _by_id["ND-CORPORATE-REVENUES-2026"]
if dept_sum != REVENUE_TOTAL:
    raise EvidenceModelError(
        f"allocation base {dept_sum} does not tie to published revenues {REVENUE_TOTAL}"
    )
GOVERNANCE_SUBLINE = round(1434.63 * (_by_id["ND-COUNCIL-2026"] + _by_id["ND-ELECTIONS-2026"]) / dept_sum, 2)

township_avg = 1434.63

# --- Combined household bill from By-law 3637-26 Schedule A (agenda p.103) ---
_val = {f["id"]: f.get("value") for f in facts}
RATE_TWP = _val["ND-TAXRATE-RES-TOWNSHIP-2026-FINAL"]
RATE_REG = _val["ND-TAXRATE-RES-REGION-2026-FINAL"]
RATE_EDU = _val["ND-TAXRATE-RES-EDUCATION-2026-FINAL"]
RATE_SAR = _val["ND-TAXRATE-RES-AYR-SAR-2026-FINAL"]
RATE_TOTAL = _val["ND-TAXRATE-RES-TOTAL-2026-FINAL"]
RATE_TOTAL_AYR = _val["ND-TAXRATE-RES-TOTAL-AYR-2026-FINAL"]
ASSESSMENT = 455_000

# The published rate columns must be internally consistent before we bill anything off them.
if abs((RATE_TWP + RATE_REG + RATE_EDU) - RATE_TOTAL) >= 1e-12:
    raise EvidenceModelError(
        f"rate columns {RATE_TWP} + {RATE_REG} + {RATE_EDU} do not sum to the "
        f"printed total {RATE_TOTAL}"
    )
if abs((RATE_TOTAL + RATE_SAR) - RATE_TOTAL_AYR) >= 1e-12:
    raise EvidenceModelError(
        f"Ayr total {RATE_TOTAL_AYR} is not total {RATE_TOTAL} + SAR {RATE_SAR}"
    )

BILL_TWP = round(RATE_TWP * ASSESSMENT, 2)
BILL_REG = round(RATE_REG * ASSESSMENT, 2)
BILL_EDU = round(RATE_EDU * ASSESSMENT, 2)
BILL_SAR = round(RATE_SAR * ASSESSMENT, 2)
BILL_COMBINED = round(BILL_TWP + BILL_REG + BILL_EDU, 2)
BILL_COMBINED_AYR = round(BILL_COMBINED + BILL_SAR, 2)
IMPLIED_5000_CVA = round(5000 / RATE_TOTAL)
SHARE_TWP = round(RATE_TWP / RATE_TOTAL, 6)
SHARE_REG = round(RATE_REG / RATE_TOTAL, 6)
SHARE_EDU = round(RATE_EDU / RATE_TOTAL, 6)

# The township component derived from the final rate must reproduce the separately cited
# $1,434.63 to the cent, or one of the two figures is wrong.
if BILL_TWP != township_avg:
    raise EvidenceModelError(
        f"township rate x assessment {BILL_TWP:.2f} does not equal the separately "
        f"cited {township_avg:.2f}; one of the two figures is wrong"
    )
if abs(BILL_COMBINED - round(RATE_TOTAL * ASSESSMENT, 2)) >= 0.02:
    raise EvidenceModelError(
        f"components sum to {BILL_COMBINED:.2f} but the total rate gives "
        f"{round(RATE_TOTAL * ASSESSMENT, 2):.2f}"
    )

derived_rows = [
    derived(
        id="DRV-ND-DEPT-SUM",
        label="Sum of township draft dept nets used for allocation base",
        amountCad=dept_sum,
        formula=" + ".join(dept_ids),
        inputs=dept_ids,
        note="Ties to the p.7 summary schedule. NOT the $9,002,499 municipal levy: the base is funded by taxation ($9,182,824) plus non-tax corporate revenues ($866,800).",
    ),
    derived(
        id="DRV-ND-BASE-TIES-TO-REVENUES",
        label="Expenditure base reconciles to published revenues (Net Budget 0)",
        amountCad=REVENUE_TOTAL - dept_sum,
        formula="(ND-TAXATION-REVENUE-2026 + ND-CORPORATE-REVENUES-2026) - DRV-ND-DEPT-SUM",
        inputs=["ND-TAXATION-REVENUE-2026", "ND-CORPORATE-REVENUES-2026", "DRV-ND-DEPT-SUM"],
        note="Must be 0. Taxation 9,182,824 + corporate revenues 866,800 = 10,049,624 = the expenditure base.",
    ),
    derived(
        id="DRV-ND-GOVERNANCE-SUBLINE",
        label="Council + Elections share of the rural average township bill (disclosure only)",
        amountCad=GOVERNANCE_SUBLINE,
        formula="1434.63 * ((ND-COUNCIL-2026 + ND-ELECTIONS-2026) / DRV-ND-DEPT-SUM)",
        inputs=["ND-TOWNSHIP-TAX-RURAL-AVG-2026", "ND-COUNCIL-2026", "ND-ELECTIONS-2026", "DRV-ND-DEPT-SUM"],
        note="Discloses governance cost already contained inside Corporate Services. Nested sub-line only; NOT a base component and not added to any total.",
    ),
    derived(
        id="DRV-ND-BILL-TOWNSHIP-455K",
        label="Township portion of a $455,000 residential bill",
        amountCad=BILL_TWP,
        formula="ND-TAXRATE-RES-TOWNSHIP-2026-FINAL * 455000",
        inputs=["ND-TAXRATE-RES-TOWNSHIP-2026-FINAL"],
        note="Reproduces the separately cited ND-TOWNSHIP-TAX-RURAL-AVG-2026 figure of $1,434.63 to the cent.",
    ),
    derived(
        id="DRV-ND-BILL-REGION-455K",
        label="Region portion of a $455,000 residential bill",
        amountCad=BILL_REG,
        formula="ND-TAXRATE-RES-REGION-2026-FINAL * 455000",
        inputs=["ND-TAXRATE-RES-REGION-2026-FINAL"],
        note="Supersedes reading the Region household table at its own $354,500 average. Same 2016 MPAC base; this applies the actual by-law rate to the North Dumfries average property.",
    ),
    derived(
        id="DRV-ND-BILL-EDUCATION-455K",
        label="Education portion of a $455,000 residential bill",
        amountCad=BILL_EDU,
        formula="ND-TAXRATE-RES-EDUCATION-2026-FINAL * 455000",
        inputs=["ND-TAXRATE-RES-EDUCATION-2026-FINAL"],
        note="Province sets this rate under O. Reg. 400/98; the Township only collects it.",
    ),
    derived(
        id="DRV-ND-BILL-AYR-SAR-455K",
        label="Ayr Special Area Rate on a $455,000 bill (Ayr urban only)",
        amountCad=BILL_SAR,
        formula="ND-TAXRATE-RES-AYR-SAR-2026-FINAL * 455000",
        inputs=["ND-TAXRATE-RES-AYR-SAR-2026-FINAL"],
        note="Rural properties do not pay this. Township rate + SAR reproduces the draft binder urban figure of $1,505.47.",
    ),
    derived(
        id="DRV-ND-BILL-COMBINED-455K",
        label="Total 2026 residential bill at $455,000 (rural)",
        amountCad=BILL_COMBINED,
        formula="DRV-ND-BILL-TOWNSHIP-455K + DRV-ND-BILL-REGION-455K + DRV-ND-BILL-EDUCATION-455K",
        inputs=["DRV-ND-BILL-TOWNSHIP-455K", "DRV-ND-BILL-REGION-455K", "DRV-ND-BILL-EDUCATION-455K", "ND-TAXRATE-RES-TOTAL-2026-FINAL"],
        note="Cross-checked against the printed Total 2026 Rate column applied to the same assessment.",
    ),
    derived(
        id="DRV-ND-BILL-COMBINED-AYR-455K",
        label="Total 2026 residential bill at $455,000 including Ayr S.A.R.",
        amountCad=BILL_COMBINED_AYR,
        formula="ND-TAXRATE-RES-TOTAL-AYR-2026-FINAL * 455000",
        inputs=["DRV-ND-BILL-COMBINED-455K", "DRV-ND-BILL-AYR-SAR-455K", "ND-TAXRATE-RES-TOTAL-AYR-2026-FINAL"],
    ),
    derived(
        id="DRV-ND-IMPLIED-CVA-5000",
        label="Assessment implied by a $5,000 total residential bill",
        amountCad=IMPLIED_5000_CVA,
        formula="5000 / ND-TAXRATE-RES-TOTAL-2026-FINAL",
        inputs=["ND-TAXRATE-RES-TOTAL-2026-FINAL"],
        note="A $5,000 bill corresponds to a property assessed slightly below the township average of $455,000. The original hypothetical was close to reality, not a fantasy figure.",
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
            # Node ids, not the numbers they happen to hold. With literals baked
            # in, recomputing the formula only re-evaluates its own constants -
            # it agrees with itself no matter what the cited facts say, which is
            # the definition of a check that cannot fail. GENERALIZATION-PLAN
            # section 9.5 already calls a bare-literal formula leaf a hard fail;
            # this makes these nodes actually recomputable from their inputs.
            formula=f"ND-TOWNSHIP-TAX-RURAL-AVG-2026 * ({did} / DRV-ND-DEPT-SUM)",
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
        formula=" + ".join(legal_ids),
        inputs=legal_ids,
    )
)

corp = 2_091_306
pop = 10_619
pop_2025 = 13_051
derived_rows.append(
    derived(
        id="DRV-ND-CORP-PER-CAPITA",
        label="Corporate Services $ per 2021 census capita",
        amountCad=round(corp / pop, 2),
        formula="ND-DEPT-CORPORATE-2026 / ND-POP-CENSUS-2021",
        inputs=["ND-DEPT-CORPORATE-2026", "ND-POP-CENSUS-2021"],
        note="Biased upward vs current population; see DRV-ND-CORP-PER-CAPITA-2025.",
    )
)
derived_rows.append(
    derived(
        id="DRV-ND-CORP-PER-CAPITA-2025",
        label="Corporate Services $ per StatCan July 1, 2025 capita",
        amountCad=round(corp / pop_2025, 2),
        formula="ND-DEPT-CORPORATE-2026 / ND-POP-STATCAN-2025",
        inputs=["ND-DEPT-CORPORATE-2026", "ND-POP-STATCAN-2025"],
    )
)
derived_rows.append(
    derived(
        id="DRV-ND-POP-BIAS-RATIO",
        label="Inflation of per-capita metrics from using 2021 Census vs 2025 estimate",
        value=round(pop_2025 / pop, 4),
        formula="ND-POP-STATCAN-2025 / ND-POP-CENSUS-2021",
        inputs=["ND-POP-STATCAN-2025", "ND-POP-CENSUS-2021"],
        note="2025 estimate is 22.9% above the 2021 Census count; census-based per-capita figures are inflated by that factor.",
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
        id="DRV-ND-ARENA-PER-CAPITA-2025",
        label="Arena project $ per StatCan July 1, 2025 capita",
        amountCad=round(16_190_160 / pop_2025, 2),
        formula="ND-CAP-ARENA-2026 / ND-POP-STATCAN-2025",
        inputs=["ND-CAP-ARENA-2026", "ND-POP-STATCAN-2025"],
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

# FIR 2023 General government per-capita (same-year StatCan estimates)
_fir_pc = [
    ("DRV-FIR-GG-PCAP-ND-2023", 1_933_805, 12_047, ["FIR-GG-ND-2023", "ND-POP-STATCAN-2023"], "North Dumfries"),
    ("DRV-FIR-GG-PCAP-WELLESLEY-2023", 2_104_106, 12_253, ["FIR-GG-WELLESLEY-2023", "STATCAN-POP-WELLESLEY-2023"], "Wellesley"),
    ("DRV-FIR-GG-PCAP-WILMOT-2023", 4_008_877, 23_244, ["FIR-GG-WILMOT-2023", "STATCAN-POP-WILMOT-2023"], "Wilmot"),
    ("DRV-FIR-GG-PCAP-WOOLWICH-2023", 4_153_213, 30_909, ["FIR-GG-WOOLWICH-2023", "STATCAN-POP-WOOLWICH-2023"], "Woolwich"),
]
for did, spend, pop_n, inputs, label in _fir_pc:
    derived_rows.append(
        derived(
            id=did,
            label=f"FIR 2023 General government $ per capita — {label}",
            amountCad=round(spend / pop_n, 2),
            formula=f"{inputs[0]} / {inputs[1]}",
            inputs=inputs,
        )
    )
_peer_pc = [round(s / p, 2) for _, s, p, _, _ in _fir_pc[1:]]
_nd_pc = round(1_933_805 / 12_047, 2)
_peer_mean = round(sum(_peer_pc) / len(_peer_pc), 2)
derived_rows.append(
    derived(
        id="DRV-FIR-GG-PEER-MEAN-PCAP-2023",
        label="Mean FIR 2023 General government $/capita — Wellesley/Wilmot/Woolwich",
        amountCad=_peer_mean,
        formula="(DRV-FIR-GG-PCAP-WELLESLEY-2023 + DRV-FIR-GG-PCAP-WILMOT-2023 + DRV-FIR-GG-PCAP-WOOLWICH-2023) / 3",
        inputs=[
            "DRV-FIR-GG-PCAP-WELLESLEY-2023",
            "DRV-FIR-GG-PCAP-WILMOT-2023",
            "DRV-FIR-GG-PCAP-WOOLWICH-2023",
        ],
    )
)
derived_rows.append(
    derived(
        id="DRV-FIR-GG-ND-VS-PEER-MEAN-2023",
        label="North Dumfries FIR GG $/capita as ratio of peer-township mean",
        value=round(_nd_pc / _peer_mean, 4),
        formula="DRV-FIR-GG-PCAP-ND-2023 / DRV-FIR-GG-PEER-MEAN-PCAP-2023",
        inputs=["DRV-FIR-GG-PCAP-ND-2023", "DRV-FIR-GG-PEER-MEAN-PCAP-2023"],
        note=f"ND ${_nd_pc}/capita vs peer mean ${_peer_mean}/capita. Ratio ≈1.0 — not an outlier.",
    )
)

# Flip ND draft binder facts to approved after By-law 3617-26 (levy unchanged; dept nets unchanged).
for f in facts:
    if f.get("sourceId") == "nd-2026-draft" and f.get("status") == "draft":
        f["status"] = "approved"

# Gaps (closed gaps recorded separately; only open gaps ship to the UI list)
closed_gaps = [
    {
        "id": "GAP-EDUCATION-2026",
        "status": "closed",
        "resolution": "Replaced by FACT ND-TAXRATE-RES-EDUCATION-2026-FINAL from By-law 3637-26 Schedule A (agenda p.103); adopted C-153-26 / third reading C-163-26.",
        "replacedByFactIds": ["ND-TAXRATE-RES-EDUCATION-2026-FINAL"],
    },
    {
        "id": "GAP-ND-FINAL-BUDGET",
        "status": "closed",
        "resolution": "2026 Budget approved Feb 2, 2026 via By-law 3617-26 at tax levy $9,002,499 (Special Budget minutes p.5). ND binder facts flipped draft→approved. Department published nets unchanged by the Feb 2 amendments (fireworks reallocation; heritage capital from reserves).",
        "replacedByFactIds": ["ND-LEVY-2026-ADOPTED"],
    },
    {
        "id": "GAP-5000-BILL",
        "status": "closed",
        "resolution": (
            "Final RT rates ingested (township 0.00315303, Region 0.00717545, education 0.00153000). "
            "Prior detail was wrong: township $455,000 and Region $354,500 sit on the SAME MPAC January 1, 2016 valuation base; "
            "they are different average properties, not different assessment systems. "
            "Combined receipt at one assessment is deferred to a later step — not built here."
        ),
        "replacedByFactIds": [
            "ND-TAXRATE-RES-TOWNSHIP-2026-FINAL",
            "ND-TAXRATE-RES-REGION-2026-FINAL",
            "ND-TAXRATE-RES-EDUCATION-2026-FINAL",
        ],
    },
    {
        "id": "GAP-RURAL-HH-LINE-SUM",
        "status": "closed",
        "resolution": "resolved_source_rounding — 23 printed rural lines sum to $2,619; printed subtotal $2,621; less printed ($78) PIL = printed $2,543. Each line rounded to whole dollars; subtotal from unrounded values. $2,543 remains authoritative.",
    },
    {
        "id": "GAP-ND-POP-CURRENT",
        "status": "closed",
        "resolution": (
            "StatCan Table 17-10-0155-01 July 1, 2025 estimate for North Dumfries (TP) is 13,051 "
            "(FACT ND-POP-STATCAN-2025). Census-based per-capita figures using 10,619 inflate by "
            "factor 1.229 (DRV-ND-POP-BIAS-RATIO). 2021 Census figures retained alongside."
        ),
        "replacedByFactIds": ["ND-POP-STATCAN-2025", "DRV-ND-CORP-PER-CAPITA-2025", "DRV-ND-POP-BIAS-RATIO"],
    },
    {
        "id": "GAP-PEER-BENCHMARK",
        "status": "closed",
        "resolution": (
            "FIR Schedule 40 General government Total Expenses Before Adjustments (2023) for "
            "North Dumfries, Wellesley, Wilmot and Woolwich, divided by same-year StatCan July 1 "
            "estimates. ND $160.52/capita vs peer mean $159.52 (ratio 1.006) — not an outlier. "
            "Year note: FIR 2023 actuals are not 2026 budget dollars; Corporate Services ≠ FIR "
            "General government. The peer test still rejects the 'large' claim on the normalised basis."
        ),
        "replacedByFactIds": [
            "FIR-GG-ND-2023",
            "FIR-GG-WELLESLEY-2023",
            "FIR-GG-WILMOT-2023",
            "FIR-GG-WOOLWICH-2023",
            "DRV-FIR-GG-ND-VS-PEER-MEAN-2023",
        ],
    },
]

gaps = [
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
        # Reworded to say only what the binder says. The previous title and
        # detail ("spend not isolated...") asserted the existence of a spend the
        # ledger holds no amount for and attached a characterisation to it -
        # docs/GENERALIZATION-PLAN.md calls that exact text a published
        # insinuation the project's own finding rules would forbid. A gap
        # records what was looked for and not found; it does not get to imply a
        # conclusion the evidence cannot carry. The id is stable and kept.
        id="GAP-BEAVER-LINE-AMOUNT",
        title="Animal Control budget components are not itemized in the binder",
        detail=(
            "The binder states (p.20) that 'the balance of the Animal Control "
            "budget includes Pound costs as well as for traps as required by "
            "external contractors for beaver extraction', without dollar "
            "amounts for any component. No component amount is extracted, and "
            "none is published."
        ),
        blocks=["beaver_extraction_amount"],
        neededEvidence=["Departmental GL detail or invoice line for any Animal Control component"],
    ),
]

gaps.extend(
    [
        gap(
            id="GAP-TWINPAD-OPERATING-DELTA",
            title="Net operating cost change once Twin Pad opens is not established",
            detail="The ledger covers the one-time capital cost but holds no evidence on what the Twin Pad costs to RUN versus the ACC ice it replaces. For a household receipt the recurring operating change matters more than the capital event.",
            blocks=["twinpad_recurring_cost_on_bill"],
            neededEvidence=["Projected annual operating cost for the Twin Pad and the offsetting ACC ice savings"],
            searchTrail=[
                "2026 draft budget binder: ACC and NDCC facility operating lines exist for the current year; no projected Twin Pad annual operating cost or ACC-ice savings delta.",
                "Feb 2 / Apr 27 2026 council agenda and minutes packages already ingested: Twin Pad appears as capital / Net Zero Arena updates only.",
                "FIN-03-2026 10-year capital forecast narrative (in Feb 2 agenda): design/debt context, not operating delta.",
                "Ontario FIR Schedule 40 open data (2023/2024): historical actuals only; no forward Twin Pad operating projection.",
                "Conclusion (2026-07-25): figure is not published in the sources searched. Likely requires a facility business case, 10-year operating forecast detail, or a records request. Do not estimate it.",
            ],
        ),
    ]
)

findings = [
    {
        "id": "FIND-ADMIN-CORP-SCALE",
        "kind": "JUDGMENT",
        "category": "administrative_scale",
        "title": "Corporate Services scale tested against FIR peers — not an outlier",
        "opportunitySeverity": "watch",
        "citedFactIds": [
            "ND-DEPT-CORPORATE-2026",
            "ND-LEVY-2026",
            "DRV-ND-CORP-PER-CAPITA",
            "DRV-ND-CORP-PER-CAPITA-2025",
            "ND-POP-CENSUS-2021",
            "ND-POP-STATCAN-2025",
            "FIR-GG-ND-2023",
            "FIR-GG-WELLESLEY-2023",
            "FIR-GG-WILMOT-2023",
            "FIR-GG-WOOLWICH-2023",
            "DRV-FIR-GG-PCAP-ND-2023",
            "DRV-FIR-GG-PEER-MEAN-PCAP-2023",
            "DRV-FIR-GG-ND-VS-PEER-MEAN-2023",
        ],
        "evidenceSummary": (
            "Suspicion tested and not supported. On the normalised FIR 2023 General government basis "
            "(Total Expenses Before Adjustments ÷ StatCan July 1, 2023 population), North Dumfries is "
            "$160.52/capita vs a Wellesley/Wilmot/Woolwich mean of $159.52 (ratio 1.006). "
            "The earlier ~$197/capita figure used the 2021 Census count (10,619) against a 2026 budget; "
            "on the July 1, 2025 estimate (13,051) Corporate Services is ~$160/capita. "
            "Caveats: FIR 2023 ≠ 2026 budget year; Corporate Services is not identical to FIR General government. "
            "Downgraded — do not publish as an administrative-scale accusation."
        ),
        "billImpactCad": None,
        "gapIds": ["GAP-FLAGGED-DOLLARS-ON-BILL"],
        "townshipResponse": None,
    },
    {
        "id": "FIND-ADMIN-LEGAL-STACK",
        "kind": "JUDGMENT",
        "category": "administrative_scale",
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
        # 16,190,160 of 31,192,121 is 51.9%. "Dominates" is a claim about a
        # bare majority, and the project's own review produced this wording
        # before the plan was written; it never reached the repo. Findings are
        # watch items with citations, so the title may not say more than the
        # cited arithmetic supports.
        "title": "Net Zero Twin Pad takes just over half the 2026 capital program",
        "opportunitySeverity": "high_attention",
        "citedFactIds": [
            "ND-CAP-ARENA-2026",
            "ND-CAPITAL-PROGRAM-2026",
            "ND-CAP-DEBT-TWINPAD",
            "DRV-ND-ARENA-PER-CAPITA",
            "DRV-ND-ARENA-SHARE-OF-CAPITAL",
        ],
        "evidenceSummary": "$16,190,160 of $31,192,121 capital (~51.9%); $5M new debt, debt service starting 2027. Per-capita figure is SECONDARY only: $1,524.64/capita divides a lifetime capital cost by a single year of population, so it overstates the annual burden. The honest recurring number is annual debt service per household, available once the amortization schedule is published.",
        "billImpactCad": None,
        "gapIds": ["GAP-ARENA-2026-TAX-IMPACT", "GAP-FLAGGED-DOLLARS-ON-BILL"],
    },
    {
        "id": "FIND-CAP-DUAL-FACILITY",
        "kind": "JUDGMENT",
        "category": "questionable_capital",
        "title": "ACC $3.5M exterior rehab overlaps the Twin Pad build — explanation not established",
        "opportunitySeverity": "watch",
        "citedFactIds": ["ND-CAP-ACC-EXTERIOR-2026", "ND-CAP-ARENA-2026"],
        "evidenceSummary": "ACC exterior rehab $3,500,000 ($1M Ontario grant; residual from reserve accounts rather than the levy) while the Twin Pad is under construction. Counter-explanation already on the record: the ACC ice is decommissioned when the Twin Pad opens, so envelope work on a building that continues in non-ice community use is not duplication. Downgraded from high_attention because 'concurrent' does not establish waste.",
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

# --- Step 4 post-processing: disclosure fields, materiality floor ---
for _f in findings:
    _f.setdefault("townshipResponse", None)

_extra_gaps = {
    "FIND-CAP-ARENA": ["GAP-TWINPAD-OPERATING-DELTA"],
}
for _f in findings:
    for _g in _extra_gaps.get(_f["id"], []):
        if _g not in _f["gapIds"]:
            _f["gapIds"].append(_g)

MATERIALITY_FLOOR = round(0.0025 * 9_002_499)
_below = {"FIND-UNUSUAL-HERITAGE-SOFTWARE", "FIND-UNUSUAL-PARTNERSHIP-FEES"}
for _f in findings:
    _f["belowMateriality"] = _f["id"] in _below
PUBLISHED_FINDING_IDS = [_f["id"] for _f in findings if not _f["belowMateriality"]]

_gap_ids_all = {_g["id"] for _g in gaps}
for _f in findings:
    for _g in _f["gapIds"]:
        if _g not in _gap_ids_all:
            raise EvidenceModelError(
                f"finding {_f['id']} references missing gap {_g}"
            )

sources = [
    {
        "id": "nd-2026-draft",
        "title": "Township of North Dumfries 2026 Municipal Draft Budget Binder",
        "url": "https://www.northdumfries.ca/media/csjjshvf/2026-draft-budget-binder.pdf",
        "localPath": "source-pdfs/2026-draft-budget-binder.pdf",
        "extractedText": "data/_extracts/2026-draft-budget-binder.txt",
        "asOf": "2025-12-08",
        "authority": "draft",
        "note": "Figures approved Feb 2, 2026 (By-law 3617-26) at the same municipal levy; used for department-line page cites.",
    },
    {
        "id": "nd-2026-budget-agenda",
        "title": "Special (Budget) Council Meeting Agenda — February 2, 2026",
        "url": "https://calendar.northdumfries.ca/council/Detail/2026-02-02-1800-Special-Budget-Meeting/4251bc8c-cc76-48d8-89a2-b3e1012c9cca",
        "localPath": "source-pdfs/2026-02-02-special-budget-agenda.pdf",
        "extractedText": "data/_extracts/2026-02-02-special-budget-agenda.txt",
        "asOf": "2026-02-02",
        "authority": "approved",
    },
    {
        "id": "nd-2026-budget-minutes",
        "title": "Special (Budget) Council Meeting Minutes — February 2, 2026",
        "url": "https://calendar.northdumfries.ca/council/Detail/2026-02-02-1800-Special-Budget-Meeting/06d26127-4ec5-4bf9-9070-b3fb0106ccf8",
        "localPath": "source-pdfs/2026-02-02-special-budget-minutes.pdf",
        "extractedText": "data/_extracts/2026-02-02-special-budget-minutes.txt",
        "asOf": "2026-02-02",
        "authority": "approved",
    },
    {
        "id": "nd-2026-tax-rate-bylaw",
        "title": "Council Agenda Package April 27, 2026 — includes By-law 3637-26 Schedule A (Final Tax Rates)",
        "url": "https://calendar.northdumfries.ca/council/Detail/2026-04-27-1800-Council-Meeting/e53fc266-10b7-4886-a08f-b43901092c5d",
        "localPath": "source-pdfs/2026-04-27-council-agenda.pdf",
        "extractedText": "data/_extracts/2026-04-27-council-agenda.txt",
        "asOf": "2026-04-27",
        "authority": "final",
    },
    {
        "id": "nd-2026-tax-rate-minutes",
        "title": "Council Meeting Minutes — April 27, 2026 (adoption of By-law 3637-26)",
        "url": "https://calendar.northdumfries.ca/council/Detail/2026-04-27-1800-Council-Meeting/a279405d-b775-47ec-b5d9-b44800f51f79",
        "localPath": "source-pdfs/2026-04-27-council-minutes.pdf",
        "extractedText": "data/_extracts/2026-04-27-council-minutes.txt",
        "asOf": "2026-04-27",
        "authority": "final",
    },
    {
        "id": "row-2026-book",
        "title": "Region of Waterloo 2026 Final Budget Book",
        "url": "https://www.regionofwaterloo.ca/media/ynro4cd2/2026_final_budget_book.pdf",
        "localPath": "source-pdfs/2026_final_budget_book_region.pdf",
        "extractedText": "data/_extracts/2026_final_budget_book_region.txt",
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
    {
        "id": "statcan-csd-estimates",
        "title": "Statistics Canada Table 17-10-0155-01 — Population estimates, July 1, by census subdivision",
        "url": "https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=1710015501",
        "localPath": None,
        "authority": "external",
        "asOf": "2025-07-01",
        "note": "Downloaded CSV extract 17100155-eng.zip used to cite township estimates; full table not committed.",
    },
    {
        "id": "mmah-fir-2023",
        "title": "Ontario MMAH Financial Information Return — fir_data_2023 (Schedule 40 General government)",
        "url": "https://efis.fma.csc.gov.on.ca/fir/MultiYearReport/fir_data_2023.zip",
        "localPath": "source-pdfs/fir/fir-general-government-peers-2023-2024.csv",
        # A text source is its own extract. Declaring it lets audit_citations
        # read the rows these four facts quote; without it they were reported
        # "unverifiable", which meant unread rather than unverifiable - the file
        # has been committed the whole time.
        "extractedText": "data/_extracts/fir/fir-general-government-peers-2023-2024.txt",
        "authority": "external",
        "asOf": "2023-12-31",
        "note": "Peer extract only is committed. Full provincial ZIP kept locally / gitignored.",
    },
]

ledger = {
    "schemaVersion": "2.0.0",
    "artifact": "EvidenceLedger",
    # The ledger has to say which municipality, year and currency it describes.
    # It did not, so validate_pack --strict could not confirm that the pack
    # descriptor, the ledger and the receipt were talking about the same place:
    # an identity check that cannot run is not a check that passed.
    #
    # Nothing here is new. Every value is already declared in
    # corpus/north-dumfries-on/pack.yaml and carried on the receipt; this
    # carries it into the third artifact so the three can be compared, which is
    # what makes a mismatch detectable at all. Brant's builder already does this.
    "fiscalYear": 2026,
    "currency": "CAD",
    "jurisdiction": {
        "slug": "north-dumfries-on",
        "name": "Township of North Dumfries",
        "level": "lower-tier",
        "assessmentCode": "3001",
        "aliases": ["North Dumfries", "Ayr"],
    },
    "evidencePolicy": {
        "rules": [
            # The reader sees these rules on the page, so the excerpt rule has to
            # carry the same qualification README.md does. An "excerpt" that is
            # actually a reconstruction of the cited row, presented without saying
            # so, is the one overclaim this project cannot afford.
            "FACT: must include sourceId, excerpt, and page when from PDF. An excerpt is a "
            "reconstruction of the cited row unless data/citation-audit.json reports a verbatim "
            "or stronger match for that fact.",
            "DERIVED: must include formula and input ids; no new external numbers.",
            "GAP: record missing evidence; never invent amounts to fill UI.",
            "JUDGMENT: interpretive only; billImpactCad stays null.",
            "Draft vs final: North Dumfries 2026 operating figures are approved (By-law 3617-26); final residential rates from By-law 3637-26 Schedule A.",
        ]
    },
    "sources": sources,
    "facts": facts,
    "derived": derived_rows,
    "gaps": gaps,
    "closedGaps": closed_gaps,
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
        # Cite the printed ($78) itself, not the $2,543 total it reconciles to.
        # Citing the total meant this line's number could never be checked
        # against what it cited - the last unbound value in the corpus.
        "sourceFactId": "ROW-PIL-SUPP-REDUCTION-2026",
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
        "evidenceStatus": "RECONCILING",
        "note": "Source rounding (resolved): printed lines sum $2,619; printed subtotal $2,621; less ($78) PIL = $2,543. Do not treat as a service.",
    }
)

township_lines = []
label_map = {
    "ND-DEPT-CORPORATE-2026": "Corporate Services",
    "ND-DEPT-PROTECTIVE-2026": "Protective Services (incl. Fire)",
    "ND-DEPT-PW-2026": "Public Works",
    "ND-DEPT-REC-2026": "Recreation Services",
    "ND-DEPT-PLANNING-2026": "Planning",
    "ND-DEPT-ENVIRONMENTAL-2026": "Environmental Services (net credit)",
    "ND-CAPITAL-FUNDED-BY-LEVY-2026": "Capital funded by tax levy",
}
for row in township_alloc:
    township_lines.append(
        {
            "id": row["factId"],
            "label": label_map[row["factId"]],
            "amountCad": row["amountCad"],
            "classification": "township_draft_allocated",
            "evidenceStatus": "DERIVED",
            # Cite the allocation, not its input. This line printed a
            # per-household share while citing the municipality-wide department
            # figure it was derived from, so the two were never the same number
            # and nothing could compare them: a planted 999999 passed
            # validate_pack with zero errors. Pointing at DRV-ALLOC-* makes the
            # printed value equal to its cited node, which is what makes the
            # binding checkable at all. Provenance is not lost - the department
            # fact is the first declared input, and every consumer already walks
            # a derived node's inputs to reach the source document.
            "sourceFactId": f"DRV-ALLOC-{row['factId']}",
            "note": "Pro-rata of the tax-supported expenditure base ($10,049,624) against rural average township tax $1,434.63",
        }
    )

for _tl in township_lines:
    if _tl["id"] == "ND-DEPT-CORPORATE-2026":
        _tl["subLines"] = [
            {
                "id": "ND-GOVERNANCE-COUNCIL-ELECTIONS",
                "label": "of which Council & Elections",
                "amountCad": GOVERNANCE_SUBLINE,
                "classification": "disclosure_subline",
                "evidenceStatus": "DERIVED",
                "sourceFactId": "DRV-ND-GOVERNANCE-SUBLINE",
                "note": "Already included in the Corporate Services figure above. Shown for transparency; not added to any total.",
            }
        ]

receipt = {
    "schemaVersion": "2.0.0",
    "artifact": "TaxpayerReceipt",
    "fiscalYear": FISCAL_YEAR,
    "currency": CURRENCY,
    "status": "partial_evidence_based",
    "purpose": (
        "UI data model using only supported allocations. A hypothetical $5,000 "
        "combined bill can be split among taxing bodies from adopted rates; it "
        "is not a published household bill."
    ),
    "evidencePolicyRef": "data/evidence-ledger.json",
    "jurisdiction": {
        "slug": "north-dumfries-on",
        "displayName": "Township of North Dumfries",
        "level": "lower-tier",
        "aliases": ["North Dumfries", "Ayr"],
    },
    "profiles": {
        "supportedAverageHousehold": {
            "description": "Best evidence-based profile without inventing a $5,000 bill.",
            "township": {
                "basis": "ND 2026 approved rural average at $455,000 assessment — TOWNSHIP PORTION ONLY (rate confirmed in By-law 3637-26)",
                "amountCad": 1434.63,
                "assessmentCad": 455_000,
                "evidenceStatus": "FACT",
                "sourceFactId": "ND-TOWNSHIP-TAX-RURAL-AVG-2026",
                "uiLabel": "Township portion",
                "lineItems": township_lines,
            },
            "region": {
                "basis": "Region 2026 Budget Book p.12 Rural column (North Dumfries + Wellesley) at $354,500 assessment",
                "amountCad": 2543,
                "assessmentCad": 354_500,
                "evidenceStatus": "FACT",
                "sourceFactId": "ROW-RURAL-HH-TOTAL-2026",
                "uiLabel": "Region portion",
                "lineItems": region_lines,
                "lineItemsSumCheckCad": sum(item["amountCad"] for item in region_lines),
            },
            "education": {
                "basis": "By-law 3637-26 Schedule A — RT Residential Education Rate 0.00153000 at $455,000",
                "amountCad": BILL_EDU,
                "assessmentCad": ASSESSMENT,
                "evidenceStatus": "DERIVED",
                "sourceFactId": "DRV-ND-BILL-EDUCATION-455K",
                "uiLabel": "Education",
                "note": "Province sets this rate under O. Reg. 400/98; the Township only collects it.",
            },
            "combinedTotalCad": BILL_COMBINED,
            "combinedAtAssessment": {
                "assessmentCad": ASSESSMENT,
                "basis": "By-law 3637-26 Schedule A, CODE RT Residential (2026-04-27 council agenda p.103)",
                "evidenceStatus": "DERIVED",
                "components": [
                    {"label": "Township of North Dumfries", "amountCad": BILL_TWP, "rate": RATE_TWP, "sourceFactId": "ND-TAXRATE-RES-TOWNSHIP-2026-FINAL"},
                    {"label": "Region of Waterloo", "amountCad": BILL_REG, "rate": RATE_REG, "sourceFactId": "ND-TAXRATE-RES-REGION-2026-FINAL"},
                    {"label": "Education (Province of Ontario)", "amountCad": BILL_EDU, "rate": RATE_EDU, "sourceFactId": "ND-TAXRATE-RES-EDUCATION-2026-FINAL"},
                ],
                "totalCad": BILL_COMBINED,
                "totalRate": RATE_TOTAL,
                "ayrUrbanVariant": {
                    "specialAreaRateCad": BILL_SAR,
                    "totalCad": BILL_COMBINED_AYR,
                    "totalRate": RATE_TOTAL_AYR,
                    "note": "Ayr urban service area only. Rural properties pay the rural total.",
                },
            },
            # The Ayr urban special area rate is a variant of this bill rather
            # than a fourth body on it - rural properties do not pay it - so it
            # stays inside combinedAtAssessment until variants are modelled.
            "taxingBodies": build_taxing_bodies(
                [
                    {"label": "Township of North Dumfries", "amountCad": BILL_TWP, "rate": RATE_TWP,
                     "sourceFactId": "ND-TAXRATE-RES-TOWNSHIP-2026-FINAL"},
                    {"label": "Region of Waterloo", "amountCad": BILL_REG, "rate": RATE_REG,
                     "sourceFactId": "ND-TAXRATE-RES-REGION-2026-FINAL"},
                    {"label": "Education (Province of Ontario)", "amountCad": BILL_EDU, "rate": RATE_EDU,
                     "sourceFactId": "ND-TAXRATE-RES-EDUCATION-2026-FINAL"},
                ],
                {
                    "ND-TAXRATE-RES-TOWNSHIP-2026-FINAL": "local",
                    "ND-TAXRATE-RES-REGION-2026-FINAL": "upper-tier",
                    "ND-TAXRATE-RES-EDUCATION-2026-FINAL": "education",
                },
                total_cad=BILL_COMBINED,
                assessment_cad=ASSESSMENT,
                basis="By-law 3637-26 Schedule A RT Residential rates at $455,000",
            ),
            "combinedTotalNote": (
                "Built from the adopted By-law 3637-26 Schedule A rates applied to ONE assessment ($455,000), "
                "not by adding two governments' differently-based household averages. The three rates sum exactly "
                "to the printed Total 2026 Rate, and the township component reproduces the separately cited $1,434.63 to the cent."
            ),
            "warnings": [
                "The Region figure of $2,543 elsewhere in this model is the Region's own average household at $354,500 — do not mix it with this $455,000 receipt. Both sit on the same MPAC January 1, 2016 base; they differ only in which average property each government reports.",
                "Ayr urban properties additionally pay the Special Area Rate; the rural total excludes it.",
                "North Dumfries operating amounts are approved (By-law 3617-26).",
            ],
        },
        "hypothetical5000": {
            "amountCad": 5000,
            "evidenceStatus": "DERIVED",
            "allocatable": True,
            "impliedAssessmentCad": IMPLIED_5000_CVA,
            "compositionShares": [
                {"label": "Township of North Dumfries", "share": SHARE_TWP, "sourceFactId": "ND-TAXRATE-RES-TOWNSHIP-2026-FINAL"},
                {"label": "Region of Waterloo", "share": SHARE_REG, "sourceFactId": "ND-TAXRATE-RES-REGION-2026-FINAL"},
                {"label": "Education (Province of Ontario)", "share": SHARE_EDU, "sourceFactId": "ND-TAXRATE-RES-EDUCATION-2026-FINAL"},
            ],
            "message": (
                "A $5,000 total bill implies an assessment of about $" + format(IMPLIED_5000_CVA, ",") + ", slightly below the "
                "township average of $455,000. Shown as rate shares rather than invented dollars: the split of any bill is fixed "
                "by the by-law rates regardless of assessment. For dollar figures see combinedAtAssessment."
            ),
        },
    },
    "findings": findings,
    "uiModelHints": {
        "screen": "TaxReceipt",
        "defaultProfile": "supportedAverageHousehold",
        "showGapsAsFirstClassUi": True,
        "forbidFillerAllocation": True,
        "materialityFloorCad": MATERIALITY_FLOOR,
        "materialityNote": (
            "Findings below this floor (0.25% of the municipal levy) stay in the ledger but are "
            "excluded from published output. Publishing a $1,725 line beside a $16M project invites "
            "dismissal of the whole instrument."
        ),
        "flaggedDefinition": (
            "Flagged means this line needs an explanation. It does not mean the money was wasted."
        ),
        "publishedFindingIds": PUBLISHED_FINDING_IDS,
        "marqueeFindings": [
            _id
            for _id in ["FIND-CAP-ARENA", "FIND-ADMIN-LEGAL-STACK", "FIND-ADMIN-CORP-SCALE"]
            if _id in PUBLISHED_FINDING_IDS
        ],
        "municipalBucketLabel": "Township portion",
        "regionBucketLabel": "Region portion",
        "heroLabel": "Total residential bill · rural · By-law 3637-26",
    },
}

# Write BOTH the canonical copy and the UI mirror. The mirror used to be copied by
# hand, so running this script silently left the UI reading stale data.
# Pack metadata lives in corpus/north-dumfries-on/pack.yaml (bridge until YAML corpus).
WEB_DATA = ROOT / "web" / "src" / "data"

# Serialise once per artifact and hand the same bytes to both destinations. The
# mirror check used to run after both files had already been written: by the time
# it noticed a divergence, the divergence was on disk and the UI could be reading
# it. Establishing the invariant before the write makes divergence impossible
# rather than merely detected.
_artifacts = {
    "evidence-ledger.json": (json.dumps(ledger, indent=2) + "\n").encode("utf-8"),
    "taxpayer-receipt.json": (json.dumps(receipt, indent=2) + "\n").encode("utf-8"),
}

# Mirror the citation audit when present so the UI can refuse bad #page= deep links.
_audit = DATA / "citation-audit.json"

_destinations = (DATA, WEB_DATA)
if len({_d.resolve() for _d in _destinations}) != len(_destinations):
    raise EvidenceModelError(
        f"canonical and mirror directories resolve to the same path: {DATA}"
    )
for _dir in _destinations:
    if not _dir.is_dir():
        raise EvidenceModelError(f"output directory does not exist: {_dir}")

for _name, _payload in _artifacts.items():
    for _dir in _destinations:
        write_bytes_atomic(_dir / _name, _payload)

if _audit.exists():
    write_bytes_atomic(WEB_DATA / "citation-audit.json", _audit.read_bytes())

# Read back what actually landed. The pre-write guarantee covers what we intended
# to write; this covers the disk.
for _name, _payload in _artifacts.items():
    for _dir in _destinations:
        _written = (_dir / _name).read_bytes()
        if _written != _payload:
            raise EvidenceModelError(
                f"{_dir / _name} does not match the bytes just written "
                f"({len(_written)} on disk vs {len(_payload)} intended)"
            )

print("facts", len(facts))
print("derived", len(derived_rows))
print("gaps", len(gaps))
print("closedGaps", len(closed_gaps))
print("findings", len(findings))
print("pack", "corpus/north-dumfries-on (status: see pack.yaml — run scripts/validate_pack.py)")
print(
    "region rural service lines",
    region_sum,
    "published subtotal",
    region_sum + 2,
    "after PIL",
    region_sum + 2 - 78,
)
print("township alloc sum", round(sum(x["amountCad"] for x in township_lines), 2))
print("wrote evidence-ledger.json and taxpayer-receipt.json")
