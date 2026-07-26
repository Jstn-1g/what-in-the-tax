# Canada-wide province and territory rollout playbook

This is the operating guide for expanding AuditBack from a national geography
baseline to verified governing bodies in every province and territory. It
covers municipalities, cities, towns, villages, counties, regional and district
bodies, and other official local-government forms without flattening them into
one misleading category.

The current registry foundation is ready for this work, but no province or
territory is yet approved as complete for governing-body coverage. The
checked-in snapshot tracks all 13 jurisdictions with 0 verified source locks
and 0 publication-ready layers: Newfoundland and Labrador and Nova Scotia
remain in `source-discovery`, while the other 11 are `adapter-needed`. The
authoritative machine-readable state is produced by:

```bash
python scripts/manage_national_rollout.py check
python scripts/manage_national_rollout.py status --format json
```

## What “Canada-wide” means

AuditBack tracks seven separate coverage layers for every province and
territory:

1. national geography baseline;
2. current census-subdivision geography;
3. federal, provincial, and territorial governments;
4. municipal and regional governments;
5. Indigenous governments;
6. education taxing authorities;
7. special-purpose taxing authorities.

The municipal/regional layer is only one part of the governing-body graph. A
city can be single-tier, a town can sit below a county or region, and a regional
service body may overlap rather than contain municipalities. Indigenous,
education, and special-purpose bodies remain independent layers.

The current `national/jurisdictions/<CODE>/rollout.json` contract governs the
municipal/regional layer. The full seven-layer matrix remains authoritative in
`national/coverage_plan.json`; parallel layers should receive their own
equally strict contracts rather than being forced into the municipal manifest.

Statistics Canada geography is the join spine, not proof that a governing body
exists. Official legal or administrative directories establish government
identity. Exact published codes establish joins. Names are display values, not
keys.

## GitHub operating model

Each rollout should move through one auditable GitHub thread:

1. Open a **Province/territory rollout** issue for one jurisdiction's
   municipal/regional layer.
2. Record the official sources, body types, expected counts, licence decision,
   identifiers, exceptions, and known gaps in that issue.
3. Update `national/jurisdictions/<CODE>/rollout.json` as evidence is added.
4. Submit a focused pull request using the repository template.
5. Let `National rollout readiness` run the national tests, manifest check,
   status report, and regional pilot validation.
6. Obtain CODEOWNER review for sources, crosswalks, counts, and stage changes.
7. Merge only after every completed stage is supported by reviewed artifacts.
8. Approve publication separately. A merge or green workflow never deploys a
   registry or public receipt.

Use the **Official source change** issue form when an upstream publisher moves
an endpoint, changes a schema or licence, revises identifiers, or announces an
amalgamation/dissolution. Do not quietly repair those changes in an unrelated
pull request; source history is part of the audit trail.

The checked-in workflow and CODEOWNERS rules are advisory until repository
settings require the `National rollout readiness` check and CODEOWNER review.
If the GitHub plan or private-repository settings do not support branch
protection, do not describe those controls as enforced; use documented manual
review or change the repository/plan deliberately.

## Rollout manifest

Each jurisdiction manifest is checked against
`national/schemas/jurisdiction-rollout.schema.json`.
Its locked payloads, verified directory output, and approval decision use
`jurisdiction-source-lock.schema.json`,
`verified-jurisdiction-directory.schema.json`, and
`publication-approval.schema.json`. The national SGC allowlist is
`national/sgc_2021_geography_index.json`, constrained by
`sgc-geography-index.schema.json` and pinned to the catalog-approved Statistics
Canada release.

The required stage sequence is:

| stage | evidence required before `complete` |
|---|---|
| `official-source-identified` | Official publisher, landing page, layer, legal body types, stable identifiers, update cadence |
| `reuse-approved` | Licence URL and reviewed redistribution decision; unresolved terms remain blocked |
| `transport-pinned` | Exact HTTPS request, release/effective date, media type, SHA-256, byte count, immutable source lock, and repository payload object whose observed bytes match |
| `adapter-tested` | Catalog-matching offline provider, importing `unittest` module executed in a guarded child process, fixtures, two fresh identical child-process builds from locked bytes, and raw/canonical hashes for a positive verified directory |
| `exact-crosswalk-reviewed` | Every directory body/geography edge exists in the pinned SGC index and is joined by exact published codes whose source ID, snapshot, and record key match provider-emitted evidence; unmatched rows retained |
| `exceptions-reviewed` | Every locked roster record is emitted, routed, or explicitly excluded; source legal types, tier decisions, inactive/dissolved/transitional/overlapping forms, and jurisdiction-specific exceptions are accounted for; status must match disposition and every non-emitted row requires a reason |
| `count-reconciled` | Positive dated control total and type-level counts equal active records derived from the verified directory |
| `publication-approved` | All earlier required stages accepted and a human approval artifact is hash-bound to the same source lock, directory, count, reviewer, date, and reviewable GitHub commit, release, or pull-request URL |

