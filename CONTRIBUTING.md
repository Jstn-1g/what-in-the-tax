# Contributing to AuditBack

AuditBack accepts contributions that make Canadian public-finance data more
accurate, reproducible, and understandable. The project is evidence-first:
missing evidence stays missing, statistical geography is not treated as proof
of a government, and a pull request must not claim more coverage than its
locked official sources support.

## Choose a contribution path

- **Start or advance a province/territory rollout:** read
  [`docs/PROVINCIAL-ROLLOUT.md`](docs/PROVINCIAL-ROLLOUT.md), then open a
  Province/territory rollout issue.
- **Report an upstream source change:** use the Official source change issue
  form. This includes moved endpoints, changed columns, new identifiers,
  amalgamations, dissolutions, licence changes, and revised control totals.
- **Improve the receipt UI or existing evidence packs:** describe the affected
  jurisdiction and evidence impact in the pull request. A UI change must
  continue to fail closed when a pack is unavailable or incomplete.
- **Fix a small documentation or test problem:** a focused pull request is
  welcome. Link the issue when one exists.

Please do not put personal information, property addresses, roll numbers,
account numbers, owner names, private correspondence, credentials, or
unpublished government material in an issue, fixture, commit, or pull request.

## Province and territory onboarding

The current rollout unit is one jurisdiction's
`municipal-regional-governments` layer, not one name found on a webpage.
Cities, towns, villages, counties, regional municipalities, districts, hamlets,
designated authorities, and other legal forms must keep their published type
visible in the mapping review and provenance even when they normalize to the
canonical municipal or regional body type. The other national coverage layers
remain separately tracked in `national/coverage_plan.json`.

Each jurisdiction has a checked-in manifest at:

```text
national/jurisdictions/<CODE>/rollout.json
```

The schema is:

```text
national/schemas/jurisdiction-rollout.schema.json
```

Evidence artifacts are separately constrained by:

```text
national/schemas/jurisdiction-source-lock.schema.json
national/schemas/verified-jurisdiction-directory.schema.json
national/schemas/publication-approval.schema.json
national/schemas/sgc-geography-index.schema.json
```

`national/sgc_2021_geography_index.json` is the reviewed, pinned national
geography allowlist. Rebuild it only from the catalog-approved Statistics
Canada bytes with `scripts/build_sgc_geography_index.py`.

Do not edit a manifest merely to make a dashboard look greener. Its stages must
describe evidence already present in the pull request. The authoritative
commands are:

```bash
python scripts/manage_national_rollout.py check
python scripts/manage_national_rollout.py status --format json
```

The rollout stages, in order, are:

1. `official-source-identified`
2. `reuse-approved`
3. `transport-pinned`
4. `adapter-tested`
5. `exact-crosswalk-reviewed`
6. `exceptions-reviewed`
7. `count-reconciled`
8. `publication-approved`

Each of these municipal-rollout stages is mandatory and is `not-started`,
`in-progress`, `blocked`, or `complete`. Only the first unfinished stage may be
active or blocked; later stages remain `not-started`.
The manifest's overall coverage status separately follows the coverage-plan
vocabulary: `not-started`, `source-discovery`, `adapter-needed`, `partial`,
`complete`, or `not-applicable`. The municipal/regional layer itself is never
`not-applicable` for a Canadian province or territory. No jurisdiction should
be described as ready or complete until the command above accepts every
required stage and the coverage plan's stricter reconciliation gates pass.
`partial` is also an evidence claim: the first six stages must be complete,
the exact source bundle and its repository payload objects must be hash-checked,
and the verified directory must contain at least one active body whose legal
classification and exact SGC crosswalk are reviewed. Every geography ID must
exist in the pinned official SGC index.

## Local setup

Use Python 3.12 and Node.js 22, matching GitHub Actions.

```bash
python -m pip install -r requirements.txt

cd web
npm ci --ignore-scripts --no-audit --no-fund
cd ..
```

National ingestion and rollout checks are offline. Downloading an approved
official release is a separate, explicit transport task; adapters and tests
consume locked local bytes.

## Required checks

For national rollout changes, run:

