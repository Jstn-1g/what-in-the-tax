"""Extract Brant County source PDFs into page-marked text for citation audit."""
from __future__ import annotations

from pathlib import Path

from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "source-pdfs" / "brant"
OUT = ROOT / "data" / "_extracts" / "brant"
OUT.mkdir(parents=True, exist_ok=True)

# Overview PDF remains on disk for searchTrail work; it is not a receipt-driving
# source in build_brant_evidence_model.py, so it must not land under
# data/_extracts/brant/ (extract_pdf_text.py --check treats unclaimed extracts
# as provenance defects). Mine it via --uncited when needed.
FILES = [
    "2026-approved-budget-accessible.pdf",
    "2026-tax-rates.pdf",
]

for name in FILES:
    path = SOURCE / name
    if not path.exists():
        print("missing", path)
        continue
    reader = PdfReader(str(path))
    parts: list[str] = []
    for i, page in enumerate(reader.pages):
        parts.append(f"\n\n===== PAGE {i + 1} =====\n")
        parts.append(page.extract_text() or "")
    out = OUT / f"{path.stem}.txt"
    out.write_text("".join(parts), encoding="utf-8", newline="\n")
    print(f"wrote {out.name}: {len(reader.pages)} pages, {out.stat().st_size} bytes")
