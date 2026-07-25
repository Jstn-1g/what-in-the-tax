# north-dumfries-on

Reference pack for the Township of North Dumfries (Ontario), fiscal year **2026**.

**Publication status: draft.** Citation audit still reports hard failures (`wrong-page`).
Do not label this Published. See `pack.yaml`, `validation-report.json` (after validate),
`PUBLISH.md`, and `data/citation-audit.json`.

## Bridge layout

Until Phase 1 transcription to YAML (`docs/GENERALIZATION-PLAN.md` §12 item 7), this pack
points at the living artifacts:

| file | role |
|---|---|
| `pack.yaml` | jurisdiction + publication metadata |
| `../../data/evidence-ledger.json` | FACT / DERIVED / GAP / JUDGMENT |
| `../../data/taxpayer-receipt.json` | UI model |
| `../../data/_extracts/` | page-marked text for citation audit |

```bash
python scripts/validate_pack.py north-dumfries-on
# seal only when exit 0:
python scripts/seal_pack.py north-dumfries-on 1
```
