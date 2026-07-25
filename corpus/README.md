# Corpus — jurisdiction packs

A **pack** is one municipality, one fiscal year, expressed entirely as reviewed data. There is no
central database and no service. Each pack is a directory of YAML plus committed text extracts; the
engine reads it, validates it, and emits a static receipt directory that a third party can
re-verify offline.

**`corpus/` contains data only. No code.** Anything that branches on a place name, a statute, a
currency or a by-law number belongs in the engine or in a jurisdiction plugin, never here
(`docs/GENERALIZATION-PLAN.md` §8.1).

## Layout

```
corpus/
  _template/                        scaffold — copy, never edit in place
  <slug>/                           e.g. north-dumfries-on
    municipality.yaml               jurisdiction descriptor; publication block; control total with
                                    rationale + rejected alternatives; gross/net declaration;
                                    allocation-base membership; corroboration pairs; composites
    sources.yaml                    url, retrievedAt, sha256, bytes, pageCount, archiveUrl,
                                    extractor{tool,version}, pageOffset, licence
    sources.lock                    sha256 per document — verified on every build
    facts.yaml                      FACT rows: source, pdfPage, printedRowLabel, printedValue,
                                    scaleFactor, unit, canonicalValue
    derived.yaml                    DERIVED rows as expression trees over fact ids, no bare literals
    identities.yaml                 declared invariants, per-identity tolerance, declaredUnreconciled
    gaps.yaml                       missing evidence with searchTrail and blocks[]
    findings.yaml                   Tier 2 only; absent for a Tier 0 pack
    crosswalk.yaml                  local department names to the statutory schedule
    responsibility-matrix.yaml      which body provides which service by which mechanism
    extracts/                       committed page-marked text — the verifier's ground truth
    pdf/                            local document cache, gitignored, never served
```

Slugs are lowercase, hyphenated, and carry the subdivision: `north-dumfries-on`,
`region-of-waterloo-on`. The slug is the identity used by `jurisdiction.slug`, the git tag
`pack/<slug>/YYYY.N`, and the output path `receipts/<slug>/<fiscalYear>/<revision>/`.

**An upper tier is its own pack**, referenced by id and never copied into its lower tiers. Four
Waterloo townships must resolve to one `region-of-waterloo-on` revision, or four copies of the same
regional table drift apart.

## Adding a municipality

1. **Decide whether to onboard at all.** Refused while any existing pack is past its
   `refreshDueBy`. Do not publish a municipality you are not committed to republishing next year
   (`PURPOSE.md`).
2. **`cp -r corpus/_template corpus/<slug>`.** Fill `municipality.yaml` first — jurisdiction, tier
   structure, taxing bodies, fiscal year, valuation regime, publisher, license, contact. Ontario's
   tier codes and assessment codes come straight out of FIR, so this step is mostly mechanical.
3. **Acquire sources.** Record `sha256`, `retrievedAt`, an archive snapshot URL and a checked
   licence for each. The vendor's terms govern automated access to a civic portal, not the
   municipality's. A gated portal is a permanently human-fetch municipality; never bypass a CAPTCHA.
4. **Extract every page** with the rotation-aware extractor and commit `extracts/`. Fail hard on a
   missing local path rather than skipping it — a `searchTrail` that claims "we looked" must be true.
5. **Declare the control total and the gross/net basis** in `municipality.yaml`, with the rationale
   and every rejected figure's per-household delta. The engine must never infer these and never
   default them. This step, not extraction, is what dominates the effort, and getting it wrong
   produces a receipt that ties to the cent, cites real pages, and is wrong in every published line
   (§6.1).
6. **Transcribe facts** with `pdfPage`, `printedRowLabel` and `printedValue` separate. Write
   derivations as expression trees over fact ids — a formula is the computation, not a comment about
   it.
7. **Declare identities.** At minimum: the rate columns sum to the printed total; the allocation
   residual is exactly zero; a cross-document corroboration pair. In Ontario, the FIR education-rate
   identity (education taxes ÷ residential CVA = the provincial rate within 1e-6) is a free
   per-municipality integrity gate that holds for 97.5% of taxing municipalities (§2.4) — use it.
8. **Record what is missing** as gaps with a dated search trail and `blocks[]`. A documented dead end
   is a correct outcome; an estimate is not.
9. **Build and validate.** Follow `PUBLISH.md` — hard failures block, missing evidence degrades. A
   new pack is Tier 0: receipt only, no findings.
10. **Seal and tag** `pack/<slug>/YYYY.1` (`docs/VERSIONING.md`). Publish only after the citation
    audit reports zero hard failures.

## What is committed and what is not

Committed: every YAML file, `sources.lock`, and `extracts/`. The extracts are the ground truth a
third party needs to reconcile our excerpts line by line without our tooling; keeping them out of
git makes every citation an unverifiable claim.

Not committed: `pdf/` (the local document cache, never served — see `.gitignore` and
`source-pdfs/.gitignore`) and any local review working state.

## Current state

**Bridge packs are in place:** `corpus/north-dumfries-on/pack.yaml` and `corpus/_template/`.
The living ledger still lives in `data/` (and the web mirror) until Phase 1 item 7 transcribes it to
`corpus/north-dumfries-on/*.yaml`, with acceptance = key-order-insensitive equality against the
frozen golden fixture.

```bash
python scripts/validate_pack.py north-dumfries-on   # must exit 0 before seal
python scripts/seal_pack.py north-dumfries-on 1     # refuses unless validate is green
```

`north-dumfries-on` is **draft** while citation hard failures remain (see `PUBLISH.md`).

## See also

- `PURPOSE.md` — who this is for, and what v1 refuses to do
- `PUBLISH.md` — draft, sealed, published, and the only path between them
- `docs/VERSIONING.md` — engine and pack version lines, fiscal-year roll, seal immutability
- `docs/GENERALIZATION-PLAN.md` — the specification: §8.1 packages, §9.5 hard-fail vs degrade,
  §9.6 the re-verifiable receipt directory, §11.5 publication tiers, §12 roadmap
