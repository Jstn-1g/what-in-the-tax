# Provider-neutral subscription-model handoff

What in the Tax? can use Gemini, Claude, Grok, Codex, or another subscription
model without making any model part of the public application or source of
truth.

The permanent contract is:

```text
hash-bound municipal job
  → signed-in local subscription model
  → quarantined candidate JSON
  → offline candidate validation
  → independent source download and hashing
  → deterministic evidence checks
  → human approval
  → existing release gate
```

The website remains static and model-free. A model cannot mark a candidate
verified, change canonical data, deploy, or publish.

## What “headless” means here

Headless means an operator starts an official provider CLI on the trusted,
signed-in local computer and receives structured output without an interactive
terminal interface. It does not mean automating consumer webpages, sharing
cookies, copying account tokens to a server, or converting a subscription into
an unattended API service.

Each provider authenticates separately and consumes that provider's own
subscription allowance. A ChatGPT subscription does not pay for Gemini, Claude,
or Grok.

As of July 27, 2026, the provider-neutral contract can be used manually with
several subscription clients. The checked-in runner automatically executes only
the locally reviewed Claude route:

| provider | local mode | automatic status | boundary |
|---|---|---|---|
| Claude | `claude --print` | enabled for one reviewed turn | manifest-pinned executable path and digest; strict result envelope; exact requested-model and reported-usage checks; empty built-in tool list and MCP config; safe mode; plan mode; no session persistence |
| Google | Antigravity `agy` | dry-run/manual quarantine only | version 1.1.7 puts the prompt on the command line and does not attest per-run model, tool, or usage metadata |

Codex, Grok, and other signed-in subscription clients can still receive the
same rendered manual handoff. They are not executable adapters until their
local authentication, tool isolation, output handling, and no-retry behaviour
have their own tests.

Provider flags and authentication behaviour can change. Recheck local help and
login state before enabling a provider adapter.

## Files

- [`handoffs/PROMPT.md`](../handoffs/PROMPT.md) is the permanent instruction.
- [`national/schemas/municipal-evidence-handoff-job.schema.json`](../national/schemas/municipal-evidence-handoff-job.schema.json)
  defines the immutable task.
- [`national/schemas/municipal-evidence-candidate.schema.json`](../national/schemas/municipal-evidence-candidate.schema.json)
  defines the only acceptable model response.
- [`scripts/render_model_handoff_prompt.py`](../scripts/render_model_handoff_prompt.py)
  produces a self-contained prompt without using a model or network.
- [`scripts/validate_model_handoff.py`](../scripts/validate_model_handoff.py)
  validates a candidate without network access or canonical writes.
- [`national/schemas/prefetched-source-packet.schema.json`](../national/schemas/prefetched-source-packet.schema.json)
  defines the small, hash-bound input packet for source classification.
- [`national/subscription_provider_runner.py`](../national/subscription_provider_runner.py)
  implements the fail-closed Claude automatic boundary and Antigravity dry-run
  preparation.
- [`scripts/run_subscription_provider_candidate.py`](../scripts/run_subscription_provider_candidate.py)
  dry-runs by default and requires two explicit flags before using subscription
  quota.
- [`handoffs/trusted-job-manifest.json`](../handoffs/trusted-job-manifest.json)
  binds every runnable job to the reviewed prompt, schema, and canonical target
  directory path plus exact target record. Classification jobs additionally
  bind the only acceptable packet path and digest.
- [`handoffs/trusted-provider-clis.json`](../handoffs/trusted-provider-clis.json)
  pins the reviewed Windows provider executable locations and SHA-256 digests.
- [`handoffs/jobs/ontario-waterloo-2026`](../handoffs/jobs/ontario-waterloo-2026)
  starts with Wellesley and Wilmot in the original rollout order.

## What the offline gate proves

The validator:

- strictly parses UTF-8 JSON;
- rejects duplicate keys, floats, non-finite numbers, deep trees, symlinks, and
  oversized payloads;
- applies closed JSON Schemas;
- recomputes the job's canonical SHA-256;
- binds the candidate to the exact job and municipality;
- permits subscription UI/CLI access modes only;
- checks every requested document, source, and gap against one stable
  `authorityId`, then checks its HTTPS host, exact publisher, and government
  level against that same authority entry; authorities may share domains or
  government levels without becoming interchangeable;
- refuses jobs that are not listed in the checked-in trust manifest and binds
  the prompt, output schema, and the selected province/territory target
  directory digest;
