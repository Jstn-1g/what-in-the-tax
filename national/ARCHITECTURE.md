# AuditBack national ingestion architecture

## Accuracy boundary

Statistics Canada's Standard Geographical Classification (SGC) is the national
classification spine: it covers provinces and territories, census divisions,
and census subdivisions. SGC 2021 contains 5,161 CSDs. The current intercensal
2025 CSD file contains 5,054, so a successful 2021 classification build is not
misrepresented as current legal-geography coverage. That 2025 layer is an
explicit, non-complete adapter item in the source and coverage plans.

A CSD can be a municipality **or an area treated as equivalent to a
municipality for statistical purposes**, so the pipeline must not promote every
CSD to a governing body.

The registry therefore has two separate collections:

1. `geographies`: official SGC areas and their exact hierarchy.
2. `governingBodies`: bodies verified in an official administrative directory,
   cross-walked to geographies only by exact published identifiers.

Name similarity never establishes identity. Unmatched rows remain visible
coverage gaps.

Official baseline references:

- SGC 2021: <https://www.statcan.gc.ca/en/subjects/standard/sgc/2021/index>
- Classification CSV: <https://www.statcan.gc.ca/en/statistical-programs/document/sgc-cgt-2021-structure-eng.csv>
- Current Census Subdivision Boundary File series: <https://www150.statcan.gc.ca/n1/en/catalogue/92-162-X>

`national/sgc_2021_geography_index.json` is deterministically generated from
the catalog-approved SGC 2021 CSV. The rollout validator binds it to the active
catalog source/hash, coverage classification version, reviewed canonical
digest, counts, hierarchy, and exact ID membership. A correctly shaped or
province-prefixed code is insufficient when it is absent from this index.

## Data flow

```text
official API/download
        |
        v
explicit transport job (HTTPS, rate-limited, conditional GET)
        |
        v
content-addressed payload + immutable snapshot lock
        |
        v
provider adapter (offline, versioned, fixture-tested)
        |
        v
normalized geography or governing-body records
        |
        v
exact-code joins + coverage gates + field provenance
        |
        v
static national registry / municipal receipt build inputs
        |
        +--> unresolved deterministic gap
                  |
                  +--> manual/rule-based resolution first
                  |
                  +--> optional bounded AI packet, human review required
```

The public site reads prebuilt static JSON. It does not call municipal sites,
government APIs, or AI at runtime.

## Source and cache contract

Each active official provider has a stable `sourceId`, publisher, landing page,
request URL, coverage layer, adapter ID/version, refresh policy, `licenseStatus`,
`licenseUrl`, and `reuseReviewRequired` in `source_catalog.json`. A source may
support a `complete` or public-safe claim only when reuse review is closed and
its licence status is on the code-reviewed approval allowlist. In production,
that same gate applies to every source that produces any geography or
governing-body record, even when its coverage layer remains `partial`. Pending
permission may remain catalogued for discovery and coverage planning, but
cannot emit production registry records or support complete coverage.

The plan includes an official municipal/regional starting source for all 13
provinces and territories, the Statistics Canada current-CSD layer, and
Indigenous Services Canada's First Nations Location layer. Each planned source
has an explicit reuse-review flag. A source with unclear ordinary-web-content
terms remains discovery-only until licence review permits redistribution.

Transport metadata is locked as:

- source ID and exact HTTPS request URL;
- SHA-256, byte count, and media type;
- optional effective date, ETag, Last-Modified, and retrieval time.

Payloads live under `objects/<sha-prefix>/<sha256>`. A build reads only bytes
whose observed digest and length match the lock, whose lock contents match the
source/digest path, and whose digest equals the approved catalog release hash.
Ordinary builds omit wall-clock timestamps, so identical official inputs
produce byte-identical registry semantics. Conditional requests and rate limits
belong in the transport job; the builder has no HTTP client.

## Provider adapter contract

An adapter is a small, versioned parser:

```python
class ProviderAdapter(Protocol):
    adapter_id: str
    adapter_version: str

    def parse(
        self, payload: bytes, snapshot: SourceSnapshot
    ) -> AdapterResult: ...
```

