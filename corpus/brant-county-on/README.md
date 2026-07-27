# brant-county-on (Paris, Ontario)

Tier-0 publication candidate for the **County of Brant**, the single-tier
municipality that bills **Paris, Ontario**. MMAH FIR assessment code **2920**.
There is no separate Town of Paris property-tax pack.

**Publication status: draft candidate, not Published.** The pack contains no
findings, judgments, or open gaps. Passing the machine gate does not record the
named-human publication approval required by `PUBLISH.md`.

## Declared scope

The receipt applies the final 2026 `RT Residential` municipal, hospital, and
education rates to the County-published median residential assessment of
$391,000. It allocates only the municipal portion across the eleven approved
department net requirements, pro rata against their exact $92,457,575 control
total.

It excludes parcel-specific adjustments and rebates, non-RT classes,
special-area charges, water/wastewater and other user fees, peer comparisons,
findings, and judgments. It is an illustration, not an exact tax bill.

## Evidence and reconciliation

| item | result |
|---|---|
| receipt-driving official sources | 2 |
| reviewed source/extract pairs | 2, each SHA-256 and byte locked |
| cited facts | 20 (18 verbatim, 2 normalized) |
| department control | eleven net requirements = $92,457,575 exactly |
| RT rate control | municipal + hospital + education = 0.0125155 exactly |
| County portion at $391,000 | $4,295.33 from the final rate schedule |
| approved-budget illustration | $4,295.35; retained as a cited $0.02 presentation difference |
| full RT illustration | $4,893.56 including education |

The receipt uses the final tax-rate schedule for bill arithmetic. It does not
infer why the approved-budget illustration is two cents higher.

## Artifacts

| file | role |
|---|---|
| `pack.yaml` | jurisdiction, project, licence, coverage, and approval metadata |
| `sources.lock.json` | exact official source, extract, and ledger hashes |
| `../../data/brant/evidence-ledger.json` | FACT and DERIVED evidence model |
| `../../data/brant/taxpayer-receipt.json` | Tier-0 receipt model |
| `../../data/brant/citation-audit.json` | citation and hash-binding audit |
| `../../data/_extracts/brant/` | page-marked text used by the audit |

```bash
python scripts/build_brant_evidence_model.py
python scripts/lock_pack_sources.py brant-county-on
python scripts/validate_pack.py brant-county-on --strict
python -m unittest tests.test_brant_pack
```

The MIT licence covers project-authored receipt and evidence metadata only.
The County source pages display a County of Brant copyright notice; no explicit
reuse licence was identified for the two cited PDFs, so they are not relicensed.

The project corrections route is intentionally marked pending until a public,
anonymous-reader-accessible channel exists. It is not the County's contact
channel and does not imply County review or endorsement.