- binds classification candidates to the manifest-pinned prefetched packet
  artifact and carries source retrieval time, media type, source-content
  digest, and exact-excerpt digest into review;
- treats draft, unclear, and excerpt-free sources as non-closing evidence that
  must be paired with an explicit gap;
- checks fiscal year, government level, and requested document scope;
- carries explicit prompt, output, search, fetch, PDF-page, and turn ceilings;
- requires every mandatory request to resolve to a source or an explicit gap;
- rejects publication claims and unknown fields, and applies deterministic
  defense-in-depth checks for common credentials, local paths, contact data,
  and valid-checksum SIN-like values; and
- returns a candidate digest while making zero network requests and zero
  canonical writes.

A pass proves only that a candidate is well-formed and safely quarantined. It
does not prove that a URL resolves, a document is official, an excerpt is exact,
or a figure is accurate. Those require independent transport, hashing,
extraction, reconciliation, and human review.

The trusted manifest can list multiple Canadian target directories. Each entry
declares a generic repository-relative path, schema version, `CA-XX`
province/territory jurisdiction, and canonical digest. Each job is bound to one
`targetDirectoryPath` and one `targetRecordId`. Target and assessment
identifiers may be alphanumeric, so the same first-release contract works
outside Ontario without weakening Ontario's existing `on-####` identity
bindings.

The executable runner enforces a 20,000-byte local prompt ceiling, captured
output bytes, elapsed time, one no-tool response plus read-only CLI preflights, and
zero search/fetch/PDF budgets. It resolves Claude from the manifest-pinned
absolute path, verifies the executable SHA-256 before every live run, sanitizes
the child environment, suppresses user/project/local setting sources, disables
hooks, plugins, and Git instructions through inline settings, fails on
unexpected final stderr, and terminates the process tree on timeout or output
overflow. Claude uses one `--print` response with an empty tool list, and its
success envelope must report exactly one turn. Native JSON Schema mode is
deliberately disabled because a provider may internally retry schema-invalid
output. Only the reviewed success envelope is accepted, its `result` must
itself be one strict JSON candidate, and its exact model and finite usage
metadata must match the job. A Claude result is rejected when its reported
output tokens exceed `maxOutputTokens`.

Antigravity has no equivalent authoritative per-run model, tool, usage, or
output-token attestation, and its prompt-on-command-line interface exposes the
packet to other local process inspection. It therefore remains a manual,
quarantined exception lane. Its dry-run byte estimate is a planning guard, not
a provider-guaranteed ceiling on hidden reasoning tokens or subscription
usage.

## Model routing

Use a fast model for the first source-map candidate. Escalate only gaps,
conflicts, scanned documents, and ambiguous adoption status to a stronger model.
Where a claim is material, ask a second provider to review the source
independently before seeing the first answer.

Provider web tools can tokenize entire PDFs and search results before producing
an answer. For fleet-scale work, deterministic transport should download,
hash, extract, and slice official documents first. Give models only bounded
excerpts and unresolved fields. A provider that cannot enforce the job's limits
must remain an operator-run exception lane, not an automatic batch worker.

Discovery jobs and classification jobs are different:

- A discovery job is a manual research handoff. Its retrieval budget is a stop
  rule for the operator and provider, not permission for the checked-in runner
  to browse. Its candidate uses `packetCanonicalSha256: null`, and uncaptured
  source provenance remains explicitly null.
- An `extract-candidates` classification job is executable only when every web,
  fetch, and PDF-page budget is zero and it is paired with the exact
  manifest-pinned prefetched-source packet. Prompt rendering and offline
  validation both require `--packet`; the candidate carries that packet's
  canonical hash and exact source provenance.

`final-tax-rate-instrument` is deliberately broader than “by-law.” Across
Canada the controlling official source may be a municipal by-law, provincial
regulation, approved schedule, order, or another legally operative instrument.

Measure candidate acceptance rate, correction rate, and human-review minutes by
provider. The job and candidate contracts remain unchanged when the preferred
model changes.

## Publication boundary

Model output must stay outside the repository until accepted evidence has been
downloaded and locked by deterministic tooling. Even then, it enters the normal
pack and publication workflow; it does not bypass [`PUBLISH.md`](../PUBLISH.md).

The separate Codex subscription gap worker remains appropriate for small,
hash-bound excerpts after structured extraction and OCR have already failed.
This handoff is the broader, vendor-neutral source-mapping layer.