Adapters return normalized geographies, governing bodies, and deterministic
gaps. Every normalized record carries source ID, snapshot hash, source record
key, contributing fields, transform description, and adapter version.

Province/territory adapters should be thin mappings over official JSON, CSV,
ArcGIS REST, Socrata, CKAN, or open-data downloads. Pagination, rate limiting,
and HTTP retries happen before parsing. PDF/HTML scraping is a fallback provider,
not the default.

For a municipal rollout, the provider module additionally exposes:

```python
def build_verified_directory(
    *,
    payloads: dict[str, bytes],
    snapshots: dict[str, dict],
    jurisdiction: str,
    source_lock_canonical_sha256: str,
) -> dict: ...
```

The checker executes the manifest-declared `unittest` in a child process with
guarded Python socket and process APIs. It then starts two fresh isolated
provider processes over newly decoded copies of the locked bytes, rejects
non-plain JSON or differing results, and requires the result to equal the
reviewed directory artifact. This guard detects accidental I/O and premature
process exits; it is not presented as an OS-level sandbox for hostile code.

Evidence is independently reselected from locked structured bytes:
the catalog pins `recordKeyField`, `recordCollectionPath`, and, for roster
sources, `officialLegalTypeField`, `identityFieldMap`, and
`externalIdNamespace`; `sourceFields[0]` must repeat that key field.
The key must select exactly one CSV row or JSON object. That record must contain
the official body ID and claimed SGC value for geography edges, or both official
body IDs for a parent edge. The provider's `identityFieldMap` must exactly match
the catalog contract and binds the sole emitted external-ID namespace/value,
all official-name values, legal type, and URL to exact source fields. Opaque
source formats require a separately locked normalized CSV/JSON evidence source
before they can support a coverage claim.

The included version 3 canonical directory adapter is an interchange boundary
for those province-specific adapters. It requires:

- a namespaced AuditBack body ID;
- body type and active/inactive/transitional status;
- at least one exact official name keyed by a canonical BCP-47 language tag or
  `und` when the source does not identify a language;
- official HTTPS site;
- at least one official external ID;
- at least one exact SGC geography ID for every non-federal body; a federal
  body is Canada-scoped and cannot claim a province or territory;
- the source-published legal type and reviewed government tier;
- exact parent governing-body IDs only for lower-tier municipalities; every
  parent must resolve to a same-province/territory upper-tier regional
  government, with unknown parents and cycles rejected;
- nullable ISO effective-from/effective-to dates;
- source record locator and transform metadata.

No English translation is required or invented. A Québec or Indigenous
directory may therefore supply only its published French, Indigenous-language,
or `und` official name. Reviewed display translations, if introduced later,
must remain separate from official names and carry their own review provenance.
Malformed canonical field types are converted to adapter validation errors,
not leaked Python attribute/type errors.

## Coverage model

Canada-wide coverage is a matrix, not one percentage. Every province and
territory is tracked across:

- national geography baseline;
- current CSD geography;
- federal, provincial, and territorial governments;
- municipal and regional governments;
- Indigenous governments;
- education taxing authorities;
- special-purpose taxing authorities.

A layer may be `not-started`, `source-discovery`, `adapter-needed`, `partial`,
`complete`, or `not-applicable`. Every required layer is explicitly rendered
for every province and territory; absent layers are errors rather than silently
defaulting to `not-started`. Production mode requires the exact 13
province/territory codes and the canonical seven-layer list. Reduced fixtures
must explicitly select non-production `test` scope, and the CLI defaults to
strict production scope. `complete` is rejected unless every named official
source is locked, licence-approved for reuse, the SGC
classification/version and release-specific national/provincial counts
reconcile exactly, and administrative layers match a positive expected
verified-body count. `partial` is also an evidence claim: its sources must be
locked and licence-approved, and an administrative layer must contain at least
one verified governing body. A completed census-geography baseline alone
does not advance municipal/regional coverage; source approval remains planned
while the rollout stays `source-discovery` or `adapter-needed`. The starting
plan truthfully marks only the SGC 2021
classification layer complete; the current 2025 CSD and every
government/authority overlay remain non-complete.

