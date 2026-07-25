# Generalizing the Taxpayer Receipt: What Is Needed, Missing, Good, and Bad

**Subject:** `C:/Users/User/tax-receipt-prototype` — "Taxpayer Receipt", Township of North Dumfries + Region of Waterloo, Ontario
**Question:** can this be pointed at any municipality and produce a similar report?
**Method:** seven analysis lenses and three adversarial critiques, independently re-verified against the repository on branch `cursor/fir-peers-and-population-gaps` (HEAD `52e6f25`). Where a lens and a critic disagreed, I ran the measurement myself. Several load-bearing claims in the briefing are wrong; they are corrected below before anything is built on them.

---

## 1. Blunt verdict

**What this is today:** a single, carefully hand-curated municipal finance dataset, transcribed from PDFs by one person, expressed as 1,587 lines of Python (`scripts/build_evidence_model.py`), rendered by a React screen that has North Dumfries compiled into it. There is no pipeline. There is no configuration. There is no schema. There is no jurisdiction descriptor — schema v2 has **zero** occurrences of the string `jurisdiction`, and v1 had one (`data/taxpayer-receipt.ui-v1.json`, keys `lowerTier/upperTier/province/populationCensus2021/medianAssessmentUsedInTownshipDocs`) which was deleted along with `generatedAt`. The only automation in the repo is a 32-line pypdf loop whose hardcoded 8-filename list has already drifted from the 16 PDFs on disk.

**The honest answer is neither "generalize the engine" nor "start over."** It is:

> **The evidence grammar is the product and it generalizes completely. The dataset is a golden fixture. The pipeline is a new product. And the current artifact is not yet honest enough to be the reference for either.**

Three things are true simultaneously and the plan must hold all three:

1. **The IP is real and portable.** FACT / DERIVED / GAP / JUDGMENT, with `searchTrail`, `closedGaps`, `replacedByFactIds`, `billImpactCad` permanently null, a materiality floor expressed as a ratio, right-of-reply as a schema obligation, and refuse-to-emit arithmetic identities — none of that contains a single Ontario concept. `web/src/lib/evidenceLookup.ts` contains **zero** jurisdiction strings (verified). This grammar is worth more than the North Dumfries data and more than the UI.

2. **Nothing else travels.** `web/src/types.ts:92-94` makes `township`, `region` and `education` three *required named keys*; `types.ts:103` promotes `ayrUrbanVariant` — one village of ~4,000 — into the schema. I measured Ontario's own filings: **167 of the 405 taxing municipalities (41%) are single-tier and have no `region`**. The schema cannot represent 41% of its own province on day one. That is not a future concern.

3. **Municipality #1 fails the promise municipality #1 advertises, and the project has already measured it and not disclosed it.** `data/citation-audit.json` (present, **untracked**, so absent from any clone) records of 93 facts: **10 verbatim**, 51 numbers-only, 8 normalized, 13 wrong-page, 1 alnum, 10 unverifiable. `README.md:40` still says FACT means "a verbatim excerpt." Two of the 13 wrong-page facts are `ND-TAXATION-REVENUE-2026` (9,182,824) and `ND-CORPORATE-REVENUES-2026` (866,800) — **the two operands of the control-total assertion every lens calls the crown jewel.** Refactoring the schema before fixing this freezes a candour defect into a corpus format and multiplies it by N.

**The strategic inversion.** Six of the seven lenses treat the receipt as the safe product and the findings as the risky one. That is backwards on the axis that matters. The findings carry the legal exposure; the **receipt** carries the credibility exposure, because its headline lines (`your $298.54 of Corporate Services`) are the tool's *own* pro-rata model over a denominator no municipality published as a per-household split, and its citation trail fails on a click for the facts that justify that denominator. A municipality does not sue. It publishes one true paragraph: *"this site attributes $298.54 per household to Corporate Services; that figure appears nowhere in our budget."*

**And there is no product decision anywhere.** Across ~150 findings there is not one about who reads this, not one about who pays for it, not one about year two, and not one about accessibility. No `LICENSE`, no publisher, no contact, no `generatedAt`, no version, no corrections surface — verified. Every architectural fork below is currently being decided by whichever lens argued hardest.

---

## 2. Corrections to the briefing (verify, don't trust — I did)

These are not quibbles. Three of them change the recommended v1.

### 2.1 The "57 excerpts not found anywhere" figure is wrong by ~7x

The repo's own audit finds **zero** not-found. Measured counts from `data/citation-audit.json`:

| tier | count |
|---|---|
| verbatim | 10 |
| numbers-only | 51 |
| normalized | 8 |
| wrong-page | 13 |
| alnum | 1 |
| unverifiable (no local extract) | 10 |

`numbers-only` means **the number is on the cited page** and only the wording differs. The "57" was a false-negative artifact of the very pypdf defect the same lens documented. Specifically, the accusation that `ND-DEPT-FIRE-2026`'s 1,182,646 "is not in that row at all" is **false** — the committed extract's row reads `TOTAL FIRE 976,485 1,069,867 1,119,011 805, 123 1, 182,646 63, 635`; the substring search missed it because of the injected space. **The human author was substantially more accurate than the measurement claimed.**

This matters for budget: a heavyweight verification stack (char-spans, PNG crops, geometry boxes, a six-tier provenance ladder, attestation signing keys) was proposed against a defect rate that is mostly measurement error. The real defect set is narrow — 13 wrong pages, dominated by one page-namespace bug, plus a README that mislabels reconstructions as quotations.

### 2.2 The dominant extraction failure is label-to-row binding, and both flagship controls are blind to it

I ran four extractors over binder page 9 — the department summary the entire receipt allocates from. **`pdftotext -layout` shifts every row label by one, starting at `Total Council`:**

```
Total Council                          (9,315,126) (9,626,023) (10,049,624)   ← TOTAL TAXES AND CORPORATE REVENUES' numbers
Total Elections            167,365  177,540  190,577  138,629    201,669  11,092   ← Council's numbers
Total Corporate Serv Admin  23,347   23,010   23,100   23,010     37,034  13,934   ← Elections' numbers
TOTAL CORPORATE SERVICES    34,000    4,800    5,300        -      5,300       -   ← Admin Office NDCC's numbers
Total Fire                  15,306      282    2,000               5,500   3,500   ← Earl Thompson's numbers
TOTAL FIRE               1,667,449 1,929,389 2,018,495 1,615,504 2,091,306 62,785  ← CORPORATE SERVICES' numbers
Total School Crossing Guards  4,489 1,069,867 1,119,011         1,182,646          ← Fire's numbers
```

`TOTAL FIRE = 2,091,306` (Corporate Services) and `Total School Crossing Guards = 1,182,646` (Fire). Every label is bound to the wrong department.

Now note what survives this: the numeric row order is preserved, so **every arithmetic tie-out still passes.** I verified: Council 201,669 + Elections 37,034 + Corp Serv Admin 1,841,803 + Admin NDCC 5,300 + Admin Earl Thompson 5,500 = 2,091,306 exactly. And all extractors emit the same numeric token multiset, so **2-of-3 extractor agreement also passes.** The tie-out lattice and multi-extractor agreement — the plan's two flagship correctness mechanisms — are *anti-diagnostic* for the one error class that silently destroys every published line. The receipt's entire product is the labels.

Worse for the "use a better extractor" instinct: **pypdf, the committed extractor, gets the labels right on this page** (while corrupting separators: `2, 091,306`, `1, 841,803`, `( 126,300)` — I counted 160 such tokens of 4,560 in the binder, 3.5%). The two extractors fail in disjoint ways. Majority-voting across them would let the wrong one win.

**Coordinate extraction fixes both, in ~12 lines.** PyMuPDF `page.get_text('words')`, cluster by `y0` at 2pt tolerance, sort by `x0`:

```
'TOTAL CORPORATE SERVICES 1,667,449 1,929,389 2,018,495 1,615,504 2,091,306 72,811'
'TOTAL FIRE 976,485 1,069,867 1,119,011 805,123 1,182,646 63,635'
'Total School Crossing Guards 94,030 94,589 106,438 74,990 116,292 9,854'
```

Correct labels, clean numbers, exactly reproducing the ledger's values. **The human author was right and the tooling was wrong.** Column binding is also recoverable: the `2026 Draft Budget` values sit at x≈492, against a two-level stacked header (`Actual to / Actual to / Approved / Actual to / 2026 Draft / budget to` over `12/31/2023 / 12/31/2024 / Budget / 10/31/2025 / Budget / 2026 Budget`).

**This also probably explains the DIRECTOR-REVIEW §8 error** used to justify a ~20% irreducible human error rate. `DIRECTOR-REVIEW.md:4` records that the reviewer re-extracted with `pdftotext -layout`. In that output `Total Council` appears as a top-level row carrying the `TOTAL TAXES AND CORPORATE REVENUES` figures. Concluding Council was a sibling missing from the base is the *correct reading of that text*. The reviewer's self-diagnosis ("I read a summary schedule as a flat list when it was hierarchical") describes the symptom, not the cause. So one of the two data points behind the headline error rate is a tooling bug. Do not price per-municipality sign-off off that rate until extraction is fixed and the rate is re-measured. (Keep the sign-off anyway — its justification is the control-total decision, which no extractor fixes.)

### 2.3 A hazard no lens identified: page rotation silently transposes tables

`source-pdfs/2026-04-27-council-agenda.pdf` page 103 — the tax-rate schedule the entire bill rests on — has **`rotation: 90`**. Naive y-clustering (the approach I just recommended) *transposes* it, emitting property classes as rows and rate types as columns, producing plausible-looking rate values that belong to commercial and farm classes. Clustering by `x0` instead recovers the truth:

```
'0.01201419 0.00015571 0.01185848 0.00153000 0.00717545 0.00315303 Residential RT'
```

Exactly matching all six ledger facts. **Rotation-awareness is mandatory**, and the failure mode is the signature one for this whole project: internally consistent, correctly-cited, wrong. A second trap on the same page: the row above is `... 0.00315303 Multi-Residential NEW NMT` — the NMT class carries rates *identical* to RT, so a wrong-row read here yields the right numbers by luck. Do not let luck into the verification design.

### 2.4 Ontario's FIR is far richer than the ingestion lens claimed — this changes v1

The claim "no standardized filing anywhere can produce the receipt" is **false for Ontario**. I opened `source-pdfs/fir/fir_data_2023.zip` (197,677,005-byte CSV, 18 columns, 682,127 rows) and measured:

| measurement | value |
|---|---|
| filers | 436 (238 lower-tier, 167 single-tier, 30 upper-tier) |
| rows for North Dumfries | 1,245 |
| Schedule 40 expenses, ND | **24 functions × 9 columns** (Salaries / Materials / Contracted Services / Rents & Financial / External Transfers / Interest on LTD / Amortization / Total Before Adj / Total After Adj) |
| Schedule 26A, per property class | Taxable Asmt. (CVA), Municipal Taxes LT/ST, Municipal Taxes UT, Education Taxes, ENG/FRE Public/Separate splits, phase-in columns |
| ND residential | CVA 1,741,011,393 · LT 4,792,601 · UT 9,878,098 · ED 2,663,747 |
| derived ND residential rates | LT **0.00275277** · UT **0.00567377** · ED **0.00153000** |
| median population, taxing municipalities | **6,588** (302 of 405 under 15,000) |

24 functions is **finer than the 7-department budget schedule the receipt currently allocates over.** And the education-rate identity is a genuine free asset: dividing Education Taxes by residential CVA reproduces the provincial 0.00153 **within 1e-6 for 395 of 435 filers**. The 40 exceptions are 30 upper-tier filers (which levy no education — correctly excluded) plus 8 LT and 2 ST. So it holds for **395 of 405 actual taxing municipalities (97.5%)**, fully automated, zero PDF parsing. That is precisely the "two witnesses" cross-document corroboration class the project calls its crown jewel, available province-wide, and nobody proposed it.

What FIR genuinely lacks: the *current* budget year (1–2 year lag), the adopted rates *as printed in the by-law*, capital project line items, and levy-vs-accrual basis reconciliation.

One honest caveat the critic overstated: a FIR-derived *average* residential assessment is denominator-sensitive. `1,741,011,393` divided by plausible ND dwelling counts gives **$405k–$458k** — a 13% swing around the published $455,000. Good enough to render shares; **not** good enough for a to-the-cent corroboration assertion.

### 2.5 Smaller verified corrections

- **35 tests, not 31.** `README.md:76` says 31; `npx vitest run` reports 35 passing.
- **48 near-empty pages** in the 04-27 agenda, not 42 — and each carries exactly one image, i.e. they are genuine raster scans, not vector-without-text-layer. The OCR-optimism was misplaced for *this* document; the load-bearing page 103 is born-digital.
- **`assert dept_sum == REVENUE_TOTAL` (build:765) *does* read through `_by_id[...]`** — it is fact-to-fact. The code-portability lens was wrong here. But `township_avg = 1434.63` (build:768) and `ASSESSMENT = 455_000` (build:778) *are* bare literals, while `ND-TOWNSHIP-TAX-RURAL-AVG-2026` (=1434.63) and `ND-AVG-ASSESSMENT` (=455000) both exist as facts. So assertion class 1 (base closure) is sound and **assertion class 2 (cross-document corroboration) is degraded to rate × literal == literal.**
- **`publishedFindingIds` is read by nothing but a self-referential test** (`framing.test.ts:53`); the render gate is `!finding.belowMateriality` (`TaxReceiptScreen.tsx:168`). They agree today only because `PUBLISHED_FINDING_IDS` is *derived from* `belowMateriality` at build:1275. The divergence risk is real; the current discrepancy is not.
- **Suppressed findings ship in the bundle.** `Sustainable WR`, `Heritage annual software`, `FIND-UNUSUAL-HERITAGE-SOFTWARE` and `questionable` each grep out of `web/dist/assets/index-55assK8C.js`.
- **`"dominates"` is live in five files** (`build_evidence_model.py:1185`, both `data/*.json`, both `web/src/data/*.json`). `"takes just over half"` exists only in `marai-ledger/review/pair-58314172012c/blinded-pairing.json`, which has **no `reveals.json`** (two of the four pairings do). The MARAI mechanism has never changed the repository.
- **The `billImpactCad` invariant has an escape hatch in the published policy.** `evidencePolicy.rules` reads: *"JUDGMENT: interpretive only; billImpactCad null **unless a cited formula exists**."* `README.md:43` says "always". `types.ts:68` types it `number | null`. Every lens certified this as the safest rule in the codebase.
- **README is stale on its own gaps.** It lists `GAP-PEER-BENCHMARK` and `GAP-ND-POP-CURRENT` as open; both are in `closedGaps`. Four gaps are open.
- **204 `*Cad` field-name occurrences** across 10 distinct names.
- **Nine third-party documents are tracked in git** (8 PDFs + the FIR CSV); `source-pdfs/` is 139MB on disk.
- **All 8 `townshipResponse` values are `null`.** No component reads the field.

