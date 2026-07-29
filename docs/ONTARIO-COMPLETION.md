# Getting to all of Ontario, verified

**Status:** analysis, not a commitment. Every count below was measured on 2026-07-29 against the
hash-pinned FIR bulk files already in `source-pdfs/fir/`. The commands to re-measure are in the
appendix. If a number here disagrees with the artifacts, the artifacts are right and this document
is stale — the same rule `README.md` now enforces on itself.

**Why this document exists.** The goal is every Ontario municipality on the site, as accurate as
the evidence allows, proven — and then open sourced, so contributors can extend it to the rest of
Canada and to other jurisdictions with a comparable property-tax system. That endgame changes what
has to be built first, and §6 is the part most likely to be underestimated.

---

## 1. The finding that changes the plan

**The data for all of Ontario is already on disk, already hash-pinned, already reviewed.**

`scripts/build_fir_functional_receipts.py` reads Schedule 40 (expenses by function) out of the FIR
bulk CSV. That same CSV — one file per year, already acquired, already locked, already verified
byte-for-byte in CI — carries twenty-four schedules. Two of them are the whole receipt:

| schedule | what it gives |
|---|---|
| `26A` — Taxation and Payments-in-Lieu Summary | per property class: CVA, total taxes, municipal lower/single-tier, municipal upper-tier, education |
| `22D` — Municipal and School Board Taxation | levies by tier, supplementaries, totals |

For North Dumfries, 2024, the residential class:

| | |
|---|---|
| Taxable assessment (CVA) | $1,815,031,052 |
| Municipal — lower-tier | $5,208,124 |
| Municipal — upper-tier | $11,175,909 |
| Education | $2,776,998 |
| **Total residential taxes** | **$19,161,031** |

Which is 27.2% / 58.3% / 14.5%. The hand-built 2026 gold receipt — a budget binder, a tax-rate
by-law, ten locked sources, 93 cited facts, weeks of work — says 26.6% / 60.5% / 12.9%. The
remaining difference is two years of rate changes, not a modelling failure.

**One CSV reproduces the shape of the receipt for every taxing municipality in the province.**

### Measured coverage

Municipalities with a complete, usable residential taxation row:

| filing year | taxing municipalities covered | lower-tier | single-tier |
|---|---|---|---|
| 2023 | **405** | 238 | 167 |
| 2024 | 373 | — | — |
| 2025 | 115 | — | — |

**405 is not a sample. It is the whole set.** Ontario's 30 upper-tier municipalities — the counties
and regions — appear in the data with no usable residential rate, and that is correct rather than
missing: an upper tier does not levy on CVA directly, it is apportioned through its member
municipalities. Its money shows up inside each member's receipt, exactly as Region of Waterloo does
inside the North Dumfries one.

So Ontario's taxing municipalities are 238 lower-tier + 167 single-tier = 405, and for filing year
2023 the coverage is 405 of 405. Municipalities file on their own schedule, which is why 2024 and
2025 are thinner; the site already selects each municipality's newest available year and says which
one it used.

Both figures corroborate `docs/GENERALIZATION-PLAN.md`, which estimated "~405 Ontario taxing
municipalities (238 lower-tier + 167 single-tier)". That estimate is now a measurement.

### Two integrity checks, and only one of them counts

**The weak one.** Lower-tier + upper-tier + education equals total, for every municipality, in
every year: 435 of 435, 403 of 403, 130 of 130 rows. Zero failures, against the plan's estimate of
roughly ten. **Do not over-read it.** The FIR form almost certainly computes the total as the sum
of its parts, which makes this an accounting tautology. It proves the file is internally
consistent and nothing more. Useful smoke test, bad publication gate.

**The strong one.** Ontario sets a single residential education rate province-wide — 0.153%, which
you can see printed in Waterloo's own rate table in `corpus/waterloo-on/build-inputs.yaml`. So
`education ÷ CVA` should land on that constant for every municipality, and it is a number the
municipality does not control. This tests each filing against something outside itself.

Measured:

| filing year | municipalities | median rate | within 0.001pp | within 0.005pp |
|---|---|---|---|---|
| 2023 | 405 | 0.1530% | 404 (99.8%) | **405 (100%)** |
| 2024 | 373 | 0.1530% | 371 (99.5%) | **373 (100%)** |
| 2025 | 115 | 0.1530% | 115 (100%) | **115 (100%)** |

