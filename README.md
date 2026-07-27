# What in the Tax?

What in the Tax? is an evidence-first public-finance model and resident-facing
property-tax receipt guide.
It currently provides draft previews for six Ontario municipalities while the
Canada-wide registry and source-ingestion system are being built.

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
- The resident search now starts from Ontario's current 444-municipality list.
  Each municipality then selects its newest record from hash-pinned 2025, 2024,
  and 2023 FIR bulk files: 129 currently select 2025, 273 fall back to 2024,
  34 fall back to 2023, and 8 have no record in that window. All available
  years are retained for context. FIR records are historical filings, not
  receipts, current tax by-laws, or formal audits.
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
| `scripts/extract_pdf_text.py` | PDF to text |
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
python scripts/seal_pack.py north-dumfries-on N     # only after the full gate passes
```

**Pack status today:** all packs, including `north-dumfries-on`, are **draft previews**.
The historical `receipts/north-dumfries-on/2026/{1,2,3}` directories are retained as integrity
experiments, but they are not deployment attestations: their metadata and the deployed bytes do
not agree, their claimed release tags are absent, and their source evidence is not fully locked.
The next valid seal must be a new revision produced after every gate in `PUBLISH.md` passes.

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

**Before Published:** citation audit hard failures must be zero and every load-bearing source,
calculation, identity, public projection, and deployed byte must pass the stronger gates in
`PUBLISH.md`. That bar is currently not met.