---

## 3. What is good and must be preserved

### 3.1 The crown jewel: the evidence grammar

This is the entire reason the project is worth generalizing, and it is jurisdiction-neutral in a way almost nothing else in civic-tech is. Preserve the semantics **exactly** through any refactor:

| construct | why it is the IP |
|---|---|
| **FACT / DERIVED / GAP / JUDGMENT** | Four kinds, enforced separation. Most budget tools have one kind: "number." |
| **GAP with `searchTrail`** | *A documented dead end is a correct outcome.* `GAP-TWINPAD-OPERATING-DELTA`'s trail ends in a dated "not published in the sources searched; do not estimate it." This is the single most valuable rule in the codebase and it becomes **more** important at scale, because it is what stops a second operator re-searching or, worse, estimating. |
| **`closedGaps` with `resolution` + `replacedByFactIds`** | Resolved gaps are archived, not deleted (6 of them). The audit trail survives its own resolution. Rare and correct. Make deletion impossible in the engine. |
| **`billImpactCad: null` on every JUDGMENT** | *"This line costs you $X of your bill"* is simultaneously the most persuasive and the most indefensible claim the product could make. Make it structurally impossible — and **strike the "unless a cited formula exists" clause from `evidencePolicy.rules`**, which currently authorizes exactly that. |
| **Materiality floor as a *ratio*** | 0.25% of a declared denominator generalizes; $22,506 does not. The factoring is already right. |
| **Right-of-reply as a schema obligation** | The field is a stub, but the *decision to make it a required field* is correct and maps directly onto Grant v. Torstar's controlling diligence factor. |
| **Counter-explanation inside the finding** | `FIND-CAP-DUAL-FACILITY` records the innocent reading and is stronger for it. |
| **Refusing to decompose a pass-through** | The `education` bucket has no `lineItems` because the Province sets the rate and the Township only collects it. Exactly right for Ontario. (Inverts in the US — see §7.) |
| **`gap.blocks[]`** | A gap naming which UI features it blocks. Unusually good design. Make the engine *enforce* it: a blocked feature must not render. |
| **`forbidFillerAllocation` / `showGapsAsFirstClassUi`** | The UI is contractually committed to rendering holes. Keep, because a generalized pipeline will produce far more holes than this one does. |
| **The four-denominator distinction** | `README.md:50-57` keeps 9,002,499 / 9,182,824 / 10,049,624 / 9,002,462 deliberately distinct. Collapsing these is the most common error in citizen-facing budget tools. |
| **Recording, not reconciling, a real discrepancy** | `ND-BUDGET-REQUIREMENT-TAXBYLAW-2026` is $37 off the adopted levy and the note says so rather than picking a winner. This behaviour must become an engine-level `discrepancies[]` construct, not prose. |

### 3.2 The three assertion classes

`build_evidence_model.py` refuses to emit unless a set of published identities close. This — **not the extractor** — is why the numbers are right. Each generalizes as a *class*:

- **Class 1 — internal consistency of a published composite** (build:781-782). Components must reproduce their own printed total before anything is billed off them. Generalizes to every jurisdiction publishing a rate schedule with a printed total: Ontario Schedule A, a US county millage table, a Texas M&O + I&S notice, a UK band table with precepts.
- **Class 2 — cross-document corroboration, "two witnesses"** (build:797). The township component computed from the *final by-law* rate must reproduce the $1,434.63 published independently in the *draft budget binder*, to the cent. Two documents produced by different processes at different times forced to agree on a quantity neither states in the other's terms. **The most valuable thing in the project methodologically** — currently degraded to literal-vs-literal, and now available province-wide via the FIR education-rate identity (§2.4).
- **Class 3 — allocation-base closure** (build:765). Any pro-rata allocation must declare its denominator set *and* an independently published control total, with the residual exactly zero. Generalizes. **Which** total is correct does not — see §6.1.

### 3.3 The genuinely portable code

Lift these essentially unchanged: `web/src/lib/evidenceLookup.ts` (101 lines, **zero** jurisdiction strings — `buildEvidenceIndex`, `sourceHref` with `#page=` appending, `resolveCitation` with depth-2 recursion into DERIVED inputs, `citationLabel`); `web/src/components/FlagDetailDrawer.tsx` (118 lines, generic over Finding/Gap, correct focus trap, body-scroll lock, Escape handling, recursive nested-provenance `CitationCard`); `MarqueeFlags.tsx`; the `LineList` component and `lineTone` helper at `TaxReceiptScreen.tsx:29-128`; `combinedAtAssessment.components` — already an array, already the right shape, the exact pattern to extend to the whole receipt.

### 3.4 Two process assets worth more than they look

**The published-corrections norm.** `DIRECTOR-REVIEW.md` §0 and §8 publish the reviewer's *own* withdrawn claims, including "Acting on my recommendation would have double-counted $238,703 and shifted every published dollar in the wrong direction" (:230), plus a process note naming the recurring failure mode (:280), plus a §9 disposition table. That is a better corrections culture than most newsrooms have. It is currently prose about a *review*, not a mechanism attached to *published findings* — and the un-landed "dominates" fix is the proof.

**The `sources[]` registry with committed `extractedText`.** Committing the text derivative alongside the PDF is what makes independent line-level reconciliation possible at all — it is what let me audit 93 excerpts in one pass. The `authority` tier (`draft|approved|final|summary|external`) plus the note on `nd-2026-draft` ("Figures approved Feb 2, 2026 (By-law 3617-26) at the same municipal levy; used for department-line page cites") is a draft-vs-final distinction most people get wrong. Keep the shape; extend it (§8.3). One fix: `data/_extracts/` is **gitignored**, so the verifier's ground truth is unreviewable. Commit it.

---

## 4. What is hardcoded

### 4.1 Schema-level (breaking; fix in one pass)

| what | where | why it blocks |
|---|---|---|
| `township` / `region` / `education` as required named keys | `web/src/types.ts:92-94`; `build_evidence_model.py:1475-1499` | **41% of Ontario (167 of 405) is single-tier and has no `region`.** `TaxReceiptScreen.tsx:174` does `profile.region.lineItems ?? []` → TypeError. Separated municipalities (Guelph, Stratford, Orillia, Brantford, Cornwall) are a third case: no county levy but real apportioned DSSAB/social-services cost-shares. |
| `ayrUrbanVariant` as a typed first-class field | `types.ts:103`; `build:1512-1517` | One village of ~4,000 promoted into the schema. Every future municipality inherits an "Ayr" concept. Not rendered by any component, yet asserted by `combinedBill.test.ts:46`. |
| `education` bucket cannot hold `lineItems` | verified: keys are `basis/amountCad/assessmentCad/evidenceStatus/sourceFactId/note` only | Correct for Ontario (Province sets the rate). **Inverted in the US**, where the school district is the largest and *most* decomposable levy. |
| `hypothetical5000` as a schema key | `types.ts:117`; `build:1530` | A dollar figure promoted into a key name. Should be `scenarios: [{id, targetAmount, ...}]`. |
| 204 `*Cad` field-name occurrences, 10 names | `amountCad`, `assessmentCad`, `combinedTotalCad`, `billImpactCad`, `materialityFloorCad`, `specialAreaRateCad`, `impliedAssessmentCad`, `lineItemsSumCheckCad`, `totalCad`, `assessmentBasisCad` | Currency baked into field names. Mechanical but wide. |
| `regionalNetExpenditure000s` | `build:735-749` | A thousands scaling baked into a field name, with a manual `// 1000` at build:743-744. |
| No unit/scale field at all | 4 facts store full dollars where the source prints thousands (`ROW-LEVY-2026` = 887,329,000 from a printed `887,329 ($000's)`) | The ×1000 lives only in the author's head. No mechanical check can pass these, and none can catch the inverse — a forgotten ×1000 is a three-order-of-magnitude error that reads as plausible. |
| No `jurisdiction`, `fiscalYear`, `generatedAt`, `publisher`, `license`, `validUntil` | grep = 0 for all | v1 had `jurisdiction` **and** `generatedAt` at `taxpayer-receipt.ui-v1.json`; v2 deleted both, and `data/.gitignore` excludes the v1 file — the project already deletes superseded reasoning. |
| No `sha256`, `retrievedAt`, `pageCount`, `archiveUrl` on sources | grep = 0 | Every `url` is an unverified claim. Municipal CMSs repost PDFs in place. |
| No `taxClass` on rate facts | `build:114-172`, every rate fact excerpt is `RT Residential` | Fine for a rural residential receipt; a city needs RT/MT/NT/CT/IT/FT/PT plus subclasses, upper-tier ratios under O. Reg. 386/98, and capping/clawback. |
| No `excerptLang` / `translation` | `types.ts:20` | The verification affordance ("open the PDF and check") breaks the first time this is deployed in Quebec. |

### 4.2 Generator-level

| what | where | failure mode |
|---|---|---|
| `MATERIALITY_FLOOR = round(0.0025 * 9_002_499)` | build:1271 | Levy re-typed rather than read from `ND-LEVY-2026`. |
| `_below = {"FIND-UNUSUAL-HERITAGE-SOFTWARE", "FIND-UNUSUAL-PARTNERSHIP-FEES"}` | build:1272-1274 | The one mechanical fairness rule is a hand-maintained ID set — and it is **wrong**: `FIND-UNUSUAL-PARTNERSHIP-FEES` cites $20,000 + $5,000 + $1,725 = **$26,725**, above the $22,506 floor, and is still suppressed. `framing.test.ts:46-53` asserts that exact two-element set, locking the inconsistency in. |
| `township_avg = 1434.63`; `ASSESSMENT = 455_000` | build:768, 778 | Re-typed literals where facts exist. Degrades assertion class 2 to literal-vs-literal. |
| `label_map[row['factId']]` with no `.get()` | build:1430-1442 | KeyError on any municipality whose departments differ — i.e. all of them. |
| `region_lines` selected by `re.fullmatch(r"ROW-RURAL-HH-\d{2}")` | build:1402 | An ID-naming convention doing structural work. |
| `dept_ids` — the 7 hand-picked base components | build:752-760 | Genuinely not automatable. Must become reviewed config; the engine validates closure, never chooses members. |
| `REGION_RURAL_HH` — 23 rows × 4 numbers | build:37-61 | Upper-tier data embedded in a lower-tier build. Four Waterloo townships would fork four copies. |
| ~12 DERIVED rows computing from duplicated constants | build:916-918 (`corp = 2_091_306`, `pop = 10_619`, `pop_2025 = 13_051`), 952/961/970, 978, 994 | `formula` is a **decorative string**, never parsed, never evaluated, never cross-checked. `DRV-ND-DEPT-SUM`'s formula uses invented names (`CORPORATE + PROTECTIVE + …`) that don't correspond to its own `inputs`. `DRV-ND-BILL-AYR-SAR-455K`'s formula is `… * 455000` — the assessment base silently stops being cited evidence. |
| Bare `assert` as the only emit guard | build:765, 781-782, 797-798, 1280, 1577-1578 | Stripped under `python -O`. And 1577-1578 run **after** the files are written at 1575-1576, so a mirror-divergence failure leaves bad output on disk. |
| `FILES = [8 literal names]` | `extract_pdf_text.py:9-18` | 16 PDFs on disk. The 2025 budget book (the only available year-over-year stability test), the entire 04-13 package, and all three addenda are **never extracted** — so any `searchTrail` claiming "we looked" did not look there. Prints `missing` and continues (`:23-24`). |

### 4.3 Presentation-level

`TaxReceiptScreen.tsx` cannot render any municipality but North Dumfries: `:188` hero `What a $455,000 rural bill pays in 2026`; `:190`/`:205` `By-law 3637-26`; `:228` `Township + Region + Education at one $455,000 assessment`; `:238` `?? 455000` default and `component.rate.toFixed(8)` (right for an Ontario per-dollar rate, wrong for US mills, UK £-per-Band-D, German Hebesatz); `:275`/`:284` literal `Township portion` / `Region portion (rural household table)`; `:61-70` `shortSourceName` is seven `title.includes(...)` matches on ND/Waterloo/StatCan/FIR titles; `:176-180` `primarySources` is a hardcoded allowlist of four source IDs; `:21-25` `FINDING_TABS` fixes the taxonomy to three categories; `:29-37` `lineTone` branches on ND-shaped classification strings. `web/src/lib/format.ts:2-4` hardcodes `Intl.NumberFormat('en-CA', {currency:'CAD'})`. `web/index.html` hardcodes `lang="en"` and loads three font families from `fonts.googleapis.com` — which leaks to a third party that a given IP is reading criticism of their own council, and breaks in exactly the offline library and school contexts this tool most needs.

### 4.4 The test suite is a golden fixture masquerading as a portability guarantee

35 tests, ~40 numeric literals: `combinedBill.test.ts:5` `ASSESSMENT = 455_000`, `:34` `toBeCloseTo(5395.61)`, `:52` `toBeCloseTo(1505.47)`, `:46-50` asserts `ayrUrbanVariant` exists (which no component renders); `scaleReceipt.test.ts:18-20` `1434.63 / 2543 / 5395.61`, `:86` `toBe(10049624)`, `:90` `not.toBe(9002499)`, `:98` `+ 5300 + 5500` (two magic numbers with no source); `framing.test.ts:44` `Math.round(0.0025 * 9002499)`, `:46-53` the exact `belowMateriality` set, `:63` the literal `'not an outlier'` substring, `:67-74` the exact closed-gap set, `:34` `expect('townshipResponse' in f).toBe(true)` — key presence, not diligence.

These tests cannot tell you whether municipality #2 conforms to the model, only whether North Dumfries still produces North Dumfries' numbers. **Keep every one of these literals** — a golden fixture with parameterized expectations tests nothing — but split them into a per-municipality fixture suite and write a *separate* jurisdiction-agnostic invariant suite.

---

## 5. What is missing entirely

