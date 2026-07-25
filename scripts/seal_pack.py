"""
seal_pack — write an immutable receipts/<slug>/<year>/<revision>/ tree.

Refuses unless validate_pack exits 0. No override flag (PUBLISH.md).

Today this seals the *bridge* artifacts (data/ledger + receipt + pack.yaml +
validation-report + citation-audit). Full two-artifact emission arrives later.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def git_rev() -> str | None:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=str(ROOT), text=True
        ).strip()
        return out
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def main(argv: list[str]) -> int:
    slug = argv[1] if len(argv) > 1 else "north-dumfries-on"
    revision = int(argv[2]) if len(argv) > 2 else 1

    validate = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "validate_pack.py"), slug],
        cwd=str(ROOT),
    )
    if validate.returncode != 0:
        print(
            "REFUSED: validate_pack did not exit 0. Sealing is blocked (PUBLISH.md).",
            file=sys.stderr,
        )
        return 1

    pack_dir = ROOT / "corpus" / slug
    # Minimal YAML/JSON load without requiring PyYAML if pack.json exists
    pack_path = pack_dir / "pack.yaml"
    if not pack_path.exists():
        pack_path = pack_dir / "pack.json"
    if pack_path.suffix == ".json":
        pack = json.loads(pack_path.read_text(encoding="utf-8"))
    else:
        try:
            import yaml  # type: ignore
        except ImportError:
            print("PyYAML required to seal from pack.yaml", file=sys.stderr)
            return 1
        pack = yaml.safe_load(pack_path.read_text(encoding="utf-8"))

    year = str(pack.get("fiscalYear") or pack.get("fiscalYearLabel") or "unknown")
    out = ROOT / "receipts" / slug / year / str(revision)
    if out.exists():
        print(
            f"REFUSED: {out} already exists. Sealed revisions are immutable; "
            f"bump revision (next would be {revision + 1}).",
            file=sys.stderr,
        )
        return 1

    artifacts = pack.get("artifacts") or {}
    ledger = ROOT / artifacts.get("ledger", "data/evidence-ledger.json")
    receipt = ROOT / artifacts.get("receipt", "data/taxpayer-receipt.json")
    audit = ledger.parent / "citation-audit.json"
    report = pack_dir / "validation-report.json"

    out.mkdir(parents=True)
    staged: dict[str, Path] = {
        "evidence-ledger.json": ledger,
        "taxpayer-receipt.json": receipt,
        "citation-audit.json": audit,
        "validation-report.json": report,
        "pack.yaml" if pack_path.suffix == ".yaml" else "pack.json": pack_path,
    }

    file_hashes: dict[str, str] = {}
    for name, src in staged.items():
        if not src.exists():
            print(f"REFUSED: missing input {src}", file=sys.stderr)
            shutil.rmtree(out)
            return 1
        dest = out / name
        shutil.copy2(src, dest)
        file_hashes[name] = sha256_file(dest)

    # manifest written LAST
    manifest = {
        "schemaVersion": "seal-1.0.0",
        "slug": slug,
        "fiscalYear": year,
        "revision": revision,
        "packTag": f"pack/{slug}/{year}.{revision}",
        "engineTag": pack.get("engineTag", "engine/0.1.0-bridge"),
        "sealedAt": datetime.now(timezone.utc).isoformat(),
        "gitRev": git_rev(),
        "files": file_hashes,
        "note": (
            "Bridge seal of legacy data/ artifacts. Re-seal after corpus YAML "
            "transcription; never mutate this directory."
        ),
    }
    manifest_path = out / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    # both-directions check
    on_disk = {p.name for p in out.iterdir() if p.is_file()}
    expected = set(file_hashes) | {"manifest.json"}
    if on_disk != expected:
        print(
            f"REFUSED: manifest/disk mismatch: disk={sorted(on_disk)} expected={sorted(expected)}",
            file=sys.stderr,
        )
        shutil.rmtree(out)
        return 1

    for name, digest in file_hashes.items():
        if sha256_file(out / name) != digest:
            print(f"REFUSED: hash drift on {name}", file=sys.stderr)
            shutil.rmtree(out)
            return 1

    print(json.dumps({"sealed": str(out.relative_to(ROOT)).replace("\\", "/"), "packTag": manifest["packTag"]}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
