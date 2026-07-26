# Subscription-only AI review

What in the Tax? does not require an OpenAI API key or pay-as-you-go API
billing. The optional AI fallback runs only on a trusted, signed-in operator's
computer through the Codex CLI and its saved ChatGPT subscription session.

This is an exception-review aid, not part of the public application. The
browser, GitHub checks, source ingestion, registry build, and publication gates
remain deterministic and model-free.

## What the worker may do

The normal pipeline must exhaust structured official data, deterministic
extraction, OCR, and human/rule review first. Only then may an operator prepare
a bounded gap packet containing the unresolved fields and small, hash-bound
source excerpts.

The local worker:

1. verifies that Codex is signed in with ChatGPT and that no API credential is
   present;
2. opens one previously validated packet in a fresh, read-only invocation;
3. asks `gpt-5.4-mini` at low reasoning for a schema-constrained candidate
   based only on the included excerpts, or uses `gpt-5.6-luna` when a human
   deliberately selects the escalation lane;
4. rejects tool, file, web, app, plugin, or subagent activity;
5. verifies every quoted span against the packet;
6. records observed subscription token usage, including failed completed turns;
   and
7. writes a review candidate that cannot publish automatically.

Packets are processed one at a time. A candidate is useful only when its exact
evidence survives deterministic verification. An unresolved or conflicting
answer remains a gap.

## Deliberate opt-in

[`national/ai_gap_policy.json`](../national/ai_gap_policy.json) is disabled by
default. Live review requires the checked-in policy to be enabled, a valid
per-run queue, an explicit execution choice, and the exact packet selected by
its hash. Turning on the policy is not approval to process every municipality.

Human review is mandatory. Subscription output is never a source of truth and
must not write directly to the registry, receipt data, fleet plans, or public
site. The normal evidence and publication gates still apply after a reviewer
accepts a candidate.

## Local commands

The checked-in policy remains disabled, and no live subscription run has been
made. The commands below are the operator runbook for a future approved packet;
they will refuse to proceed until the checked-in policy is deliberately
enabled, the queue passes validation, the locked normalized text is available
in the source cache, and the exact packet hash is supplied.

First run the default no-model check. It validates and selects the packet but
does not invoke Codex or consume subscription usage:

```powershell
python scripts/run_subscription_gap_review.py `
  --queue <validated-ai-gap-queue.json> `
  --packet-sha256 <packetCanonicalSha256> `
  --source-cache <content-addressed-source-cache>
```

After reviewing that output, a live first-lane run requires both explicit
subscription confirmations. The worker pins low reasoning and processes only
the selected packet:

```powershell
python scripts/run_subscription_gap_review.py `
  --queue <validated-ai-gap-queue.json> `
  --packet-sha256 <packetCanonicalSha256> `
  --source-cache <content-addressed-source-cache> `
  --model gpt-5.4-mini `
  --execute `
  --confirm-subscription-usage
```

For a difficult packet that a human has selected for the escalation lane,
choose `gpt-5.6-luna` instead of the default model:

```powershell
python scripts/run_subscription_gap_review.py `
  --queue <validated-ai-gap-queue.json> `
  --packet-sha256 <packetCanonicalSha256> `
  --source-cache <content-addressed-source-cache> `
  --model gpt-5.6-luna `
  --execute `
  --confirm-subscription-usage
```

The two live commands are alternatives, not an automatic retry chain. Each
invocation handles one packet, and any output remains pending human review.
Candidates and content-addressed attempt records are written only under the
signed-in user's Windows LocalAppData known folder at
`WhatInTheTax\subscription-review`, never inside the repository or public site.
The location is resolved from Windows rather than trusted from an environment
variable. The attempt record is acquired before Codex starts, so two concurrent
commands cannot consume usage for the same packet, prompt, schema, model, and
reviewed Codex build.

## Authentication boundary

Use only the Codex login already stored by the local CLI. Do not create an API
key for this workflow, put one in an environment file, or copy, inspect, print,
upload, or share `auth.json`. Treat the saved Codex session as a
password-equivalent local credential.

The public site, GitHub Actions, hosted workers, and other shared machines must
not reuse the operator's ChatGPT login. Subscription authentication is for a
trusted local run only. The worker refuses common CI environments even if
someone has copied a valid login there. It also rejects `CODEX_HOME` overrides
and requires the signed-in Windows profile to remain on a fixed local drive.
Profile, app-data, temporary, Windows, PowerShell-module, and Program Files
paths are resolved from Windows and passed to Codex in an allowlisted child
environment.

Before authentication is used, the worker verifies the Codex executable
against [`national/codex_subscription_worker_lock.json`](../national/codex_subscription_worker_lock.json):
the Windows binary must match the reviewed SHA-256 and have a valid
Authenticode signature from the locked OpenAI publisher. A Codex update fails
closed until that lock is deliberately reviewed and refreshed.

## Operating limits

This design keeps model use within the operator's ChatGPT/Codex subscription
allowance, subject to the plan's usage limits. It does not provide unattended
cloud automation, a server-side model endpoint, or guaranteed background
capacity. The signed-in computer and operator must be present for each live
run.

Codex CLI 0.144.4 does not expose a verified provider-side output-token cap for
this command. The worker therefore keeps excerpts and the complete prompt
small, uses low reasoning, constrains the useful JSON shape, processes only one
packet, and records the `turn.completed` usage. The packet's 500-token output
limit is checked after the turn and is an advisory stop, not a promise that
reasoning tokens could not already have been consumed. Failed and over-limit
attempts are not retried automatically.

If Canada-wide throughput eventually requires unattended CI or hosted workers,
that would be a different architecture and billing decision. It must not be
enabled by quietly adding an API key to this workflow.
