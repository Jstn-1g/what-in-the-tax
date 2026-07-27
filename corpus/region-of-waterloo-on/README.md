# region-of-waterloo-on (Region of Waterloo)

Shared **upper-tier** pack for the Region of Waterloo 2026 household
tax-supported schedule. Lower-tier packs import one verified area key; the
loader fails closed if the schedule, official PDF, page-marked extract, ledger,
receipt, or lock drifts. They must not copy these `$354,500` dollars into a
differently assessed municipal bill without an explicit rate×assessment
DERIVED path.

**Publication status: draft.** Run validate before any seal.

## Why a separate pack?

Four Waterloo area municipalities would otherwise each embed a copy of the same
Region table and drift apart. One revision here; importers reference it.

## Artifacts

| file | role |
|---|---|
| `pack.yaml` | jurisdiction + publication metadata |
| `schedules/household-tax-supported-2026.yaml` | parsed HH schedule (source of truth) |
| `sources.lock.json` | PDF, extract, schedule, ledger and receipt SHA-256/byte locks |
| `../../data/region-waterloo/evidence-ledger.json` | bound FACT/DERIVED lines for all five areas |
| `../../data/region-waterloo/taxpayer-receipt.json` | five-profile validation model |
| `../../data/_extracts/2026_final_budget_book_region.txt` | page-marked extract |

## CLI pipeline

```bash
# If the PDF extract is missing (Region budget book under source-pdfs/):
python scripts/extract_pdf_text.py

# The parser rewrites only the numeric schedule. Re-review/preserve the source,
# basis, currency, coverage and lock metadata before building.
python scripts/parse_row_household_schedule.py
python scripts/build_region_waterloo_pack.py
python scripts/build_kitchener_evidence_model.py
# optional: rebuild ND after rural import from YAML
python scripts/build_evidence_model.py
python scripts/validate_pack.py region-of-waterloo-on --strict
python scripts/validate_pack.py kitchener-on
```

`build_region_waterloo_pack.py` updates only the regional corpus/data artifacts
by default. Its legacy frontend mirror requires the explicit `--sync-web` flag.

## Basis and reconciliation

The page contains two related bases that must not be mixed:

- program values are **CAD thousands**;
- household values are **whole CAD per average household at $354,500**.

Program controls reconcile as follows:

| control | CAD thousands |
|---|---:|
| printed service property-tax-levy subtotal | 910,967 |
| less general revenues (PIL and supplementary taxes) | (23,639) |
| printed-control rounding | 1 |
| published Regional Tax Levy | 887,329 |

The service net-expenditure rows sum to 1,612,758 while the printed subtotal is
1,612,760, a disclosed 2 ($000) source-table rounding difference. “Net
expenditure” is already net of user fees, grants, subsidies and recoveries; it
is not the same as the property-tax levy.

Household service lines also do **not** always sum to the printed services
subtotal. For every area the pack records:

- `servicesSubtotalCad` — sum of parsed line items
- `publishedServicesSubtotalCad` — printed subtotal (authoritative for PIL math)
- `roundingAdjustmentCad` — difference
- `taxSupportedTotalCad` — published after-PIL total (authoritative household total)

Validation uses exact `Decimal` arithmetic:
`sum(lines) + roundingAdjustment == publishedSubtotal` and
`publishedSubtotal + PIL == afterPIL`.

## Area keys

| key | municipalities |
|---|---|
| `urban` | Kitchener, Waterloo, Cambridge |
| `rural` | North Dumfries, Wellesley |
| `woolwich` | Woolwich |
| `wilmot` | Wilmot |
| `blended` | Region-wide blend |

All 23 service rows and all five columns are covered: 115 household
allocations. User-rate water/wastewater rows, lower-tier taxes, education taxes,
and property-specific adjustments are explicitly out of scope.

## Evidence disclosure

The exact official PDF and extract are hash- and byte-locked, page 12 is checked
against the 191-page PDF/extract range, and every fact records a deterministic
table row/column binding. The original source retrieval timestamp was not
independently recorded; it remains `null` and is carried as an open evidence
gap. This pack remains a **draft preview** with no claimed municipal approval,
publisher contact, or published status.
