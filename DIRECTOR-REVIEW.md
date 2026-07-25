# Director Review — North Dumfries / Waterloo Region "Taxpayer Receipt"

**Reviewer:** Claude (Opus 5) · **Date:** 2026-07-25 · **Reviewed:** `cursor/north-dumfries-taxpayer-receipt` @ `a455829`
**Method:** independent re-extraction of all four source PDFs (`pdftotext -layout`), line-level reconciliation of the ledger against extracted text, static + runtime analysis of the UI model.

---

## 0. Corrections to my own first pass

Two things I reported early and got wrong. Owning them before anything else:

1. **There is no CRLF churn.** I first read the repo through the desktop file bridge, which reported 6 modified files, 4,229 insertions / 4,229 deletions. Run natively on your machine, `git status` is **clean** and `git diff -w` is empty. The "churn" was an artifact of my access path, not your repo.
2. **There is nothing to commit.** The branch is clean at `a455829`. The single file in Cursor's Changes panel was `_to_delete/index.lock.stale`, a stale git lock artifact I created and have since removed. Had "Commit & Push" been clicked, that lock file is all it would have pushed.

Everything below is independent of that and stands.

---

## 1. Verification results

### 1.1 FACT spot-checks — 12 of 12 verified verbatim

| Fact ID | Ledger | Source line | Status |
|---|---|---|---|
| `ND-LEVY-2026` | 9,002,499 | binder: "total tax levy in the 2026 draft budget is $9,002,499" | ✅ |
| `ND-LEVY-2025` / `-INCREASE` | 8,427,827 / 574,672 | "2025 LEVY REQUIREMENT = $8,427,827 … Levy Increase $574,672" | ✅ |
| `ND-TAXRATE-RURAL-2026` | 0.00315303 | "Residential Township Tax Rate 0.00315303" | ✅ |
| `ND-TOWNSHIP-TAX-RURAL-AVG-2026` | 1,434.63 | "Township Taxes Annually $ 1,434.63" | ✅ (455,000 × 0.00315303 = 1,434.629) |
| `ND-DEPT-CORPORATE-2026` | 2,091,306 | "TOTAL CORPORATE SERVICES … 2,091,306" | ✅ |
| `ND-DEPT-PROTECTIVE-2026` | 1,554,793 | "TOTAL PROTECTIVE SERVICES … 1,554,793" | ✅ (Fire 1,182,646 nested — correctly not double-counted) |
| `ND-DEPT-PW-2026` | 2,477,423 | "TOTAL PUBLIC WORKS … 2,477,423" | ✅ |
| `ND-DEPT-REC-2026` | 1,867,455 | "TOTAL RECREATION SERVICES … 1,867,455" | ✅ |
| `ND-DEPT-PLANNING-2026` | 451,372 | "TOTAL PLANNING … 451,372" | ✅ |
| `ND-CAPITAL-PROGRAM-2026` | 31,192,121 | "TOTAL $31,192,121" | ✅ |
| `ND-CAP-ARENA-2026` | 16,190,160 | capital table row D6 + narrative | ✅ (funding split verified: 5.0M grant / 5.0M debt / 520k DC / 2,062,448 fundraising) |
| `ROW-RURAL-HH-TOTAL-2026` | 2,543 @ 354,500 | Region p.11–12 Rural (4) column | ✅ |

Derived arithmetic also checks: legal stack = 94,000 exactly; corporate per-capita 2,091,306 / 10,619 = 196.94; arena per-capita = 1,524.64; arena share = 51.9%; the six allocation lines sum to **exactly** $1,434.63 and their shares to 1.000000.

**The evidence discipline is real.** No invented numbers found anywhere in ledger, receipt, or UI. The v1 rollback was done properly.

### 1.2 Region rural table interpretation — confirmed, with the $2 gap resolved

`Rural (4)` column is correct, and the follow-on per-municipality table confirms **N. Dumfries $2,543 and Wellesley $2,543** (Wilmot $2,617, Woolwich $2,576, the three cities $2,984). Your reading is right.

