# What in the Tax?

[![Validate sealed release candidate](https://github.com/Jstn-1g/what-in-the-tax/actions/workflows/release-validation.yml/badge.svg?branch=main)](https://github.com/Jstn-1g/what-in-the-tax/actions/workflows/release-validation.yml)
[![National rollout readiness](https://github.com/Jstn-1g/what-in-the-tax/actions/workflows/national-readiness.yml/badge.svg?branch=main)](https://github.com/Jstn-1g/what-in-the-tax/actions/workflows/national-readiness.yml)
[![License: MIT](https://img.shields.io/badge/code%20license-MIT-1f6f43)](LICENSE)
[![Corrections welcome](https://img.shields.io/badge/wrong%20number%3F-report%20it-c92f23)](https://github.com/Jstn-1g/what-in-the-tax/issues/new?template=wrong-number.yml)

What in the Tax? is an evidence-first public-finance model and resident-facing
property-tax receipt guide, live at [whatinthetax.com](https://whatinthetax.com).
Created and maintained by Justin Skowyra (Eversko), with AI-assisted
engineering under human review.

For every Ontario taxing municipality with a usable filing in the province's
own Financial Information Return — the exact counts are generated from the
artifacts further down this page — it shows who levied the property tax and
what it was spent on, rebuilt byte-for-byte from hash-locked official files in
CI. Six municipalities additionally carry hand-built draft receipts traced to
their own budget books and tax by-laws. The Canada-wide registry and
source-ingestion system this generalizes into is documented in
[CONTRIBUTING.md](CONTRIBUTING.md), with a rollout manifest already in place
for all thirteen provinces and territories.

Every displayed figure is intended to trace to a published document or to a recorded formula
over cited inputs. Explicit illustration and pro-rata models are labelled as such, and missing
evidence must remain a GAP rather than being filled.

What in the Tax? is independent. It is not affiliated with any government and
is not an official bill, formal financial audit, or source of tax advice.

Some internal schemas, historical receipts, and release documents retain the
legacy AuditBack name during migration. Those identifiers are evidence
contracts, not the resident-facing brand, and are not being renamed casually.

## Status and national boundary

- The browser is a static reader: it makes no runtime AI or government-site
  requests and collects no address, roll number, or account data.
- Six Ontario receipts are available as **draft previews**. They are not sealed
  publications.
- The national builder reproducibly loads the approved Statistics Canada SGC
  2021 baseline: 5,473 geographies, including 5,161 census subdivisions across
  all 13 provinces and territories. A checked-in, schema-validated index pins
  every allowed geography ID to the catalog-approved official release hash.
- A census subdivision is a geography, not proof of a governing body. The project
  never converts all CSDs into municipalities or governments.
- The source catalog and seven-layer coverage matrix include every province and
  territory, Statistics Canada's 2025 CSD layer, and Indigenous Services
  Canada's First Nations Location dataset. All 13 jurisdiction directory
  providers and the separate transport job are still to be implemented.
- All 13 municipal/regional onboarding packets are tracked: 11 are
  `adapter-needed`, 2 remain in `source-discovery`, and 0 are currently
  publication-ready.

<!-- generated:fir-selection -->
The resident search starts from Ontario's current 444-municipality list. Each municipality
then selects its newest record from the hash-pinned 2025, 2024 and 2023 FIR bulk files: 142
currently select 2025, 262 fall back to 2024, 32 fall back to 2023, and 8 have no record in
that window. All available years are retained for context. FIR records are historical
filings, not receipts, current tax by-laws, or formal audits.
<!-- /generated:fir-selection -->

The current milestone is therefore a hardened, zero-token national ingestion
foundation—not a claim that every Canadian governing body is already loaded.

## Deterministic national ingestion

The production path is official structured data first: API/open-data download,
content-addressed cache, immutable source lock, versioned adapter, exact-ID
crosswalk, reconciliation gates, then static browser artifacts. PDF extraction,
OCR, human review, and finally bounded AI excerpts are fallbacks in that order.
AI is disabled by default, requires explicit per-run opt-in, cannot
auto-publish, and is subject to recomputed per-packet and aggregate token/cost
ceilings.

See [`national/ARCHITECTURE.md`](national/ARCHITECTURE.md) for the data model,
coverage rules, official-source plan, and adapter contract. A national baseline
build consumes pre-downloaded, approved official bytes:

Optional exception review can use a trusted operator's existing ChatGPT/Codex
subscription without an API key or pay-as-you-go API calls. The local-only
boundary and mandatory review controls are documented in
[`docs/SUBSCRIPTION-AI-REVIEW.md`](docs/SUBSCRIPTION-AI-REVIEW.md).
Provider-neutral source mapping through signed-in subscription clients uses
quarantined candidates and the offline gate documented in
[`docs/MODEL-HANDOFF.md`](docs/MODEL-HANDOFF.md). The reviewed executable routes
use Claude for one automatic subscription-backed classification turn.
Antigravity (`agy`) can prepare a dry run or receive the same handoff manually,
but its automatic route stays disabled until it can accept the prompt through
standard input and attest the model, tool use, and per-run usage.

```powershell
python scripts/build_national_registry.py `
  --sgc-csv <official-local-csv> `
  --sgc-sha256 <catalog-approved-sha256> `
  --cache-dir <durable-cache> `
  --output <registry.json> `
  --source-lock-output <sources.lock.json>
```

The builder deliberately has no network or model client. The next expansion
milestone is an allowlisted, rate-limited transport job plus the 2025 CSD and
13 provincial/territorial directory adapters, followed by education,
Indigenous, and special-purpose taxing authorities.

## Help roll out a province or territory

The GitHub rollout path is documented in
[`docs/PROVINCIAL-ROLLOUT.md`](docs/PROVINCIAL-ROLLOUT.md). It covers every
province and territory, official source approval, adapter fixtures, exact
crosswalk review, municipality/region exceptions, count reconciliation, and
separate publication approval. Contributor setup and evidence rules are in
[`CONTRIBUTING.md`](CONTRIBUTING.md).
The status checker refuses `partial` without verified positive directory
output, and refuses publication unless actual locked source bytes, output
records freshly reproduced by the provider, pinned SGC membership, crosswalk
provenance, derived counts, and a human approval artifact all agree.

Check the machine-readable rollout manifests without downloading government
data or calling AI:

```bash
python scripts/manage_national_rollout.py check
python scripts/manage_national_rollout.py status --format json
```

Use the GitHub Province/territory rollout issue form for one jurisdiction's
municipal/regional layer at a time. A dedicated `National rollout readiness`
workflow runs the offline checks on pull requests but never deploys.

## What's included

| path | role |
|---|---|
| `data/evidence-ledger.json` | FACT / DERIVED / GAP / JUDGMENT ledger with citations |
| `data/taxpayer-receipt.json` | UI data model |
| `web/src/data/` | mirror of the two above, written by the generator |
| `scripts/build_evidence_model.py` | single source of truth — regenerates both copies |
| `scripts/extract_pdf_text.py` | PDF to text, driven by each pack's `sources[]`; `--check` verifies every committed extract still reproduces |
| `source-pdfs/` | cited source documents only |
| `national/` | national registry, source catalog, coverage gates, schemas, and AI gap policy |
| `national/sgc_2021_geography_index.json` | release-pinned allowlist of all 5,473 official SGC 2021 geography IDs |
| `scripts/build_national_registry.py` | offline, locked national registry builder |
| `scripts/build_sgc_geography_index.py` | deterministic offline builder for the pinned SGC allowlist |
| `scripts/build_ontario_municipal_history.py` | deterministic, zero-AI builder for the current 444-municipality directory with 2025 → 2024 → 2023 FIR history |
| `scripts/build_ontario_fir_public_index.py` | retained deterministic builder for the immutable 2023 FIR baseline |
| `scripts/manage_national_rollout.py` | offline jurisdiction-manifest readiness and status CLI |
| `web/` | Vite + React What in the Tax? resident guide |
| `DIRECTOR-REVIEW.md` | independent review, including corrections to its own findings |
| `docs/WHATINTHETAX-DOMAIN.md` | safe `whatinthetax.com` registration and cutover checklist |
| `docs/PROVINCIAL-ROLLOUT.md` | GitHub playbook for all 13 province/territory rollouts |
| `docs/SUBSCRIPTION-AI-REVIEW.md` | local subscription-only exception review; no API key or API billing |
| `docs/MODEL-HANDOFF.md` | provider-neutral municipal source-mapping handoff and candidate-only gate |
| `handoffs/` | hash-bound jobs, permanent prompt, and non-authoritative examples |
| `docs/` | deployment and working briefs |

## Evidence rules

- **FACT** — cited to a source with a page or URL and an excerpt. Excerpts are reconstructions unless `data/citation-audit.json` reports a verbatim (or stronger) match for that fact.
- **DERIVED** — computed only from fact IDs, with the formula recorded.
- **GAP** — missing evidence. Never invent a number to fill one. Resolved gaps move to `closedGaps` rather than being deleted, so the audit trail survives.
- **JUDGMENT** — interpretive only. `billImpactCad` stays `null`, always.
- A documented dead end is a correct outcome. Where we have searched, the gap carries a `searchTrail` recording where we looked; the open-gap list below reports how many currently do.
- Think a published figure is wrong? File it with the
  [Report a wrong number](https://github.com/Jstn-1g/what-in-the-tax/issues/new?template=wrong-number.yml)
  form — that is the report this project most wants. Outcomes, including
  reports that turn out to be sound, are logged with dates in
  [CORRECTIONS.md](CORRECTIONS.md).

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
python scripts/seal_pack.py north-dumfries-on N     # only after the full gate passes
```

**Pack status today:** all packs, including `north-dumfries-on`, are **draft previews**.
The historical `receipts/north-dumfries-on/2026/{1,2,3}` directories are retained as integrity
experiments, but they are not deployment attestations: their metadata and the deployed bytes do
not agree, their claimed release tags are absent, and their source evidence is not fully locked.
The next valid seal must be a new revision produced after every gate in `PUBLISH.md` passes.

## What the artifacts currently say

Every figure in this section and the two below is regenerated from
`data/evidence-ledger.json`, `data/citation-audit.json` and
`web/public/registry/ontario-municipal-history.json` by
`scripts/render_readme_facts.py`. Release validation runs it with `--check`, so a
count here that has drifted from the artifact behind it is a failed build rather
than a correction someone eventually notices. The prose is hand-written and
reviewed; the numbers are not, and each is bound to a ledger id so a renamed
entry fails loudly instead of quietly rewriting this page.

<!-- generated:ledger-counts -->
- Draft previews published: **6** Ontario packs.
- North Dumfries ledger: **94** facts, 30 derived rows, 8 findings, 4 open gaps, 6 closed gaps.
- Citation audit over 94 cited facts: **0** hard failures (not-found, wrong-page, bad-page-number). Binding tiers — verbatim 50, row-bound 30, normalized 12, alnum 1, numbers-only 1.
- Every finding carries `billImpactCad: null`. No exception exists in the policy and none is reachable in the builder.
<!-- /generated:ledger-counts -->

## Reconciliation

<!-- generated:reconciliation -->
The township allocation base is **10,049,624**, which ties exactly to the binder's own
published total: taxation 9,182,824 + corporate revenues 866,800, Net Budget 0.
The generator asserts this identity and so does this README renderer.

Four figures are easy to conflate and are deliberately kept distinct:

| figure | ledger id | meaning |
|---|---|---|
| 9,002,499 | `ND-LEVY-2026-ADOPTED` | municipal levy — rate × assessment, what appears on a tax bill |
| 9,182,824 | `ND-TAXATION-REVENUE-2026` | total taxation revenue — levy plus supplementaries and PILs |
| 10,049,624 | `DRV-ND-DEPT-SUM` | expenditure base — funded by taxation *plus* non-tax corporate revenue |
| 9,002,462 | `ND-BUDGET-REQUIREMENT-TAXBYLAW-2026` | the tax-rate by-law's recital, $37 below the adopted levy — recorded, not reconciled |
<!-- /generated:reconciliation -->

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
npm run dev        # http://127.0.0.1:5401 (fails closed if the port is occupied)
npm test           # vitest suite in web/
npm run build      # tsc + vite
```

```bash
python scripts/render_readme_facts.py --check   # this README still matches the artifacts
```

Test counts are deliberately not quoted on this page. A number that cannot be
kept true mechanically should not be written down: the last one drifted from 31
to 35 without anyone noticing. Run the suites.

## Known open gaps

<!-- generated:open-gaps -->
4 open, from the ledger's own `gaps` list:

- `GAP-ARENA-2026-TAX-IMPACT` — 2026 tax-bill impact of Twin Pad debt service not stated
- `GAP-BEAVER-LINE-AMOUNT` — Animal Control budget components are not itemized in the binder
- `GAP-FLAGGED-DOLLARS-ON-BILL` — Cannot allocate 'flagged/inefficient' dollars on a household bill without an explicit rule set
- `GAP-TWINPAD-OPERATING-DELTA` — Net operating cost change once Twin Pad opens is not established *(search trail recorded)*

1 of 4 carries a `searchTrail` recording where we looked. The rest record what is missing and what would close them, but not yet the search.

Closed and retained in `closedGaps` rather than deleted, so the audit trail survives (6): `GAP-5000-BILL`, `GAP-EDUCATION-2026`, `GAP-ND-FINAL-BUDGET`, `GAP-ND-POP-CURRENT`, `GAP-PEER-BENCHMARK`, `GAP-RURAL-HH-LINE-SUM`.
<!-- /generated:open-gaps -->

The ledger is authority over this list; this page only reports it.

**Before Published:** citation audit hard failures must be zero and every load-bearing source,
calculation, identity, public projection, and deployed byte must pass the stronger gates in
`PUBLISH.md`. That bar is currently not met.