1. **Any acquisition layer.** `grep -riE 'requests\.|urllib|httpx|sha256|playwright|bs4'` over `scripts/` and `web/src/` returns nothing. Every PDF was placed by a human hand. No hash, no `retrievedAt`, no link checker, no re-fetch diff.
2. **Any schema.** No JSON Schema, no validator, no `additionalProperties: false`. `App.tsx:6,11` use `as unknown as`, so TypeScript checks nothing about the two JSON files it loads. `DIRECTOR-REVIEW.md:201` asked for exactly this five commits ago and documented how its absence let a one-key typo (`severitySeverity`) crash a primary UI path while tsc, the tests and the production build all stayed green.
3. **Any excerpt-verification check.** `sources[].extractedText` names a path for every PDF source and the build script **never opens it.** This is fully checkable today given the committed extracts and the `===== PAGE N =====` markers written by `extract_pdf_text.py:21`. It is the cheapest high-value check available and nobody built it.
4. **Any page-anchor check.** Nothing validates that a cited page exists or contains the value. 13 facts cite the wrong page — and `evidenceLookup.ts` appends `#page=N` to the live municipal URL, so those citations open the wrong page for the skeptical clerk who clicks first.
5. **Coordinate/geometry extraction.** No word boxes, no column-header binding, no rotation handling. This is where the engineering budget should go (§2.2, §2.3).
6. **OCR path.** `page.extract_text() or ""` and move on. 48 raster pages in the package containing the headline by-law, with no detection that a page yielded nothing.
7. **Plausibility / order-of-magnitude guards.** Every current assertion checks consistency among numbers a human already eyeballed. Nothing catches a mis-parsed 10×, a thousands-vs-units column error, a rate from the wrong column, or a sign flip.
8. **A declarative formula evaluator.** `formula` must *be* the computation, not a comment about it.
9. **A comparator object on findings.** No `comparator`, no `threshold`, no `expectedValue`, no `result`. DIRECTOR-REVIEW gate (c) exists only as prose in a review document — and empirically was not followed: five of eight findings are bare enumerations.
10. **A service-responsibility matrix.** Nothing captures which body provides which function by which mechanism. This is the hardest generalization problem in the project and there is currently *nothing* for it.
11. **A department-name → statutory-schedule crosswalk.** "Corporate Services ≈ FIR General government" is an English sentence in an `evidenceSummary`, silently absorbing an 8% gap ($1,933,805 vs $2,091,306).
12. **A mandated-vs-discretionary classification.** `grep -E 'discretionary|mandated|statutor'` over the generator returns zero. DIRECTOR-REVIEW gate (b) is unimplemented, and `DIRECTOR-REVIEW.md:307` records it as such.
13. **Assessment-base composition.** No total weighted assessment, no residential share, no tax ratios, no household counts. The only assessment facts are two single-property averages. So the moment two towns are compared, differences in commercial assessment share will be attributed to spending.
14. **A recurrence / funding-source flag.** The allocation base mixes operating nets with $1,607,500 of levy-funded capital; findings mix a $16M once-in-a-generation build with recurring $94,000 of legal fees. Nothing marks recurring / one-time / reserve-transfer / debt-financed / externally-funded.
15. **Deflators.** 2023 FIR actuals compared to 2026 budgets in nominal dollars. No `currencyYear`, no CPI fact.
16. **A right-of-reply process.** The field exists and is `null` eight times. No transport, no clock, no recipient, no log.
17. **A claim-strength check.** "dominates" against 51.9% survived a human author, a director review, a materiality pass and a language pass.
18. **Temporal identity and an archive.** No `fiscalYear`, no `generatedAt`, no lifecycle state, no per-year URL, no immutable snapshot. `App.tsx` statically imports one receipt at build time, so the app structurally holds one year for one municipality. `web/dist` is gitignored, so *the exact text published on a given date is unreconstructable* — while an Ontario online-only publisher likely faces the ordinary two-year limitation rather than the Libel and Slander Act's three months.
19. **Publisher identity, license, contact, corrections surface, error-intake channel.** `TaxReceiptScreen.tsx:419-422` renders exactly `data.status` and `data.evidencePolicyRef`. No `LICENSE`, `TERMS`, `PRIVACY`, `CORRECTIONS` anywhere.
20. **A stated user and a theory of change.** No analytics, no feedback, no `PURPOSE.md`. There are at least four plausible users wanting four incompatible products (residents / candidates / journalists / municipal staff), and at least one of them — candidates — is the "campaign artifact" use `DIRECTOR-REVIEW.md:162` says makes "the evidence discipline stop protecting you… it starts looking like a costume."
21. **Accessibility conformance.** Genuinely good: a real `prefers-reduced-motion` block (`styles.css:1031`) covering the infinite drift animation, an `@media print` block (`:790`), landmark structure, `aria-labelledby` on sections, a correct focus-trapped `role=dialog` (`FlagDetailDrawer.tsx:65-78`). Missing: `role="tablist"` declared at `:305-315` with **no `role="tabpanel"` anywhere**, no `aria-controls`, no arrow keys, no roving tabIndex (an incomplete ARIA tab pattern is worse than plain buttons — it promises keyboard semantics it doesn't implement); no skip link despite a sticky nav; `aria-live="polite"` on the *static* hero amount (`:204`); zero `prefers-color-scheme`; no axe pass, no AT testing. This is a **distribution gate**, not a checkbox: O. Reg. 191/11 s.14 binds every municipality, library and school board to WCAG 2.0 AA, so non-conformance locks the tool out of its only high-trust channels.

---

## 6. What will not work as imagined

### 6.1 "Automate the control-total choice"

North Dumfries publishes four figures within $1.05M of each other. The receipt allocates against 10,049,624 and that is correct — but establishing it took a director review, a **withdrawn claim**, and a full re-derivation. `DIRECTOR-REVIEW.md:66` asserted the base must tie to the $9,002,499 levy; `:215` withdrew it; `:254-263` records *"my instruction to tie it there was also wrong… three distinct figures and they are not interchangeable."*

A wrong denominator produces a receipt that **ties to the cent, cites real pages, satisfies every identity, and is wrong in every published line, with no visible symptom.** There is no automated detector. Every municipality has its own version of this trap under different names (US: total appropriations vs net levy vs general fund vs all funds, with the gap set by state-specific non-tax revenue and fund-accounting rules).

Declaring the winner is necessary and **insufficient** — it makes the choice auditable to someone who already knows the four figures exist, and hides from the reader that a judgment was made. **Render the rejected alternatives with the per-household dollar delta each would have produced.** Refuse to emit if `competingFigures` is empty. That is cheap, it turns the project's hardest-won insight into visible rigour, and it is the strongest available responsible-communication posture.

### 6.2 "Better extractors plus tie-outs make extraction safe"

Killed in §2.2 with measurements. `pdftotext -layout` scrambles labels on the load-bearing page; every tie-out passes; 2-of-3 numeric agreement passes; the receipt attributes Fire's budget to Corporate Services. And §2.3: rotation silently transposes the rate schedule. **Correctness must come from coordinate binding and redundancy, not from extractor quality or from voting.** Realistic ceilings: born-digital financial tables with a coordinate-aware extractor, ~85–95% cell accuracy; genuine raster scans with OCR, 60–85%, where the errors are digit substitutions (5/6, 1/7, 0/8) that pass every format check.

### 6.3 "Build the verifier now"

**Hard ordering constraint.** A span-verifier built against `data/_extracts/*.txt` is built against pypdf output — an artifact that mangles 3.5% of numeric tokens. It will reject correct facts, and the first engineer to see it fail on ~10 good facts will loosen the matcher until it accepts anything. Point it at `pdftotext -layout` instead and it will happily certify `TOTAL FIRE = 2,091,306` as *verbatim*, because that string really is in the extract. **The check does not verify the claim against the document; it verifies the claim against whichever extractor's failure mode you committed.** Fix extraction → regenerate extracts → re-run the audit → *then* write the verifier, with coordinate row/column binding as its ground truth.

### 6.4 "A six-tier provenance ladder is the public trust mechanism"

No journalist, councillor or resident reads a badge. They read a number, check one, and generalize. A single wrong T4 figure discredits the T1 population. And "every figure carries a machine-checked citation, and we publish how strong each one is" is still a categorical promise — about the apparatus rather than the numbers. The only element that converts *"we cite a page"* into *"we verified the page says this"* is the **char-span plus a rendered pixel crop**, which makes the reader the final verifier. Ship the crop; keep the tiers internal as a build gate; replace the marketing claim with two verifiable artifacts — a coverage table and a dated corrections log with a measured error rate. **A published error rate is the only credibility claim that survives being wrong.**

### 6.5 "Morrow's `verifyReceipt` can be pointed at this"

No. `packages/evidence/src/verify.ts` is 1,877 lines of experiment-specific re-derivation — arms, runs, harnesses, fixture directory hashes, lifecycle transition tables, provider probes, git patch reconciliation. Its ~60 named checks answer *"did this agent run happen as claimed."* There is no meaningful mapping from "two arms started from an identical fixture" to "this excerpt is on this page." **Reuse the primitives and the report shape, write the verifier fresh:** `canonicalJson` + `sha256Hex` (including their refusal to serialize `undefined`/`NaN` — silent coercion corrupting hashes is exactly this project's bug class), `listFilesRecursiveSync`/fixture-manifest hashing with its symlink-root rejection, `JsonlAppender`, `commitment.ts` + `firewall.ts` wholesale, and above all the *report shape*: an array of independently named checks each with ok/failed/not-applicable and a **re-derivation rather than a trust**, plus the both-directions rule (files a status doesn't imply also fail, so stale artifacts cannot be laundered in). Language boundary: the generator is Python, Morrow is TypeScript — make the ledger the interchange format and write the verifier in TS against the published JSON, which has the side benefit that it shares no code with the generator and cannot inherit its bugs.

### 6.6 "Blinded pairing is the calibration control"

Its demonstrated efficacy is **zero**. Four pairings, two with `reveals.json`; the one substantive catch never applied; `marai-ledger/` untracked in WAL-mode SQLite, so a clone has no record it happened. A mechanism that has identified a defect and never once caused a repository change is *preference elicitation*, not a control. Also: model-vs-model preference between two of your own candidate sentences is **not independent review** and must never be described as such publicly. Ship the mechanical lexicon check first, because it fires deterministically; keep blinded pairing for *tuning* the lexicon; add `appliedInCommit` and fail CI while any upheld claim is unapplied.

But do not overclaim for the lexicon either: "dominates" against 51.9% is the easy case. `FIND-ADMIN-LEGAL-STACK` — *"Multiple legal expense lines across departments"*, $94,000, `needs_review`, in the marquee — contains no superlative, no threshold, no comparator, and carries its entire adverse implication through juxtaposition under a category heading. **Five of eight findings are bare enumerations of that shape.** A lexicon passes all five and produces a green build with a control named after the problem, which is worse than no control because it substitutes for the gate that would work (§10.6).

### 6.7 "The average assessed home"

Invalid as an anchor in every acquisition-value or capped-assessment regime: California Prop 13, Florida Save Our Homes, Michigan Proposal A, Oregon Measure 50, Nova Scotia's CAP. Under Prop 13 the taxable base is a function of *when you bought*; the median long-tenure owner and the median 2025 purchaser on the same street differ by 2–4×. Publishing "what the average assessed home pays" there is worse than publishing nothing.

And even in Ontario the denominator is **not publicly obtainable**. The $455,000 is the Township's own disclosure, whose footnote says it came from **OPTA** using the *2017* Tax Impact on Median/Typical Property, Single Family Home code. OPTA is a subscription tool; MPAC roll data and property counts are not public. Most Ontario municipalities publish no average at all. Deriving it from FIR CVA ÷ dwelling counts gives $405k–$458k for ND depending on the denominator (§2.4) — good enough for shares, **structurally incompatible with a to-the-cent corroboration assertion**, which would then either be silently relaxed until it certifies nothing or refuse to emit for nearly every municipality.

### 6.8 "Enter your address, see your receipt"

Do not build it. Same feature, three different legal characters: routine in Ohio (county assessor bulk data is public), licence-encumbered in Ontario (roll inspection ≠ bulk republication; Canadian regulators have rejected "publicly available means free to use" — OPC/provincial Clearview AI finding, 2021; MPAC licenses commercially), a lawful-basis question in England. **Never accept an address.** Let the user *type* their assessed value, which is already on their bill.

But the "~0% exposure" framing is wrong on credibility. The moment a resident types their value, they compare against the bill on their kitchen table, and it will diverge — assessment phase-in, area rates (the Ayr SAR is in the schema and **never rendered**), property class, levy-vs-bill. A visible mismatch against a document the reader already trusts is the fastest and most personal falsification available, at the moment of maximum engagement. If personalization ships, ship reconciliation with it, or hold it and show shares.

### 6.9 "~45 minutes per municipality, ~5 minutes in year two"

The 45-minute Anchor Sheet has three steps — confirm pages, label columns, type tie-out targets — and contains **no step for the work that dominates**: choosing the control total, and determining whether the department figures are gross or net of departmental revenue (an *open question* in the analysis that the entire allocation rests on). It also over-assigns automatable work: a regex signature (≥6 eight-decimal rates + ≥3 property class codes) narrows 143 agenda pages to 2 candidates including the target, and the column header row extracts verbatim. **It is a real estimate of the wrong tasks.**

The year-two claim rests on documents being near-identical year over year, and **the repo contains its own counterexample**: `2025-township-of-north-dumfries-budget-book-december.pdf` (114pp, a "budget book") vs `2026-draft-budget-binder.pdf` (a differently-structured "draft binder"). Different document species, same municipality, one year apart. The one available stability test has never been run — because `extract_pdf_text.py`'s hardcoded list omits the 2025 book. And the modal target makes it worse: **median population of Ontario's taxing municipalities is 6,588; 302 of 405 are under 15,000.** These are the municipalities that change budget-book vendors and lose the clerk who built the spreadsheet.

**Publish two numbers and never average them:**

| path | first year | steady state |
|---|---|---|
| FIR-derived receipt, no findings | ~0 human minutes (one-time dwellings join) | ~0 |
| PDF current-year receipt, no findings | **4–8 hours**, dominated by control-total and gross/net determination | unknown until the 2025-vs-2026 test is run — assume 0.3–1 expert-day/year until measured |
| receipt + findings | + unbounded calendar time for right-of-reply | + monitoring and correction forever |

At 200 municipalities and a charitable 0.3 expert-days/year each, that is ~60 days/year of pure maintenance before a single new town is added. **The marginal cost does not amortize; the archive is the liability.**

### 6.10 "The receipt is legally inert, so publish 444 of them"

Killed in §1 and §11. Also: the composition of the *risk* is misread. In Canada there is **no actual-malice shield** — a plaintiff establishes publication, reference and defamatory meaning; falsity and damage are then **presumed** and the burden shifts to the publisher. The strongest available defence (responsible communication, *Grant v. Torstar*, 2009 SCC 61) names *"was the plaintiff's side sought and accurately reported"* as an explicit diligence factor. `townshipResponse` is that factor and it is a stub.

Two "reassurances" in the briefing are cost and displacement, not safety. Ontario anti-SLAPP (CJA s.137.1, *Pointes Protection*) is a real proceeding with real fees for an unincorporated publisher with no cover, and its weighing step is precisely where the current presentation hurts. And *Derbyshire* / *Montague (Township) v. Page* displacing the plaintiff from the corporation to the **individuals** is worse, not better: in a township of 13,051, "Corporate Services" is a dozen identifiable people who can sue in their own names, and a generalized tool aimed at "any town" will overwhelmingly hit small municipalities where a departmental finding identifies an individual more precisely, not less.

### 6.11 "The materiality floor protects you"

It currently does two things it was not designed to do. It ships an internal catalogue of unpublished adverse judgments about identifiable municipal staff — with a **documented ranking mechanism showing you assessed and deliberately withheld them** — and it ships a copy to every visitor's browser (`web/dist/assets/index-55assK8C.js` contains both suppressed strings). To a plaintiff that is not protection; it is a record. And at N municipalities, generated by tooling, retained indefinitely, with no entity to hold it and no retention policy.

### 6.12 "Peer comparison safeguards are an internal correctness problem"

Every proposed safeguard — pre-registered peer sets, size banding, four denominators — lives inside the publisher's process and **none survives a third party taking the data**. `App.tsx:3` imports the complete `evidence-ledger.json` into the client bundle, so at N municipalities the entire dataset for every town ships at a predictable static URL; a "most wasteful municipality in Ontario" ranking is a twenty-line script. There is no `LICENSE`, so you have no standing to object. And every non-comparability caveat lives in `evidenceSummary` prose — exactly the content a scraper drops. **There is no machine-readable field anywhere saying "this figure may not be compared with that one."** The ranking will be sourced to you, invalid by your own methodology, and most wrong for the small rural municipalities that make up most of the fleet — because their police and transit sit upstream.

### 6.13 "Multi-language is localization"

It is a schema and editorial problem. The project's central verification affordance is *"here is a verbatim excerpt, open the PDF at page N."* In Quebec the source is legally French. A verbatim French excerpt in an English UI is unverifiable to a monolingual English reader; an English translation of it is no longer verbatim. **The FACT tier itself degrades in the second language.** And machine-translating a *finding* publishes a fresh accusation in a language nobody reviewed — "dominates" vs "takes just over half" is exactly the calibration class that survived three human passes in English, and in French no reviewer will catch it. Declare the v1 language scope as English-only and therefore exclude Quebec, New Brunswick and Ontario FLSA-designated municipalities. A stated boundary is honest; a silent one is a defect.

### 6.14 "Link-don't-rehost is a cheap fix"

It is neither cheap nor sufficient. **Nine third-party documents are tracked** and the bytes are in history across pushed branches, so "stop rehosting" means a history rewrite — which this project's own rules forbid without explicit same-turn consent. Simultaneously the verifier must re-extract from byte-identical sources for the limitation period. Link-only satisfies copyright and defeats reproducibility; rehosting satisfies reproducibility and takes the amount-of-the-dealing factor (fair dealing under s.29.1 is *strong* for quoting a line with a page cite, *weak* for rehosting 35MB). Treat the history rewrite as a **scheduled, consented, pre-publication operation**, not a cleanup.

---

## 7. Jurisdictional variance — what the data model must support

`tier` labels carry **no semantic content**. Any comparison or narrative that assumes "the township does X" must be driven by a per-jurisdiction service→body map, never by code or copy. The repo's own dataset proves it: Police $900 sits in the *Region* column because Waterloo Regional Police is upper-tier; in most Ontario county-structured municipalities policing is a *lower*-tier OPP contract. Same service, same province, different tier.

### 7.1 Charge mechanics — the model can currently express only `rate × assessed value`

| mechanism | where it appears | what the schema needs |
|---|---|---|
| **AdValorem** | Ontario/BC per-dollar; US mills (per $1,000); Texas/Louisiana per $100; German Hebesatz (%) | `rateUnit` + `taxableValueBasis` (market / assessed-at-ratio / capped / acquisition-year / portioned / land-only / improvement-only) |
| **Banded** | UK council tax — England bands A–H on **1 April 1991** values, Wales A–I on 2003, Scotland A–H on 1991 with E–H multipliers uplifted 2017; statutory ratios to Band D (A 6/9 … H 18/9) | `band`, `bandRatio`, `referenceBandCharge`, and an ordered discount chain (25% single-person, CTR, disabled band reduction, empty/second-home premiums to 300%) |
| **Flat** | NZ Uniform Annual General Charge (capped at 30% of total rates); Saskatchewan base + minimum tax; BC parcel taxes (per parcel or per frontage metre); Florida non-ad-valorem MSBUs | per-parcel / per-unit / per-frontage amount + `flatShareOfBill` disclosure — the flat component is regressive relative to the ad valorem one, which is itself worth surfacing |
| **Formula** | California Mello-Roos CFD special taxes; 1915 Act assessments | value-independent adopted formula |
| **Diversion** | TIF (Chicago ~120 districts capturing >$1B/yr), PA LERTA, MO Ch. 353/99, MI IFT, NY 421-a/485-x, PILOTs | **the parcel pays the same composite rate, so the bill looks normal — but "$X of your bill funds the school district" is wrong by the diverted fraction.** Minimum handling: a jurisdiction flag forcing a GAP rather than a confident allocation |
| **Split-rate** | PA LVT municipalities (Allentown, Scranton, Harrisburg, Altoona 2011-16) | **two** AdValorem charges on one body — land millage and improvement millage |

**UK breaks the identity outright:** the tax base is denominated in **Band D equivalent dwellings**, not currency. There is no `assessed value` field to populate. And "UK" is not one model — Northern Ireland is ad valorem on 1 Jan 2005 values with a £400k cap, regional rate (Stormont) + district rate (11 councils).

**US overlapping districts cannot be modelled as a hierarchy.** Ontario's two-tier structure is nested and coterminous. A Harris County TX parcel pays 8–10 separately-governed bodies; Illinois parcels routinely 10–15; Colorado has thousands of Title 32 metro districts. **Boundaries cross** — a school district spans several cities, a fire district covers parts of three municipalities. So the composition needs `parcel → set of overlapping bodies` with a per-body `boundaryNote` (coterminous / crosses / subset), and *"which municipality am I pointed at"* itself breaks: the set of bodies is a property of the **parcel**, not the city.

### 7.2 The rest of the variance surface

| dimension | variance | schema requirement |
|---|---|---|
| **Tier structure** | ON: 238 LT / 167 ST / 30 UT (measured). Separated municipalities: no county levy but real DSSAB/social-services apportionment. QC: no upper tier. | ordered `taxingBodies[]`; `tier` is a display label only |
| **Education** | ON/BC: provincially set, pass-through (correctly non-decomposable). AB: province *requisitions* a dollar amount; separate-school supporters can direct their share. QC: single province-wide rate billed **separately** by the CSS, not on the municipal bill. US: independently governed districts, 50–60% of the bill, **the most decomposable line** | per-body `passThrough` / `allocatable` / `setsOwnBudget` flags with an evidenced reason; the UI must render a 1-line body beside a 23-line body |
| **Levy-first vs rate-first** | ON + US Midwest: adopt a dollar levy, rate falls out. CA: 1% constitutionally fixed, levy falls out | derivations must run both directions |
| **Levy limits — and this is where the *interesting finding* lives** | TX no-new-revenue / 3.5% voter-approval; MA Prop 2½ overrides and debt exclusions; MI Headlee rollback; NY/NJ 2% cap; UT certified rate; England referendum principles (~3% + 2% ASC) and, far more consequential, **proximity to a s.114 notice** (Northamptonshire, Croydon, Slough, Thurrock, Woking, Birmingham, Nottingham) | none of these map onto `administrative_scale` / `questionable_capital` / `unusual_line_items`, hardcoded as three tabs |
| **Valuation regime** | ON: MPAC frozen at **1 Jan 2016** (a temporary anomaly, not a structural truth) with 4-year phase-in when reassessment runs. BC: annual, 1 July valuation date, roll effective following 1 Jan. AB: annual, 1 July valuation / 31 Dec condition. QC: 3-year rôle by the MRC. England: 35 years stale. Bavaria post-2025: taxes **square metres** | `valuationDate`, `revaluationCycle`, `phaseInRule`, `assessorAuthority` — and the UI must be able to say "your assessment reflects 2016 prices" as a *finding*, not a footnote |
| **Sub-national variance ≥ international variance** | MB portioned assessment (residential 45%); SK percentage-of-value by class then mill rate *factors* then base/minimum tax; NS CAP. US ratios per state and per class (Cook Co. 10%/25%, SC 4%/6%, AR 20%, GA 40%, MO 19%, LA 10%, MI 50% of SEV, NYC Class 1 6%). Germany 2025: Bundesmodell value-based, Bavaria **area**-based, Baden-Württemberg land-value-only | **the config unit is `(country, subdivision, class)`. "US support" and "Germany support" are not meaningful milestones.** |
| **Fiscal year alignment** | ON calendar. US school districts overwhelmingly Jul–Jun while overlapping counties/cities are calendar or Oct–Sep. UK Apr–Mar. AU/NZ Jul–Jun | per-body `fiscalYear {label, start, end}` + an explicit on-screen statement when bodies do not align. A US receipt mixes two fiscal years and "2026" is not a well-formed label |
| **Area rating** | ON special area rates and BIA levies; NS area rates; **UK parish/town precepts — one English district can contain 60 parishes each with its own precept, which is exactly why "the average bill in that district" is meaningless**; Montréal arrondissements; US ESDs and MUDs; AU differential general rates; NZ targeted rates | `areaRateVariants[]`, arbitrary count, arbitrary additional charges |
| **Peer benchmarking availability** | **Genuinely good:** ON FIR (measured — see §2.4), BC LGS, AB MFSD, QC MAMH, England MHCLG RO/RA multi-year CSV. **Absent:** US has *no* annual standard line schedule — Census of Governments every 5 years, F-33 for school districts, ACFRs comparable only at fund level with divergent department naming. State comptroller filings (NY OSC AUD, TX, OH, CA SCO) are the best analogue: real data, 50 schemas, 50 portals. AU state-by-state; NZ DIA/StatsNZ | `peerBenchmark {available, instrument, comparabilityCaveat}`. Where absent, the honest output is the GAP this project already knows how to write. **Never fall back to name-to-name department comparison** — `docs/SPRINT-STEP-5.md` correctly calls that "invalid and worse than no comparison" |
| **Out-of-scope utilities** | ON water/wastewater rate-supported and legitimately off the tax bill. FL solid waste and stormwater are **on** it. QC water/waste `tarification` on the municipal bill. England excludes water; **Scottish councils collect water and sewerage on the council tax bill**. England's HRA is a legal ring-fence — allocating it to a council tax receipt is simply wrong | explicit `outOfScope[]` with `{label, reason, estimatedMagnitude|null}`. Understating local cost by 20–40% with no field saying so lets a reader conclude the receipt is the total cost of local government |
| **No council / no local property tax** | ON unorganized territory (Provincial Land Tax, Local Roads/Services Boards, DSSAB apportionment); BC rural areas (Surveyor of Taxes bills provincially); AB Special Areas Board; NB pre-2023 LSDs. **Different product entirely:** Sweden/Denmark fund municipalities through local *income* tax; Japan fixed asset + inhabitant tax; Ireland LPT band-based with a ±15% LAF over mostly central grant; France abolished taxe d'habitation on principal residences in 2023 and replaced commune revenue with a share of national VAT | **decide up front:** scoped to ad-valorem-and-banded local property tax jurisdictions (buildable), or "local government cost of a household" generally (a different product) |
| **Right of reply routing** | A finding may implicate a school district or hospital district, not the city — offering reply to the wrong body is worse than not offering | `subjectResponses[]` keyed by body id |
| **Records-access route** | MFIPPA (ON), provincial FOI acts, federal FOIA + 50 divergent state acts, FOIA 2000 / EIR (UK) | *"do not estimate it — request it"* is only actionable if the model knows the channel |
| **Legal/publishing regime** | see §11.1 | `canEntitySue`, `officialsCanSue`, `noticeRegime`, `limitationPeriod`, `antiSLAPP`, `burdenOnFalsity`, `publicFigureStandard`, `sourceLicence`, `personalDataRegime` |

---

## 8. Target architecture

### 8.1 Four packages

**`packages/receipt-core`** — portable, **zero place names, zero statutes, zero currency concepts**:
1. Evidence kernel — Source / Fact / Derived / Gap / ClosedGap / Finding / Discrepancy record types + Ledger builder.
2. **Declarative expression evaluator** — restricted AST (`ref(factId) | add | sub | mul | div | mean | ratio | round`), no attribute access, no bare numeric leaves except a closed set of declared dimensionless constants. `formula` **is** the computation; the human-readable string is rendered *from* the AST; `inputs[]` is derived, not hand-maintained.
3. **Identity engine** — named declared invariants with per-identity tolerance and a failure message, replacing every module-level `assert`. Plus `declaredUnreconciled` records for known discrepancies like the $37 gap.
4. Allocation engine — pro-rata over a declared base, disclosure sub-lines excluded from totals, materiality floor as a fraction of a *referenced* denominator fact, publication filter.
5. Claim-calibration lexicon (backstop only — §10.6).
6. Gap lifecycle with `searchTrail` and enforced `blocks[]`.
7. JSON Schema emission (`additionalProperties: false`, `$id` carrying schemaVersion) + version negotiation. Jurisdiction extension confined to a namespaced `ext: {}` bag validated by the pack's own schema.
8. Citation resolver — lift `evidenceLookup.ts` verbatim.

**`packages/jurisdiction-on-ca`** — six required contents:

| content | for Ontario |
|---|---|
| tax composition model | ordered taxing authorities with role (`lower_tier`/`upper_tier`/`education`/`area_rated`), rate-or-requisition mechanic, same-bill flag |
| assessment mechanics | MPAC, valuation base 2016-01-01 frozen, phase-in rule, class/ratio system, capping/clawback |
| document types + **per-platform** locators | eSCRIBE/Diligent (what ND uses — no public API; scrape the calendar for GUIDs), Legistar (real REST API at `webapi.legistar.com/v1/<client>/` — the one genuine win, mostly large US cities), PrimeGov (JSON), CivicWeb (`filepro/documents/<id>`), CivicPlus AgendaCenter (semi-guessable), BoardDocs/Novus/WordPress (pure scraping). **Even where an API exists, the document is still a PDF blob — the API gets you discovery, not data.** ~5 adapters covers 60–70% of North American municipalities *by population* and far less *by count*, because small towns are on plain WordPress |
| peer dataset adapter | FIR — `(assessmentCode, year, slcCode) → {value, sourceRef}` + a written comparability contract |
| statutory vocabulary | levy, taxation revenue, requisition, SAR, PIL, supplementary, CVA + the mandated/discretionary classifier |
| guaranteed identities | rate columns sum to printed total; Net Budget 0; **education rate = 0.00153 within 1e-6** (§2.4); levy ≠ taxation revenue ≠ expenditure base |

**`corpus/<slug>/`** — **data only, no code**: `municipality.yaml` (jurisdiction descriptor + control total with rationale and rejected alternatives + gross/net declaration + base membership + corroboration pairs + composites), `sources.yaml`, `sources.lock` (sha256 per PDF), `facts.yaml`, `derived.yaml`, `identities.yaml`, `findings.yaml`, `gaps.yaml`, `crosswalk.yaml`, `responsibility-matrix.yaml`, `pdf/` (private cache), `extracts/` (**committed**). **The upper tier is its own instance** — `corpus/region-of-waterloo-on/` referenced by id, never copied, or four Waterloo townships fork four copies of `REGION_RURAL_HH` and they drift.

**`apps/web`** — generic over `taxingBodies[]`. No place name, rate, or by-law number in any `.tsx`. A `vocabulary` block in the payload carries authority labels, tier names, document short names and a templated headline; `sources[]` gains `shortTitle` and `priority`; finding categories come from the data.

### 8.2 The schema break — do it exactly once

```
jurisdiction: {slug, name, level, parentBodies[], country, subdivision, currency, locale,
               fiscalYear{label,start,end}, valuationRegime, plugin, taxClass}
publication:  {publisher, contact, license, generatedAt, receiptVersion,
               lifecycle: draft|provisional|final|superseded|archived, validUntil, refreshDueBy}
taxingBodies: [{id, name, level, charge: ChargeSpec, amount, sourceFactId, lineItems[],
                passThrough, allocatable, setsOwnBudget, boundaryNote, fiscalYear,
                areaRateVariants[], mandatedBy}]
allocationBase: {figureId, semantic, grossOrNet, chosenBy, chosenAt, rationale,
                 competingFigures: [{figureId, label, whyRejected, perHouseholdDelta}]}
anchors:      [{id, label, kind, value, sourceFactId, cohortNote}]   // plural, each citable
Fact:         + pdfPage (machine-authoritative, the ONLY thing #page= may use)
              + printedFolio (display, nullable)
              + printedRowLabel + printedValue (replacing prose excerpt)
              + scaleFactor + unit + canonicalValue
              + matchLevel + provenanceTier + rowLabelBox/valueBox/columnHeaderBox
              + excerptLang + translation{text,translator,method,reviewedBy}
              + taxClass, currencyYear, recurrence, fundingSource
              + reviewedBy/reviewedAt/reviewMethod
Source:       + sha256, bytes, pageCount, retrievedAt, retrievedFrom, httpEtag, archiveUrl,
                extractor{tool,version}, extractSha256, textYieldPerPage, pageOffset,
                licence{id,url,permitsRedistribution,checkedAt}
Finding:      + comparator{basis,peerSetId,peerSetPreRegisteredAt,denominator,period,deflator,
                            thresholdDeclaredBefore,observed,result}
              + gates{traceable,discretionaryInLaw,comparator,rightOfReply}
              + subjectResponses[{bodyId,requestedAt,channel,recipientRole,deadlineAt,
                                  responseReceivedAt,responseText,status}]
              + materialityBasisCad, claimBand, publicationTier
Comparative:  + comparableWith[], comparabilityBasis, noPeerSetAvailable
Ledger:       + discrepancies[], outOfScope[], reviewClaims[], disputes[], corrections[]
```

Replace the three named buckets and `ayrUrbanVariant` in the same commit as the currency rename and the `hypothetical5000` → `scenarios[]` change. **The `combinedAtAssessment.components` array is already the right shape — extend that pattern to the whole receipt.** This is the highest-leverage change in the codebase and it touches no evidence logic.

### 8.3 Pipeline stages

| # | stage | automation | notes |
|---|---|---|---|
| 1 | **IDENTIFY** — name → jurisdiction, tier, parent, FIR assessment code | **automated** | Ontario's 436 filers with tier codes come straight out of FIR |
| 2 | **DISCOVER** — locate documents | assisted + **human-gated** | `source-pdfs/.gitignore` is the confession: seven packages downloaded "while searching for the tax rate by-law but NOT cited" — 3 wrong guesses out of 4, ~90MB, to find one page |
| 3 | **ACQUIRE** — fetch, sha256, archive snapshot, lock | **automated** | robots honoured, single-digit req/min, identifying UA with contact URL, per-domain allowlist with a recorded ToS review date, **no CAPTCHA bypass ever** (a gated portal is a permanently human-fetch municipality), manual-fetch as a first-class supported mode. Note the vendor's ToS governs, not the municipality's |
| 4 | **EXTRACT** — **rotation-aware coordinate** extraction, all pages, page classification (text/raster/mixed), 300dpi renders | **automated** | rebuild from scratch: PyMuPDF word boxes, cluster on the correct axis per `page.rotation`, record `textYieldPerPage`, OCR raster pages. Iterate `sources[]` as the single source of truth; **fail hard** on a missing localPath |
| 5 | **LOCATE** — per-page classifier | **automated** | tractable *because the targets have distinctive numeric signatures*: ≥6 eight-decimal rates + ≥3 two-letter class codes narrowed 143 pages to 2. Classify at **page** level, never document level. Score for `rate-schedule`, `levy-adoption`, `department-summary`, `capital-list`, `debt-schedule`, `reserve-transfers`, `valuation-note`, `upper-tier-apportionment` |
| 6 | **PROPOSE** — candidate FACTs with row/column boxes | assisted | engine **mechanically rejects** any proposal whose `printedValue` is not present at the declared box |
| 7 | **VERIFY-IDENTITIES** | **automated, hard fail** | no emit |
| 8 | **HUMAN REVIEW** — three tasks only | **human-gated, irreducible** | (a) confirm page identity from top-5 rendered thumbnails — *recognition*, ~10 min; (b) label columns from a dropdown against the **rendered image**, not the extract, because the image preserves the indentation the extract destroys — ~20 min, and this is where the hierarchy trap is caught; (c) type the **tie-out targets** by reading the printed totals off the render — ~10 min, and this is the human's real contribution because it is the redundancy that catches every extraction error |
| 9 | **DECLARE THE CONTROL TOTAL AND GROSS/NET** | **human-gated, hard emit failure if unnamed** | 1–2 days when the budget book has no Net-Budget-0 schedule. **The engine must never infer it and never default.** |
| 10 | **DERIVE** from the expression AST | **automated** | |
| 11 | **BENCHMARK** — peer set pre-registered and timestamped *before* the metric | assisted; FIR fetch automated | timestamp ordering asserted mechanically |
| 12 | **FINDINGS** — proposal assisted, approval human-gated, claim band automated | **human-gated** | **do not attempt to automate findings** |
| 13 | **RIGHT OF REPLY** | **human, out of band** | 30-day minimum; blocks publication above `watch` |
| 14 | **BUILD + PUBLISH** — two artifacts | **automated** | full internal ledger (never deployed) + published subset |

**The Anchor Sheet is a template keyed by row-label text and column-header text — not by page number or bounding box** — so a reflow degrades to a re-search rather than a re-do. State the year-2 figure as a **hypothesis with the test named**, not a planning input.

---

## 9. Verification layer

### 9.1 Ordering constraint (repeating because it is the most-violated recommendation)

**Coordinate extraction → regenerate extracts → commit extracts → re-run the audit → then build the verifier.** A verifier over the wrong extract certifies wrong numbers with a green report, which is strictly worse than no verifier (§6.3). The verifier's ground truth must be the coordinate row/column binding, and it must **re-extract from the PDFs** rather than reading the shipped text — otherwise it verifies the author's copy of reality.

### 9.2 Normalization ladder — named, versioned, unit-tested

The single most dangerous ergonomic trap in the whole layer: the first engineer to add a substring check will see it fail on ~10 *correct* facts (`2, 091,306`, `( 126,300)`, `$31, 192,121`, `202 6`), conclude the checker is broken, and loosen the matcher until it accepts anything — at which point the check exists, is green, and verifies nothing.

- **L0** byte-exact
- **L1** NFKC + whitespace collapse + quote/dash folding
- **L2** digit-run canonicalization (strip separators and currency symbols, normalize parenthesized negatives)
- **L3** ordered token subsequence within a single page — permitted **only** for facts carrying `printedRowLabel` + `printedValue` separately

Record the level that succeeded as `matchLevel`, so loosening the matcher shows up in the published data as a tier downgrade rather than invisibly in the checker. Ship the mangled strings above as the fixture corpus.

### 9.3 Provenance tiers — machine-assigned, never hand-set

`Fact.status` records how authoritative the *document* is (`draft|approved|final|summary|external`) — an orthogonal axis to how well the *number* was verified. Add `provenanceTier`, derived and re-derivable from `matchLevel`, box geometry, OCR confidence and attestation:

| tier | meaning |
|---|---|
| **T1 VERBATIM** | L0/L1-exact `printedValue` located at the declared box on the cited `pdfPage` |
| **T2 CANONICAL** | located only after declared digit-run canonicalization (the pypdf case) |
| **T3 TABLE-BOUND** | value bound to a row label **and** a column header by extracted geometry, not by text order — **this is where the engineering budget goes**, because it is the only tier that catches §2.2 and §2.3 |
| **T4 OCR** | engine, version, per-token confidence recorded |
| **T5 ATTESTED** | a named human opened the page and signed, bound to `{sourceSha256, pdfPage, printedValue}` |
| **T6 MODEL-ASSERTED** | may **never** reach published output |

A DERIVED row inherits its weakest input's tier, computed automatically. Publicly, show the **pixel crop** and one binary — *"the quoted value was located on this page: yes/no"* — plus a receipt-level coverage table. Keep the ladder internal as a build gate.

### 9.4 Extraction agreement — a sibling contract, not a preference vote

Morrow's `blindedPairing` models a human choosing between candidates (`left|right|tie|neither-acceptable`) over free-text `content`. That answers *"which framing is better."* It cannot answer *"did two extractors read the same value, unit and cell"* — there is no typed claim, no agreement predicate, and **preference-with-a-winner is precisely the wrong output: a disagreement about a number must be preserved, never resolved by vote.**

Build a sibling contract reusing `commitment.ts` and `firewall.ts` unchanged:

```
extractionClaim {sourceHash, pdfPage, rotation, rowLabel, columnHeader,
                 rowLabelBox, valueBox, columnHeaderBox,
                 printedValue, scaleFactor, unit, extractorId}
agreementRecord — computed by deterministic controller code, NOT by a model, over N≥2 claims:
   UNANIMOUS → eligible for T1/T2/T3
   SPLIT     → the fact becomes a GAP with all candidate claims attached; the number is NOT published
   ABSTAIN   → counts against the tier, not for it
```

**Critically: require agreement on the `(rowLabel, columnHeader, value)` triple, not on the numeric token multiset.** Token agreement is agreement on digits, not semantics — §2.2 is exactly the case where all extractors agree on digits and disagree on nothing detectable.

### 9.5 Hard-fail vs degrade — getting this split wrong in either direction kills the project

**HARD FAIL (refuse to emit):**
- a fact/derived/finding references a missing id
- a local source's sha256 disagrees with `sources.lock`
- cited `pdfPage` exceeds the source's page count, or contains zero extractable text with no OCR record
- a declared identity fails outside its declared tolerance
- a derived value ≠ its recomputed expression tree
- a formula leaf is a bare literal or an undeclared id
- unit mismatch across an identity's operands
- `printedValue × scaleFactor ≠ canonicalValue`
- a JUDGMENT carries non-null `billImpactCad` (and **strike the "unless a cited formula exists" clause**)
- a fact reaches published output at T6
- **the control total or the gross/net basis is undeclared**
- **`allocationBase.competingFigures` is empty**
- a published finding is not on the tier allowlist
- the manifest's file set disagrees with disk **in either direction**
- the mirror diverges from canonical (already enforced — keep, but write to temp and move atomically, and raise explicit exceptions instead of bare `assert`, which `python -O` strips)

**DEGRADE, DO NOT FAIL:**
- an excerpt matching only at a weaker level (record `matchLevel`, lower the tier)
- an extractor SPLIT → the fact becomes a GAP with candidates attached and **the build succeeds with that figure absent** — this is the mechanism that makes *"never invent a number"* operational rather than aspirational
- a finding below the materiality floor (ledger yes, published no)
- a missing peer benchmark (GAP)
- **a corroboration pair with no independently published counterpart → a first-class `assertionUnavailable` state rendered on the page, never a silent pass** (this is what keeps assertion class 2 honest where the denominator is derived — §6.7)

**WARN LOUDLY AND BLOCK PUBLISH, NOT BUILD:** coverage below a declared threshold, e.g. fewer than 90% of published figures at T3 or better.

**The asymmetry is the point: fidelity defects fail the build; evidence *absence* degrades the output.** That is the rule the project already applies to gaps, extended.

### 9.6 The receipt directory a third party can re-verify

```
receipts/<slug>/<fiscalYear>/<revision>/
  manifest.json         written LAST — sha256 per file, schemaVersion, checkerVersion,
                        extractorVersion, normalizationLadderVersion, builtAt
  sources.json          url, retrievedAt, sha256, bytes, pageCount, archiveUrl,
                        extractSha256, textYieldPerPage, pageOffset, licence
  evidence-ledger.json
  identities.json       declared identities, per-identity tolerances, declaredUnreconciled
  verification.json     one entry per named check: id, scope,
                        outcome ok|failed|not-applicable|source-unavailable, what was re-derived
  coverage.json         facts per tier, checks run vs applicable — "78 of 93 machine-verified
                        to page, 4 human-attested, 11 unverifiable — here is the list"
  attestations.jsonl    append-only, hash-chained
  review.jsonl          blinded pairings, commitments, votes, reveals, appliedInCommit
  disputes.jsonl        reader-submitted, append-only
  corrections.jsonl     dated, per-finding
  rendered/             immutable snapshot of the exact published page
```

`source-unavailable` must be a **distinct outcome** so a dead link never reads as a passed check. Publish `coverage.json` in the UI: a receipt that says *"78 of 93 figures machine-verified to page, 11 unverifiable — here is the list"* is more credible than one that claims everything traces and cannot prove it.

### 9.7 Split the test suite

**(a) Portable invariants, parameterized over any corpus:** components sum to the printed total; allocation residual is exactly zero; no finding has non-null `billImpactCad`; every gap states `neededEvidence`; every derived input resolves; every FACT has source + page-or-URL + `printedValue`; the materiality floor equals the declared ratio × the *referenced* levy fact; `belowMateriality` equals (materialityBasis < floor); severity equals the severity function's output; every published finding satisfies its tier's gates.

**(b) Per-municipality golden fixtures** — keep every ND literal exactly as it is. Freeze today's two JSON files as `fixtures/golden/north-dumfries-on-2026/` and make the refactor's acceptance criterion: *the new engine, fed the transcribed YAML, emits output equal to the golden fixture modulo key ordering.* That converts an 1,587-line hand-authored liability into the regression suite.

**(c) Denylist and suppression asserted against the BUILT BUNDLE, not the source JSON** — today the guards inspect the wrong artifact. Add: grep `dist/` for every suppressed finding id, every sub-floor dollar string, and every per-property/PII pattern.

---

## 10. Methodology spec

### 10.1 Peer selection — a declared function that emits its own audit trail

The current peer set is three hardcoded IDs (Wellesley/Wilmot/Woolwich) chosen because they share an upper tier. Convenience standing in for "same service responsibility and comparable scale."

Filter on: (1) identical service-responsibility vector; (2) identical tier structure; (3) population within a declared band or same size decile; (4) same urban/rural classification; (5) weighted-assessment-per-capita within a band; (6) same province/state so basis and statutory duties match. Emit the retained set, the rejected candidates, **and the rejection reason for each**. Require a minimum n; refuse to compute if undersized — *"no defensible peer set exists for this municipality"* must be an allowed and common output. **Pre-register before computing, with the timestamp ordering asserted mechanically**, or the peer set becomes the free parameter that produces whatever conclusion is wanted.

**Never report a ratio to an unweighted pooled mean.** The current test averages three townships across a 2.6× population range (12,253 / 23,244 / 30,909) against ND at 12,047. Per-capita: $171.72 / $172.47 / $134.37, mean $159.52; ND $160.52; ratio 1.006, published as "not an outlier." But general-government cost has large fixed components, so per-capita falls with size — visible right in this data, where the 30,909 town is 22% cheaper per capita. **ND is the smallest in the set.** Against the two peers of comparable size it is ~6.7% *below*. Pooling across 2.6× washes out exactly the confound normalization exists to remove, and the direction of the finding depends on which you use. Report instead: position within the peer range, rank, and residual from a size-controlled fit or a same-size-band subset. Cap significant figures by the peer set's own dispersion (n, min, max, IQR): a 0.6% deviation reported as `1.006` from n=3 with a 28% internal range implies a resolution the instrument does not have. **Refuse to publish a ratio whose deviation from 1.0 is smaller than the peer set's coefficient of variation.**

### 10.2 Service-responsibility normalization — the hardest problem, entirely absent

A single-tier city running its own police, transit, water, wastewater, waste, paramedics, public health and social housing is not comparable on any aggregate to a lower-tier township where all of those sit upstream — the 23 Region lines in this very receipt (Police $900, Transit $63, Paramedics $134, Housing $429, Public Health $45, Children's Services $30) are the proof.

The naive detector — "which functions have nonzero spend" — fails on the three most common Ontario arrangements: **OPP contract policing** (one contract line under protective services, not a police service), **shared-service agreements** (a transfer), and **boards/commissions** (library, police services board, conservation authority levies sit off the departmental schedule). In the US it fails on special districts, which move spend off the municipal budget entirely without changing what the resident pays.

**Required:** a versioned, machine-readable matrix per municipality — for each of ~20 functions, `{provider, mechanism ∈ direct|contract|upper-tier|board|special-district|shared, citation}` — established by human research, reviewed, cited like any other fact. **Comparisons computed only on the intersection of functions with identical provider *and* mechanism. The engine must refuse to compare aggregates at all.** One partial automation from FIR: the *set of functions a municipality reports* in Schedule 40 is itself a signal (ND reports 24; a city reports transit, police, water, social housing), so the matrix can be pre-populated and then corrected — but the *mechanism* is not derivable at any price.

### 10.3 Denominators — four, always, simultaneously

Property tax is levied on assessment, not on people. Two municipalities with identical per-capita spending produce very different residential bills if their commercial/industrial/farm assessment shares differ, because non-residential assessment (often at a higher ratio) carries part of the levy. Nothing in the model captures total weighted assessment, residential share, or ratios — the only assessment facts are two single-property averages. **This is the most likely single source of an unfair headline at scale and it is invisible at N=1.**

Compute every comparative metric on **per capita, per household/occupied dwelling, per $100,000 of CVA, and per dollar of levy** — all four. **Refuse to publish a finding whose sign or ordering flips between denominators without that flip being disclosed on the face of the finding.** One mechanical rule; generalizes the entire per-capita objection; cheap. (FIR supplies weighted and unweighted CVA by class for all 435 filers — §2.4.)

Also required: `currencyYear` on every fact; a declared, cited deflator for every cross-year derivation, with both nominal and real emitted; **refuse to compute a cross-year ratio with no deflator declared.** FIR-style returns always lag budgets by 2–3 years, so cross-vintage comparison is the normal case.

### 10.4 Basis, scope and the coincidence trap

FIR Schedule 40 "Total Expenses Before Adjustments" is **PSAB accrual**: it includes amortization and post-employment benefit accruals. `TOTAL CORPORATE SERVICES $2,091,306` is a **levy/cash-basis budget** figure containing no amortization. The finding's caveats name the *timing* mismatch and the *scope* mismatch and **never the basis mismatch, which is the largest of the three** and can move the number by double digits depending on capital intensity. Add a structured `accountingBasis` and **refuse to compute a ratio across two bases** without an explicit reconciliation or a basis-mismatch disclosure on the face of the finding. (This is general wherever a statutory accrual return coexists with a cash/levy budget — PSAB in Canada, GASB in the US.)

Then the coincidence trap: `FIND-ADMIN-CORP-SCALE`'s summary places `$160.52/capita` (2023 FIR accrual / 2023 population) next to `~$160/capita` (2026 budget levy-basis / 2025 population = 2,091,306/13,051 = $160.24) in adjacent sentences. They agree to within $0.28 **across three simultaneous differences.** A reader — including a hostile one, including the next engineer — reads that as two independent measurements converging. It is coincidence. **Two figures may be presented as mutually confirming only if they share year, basis and scope**; otherwise separate labelled blocks with the differences enumerated, and the engine must not place them in the same sentence.

### 10.5 Materiality — on levy-borne dollars, in the receipt year

Ranking each published finding by gross cited amount against actual 2026 levy burden:

| finding | gross | 2026 levy impact | published |
|---|---|---|---|
| `FIND-CAP-ARENA` | $16,190,160 | **~$0** (grant/debt/DC/fundraising — asserted by the model's own `GAP-ARENA-2026-TAX-IMPACT`) | yes, `high_attention`, marquee #1 |
| `FIND-CAP-DUAL-FACILITY` | $3,500,000 | $1M provincial grant, "residual from reserve accounts rather than the levy" | yes |
| `FIND-CAP-PUMPTRACK` | $568,756 | **$70,000 township cash (12.3%)** — i.e. the tool flags residents' own charitable giving | yes |
| `FIND-UNUSUAL-PARTNERSHIP-FEES` | $26,725 | presumably levy-funded | **suppressed** |

**The published set is ordered almost inversely to levy impact.** This is a *taxpayer* receipt, so materiality must be measured on levy-borne dollars in the receipt year, with gross project cost disclosed separately. Measured on gross, an externally funded project always outranks a levy-funded one, and the tool systematically prosecutes the lines the taxpayer is *least* paying for — the most rebuttable possible failure mode, and it scales to every municipality with grant-funded capital.

Give every finding `materialityBasisCad` (decide sum-or-max of cited amounts and **write it down**), derive `belowMateriality` by comparison against a floor computed from a *referenced* levy fact, delete `_below` and rewrite `framing.test.ts:46-53` to assert the **rule**. And the floor rate itself needs a shape that scales: 0.25% of the levy is ~$2,250 for a $900k-levy village (restoring exactly the $1,725 problem the floor was invented to solve) and ~$10M for a large city (an entire department below it). Use `max(rate × denominator, absoluteFloor)` plus a per-household expression so the floor is legible — *"below $1 on your bill."* Declare **which** denominator: the build uses the levy for the floor and the expenditure base for the receipt, 10% apart here and more elsewhere.

### 10.6 Claim calibration — the comparator template is the gate

Severity is nine hand-typed strings (`'watch'` ×6, `'needs_review'`, `'high_attention'`), typed as bare `string`, derived from nothing — yet it drives the marquee, the CSS class `severity-${...}` and the drawer heading. It is the field that carries the accusation, so it is precisely the field that must not be a matter of taste. **Severity = a pure function of (materiality band) × (comparator result vs pre-declared threshold) × (evidence status of underlying lines) × (right-of-reply status)**, computed in the generator, asserted, unwritable by hand. **Any finding lacking a comparator caps at the lowest band by construction.**

Then the publication gate, which is the real control:

> **X is $A on basis B, versus comparator C of $D drawn from pre-registered peer set E, a difference of F%, exceeding/not exceeding pre-declared threshold G. The municipality's explanation is H, or was requested on I and not received.**

**Anything that cannot fill this template is an internal observation and gets no category label — because the category label is itself the claim.** Five of eight current findings are bare enumerations: *"Identified legal lines sum to $94,000." "Community grants $40,000; Ayr Cemetery $10,000; Sheffield Lions $3,500." "Heritage annual software licensing $5,000." "$568,756 total; Township cash $70,000."* None states what the amount should be or what would falsify it. The entire adverse implication is carried by listing them under headings named `unusual_line_items` and `questionable_capital`. **That is unfalsifiable by construction** — there is nothing to rebut — and it is the form of unfairness hardest to see from inside the project, because every individual number is a verified FACT.

The lexicon (`'majority' ≥50%`, `'dominates'/'overwhelmingly' ≥75%`, `'largest single' = rank 1 with no share claim`), asserted against the finding's own cited derived value with refuse-to-emit, is a **backstop only**. Also retire `questionable` from the schema vocabulary — `DIRECTOR-REVIEW.md:167` directed it ("Questionable invites 'by whom?'"), it is currently mapped to the neutral tab label `Capital` so it does not reach the DOM, but it is what a journalist reading your data model sees as your own name for the category, and it propagates to any export or feed.

### 10.7 Symmetric epistemics — three outcomes, not two

`FIND-ADMIN-CORP-SCALE` was correctly downgraded but did not become silent — it became an assertion in the **opposite** direction, and `framing.test.ts:63` now *requires* the string `'not an outlier'`. If $160.52 against an unweighted 3-town mean with a 28% internal range, across a year gap, a basis gap and a scope gap, cannot establish "large," then **by symmetry it cannot establish "not an outlier."** A weak instrument licenses neither direction. Three outcomes: **supported / not supported / indeterminate.** The honest title is *"Corporate Services scale: peer test inconclusive on available data."* Getting this wrong in the exculpatory direction is less legally risky and destroys credibility just as fast, because it shows conclusions are drawn to whatever strength the author prefers.

Relatedly: `DRV-ND-ARENA-PER-CAPITA` = $1,524.64 divides a lifetime capital cost by one year of population. The project knows — the `evidenceSummary` says "SECONDARY only" and "overstates the annual burden" — but the number still exists with a stable ID, a formula, a dollar sign, and is cited by the published `high_attention` marquee finding. **Prose demotion does not survive a screenshot, a quotation, or a second developer reading the ledger.** Add `notForPublication`, assert it, and prefer simply not minting the ID.

### 10.8 Pro-rata is a model, not a derivation

The receipt allocates `round(township_avg * dept_amount / dept_sum, 2)` where `dept_sum = 10,049,624 = taxation 9,182,824 + corporate revenues 866,800`. That spreads ~$1,047,125 of **non-levy** revenue uniformly across departments in proportion to expenditure. Real cost recovery is wildly uneven and partly statutory: building permit activity must be fee-funded and separately reserved under the Building Code Act; recreation carries user fees; water/wastewater is usually rate-funded entirely outside the levy.

**Use published department-level NET LEVY REQUIREMENT wherever the municipality publishes it (most do).** Where it does not, the pro-rata fallback must be labelled a distinct tier — **`MODEL` or `ALLOCATED`, not `DERIVED`** — must state the assumption on the face of the line, and must be **excluded from any cross-municipal comparison**. Two municipalities using different fallbacks are not comparable at the line level. And print the published department total beside each allocated line; never set an allocated dollar in larger type than the published figure it derives from.

Unresolved and blocking: **are the p.7 department figures gross expenditure or net of departmental revenue?** The identity `8,442,124 + 1,607,500 = 9,182,824 + 866,800` is consistent with "net of departmental revenue, before corporate revenue," but the labels are bare and the excerpts do not disclose it. If they are gross, every line is wrong in a direction that varies by cost recovery. **This must be a declared structured field, not inferred from an identity — because in the next municipality the identity may hold for a different reason and the code would happily proceed.**

### 10.9 Forbidden auto-findings — enforced in code

These require local context a machine cannot have. **The current build already ships four classes a machine must never generate unaided:**

- **(a) duplication/overlap between two capital projects** — `FIND-CAP-DUAL-FACILITY` is exactly this, and DIRECTOR-REVIEW called it "the single most rebuttable finding in the set"
- **(b) grants and transfers to named community organizations** — `FIND-UNUSUAL-GRANTS` names Ayr Cemetery and Sheffield Lions, real local bodies with no capacity to reply
- **(c) projects majority-funded from outside the levy** — `FIND-CAP-PUMPTRACK` is 87.7% donations and fundraising
- **(d) "unusual line item" grounded only in an unfamiliar label** — `FIND-UNUSUAL-HERITAGE-SOFTWARE` is a $5,000 software licence, unremarkable anywhere

Also forbid: staffing levels or compensation; anything naming an individual or vendor; any "this service should not be provided" thesis; any cross-municipal "worse than" claim where the responsibility matrix differs; any department-level judgment where `unknown` is the mandated/discretionary classification; **any department-level judgment below a size threshold** (§11.2). Implement as a hard predicate over `(category, cited fact attributes, funding source, named-entity detection, staff/population size)` raising at generation time. In a small municipality every "unusual line item" is a dozen identifiable people, and the engine cannot know which of them a resident is about to meet at the arena.

### 10.10 Gaps are a publication surface and must be governed like one

`TaxReceiptScreen.tsx:350-372` renders **every** open gap verbatim to the public, styled `severity-watch`. `framing.test.ts` checks only `neededEvidence.length > 0`, that a `searchTrail` exists, and that resolutions exceed 40 characters. **Nothing checks gap language.** And the gaps are where the author's unproven hypotheses live. `GAP-BEAVER-LINE-AMOUNT` is live and public: *"Beaver extraction spend not isolated as its own budget line amount… Narrative mentions external contractors for beaver extraction; no discrete dollar line extracted."* That sentence asserts the existence of a spend, attaches an implicitly absurd characterisation, and concedes it cannot be quantified — **a published insinuation the project's own finding rules would forbid**, and the clearest available evidence of intent for a fair-comment analysis.

**A gap must name a missing DOCUMENT or an unverifiable MODEL STEP, never a suspected behaviour.** Rewrite as *"narrative-only items in the Public Works budget cannot be tied to discrete line amounts."* Apply the denylist and the finding template to gap titles and details. Publish only gaps that blank a specific receipt line; keep hypothesis-driven gaps internal. And extend the GAP record with acquisition provenance — which adapter ran, which packages were fetched and hashed, which candidate pages were shown and rejected, whether the page was raster, whether extractors split — so *"we looked in these 4 packages and these 12 candidate pages, and 3 were image-only"* is a far stronger claim than "missing," and is re-runnable.

### 10.11 Make non-comparability machine-readable and refusal the default

Nobody proposed this and it is the structural answer to §6.12: every comparative metric carries `comparableWith: [municipalityIds]`, `comparabilityBasis`, and a hard `noPeerSetAvailable` flag, **computed from the responsibility matrix and crosswalk coverage** — so a scraper that ignores it is visibly ignoring a field rather than dropping prose. **Never publish a rank, an ordinal, or a single-number score in any artifact, even internally** — publish position-within-declared-peer-range only. Add a `LICENSE` (CC BY 4.0 with an explicit attribution-and-comparability condition) plus a machine-readable data-use statement shipped alongside the JSON. Stop bundling the full ledger client-side; serve per-municipality receipts and gate the bulk ledger behind a documented endpoint so bulk use is at least observable. And publish a one-page *"how not to use this data"* naming the upstream-service confound with the **Police $900 / Transit $63** example from this very receipt — the most persuasive possible illustration, already in the repo.

---

## 11. Risk and publishing posture

*Not legal advice. Have Ontario counsel confirm before any external publication — including, specifically, reading the finding **titles**, which `DIRECTOR-REVIEW.md:171` asked for and which has not happened.*

### 11.1 The jurisdiction profile must carry the legal regime

Generalization will naturally extend `profiles{}` to tax structures and stop. It must also carry, per jurisdiction, what determines whether a finding may be published at all: `canEntitySue` (Derbyshire followed? — Ontario likely yes; US varies by state; UK settled), `officialsCanSue` (always yes), `noticeRegime` (Ontario LSA s.5 six-week / s.6 three-month **if applicable** — see below; UK Defamation Act 2013 s.1 serious-harm and s.4 public-interest; US none), `limitationPeriod`, `antiSLAPP` (Ontario CJA s.137.1; ~33 US states; England none), `burdenOnFalsity` (defendant in CA/UK, plaintiff in US), `publicFigureStandard` (actual malice in US only), `recordsAccessRoute`, `sourceLicence`, `personalDataRegime`. **The fiscal generalization is hard-but-tractable engineering; the legal generalization is per-jurisdiction research with no automated shortcut, and it must gate the first publication in each new jurisdiction rather than trail it.**

**One likely-misread item, flag to counsel explicitly.** Ontario's LSA s.5(1) six-week notice and s.6 three-month limitation apply to a libel *"in a newspaper printed and published in Ontario"* or *"in a broadcast."* *John v. Ballingall*, 2017 ONCA 579 extended that to the online edition of a print newspaper. **An online-only publisher that is not a newspaper or broadcaster likely falls outside the regime** — meaning no six-week notice precondition to be sued, and the ordinary **two-year** Limitations Act clock rather than three months. Consequences: (a) you cannot count on early notice that would let you correct and cap damages, which makes the self-service corrections surface a substitute for a statutory benefit you don't have; (b) officials can sue on a finding published two years earlier, so every published finding needs a retained provenance record for at least the limitation period — and today `data/_extracts/` and `web/dist/` are both gitignored, so **the exact text published on a given date is unreconstructable.**

### 11.2 The individual-identification rule

The municipal corporation probably cannot sue over its governing reputation (*Derbyshire County Council v Times Newspapers* [1993] AC 534; followed in Ontario, e.g. *Montague (Township) v. Page*, 2006). **The real exposure is the reference element.** A finding about "Corporate Services" in a township of ~13,000 is in substance about a handful of identifiable people, and defamation does not require naming — only that readers who know the person would identify them. `DIRECTOR-REVIEW.md:166` spotted it exactly: *"in a township this size 'Corporate Services' is a dozen identifiable people."* Two live findings sit on that line (`FIND-ADMIN-CORP-SCALE`, `FIND-ADMIN-LEGAL-STACK`).

**Scale makes this worse, not better:** the smaller the municipality, the smaller the department, the more precisely a departmental finding identifies an individual — and Ontario's median taxing municipality has **6,588** residents, with 302 of 405 under 15,000. **Rule: below a population/staff threshold, any department-level JUDGMENT is treated as implicating individuals and is routed to Tier 2 (right of reply completed + human sign-off + counsel read of the title) or held. Never publish a department-level finding for a department whose headcount is small enough to be a named person.**

### 11.3 Right of reply — process, not a field, and the current design is pretextual

All 8 findings carry `null`. No component reads the field. The only test asserts key presence. **And `README.md:64` markets the emptiness as diligence** — *"An empty townshipResponse: null shows you asked."* That sentence is false and it is quotable: a hostile reader needs no analysis, only `README.md:64` next to eight nulls, on a page whose own README names that as *"the real risk."* **Delete that sentence today.**

The proposed 14-day auto-expiry is also wrong. *Grant v. Torstar* asks whether the plaintiff's side was **sought and accurately reported**, not whether a timer expired. Ontario clerks route substantive media questions into a council report cycle — four to eight weeks. A 14-day clock followed by publication reads as pretextual, which is **worse than not having the field**, because it documents that you set a clock you knew was too short.

**Design:** named officer via the clerk's office, in writing, documented second attempt, **minimum 30 days**, no publication while a response is in progress, publish the request date/channel/recipient role verbatim alongside any non-response so silence is visible **as silence**. Route each finding to the body it implicates (`subjectResponses[]` keyed by body id — three of eight findings implicate the Region, WRPS, or third parties). **Refuse publication outright where no reachable channel exists, and forbid publication of any finding naming a private or volunteer organization regardless of reply status.** Sending 444 reply requests with a clock is automatable; reading and fairly summarising 444 replies is not.

### 11.4 Two-artifact emission — not a flag rewire

Costed as "make `publishedFindingIds` the gate," this gets scheduled as polish. It is not. Required: the generator emits **two artifacts** — a full internal ledger that never enters a bundle, and a published subset containing only tier-eligible findings **and only the facts they cite**. `publishedFindingIds` becomes the single **build-time** gate; `belowMateriality` is deleted from the render path; CI greps the **built asset**. Today `web/dist/assets/index-55assK8C.js` contains both suppressed strings, so the exact scenario the floor was created to prevent is available to anyone who opens devtools — and now looks like *concealment of a judgment you formed about them*, which is worse than publishing openly.

Then decide deliberately whether internal-only findings should exist **at all** before an entity exists to hold them, and set a retention and deletion policy if they do (§6.11).

### 11.5 Publication tiers

Every municipality starts at Tier 0 and is promoted by an explicit, logged human act.

| tier | contents | gates |
|---|---|---|
| **0** | receipt only — allocation, rates, citations, sources, method note, denominator + rejected alternatives, coverage table. **No findings. No gaps.** | schema valid; all identities close; coverage ≥ threshold; publisher identity + license + contact + `generatedAt` + version present |
| **1** | + method gaps, naming missing **documents** only, and only those that blank a receipt line | gap language denylist + template asserted |
| **2** | + findings | right of reply completed or ≥30 days expired; recorded human sign-off (reviewer, date, documents read, hash of reviewed artifact); counsel review of finding **titles**; size-aware individual-identification check; materiality enforced at build time; comparator template filled; claim band satisfied; **`result == supported`** |

**This makes "scale" honest.** You can genuinely point the tool at 444 municipalities for receipts and will publish findings for a handful — and **saying so publicly is itself a credibility asset.** Note the honest consequence, too: the throughput ceiling is set by review and monitoring capacity, not compute, so the roadmap should state a number of municipalities you can **defend**, not a number you can generate.

### 11.6 Present disconfirmation as prominently as suspicion

`FIND-ADMIN-CORP-SCALE` concludes the opposite of a concern — *"tested against FIR peers — not an outlier"*, with its own summary saying *"Downgraded — do not publish as an administrative-scale accusation"* — and is nevertheless in `marqueeFindings`, rendered under **"Watch these first / Highest-signal findings"** with a `review` chip. The exoneration is after an em-dash in a card title. Readers take headlines; a municipal communications officer reasonably reads that page as *"we are on their watch list for admin costs."*

**Move disconfirmed findings into a separate, equally prominent "Tested and cleared" section.** This is the single best-value editorial change available: it removes the mischaracterisation, it is the most credibility-building content the project could publish (a transparency tool that publishes what it checked and found *nothing* is far more persuasive than one that only publishes hits), and it is direct documentary evidence of responsible-communication diligence. `docs/SPRINT-STEP-5.md` had the right instinct — *"If the benchmark shows North Dumfries is NOT an outlier, say that plainly"* — and the presentation layer undid it.

### 11.7 Corrections — mechanism, not culture

When a published finding is wrong: (1) correct **at least as prominently, on the same surface** — a finding that appeared in "Watch these first" gets its correction in "Watch these first," not in a log; (2) show the wrong number **struck, not silently replaced** — silent editing of a published accusation is worse than the original error and is discoverable via archives; (3) **tell the municipality directly**, because they are the injured party and notification is what converts an error into a demonstrated good-faith process; (4) record it in a dated machine-readable corrections log carried in the data model, so the correction rate is publishable — **a published error rate is a credibility asset and a concealed one is an existential risk.** Add `ReviewClaim {status: open|upheld|withdrawn, claim, rebuttal, wouldHaveCaused, appliedInCommit}` as a schema type and **fail CI while any upheld claim is unapplied.** The "dominates" fix is the proof that hand-applied review outcomes get lost.

### 11.8 Copyright, retrieval, and the error-intake channel

**Copyright:** default to link-don't-rehost for *future* sources; private hash-addressed evidence cache never served; `sources[].licence {id, url, permitsRedistribution, checkedAt}` with refuse-to-publish on unknown; sha256 + `retrievedAt` + an **independent archive snapshot URL as the citation of record**, with the live URL as convenience. Treat the existing 9 tracked documents as a scheduled, consented, pre-publication history operation (§6.14). Note the fair-dealing analysis (s.29.1 criticism or review, requiring attribution of source and author, on the *CCH Canadian* factors) is **strong** for quoting a line with a page cite and **weak** on amount-of-the-dealing for a rehosted 35MB package. `source-pdfs/.gitignore` shows the discipline already exists for uncited documents — extend the instinct to cited ones.

**Retrieval** is the riskiest unbuilt component precisely because it has zero accumulated safety discipline in a project whose safety discipline is otherwise its main asset. Most Ontario agendas are on third-party civic-portal vendors, and **the vendor's terms govern automated access, not the municipality's** — so "this is public information" does not settle it.

**Privacy is the project's best legal asset and it is currently accidental.** I scanned all 93 facts: no individual assessment, no address, no name, no salary. The only hit is `ROW-RURAL-HH-16`, an aggregate Region service line label. And the $455,000 is `ND-AVG-ASSESSMENT`, cited to the Township's own binder — **not MPAC data**, which matters because MPAC's products are licensed and the Assessment Act route is a per-office inspection. **Make it an architectural invariant with a CI test against the built bundle:** assessments enter only as government-published aggregate averages with a citation; no per-property value, address, postal code, roll number or owner name may exist in any fact, derived row, or published artifact.

**Build the inbound error channel before the second municipality** — it is the cheapest QA in the plan and currently discarded. The people best equipped to catch a wrong number are the dozen people per town who know that budget line: the clerk, the retired treasurer, the volunteer who runs the arena. The dominant error class is structural misreading that is arithmetically self-consistent and therefore invisible to every automated check — and trivially visible to a local expert. A per-figure "this looks wrong" link, no account, no personal data; submissions routed into the ledger as `Dispute {factId, receiptVersion, submittedAt, claim, status, resolution}` reusing the withdrawn-claim shape; a published dated dispute log that doubles as the corrections surface and the diligence record; a stated response interval, because an unanswered intake channel is worse than none. **A clerk correcting your number in public, with your correction published, is the single best outcome available to this project and there is currently no way for it to happen.**

---

## 12. Roadmap

### Phase 0 — Fix N=1 to the standard you intend to claim at N=444 (days; blocks everything)

Do not touch the schema first. Refactoring now freezes a candour defect into a corpus format.

1. **Commit `data/citation-audit.json` and render its counts on the page.** An instrument that publishes its own measured citation-fidelity rate is more credible than one that claims perfection.
2. **Amend `README.md:40` and `evidencePolicy.rules`** to the true statement (excerpts are reconstructions unless `matchLevel` says otherwise). **Strike "unless a cited formula exists" from the JUDGMENT rule.** Delete the "shows you asked" sentence at `:64`. Regenerate the open-gaps list, the finding count, the reconciliation table and the test count **from the ledger** — a tool whose value proposition is "nothing is stated without evidence" has hand-written prose that has already drifted at N=1.
3. **Fix the 13 wrong-page cites** (dominated by one namespace bug: 7 facts cite p7 for rows physically on PDF p9) and **disable `#page=` for any fact that does not verify on that page.**
4. **Apply the "dominates" fix** in the repo that owns the artifact.
5. **Commit `data/_extracts/`**, un-gitignore `taxpayer-receipt.ui-v1.json`, and stop deleting superseded artifacts.
6. Un-hardcode `extract_pdf_text.py` to iterate `sources[]` and extract everything on disk; fail hard on missing paths.
7. Accessibility: delete the incomplete ARIA tab roles in favour of `aria-pressed` buttons (10 minutes, strictly better), add a skip link, remove `aria-live` from static content, add `prefers-color-scheme`, **self-host the three fonts** (fixes the referer leak and the offline case in one commit), add axe-core to the vitest suite, do one manual NVDA/VoiceOver pass, and state WCAG 2.1 AA conformance with an audit date on the page — that statement is the artifact an institutional reviewer asks for and its absence is itself the blocker.
8. Replace bare `assert` with explicit exceptions; write to temp and move atomically; move the mirror check **before** the write.

### Phase 1 — Structural unblocking (days–weeks; each independently shippable, in this order)

1. **`taxingBodies[]` + `jurisdiction` + `publication` + `areaRateVariants[]` + `anchors[]` + `scenarios[]` + currency rename.** One breaking change. **Unblocks the 167 single-tier Ontario municipalities. Touches no evidence logic.** Highest leverage in the codebase.
2. **JSON Schema with `additionalProperties: false`; drop the `as unknown as` casts** so tsc is load-bearing.
3. **Split the test suite** (§9.7) — portable invariants vs ND golden fixture vs built-bundle denylist. Keep every ND literal.
4. **Rotation-aware coordinate extraction**; regenerate and commit extracts; **re-run the audit**; re-derive the structural error rate.
5. **Two-artifact emission** with `publishedFindingIds` as the build-time gate.
6. **Declarative expression AST + Identity engine**; forbid bare literals in derivations; add plausibility bounds.
7. **Transcribe ND to `corpus/north-dumfries-on/*.yaml`**; acceptance test = byte/key-order-insensitive equality against the frozen golden fixture. This converts 1,587 lines of Python into data and the old artifact into the regression suite.
8. **Run the year-2 experiment now:** re-derive the ND receipt from the 2025 budget book using only the process you intend to ship, and measure it. One day of work; converts the "5 minutes" guess into a number.

### Phase 2 — v1: the FIR-derived Ontario receipt (weeks)

**Scope:** all ~405 Ontario taxing municipalities (238 lower-tier + 167 single-tier). Prior-year FIR actuals, PSAB accrual, ~24 functions, three-tier levy split, per-class CVA, four denominators, findings engine **absent**, no PDF ingestion, **no human in the loop.** Basis and lag labelled on the face of it. Use the **education-rate identity as a per-municipality integrity gate** and refuse to publish the ~10 of 405 that fail. Anchors: user-entered assessment with shares as percentages; never a claimed dollar average from a derived denominator; **never an address.**

**Marginal human cost: ~0 minutes per municipality.** This is the largest misallocation the analysis corrected — the plan sent a team at portal adapters, page classifiers and OCR tiers to obtain, one municipality at a time at 4–8 hours each, a **coarser** breakdown than a single CSV already gives for all 405.

**Publish in small cohorts with a declared public error budget and a dated corrections log. When the budget is breached, stop publishing and fix before expanding.** Credibility is joint and several across the fleet: one wrong receipt in a town nobody is watching discredits the North Dumfries receipt, because the reader's inference is about the tool, not the town.

### Phase 3 — v2: current-year PDF receipts for a hand-picked cohort (weeks–months)

First cohort: **North Dumfries, Wellesley, Wilmot, Woolwich** — one shared already-ingested upper tier (as its own corpus instance) and FIR facts already in the ledger, so the cohort tests the shared-upper-tier design and the peer adapter for near-zero marginal document work. Then two lower tiers outside Waterloo, two single-tier cities, two small/northern, one large city.

**Before committing architecture, survey those ten municipalities' budget documents to answer the question that gates the whole design:** *does the pro-rata department allocation exist outside North Dumfries?* The receipt's entire visual payoff is the 7-line breakdown, and it works because the ND binder happens to publish a summary schedule of department nets that ties to Net Budget 0. **That is a property of one municipality's document design, not of Ontario.** Many publish by fund, by service area, program-based, or on a full-accrual basis that does not decompose into levy-fundable nets at all. If allocation is unavailable for a meaningful fraction, the product for those targets is a rate composition plus a source list — still honest, much less compelling — and the UI needs a **designed degraded state that does not look broken.**

**Marginal human cost: 4–8 hours first year** (dominated by control-total and gross/net determination, not extraction), **plus the measured year-2 figure** from the Phase 1 experiment. **No findings.**

### Phase 4 — v3: findings, as a separate default-off package (months + unbounded calendar time)

`packages/findings` cannot be enabled without a `rightOfReply` transport configured, and the engine refuses to publish any finding above `watch` whose `rightOfReply.requestedAt` is null. Requires everything in §10 and §11: responsibility matrix, crosswalk, mandated/discretionary table, comparator objects, severity function, forbidden predicates, entity, insurance, counsel. **Marginal cost: unbounded per municipality; the binding constraint is right-of-reply throughput and human sign-off, neither of which scales with compute.**

### Phase 5 — second jurisdiction

**Choose Alberta, not BC and not a US state.** Alberta's provincial education **requisition** is a dollar amount apportioned to the municipality, not a rate the by-law prints — which forces the composition model to generalize past *"every authority publishes a rate,"* the single assumption most deeply baked into the current design. BC then adds "many independent taxing authorities on one bill" cheaply. **US is v4+ and honestly a different product** (overlapping independent districts, separately elected school boards, homestead exemptions, assessment caps, TIF carve-outs — none of the Ontario abstractions survive). **Do not let a US pilot into v1 scope, and do not build the full ChargeSpec union for UK/US/banded/flat/formula/diversion until a jurisdiction that needs it is actually next** — 405 Ontario municipalities, 167 single-tier, is a larger addressable set than that abstraction serves.

### What is deliberately *not* in this roadmap

The 13-stage pipeline, 5 portal adapters, the review UI, the ChargeSpec union, the six-tier provenance ladder with signing keys, findings at scale — all proposed as prerequisites to municipality #2. That is a multi-quarter product for a team with a dedicated data engineer, a frontend engineer, an Ontario municipal-finance expert, and an editor. The repo's demonstrated throughput is one municipality, one live uncorrected calibration defect, a README that contradicts its own gap list, `as unknown as` casts asked to be removed five commits ago, and an extractor list that has drifted from disk. **Attempting the described system yields a half-built pipeline and no second municipality, while the highest-leverage change — `taxingBodies[]`, which is days and touches no evidence logic — gets scheduled behind it.** Re-scope after Phase 2 reveals what the FIR path already covers.

---

## 13. Open questions only the owner can decide

**Strategic — these select the architecture, and are currently being answered by UI copy rather than by decision:**

1. **Who is the primary user, and what action is the receipt supposed to enable?** Residents, candidates, journalists and municipal staff want four incompatible products, and candidates are the use `DIRECTOR-REVIEW.md:162` says makes the discipline "look like a costume." Write one page, commit it as `PURPOSE.md`, and derive scope from it. Cheapest possible test: publish the existing ND receipt at a URL, put it in front of 20 residents, 3 councillors, 2 clerks and 2 local reporters, and watch. No instrumentation needed at n=27.
2. **Does the project intend to publish FINDINGS at scale at all?** This one decision is ~80% of the legal surface. "Receipts at scale, findings rarely and by hand" makes this a fiscal-data problem with a modest legal wrapper. "Findings at scale" makes the binding constraint right-of-reply throughput, sign-off capacity and counsel review — none of which scale with compute, all of which cost per municipality.
3. **Who pays?** Each source corrupts the instrument differently and selects the product: municipal self-audit (real buyers, but the buyer is the subject, so findings must be private or absent and every adversarial feature dies); grant-funded transparency (needs an entity and a stated charitable purpose, and funders will ask exactly the unresolved defamation questions); campaigns (maximum willingness to pay, fatal capture); unfunded volunteer labour (current state — caps the fleet at one person's calendar and leaves that person personally liable).
4. **Ad-valorem-and-banded local property tax jurisdictions, or "local government cost of a household" generally?** The former is buildable. The latter is a different product (Scandinavian local income tax, Japanese inhabitant tax, France's post-2023 VAT share).
5. **What is the maintenance floor?** State a coverage policy — *"we maintain N municipalities and N is set by capacity, not ambition"* — and enforce it in the pipeline by refusing to onboard N+1 while any existing receipt is past its refresh deadline. **Do not publish a municipality you are not committed to republishing next year.**

**Governance — Tier-0 preconditions, not Tier-2 polish:**

6. **Who is the publisher of record, in what entity, in which jurisdiction, and is there media liability / E&O cover?** An individual publishing under their own name bears personal exposure, and `DIRECTOR-REVIEW.md:171` conditioned its comfort on counsel reading the finding titles in that case. **Recommendation: treat insurance as the forcing function** — attempt to obtain cover and let the underwriter's questionnaire define the governance artifact list, because an underwriter will ask precisely the questions in this document. A single notice with no cover ends the project regardless of how strong the evidence discipline is. Note there is currently **nobody to sign** a per-municipality sign-off, and recruiting volunteers to attest facts about their own township's staff exports uninsured personal exposure to people with no indemnity, in the community where they live.
7. **Commit the PDFs, publish hashes only, or hash + archive snapshot?** Recommendation: hash + independent archive snapshot as the citation of record, with an explicit `source-unavailable` verification outcome. Fifty municipalities' agendas is not a git repo.
8. **Does OCR'd text qualify as FACT-grade, and how is that shown?** `evidencePolicy.rules` is silent, and 48 raster pages sit in the package containing the headline by-law. Recommendation: OCR text is FACT-grade only if the number ties out arithmetically **and** two engines agree **and** the UI shows the pixel crop beside the transcription. **Decide before the schema is generalized**, because it changes the fact record shape. First, classify the raster pages — for the load-bearing page here, the answer is zero.
9. **What does `page` mean, and what does the deep link point at?** Must be 1-based PDF index for machine verification, with printed folio carried alongside. Package-level (143-page agenda) or attachment-level (2-page Schedule A)? The latter gives better links but creates a derivative whose provenance you must then defend.
10. **Who signs a T5 attestation, and what makes it worth anything?** Named individual with public identity (real accountability, real personal exposure) or a role? Signing key or a typed row? Recommendation: append-only, names a signer, binds to `{sourceSha256, pdfPage, printedValue}`, **auto-invalidates when the source hash changes**, and renders as *"confirmed by \<name\>, \<date\>"* **visually distinct from a citation** — never blended, because that is the one place where the strongest-looking tier is actually the weakest. **Never publish an attestor's name beside a finding about their own municipality.**

**Methodological — cheap now, expensive later:**

11. **When upper and lower tiers publish household illustrations at different reference properties, what does the engine do?** ND's $455,000 township average vs the Region's $354,500 region-wide average is handled honestly here (build:1519-1528 warnings, `DIRECTOR-REVIEW.md:106-121`) but as bespoke prose plus a UI caveat, not a designed construct — and it recurs in every two-tier province and every US county/city/school stack. Options: (a) always rebuild from rates at one assessment, treating published household tables as **corroboration only**; (b) render each body at its own basis with explicit non-additivity; (c) require the corpus author to declare a canonical reference property. **(a) is the most defensible and is what the combined receipt already does — but it requires the actual rate schedule for *every* taxing body, and where that is not published in usable form the tool must be able to say "no combined receipt is possible here" rather than degrade.** This is a schema decision, not an implementation detail.
12. **Are the p.7 department figures gross or net of departmental revenue?** (§10.8) Must be resolved and recorded as a structured field, not inferred from an identity, before the pattern touches a second municipality.
13. **`materialityBasisCad` — sum or max of cited fact amounts?** Pick one and write it down.
14. **What is the language scope, and therefore the jurisdiction scope?** English-only means excluding Quebec, New Brunswick and Ontario FLSA-designated municipalities. **A stated boundary is honest; a silent one is a defect.** And rule out machine translation of findings in the publishing policy: a finding may exist only in a language a competent human has reviewed for claim strength.
15. **Fact review ownership.** Stage 8 is irreducibly human. One person = ~200 municipalities/year and the product is a **curated catalogue** — which is fine and should be said out loud in the roadmap. Crowd-sourced or delegated needs a reviewer-trust model, per-fact attribution, and a dispute path. **Add `reviewedBy` / `reviewedAt` / `reviewMethod` in v1 regardless of the answer; they cost nothing now.**

---

## Closing

The best thing in this repository is not the North Dumfries data and not the React screen. It is a nine-rule epistemic contract — quote it or gap it, compute it from cited ids or don't compute it, record where you looked when you found nothing, never put a dollar figure on an interpretation, archive resolved uncertainty instead of deleting it, express the materiality floor as a ratio, ask before you publish, record the innocent explanation, refuse to emit when the arithmetic doesn't close — that would survive a port to any country and that almost nobody else has.

The worst thing is that the artifact does not yet meet that contract, the project has measured the shortfall in an untracked file, and the review that caught its one live calibration defect never changed the repository. Both of those are fixable in days, and both must be fixed **before** the schema is generalized, because the schema is how a defect at N=1 becomes a defect at N=405.

The single most useful discovery in this analysis is that **Ontario already publishes, in one CSV, a finer functional breakdown than the receipt currently renders, for all 405 taxing municipalities, with a built-in cross-document identity that holds for 97.5% of them** — and that the extraction problem everyone was designing around is a rotation flag and twelve lines of coordinate clustering. Point the tool at Ontario through FIR first. Earn the right to open a PDF second.