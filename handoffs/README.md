# Municipal model handoffs

This directory is the provider-neutral research boundary for Gemini, Claude,
Grok, Codex, or another capable subscription model.

Models return unverified candidates. They never edit the canonical registry,
receipt packs, release records, GitHub state, Cloudflare state, or publication
status.

## Manual discovery workflow

1. Select one job listed in the checked-in trusted-job manifest, in the
   documented rollout order. The validator binds the job digest, prompt,
   output schema, target-directory path and digest, and exact target record
   before accepting it.
2. Render the complete prompt:

   ```powershell
   python scripts/render_model_handoff_prompt.py `
     --job handoffs/jobs/ontario-waterloo-2026/02-wellesley/job.json
   ```

3. Give that prompt to one signed-in subscription UI or CLI. Use one
   municipality per session.
4. Save exactly the candidate JSON returned by the model outside the repository,
   preferably under the current Windows user's LocalAppData
   `WhatInTheTax\model-handoff` directory.
5. Validate the candidate:

   ```powershell
   $CandidatePath = Join-Path $env:LOCALAPPDATA `
     'WhatInTheTax\model-handoff\wellesley-candidate.json'

   python scripts/validate_model_handoff.py `
     --job handoffs/jobs/ontario-waterloo-2026/02-wellesley/job.json `
     --candidate $CandidatePath
   ```

6. A passing result means `pending-human-review`, not verified or publishable.
   The next pipeline must independently download the source, inspect redirects
   and media type, hash the exact bytes, reconcile years and government levels,
   and verify excerpts before a person can approve it.

The checked-in example is deliberately partial. It demonstrates the contract;
it is not evidence that Wellesley's 2026 source set is complete.

## Bounded prefetched classification

Use this lane after normal code has already downloaded, hashed, and excerpted
official sources. The model receives no browsing tools and cannot fetch a URL.
The current Wellesley packet contains six exact-byte-bound official records
covering five of its seven required document slots. The lower- and upper-tier
service-allocation schedules remain explicit gaps until deterministic
collection finds and locks them.

Dry-run either prepared subscription route without invoking a model:

```powershell
$JobPath = 'handoffs/jobs/ontario-waterloo-2026/02-wellesley/classification/job.json'
$PacketPath = 'handoffs/jobs/ontario-waterloo-2026/02-wellesley/classification/prefetched-source-packet.json'

python scripts/run_subscription_provider_candidate.py `
  --job $JobPath `
  --packet $PacketPath `
  --provider claude

python scripts/run_subscription_provider_candidate.py `
  --job $JobPath `
  --packet $PacketPath `
  --provider agy
```

After reviewing the dry-run summary, an operator can allow exactly one
non-retried subscription turn:

```powershell
$OutputDirectory = Join-Path $env:LOCALAPPDATA 'WhatInTheTax\model-handoff'
New-Item -ItemType Directory -Force $OutputDirectory | Out-Null
$CandidatePath = Join-Path $OutputDirectory 'wellesley-classification.json'

python scripts/run_subscription_provider_candidate.py `
  --job $JobPath `
  --packet $PacketPath `
  --provider claude `
  --execute `
  --confirm-subscription-usage > $CandidatePath

python scripts/validate_model_handoff.py `
  --job $JobPath `
  --packet $PacketPath `
  --candidate $CandidatePath
```

The `agy` command is intentionally dry-run-only. Antigravity 1.1.7 places the
full prompt on the process command line and does not return authoritative
per-run model, tool, or usage metadata. Use its rendered handoff manually and
keep the result quarantined; do not add `--execute`.

For a manual Antigravity handoff, first confirm its subscription sign-in and
that it discovers `whatinthetax-classifier`:

```powershell
agy --add-dir (Get-Location).Path agent
```

Render its packet-bound prompt without invoking a model:

```powershell
python scripts/render_model_handoff_prompt.py `
  --job $JobPath `
  --packet $PacketPath
```

The Claude executable is resolved from its manifest-pinned absolute location
and its SHA-256 must match
[`trusted-provider-clis.json`](trusted-provider-clis.json). Updating a provider
CLI requires a deliberate review of its version, help output, authentication
mode, executable digest, and tests before changing that manifest. A successful
provider process must also keep stderr empty. Timeouts and output overflows
terminate its process tree. The live turn loads no user, project, or local
Claude settings, supplies empty plugin settings, and disables hooks and Git
instructions while retaining access to the saved subscription login. A failure
is never retried automatically.

## Current starter order

The original current-year receipt cohort remains:

1. North Dumfries
2. Wellesley
3. Wilmot
4. Woolwich

North Dumfries already has a draft preview. The new source-mapping jobs therefore
start at sequence 2 with Wellesley, then sequence 3 with Wilmot. Woolwich already
has a draft preview but remains sequence 4 for refresh and completion work.

## Hard boundaries

- Subscription UI or subscription CLI only; no API-key billing mode.
- One job and one candidate at a time.
- Discovery search/fetch/PDF budgets are mandatory operator stop rules.
- Executable classification jobs must set search, fetch, and PDF budgets to
  zero; prompt bytes (20,000 maximum), captured output bytes, and timeout are
  enforced locally.
- `maxOutputTokens` is a declared review budget, not a universal provider-side
  hard cap. Claude must report the exact requested model and finite usage, and
  its result is rejected when reported output tokens exceed the budget.
  Antigravity does not expose equivalent authoritative per-run usage, so it is
  not eligible for automatic execution. The dry-run route still reports a
  conservative captured-byte limit as a transport planning guard; it does not
  cap hidden reasoning tokens or subscription usage.
- Stop at a budget boundary and return gaps; never retry automatically.
- Exact publisher/domain/government-level authority lanes only.
- Every requested document, source, and gap carries a stable `authorityId`;
  shared government levels or domains never make authorities interchangeable.
- Discovery candidates use `packetCanonicalSha256: null`. Classification
  candidates copy the exact prefetched packet digest and its source retrieval
  time, media type, source-content digest, and excerpt digest.
- `producer.runBindingAt` is an execution-wrapper nonce fixed before the
  attempt, not a model completion attestation.
- Draft, unclear, or excerpt-free sources remain gaps; they cannot complete a
  final or approved evidence requirement.
- V1 supports manual source discovery and zero-retrieval prefetched
  classification, using only manifest-listed jobs.
- Unknown or conflicting evidence becomes a gap.
- Every source remains second-check-required.
- Only reviewed, manifest-pinned public official-source packets may be sent.
  Deterministic pattern checks reject common credentials, local paths, contact
  data, and valid-checksum SIN-like values, but those checks are defense in
  depth rather than a privacy guarantee.
- No automatic retry, acceptance, canonical import, deployment, or publication.

The provider-specific Codex exception worker in
[`docs/SUBSCRIPTION-AI-REVIEW.md`](../docs/SUBSCRIPTION-AI-REVIEW.md) remains a
separate, stricter path for bounded excerpts after deterministic extraction has
already failed.