Every SGC record ID embeds the build's classification version. The builder also
recomputes the canonical ID, province/territory code, ISO subdivision, parent
level, and parent code prefix. A 2026 adapter record cannot enter a 2021 build.
Governing-body provenance must come from a source catalogued for the body's
province or territory. A CA source may prove province/territory bodies only
under a catalogued multi-jurisdiction rule that names the permitted codes and
documents its basis.

Receipt-data providers form a second matrix per confirmed body:

1. structured official API/open-data endpoint;
2. structured published CSV/XLSX;
3. stable HTML table;
4. digitally generated PDF/table extraction;
5. OCR/manual evidence packet;
6. bounded AI gap aid.

Each stage runs only when earlier deterministic stages cannot supply a field.

## AI gap queue and token controls

AI is disabled in `ai_gap_policy.json`, and the registry build imports no model
client. The optional local subscription wrapper is isolated from that build.
Creating a packet requires both an enabled policy and explicit per-run opt-in.
A packet also requires:

- the exact unresolved entity and requested fields;
- a locked source hash;
- recorded deterministic attempts;
- at most 3 human/rule-selected, locatable excerpts;
- no excerpt over 1,600 characters;
- no more than 4,800 excerpt characters total;
- normalized-text SHA-256 plus exact character offsets and excerpt hashes;
- a strict tokenizer-independent UTF-8-byte excerpt ceiling and a 500-token
  advisory output limit;
- aggregate per-run input, output, and configured price-ceiling cost limits;
- a deterministic packet hash for result caching;
- human review, with automatic publication forbidden.

Full documents are always rejected. Both packet construction and queue
validation merge overlapping excerpt intervals and reject a set of split
excerpts whose union covers the complete normalized document. Queue assembly
recomputes excerpt lengths, text hashes, input ceilings, output caps, and
maximum cost rather than trusting claimed budget fields.

Normalized text is not accepted from a caller-provided hash map. It is stored
under a content-addressed normalized-text object and an immutable lock that
contains the complete verified `SourceSnapshot`, normalizer ID/version, source
hash, text hash, byte length, and character count. Resolution re-verifies the
source snapshot lock, original source object, normalized lock path/content, and
normalized text object before checking offsets and excerpt content. Mutating
the packet source ID/hash and recomputing the packet hash therefore cannot bind
fabricated evidence. The verified full text never enters the model packet; a
model sees only bounded excerpts.

The optional execution boundary is a trusted local Codex CLI session using the
operator's existing ChatGPT subscription, never an API key, hosted worker, or
GitHub Action. It processes one packet per fresh invocation, produces only a
human-review candidate, and cannot publish. Because Codex CLI 0.144.4 exposes
no verified provider-side output-token cap for this command, the worker records
completion usage and checks the 500-token advisory after the turn; small
prompts, low reasoning, serialization, and an atomic attempt ledger are the
preventive controls. See
[`../docs/SUBSCRIPTION-AI-REVIEW.md`](../docs/SUBSCRIPTION-AI-REVIEW.md) for the
operator boundary and limitations.

## Build and rollout

The first production build uses the catalog-approved official SGC CSV hash:

```text
python scripts/build_national_registry.py
  --sgc-csv <downloaded official CSV>
  --sgc-sha256 <verified digest>
  --cache-dir <durable cache>
  --output <registry.json>
  --source-lock-output <sources.lock.json>
```

`--scope production` is the default. `--scope test` is an explicit escape hatch
for reduced offline fixtures and must not be used for a published national
registry.

The GitHub operating procedure, stage evidence, source work order, adapter
acceptance matrix, and definition of ready are maintained in
[`../docs/PROVINCIAL-ROLLOUT.md`](../docs/PROVINCIAL-ROLLOUT.md). Each
jurisdiction records its reviewed state in
`jurisdictions/<CODE>/rollout.json`, validated against
`schemas/jurisdiction-rollout.schema.json`. These offline commands are the
authoritative readiness interface:

```text
python scripts/manage_national_rollout.py check
python scripts/manage_national_rollout.py status --format json
```

The GitHub readiness workflow validates manifests, national tests, and the
regional mapping pilot. It does not fetch official sources, publish a registry,
or deploy the public site.

The pinned SGC index contains 5,473 sorted IDs from the catalog-approved
official release. Rollout validation checks its schema, source hash,
classification version, counts, parent chain, self-digest, reviewed release
digest, and exact membership for every governing-body geography edge.