Allowed stage states are `not-started`, `in-progress`, `blocked`, and
`complete`. All eight municipal-rollout stages are mandatory. Only the first
unfinished stage may be active or blocked; later stages remain `not-started`.
The CLI and schema are authoritative if this prose and the manifest contract
ever differ.
The manifest's overall coverage status is separately constrained to
`not-started`, `source-discovery`, `adapter-needed`, `partial`, `complete`, or
`not-applicable`, and must equal the jurisdiction's municipal/regional status
in `national/coverage_plan.json`. For this nationwide municipal layer,
`not-applicable` is rejected for every province and territory.
`partial` cannot be used as a planning label. It requires the first six stages,
the exact active source bundle, a verified source lock and payload bytes, and at
least one active emitted body with reviewed classification and crosswalk
evidence. Before that point the status remains `adapter-needed` (or
`source-discovery` while the source bundle is incomplete).

`primarySourceIds` is the reviewed candidate bundle, not a claim that those
sources are downloaded or publishable. `sourceRoles` records whether each
candidate supplies a governing-body roster, legal authority, boundary
crosswalk, code history, relationships, or a control total. Geometry and
relationship references cannot by themselves prove government identity.
`coverage_plan.json` keeps `sourceIds` empty until actual locked sources support
`partial` or `complete` evidence; the rollout contract enforces that separation.

The evidence fields are also machine-gated. `transport-pinned` requires an
existing lock bound to that jurisdiction's exact current source bundle and
coverage-layer row; unrelated provinces can advance without invalidating it.
Its actual repository payload files must match the recorded hashes and byte
counts.
Adapter completion requires catalog-matching provider identity, valid Python
provider/test files, fixtures, and a positive verified directory whose raw and
canonical hashes are pinned. The declared tests are run offline, and the
provider is then run twice over the locked payload bytes; its fresh result must
equal the reviewed directory. Crosswalk and classification rows must cover that
directory exactly. Reconciliation counts are derived from its active records,
and a hash-checked human publication-approval artifact with a reviewable GitHub
reference becomes mandatory at the last stage.

## Starting source map

`national/source_catalog.json` is the authority for URLs, licensing, notes, and
current source status. This table is a work-order view, not a completeness
claim.

| code | initial official municipal/regional source | first gate |
|---|---|---|
| AB | Four-source official roster/code/boundary/relationship bundle | Pin the four releases; classify service commissions and non-municipal forms without promoting them to regional governments |
| BC | Municipality and regional-district legal-area datasets | Pin both releases and reconcile them to legal names, tier relationships, and incorporation authority |
| MB | `mb-municipal-officials-directory` | Complete source-specific reuse review; exclude personal contact fields |
| NB | `nb-local-governance` | Emit only proven local governments; retain rural districts separately and treat regional service commissions as shared-service relationships, not regional governments |
| NL | Directory, current boundaries, and regional-board reference | Identify a complete regional-service-board roster/control total before reuse and adapter work |
| NS | Municipality and village boundary datasets | Add a complete official legal roster/authority source; the current village geometry is explicitly cartographic, not legal |
| NT | `nt-maca-communities` | Complete source-specific reuse review and distinguish municipalities from designated authorities |
| NU | Hamlets plus Cities/Towns/Villages legislation | Reconcile every hamlet and the City of Iqaluit against original enactments/amendments, then resolve bulk-roster reuse |
| ON | `on-mmah-municipalities` | Join the official roster to LIO identifiers; keep northern districts as geography unless a governing body is separately proven |
| PE | `pe-municipalities` | Confirm licence coverage for each selected directory and boundary service |
| QC | `qc-mamh-municipal-directory` | Preserve official French names, provincial codes, MRCs, boroughs, metropolitan bodies, and history |
| SK | `sk-municipal-directory` | Obtain bulk-directory reuse permission; use only approved redistributable sources until then |
| YT | `yt-local-government-directory` | Complete source review and keep municipalities, advisory councils, and Indigenous governments distinct |

Two national parallel sources are already planned:

- `statcan-csd-boundaries-2025` for the current census-subdivision layer;
- `isc-first-nations-location` as a national Indigenous-location anchor, while
  reserve geography and government identity remain separate.

### Suggested implementation waves

Waves help share transport and adapter patterns; they do not weaken any
jurisdiction's gate.

