# Sprint Step 1 — close the evidence gaps (do ONLY this step)

Read `DIRECTOR-REVIEW.md` first. It is the director review of your last commit. Sections 1-4 are the verification results, section 6 is the sprint. This file is Step 1 only. Do not start Step 2+.

## Goal

Close `GAP-5000-BILL`, `GAP-EDUCATION-2026`, and `GAP-ND-FINAL-BUDGET` with cited FACTs.

## Why this is unblocked

Binder p.1 shows Council was scheduled to pass the **Final Full Tax Rate By-law (including Region and School Board Rates) on April 27, 2026**, and the adopted budget + Township Tax Rates By-law on **February 23, 2026**. Today is 2026-07-25. Both documents should be published.

## Tasks

1. Find and download, from northdumfries.ca (by-laws / council agendas / budget pages):
   - the **2026 Final Full Tax Rate By-law** (township + Region + school board rates), and
   - the **adopted 2026 budget**.
   Save into `source-pdfs/`. Register each in `sources` in the ledger with url, localPath, authority (`final`/`approved`), and asOf date.
2. Extract with `scripts/extract_pdf_text.py`, then add FACTs **with page + verbatim excerpt** for: the residential township rate, the Region rural/residential rate, and the **education rate**. Add the adopted levy and adopted department nets if the adopted budget changes them.
3. Update the gaps:
   - `GAP-EDUCATION-2026` -> closed, replaced by an education-rate FACT.
   - `GAP-ND-FINAL-BUDGET` -> closed if adopted figures are ingested; flip affected fact `status` from `draft` to `final`/`approved`.
   - `GAP-5000-BILL` -> **rewrite the `detail`**. Its current reason is wrong. Both figures already sit on the SAME MPAC valuation base (January 1, 2016). Binder: "properties continue to be assessed at the 2016 assessment values." Region p.12 footnote: "based on a valuation date of January 1, 2016." What differs is only which average property each government reports: $455,000 is North Dumfries' own median, $354,500 is the region-wide average. That is not a units mismatch. Say so.
   - `GAP-RURAL-HH-LINE-SUM` -> **close it as resolved source rounding**. The 23 printed rural lines sum to $2,619, the printed subtotal is $2,621, less the printed ($78) PIL gives the printed $2,543. Each line is rounded to whole dollars while the subtotal is struck from unrounded values. Not a parse error. $2,543 stays authoritative.

## Hard rules

- **Do not invent the education rate.** If the by-law cannot be found, leave `GAP-EDUCATION-2026` open, and record in the gap `detail` exactly where you looked and what you searched. A documented dead end is a correct outcome; a plausible number is not.
- No `billImpactCad` becomes non-null in this step.
- Do not build the combined receipt yet, and do not touch the township allocation base (Council & Elections / the levy reconciliation). Those are later steps and Justin has not approved the base change.
- Regenerate via `scripts/build_evidence_model.py`; do not hand-edit the JSON only. Keep `data/` and `web/src/data/` byte-identical.
- Before you finish: `cd web; npm test` and `npm run build` must both pass. The schema guards in `web/src/lib/scaleReceipt.test.ts` must stay intact — do not weaken or delete them.

## Report back

List each gap with: closed / still open, the fact IDs added, and the document + page each came from. If a document was not found, say that plainly instead of working around it.