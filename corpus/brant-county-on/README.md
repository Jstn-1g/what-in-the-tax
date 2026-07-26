# brant-county-on (Paris, Ontario)

Gold-style draft pack for the **County of Brant** — the single-tier municipality that bills **Paris, ON**.

There is no separate Town of Paris lower-tier tax pack. MMAH FIR assessment code **2920**.

**Publication status: draft.** Run validate before any seal.

## Why not “Paris”?

Paris is an urban centre inside County of Brant. Property tax rates and the net levy are County documents. Searching “Paris” should resolve to this slug.

## Artifacts

| file | role |
|---|---|
| `pack.yaml` | jurisdiction + publication metadata |
| `../../data/brant/evidence-ledger.json` | FACT / DERIVED / GAP |
| `../../data/brant/taxpayer-receipt.json` | UI model |
| `../../data/_extracts/brant/` | page-marked text for citation audit |

```bash
python scripts/extract_brant_pdf_text.py
python scripts/build_brant_evidence_model.py
python scripts/validate_pack.py brant-county-on
```

## Bill shape (single-tier)

Unlike North Dumfries (Township + Region of Waterloo + Education), Brant is:

1. County municipal rate  
2. Hospital special levy  
3. Education  

The County’s published median illustration (**$4,295.35** at **$391,000**) is municipal + hospital only — **education excluded**. This receipt shows the full RT total including education.
