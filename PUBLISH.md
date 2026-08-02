# Publishing a pack

The word **Published** is a claim about a specific artifact, not a description of a URL. This page
defines the only path to it. Nothing may be labelled Published by any other route, including "it
looked fine in review."

Aligned with `docs/GENERALIZATION-PLAN.md` §9.5 (hard-fail vs degrade), §9.6 (receipt directory),
§11.4 (two-artifact emission) and §11.5 (publication tiers). Where this page and the plan disagree,
the plan is the specification and this page is the bug.

## Three states

| state | definition | may be labelled |
|---|---|---|
| **draft** | Any build that is not sealed. The default. May be served as a clearly draft-labelled preview at a non-canonical URL. | "draft", never "Published" |
| **sealed** | A build whose `manifest.json` exists, was written **last**, carries a sha256 for every file in the directory, agrees with disk **in both directions**, and pins its inputs (`sources.lock` verified, engine tag, pack tag). | "sealed" |
| **published** | A sealed build placed at its canonical static URL, carrying publisher, contact, license, `generatedAt`, version and the coverage table on its face, with a live corrections and dispute surface. Publication is an act performed and logged by a named human. | "Published" |

`sealed` is **not** a new value of `publication.lifecycle`, which stays
`draft | provisional | final | superseded | archived` (§8.2). Sealing is a property of the build
artifact — hashes frozen, manifest closed. A sealed build is normally lifecycle `final`, and a
sealed build that is never published is a normal and expected outcome.

Sealing asserts integrity and reproducibility. It asserts nothing about whether the control total
was the right one, and no amount of hashing ever will (§6.1).

## The only path

Every step must pass. There is no override flag, and adding one is a change to this document.

**1. Build.** Emit into `receipts/<slug>/<fiscalYear>/<revision>/` (§9.6). Two artifacts (§11.4):
the full internal ledger, which never enters a deployable bundle, and the published subset
containing only tier-eligible findings and only the facts they cite.

**2. `validate_pack`.** Refuse to emit on any hard failure in §9.5. At minimum: schema valid with
`additionalProperties: false`; every referenced id resolves; every declared identity closes inside
its declared tolerance; every derived value equals its recomputed expression tree with no bare
literal leaves; `printedValue × scaleFactor == canonicalValue`; local source sha256 matches
`sources.lock`; the control total **and** the gross/net basis are declared, never inferred and never
defaulted; `allocationBase.competingFigures` is non-empty; no JUDGMENT carries a non-null
`billImpactCad`; no T6 model-asserted fact reaches published output; every published finding is on
its tier's allowlist; the PII denylist passes against the **built bundle**, not the source JSON.

Evidence *absence* degrades instead: a weaker match level lowers the tier, an extractor split turns
the figure into a gap and the build succeeds without it, a missing peer benchmark is a gap. Fidelity
defects fail the build; missing evidence shows up as a hole. That asymmetry is the whole design.

**3. Citation audit hard failures must be zero.**

```bash
python scripts/audit_citations.py data/evidence-ledger.json   # must exit 0
```

Hard failures are `not-found`, `wrong-page` and `bad-page-number`. Zero means zero — no allowance,
no waiver, no "13 is close enough." `numbers-only` and `unverifiable` are honest weaker tiers: they
do not block publication, but they must be disclosed in `data/citation-audit.json` and on the
page, and the page must not describe them as verbatim quotations (Phase 0 item 2). Deep links
must not append `#page=` for any fact that does not verify on that page (Phase 0 item 3),
because a citation that opens the wrong page is worse than no link for the one reader who clicks.

**4. MARAI receipt — optional, and can only block.**

MARAI (the Morrow review harness) is an optional pre-publish human/model gate over wording:
headline claims, finding titles, gap language. It is not required to publish, and it can never
authorize publication.

- Model-vs-model preference between two of our own candidate sentences is **not independent
  review** and must never be described publicly as such (§6.6).
- If run, the outcome must be exported into the pack as `review.jsonl` and committed. The working
  ledger in `marai-ledger/` is local SQLite in WAL mode and is gitignored; an unexported review
  leaves a clone with no record it happened, which is the current state and the reason the one
  substantive catch was never applied.
- Every upheld claim carries `appliedInCommit`, and CI fails while any upheld claim is unapplied
  (§11.7). The unlanded "dominates" fix is the proof this is needed.
- The mechanical claim-calibration lexicon runs regardless, and a green lexicon is not a pass: five
  of eight current findings are bare enumerations carrying their adverse implication through
  juxtaposition, which no lexicon catches (§6.6, §10.6).

**5. Seal.** Write `manifest.json` last: sha256 per file, `schemaVersion`, engine version, pack
version, checker version, extractor version, normalization-ladder version, `builtAt`. Verify the
manifest against disk in both directions — a file present on disk and absent from the manifest is a
failure, so stale artifacts cannot be laundered in. Commit `rendered/`, the immutable snapshot of
the exact page published, then tag `pack/<slug>/YYYY.N` (see `docs/VERSIONING.md`).

