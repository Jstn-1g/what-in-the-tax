# Pack scaffold

1. Copy this folder to `corpus/<slug>/` (never edit `_template` in place).
2. Fill `pack.yaml` — every `TODO` / `null` that blocks validation.
3. Acquire sources; record hashes; extract text; commit extracts.
4. Build the ledger (today: extend `scripts/build_evidence_model.py` or a future YAML corpus).
5. Run:

```bash
python scripts/validate_pack.py <slug>
```

6. Seal only when that exits 0:

```bash
python scripts/seal_pack.py <slug> 1
```

7. Follow `PUBLISH.md` before any public "Published" label.

New packs start at **Tier 0** (receipt only). Findings are rare and by hand (`PURPOSE.md`).
