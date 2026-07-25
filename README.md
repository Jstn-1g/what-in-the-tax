# Taxpayer Receipt

Evidence-first forensic budget model and Tax Receipt UI for the **Township of North Dumfries** and the **Region of Waterloo**.

Every dollar on screen traces to a page in a published document, or to a formula over figures that do. Nothing is modelled, estimated, or filled in.

## The headline number

A residential property assessed at **$455,000** (the Township's own average, on the MPAC January 1 2016 valuation base) pays for 2026:

| | rate | amount |
|---|---|---|
| Township of North Dumfries | 0.00315303 | $1,434.63 |
| Region of Waterloo | 0.00717545 | $3,264.83 |
| Education (Province of Ontario) | 0.00153000 | $696.15 |
| **Total** | **0.01185848** | **$5,395.61** |

Ayr urban properties additionally pay the Special Area Rate of 0.00015571 ($70.85), for $5,466.46.

Source: **By-law No. 3637-26**, Schedule A, CODE RT Residential — Report FIN-07-2026 Attachment 1, in the 2026-04-27 council agenda at PDF page 103. Adopted by resolution C-153-26.

The three rate columns sum exactly to the printed Total 2026 Rate, and the township component reproduces the separately published $1,434.63 to the cent. Both identities are asserted in the generator, which refuses to emit if either fails.

## What's included

| path | role |
|---|---|
| `data/evidence-ledger.json` | FACT / DERIVED / GAP / JUDGMENT ledger with citations |
| `data/taxpayer-receipt.json` | UI data model |
| `web/src/data/` | mirror of the two above, written by the generator |
| `scripts/build_evidence_model.py` | single source of truth — regenerates both copies |
| `scripts/extract_pdf_text.py` | PDF to text |
| `source-pdfs/` | cited source documents only |
| `web/` | Vite + React Tax Receipt screen |
| `DIRECTOR-REVIEW.md` | independent review, including corrections to its own findings |
| `docs/` | per-step working briefs |

## Evidence rules

- **FACT** — cited to a source with a page or URL and an excerpt. Excerpts are reconstructions unless `data/citation-audit.json` reports a verbatim (or stronger) match for that fact.
- **DERIVED** — computed only from fact IDs, with the formula recorded.
- **GAP** — missing evidence. Never invent a number to fill one. Resolved gaps move to `closedGaps` rather than being deleted, so the audit trail survives.
- **JUDGMENT** — interpretive only. `billImpactCad` stays `null`, always.
- A documented dead end is a correct outcome. Gaps carry a `searchTrail` recording where we looked.

## Static packs, validation, and versioning

Rollout is **static jurisdiction packs** (files + git), not a shared multi-tenant database. Integrity is content hashes and citation audit — not a blockchain as source of truth.

| doc | role |
|---|---|
| `PURPOSE.md` | Who it's for; what v1 refuses |
| `PUBLISH.md` | draft → sealed → Published (only path) |
| `docs/VERSIONING.md` | `engine/x.y.z` vs `pack/<slug>/YYYY.N` |
| `corpus/` | Pack descriptors + `_template` |
| `LICENSE` | MIT |

```bash
python scripts/build_evidence_model.py
python scripts/audit_citations.py
python scripts/validate_pack.py north-dumfries-on   # must exit 0 to seal
python scripts/seal_pack.py north-dumfries-on 1     # writes receipts/.../manifest.json
```

**Pack status today:** `north-dumfries-on` is **sealed** at `pack/north-dumfries-on/2026.3` (provisional preview). Citation hard failures are zero. See `docs/DEPLOY.md` to host on GitHub Pages. Full “Published” still needs the human steps in `PUBLISH.md`.

## Reconciliation

The township allocation base is **10,049,624**, which ties exactly to the binder's own published total: taxation 9,182,824 + corporate revenues 866,800, Net Budget 0. The generator asserts this.

Four figures are easy to conflate and are deliberately kept distinct:

| figure | meaning |
|---|---|
| 9,002,499 | municipal levy — rate × assessment, what appears on a tax bill |
| 9,182,824 | total taxation revenue — levy plus supplementaries and PILs |
| 10,049,624 | expenditure base — funded by taxation *plus* non-tax corporate revenue |
| 9,002,462 | the tax-rate by-law's recital, $37 off the adopted levy — recorded, not reconciled |

## Findings discipline

Findings are watch items with citations, never accusations. Specifically:

- "Flagged" is defined on screen as **needs an explanation** — not "wasted".
- Every finding carries `townshipResponse`, null until the Township has been asked. Publishing a judgment without offering right of reply is the real risk.
- A materiality floor of $22,506 (0.25% of the levy) keeps sub-floor items in the ledger but out of published output. A $1,725 line beside a $16M project invites dismissal of the whole instrument.
- Where a finding has a plausible innocent explanation, that explanation is recorded in the finding itself.

## Run

```bash
python scripts/build_evidence_model.py   # regenerate both data copies

cd web
npm install
npm run dev        # http://127.0.0.1:5173
npm test           # vitest suite in web/
npm run build      # tsc + vite
```

## Known open gaps

Open gaps (each with a search trail in the ledger):

- `GAP-TWINPAD-OPERATING-DELTA` — no published Twin Pad vs ACC ice operating delta
- `GAP-FLAGGED-DOLLARS-ON-BILL` — no approved rule for “flagged” dollars on a household bill
- `GAP-ARENA-2026-TAX-IMPACT` — Twin Pad debt service tax impact not stated for 2026
- `GAP-BEAVER-LINE-AMOUNT` — beaver extraction spend not isolated as a line amount

Closed (retained in `closedGaps`): `GAP-PEER-BENCHMARK`, `GAP-ND-POP-CURRENT`, and earlier resolved items. The ledger is authority over this list.

**Before Published:** citation audit hard failures must be zero (`PUBLISH.md`). That bar is currently not met.