**`GAP-RURAL-HH-LINE-SUM` can be closed.** The 23 printed rural line items sum to $2,619; the printed subtotal is $2,621; less the printed ($78) PIL gives the printed $2,543. So the $2 is **rounding inside the source**: each line is rounded to whole dollars, the subtotal is struck from unrounded values. Not a parse error. Close it as `resolved_source_rounding` and keep $2,543 authoritative.

---

## 2. Defects found

### P0 — Runtime crash on a primary path

`FIND-ADMIN-CORP-SCALE` carries the key **`severitySeverity`**; every other finding uses `opportunitySeverity`. `FlagDetailDrawer.tsx` does:

```tsx
<p className="drawer-severity">{flag.opportunitySeverity.replace(/_/g, ' ')}</p>
```

`FIND-ADMIN-CORP-SCALE` is in `uiModelHints.marqueeFindings`, so it renders as a "Watch these first" card. **Clicking it throws `TypeError: Cannot read properties of undefined (reading 'replace')`** and takes out the drawer. Reproduced directly against the committed JSON.

Why nothing caught it: `types.ts` declares `opportunitySeverity: string` as required, but both the screen and the test cast with `as unknown as TaxpayerReceipt`, which erases the check. `tsc` passes, the three vitest assertions pass, production build passes — and the app still crashes on click. "Tests + build green" is not evidence of correctness here.

Fix in `scripts/build_evidence_model.py` (the generator), not just the two JSON copies, or it regenerates.

### P1 — Allocation base does not reconcile to the levy

```
dept nets only:               8,442,349
+ capital reserve xfer:      10,067,349   ← DRV-ND-DEPT-SUM
published municipal levy:     9,002,499
difference:                   1,064,850   (11.8% over)
```

Because the allocation is pro-rata, the **total** still lands on the cited $1,434.63 — so nothing looks wrong on screen. The **distribution** is what's off, and there are two distinct problems:

**(a) Council and Elections are missing entirely.** Binder p.7 shows `Total Council 201,669` and `Total Elections 37,034` for 2026 draft. Neither is in the base, so neither appears on the receipt. For a product whose lead thesis is administrative scale, **the governance line is absent from the taxpayer receipt.** That is the first thing a hostile reader will notice.

Adding them (base → 10,306,052) gives a missing **"Council & Elections — $33.23"** line and shows every published line is currently overstated by 2.37%:

| Line | Shown | Corrected |
|---|---|---|
| Corporate Services | $298.02 | $291.12 |
| Protective Services | $221.56 | $216.43 |
| Public Works | $353.04 | $344.86 |
| Recreation | $266.12 | $259.95 |
| Planning | $64.32 | $62.83 |
| Capital reserve transfers | $231.57 | $226.20 |
| **Council & Elections** | *absent* | **$33.23** |

**(b) The capital transfer figure is ambiguous.** The ledger uses $1,625,000 (p.43 narrative + capital table column). The p.7 summary schedule shows `Capital Funded by tax levy and building bill … 1,607,500` for 2026. Both are in the same document for what looks like the same concept. Pick one, cite the choice, and note the other — a reviewer who finds the second number without your note assumes an error.

**Recommendation:** rebuild the base to reconcile to $9,002,499 explicitly, with a visible residual/unallocated line rather than a silent one. A transparency tool that cannot tie its own denominator to the published levy is the easiest possible thing to discredit.

### P2 — Region reconciliation artifacts

- `lineItemsSumCheckCad: 2541` contradicts the array it describes. The 23 services (2,619) + PIL (−78) + rounding plug (+2) = **2,543**. The check value equals the sum *without* the plug that sits in the same array. Set it to 2543, or drop the plug and let the check be 2541 — but not both.
- `ROW-TABLE-ROUNDING` has `evidenceStatus: "GAP"`, and `TaxReceiptScreen` maps `evidenceStatus === 'GAP' → 'flagged'`. So **a $2 rounding artifact renders to users with a red "flagged" badge**, directly against its own note ("Do not treat as a service"). Give reconciling items their own status (`RECONCILING`) and their own neutral styling.

