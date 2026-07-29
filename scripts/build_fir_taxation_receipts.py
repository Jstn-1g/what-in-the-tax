#!/usr/bin/env python3
"""Build FIR taxation receipts from Schedule 26A - deterministic, zero AI.

Where build_fir_functional_receipts.py answers "what did the municipality spend
it on", this answers "who levied it". Schedule 26A publishes, per property
class, the assessment and the split of the tax between the lower/single tier,
the upper tier and education - which is the shape of a property-tax receipt for
every taxing municipality in Ontario.

Same contract as the Schedule 40 builder: the locked archive member goes in,
`--check` proves the committed artifacts reproduce byte for byte, and a
municipality whose filing cannot be trusted is refused by name rather than
dropped silently.

Two identities are checked, and they are not equally strong.

  The weak one. Lower/single tier + upper tier + education equals total taxes,
  per class. The FIR form almost certainly computes the total as the sum of its
  parts, which makes this close to an accounting tautology. It is enforced
  anyway - a filing whose printed parts disagree with its printed total is not
  publishable - but passing it proves only internal consistency.

  The strong one, and the reason this builder has a publication gate at all.
  Ontario sets one residential education rate province-wide. So education
  divided by residential CVA must land on that constant for every municipality,
  and it is a number the municipality does not control. This tests each filing
  against something outside itself, and it is wired here as a hard gate: a
  municipality that misses it is refused and named.

On today's data that gate refuses nobody, which is the point. It costs nothing
now and catches the year a filing goes wrong.
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
LOCK_DIR = ROOT / "sources" / "locks" / "ca-on"
OUT_ROOT = ROOT / "web" / "public" / "fir-taxation"

# Schedule 26A, column block 01 - taxable property. Block C02 is payments in
# lieu, which is a different population of properties and is deliberately out of
# scope here rather than folded into a taxpayer-facing total.
LINE_RE = re.compile(r"^slc\.26A\.L(\d{4})\.C01\.(\d{2})$")

# The taxable property classes, in the order the schedule prints them. Declared
# rather than discovered: a class appearing upstream that is not in this list is
# reported, not silently absorbed into a total.
CLASS_LINES: dict[str, str] = {
    "0010": "Residential",
    "0050": "Multi-residential",
    "0110": "Farmland",
    "0140": "Managed forests",
    "0210": "Commercial",
    "0310": "Parking lot",
    "0320": "Office building",
    "0340": "Shopping centre",
    "0510": "Industrial",
    "0610": "Large industrial",
    "0705": "Landfill",
    "0710": "Pipelines",
}
RESIDENTIAL_LINE = "0010"

# The measures this receipt reads. A suffix is not interchangeable with its
# neighbour: .04 is the municipality's own levy and .05 is its region's, and
# .02 is assessment weighted and discounted while .16 is plain CVA. They
# coincide for residential, whose weight is 1.0, and diverge everywhere else.
COL_ASSESSMENT_WEIGHTED = "02"
COL_TOTAL_TAXES = "03"
COL_MUNICIPAL_LOWER_SINGLE = "04"
COL_MUNICIPAL_UPPER = "05"
COL_EDUCATION = "06"
COL_ASSESSMENT_CVA = "16"
WANTED_COLUMNS = frozenset(
    {
        COL_ASSESSMENT_WEIGHTED,
        COL_TOTAL_TAXES,
        COL_MUNICIPAL_LOWER_SINGLE,
        COL_MUNICIPAL_UPPER,
        COL_EDUCATION,
        COL_ASSESSMENT_CVA,
    }
)

# Ontario's province-wide residential education rate. Printed in Waterloo's own
# rate table in corpus/waterloo-on/build-inputs.yaml, and reproduced by every
# taxing municipality in the three locked years.
EDUCATION_RATE_EXPECTED = 0.00153

# 0.005 percentage points. A declared judgement, not a discovered one: measured
# across 2023, 2024 and 2025 every taxing municipality lands inside it, and the
# worst filing anywhere in three years is 0.1494% - 2.4% off the constant, on
# one municipality in one year. Tight enough to catch a filing that used the
# wrong rate, loose enough not to refuse anyone for rounding.
EDUCATION_RATE_TOLERANCE = 0.00005

# Cent-level tolerance. FIR amounts are whole dollars, so anything above this is
# a real disagreement rather than floating-point noise.
IDENTITY_TOLERANCE_CAD = 0.51

SOURCE = {
    "id": "mmah-fir",
    "title": "Ontario MMAH Financial Information Return (Multi-Year Report data)",
    "urlPattern": "https://efis.fma.csc.gov.on.ca/fir/MultiYearReport/fir_data_{year}.zip",
    "schedule": "Schedule 26A - Taxation and Payments-in-Lieu Summary",
    "measure": "Taxable property, column block 01",
    "note": (
        "Taxes levied for the stated fiscal year as filed by the municipality. "
        "Not a current tax by-law, an individual tax bill, or an audit."
    ),
}

DISCLAIMER = (
    "Levies as filed by the municipality for this fiscal year. Shares describe "
    "how the total was split between the taxing bodies, not what any individual "
    "property owner paid."
)


class ReceiptBuildError(RuntimeError):
    """Raised when the build cannot proceed safely."""


def load_source_lock(year: str) -> dict:
    """The reviewed release record for a fiscal year."""
    path = LOCK_DIR / f"on-fir-{year}.lock.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ReceiptBuildError(f"cannot read reviewed lock {path}: {exc}") from exc


def sha256_archive_member(path: Path, member: str) -> str:
    """Digest the data inside the archive, not the archive.

    Ontario re-zips the same CSV from time to time: the container digest changes
    while every byte a receipt is built from stays identical. Pinning the
    container made those benign re-compressions look like data changes, so
    provenance here is anchored to the payload, exactly as
    acquire_official_sources.py and the Schedule 40 builder already decide.
    """
    digest = hashlib.sha256()
    try:
        with zipfile.ZipFile(path) as archive, archive.open(member) as raw:
            for chunk in iter(lambda: raw.read(1 << 20), b""):
                digest.update(chunk)
    except (OSError, KeyError, zipfile.BadZipFile) as exc:
        raise ReceiptBuildError(f"cannot read {member} from {path}: {exc}") from exc
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
    """Stream the FIR CSV once, keeping only the Schedule 26A rows needed."""

    member = f"fir_data_{year}.csv"
    collected: dict[str, dict] = {}
    with zipfile.ZipFile(zip_path) as archive:
        if member not in archive.namelist():
            raise ReceiptBuildError(f"{zip_path.name} does not contain {member}")
        with archive.open(member) as raw:
            # The payload is valid UTF-8; errors='replace' is a guard, not a
            # decoding strategy, and it has nothing to replace today.
            stream = io.TextIOWrapper(raw, encoding="utf-8", errors="replace", newline="")
            for row in csv.DictReader(stream):
                code = (row.get("ASSESSMENT_CODE") or "").strip()
                if not code or (codes is not None and code not in codes):
                    continue

                entry = collected.setdefault(
                    code,
                    {
                        "assessmentCode": code,
                        "classes": {},
                        "name": None,
                        "tier": "",
                        "sgcCode": "",
                    },
                )
                entry["name"] = (row.get("MUNICIPALITY_DESC") or "").strip() or entry["name"]
                entry["tier"] = (row.get("TIER_CODE") or "").strip() or entry["tier"]
                entry["sgcCode"] = (row.get("SGC_CODE") or "").strip() or entry["sgcCode"]

                matched = LINE_RE.match((row.get("SLC") or "").strip())
                if not matched:
                    continue
                line, column = matched.group(1), matched.group(2)
                if line not in CLASS_LINES or column not in WANTED_COLUMNS:
                    continue

                amount_raw = (row.get("AMOUNT") or "").strip()
                if amount_raw == "":
                    continue
                try:
                    amount = float(amount_raw)
                except ValueError:
                    continue
                entry["classes"].setdefault(line, {})[column] = amount
    return collected


def _share(part: float, whole: float) -> float | None:
    if whole <= 0:
        return None
    return round(part / whole, 6)


def build_receipt(
    year: str,
    entry: dict,
    zip_hash: str,
    member_hash: str,
    zip_name: str,
    built_at: str | None,
) -> tuple[dict | None, str | None]:
    """Return (receipt, skip_reason). Exactly one is non-None."""

    classes = entry["classes"]
    tier = entry["tier"]

    residential = classes.get(RESIDENTIAL_LINE, {})
    cva = residential.get(COL_ASSESSMENT_CVA)
    education = residential.get(COL_EDUCATION)

    # An upper tier does not levy on CVA directly. Its money is apportioned
    # through its member municipalities and already appears inside each member's
    # receipt, so it has assessment on this schedule and no education line. That
    # is a fact about Ontario's tier structure, not a hole in the filing, and it
    # must not be reported as one.
    if tier == "UT":
        return None, (
            "upper-tier municipality: it does not levy on assessment directly, "
            "and its share is already inside each member municipality's receipt"
        )

    if cva is None or cva <= 0:
        return None, "no residential taxable assessment (CVA) on Schedule 26A"
    if education is None:
        return None, "no residential education levy on Schedule 26A"

    # The publication gate. Education divided by CVA is set by the province, so
    # a filing that misses it disagrees with something its author does not
    # control - which is the only check here that is not self-referential.
    education_rate = education / cva
    if abs(education_rate - EDUCATION_RATE_EXPECTED) > EDUCATION_RATE_TOLERANCE:
        return None, (
            f"residential education rate is {education_rate * 100:.4f}%, outside "
            f"{EDUCATION_RATE_TOLERANCE * 100:.4f}pp of Ontario's province-wide "
            f"{EDUCATION_RATE_EXPECTED * 100:.4f}%"
        )

    emitted: list[dict] = []
    for line in CLASS_LINES:
        values = classes.get(line)
        if not values:
            continue
        total = values.get(COL_TOTAL_TAXES)
        if total is None:
            continue
        lower_single = values.get(COL_MUNICIPAL_LOWER_SINGLE, 0.0)
        upper = values.get(COL_MUNICIPAL_UPPER, 0.0)
        edu = values.get(COL_EDUCATION, 0.0)

        # Fail hard on integrity: printed parts that disagree with a printed
        # total mean the filing cannot be published, not that it needs a note.
        parts = lower_single + upper + edu
        if abs(parts - total) > IDENTITY_TOLERANCE_CAD:
            return None, (
                f"class L{line} ({CLASS_LINES[line]}) parts sum to {parts:,.2f} "
                f"but the filing reports {total:,.2f}"
            )

        emitted.append(
            {
                "code": line,
                "label": CLASS_LINES[line],
                "taxableAssessmentCvaCad": values.get(COL_ASSESSMENT_CVA),
                "taxableAssessmentWeightedDiscountedCad": values.get(
                    COL_ASSESSMENT_WEIGHTED
                ),
                "totalTaxesCad": total,
                "municipalLowerOrSingleTierCad": lower_single,
                "municipalUpperTierCad": upper,
                "educationCad": edu,
            }
        )

    if not emitted:
        return None, "no taxable property class rows on Schedule 26A"

    res = next(item for item in emitted if item["code"] == RESIDENTIAL_LINE)
    res_total = res["totalTaxesCad"]

    receipt = {
        "schemaVersion": "fir-taxation-receipt-0.1.0",
        "grade": "FIR",
        # These are filings, not tax bills. The web loader refuses any FIR
        # artifact that claims otherwise.
        "isReceipt": False,
        "jurisdiction": "CA-ON",
        "assessmentCode": entry["assessmentCode"],
        "slug": slugify(entry["name"] or "", entry["assessmentCode"]),
        "name": entry["name"],
        "tier": tier,
        "sgcCode": entry["sgcCode"],
        "fiscalYear": int(year),
        "source": {
            **SOURCE,
            "url": SOURCE["urlPattern"].format(year=year),
            "archive": zip_name,
            "archiveSha256": zip_hash,
            "archiveMemberSha256": member_hash,
        },
        "residential": {
            "taxableAssessmentCvaCad": cva,
            "totalTaxesCad": res_total,
            "municipalLowerOrSingleTierCad": res["municipalLowerOrSingleTierCad"],
            "municipalUpperTierCad": res["municipalUpperTierCad"],
            "educationCad": res["educationCad"],
            "shares": {
                "municipalLowerOrSingleTier": _share(
                    res["municipalLowerOrSingleTierCad"], res_total
                ),
                "municipalUpperTier": _share(res["municipalUpperTierCad"], res_total),
                "education": _share(res["educationCad"], res_total),
            },
            "educationRate": round(education_rate, 8),
        },
        "classes": emitted,
        "checks": {
            "partsSumToTotalPerClass": True,
            "educationRateWithinProvincialConstant": True,
            "provincialEducationRate": EDUCATION_RATE_EXPECTED,
            "educationRateToleranceAbsolute": EDUCATION_RATE_TOLERANCE,
            "identityToleranceCad": IDENTITY_TOLERANCE_CAD,
        },
        "crossMunicipalityComparable": False,
        "disclaimer": DISCLAIMER,
        "aiTokensUsed": 0,
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
        description="Build FIR taxation receipts from Schedule 26A (deterministic, zero AI)"
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

    # Verify the payload against the reviewed lock before building anything, so
    # a swapped archive fails here rather than quietly producing 400 wrong
    # receipts. The container digest is deliberately not compared.
    lock = load_source_lock(year)
    member_name = lock.get("archiveMember") or f"fir_data_{year}.csv"
    member_hash = sha256_archive_member(zip_path, member_name)
    locked_member = lock.get("archiveMemberSha256")
    if not isinstance(locked_member, str):
        print(
            f"MISSING: on-fir-{year} lock does not pin archiveMemberSha256",
            file=sys.stderr,
        )
        return 1
    if member_hash != locked_member:
        print(
            f"MISMATCH: {member_name} is {member_hash}, "
            f"reviewed lock pins {locked_member}",
            file=sys.stderr,
        )
        return 1
    zip_hash = lock["sha256"]

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
            year, collected[code], zip_hash, member_hash, zip_path.name, built_at
        )
        if receipt is None:
            skipped.append({"assessmentCode": code, "reason": reason})
            continue
        receipts.append(receipt)

    index = {
        "schemaVersion": "fir-taxation-receipt-index-0.1.0",
        "grade": "FIR",
        "isReceipt": False,
        "jurisdiction": "CA-ON",
        "fiscalYear": int(year),
        "sourceZip": zip_path.name,
        "sourceZipSha256": zip_hash,
        "sourceArchiveMemberSha256": member_hash,
        "method": "schedule-26A-taxation-summary",
        "aiTokensUsed": 0,
        "crossMunicipalityComparable": False,
        "provincialEducationRate": EDUCATION_RATE_EXPECTED,
        "educationRateToleranceAbsolute": EDUCATION_RATE_TOLERANCE,
        "municipalityCount": len(receipts),
        "skipped": skipped,
        "municipalities": [
            {
                "assessmentCode": item["assessmentCode"],
                "slug": item["slug"],
                "name": item["name"],
                "tier": item["tier"],
                "residentialTotalTaxesCad": item["residential"]["totalTaxesCad"],
                "residentialCvaCad": item["residential"]["taxableAssessmentCvaCad"],
                "educationRate": item["residential"]["educationRate"],
                "classCount": len(item["classes"]),
                "path": f"fir-taxation/{year}/{item['assessmentCode']}.json",
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
            print(f"FIR taxation receipts drifted: {len(drift)} file(s)", file=sys.stderr)
            for path in drift[:10]:
                print(f"  {path}", file=sys.stderr)
            return 1
        print(
            f"FIR taxation receipts are fresh: {len(receipts)} municipalities, "
            f"{len(skipped)} skipped, AI tokens 0"
        )
        return 0

    for item in receipts:
        write_json(out_dir / f"{item['assessmentCode']}.json", item)
    write_json(out_dir / "index.json", index)

    refusals = [item for item in skipped if "upper-tier municipality" not in item["reason"]]
    print(f"=== FIR taxation receipts, fiscal {year} ===")
    print(f"1. Official input: {zip_path.name}  payload sha256={member_hash[:12]}...")
    print(f"2. Municipalities receipted: {len(receipts)}")
    print(f"3. Upper tiers, correctly not receipted: {len(skipped) - len(refusals)}")
    print(f"4. Refused (fail closed): {len(refusals)}")
    for item in refusals[:10]:
        print(f"     {item['assessmentCode']}: {item['reason']}")
    print(f"5. Output: {out_dir.relative_to(ROOT)}/")
    print("6. Identities asserted per municipality; no AI was called. Tokens: 0.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
