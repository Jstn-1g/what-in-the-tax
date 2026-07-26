# Sealed receipt directory

Immutable outputs land here as:

```text
receipts/<slug>/<fiscalYear>/<revision>/
  manifest.json          # written last; sha256 of every sibling file
  evidence-ledger.json
  taxpayer-receipt.json
  citation-audit.json
  validation-report.json
  pack.yaml
```

Created only by `python scripts/seal_pack.py <slug> <revision>`, which refuses unless
`validate_pack` exits 0. Never edit a sealed revision in place — bump `N`
(`docs/VERSIONING.md`, `PUBLISH.md`).

This directory stays empty until the first pack clears the citation-audit hard-fail gate.