---

## 3. The methodology finding that matters most

**`GAP-5000-BILL`'s stated reason is wrong, and it is blocking the core product unnecessarily.**

The ledger and UI both say the township and region figures cannot be combined because *"assessment bases differ ($455k vs $354.5k)."* They do not differ. Both sit on the **same** MPAC valuation base:

- Binder: *"Property taxes continue to be assessed at the 2016 assessment values … properties are assessed by MPAC as to the value they would have had in 2016."*
- Region p.12 footnote: *"Based on an average residential property valued at $354,500, based on a valuation date of January 1, 2016."*

Same base. What differs is **which average property each government reports**: $455,000 is North Dumfries' own median residential assessment; $354,500 is the *region-wide* average. That is not a units mismatch — it is two different sample means on one common scale.

Which means the combination is a legal `DERIVED` under your own rules, from facts already in the ledger:

```
DRV-ROW-RURAL-IMPLIED-RATE   = 2543 / 354500            = 0.00717348
DRV-ROW-RURAL-AT-455K        = 0.00717348 × 455000      = $3,263.94
DRV-ND-COMBINED-EX-EDUCATION = 1434.63 + 3263.94        = $4,698.57
```

Caveats to state on the face of it: the implied rate embeds the area-rated components (transit $63, library $79) and the ($78) PIL offset, so it approximates a true rate schedule and should be replaced by actual by-law rates the moment those are in hand.

**So the real blocker is only education**, not the assessment bases. And the arithmetic is instructive: a $5,000 total bill at $455,000 implies a combined rate of 0.01098901, against 0.01032651 for township + region. The residual attributable to education is **0.00066250**. I am not putting a number in your ledger for it — pull it from the by-law. But note the shape: a $5,000 bill is not a fantasy figure, it is roughly a North Dumfries house at or slightly below the township average. The hypothetical you started with was closer to reality than the current model admits.

**And the document that closes this already exists.** Binder p.1: Council was scheduled to pass the **Final Full Tax Rate By-law (including Region and School Board Rates) on April 27, 2026** — three months ago. The adopted budget and Township Tax Rates By-law were scheduled February 23, 2026. `GAP-5000-BILL`, `GAP-EDUCATION-2026`, and `GAP-ND-FINAL-BUDGET` are not waiting on the world; they are waiting on a download.

---

## 4. Challenging the findings

Fairness and completeness, finding by finding. Two should be downgraded, one strengthened, and there is a material omission.

**`FIND-ADMIN-CORP-SCALE` — weakest of the eight. Downgrade until benchmarked.**
Three problems. (i) $197/capita divides a 2026 budget by **2021** census population; North Dumfries has grown since, so every per-capita metric in the ledger is biased upward by an unknown amount. (ii) In a township of ~10.6k, "Corporate Services" bundles clerk, treasury, IT, HR, and communications that a city reports separately — the category is not comparable to a larger municipality's "admin" line without normalization. (iii) There is no peer set, so $197/capita is a number, not a finding. As written, it asserts "large" against no stated comparator.

**`FIND-CAP-DUAL-FACILITY` (ACC $3.5M) — downgrade `high_attention` → `watch`.**
Your own `evidenceSummary` contains the rebuttal: *"ACC ice to be decommissioned on Twin Pad opening."* If the ACC continues in non-ice community use, exterior envelope work is not duplication — it is maintaining a building that stays in service. Add that $1M is provincially granted and the residual comes from reserves, not the levy. Unless you can show the exterior scope is contingent on ice use, "concurrent with" implies waste you have not established. This is the single most rebuttable finding in the set, and it is currently at your second-highest severity.