1. **Structured, reuse-cleared source bundles:** AB, BC, NB, ON, and QC.
2. **Source-sufficiency work:** NS and NL.
3. **Sources requiring a scoped reuse review:** PE, MB, YT, and NT.
4. **Permission/legal-roster work:** SK and NU.
5. **Parallel national layers:** current CSD, then Indigenous, education, and
   special-purpose authorities.

Within a wave, start with a small fixture cohort that includes at least one
ordinary municipality, one upper-tier/shared-service body where applicable,
one inactive or changed entity, one leading-zero identifier where applicable,
and one deliberately unmatched row.

## Per-jurisdiction implementation sequence

### 1. Define the legal body inventory

List every government form the source can prove. Record forms that are
geographies only, forms that do not levy property tax, upper-tier or overlapping
relationships, and bodies governed by a separate statute or directory. Preserve
the publisher's official language and document how each published legal form
maps—or deliberately does not map—to the canonical municipal or regional body
type. Use the scaffold's `classification-decisions.csv` to record official
legal type, tier, parent/overlap, effective dates, and layer disposition.

### 2. Approve the source before building the adapter

Confirm the publisher, licence, reuse terms, endpoint, release date, update
cadence, media type, stable identifiers, and historical-change fields. If reuse
is unclear, set `reuse-approved` to `blocked`; do not treat accessibility on the
public web as permission to redistribute.

### 3. Pin transport separately

The transport job may use conditional requests, pagination, throttling, and
retries. It stores immutable content-addressed bytes and a source lock. The
adapter receives only local verified bytes and has no HTTP client. A changed
hash is a new source snapshot, never an in-place replacement.
Request only the government-entity fields needed for the registry. If the
official response includes personal contact details or is too large for the
approved repository storage path, leave transport blocked until a reviewed,
field-minimized official endpoint or controlled artifact mechanism exists; do
not commit personal data merely to satisfy the lock.

Generate a candidate-only workspace with:

```bash
python scripts/manage_national_rollout.py scaffold ON --output work/on
```

The scaffold includes source candidates, legal-type decisions, exact-crosswalk
provenance, exceptions, reconciliation, and publication-approval templates. Its
verified directory and approval are marked `candidateOnly`; neither can support
coverage until reviewed promotion explicitly removes that marker and pins the
corresponding evidence hashes.

### 4. Normalize without guessing

Map official fields into each verified-directory record's `body` and
`provenance` objects:

- namespaced AuditBack body ID;
- official body type and active/inactive/transitional status;
- one or more official names with canonical BCP-47 language tags, or `und`;
- province/territory code;
- official HTTPS page;
- at least one official external identifier;
- exact SGC geography IDs;
- source-published legal type, reviewed tier, exact parent-body IDs, and
  effective dates;
- source record key and transform provenance.
- one `geographyEvidence` item for each governed SGC ID and one
  `relationshipEvidence` item for each parent body, each bound to an exact
  locked source record.

In every evidence item, `sourceFields[0]` is the stable record-key field. The
catalog also pins the record key, collection path, roster legal-type field,
four-field identity map, and external-ID namespace.
The checker selects exactly one locked CSV row or JSON object through that field
and verifies the same record contains the official body ID and claimed
geography code, or both child and parent official IDs. Opaque sources must
first produce a separately locked normalized CSV/JSON evidence source.

Each emitted body also carries the same `identityFieldMap` for its external ID,
official name, legal type, and official URL. The checker requires the exact
catalogued namespace/value, rejects additional unproven IDs or name values, and
binds every value to the selected source row. Classification review is
exhaustive over every locked governing-body roster record, including routed and
excluded rows; status must match disposition and every non-emitted row needs a
reason, so an adapter cannot silently drop a municipality and still claim
completion.

Crosswalk `officialExternalId` values use the exact
`namespace:value` identity recorded on the body.

Do not translate a name, infer a government from a boundary, or repair a
missing crosswalk using fuzzy matching.

### 5. Reconcile identity and coverage

Review all unmatched rows. Reconcile active counts by official type against a
dated positive control total. Document dissolutions, amalgamations, boundary
changes, duplicate aliases, upper-tier membership, overlapping bodies, and
source omissions. A layer stays `partial` while any required class or unresolved
count difference remains.

### 6. Advance manifest stages

Advance only the stages supported by the pull request. Run:

```bash
python scripts/manage_national_rollout.py check
python scripts/manage_national_rollout.py status --format json
python -m unittest discover -s tests -p "test_national_*.py"
```

The JSON status output is suitable for a future GitHub summary or public
readiness dashboard; the source manifests remain the reviewable record.