The worst outlier anywhere in three years is 0.1494% — 2.4% off the provincial rate, on one
municipality in one year.

**This is the result that matters.** An independent check, against a provincial constant, passes
for every taxing municipality in Ontario. The FIR path is a publication route, not a research
project. The outliers are few enough to look at individually rather than model around.

---

## 2. Two products, and only one of them scales

| | FIR-derived receipt | Gold by-law pack |
|---|---|---|
| source | one provincial CSV, already locked | that municipality's budget PDF + tax-rate by-law |
| basis | prior-year actuals, PSAB accrual | current-year adopted rates |
| lag | 1–2 years, stated on the page | current |
| marginal human cost | ~0 minutes | 4–8 hours, first year |
| built today | 0 | 7 |
| reachable | 405 | as many as you personally have weeks for |

405 × 4–8 hours is roughly a person-year of document work, and next year's budgets land before you
finish. That path does not terminate.

The FIR path does. It publishes a real, cited, reproducible receipt for every taxing municipality
in the province at near-zero marginal cost, labelled honestly as prior-year actuals. The gold packs
stay what they are: a small hand-built cohort where current-year detail justifies the effort, and
the proof that the harder standard is achievable at all.

**This is the load-bearing decision in the project**, and §8 puts it to you plainly.

---

## 3. What "verified" has to mean before it can mean anything at 405

Today: **seven corpus packs, six published as drafts, zero sealed.** `PUBLISH.md` defines the path
from draft to sealed to Published, and `validate_pack.py` / `seal_pack.py` currently implement a
bridge, not the full §9.5 gate — no JSON Schema with `additionalProperties: false`, no expression
AST, no `sources.lock` verify, no two-artifact emission.

So "all of Ontario verified" cannot be scheduled yet, because verified is not yet something that
has happened once. **Seal North Dumfries first.** One municipality all the way through the real
gate is worth more than four hundred drafts, and it converts `PUBLISH.md` from a description into
a tested path.

It also forces the distinction the whole fleet depends on:

- **Machine-checkable** — hashes match, arithmetic reconciles, the cited page contains the value,
  the artifact reproduces byte-for-byte, the education rate lands on the provincial constant. These
  scale to 405 for free.
- **Human-attested** — a named person read the source and signed the claim. This does not scale,
  and pretending otherwise is the failure mode that would discredit the instrument.

A FIR-derived receipt should carry only the first kind of claim, and say so on its face. That is
not a weakness. It is the reason it can honestly cover a province.

---

## 4. The sequence

Ordered by what unblocks what. Each step is independently shippable.

**0. Finish the house before adding rooms.** The extractor rewrite surfaced nine provenance defects
in the *existing seven* packs: three declaring source PDFs that have never existed in the tree,
five extracts no source claims, and Kitchener with no source declaration at all. A process that is
not clean at n=7 will not become clean at n=405. Hours, not days, and most need a decision from you
rather than code.

**1. `taxingBodies[]` + `jurisdiction` + `publication` + `areaRateVariants[]` + `anchors[]` +
`scenarios[]`.** Phase 1 item 1. The schema assumes a lower tier beneath an upper tier. **167
single-tier municipalities cannot be represented at all** — no upper-tier row exists for them. Days
of work, touches no evidence logic, unblocks the largest single cohort, and turns the model from
"Ontario two-tier region" into "a jurisdiction with some set of taxing bodies" — which is exactly
what the open-source and other-country goals require. Highest leverage in the codebase.

**2. Seal North Dumfries.** §9.5 for real. One municipality through the full gate.

**3. `build_fir_taxation_receipts.py`.** Same shape as the Schedule 40 builder that already works:
read the locked archive member, emit one artifact per municipality per year, `--check` proves byte
reproducibility. **Wire the education-rate identity in as a hard publication gate** — refuse to emit
for any municipality whose rate misses the provincial constant, and name the refusals rather than
dropping them silently. On today's data that gate refuses nobody, which is the point: it costs
nothing now and catches the year a filing goes wrong.

