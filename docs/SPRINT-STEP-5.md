# Sprint Step 5 — close the three open evidence gaps

Read `DIRECTOR-REVIEW.md` first for the methodology and the standing rules. Five commits are already in on this branch; HEAD is `8687d49`. Tests 31/31, build clean. **Do only this step.**

## Standing rules (non-negotiable)

- **FACT** = quoted from a source with a page or URL and a verbatim excerpt.
- **DERIVED** = computed only from existing fact IDs, with the formula recorded.
- **GAP** = missing evidence. Never invent a number to fill one.
- **JUDGMENT** = interpretive. `billImpactCad` stays `null`.
- **A documented dead end is a correct outcome.** If a figure is not published, leave the gap open and record exactly where you looked and what you searched. Do not substitute a plausible number. This is the single most important rule in the project.
- Edit `scripts/build_evidence_model.py` and regenerate — never hand-edit the JSON. The generator writes both `data/` and `web/src/data/` and asserts they are byte-identical.
- `cd web; npm test` and `npm run build` must both pass before you finish. Do not weaken or delete any of the 31 existing tests.
- **Do not touch** the allocation base (10,049,624), the combined receipt ($5,395.61), or any published dollar figure. Those are settled and verified.

---

## Gap 1 — `GAP-PEER-BENCHMARK` (highest value, do this first)

**The problem.** `FIND-ADMIN-CORP-SCALE` says Corporate Services is "large" at ~$197/capita, but names no comparator. Without one it is a number, not a finding. It is currently the weakest finding in the set.

**The trap to avoid.** Do NOT compare North Dumfries' own "Corporate Services" department against another municipality's differently-named department. In a township of ~10,600 that line bundles clerk, treasury, IT, HR and communications that a city reports separately. A naive name-to-name comparison is invalid and worse than no comparison.

**Do this instead.** Use a normalised common schedule. Ontario's **Financial Information Return (FIR)** is the right instrument — every municipality files one, and the `General government` line is defined consistently across filers. Ministry of Municipal Affairs and Housing publishes FIR data.

**Peer set.** Prefer lower-tier rural townships in two-tier regions with comparable population. The strongest comparators are the ones in the same region, because they share the same upper-tier services: **Wellesley, Wilmot, Woolwich**. Widen only if needed (e.g. Puslinch, Blandford-Blenheim, Perth East).

**Deliverable.** Cited FACTs for each peer's `General government` expenditure and population, on the same FIR year. A DERIVED per-capita figure for each, including North Dumfries on the same basis. Then either close the gap and update `FIND-ADMIN-CORP-SCALE` with a real comparator, or — if the FIR year available is not comparable to 2026 — say so and keep the gap open with the mismatch documented.

**If the benchmark shows North Dumfries is NOT an outlier, say that plainly and downgrade or retire the finding.** Confirming a suspicion is not the goal; testing it is.

---

## Gap 2 — `GAP-ND-POP-CURRENT`

Every per-capita metric divides 2026 dollars by the **2021 Census population of 10,619**, biasing all of them upward by an unknown amount.

Find a citable current or 2026 population figure. Candidates: Region of Waterloo population projections, the Township's Official Plan or Development Charges Background Study, StatCan population estimates. Add it as a FACT with source and date, add DERIVED per-capita figures on the current basis alongside the 2021 ones, and note the direction and size of the bias. Do not delete the 2021 figures — show both.

---

## Gap 3 — `GAP-TWINPAD-OPERATING-DELTA` (stretch; expect to fail)

No evidence exists in the ledger on what the Twin Pad costs to **run** versus the ACC ice it replaces. For a household receipt the recurring change matters more than the one-time capital.

Look for a projected annual operating cost and the offsetting ACC ice savings — a staff report, business case, or the 10-year operating forecast. **This may simply not be published.** If so, leave the gap open, record where you looked, and note that it likely requires a records request. Do not estimate it.

---

## Report back

For each gap: closed or still open, the fact IDs added, and the document plus page or URL each came from. Where you found nothing, say so directly rather than working around it. If the peer benchmark contradicts the existing finding, lead with that.
