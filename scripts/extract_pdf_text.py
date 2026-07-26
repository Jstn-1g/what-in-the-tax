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


def extract_one(pdf: Path, out: Path) -> None:
    reader = PdfReader(str(pdf))
    parts: list[str] = []
    for i, page in enumerate(reader.pages):
        parts.append(f"\n\n===== PAGE {i + 1} =====\n")
        parts.append(page.extract_text() or "")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("".join(parts), encoding="utf-8")
    print(f"wrote {out}: {len(reader.pages)} pages, {out.stat().st_size} bytes")


def load_manifest(path: Path) -> list[dict]:
    if yaml is None:
        raise SystemExit("PyYAML required for --pack / --manifest")
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    files = doc.get("extract", {}).get("files") or doc.get("files") or []
    if not files:
        raise SystemExit(f"no extract.files in {path}")
    return files


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdfs", nargs="*", type=Path, help="Explicit PDF paths")
    parser.add_argument("--pack", help="corpus/<slug>/build-inputs.yaml extract.files")
    parser.add_argument("--manifest", type=Path, help="YAML with extract.files or files[]")
    parser.add_argument("--out-dir", type=Path, help="Override output directory")
    args = parser.parse_args(argv)

    jobs: list[tuple[Path, Path]] = []

    if args.pack:
        inputs = ROOT / "corpus" / args.pack / "build-inputs.yaml"
        for entry in load_manifest(inputs):
            pdf = ROOT / entry["pdf"]
            out = ROOT / entry["out"]
            jobs.append((pdf, out))
    elif args.manifest:
        for entry in load_manifest(args.manifest):
            pdf = ROOT / entry["pdf"] if not Path(entry["pdf"]).is_absolute() else Path(entry["pdf"])
            out = ROOT / entry["out"]
            jobs.append((pdf, out))
    elif args.pdfs:
        out_dir = args.out_dir or OUT
        for pdf in args.pdfs:
            p = pdf if pdf.is_absolute() else ROOT / pdf
            jobs.append((p, out_dir / f"{p.stem}.txt"))
    else:
        OUT.mkdir(parents=True, exist_ok=True)
        for name in LEGACY_FILES:
            path = SOURCE / name
            if not path.exists():
                print("missing", path)
                continue
            jobs.append((path, OUT / f"{path.stem}.txt"))

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
