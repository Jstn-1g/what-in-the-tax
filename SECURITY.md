# Security policy

## Reporting a vulnerability

Use GitHub's **[private vulnerability reporting](https://github.com/Jstn-1g/what-in-the-tax/security/advisories/new)**
on this repository. It reaches the maintainer privately and does not create a
public issue.

Please do not open a public issue for a security problem, and please do not post
one to a municipality's contact channels — this project is independent and not
affiliated with any government.

There is no published email contact yet. That gap is tracked: `PUBLISH.md`
records `correctionsRoute` as `pending-public-contact-channel`, and publication
is blocked until it exists.

## What counts as a security issue here

This is a static site over committed data artifacts. There is no user account,
no database, and no personal data collected. So the interesting surface is not
the usual one:

**In scope**

- A way to make a published figure differ from the source it cites — a citation
  that passes `scripts/audit_citations.py` while being false, an extract that
  does not derive from its declared source, or any path that gets a number onto
  the page without passing the gates in `.github/workflows/release-validation.yml`.
- A way to weaken or bypass a gate: source-lock verification, the citation audit,
  the reproducibility `--check` builds, or the reviewer attestation required by
  `scripts/acquire_official_sources.py`.
- Anything in the build or deploy path that could ship bytes nobody reviewed —
  workflow permissions, action pinning, dependency confusion.
- Secrets or credentials committed to the repository or its history.

**Not a security issue, but still wanted**

- A wrong number that traces honestly to its source. That is a *data* problem,
  and it is the one this project most wants to hear about. It goes to the
  corrections route rather than here.
- A municipality disputing how its figures are characterised. Same route.

## Why the first category matters more than it looks

This project's only claim is that every published number traces to a reviewed
source. A vulnerability that lets a wrong number through the gates is not a
cosmetic bug — it is the failure the whole design exists to prevent, and it
would be indistinguishable from the project simply being unreliable.

Report those first.

## Handling

There is no SLA. This is a small project; expect a human, eventually. Reports
that include a reproduction — a branch, a command, the actual output — get
handled fastest, because the gates here are all deterministic and a repro
usually *is* the diagnosis.