**4. Publish in cohorts against a declared error budget.** Not 405 at once. Publish a cohort, state
the error budget publicly, keep a dated corrections log, and when the budget is breached stop
expanding and fix. Credibility is joint and several: one wrong receipt in a town nobody is watching
discredits the North Dumfries receipt, because the reader's inference is about the tool, not the
town.

**5. Then the open-source release.** §6 explains why it comes after, not before.

---

## 5. What blocks this that isn't code

**French.** Ontario has French Language Services Act designated areas. `docs/GENERALIZATION-PLAN.md`
scopes v1 as English-only and therefore *excludes* FLSA-designated municipalities — which means "all
of Ontario" is currently false by construction. Someone has to count that subset, decide whether
they are excluded-and-declared or blocked-until-translated, and put it on the page. Machine
translation is not an approval path, and the plan is right about why: a verbatim French excerpt in
an English UI is unverifiable to a monolingual reader, and a translation of it is no longer
verbatim. **The FACT tier itself degrades in the second language.**

**The municipalities with no FIR record.** They need a designed, visible "we have nothing for this
place" state. A 404 reads as a bug; an honest empty state reads as an instrument that knows its own
limits.

**Findings do not come with you.** Right-of-reply throughput does not scale with compute. Receipts
at 405 with findings on a hand-built cohort is coherent. Findings at 405 is a different
organisation with counsel and an editor. `packages/findings` staying default-off, and refusing to
publish anything above `watch` without a `rightOfReply` transport, is what lets the fleet grow
without the legal surface growing with it.

**Nobody but the author has read any of this code.** Survivable now. Not survivable at the point
where strangers are contributing.

---

## 6. What open sourcing actually requires

The section most likely to be underestimated, because open sourcing an evidence-first project is
not like open sourcing a normal one.

The value of this project is a single claim: **every published number traces to a reviewed source.**
The moment contributors can add municipalities, that claim is only as strong as the weakest
contribution — and no one person can review 405 pull requests, never mind several thousand across
Canada.

Which means:

**The gates have to be mechanical and unfakeable, or the project dies of its own success.** Not
"reviewers should check the citation" — a CI job that fails the pull request when the cited page
does not contain the value. `audit_citations.py` already does this. `render_readme_facts.py --check`
and `extract_pdf_text.py --check` are the same pattern. Every one of them has to exist and be
*required* before the repository is public, because after that point they are the only thing between
the project and its first confidently-wrong receipt.

**The seal path is the licence to open source.** Until draft→sealed→Published is a mechanical gate a
stranger's contribution must pass, "open source" means anyone can publish tax claims about their
neighbours under this project's name. Sealing North Dumfries is not a milestone before open source.
It is the prerequisite.

**Human attestation needs an identity model.** Some claims can only be made by a named person who
read the source. In a solo repository that person is implicit. In a public one, `reviewedAt` and
`reviewStatus` have to record *who*, and the project needs a stated policy on who may attest and
what happens when an attestation turns out to be wrong. `DIRECTOR-REVIEW.md` already publishes its
own withdrawn claims — that corrections culture is genuinely rare and is the right foundation, but
it is currently prose about one review rather than a mechanism attached to published findings.

**A contribution has to be possible without a maintainer.** The realistic contributor is a resident
who wants their own town on the site. If that requires reading 1,587 lines of Python, it will not
happen. Phase 1 item 7 — transcribing a municipality to `corpus/<slug>/*.yaml` — converts the
process from code into data, and is what makes "add your town" a pull request a non-programmer can
file. It matters more for the open-source goal than for the Ontario goal.

**Governance and liability need deciding before the repository is public.** MIT is already the
licence, which handles the code. It does not handle who is responsible when a contributor publishes
a wrong number about a real municipality under this project's name. That is a question for the
owner and, at some point, for someone with a law degree — and it is far easier to answer before
there are contributors than after.

---

## 7. Other countries

What generalises is narrower than it looks, and the plan is already clear-eyed about it.

**Generalises well:** ad-valorem property tax, assessed value × rate, multiple taxing bodies on one
bill, published rates. That is Ontario, most of Canada, and a good deal of the anglosphere.

**Breaks the current model:** Alberta's provincial education *requisition* is a dollar amount
apportioned to the municipality, not a rate the by-law prints. That single difference forces the
composition model past *"every authority publishes a rate"* — the assumption most deeply baked into
the design today. Which is exactly why the plan says Alberta second, not BC. It is the cheapest way
to find out whether the abstraction is real.

