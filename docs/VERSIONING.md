# Versioning

Two independent version lines: the **engine** (code, schema, checkers) and each **pack** (one
municipality, one fiscal year). They move at different rates for different reasons and must never
be collapsed into a single repository version.

Aligned with `docs/GENERALIZATION-PLAN.md` §8.2, §9.6 and §11.7. Publication states are defined in
`PUBLISH.md`.

## Engine

Tag: `engine/x.y.z`, semver over the pair *(schema, validator behaviour)*.

| bump | when | consequence for packs |
|---|---|---|
| **MAJOR** | Schema break, a new hard failure in `validate_pack`, a changed identity tolerance, or any change to the normalization ladder or extractor that can move a published figure. | Every pack must be rebuilt and revalidated. Sealed packs are **not** retroactively invalid — they record the engine that built them — but they may not be republished as-is. |
| **MINOR** | New capability that a conforming pack can ignore: an optional field, a new check that only degrades a tier, a new renderer. | Existing packs rebuild byte-identically. |
| **PATCH** | Fix that cannot change the output of any valid pack. | None. |

**The load-bearing rule:** if rebuilding an existing pack changes any published figure, any
`matchLevel`, any `provenanceTier` or any coverage count, it is not a PATCH. Verify against the
golden fixtures (§9.7(b)) before choosing the number, not after.

The engine records, in every `manifest.json`: `schemaVersion`, engine tag, checker version,
extractor version and normalization-ladder version. A verification result that does not name the
checker that produced it is not a verification result.

## Packs

Tag: `pack/<slug>/YYYY.N`

- `<slug>` matches `jurisdiction.slug` and the `corpus/<slug>/` directory, e.g. `north-dumfries-on`.
- `YYYY` is the fiscal-year label from `jurisdiction.fiscalYear.label`, not the year of the build.
  Where a body's fiscal year does not align with the calendar (US school districts, UK Apr–Mar), the
  label is the pack's declared label and the misalignment is stated on the receipt's face.
- `N` is the revision integer, starting at `1`, strictly monotonic per `(slug, YYYY)`, **never
  reused** even for a revision that was sealed and never published.

`pack/north-dumfries-on/2026.1` corresponds exactly to
`receipts/north-dumfries-on/2026/1/` (§9.6).

Each revision records the engine tag that built it. A rebuild under a different engine version is a
new `N`, even if every figure is unchanged — otherwise a tag stops identifying a byte sequence.

The upper tier is its own pack with its own version line (`corpus/region-of-waterloo-on/`,
`pack/region-of-waterloo-on/2026.1`), referenced by id and never copied. Four Waterloo townships
sharing one upper tier must resolve to one upper-tier revision, not four forks that drift.

### What forces a new revision

Any change to a sealed artifact's bytes: a corrected fact, a fixed citation page, a new source
retrieval, a right-of-reply response arriving, a withdrawn finding, a rebuild under a new engine
MAJOR or MINOR. Editorial changes to prose that ships in the pack count.

### What does not

Anything outside the pack: repository documentation, CI configuration, the web app's styling, a new
municipality's pack.

## Fiscal-year roll

A new fiscal year is a **new pack**, never an edit of the prior one. Copying last year's directory
and changing numbers is the failure mode this section exists to prevent, because it silently inherits
judgments that were only valid against last year's documents.

Required for every roll, each re-done rather than carried:

1. **Sources re-acquired** — new `url`, `retrievedAt`, `sha256`, `bytes`, `pageCount`, `archiveUrl`,
   and a re-checked `licence`. Municipal CMSs repost PDFs in place; last year's hash is evidence
   about last year's bytes.
2. **Extracts regenerated and committed** with the recorded extractor version.
3. **Rate and levy facts re-cited** to the new by-law, with the new by-law number. No rate, no
   assessment figure and no by-law number survives a roll by inheritance.
4. **Control total re-declared** with `chosenBy`, `chosenAt`, `rationale` and a non-empty
   `competingFigures` carrying each rejected figure's per-household delta. The prior year's choice is
   not evidence for this year's; the figures are renamed and restructured between budget books
   (§6.1, §6.9).
5. **Gross/net basis re-declared** as a structured field (§10.8, §13 Q12).
6. **Anchors and assessment basis re-cited**, including the valuation base and phase-in state.
7. **`currencyYear` set** on every amount, and a deflator fact cited before any cross-year
   comparison.
8. **Peer set re-registered and timestamped before** the metric is computed (§10.1, §10.11).
9. **Gaps re-dated.** A `searchTrail` records where we looked *and when*. Carrying a two-year-old
   trail forward asserts a search that never happened.
10. **`closedGaps` carried, never deleted**, with `resolution` and `replacedByFactIds` intact.
11. **Prior year set to lifecycle `superseded`**, left at its URL, and linked from the new pack. It
    is not deleted, redirected, or overwritten — the exact text published on a given date must stay
    reconstructable for at least the limitation period (§11.1).
12. **`validUntil` and `refreshDueBy` set** on the new pack. Onboarding is refused while any
    existing pack is past `refreshDueBy` (`PURPOSE.md`).

Run the year-over-year test as a first-class step, not an assumption. This repository contains its
own counterexample: North Dumfries' 2025 "budget book" and 2026 "draft binder" are different
document species one year apart (§6.9). Report the measured effort per roll; do not plan against a
guess.

## Seal immutability

A sealed artifact is never rewritten. Not to fix a typo, not to correct a number, not to apply a
review outcome.

- **Corrections produce `N+1`.** The wrong figure is shown **struck, not silently replaced**, at
  least as prominently and on the same surface where it appeared (§11.7). Silent editing of a
  published accusation is worse than the original error and is discoverable through archives anyway.
- **`corrections.jsonl` and `disputes.jsonl` are append-only** and carried in the pack, so the
  correction rate is publishable. A published error rate is a credibility asset; a concealed one is
  an existential risk.
- **Never force-push over a tag.** A tag that moves destroys the only cheap claim the project makes
  about its own history. If a tag is wrong, the fix is a new tag and a correction record.
- **Never reuse a revision number**, including for a sealed-but-unpublished build.
- The prior revision stays at its URL, marked `superseded`, linked forward.

The one exception is a scheduled, consented, pre-publication history operation to remove rehosted
third-party documents from git history (§6.14). It is a deliberate operation with the owner's
same-turn consent, planned before first publication — not a cleanup, and never applied to a
published pack.
