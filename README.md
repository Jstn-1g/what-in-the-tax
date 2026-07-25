# Taxpayer Receipt

Prototype forensic budget model + Tax Receipt UI for **North Dumfries** / **Region of Waterloo**.

## What’s included

- `data/taxpayer-receipt.json` — foundational data model for a hypothetical property-tax bill
- `source-pdfs/` — downloaded 2025/2026 township + regional budget PDFs
- `web/` — Vite + React Tax Receipt screen

## UI features

- Itemized receipt with necessary / education / flagged filters
- Forensic findings (admin bloat, capital, unusual items) with linked-line drawer
- Bill scaler (slider + presets)
- Assessment → estimated bill calculator
- Copy / share / CSV export / print receipt summary
- Shareable URL state (`?bill=5000&assessment=455000`)
- “Watch these first” marquee flags
- Baseline compare vs the $5,000 model
- Local persistence for bill + assessment values

## Run

```bash
cd web
npm install
npm run dev
```

Open the URL Vite prints (default `http://127.0.0.1:5173`).

```bash
npm test
```

## Notes

Figures are modeled from publicly published draft/final budget materials. Education is a provincial pass-through. Flag tags are forensic hypotheses for UI highlighting, not audit findings of illegality.
