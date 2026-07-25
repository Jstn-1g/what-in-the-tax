# Fleet dry run — how to explain it

This is the talk track for the dry run we just set up.

## The one-sentence version

> Ontario already publishes each town’s finance return; our script reads that file, pulls two defined lines, does division, and writes a small JSON card per town — no AI, no volunteers uploading receipts.

## The demo cohort

| Code | Name | Why it’s in the dry run |
|---|---|---|
| **2920** | Brant County | Paris residents are billed by this **single-tier** county — not a separate “Town of Paris” pack |
| **3001** | North Dumfries | Same town as our gold by-law pack — so you can compare grades later |
| **3024** | Wellesley | Nearby peer township |

## Steps (what actually happens)

1. **Input** — `source-pdfs/fir/fir_data_2023.zip` (official MMAH file; kept local / gitignored).
2. **Select** — only the demo assessment codes (later: all codes that pass gates).
3. **Extract** — two SLC rows only: FIR population + Schedule 40 general government expenses.
4. **Gate** — if either row is missing → **skip** (fail closed). No invented numbers.
5. **Derive** — `general government ÷ population = $ per capita`.
6. **Emit** — `fleet/dry-run/by-code/<code>.json` + `index.json` phone book.
7. **AI** — not in this path. Tokens for the run: **0**.

## How this differs from North Dumfries gold

| | FIR fleet stub (this dry run) | Gold pack (ND / Ayr path) |
|---|---|---|
| Source | One provincial FIR zip | Local by-law / budget PDFs |
| Who builds | Script | You (+ optional AI assist) + citation audit |
| Shows | Coarse, labeled baseline | Exact rates, pages, excerpts |
| Findings | Never | Rare, by hand |
| Cost to add a town | ~0 after script exists | Hours |

## What you say when someone asks about Paris

> “Paris isn’t a separate lower-tier FIR filer. We stamp **Brant County (2920)**. Search ‘Paris’ in the app should resolve to that county card. If we later do a gold by-law pack, it’s still Brant’s documents — same as we did for North Dumfries.”

## Commands

```bash
python scripts/build_fir_fleet_dry_run.py
python scripts/build_fir_fleet_dry_run.py --year 2023 --codes 2920,3001,3024
```

Then open `fleet/dry-run/index.json` and `fleet/dry-run/by-code/2920.json`.
