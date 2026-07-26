# Purpose

Decision record answering Q1 and Q2 of `docs/GENERALIZATION-PLAN.md` §13. Scope in every other
document derives from this page. A proposed feature that does not serve the user and action below
is out of scope, regardless of how cheap it is to build.

## Primary user

**A resident of a covered municipality who holds a tax bill and has one question about it.**

One user, chosen deliberately, because residents, candidates, journalists and municipal staff want
four incompatible products (§13 Q1). Reporters, councillors and clerks are welcome and are the most
likely source of corrections, but they are not the design target — when their needs conflict with
the resident's, the resident wins.

Candidates are explicitly **not** a design target. A receipt built to be a campaign artifact is the
case `DIRECTOR-REVIEW.md:162` describes, where the evidence discipline stops protecting the project
and starts looking like a costume.

Validation is observational, not instrumented: put a published receipt in front of ~20 residents,
3 councillors, 2 clerks and 2 local reporters and watch what they do. At n=27 no analytics are
needed, and the project collects none.

## The action the receipt enables

Exactly one: **take a single figure, open the municipality's own document at the cited page, and
confirm or refute it** — then ask about that figure by name, at a council meeting, in an email to
the clerk, or in a records request.

Everything on screen is subordinate to that click. The success condition is a resident asking a
specific, sourced question, or a clerk publicly correcting one of our numbers with the correction
published (§11.8). Neither outrage nor sharing is a success condition.

## What the receipt is

A **composition**, not an evaluation: which bodies levy what, at what rate, over what base, with
every figure resolving to a page in a published document or to a formula over figures that do.
The four easily-conflated denominators stay distinct (`README.md` reconciliation table). Missing
evidence renders as a gap with its search trail rather than being filled (§3.1). Where a peer
comparison is unavailable or invalid, the honest output is refusal, not a weaker comparison.

## Out of scope for v1 — explicit

| out of scope | why |
|---|---|
| **Findings at scale** | Findings carry the legal exposure and the binding constraint is right-of-reply throughput, sign-off and counsel review, none of which scale with compute (§11.5, Phase 4). |
| **Multi-tenant SaaS** | No accounts, no tenants, no third-party self-serve onboarding. The artifact is a static jurisdiction pack on a static host. A tenant model would put unreviewed packs under our name. |
| **Blockchain as source of truth** | The source of truth is the municipality's published document. Integrity is content hashes in `manifest.json`, git tags, and an independent archive snapshot as the citation of record (§9.6, §11.8). A chain answers "this bytestring existed" and never answers "page 103 says this," while moving the reader's trust from the municipality's document to our ledger. |
| **Address entry / per-parcel lookup** | Licence- and privacy-encumbered in Ontario and legally different in every jurisdiction (§6.8). The reader types the assessed value already printed on their bill; the tool never accepts an address, postal code, roll number or owner name. |
| **Rankings, scores, leaderboards** | Invalid by our own methodology and most wrong for the small rural municipalities that make up most of the fleet, because their police and transit sit upstream (§6.12). Non-comparability must be machine-readable and refusal is the default (§10.11). |
| **Unreviewed-language publication** | The current preview interface is English-only and is not Canada-wide publication-ready. A national release requires reviewed English/French interface catalogs, dynamic document language, locale-aware rates and dates, and source-native evidence. A translated excerpt must be labelled as a reviewed translation rather than verbatim evidence. No finding may be published in a language in which a competent human has not reviewed its claim strength. Runtime machine translation is out of scope. |
| **US jurisdictions** | Overlapping independently governed districts are a property of the parcel, not the city; none of the Ontario abstractions survive (§7.1, Phase 5). |

## Operating posture: receipts at scale, findings rare and by hand

Adopted, as recommended in §13 Q2.

- **Receipts scale.** Ontario's FIR publishes a finer functional breakdown than the current receipt
  renders, for all ~405 taxing municipalities, with a built-in education-rate identity that holds
  for 97.5% of them (§2.4). Marginal human cost approaches zero (Phase 2).
- **Findings do not scale and will not be made to.** Human-gated, minimum 30-day right of reply
  routed to the body actually implicated, recorded sign-off, counsel read of finding titles, and a
  size-aware individual-identification rule (§11.2, §11.3). Expect single digits across the fleet.
  Publishing that count is itself a credibility asset.
- **Coverage is capped by capacity, not ambition.** Do not onboard municipality N+1 while any
  existing pack is past its refresh deadline, and do not publish a municipality we are not
  committed to republishing next year (§13 Q5).
- **Publish the error rate.** A dated corrections log with a measured error rate is the only
  credibility claim that survives being wrong (§6.4).

## Honest current state

No pack is published, and none may be labelled Published today. The current citation audits may
report zero traditional hard failures, but source locks, identity checks, deterministic
calculation/rounding, public/internal artifact separation, and deployment-byte attestation are not
yet complete. North Dumfries and every other pack remain **draft previews**. See `PUBLISH.md`.
