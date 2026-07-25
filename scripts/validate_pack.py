"""
validate_pack — hard gate before seal/publish.

Implements what PUBLISH.md step 2 can enforce *today* against the living
North Dumfries artifacts (data/ + pack.yaml). Full YAML corpus validation
arrives with Phase 1 transcription; until then this script:

  * loads corpus/<slug>/pack.yaml
  * checks required artifact paths resolve
  * refuses any JUDGMENT with non-null billImpactCad
  * runs scripts/audit_citations.py and records its exit code + counts
  * writes validation-report.json next to the pack
  * exits 0 only when hard citation failures are zero AND structural checks pass

No override flag. Draft previews may still be built; sealing must see exit 0.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    import yaml  # type: ignore
except ImportError:  # pragma: no cover — pack.yaml is tiny; allow JSON twin
    yaml = None

ROOT = Path(__file__).resolve().parents[1]


def load_pack(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    if path.suffix in {".yaml", ".yml"}:
        if yaml is None:
            raise SystemExit(
                "PyYAML is required to read pack.yaml. Install with: pip install pyyaml"
            )
        return yaml.safe_load(text)
    return json.loads(text)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def check_judgments(receipt: dict) -> list[str]:
    errors: list[str] = []
    for finding in receipt.get("findings", []):
        impact = finding.get("billImpactCad", None)
        if impact is not None:
            errors.append(
                f"{finding.get('id')}: JUDGMENT billImpactCad must be null, got {impact!r}"
            )
    return errors


def check_ids_resolve(ledger: dict, receipt: dict) -> list[str]:
    errors: list[str] = []
    fact_ids = {f["id"] for f in ledger.get("facts", [])}
    derived_ids = {d["id"] for d in ledger.get("derived", [])}
    known = fact_ids | derived_ids
    source_ids = {s["id"] for s in ledger.get("sources", [])}

    for f in ledger.get("facts", []):
        sid = f.get("sourceId")
        if sid and sid not in source_ids:
            errors.append(f"fact {f.get('id')} references missing sourceId {sid!r}")

    for d in ledger.get("derived", []):
        for inp in d.get("inputs", []) or []:
            if inp not in known:
                errors.append(f"derived {d.get('id')} references missing input {inp!r}")

    for finding in receipt.get("findings", []):
        for cid in finding.get("citedFactIds", []) or []:
            if cid not in known:
                errors.append(f"finding {finding.get('id')} cites missing id {cid!r}")
        for gid in finding.get("gapIds", []) or []:
            gap_ids = {g["id"] for g in ledger.get("gaps", [])} | {
                g["id"] for g in ledger.get("closedGaps", [])
            }
            if gid not in gap_ids:
                errors.append(f"finding {finding.get('id')} references missing gap {gid!r}")

    return errors


def run_citation_audit(ledger_path: Path) -> tuple[int, dict]:
    script = ROOT / "scripts" / "audit_citations.py"
    proc = subprocess.run(
        [sys.executable, str(script), str(ledger_path)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    audit_path = ledger_path.parent / "citation-audit.json"
    audit = json.loads(audit_path.read_text(encoding="utf-8")) if audit_path.exists() else {}
    return proc.returncode, audit


def main(argv: list[str]) -> int:
    slug = argv[1] if len(argv) > 1 else "north-dumfries-on"
    pack_dir = ROOT / "corpus" / slug
    pack_path = pack_dir / "pack.yaml"
    if not pack_path.exists():
        alt = pack_dir / "pack.json"
        if alt.exists():
            pack_path = alt
        else:
            print(f"ERROR: missing {pack_path}", file=sys.stderr)
            return 1

    pack = load_pack(pack_path)
    artifacts = pack.get("artifacts") or {}
    ledger_rel = artifacts.get("ledger", "data/evidence-ledger.json")
    receipt_rel = artifacts.get("receipt", "data/taxpayer-receipt.json")
    ledger_path = ROOT / ledger_rel
    receipt_path = ROOT / receipt_rel

    errors: list[str] = []
    warnings: list[str] = []

    required_pack_fields = ["slug", "name", "fiscalYear", "publication"]
    for field in required_pack_fields:
        if field not in pack:
            errors.append(f"pack.yaml missing required field {field!r}")

    if pack.get("slug") != slug:
        errors.append(f"pack.slug {pack.get('slug')!r} does not match directory {slug!r}")

    if not ledger_path.exists():
        errors.append(f"ledger missing: {ledger_path}")
    if not receipt_path.exists():
        errors.append(f"receipt missing: {receipt_path}")

    ledger = receipt = {}
    if ledger_path.exists() and receipt_path.exists():
        ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        errors.extend(check_judgments(receipt))
        errors.extend(check_ids_resolve(ledger, receipt))

    audit_code, audit = (1, {})
    if ledger_path.exists():
        audit_code, audit = run_citation_audit(ledger_path)
        hard = sum(
            audit.get("counts", {}).get(t, 0)
            for t in ("not-found", "wrong-page", "bad-page-number")
        )
        if audit_code != 0 or hard:
            errors.append(
                f"citation audit hard failures: {hard} (audit exit {audit_code}). "
                "PUBLISH.md: zero means zero."
            )

    pub = pack.get("publication") or {}
    status = pub.get("status", "draft")
    if status in {"sealed", "published"} and errors:
        errors.append(
            f"publication.status is {status!r} but validation failed — "
            "status must remain draft until the gate is green"
        )
    if status == "published":
        errors.append(
            "publication.status must not be set to published in pack.yaml by hand; "
            "publishing is a logged human act after seal (see PUBLISH.md)"
        )

    content_hashes = {}
    for label, path in (("ledger", ledger_path), ("receipt", receipt_path), ("pack", pack_path)):
        if path.exists():
            content_hashes[label] = {"path": str(path.relative_to(ROOT)).replace("\\", "/"), "sha256": sha256_file(path)}

    report = {
        "slug": slug,
        "validatedAt": datetime.now(timezone.utc).isoformat(),
        "ok": not errors,
        "publicationStatusDeclared": status,
        "errors": errors,
        "warnings": warnings,
        "citationAudit": {
            "exitCode": audit_code,
            "counts": audit.get("counts", {}),
        },
        "contentHashes": content_hashes,
        "engineNote": (
            "Bridge validator for legacy data/ artifacts. Full corpus YAML + Identity "
            "engine arrives with Phase 1 transcription (docs/GENERALIZATION-PLAN.md)."
        ),
    }

    out = pack_dir / "validation-report.json"
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": report["ok"], "errors": len(errors), "wrote": str(out)}, indent=2))
    for e in errors:
        print(f"  ERROR: {e}", file=sys.stderr)

    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