**`FIND-CAP-ARENA` — strongest finding, but reframe the metric.**
52% of a one-year capital program in one project is unremarkable for a small township doing its one big build; the framing invites "it's a 40-year asset." Likewise $1,524.64/capita divides a lifetime capital cost by one year of population. The honest, un-rebuttable number is **annual debt service per household**, available once the amortization schedule lands. Keep the finding, lead with the $5M debt and the 2027 start, and hold the per-capita figure as secondary.

**Material omission — the operating delta.** The ledger has nothing on what Twin Pad costs to *run* versus the ACC ice it replaces. For a household receipt, the recurring operating change matters more than the one-time capital. Add `GAP-TWINPAD-OPERATING-DELTA`.

**Second omission — Council and Elections have no finding at all.** $238,703 of governance cost, absent from both the receipt and the findings, in a product about administrative scale. Whatever you conclude about it, it should be examined rather than missing.

**`FIND-UNUSUAL-HERITAGE-SOFTWARE` ($5,000), `FIND-UNUSUAL-PARTNERSHIP-FEES` (Sustainable Waterloo $1,725) — pull from published output.**
Not because they are wrong, but because they are 0.02% of the levy. Publishing them alongside a $16M arena gives a critic the easiest available move: point at the $1,725 line and dismiss the whole instrument as a gotcha exercise. **Set a materiality floor for published findings** — 0.25% of levy (≈$22,500) is defensible — and keep sub-floor items in the internal ledger where they belong.

---

## 5. Answers to the six asks

**1. Go / no-go on evidence-first → GO, keep strict gaps. Do not ship a modelled $5k UX with disclaimers.**
The discipline is the product's only real asset; disclaimers are not a substitute and nobody reads them. But note the irony in the current build: strictness is aimed at the wrong target. It blocks a combined bill that *is* derivable from cited facts (§3), while letting an allocation base that overstates the levy by 11.8% ship as `DERIVED` without a reconciliation note (§2). Tighten where the numbers actually move; relax where your own rules already permit the derivation.

