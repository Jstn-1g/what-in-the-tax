"""
seal_pack — write an immutable receipts/<slug>/<year>/<revision>/ tree.

Refuses unless validate_pack exits 0. No override flag (PUBLISH.md).

Today this seals the *bridge* artifacts (data/ledger + receipt + pack.yaml +
validation-report + citation-audit + any declared sources lock). Full
two-artifact emission arrives later.
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
sys.path.insert(0, str(ROOT / "scripts"))

from lib.path_safety import (  # noqa: E402
    PathSafetyError,
    resolve_under_root,
    validate_fiscal_year,
    validate_positive_integer,
    validate_slug,
)


def safe_project_path(
    value: str | Path,
    *,
    approved_root: Path,
    label: str,
    base: Path | None = None,
    allow_absolute: bool = False,
) -> Path:
    return resolve_under_root(
        value,
        project_root=ROOT,
        approved_root=approved_root,
        label=label,
        base=base,
        allow_absolute=allow_absolute,
    )


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


def load_pack_file(pack_path: Path) -> dict:
    if pack_path.suffix == ".json":
        document = json.loads(pack_path.read_text(encoding="utf-8"))
    else:
        try:
            import yaml  # type: ignore
        except ImportError as exc:
            raise PathSafetyError("PyYAML required to seal from pack.yaml") from exc
        try:
            document = yaml.safe_load(pack_path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            raise PathSafetyError(f"invalid pack YAML: {pack_path}") from exc
    if not isinstance(document, dict):
        raise PathSafetyError(f"pack must be a mapping: {pack_path}")
    return document


def refuse(message: str) -> int:
    print(f"REFUSED: {message}", file=sys.stderr)
    return 1


def cleanup_created_output(out: Path, receipts_root: Path) -> None:
    """Remove only an output still proven to be the directory we created."""

    if out.is_symlink():
        return
    try:
        safe_out = safe_project_path(
            out,
            approved_root=receipts_root,
            label="seal output cleanup",
            allow_absolute=True,
        )
    except PathSafetyError:
        return
    if safe_out.exists() and safe_out.is_dir() and not safe_out.is_symlink():
        shutil.rmtree(safe_out)


def main(argv: list[str]) -> int:
    corpus_root = ROOT / "corpus"
    data_root = ROOT / "data"
    receipts_root = ROOT / "receipts"

    try:
        slug = validate_slug(
            argv[1] if len(argv) > 1 else "north-dumfries-on"
        )
        revision = validate_positive_integer(
            argv[2] if len(argv) > 2 else 1,
            label="revision",
        )

        pack_dir = safe_project_path(
            slug,
            base=corpus_root,
            approved_root=corpus_root,
            label="pack directory",
        )
        yaml_path = safe_project_path(
            "pack.yaml",
            base=pack_dir,
            approved_root=corpus_root,
            label="pack descriptor",
        )
        json_path = safe_project_path(
            "pack.json",
            base=pack_dir,
            approved_root=corpus_root,
            label="pack descriptor",
        )
        if yaml_path.is_file():
            pack_path = yaml_path
        elif json_path.is_file():
            pack_path = json_path
        else:
            return refuse(f"missing pack descriptor under {pack_dir}")

        pack = load_pack_file(pack_path)
        if pack.get("slug") != slug:
            raise PathSafetyError(
                f"pack slug {pack.get('slug')!r} does not match {slug!r}"
            )
        year_value = pack.get("fiscalYear")
        if year_value is None:
            year_value = pack.get("fiscalYearLabel")
        year = validate_fiscal_year(year_value)

        artifacts = pack.get("artifacts") or {}
        if not isinstance(artifacts, dict):
            raise PathSafetyError("pack artifacts must be a mapping")
        ledger_value = artifacts.get("ledger", "data/evidence-ledger.json")
        receipt_value = artifacts.get("receipt", "data/taxpayer-receipt.json")
        source_lock_value = artifacts.get("sourcesLock")
        ledger = safe_project_path(
            ledger_value,
            approved_root=data_root,
            label="ledger artifact",
        )
        receipt = safe_project_path(
            receipt_value,
            approved_root=data_root,
            label="receipt artifact",
        )
        if not ledger.is_file():
            return refuse(f"missing input {ledger}")
        if not receipt.is_file():
            return refuse(f"missing input {receipt}")
        source_lock: Path | None = None
        source_lock_hash_before_validation: str | None = None
        if source_lock_value is not None:
            source_lock = safe_project_path(
                source_lock_value,
                approved_root=pack_dir,
                label="source lock artifact",
            )
            if not source_lock.is_file():
                return refuse(f"missing input {source_lock}")
            source_lock_hash_before_validation = sha256_file(source_lock)

        out = safe_project_path(
            Path(slug) / year / str(revision),
            base=receipts_root,
            approved_root=receipts_root,
            label="seal output",
        )
        if out.exists():
            return refuse(
                f"{out} already exists. Sealed revisions are immutable; "
                f"bump revision (next would be {revision + 1})."
            )
        pack_hash_before_validation = sha256_file(pack_path)
    except (json.JSONDecodeError, OSError, PathSafetyError) as exc:
        return refuse(f"unsafe or invalid pack configuration: {exc}")

    validate = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "validate_pack.py"),
            slug,
            "--strict",
        ],
        cwd=str(ROOT),
    )
    if validate.returncode != 0:
        print(
            "REFUSED: validate_pack did not exit 0. Sealing is blocked (PUBLISH.md).",
            file=sys.stderr,
        )
        return 1

    try:
        if sha256_file(pack_path) != pack_hash_before_validation:
            raise PathSafetyError("pack descriptor changed during validation")
        if source_lock is not None:
            source_lock = safe_project_path(
                source_lock_value,
                approved_root=pack_dir,
                label="source lock artifact",
            )
            if (
                source_lock_hash_before_validation is None
                or sha256_file(source_lock) != source_lock_hash_before_validation
            ):
                raise PathSafetyError("source lock changed during validation")

        # Re-resolve every pack-controlled source after the validator returns.
        # This catches symlink or descriptor changes before any seal directory
        # is created.
        ledger = safe_project_path(
            ledger_value,
            approved_root=data_root,
            label="ledger artifact",
        )
        receipt = safe_project_path(
            receipt_value,
            approved_root=data_root,
            label="receipt artifact",
        )
        audit = safe_project_path(
            "citation-audit.json",
            base=ledger.parent,
            approved_root=data_root,
            label="citation audit",
        )
        report = safe_project_path(
            "validation-report.json",
            base=pack_dir,
            approved_root=corpus_root,
            label="validation report",
        )
        out = safe_project_path(
            Path(slug) / year / str(revision),
            base=receipts_root,
            approved_root=receipts_root,
            label="seal output",
        )

        staged: dict[str, tuple[Path, Path]] = {
            "evidence-ledger.json": (ledger, data_root),
            "taxpayer-receipt.json": (receipt, data_root),
            "citation-audit.json": (audit, data_root),
            "validation-report.json": (report, corpus_root),
            "pack.yaml" if pack_path.suffix == ".yaml" else "pack.json": (
                pack_path,
                corpus_root,
            ),
        }
        if source_lock is not None:
            staged["sources.lock.json"] = (source_lock, pack_dir)
        for src, approved_root in staged.values():
            checked = safe_project_path(
                src,
                approved_root=approved_root,
                label="seal input",
                allow_absolute=True,
            )
            if not checked.is_file():
                return refuse(f"missing input {checked}")
        if out.exists():
            return refuse(
                f"{out} appeared during validation; sealed revisions are immutable"
            )
    except (OSError, PathSafetyError) as exc:
        return refuse(f"unsafe or invalid seal input: {exc}")

    try:
        out.mkdir(parents=True)
        checked_out = safe_project_path(
            out,
            approved_root=receipts_root,
            label="seal output",
            allow_absolute=True,
        )
        if checked_out != out:
            raise PathSafetyError("seal output changed through a symlink")
        out = checked_out
    except (OSError, PathSafetyError) as exc:
        return refuse(f"could not create safe seal output: {exc}")

    file_hashes: dict[str, str] = {}
    try:
        for name, (src, approved_root) in staged.items():
            checked_src = safe_project_path(
                src,
                approved_root=approved_root,
                label=f"seal input {name}",
                allow_absolute=True,
            )
            dest = safe_project_path(
                name,
                base=out,
                approved_root=out,
                label=f"seal output {name}",
            )
            shutil.copy2(checked_src, dest)
            file_hashes[name] = sha256_file(dest)
    except (OSError, PathSafetyError) as exc:
        cleanup_created_output(out, receipts_root)
        return refuse(f"could not stage safe seal inputs: {exc}")

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
    try:
        manifest_path = safe_project_path(
            "manifest.json",
            base=out,
            approved_root=out,
            label="seal manifest",
        )
        manifest_path.write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )
    except (OSError, PathSafetyError) as exc:
        cleanup_created_output(out, receipts_root)
        return refuse(f"could not write safe seal manifest: {exc}")

    # both-directions check
    on_disk = {p.name for p in out.iterdir() if p.is_file()}
    expected = set(file_hashes) | {"manifest.json"}
    if on_disk != expected:
        print(
            f"REFUSED: manifest/disk mismatch: disk={sorted(on_disk)} expected={sorted(expected)}",
            file=sys.stderr,
        )
        cleanup_created_output(out, receipts_root)
        return 1

    for name, digest in file_hashes.items():
        if sha256_file(out / name) != digest:
            print(f"REFUSED: hash drift on {name}", file=sys.stderr)
            cleanup_created_output(out, receipts_root)
            return 1

    print(json.dumps({"sealed": str(out.relative_to(ROOT)).replace("\\", "/"), "packTag": manifest["packTag"]}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
