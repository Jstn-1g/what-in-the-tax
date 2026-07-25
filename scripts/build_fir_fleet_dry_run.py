"""
FIR fleet dry run — CODE stamps municipalities from Ontario's public FIR file.

What this is (say this out loud):
  1. Ontario already publishes each municipality's Financial Information Return.
  2. We do NOT ask an AI to invent Paris/Brant numbers.
  3. A script opens the official CSV inside fir_data_YYYY.zip, pulls a few
     well-defined rows, does arithmetic, and writes a small JSON "stub pack"
     per town.
  4. Towns that lack required rows are skipped (fail closed).

What this is NOT:
  - Not a 2026 tax bill
  - Not ND-style by-law citations
  - Not findings / "waste" language
  - Not dependent on volunteers uploading packs

Usage:
  python scripts/build_fir_fleet_dry_run.py
  python scripts/build_fir_fleet_dry_run.py --year 2023 --codes 2920,3001,3024

Requires the zip at source-pdfs/fir/fir_data_<year>.zip (gitignored; download from MMAH).
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIR_DIR = ROOT / "source-pdfs" / "fir"
OUT_DIR = ROOT / "fleet" / "dry-run"

# Demo cohort for the dry run (expand later to all codes that pass gates).
# 2920 = Brant County (single-tier) — the legal billing body for Paris, ON.
# 3001 = North Dumfries Tp (lower-tier) — our gold-pack reference town.
# 3024 = Wellesley Tp — peer township.
DEFAULT_CODES = ("2920", "3001", "3024")

# FIR SLC lines we trust for this stub (same ones already used in the ND ledger).
SLC_POP = "slc.02X.L0041.C01.01"
SLC_GG_BEFORE = "slc.40X.L0299.C01.07"  # General government, Total Expenses Before Adjustments

SOURCE = {
    "id": "mmah-fir",
    "title": "Ontario MMAH Financial Information Return (Multi-Year Report data)",
    "urlPattern": "https://efis.fma.csc.gov.on.ca/fir/MultiYearReport/fir_data_{year}.zip",
    "note": "Amounts are PSAB accrual FIR actuals for the stated year — not the current tax by-law.",
}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def slugify(desc: str, code: str) -> str:
    base = (
        desc.lower()
        .replace(",", "")
        .replace(".", "")
        .replace("'", "")
        .strip()
    )
    for token in (" tp", " c", " t", " r", " uco", " county"):
        pass
    parts = []
    for word in base.replace("/", " ").split():
        if word in {"tp", "c", "t", "r", "uco", "st", "lt", "ut"}:
            continue
        parts.append(word)
    slug = "-".join(parts) if parts else f"muni-{code}"
    return f"{slug}-on"


def extract_rows(zip_path: Path, year: str, codes: set[str]) -> dict[str, dict]:
    """Stream FIR CSV; keep only demo codes + the two SLC lines we need."""
    wanted_slc = {SLC_POP, SLC_GG_BEFORE}
    by_code: dict[str, dict] = {
        c: {"assessmentCode": c, "rows": {}} for c in codes
    }
    member = f"fir_data_{year}.csv"
    with zipfile.ZipFile(zip_path) as zf:
        with zf.open(member) as raw:
            text = io.TextIOWrapper(raw, encoding="utf-8", errors="replace", newline="")
            reader = csv.DictReader(text)
            for row in reader:
                code = (row.get("ASSESSMENT_CODE") or "").strip()
                if code not in codes:
                    continue
                slc = (row.get("SLC") or "").strip()
                if slc not in wanted_slc:
                    continue
                amount_raw = (row.get("AMOUNT") or "").strip()
                if amount_raw == "":
                    continue
                try:
                    amount = float(amount_raw)
                except ValueError:
                    continue
                by_code[code]["municipalityDesc"] = row.get("MUNICIPALITY_DESC")
                by_code[code]["tierCode"] = (row.get("TIER_CODE") or "").strip()
                by_code[code]["sgcCode"] = (row.get("SGC_CODE") or "").strip()
                by_code[code]["rows"][slc] = {
                    "slc": slc,
                    "scheduleDesc": row.get("SCHEDULE_DESC"),
                    "lineDesc": row.get("SCHEDULE_LINE_DESC"),
                    "columnDesc": row.get("SCHEDULE_COLUMN_DESC"),
                    "amount": amount,
                }
    return by_code


def build_stub(year: str, code: str, data: dict, zip_hash: str, zip_name: str) -> dict | None:
    rows = data.get("rows") or {}
    pop_row = rows.get(SLC_POP)
    gg_row = rows.get(SLC_GG_BEFORE)
    missing = []
    if not pop_row:
        missing.append(SLC_POP)
    if not gg_row:
        missing.append(SLC_GG_BEFORE)
    if missing:
        return None  # fail closed — no stub without required rows

    pop = pop_row["amount"]
    gg = gg_row["amount"]
    if pop <= 0:
        return None

    per_capita = round(gg / pop, 2)
    desc = data.get("municipalityDesc") or f"ASSESSMENT_CODE {code}"
    tier = data.get("tierCode") or ""
    tier_label = {"LT": "lower-tier", "UT": "upper-tier", "ST": "single-tier"}.get(tier, tier)

    return {
        "schemaVersion": "fleet-stub-0.1.0",
        "grade": "FIR",
        "badge": "Verified: FIR baseline (not local by-law)",
        "slug": slugify(desc, code),
        "assessmentCode": code,
        "name": desc,
        "tier": tier_label,
        "fiscalYear": int(year),
        "currency": "CAD",
        "source": {
            **SOURCE,
            "url": SOURCE["urlPattern"].format(year=year),
            "localZip": f"source-pdfs/fir/{zip_name}",
            "localZipSha256": zip_hash,
            "marsYear": year,
        },
        "metrics": {
            "populationFir": {
                "amount": pop,
                "slc": SLC_POP,
                "label": "FIR population (Schedule 02)",
            },
            "generalGovernmentExpensesBeforeAdjustments": {
                "amountCad": gg,
                "slc": SLC_GG_BEFORE,
                "label": "General government — Total Expenses Before Adjustments (Schedule 40)",
            },
            "generalGovernmentPerCapita": {
                "amountCad": per_capita,
                "formula": "generalGovernmentExpensesBeforeAdjustments / populationFir",
                "label": "General government $ per FIR capita",
            },
        },
        "gates": {
            "hasPopulation": True,
            "hasGeneralGovernment": True,
            "passed": True,
        },
        "disclaimer": (
            "This is a machine-built FIR baseline stub. It is not a property-tax bill, "
            "not a by-law citation, and not a finding. For by-law-grade receipts see gold packs "
            "(e.g. north-dumfries-on)."
        ),
        "parisNote": (
            "Paris, Ontario is billed through Brant County (single-tier). "
            "A 'Paris' search should resolve to assessment code 2920, not a separate lower-tier pack."
            if code == "2920"
            else None
        ),
        "builtAt": datetime.now(timezone.utc).isoformat(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="FIR fleet dry run (code-only, no AI)")
    parser.add_argument("--year", default="2023")
    parser.add_argument(
        "--codes",
        default=",".join(DEFAULT_CODES),
        help="Comma-separated ASSESSMENT_CODE list",
    )
    args = parser.parse_args()
    year = args.year
    codes = tuple(c.strip() for c in args.codes.split(",") if c.strip())
    zip_path = FIR_DIR / f"fir_data_{year}.zip"
    if not zip_path.exists():
        print(f"MISSING: {zip_path}")
        print("Download from MMAH Multi-Year Report and place it under source-pdfs/fir/")
        print(SOURCE["urlPattern"].format(year=year))
        return 1

    zip_hash = sha256_file(zip_path)
    print("=== FIR fleet dry run (explain-as-we-go) ===")
    print(f"1. Official input: {zip_path.name}  sha256={zip_hash[:12]}…")
    print(f"2. Demo cohort assessment codes: {', '.join(codes)}")
    print("   (2920=Brant County/Paris area, 3001=North Dumfries, 3024=Wellesley)")
    print("3. Streaming CSV — keeping only population + general-government expense rows…")

    extracted = extract_rows(zip_path, year, set(codes))
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    by_code_dir = OUT_DIR / "by-code"
    by_code_dir.mkdir(exist_ok=True)

    index = {
        "schemaVersion": "fleet-index-0.1.0",
        "grade": "FIR",
        "marsYear": year,
        "builtAt": datetime.now(timezone.utc).isoformat(),
        "sourceZip": zip_path.name,
        "sourceZipSha256": zip_hash,
        "method": "code-only-dry-run",
        "municipalityCount": 0,
        "skipped": [],
        "municipalities": [],
    }

    print("4. Building stub packs (fail closed if a required FIR row is missing)…")
    for code in codes:
        stub = build_stub(year, code, extracted.get(code, {}), zip_hash, zip_path.name)
        if stub is None:
            index["skipped"].append({"assessmentCode": code, "reason": "missing required SLC rows"})
            print(f"   SKIP {code} — missing required rows")
            continue
        out_path = by_code_dir / f"{code}.json"
        out_path.write_text(json.dumps(stub, indent=2) + "\n", encoding="utf-8")
        index["municipalities"].append(
            {
                "assessmentCode": code,
                "slug": stub["slug"],
                "name": stub["name"],
                "tier": stub["tier"],
                "generalGovernmentPerCapitaCad": stub["metrics"]["generalGovernmentPerCapita"][
                    "amountCad"
                ],
                "path": f"fleet/dry-run/by-code/{code}.json",
            }
        )
        print(
            f"   OK   {code} {stub['name']:<22} "
            f"GG/capita ${stub['metrics']['generalGovernmentPerCapita']['amountCad']:,.2f}  "
            f"-> {out_path.relative_to(ROOT)}"
        )

    index["municipalityCount"] = len(index["municipalities"])
    index_path = OUT_DIR / "index.json"
    index_path.write_text(json.dumps(index, indent=2) + "\n", encoding="utf-8")

    print(f"5. Directory index written → {index_path.relative_to(ROOT)}")
    print("6. Done. No AI was called. Tokens burned for this run: 0.")
    print()
    print("How to explain this:")
    print("  Ontario publishes FIR → our script copies a few defined rows →")
    print("  does math → writes JSON. Paris resolves to Brant County (2920).")
    print("  Gold by-law receipts (like Ayr/ND) stay a separate, rare track.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