**A different product entirely:** the United States. Overlapping independent districts, separately
elected school boards, homestead exemptions, assessment caps, TIF carve-outs. None of the Ontario
abstractions survive contact. Worth doing one day; not worth designing for now.

The discipline that keeps this tractable: **do not build the general abstraction until a second
jurisdiction that needs it is actually next.** 405 taxing municipalities, 167 of them single-tier,
already exercise more of the model than a speculative union type would.

---

## 8. Decisions only the owner can make

1. **Is a prior-year, clearly-labelled, FIR-derived receipt the product for all 405 taxing
   municipalities, while a hand-built cohort keeps current-year gold packs?** If yes, all of Ontario
   is a quarter of focused work. If every municipality must meet the North Dumfries standard, it is
   not reachable by one person — better known now than at municipality forty.

2. **Are FLSA-designated municipalities excluded-and-declared, or blocked-until-translated?** The
   first is shippable this quarter and honest. The second is a translation budget.

3. **Findings: hand-built cohort only, or fleet-wide?** This is ~80% of the legal surface and it
   selects what kind of project this is.

4. **Who is the reader?** `PURPOSE.md` exists; the open question is whether it has actually been
   used to derive scope. Residents, candidates, journalists and municipal staff want four
   incompatible products. Cheapest possible test: put the existing North Dumfries receipt in front
   of twenty residents, three councillors, two clerks and two local reporters, and watch. No
   instrumentation needed at n=27.

5. **Who is responsible when a contributor publishes something wrong?** Answer before the repository
   is public.

---

## Appendix — how to re-measure everything above

Every number in this document came from the locked FIR bulk files. Nothing here required a network
call, a portal, an API key, or a single token of model inference.

```bash
python - <<'PY'
import zipfile, csv, io, statistics, collections
EXPECTED = 0.00153   # Ontario's province-wide residential education rate
for year in ('2023', '2024', '2025'):
    z = zipfile.ZipFile(f'source-pdfs/fir/fir_data_{year}.zip')
    rdr = csv.reader(io.StringIO(
        z.read(f'fir_data_{year}.csv').decode('latin-1', 'replace')))
    hdr = next(rdr)
    iA, iSLC, iAmt, iT = (hdr.index(k) for k in
                          ('ASSESSMENT_CODE', 'SLC', 'AMOUNT', 'TIER_CODE'))
    rows, tier = {}, {}
    for r in rdr:
        if len(r) <= iAmt:
            continue
        tier.setdefault(r[iA], r[iT])
        if not r[iSLC].startswith('slc.26A.L0010.C01.'):
            continue
        suffix = r[iSLC].rsplit('.', 1)[-1]
        if suffix in ('06', '16'):
            rows.setdefault(r[iA], {})[suffix] = float(r[iAmt] or 0)
    rates = {c: v['06'] / v['16'] for c, v in rows.items()
             if v.get('16', 0) > 0 and '06' in v}
    near = sum(1 for x in rates.values() if abs(x - EXPECTED) <= 0.00005)
    print(f"{year}: n={len(rates)} "
          f"tiers={collections.Counter(tier[c] for c in rates).most_common()} "
          f"median={statistics.median(rates.values()) * 100:.4f}% "
          f"within-0.005pp={near}")
PY
```

The FIR schedule identifiers used above:

- `slc.26A.L0010.C01.02` residential taxable assessment, weighted and discounted
- `slc.26A.L0010.C01.03` residential total taxes
- `slc.26A.L0010.C01.04` residential municipal taxes, lower/single-tier
- `slc.26A.L0010.C01.05` residential municipal taxes, upper-tier
- `slc.26A.L0010.C01.06` residential education taxes
- `slc.26A.L0010.C01.16` residential taxable assessment, CVA
- `slc.22D.L9990.C01.{12,13,14,15}` total levies: LT/ST, UT, education, total

Only `.07` on Schedule 40 feeds the existing functional receipts; `.03`, `.04` and `.05` do not. The
same care applies here. A column suffix is not interchangeable with its neighbours, and the
difference between `.04` and `.05` is the difference between a municipality's own levy and its
region's.
