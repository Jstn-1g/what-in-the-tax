# Sprint Step 2 (CORRECTED) — tie the allocation base to the published expenditure total

**Supersedes the earlier version of this file, which was wrong.** See `DIRECTOR-REVIEW.md` section 8.

## Do NOT add Council and Elections to the base

They are already inside `TOTAL CORPORATE SERVICES`. Binder p.7 is hierarchical, not flat:
201,669 (Council) + 37,034 (Elections) + 1,841,803 + 5,300 + 5,500 = 2,091,306 exactly.
Adding them would double-count $238,703.

## The actual defect — 17,725, fully explained

- capital funded by tax levy is **1,607,500** (p.7 summary schedule), not 1,625,000 (p.43 narrative / capital table) -> 17,500
- `TOTAL ENVIRONMENTAL SERVICES` of **-225** is omitted from the base -> 225

## Tasks

1. Change the capital component of the allocation base to **1,607,500**, cited to the p.7 summary schedule. Keep a note naming 1,625,000 and where it appears — record the conflict, do not hide it.
2. Add a cited FACT for `TOTAL ENVIRONMENTAL SERVICES` = **-225** and include it in the base.
3. The base then equals **10,049,624**, which ties exactly to the binder's own `TOTAL TAXES AND CORPORATE REVENUES` (taxation 9,182,824 + corporate revenues 866,800) with Net Budget 0. Add a DERIVED row asserting that tie.
4. Do **not** tie the base to 9,002,499. That is the municipal levy (rate x assessment), a different quantity from the expenditure base. Add short notes distinguishing 9,002,499 / 9,182,824 / 10,049,624 / 9,002,462 so nobody conflates them later.
5. Disclose **Council & Elections as a nested sub-line of Corporate Services** — $34.08 of the $298.54 — with cited component FACTs. Sub-line only; it must not enter the base.
6. Add a regression test asserting the base equals the sum of its cited components AND equals taxation + corporate revenues, so this cannot drift again.

## Expected published movement (small)

Corporate $298.02→$298.54, Protective $221.56→$221.95, Public Works $353.04→$353.66, Recreation $266.12→$266.59, Planning $64.32→$64.44, Capital $231.57→$229.48, plus a new Environmental Services -$0.03. Total stays $1,434.63.

## Hard rules

No `billImpactCad` becomes non-null. `combinedTotalCad` stays null (Step 3). Every figure needs a page + verbatim excerpt or a formula over existing fact IDs. Regenerate via `scripts/build_evidence_model.py`; keep `data/` and `web/src/data/` byte-identical. Schema guards stay intact. `npm test` and `npm run build` must pass.