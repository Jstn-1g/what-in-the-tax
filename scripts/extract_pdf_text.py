"""Extract text from PDFs into page-marked extracts.

Supports:
  python scripts/extract_pdf_text.py
      → legacy hardcoded North Dumfries / Region list
  python scripts/extract_pdf_text.py --pack waterloo-on
      → files listed under corpus/<slug>/build-inputs.yaml → extract.files
  python scripts/extract_pdf_text.py --manifest path/to/manifest.yaml
  python scripts/extract_pdf_text.py path/to/a.pdf path/to/b.pdf --out-dir data/_extracts/foo
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from pypdf import PdfReader

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from lib.path_safety import (  # noqa: E402
    PathSafetyError,
    resolve_under_root,
    validate_slug,
)

SOURCE = ROOT / "source-pdfs"
OUT = ROOT / "data" / "_extracts"

LEGACY_FILES = [
    "2026-draft-budget-binder.pdf",
    "2026-plan-and-budget-summary-booklet.pdf",
    "2026_final_budget_book_region.pdf",
    "2026-04-27-council-agenda.pdf",
    "2026-04-27-council-minutes.pdf",
    "2026-02-02-special-budget-agenda.pdf",
    "2026-02-02-special-budget-minutes.pdf",
    "2026-02-23-council-agenda.pdf",
]


def resolve_under_approved_root(
    value: str | Path,
    *,
    approved_root: Path,
    label: str,
    allow_absolute: bool = False,
) -> Path:
    """Resolve a path and prove it remains under a project-owned root.

    Manifest paths are intentionally project-relative so pack files remain
    portable. Direct CLI paths may be absolute, but only when they already
    resolve inside the same approved root.
    """

    return resolve_under_root(
        value,
        project_root=ROOT,
        approved_root=approved_root,
        label=label,
        allow_absolute=allow_absolute,
    )


def ensure_output_still_safe(path: Path) -> Path:
    """Recheck an output after creating its parent to catch symlink parents."""

    return resolve_under_approved_root(
        path,
        approved_root=OUT,
        label="extract output",
        allow_absolute=True,
    )


def extract_one(pdf: Path, out: Path) -> None:
    reader = PdfReader(str(pdf))
    parts: list[str] = []
    for i, page in enumerate(reader.pages):
        parts.append(f"\n\n===== PAGE {i + 1} =====\n")
        parts.append(page.extract_text() or "")
    out.parent.mkdir(parents=True, exist_ok=True)
    safe_out = ensure_output_still_safe(out)
    safe_out.write_text("".join(parts), encoding="utf-8")
    print(
        f"wrote {safe_out}: {len(reader.pages)} pages, "
        f"{safe_out.stat().st_size} bytes"
    )


def load_manifest(path: Path) -> list[dict]:
    if yaml is None:
        raise SystemExit("PyYAML required for --pack / --manifest")
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(doc, dict):
        raise PathSafetyError(f"manifest must be a mapping: {path}")
    extract = doc.get("extract") or {}
    if not isinstance(extract, dict):
        raise PathSafetyError(f"manifest extract must be a mapping: {path}")
    files = extract.get("files") or doc.get("files") or []
    if not files:
        raise SystemExit(f"no extract.files in {path}")
    if not isinstance(files, list) or not all(
        isinstance(item, dict) for item in files
    ):
        raise PathSafetyError(f"manifest files must be a list of mappings: {path}")
    return files


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdfs", nargs="*", type=Path, help="Explicit PDF paths")
    parser.add_argument("--pack", help="corpus/<slug>/build-inputs.yaml extract.files")
    parser.add_argument("--manifest", type=Path, help="YAML with extract.files or files[]")
    parser.add_argument("--out-dir", type=Path, help="Override output directory")
    args = parser.parse_args(argv)

    jobs: list[tuple[Path, Path]] = []

    try:
        if args.pack:
            slug = validate_slug(args.pack)
            inputs = resolve_under_approved_root(
                Path("corpus") / slug / "build-inputs.yaml",
                approved_root=ROOT / "corpus",
                label="pack manifest",
            )
            entries = load_manifest(inputs)
            for entry in entries:
                if "pdf" not in entry or "out" not in entry:
                    raise PathSafetyError(
                        f"extract entry must contain 'pdf' and 'out': {inputs}"
                    )
                pdf = resolve_under_approved_root(
                    entry["pdf"],
                    approved_root=SOURCE,
                    label="manifest PDF",
                )
                out = resolve_under_approved_root(
                    entry["out"],
                    approved_root=OUT,
                    label="manifest output",
                )
                jobs.append((pdf, out))
        elif args.manifest:
            for entry in load_manifest(args.manifest):
                if "pdf" not in entry or "out" not in entry:
                    raise PathSafetyError(
                        f"extract entry must contain 'pdf' and 'out': {args.manifest}"
                    )
                pdf = resolve_under_approved_root(
                    entry["pdf"],
                    approved_root=SOURCE,
                    label="manifest PDF",
                )
                out = resolve_under_approved_root(
                    entry["out"],
                    approved_root=OUT,
                    label="manifest output",
                )
                jobs.append((pdf, out))
        elif args.pdfs:
            out_dir_value = args.out_dir or OUT
            out_dir = resolve_under_approved_root(
                out_dir_value,
                approved_root=OUT,
                label="output directory",
                allow_absolute=(
                    args.out_dir is None or Path(out_dir_value).is_absolute()
                ),
            )
            for pdf in args.pdfs:
                p = resolve_under_approved_root(
                    pdf,
                    approved_root=ROOT,
                    label="explicit PDF",
                    allow_absolute=pdf.is_absolute(),
                )
                out = resolve_under_approved_root(
                    out_dir / f"{p.stem}.txt",
                    approved_root=OUT,
                    label="extract output",
                    allow_absolute=True,
                )
                jobs.append((p, out))
        else:
            for name in LEGACY_FILES:
                path = resolve_under_approved_root(
                    Path("source-pdfs") / name,
                    approved_root=SOURCE,
                    label="legacy PDF",
                )
                if not path.exists():
                    print("missing", path)
                    continue
                out = resolve_under_approved_root(
                    Path("data") / "_extracts" / f"{path.stem}.txt",
                    approved_root=OUT,
                    label="legacy output",
                )
                jobs.append((path, out))
    except (KeyError, TypeError, PathSafetyError) as exc:
        print(f"REFUSED: unsafe or invalid extraction path: {exc}", file=sys.stderr)
        return 2

    if not jobs:
        print("nothing to extract", file=sys.stderr)
        return 1

    rc = 0
    for pdf, out in jobs:
        if not pdf.exists():
            print(f"missing {pdf}", file=sys.stderr)
            rc = 1
            continue
        extract_one(pdf, out)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
