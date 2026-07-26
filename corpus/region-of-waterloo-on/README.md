# region-of-waterloo-on (Region of Waterloo)

Shared **upper-tier** pack for the Region of Waterloo household tax-supported
schedule. Lower-tier packs (`kitchener-on`, `north-dumfries-on`, …) import by
area key — they must not copy these `$354,500` dollars into a differently
assessed municipal bill without an explicit rate×assessment DERIVED path.

**Publication status: draft.** Run validate before any seal.

## Why a separate pack?

Four Waterloo area municipalities would otherwise each embed a copy of the same
Region table and drift apart. One revision here; importers reference it.

## Artifacts

| file | role |
|---|---|
| `pack.yaml` | jurisdiction + publication metadata |
| `schedules/household-tax-supported-2026.yaml` | parsed HH schedule (source of truth) |
| `../../data/region-waterloo/evidence-ledger.json` | FACT lines for urban + rural |
| `../../data/region-waterloo/taxpayer-receipt.json` | thin UI model for validate gate |
| `../../data/_extracts/2026_final_budget_book_region.txt` | page-marked extract |

## CLI pipeline

```bash
# If PDF extract missing (region budget book under source-pdfs/):
python scripts/extract_pdf_text.py

python scripts/parse_row_household_schedule.py
python scripts/build_region_waterloo_pack.py
python scripts/build_kitchener_evidence_model.py
# optional: rebuild ND after rural import from YAML
python scripts/build_evidence_model.py
python scripts/validate_pack.py region-of-waterloo-on
python scripts/validate_pack.py kitchener-on
```

## Rounding note

The Region PDF prints service line dollars that do **not** always sum to the
printed services subtotal (typically $2–$3). This pack records:

- `servicesSubtotalCad` — sum of parsed line items
- `publishedServicesSubtotalCad` — printed subtotal (authoritative for PIL math)
- `roundingAdjustmentCad` — difference
- `taxSupportedTotalCad` — published after-PIL total (authoritative household total)

Validation: `|sum(lines) − publishedSubtotal| ≤ 5` and
`publishedSubtotal + PIL == afterPIL`.

## Area keys

| key | municipalities |
|---|---|
| `urban` | Kitchener, Waterloo, Cambridge |
| `rural` | North Dumfries, Wellesley |
| `woolwich` | Woolwich |
| `wilmot` | Wilmot |
| `blended` | Region-wide blend |
