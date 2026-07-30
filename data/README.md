# data/

Committed evidence artifacts. Deleting any of these would turn published
citations into unverifiable claims, which is why they are in the tree rather
than gitignored (see the rationale in the root `.gitignore`).

- `evidence-ledger.json` — the North Dumfries evidence ledger: every fact, its
  source binding, and its verification state.
- `taxpayer-receipt.json` — the current (schema v2) UI data model built from
  the ledger.
- `citation-audit.json` — our own measured citation-fidelity counts, disclosed
  on the page rather than claimed as perfection.
- `_extracts/` — page-marked source text a third party can reconcile citations
  against. `_extracts/_uncited/` is local search working material and stays
  gitignored.
- `brant/`, `cambridge/`, `kitchener/`, `region-waterloo/`, `waterloo/`,
  `woolwich/` — the same ledger / receipt / audit artifacts per pack.
- `taxpayer-receipt.ui-v1.json` — **superseded, retained for the audit
  trail.** The schema-v1 receipt that predates the evidence-first rebuild. It
  contains the editorial flagging language of that era ("administrative
  bloat", "pet projects") that the current model deliberately removed; it is
  kept so the change is inspectable, not because any of it is shipped. Nothing
  in the build or the site reads this file. The project stopped deleting
  superseded artifacts on purpose (`docs/GENERALIZATION-PLAN.md`, Phase 0):
  history you can diff beats history you have to take on faith.