**2. Priority ranking of evidence pulls:**
1. **April 27, 2026 Final Full Tax Rate By-law** — closes three gaps at once (`GAP-5000-BILL`, `GAP-EDUCATION-2026`, and the combined-total block) and unblocks the headline feature. Highest leverage by a wide margin, and almost certainly already published.
2. **Adopted 2026 budget + Feb 23 Township Tax Rates By-law** — flips every ND fact from `draft` to `final`. Until this lands, every number you publish carries an asterisk.
3. **Twin Pad debt amortization** — matters, but it is a 2027+ story and does not change a 2026 receipt. Do it third, and pair it with the operating delta.
4. **Peer benchmarks** — last, and only after classification rules exist (see #6). Benchmarks without rules are rhetoric with citations.

**3. Product stance → transparency tool, publicly; internal audit aid, as the engine. Not a campaign artifact.**
The moment it is a campaign artifact, every `JUDGMENT` row is read as an accusation, and the evidence discipline stops protecting you — it starts looking like a costume. Your architecture already supports the right split: publish the receipt from `FACT`/`DERIVED` only, and keep a separately-labelled watch list of `JUDGMENT` items that never carries dollar figures. Keep that wall load-bearing in the UI, not just in the JSON.

**4. Legal / comms risk in the language:**
- **"Bloat" — retire it entirely from anything published.** It is a conclusion, not an observation, and in a township this size "Corporate Services" is a dozen identifiable people. Rename the category key `administrative_bloat` → `administrative_scale`. The finding survives; the editorializing does not.
- **"Questionable"** → "unexplained" or "high cost relative to stated justification." Questionable invites "by whom?"
- **"Flagged"** is defensible *only if the UI defines it on screen* as "needs explanation," never "wasted." Right now the word does real work with no definition attached.
- **"Pet projects"** appears in the mission framing. Do not let it reach code, schema, or UI.
- Every finding should carry a "what the Township says" field, even when empty. An empty `townshipResponse: null` shows you asked. Publishing without having asked is the actual defamation-adjacent risk, more than any single word.
- Nothing here alleges illegality and the ledger is careful about that. Keep it that way. *(I am not a lawyer and this is not legal advice — if you publish under your own name, have counsel read the finding titles specifically.)*

**5. Expand to full line-by-line, or freeze? → Freeze breadth. Fix depth for two weeks.**
Do not start the full paper-trail map until the base reconciles to the levy and the final by-law is ingested. Every node you build now hangs off a denominator you would have to rebuild, and off draft figures that are about to be superseded. Fix the foundation, then expand — the map is cheap once the model is right and expensive to redo.

**6. Approval criteria for calling any dollar "flagged / inefficient" on a household bill — propose four gates, all required:**
- **(a) Traceable.** Ties to a specific published line with document + page cite. No category-level inference.
- **(b) Discretionary in law.** Statutorily mandated spend is out by definition — police, waste, paramedics, education. You cannot call a legal obligation inefficient.
- **(c) Has a stated comparator and threshold.** Prior-year actual, peer-township per-capita, or the Township's own stated policy or target — and the line exceeds it by a pre-declared margin. The comparator is named *before* the finding, not chosen after.
- **(d) Right of reply exercised.** The Township was asked and either declined or the explanation does not reconcile. Record which.

Anything failing any gate stays `JUDGMENT` with `billImpactCad: null`. And no flag is ever expressed as a share of a household bill until *both* all four gates pass *and* the bill composition itself is `FACT`/`DERIVED` — i.e. not before the by-law is in. Add a fifth structural rule: a materiality floor, so the instrument is never seen litigating $1,725.

---

## 6. Two-week evidence sprint

**Week 1 — evidence + correctness**
1. Pull the April 27, 2026 final tax rate by-law; extract township / region / education rates at one assessment. Close `GAP-5000-BILL`, `GAP-EDUCATION-2026`.
2. Pull the adopted 2026 budget; flip ND facts draft → final. Close `GAP-ND-FINAL-BUDGET`.
3. Fix `severitySeverity` in `build_evidence_model.py` + both JSONs. **P0.**
4. Rebuild the allocation base to reconcile to $9,002,499; add Council & Elections; expose a residual line; resolve 1,625,000 vs 1,607,500 with a cited note.
5. Fix `lineItemsSumCheckCad` → 2543; give reconciling items a non-`GAP` status and neutral styling.
6. Close `GAP-RURAL-HH-LINE-SUM` as source-side rounding.

**Week 2 — methodology + guardrails**
7. Build the combined receipt from **rates at a single assessment**, not from two household averages.
8. Retire "bloat"; rename the category; rewrite finding titles; add `townshipResponse` to the finding schema.
9. Apply the materiality floor; downgrade `FIND-CAP-DUAL-FACILITY`; reframe the arena metric around annual debt service.
10. Add `GAP-ND-POP-CURRENT`, `GAP-TWINPAD-OPERATING-DELTA`, `GAP-ALLOC-BASE-RECONCILIATION`, `GAP-PEER-BENCHMARK`.
11. **Add the CI guard that would have caught the P0:** JSON-schema validation rejecting unknown keys, asserting every finding has `opportunitySeverity`, every `DERIVED` cites input IDs that exist, every dollar line's `evidenceStatus` is in the enum, and the region lines reconcile to the published total. Then drop the `as unknown as` casts so `tsc` does its job.

**Explicitly not this sprint:** full line-by-line township map; peer benchmarking; any "flagged $ on a bill" UI.

---

## 7. Bottom line

The evidence discipline is genuine and the v1 rollback was the right call — I went looking for invented numbers and there are none. What the build has instead is a foundation problem and a correctness problem: an allocation base that does not tie to the published levy and silently omits governance costs, and a one-key typo that crashes a primary UI path while every gate you have stays green.

The single highest-value insight: **you are gapped out of your own core feature for a reason that does not hold.** The assessment bases are the same, the region figure converts to a rate, and the by-law that finishes the job was published three months ago. Fix the base, pull the by-law, and the combined receipt becomes fully evidence-backed instead of permanently blocked.
