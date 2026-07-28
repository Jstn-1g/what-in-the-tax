#!/usr/bin/env python3
"""Build FIR-grade functional receipts for every Ontario municipality.

Reads Ontario's published Financial Information Return, extracts the Schedule 40
functional expense breakdown, and writes one receipt per municipality. No AI, no
network, no model client. Tokens burned per run: 0.

    python scripts/build_fir_functional_receipts.py
    python scripts/build_fir_functional_receipts.py --year 2023 --check

What this is
------------
A resident-facing composition of *where a municipality's money went by function*,
sourced entirely from the municipality's own filing. Fire, roads, winter control,
parks, libraries, planning - the lines the FIR itself publishes.

What this is not
----------------
Not a tax bill, not a by-law citation, not a finding, and not a comparison
instrument. FIR figures are PSAB accrual actuals for a past year, filed by the
municipality. Gold by-law packs remain a separate and higher evidence grade.

Structure of Schedule 40
------------------------
The hierarchy is encoded in the line numbers, not in a separate field:

    L####99   rollup total for a functional group (L0499 Protection services)
    L9910     grand total for the schedule
    L19xx     "Other" - carries no L1999 rollup row and may be NEGATIVE
    otherwise a component line belonging to group L<first two digits>99

Two identities hold across all 435 filers on the 2023 basis and are asserted per
municipality rather than assumed:

    sum(components of a group)            == that group's rollup total
    sum(group totals) + sum(L19xx Other)  == L9910 grand total

A municipality failing either identity is skipped with a recorded reason. A
skipped municipality is a correct outcome; an invented number never is.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import re
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIR_DIR = ROOT / "source-pdfs" / "fir"
OUT_ROOT = ROOT / "web" / "public" / "fir"

# Schedule 40, column 01, measure 07 = Total Expenses Before Adjustments.
# Restricting to one column keeps every emitted figure on a single declared
# basis; mixing measures is how a receipt silently stops reconciling.
LINE_RE = re.compile(r"^slc\.40X\.L(\d{4})\.C01\.07$")
GRAND_LINE = "9910"
OTHER_GROUP = "1999"

SLC_POPULATION = "slc.02X.L0041.C01.01"

# Cent-level tolerance. FIR amounts are whole dollars, so anything above this is
# a real disagreement rather than floating-point noise.
IDENTITY_TOLERANCE_CAD = 0.51

# Declared, not discovered. See build_fir_fleet_dry_run.py for the distribution
# this floor responds to: median general government per capita is $322.59
# overall but $1,162.57 below population 500, and the curve is continuous. Any
# floor is a judgement, so it is recorded as one.
COMPARABILITY_POPULATION_FLOOR = 5000

SOURCE = {
    "id": "mmah-fir",
    "title": "Ontario MMAH Financial Information Return (Multi-Year Report data)",
    "urlPattern": "https://efis.fma.csc.gov.on.ca/fir/MultiYearReport/fir_data_{year}.zip",
    "schedule": "Schedule 40 - Consolidated Statement of Operations: Expenses",
    "measure": "Total Expenses Before Adjustments (column 01, measure 07)",
    "note": (
        "PSAB accrual FIR actuals for the stated fiscal year, filed by the "
        "municipality. Not a current tax by-law, tax bill, or audit."
    ),
}


class ReceiptBuildError(RuntimeError):
    """Raised when the build cannot proceed safely."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def resolve_built_at(explicit: str | None = None) -> str | None:
    """Optional, reproducible release metadata.

    Content builds omit wall-clock time by default so ordinary verification runs
    do not dirty tracked artifacts. Release automation opts in explicitly.
    """

    if explicit:
        parsed = datetime.fromisoformat(explicit.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ReceiptBuildError("--built-at must include a timezone")
        return parsed.astimezone(timezone.utc).isoformat()
    epoch = os.environ.get("SOURCE_DATE_EPOCH")
    if epoch is None:
        return None
    return datetime.fromtimestamp(int(epoch), timezone.utc).isoformat()


def slugify(desc: str, code: str) -> str:
    base = desc.lower().replace(",", "").replace(".", "").replace("'", "").strip()
    parts = [
        word
        for word in base.replace("/", " ").split()
        if word not in {"tp", "c", "t", "r", "uco", "st", "lt", "ut"}
    ]
    return f"{'-'.join(parts) if parts else f'muni-{code}'}-on"


def extract(zip_path: Path, year: str, codes: set[str] | None) -> dict[str, dict]:
    """Stream the FIR CSV once, keeping only the rows this receipt needs."""

    member = f"fir_data_{year}.csv"
    collected: dict[str, dict] = {}
    with zipfile.ZipFile(zip_path) as archive:
        if member not in archive.namelist():
            raise ReceiptBuildError(f"{zip_path.name} does not contain {member}")
        with archive.open(member) as raw:
            stream = io.TextIOWrapper(raw, encoding="utf-8", errors="replace", newline="")
            for row in csv.DictReader(stream):
                code = (row.get("ASSESSMENT_CODE") or "").strip()
                if not code or (codes is not None and code not in codes):
                    continue
                slc = (row.get("SLC") or "").strip()
                amount_raw = (row.get("AMOUNT") or "").strip()
                if amount_raw == "":
                    continue
                try:
                    amount = float(amount_raw)
                except ValueError:
                    continue

                entry = collected.setdefault(
                    code,
                    {
                        "assessmentCode": code,
                        "lines": {},
                        "population": None,
                        "name": None,
                        "tier": "",
                        "sgcCode": "",
                    },
                )
                entry["name"] = (row.get("MUNICIPALITY_DESC") or "").strip() or entry["name"]
                entry["tier"] = (row.get("TIER_CODE") or "").strip() or entry["tier"]
                entry["sgcCode"] = (row.get("SGC_CODE") or "").strip() or entry["sgcCode"]

                if slc == SLC_POPULATION:
                    entry["population"] = amount
                    continue

                matched = LINE_RE.match(slc)
                if matched:
                    entry["lines"][matched.group(1)] = {
                        "slc": slc,
                        "label": (row.get("SCHEDULE_LINE_DESC") or "").strip(),
                        "amountCad": amount,
                    }
    return collected


def build_comparability(population: float | None, tier_label: str, year: str) -> dict:
    """Machine-readable non-comparability, refusing by default.

    PURPOSE.md puts rankings, scores and leaderboards out of scope and requires
    non-comparability to be machine-readable with refusal as the default
    (GENERALIZATION-PLAN 10.11). crossMunicipalityComparable is unconditionally
    False: functional scope depends on tier, so the three tiers were never
    interchangeable regardless of population.
    """

    below_floor = population is not None and population < COMPARABILITY_POPULATION_FLOOR
    blockers = [
        {
            "code": "tier-scope-differs",
            "detail": (
                "Functional scope depends on tier. A lower-tier municipality's "
                "figures exclude upper-tier services billed to the same "
                "resident, so lower-, upper- and single-tier receipts are not "
                "interchangeable."
            ),
        }
    ]
    if below_floor:
        blockers.append(
            {
                "code": "population-below-declared-floor",
                "detail": (
                    f"FIR population {population:,.0f} is below the declared "
                    f"floor of {COMPARABILITY_POPULATION_FLOOR:,}. Below it, "
                    "per-capita figures mostly measure the indivisible fixed "
                    "cost of running a municipal corporation rather than "
                    "spending behaviour."
                ),
            }
        )
    return {
        "crossMunicipalityComparable": False,
        "reason": "FIR functional receipt is a composition, not a comparison instrument",
        "basis": {
            "fiscalYear": int(year),
            "sourceId": SOURCE["id"],
            "measure": "totalExpensesBeforeAdjustments",
            "tier": tier_label,
        },
        "declaredPopulationFloor": COMPARABILITY_POPULATION_FLOOR,
        "belowPopulationFloor": below_floor,
        "blockers": blockers,
        "note": (
            "Any cross-municipality reading requires one common fiscal year, one "
            "common basis, and the same tier - and even then this is a filing, "
            "not a rate or bill comparison."
        ),
    }


def build_receipt(
    year: str,
    entry: dict,
    zip_hash: str,
    zip_name: str,
    built_at: str | None,
) -> tuple[dict | None, str | None]:
    """Return (receipt, skip_reason). Exactly one is non-None."""

    lines = entry["lines"]
    if GRAND_LINE not in lines:
        return None, "missing Schedule 40 grand total (L9910)"

    groups: dict[str, dict] = {}
    components: dict[str, list[dict]] = {}
    for code, line in lines.items():
        if code == GRAND_LINE:
            continue
        if code.endswith("99"):
            groups[code] = line
        else:
            components.setdefault(code[:2] + "99", []).append({**line, "code": code})

    # "Other" (L19xx) publishes no rollup row, so its total is the sum of its own
    # components. It can legitimately be negative - recoveries and adjustments
    # land here - and two Ontario municipalities report it that way.
    other_components = sorted(
        components.pop(OTHER_GROUP, []), key=lambda item: item["code"]
    )
    other_total = sum(item["amountCad"] for item in other_components)

    # A component whose rollup row is absent would be silently dropped from the
    # total. Refuse rather than under-report.
    orphans = sorted(set(components) - set(groups))
    if orphans:
        return None, f"component lines without a published rollup: {orphans}"

    functions = []
    for group_code in sorted(groups):
        group = groups[group_code]
        members = sorted(components.get(group_code, []), key=lambda item: item["code"])
        member_sum = sum(item["amountCad"] for item in members)
        if abs(member_sum - group["amountCad"]) > IDENTITY_TOLERANCE_CAD:
            return None, (
                f"group L{group_code} components sum to {member_sum:,.2f} "
                f"but the filing reports {group['amountCad']:,.2f}"
            )
        functions.append(
            {
                "code": group_code,
                "slc": group["slc"],
                "label": group["label"],
                "amountCad": group["amountCad"],
                "components": [
                    {
                        "code": item["code"],
                        "slc": item["slc"],
                        "label": item["label"],
                        "amountCad": item["amountCad"],
                    }
                    for item in members
                ],
            }
        )

    grand = lines[GRAND_LINE]["amountCad"]
    computed = sum(item["amountCad"] for item in functions) + other_total
    if abs(computed - grand) > IDENTITY_TOLERANCE_CAD:
        return None, (
            f"functions plus other sum to {computed:,.2f} but the filing "
            f"reports a grand total of {grand:,.2f}"
        )

    population = entry["population"]
    per_capita = round(grand / population, 2) if population and population > 0 else None
    tier_label = {"LT": "lower-tier", "UT": "upper-tier", "ST": "single-tier"}.get(
        entry["tier"], entry["tier"]
    )
    name = entry["name"] or f"ASSESSMENT_CODE {entry['assessmentCode']}"

    # Shares are reported only when the denominator is positive. A negative or
    # zero grand total makes a percentage meaningless rather than merely odd.
    shares_reported = grand > 0
    if shares_reported:
        for function in functions:
            function["shareOfTotal"] = round(function["amountCad"] / grand, 6)

    receipt = {
        "schemaVersion": "fir-functional-receipt-0.1.0",
        "grade": "FIR",
        "badge": "FIR baseline filing (not a local by-law receipt)",
        "isReceipt": False,
        "slug": slugify(name, entry["assessmentCode"]),
        "assessmentCode": entry["assessmentCode"],
        "sgcCode": entry["sgcCode"],
        "name": name,
        "tier": tier_label,
        "fiscalYear": int(year),
        "currency": "CAD",
        "source": {
            **SOURCE,
            "url": SOURCE["urlPattern"].format(year=year),
            "localZip": f"source-pdfs/fir/{zip_name}",
            "localZipSha256": zip_hash,
            "archiveMember": f"fir_data_{year}.csv",
        },
        "totals": {
            "grandTotalCad": grand,
            "grandTotalSlc": lines[GRAND_LINE]["slc"],
            "populationFir": population,
            "perCapitaCad": per_capita,
            "sharesReported": shares_reported,
        },
        "functions": functions,
        "other": {
            "code": OTHER_GROUP,
            "label": "Other",
            "amountCad": other_total,
            "publishedRollupLine": None,
            "components": [
                {
                    "code": item["code"],
                    "slc": item["slc"],
                    "label": item["label"],
                    "amountCad": item["amountCad"],
                }
                for item in other_components
            ],
            "note": (
                "Schedule 40 publishes no rollup row for this group, so the "
                "figure is the sum of its own component lines. It may be "
                "negative where the filing records recoveries or adjustments."
            ),
        },
        "identities": {
            "componentsSumToGroupTotals": True,
            "functionsPlusOtherEqualGrandTotal": True,
            "toleranceCad": IDENTITY_TOLERANCE_CAD,
            "assertedAtBuildTime": True,
        },
        "gates": {
            "hasGrandTotal": True,
            "hasPopulation": population is not None and population > 0,
            "passed": True,
        },
        "comparability": build_comparability(population, tier_label, year),
        "disclaimer": (
            "This is a machine-built FIR baseline receipt. It is not a property-"
            "tax bill, not a by-law citation, and not a finding. Amounts are the "
            "municipality's own filed actuals for a past fiscal year. For "
            "by-law-grade receipts see the gold packs."
        ),
    }
    if built_at is not None:
        receipt["builtAt"] = built_at
    return receipt, None


def render_json(payload: dict) -> str:
    """Single serializer for both write and --check.

    Reimplementing this in the check path is how a builder starts reporting
    "fresh" against bytes it would not actually produce.
    """

    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_json(payload), encoding="utf-8", newline="\n")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build FIR functional receipts (deterministic, zero AI)"
    )
    parser.add_argument("--year", default="2023")
    parser.add_argument(
        "--codes",
        default="",
        help="Comma-separated ASSESSMENT_CODE list. Default: every filer.",
    )
    parser.add_argument("--built-at", dest="built_at")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Verify checked-in receipts match a fresh build; write nothing.",
    )
    args = parser.parse_args()

    year = args.year
    codes = {c.strip() for c in args.codes.split(",") if c.strip()} or None
    try:
        built_at = resolve_built_at(args.built_at)
    except (ReceiptBuildError, ValueError) as exc:
        parser.error(str(exc))
        return 2

    zip_path = FIR_DIR / f"fir_data_{year}.zip"
    if not zip_path.exists():
        print(f"MISSING: {zip_path}", file=sys.stderr)
        print(SOURCE["urlPattern"].format(year=year), file=sys.stderr)
        return 1

    zip_hash = sha256_file(zip_path)
    collected = extract(zip_path, year, codes)
    if not collected:
        print("No matching municipalities found.", file=sys.stderr)
        return 1

    out_dir = OUT_ROOT / year
    receipts: list[dict] = []
    skipped: list[dict] = []
    drift: list[str] = []

    for code in sorted(collected):
        receipt, reason = build_receipt(
            year, collected[code], zip_hash, zip_path.name, built_at
        )
        if receipt is None:
            skipped.append({"assessmentCode": code, "reason": reason})
            continue
        receipts.append(receipt)

    index = {
        "schemaVersion": "fir-functional-receipt-index-0.1.0",
        "grade": "FIR",
        "isReceipt": False,
        "jurisdiction": "CA-ON",
        "fiscalYear": int(year),
        "sourceZip": zip_path.name,
        "sourceZipSha256": zip_hash,
        "method": "schedule-40-functional-breakdown",
        "aiTokensUsed": 0,
        "crossMunicipalityComparable": False,
        "declaredPopulationFloor": COMPARABILITY_POPULATION_FLOOR,
        "municipalityCount": len(receipts),
        "skipped": skipped,
        "municipalities": [
            {
                "assessmentCode": item["assessmentCode"],
                "slug": item["slug"],
                "name": item["name"],
                "tier": item["tier"],
                "grandTotalCad": item["totals"]["grandTotalCad"],
                "populationFir": item["totals"]["populationFir"],
                "belowPopulationFloor": item["comparability"]["belowPopulationFloor"],
                "functionCount": len(item["functions"]),
                "path": f"fir/{year}/{item['assessmentCode']}.json",
            }
            for item in receipts
        ],
    }
    if built_at is not None:
        index["builtAt"] = built_at

    if args.check:
        for item in receipts:
            path = out_dir / f"{item['assessmentCode']}.json"
            if not path.exists() or path.read_text(encoding="utf-8") != render_json(item):
                drift.append(str(path.relative_to(ROOT)))
        index_path = out_dir / "index.json"
        if not index_path.exists() or index_path.read_text(encoding="utf-8") != render_json(index):
            drift.append(str(index_path.relative_to(ROOT)))
        # A stale receipt for a municipality the build no longer emits is drift
        # too, and comparing only what we just built would never notice it.
        emitted = {f"{item['assessmentCode']}.json" for item in receipts} | {"index.json"}
        if out_dir.exists():
            for stale in sorted(out_dir.glob("*.json")):
                if stale.name not in emitted:
                    drift.append(str(stale.relative_to(ROOT)))
        if drift:
            print(f"FIR functional receipts drifted: {len(drift)} file(s)", file=sys.stderr)
            for path in drift[:10]:
                print(f"  {path}", file=sys.stderr)
            return 1
        print(
            f"FIR functional receipts are fresh: {len(receipts)} municipalities, "
            f"{len(skipped)} skipped, AI tokens 0"
        )
        return 0

    for item in receipts:
        write_json(out_dir / f"{item['assessmentCode']}.json", item)
    write_json(out_dir / "index.json", index)

    total_lines = sum(
        len(item["functions"]) + sum(len(f["components"]) for f in item["functions"])
        for item in receipts
    )
    print(f"=== FIR functional receipts, fiscal {year} ===")
    print(f"1. Official input: {zip_path.name}  sha256={zip_hash[:12]}...")
    print(f"2. Municipalities receipted: {len(receipts)}")
    print(f"3. Skipped (fail closed): {len(skipped)}")
    for item in skipped[:5]:
        print(f"     {item['assessmentCode']}: {item['reason']}")
    print(f"4. Functional lines written: {total_lines:,}")
    print(f"5. Output: {out_dir.relative_to(ROOT)}/")
    print("6. Identities asserted per municipality; no AI was called. Tokens: 0.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