Municipal rollout manifests separate a reviewed candidate source bundle from
locked coverage evidence. Per-source roles distinguish identity rosters and
legal authority from boundary, code-history, relationship, and control-total
references. All eight rollout gates are mandatory. Completed gates are bound
to existing repository artifacts. The jurisdiction source lock is tied to its
exact current source bundle and coverage-layer row, avoiding cross-country lock
churn, and verifies the actual repository payload bytes. Provider ID/version
must match every active bundle source; its Python
module, importing `unittest`, and fixtures must exist. The test is executed
under the cooperative I/O guard, and two fresh provider processes must return
the same plain JSON as the separately hashed verified directory. That directory
carries canonical bodies plus identity, geography, relationship,
source/snapshot, and adapter provenance.
Classification and exact-crosswalk reviews must cover that directory, count
reconciliation is derived from its active records, and every locked roster row
must be emitted, routed, or explicitly excluded with its official legal type
preserved. Status must match disposition and every non-emitted row must carry a
reason. The final human approval
artifact is bound to the same lock and output hashes. The corresponding
contracts are `schemas/jurisdiction-source-lock.schema.json`,
`schemas/verified-jurisdiction-directory.schema.json`, and
`schemas/publication-approval.schema.json`; the national allowlist uses
`schemas/sgc-geography-index.schema.json`. Candidate scaffolds carry
`candidateOnly: true` and cannot support a coverage claim.

Then add the current 2025 CSD adapter and one official jurisdiction directory at
a time. A province is not
called complete until its municipal/regional source, exceptions, dissolved
bodies, and crosswalks pass review. Indigenous, education, and special-purpose
authorities remain distinct parallel layers rather than being forced into the
municipal table.

Every non-federal governing body must carry at least one validated exact
geography crosswalk. A positive body count cannot make a layer complete when
any counted body is disconnected from the geography spine.

Federal-government records are Canada-scoped: they must use
`provinceTerritory: null` and CA source provenance. Every non-federal governing
body must declare its province or territory. A caller-controlled body type
cannot exempt a provincially scoped record from crosswalk review.

## Testing plan

Every provider adapter must have checked-in, minimal fixtures and tests for:

- BOM/encoding and exact published headers;
- leading-zero codes;
- pagination assembly before parsing;
- duplicate IDs and missing parents;
- inactive/dissolved bodies and effective dates;
- exact code crosswalks and refusal of name-only matches;
- malformed rows failing closed;
- source hash/byte-count tampering;
- source-lock path/content identity and approved-release hashes;
- normalized-text locks bound to verified source snapshots and cache objects;
- classification, catalog, adapter, and provenance version agreement;
- SGC classification/version, exact parent hierarchy, and membership in the
  pinned reviewed index;
- official-name language tags without mandatory English translations;
- source/body province or territory agreement and documented CA-wide rules;
- licence/reuse gates for complete coverage;
- exact production 13-jurisdiction and seven-layer scope;
- rejection of empty non-federal governing-body crosswalks;
- federal/Canada and non-federal/province identity consistency;
- province-safe governing-body/geography crosswalks;
- release-specific national and provincial count reconciliation;
- deterministic output from identical inputs;
- execution of the manifest-declared adapter test and exact equality between
  two fresh provider builds and the reviewed directory artifact;
- no intended network calls in unit or CI tests; the local runner guards common
  Python I/O APIs but is not an OS-level network sandbox.

The shared suite additionally tests immutable cache behavior, locked provenance,
coverage-claim gates, AI opt-in, normalized-text/offset/hash binding, recomputed
per-packet and aggregate token/cost limits, full-document rejection,
deterministic packet hashes, and the guarantee that AI output cannot
auto-publish.

`schemas/registry.schema.json` rejects empty source/geography/coverage/count
shells and constrains the nested geography codes, official names, external IDs,
coverage rows, and count shapes. Cross-field semantics such as array counts,
exact SGC prefix relationships, provenance-to-lock identity, licensing, and
coverage completeness remain enforced by `NationalRegistryBuilder`; JSON
Schema alone is not presented as sufficient publication validation.
