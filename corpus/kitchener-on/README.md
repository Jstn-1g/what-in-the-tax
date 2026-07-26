# kitchener-on (City of Kitchener)

Gold-style draft pack for the **City of Kitchener** — lower-tier municipality in the
**Region of Waterloo**.

Working MMAH code **3012** (pending FIR Schedule 02 lock).

**Publication status: draft.** Run validate before any seal.

## Bill shape (dual-tier)

1. City municipal rate  
2. Region of Waterloo rate (printed on the City tax-rates sheet)  
3. Education  

Average assessment illustration: **$326,000**. City-only increase narrative: **2.2% / $29**.

Region urban household schedule at **$354,500** is imported from the shared
`region-of-waterloo-on` pack as an **informational** illustration — it is **not**
added into the rate×$326,000 bill stack.

## Artifacts

| file | role |
|---|---|
| `pack.yaml` | jurisdiction + publication metadata |
| `../../data/kitchener/evidence-ledger.json` | FACT / DERIVED / GAP |
| `../../data/kitchener/taxpayer-receipt.json` | UI model |
| `../../data/_extracts/kitchener/` | page-marked text for citation audit |

```bash
# Prefer rebuilding Region schedule first when refreshing Region lines:
python scripts/parse_row_household_schedule.py
python scripts/build_region_waterloo_pack.py

python scripts/build_kitchener_evidence_model.py
python scripts/audit_citations.py --ledger data/kitchener/evidence-ledger.json
python scripts/validate_pack.py kitchener-on
```

## Known gaps

- No DERIVED bridge from Region $354,500 urban schedule → City $326,000 rate bill (`GAP-KIT-REGION-ASSESSMENT-BRIDGE`)
- Net tax levy headline vs Appendix B department base reconciliation  
- FIR assessment code lock  

Closed: `GAP-KIT-REGION-SCHEDULE` (urban schedule imported from shared pack).
