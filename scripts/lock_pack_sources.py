"""Create or verify a deterministic source lock for a jurisdiction pack.

The lock binds the exact local source and extracted-text bytes referenced by
an evidence ledger. Remote-only sources remain explicit ``remote-unlocked``
entries and cannot silently become publication-grade evidence.

Usage:
  python scripts/lock_pack_sources.py north-dumfries-on
  python scripts/lock_pack_sources.py north-dumfries-on --check
  python scripts/lock_pack_sources.py north-dumfries-on --stdout
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None

if __package__:
    from scripts.lib.path_safety import (
        PathSafetyError,
        resolve_under_root,
        validate_slug,
    )
else:  # direct ``python scripts/lock_pack_sources.py`` execution
    from lib.path_safety import PathSafetyError, resolve_under_root, validate_slug


ROOT = Path(__file__).resolve().parents[1]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _locked_path(
    value: object,
    *,
    project_root: Path,
    approved_root: Path,
    label: str,
) -> Path | None:
    if value in (None, ""):
        return None
    if not isinstance(value, str):
        raise PathSafetyError(f"{label} must be a project-relative string")
    return resolve_under_root(
        value,
        project_root=project_root,
        approved_root=approved_root,
        label=label,
    )


def build_source_lock(ledger_path: Path, *, project_root: Path = ROOT) -> dict:
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    entries: list[dict] = []

    for source in sorted(ledger.get("sources", []), key=lambda item: item.get("id", "")):
        source_id = source.get("id")
        if not isinstance(source_id, str) or not source_id:
            raise ValueError("every source must have a non-empty string id")

        local_path = _locked_path(
            source.get("localPath"),
            project_root=project_root,
            approved_root=project_root / "source-pdfs",
            label=f"source {source_id} localPath",
        )
        extract_path = _locked_path(
            source.get("extractedText"),
            project_root=project_root,
            approved_root=project_root / "data" / "_extracts",
            label=f"source {source_id} extractedText",
        )

        entry = {
            "id": source_id,
            "url": source.get("url"),
            "authority": source.get("authority"),
            "asOf": source.get("asOf"),
            "license": source.get("license", "unknown"),
            "localPath": (
                local_path.relative_to(project_root).as_posix() if local_path else None
            ),
            "sha256": None,
            "bytes": None,
            "extractedText": (
                extract_path.relative_to(project_root).as_posix()
                if extract_path
                else None
            ),
            "extractedTextSha256": None,
        }

        missing: list[str] = []
        if local_path:
            if local_path.is_file():
                entry["sha256"] = sha256_file(local_path)
                entry["bytes"] = local_path.stat().st_size
            else:
                missing.append("localPath")
        if extract_path:
            if extract_path.is_file():
                entry["extractedTextSha256"] = sha256_file(extract_path)
            else:
                missing.append("extractedText")

        if missing:
            entry["lockStatus"] = "missing"
            entry["missing"] = missing
        elif local_path and extract_path:
            entry["lockStatus"] = "source-and-extract"
        elif local_path:
            entry["lockStatus"] = "source-only"
        elif extract_path:
            entry["lockStatus"] = "extract-only"
        else:
            entry["lockStatus"] = "remote-unlocked"

        entries.append(entry)

    return {
        "schemaVersion": "source-lock-1.0.0",
        "ledgerPath": ledger_path.relative_to(project_root).as_posix(),
        "ledgerSha256": sha256_file(ledger_path),
        "sources": entries,
    }


def load_pack(path: Path) -> dict:
    if yaml is None:
        raise RuntimeError("PyYAML is required to read pack.yaml")
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def canonical_json(document: dict) -> str:
    return json.dumps(document, indent=2, ensure_ascii=False) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("slug")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--stdout", action="store_true")
    args = parser.parse_args(argv)

    try:
        slug = validate_slug(args.slug)
        pack_dir = resolve_under_root(
            f"corpus/{slug}",
            project_root=ROOT,
            approved_root=ROOT / "corpus",
            label="pack directory",
        )
        pack_path = pack_dir / "pack.yaml"
        if not pack_path.is_file():
            raise FileNotFoundError(f"missing pack descriptor: {pack_path}")
        pack = load_pack(pack_path)
        artifacts = pack.get("artifacts") or {}
        ledger_path = resolve_under_root(
            artifacts.get("ledger", "data/evidence-ledger.json"),
            project_root=ROOT,
            approved_root=ROOT / "data",
            label="pack ledger",
        )
        lock_rel = artifacts.get(
            "sourcesLock", f"corpus/{slug}/sources.lock.json"
        )
        lock_path = resolve_under_root(
            lock_rel,
            project_root=ROOT,
            approved_root=pack_dir,
            label="source lock output",
        )
        document = build_source_lock(ledger_path)
        rendered = canonical_json(document)
    except (FileNotFoundError, OSError, ValueError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if args.stdout:
        print(rendered, end="")
        return 0

    if args.check:
        if not lock_path.is_file():
            print(f"ERROR: missing source lock: {lock_path}", file=sys.stderr)
            return 1
        if lock_path.read_text(encoding="utf-8") != rendered:
            print(f"ERROR: source lock is stale: {lock_path}", file=sys.stderr)
            return 1
        print(f"OK: {lock_path.relative_to(ROOT)}")
        return 0

    lock_path.write_text(rendered, encoding="utf-8")
    print(f"wrote {lock_path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
