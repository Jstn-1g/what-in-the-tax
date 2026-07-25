# Taxpayer Receipt

Evidence-first forensic budget model + Tax Receipt UI for **North Dumfries** / **Region of Waterloo**.

## What’s included

- `data/evidence-ledger.json` — FACT / DERIVED / GAP / JUDGMENT ledger with citations
- `data/taxpayer-receipt.json` — UI profile (supported household slices; `$5,000` bill marked not allocatable)
- `source-pdfs/` — downloaded budget PDFs
- `web/` — Vite + React Tax Receipt screen

## Evidence rules

- FACT: cited from PDF (page + excerpt)
- DERIVED: formula from fact IDs only
- GAP: missing evidence — never invent amounts
- JUDGMENT: interpretive findings; no invented bill dollars

## Run

```bash
cd web
npm install
npm run dev
```

```bash
npm test
npm run build
```

## Notes

Township 2026 figures are **draft**. Region rural household table uses **$354,500** assessment; township rural average uses **$455,000** — do not add them into one “real” bill without a final combined tax schedule.