**6. Static host.** Publish the sealed directory at its canonical immutable path. Record an
independent archive snapshot as the citation of record, with the live municipal URL as convenience
(§11.8). A sealed artifact at a canonical URL is never edited in place; corrections produce a new
revision.

## Publication tiers

The path above governs *how* a pack is published. `GENERALIZATION-PLAN.md` §11.5 governs *what* it
may contain. Every municipality starts at Tier 0 — receipt only, no findings, no gaps — and is
promoted only by an explicit logged human act. v1 posture is Tier 0 for the fleet, with Tier 2 rare
and by hand (`PURPOSE.md`).

## Current state: previews only

No current pack is Sealed or Published. The historical
`receipts/north-dumfries-on/2026/{1,2,3}` directories are retained as integrity experiments,
but revision 3 does not satisfy this document: its embedded pack metadata disagrees with its
manifest, its claimed Git tags do not exist, its source bytes/extracts are not fully locked, and
the web deployment is built from mutable source copies rather than the sealed directory.

### Share previews and the search-discovery gate

The preview may serve a canonical link and Open Graph/Twitter metadata so a deliberately shared
URL has a useful, current preview. Those tags identify the preferred URL and presentation; they do
not authorize search indexing or change a pack's lifecycle. The share image must be self-hosted,
have accurate alt text, declare its MIME type and dimensions, and show the current interface rather
than a stale campaign or donation state.

While the site remains a draft preview, both publication controls stay closed:

- `web/index.html` keeps `<meta name="robots" content="noindex, nofollow">`;
- `web/public/_headers` keeps `X-Robots-Tag: noindex, nofollow` for every response; and
- no sitemap is advertised or submitted.

Search discovery is a separate, explicit launch action. Only after the applicable seal and human
publication gates above pass may one reviewed change remove both noindex controls, add a generated
sitemap containing only approved canonical routes, reference it from `robots.txt`, and verify the
deployed headers and sitemap bytes. A share-card improvement must never bundle or imply that action.

`corpus/north-dumfries-on/pack.yaml` is therefore reset to `draft`. Citation matching may be
green while publication remains blocked; a citation audit is one gate, not a seal. The next
candidate must use a new revision and must be promoted as the exact CI-built public artifact,
without a production rebuild.

## What is not yet built

Honest inventory, so this page is not read as a description of working software:

- `scripts/audit_citations.py` exists and works today. Step 3 is real.
- `scripts/validate_pack.py` and `scripts/seal_pack.py` exist as a **bridge**: they validate the
  living `data/` artifacts named by `corpus/<slug>/pack.yaml`, refuse seal on any citation hard
  failure, and write `receipts/<slug>/<year>/<revision>/` with `manifest.json` (both-directions
  hash check). They do **not** yet implement full §9.5 (JSON Schema with `additionalProperties:
  false`, expression AST, `sources.lock` verify, two-artifact emission). Phase 0 item 8 is done:
  `build_evidence_model.py` raises `EvidenceModelError` rather than asserting (Python strips
  `assert` under `-O`, so the invariants were optional in exactly the mode a release would use),
  writes through a temp file plus `os.replace`, and checks the canonical/mirror invariant before
  either file is written rather than after.
- Full `corpus/<slug>/*.yaml` transcription (Phase 1 item 7) is not done; the pack is a descriptor
  pointing at `data/`.
- The preview interface is currently English-only. The `fr-CA` number-formatting primitives are
  not a French message catalogue, translated pack copy, or a reviewed bilingual release. A
  Canada-wide publication remains blocked until the interface, accessibility labels, dates/rates,
  and reader-facing pack narratives have complete human-reviewed French equivalents and the page
  language switches with the selected locale. Runtime machine translation is not an approval path.
- Phase 0 items 1 and 3 are done. `data/citation-audit.json` is committed, copied into the web
  bundle, and its measured tier counts render on the page as a source-check line rather than a
  claim of perfection. `#page=` is suppressed for any fact that does not verify on its cited
  page, and the suppression **fails closed**: every fact starts unverified, so a fact missing
  from the audit gets a plain source link, never a page anchor. The 13 wrong-page cites are
  fixed — including `ND-TAXATION-REVENUE-2026` and `ND-CORPORATE-REVENUES-2026`, the two
  operands of the control-total assertion, which now bind to page 9 where the rows physically
  are. Current audit: 93 facts, zero hard failures, 24 on a weaker tier, all disclosed.
- The richer `coverage.json` of §9.4 — facts per tier, checks run versus applicable — is **not**
  built. The audit's tier counts are the whole of what the page discloses today.
- MARAI export to `review.jsonl` does not exist; local `marai-ledger/` is gitignored working state.

**Today:** every pack remains **draft**. Seal and Published stay blocked until strict identity,
source-lock, calculation, public-projection, reproducibility, and deployment-byte checks all pass.
