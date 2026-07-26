## Jurisdiction and scope

<!-- Name one jurisdiction/layer, or explain why this is shared infrastructure. -->

- Province/territory:
- Coverage layer:
- Rollout issue:
- Source-change issue, if applicable:
- Source IDs:

## What changed

<!--
Describe source, transport lock, adapter, crosswalk, reconciliation, manifest,
test, UI, or documentation changes.
-->

## Coverage claim

<!--
State the before/after stage values. Do not call a jurisdiction complete unless
every publication gate passes.
-->

- Stages advanced:
- Stages blocked:
- Known unmatched rows/gaps:
- Expected active count and dated source:
- Emitted active count:

## Evidence and reuse

- Official landing page/request URL:
- Release/effective date:
- Snapshot SHA-256:
- Locked payload object path and observed byte count:
- Verified directory raw/canonical SHA-256:
- Pinned SGC membership result:
- Licence/reuse decision:
- Reviewer/decision reference:
- Publication approval artifact, if applicable:
- Publication release reference (full repository commit/release/PR URL):

## Verification

<!-- Paste concise results, not generated caches or full source data. -->

```text
python scripts/manage_national_rollout.py check
python scripts/manage_national_rollout.py status --format json
python -m unittest discover -s tests -p "test_national_*.py"
```

## Checklist

- [ ] This pull request covers one jurisdiction/layer or one clearly shared
      change.
- [ ] Official external identifiers are preserved and name similarity is not
      used as an identity join.
- [ ] Non-federal governing bodies have exact reviewed geography crosswalks.
- [ ] Every emitted geography ID exists in the pinned official SGC index.
- [ ] Official names retain their source language tags; no unreviewed
      translation was invented.
- [ ] Emitting sources are hash/byte-count locked and approved for the intended
      reuse.
- [ ] Locked repository payload objects match every source hash and byte count.
- [ ] The provider identity matches the active catalog; its declared
      `unittest` passed under the I/O guard; and two fresh provider processes
      reproduced the verified directory from locked bytes.
- [ ] Directory legal classifications and exact crosswalk rows cover every
      emitted body/geography edge, including provider-emitted source record
      evidence.
- [ ] Every locked governing-body roster row is emitted, routed, or explicitly
      excluded with aligned status/reason, and the sole emitted identity
      namespace and values match the catalogued map and locked source fields.
- [ ] Inactive, dissolved, transitional, overlapping, and unmatched records
      remain explicit.
- [ ] Positive expected counts and type subtotals reconcile, or the layer
      remains non-complete.
- [ ] Rollout manifest stage changes are supported by artifacts in this pull
      request.
- [ ] No personal information, credentials, private correspondence, or
      unpublished material is included.
- [ ] No ordinary ingestion or browser path requires AI; any bounded gap aid is
      opt-in and cannot auto-publish.
- [ ] National readiness checks pass without rewriting tracked files.
- [ ] Publication approval remains a separate human decision and, when
      complete, its artifact is hash-bound to the same source lock, directory,
      derived count, reviewer, date, and release reference; this pull request
      does not deploy.