```bash
python -m unittest discover -s tests -p "test_national_*.py"
python scripts/manage_national_rollout.py check
python scripts/manage_national_rollout.py status --format json
python scripts/validate_regional_registry.py
```

For changes that affect the public receipt application, also run:

```bash
cd web
npm test -- --run
npm run build
```

The `National rollout readiness` GitHub workflow repeats the offline national
checks and verifies that validation did not rewrite tracked files. It does not
download official data, publish a registry, or deploy a website.

## Adapter and source expectations

A province/territory adapter pull request should include:

- an official HTTPS landing page and machine-readable request URL;
- a recorded licence or reuse decision;
- an approved release hash, byte count, media type, and source lock;
- a catalogued `recordKeyField` and exact `$`/JSON
  `recordCollectionPath`; roster sources also declare
  `officialLegalTypeField`, a four-field `identityFieldMap`, and the
  `externalIdNamespace`;
- repository-relative payload objects whose observed bytes match that lock;
- a versioned, offline provider whose declared ID/version match the active
  catalog, plus a checked-in importing `unittest` module and minimal fixtures;
- a verified directory whose raw and canonical hashes are pinned;
- official external identifiers and exact code crosswalks;
- explicit unmatched, inactive, dissolved, transitional, and exceptional rows;
- expected counts and a dated reconciliation source;
- field-level provenance for emitted records;
- source-record evidence for every emitted geography edge and parent
  relationship;
- an `identityFieldMap` exactly matching that catalog contract and binding the
  sole emitted external-ID namespace/value, all emitted official-name values,
  legal type, and URL to exact fields in the selected locked source row;
- one classification decision for every record in every locked
  governing-body roster: emitted, routed, or explicitly excluded, with status
  matching disposition and a reason for every non-emitted row;
- tests for encoding, leading zeroes, duplicates, missing parents, malformed
  rows, schema drift, and source tampering.

Name similarity is never an identity join. A census subdivision is never
promoted to a governing body without an official administrative-directory
record. Non-federal bodies require an exact geography crosswalk; federal bodies
must remain Canada-scoped.

`sourceFields[0]` names the stable record-key field. For locked CSV or JSON
evidence, the checker independently selects exactly one row/object through that
field and confirms the same row contains the body external ID plus the claimed
geography code or both sides of a parent relationship. Opaque PDF/HTML formats
must first produce a separately locked normalized CSV/JSON evidence source.

The rollout checker executes the declared adapter tests in a child process with
a guard over common Python socket and child-process APIs. It then runs
`build_verified_directory` in two fresh child processes over the actual locked
payload bytes and requires both plain-JSON results to equal the reviewed
directory artifact. This is a fail-closed correctness guard, not an OS sandbox
for hostile contributor code.

Publication `releaseReference` values are limited to a full commit,
release-tag, or pull-request URL in this repository. The offline checker
validates shape and repository scope; human review must confirm that a
PR/release reference exists.

Production code must not fetch a live endpoint while parsing. Pagination,
conditional requests, throttling, and retries belong to a separately reviewed
transport job. No model call belongs in the ordinary adapter or public runtime.

## AI and cost discipline

The normal path must use official structured data, deterministic parsing,
cached extraction, and human-reviewed exceptions. AI remains disabled by
default. It may be proposed only for a bounded unresolved evidence packet after
deterministic attempts are recorded, and it cannot approve or publish its own
output. Never send a full source document to a model.

## Pull request discipline

- Keep one jurisdiction/layer or one shared infrastructure change per pull
  request.
- Complete the pull request template and link the rollout/source-change issue.
- Separate source snapshots, parser behaviour, and coverage-state changes so a
  reviewer can trace each claim.
- Preserve official names and language tags; do not invent English
  translations.
- Do not include generated caches, secrets, or personal contact fields.
- Do not mark a layer `complete` simply because the parser emitted rows.
- Treat a green pull request as permission to review and merge—not as permission
  to publish. Publication remains a separate approval stage.

Relevant national and workflow files have CODEOWNERS review. Repository
maintainers should configure branch protection to require the `National rollout
readiness` check, CODEOWNER approval, resolved review conversations, and no
force-pushes on the default branch.