### 7. Approve publication explicitly

`publication-approved` is a human release decision after the technical gates.
It must not be set by an adapter, model, workflow, merge, or row count alone.
The public static registry should be built from approved locked inputs in a
separate release workflow. The approval must reference a reviewable GitHub
commit, release tag, or pull request URL in this repository. Offline validation
checks URL shape and repository scope; the reviewer confirms a PR/release
reference actually exists.

## Adapter acceptance matrix

Every adapter needs compact checked-in tests for the applicable rows below.

| surface | required proof |
|---|---|
| Input contract | Exact headers/schema, encoding/BOM, media type, release version |
| Transport assembly | Pagination/order assembled before parsing; no network in parser tests |
| Identifiers | Leading zeroes preserved; duplicates rejected or explicitly resolved |
| Hierarchy | Parent IDs exist; cycles and contradictory relationships fail closed |
| Lifecycle | Active, inactive, dissolved, amalgamated, and transitional cases |
| Crosswalk | Exact published codes accepted only when present in the pinned SGC index; name-only matches refused; unmatched rows emitted as gaps |
| Provenance | Identity, geography, and relationship evidence each bind source ID, snapshot hash, source record key, fields, and transform; identity also binds adapter version |
| Jurisdiction | Source/body province agrees; Canada-wide exceptions are explicitly catalogued |
| Reuse | Every emitting source is approved for the intended redistribution |
| Reconciliation | Positive expected body count and type subtotals; no “complete” zero-row layer |
| Determinism | Repeated builds over the same locked bytes are byte/semantic identical |
| Tamper handling | Hash, byte-count, lock-path, lock-content, and approved-release changes are rejected |

## Definition of ready

A jurisdiction's municipal/regional layer is ready for publication only when:

- the rollout CLI accepts its manifest;
- all eight required stages are `complete`;
- every emitting source is locked and approved for reuse;
- every source-lock payload path exists and its observed bytes match the
  approved hash and byte count;
- the provider identity matches every active source, its importing tests pass
  offline, and two fresh builds from the locked bytes exactly match the
  hash-pinned directory;
- every active non-federal body has an exact official identifier and geography
  crosswalk present in the pinned official SGC index;
- the official legal types, upper-tier relationships, exceptions, and
  lifecycle changes are represented;
- every locked roster record is emitted, routed, or explicitly excluded, with
  its legal type matching the locked source;
- active emitted rows and explicit gaps reconcile to dated positive official
  counts;
- the coverage plan passes structural production-scope checks: exactly 13
  jurisdictions with all seven layers explicitly declared;
- deterministic and tamper tests pass;
- a CODEOWNER reviews the coverage claim;
- a human records publication approval;
- that approval is an artifact bound to the exact source lock, directory
  hashes, derived count, reviewer, date, and reviewable GitHub release
  reference.

“The adapter runs,” “rows were emitted,” and “the GitHub check is green” are
necessary signals, not a completeness claim.

The local child-process I/O guard catches ordinary network/process use and
premature exits, but it is not an OS-level sandbox for hostile code. Provider
changes still require code review.

## Receipt-data rollout comes afterward

Verifying a governing body does not create a tax receipt. For each confirmed
body, receipt evidence follows a second deterministic-first ladder:

1. official structured API/open data;
2. official CSV or spreadsheet;
3. stable official HTML table;
4. digitally generated PDF extraction;
5. OCR/manual evidence packet;
6. bounded AI gap aid with human review.

Each receipt must retain fiscal year, tax/assessment basis, parent and
overlapping bodies, control totals, citations, formula provenance, and explicit
gaps. Missing evidence produces an unavailable or degraded state—not a zero,
estimate, or substituted nearby municipality.

## Token and operating-cost guardrail

Province/territory discovery, directory ingestion, crosswalks, reconciliation,
status reporting, and the public reader require no model calls. Cache
downloaded bytes and deterministic extraction by content hash. Use AI only
after deterministic and manual/rule-based attempts are recorded, with
human-selected bounded excerpts, explicit per-run opt-in, hard byte/token/cost
ceilings, cached results, and no automatic publication.

## Ongoing maintenance

Every active source needs an owner, refresh cadence, and last-verified release.
Open an Official source change issue when a source moves or changes. A refresh
must:

1. pin the new snapshot instead of overwriting the old one;
2. run schema-drift and deterministic-output tests;
3. reconcile additions, removals, type changes, and relationships;
4. update the jurisdiction manifest and coverage plan truthfully;
5. require a new publication approval.

If a source, licence, crosswalk, or count becomes unverifiable, move the
affected stage to `blocked` and withdraw the completeness claim until it is
resolved.
