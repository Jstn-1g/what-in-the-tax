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

The included canonical directory adapter is an interchange boundary for those
province-specific adapters. It requires:

- a namespaced AuditBack body ID;
- body type and active/inactive/transitional status;
- at least one exact official name keyed by a canonical BCP-47 language tag or
  `und` when the source does not identify a language;
- official HTTPS site;
- at least one official external ID;
- zero or more exact SGC geography IDs;
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
verified-body count. The starting plan truthfully marks only the SGC 2021
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

AI is disabled in `ai_gap_policy.json` and no model client exists in this
package. Creating a packet requires both an enabled policy and explicit per-run
opt-in. A packet also requires:

- the exact unresolved entity and requested fields;
- a locked source hash;
- recorded deterministic attempts;
- at most 3 human/rule-selected, locatable excerpts;
- no excerpt over 1,600 characters;
- no more than 4,800 excerpt characters total;
- normalized-text SHA-256 plus exact character offsets and excerpt hashes;
- a strict tokenizer-independent UTF-8-byte input ceiling and 500-token output
  cap;
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
- SGC ID/version and exact parent-prefix agreement;
- official-name language tags without mandatory English translations;
- source/body province or territory agreement and documented CA-wide rules;
- licence/reuse gates for complete coverage;
- exact production 13-jurisdiction and seven-layer scope;
- rejection of empty non-federal governing-body crosswalks;
- federal/Canada and non-federal/province identity consistency;
- province-safe governing-body/geography crosswalks;
- release-specific national and provincial count reconciliation;
- deterministic output from identical inputs;
- no network calls in unit or CI tests.

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
