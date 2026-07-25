from pathlib import Path
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "source-pdfs"
OUT = ROOT / "data" / "_extracts"
OUT.mkdir(parents=True, exist_ok=True)

FILES = [
    "2026-draft-budget-binder.pdf",
    "2026-plan-and-budget-summary-booklet.pdf",
    "2026_final_budget_book_region.pdf",
]

for name in FILES:
    path = SOURCE / name
    if not path.exists():
        print("missing", path)
        continue
    reader = PdfReader(str(path))
    parts = []
    for i, page in enumerate(reader.pages):
        parts.append(f"\n\n===== PAGE {i + 1} =====\n")
        parts.append(page.extract_text() or "")
    out = OUT / f"{path.stem}.txt"
    out.write_text("".join(parts), encoding="utf-8")
    print(f"wrote {out.name}: {len(reader.pages)} pages, {out.stat().st_size} bytes")
