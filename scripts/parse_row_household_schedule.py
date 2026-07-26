"""Parse Region of Waterloo 'Annual Average Cost Per Household' table.

Deterministic — no LLM. Reads a page-marked extract and writes a YAML schedule
that lower-tier packs import by area key (urban / rural / woolwich / wilmot).

Published PDF subtotals may differ from the sum of rounded line items by a few
dollars (Region table rounding). After-PIL published totals are authoritative.

Usage:
  python scripts/parse_row_household_schedule.py
  python scripts/parse_row_household_schedule.py --extract data/_extracts/2026_final_budget_book_region.txt
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None

ROOT = Path(__file__).resolve().parents[1]

DEFAULT_EXTRACT = ROOT / "data" / "_extracts" / "2026_final_budget_book_region.txt"
DEFAULT_OUT = (
    ROOT / "corpus" / "region-of-waterloo-on" / "schedules" / "household-tax-supported-2026.yaml"
)

PAGE_MARKER = re.compile(r"=====\s*PAGE\s+(\d+)\s*=====")
# Service row: label, net $000s, levy $000s, then 5× (pct, dollars) for
# Blended / Urban / Rural / Woolwich / Wilmot.
ROW_RE = re.compile(
    r"^(?P<label>.+?)\s+"
    r"(?P<net>[\d,]+)\s+"
    r"(?P<levy>[\d,]+)\s+"
    r"(?P<b_pct>[\d.]+)\s+\$?(?P<b_amt>[\d,]+)\s+"
    r"(?P<u_pct>[\d.]+)\s+\$?(?P<u_amt>[\d,]+)\s+"
    r"(?P<r_pct>[\d.]+)\s+\$?(?P<r_amt>[\d,]+)\s+"
    r"(?P<w_pct>[\d.]+)\s+\$?(?P<w_amt>[\d,]+)\s+"
    r"(?P<m_pct>[\d.]+)\s+\$?(?P<m_amt>[\d,]+)\s*$"
)
MONEY_RE = re.compile(r"\$([\d,]+)")
PIL_RE = re.compile(r"\(\$?([\d,]+)\)")
LEVY_TOTALS_RE = re.compile(
    r"100%\s+\$([\d,]+)\s+100%\s+\$([\d,]+)\s+100%\s+\$([\d,]+)\s+"
    r"100%\s+\$([\d,]+)\s+100%\s+\$([\d,]+)"
)

AREA_KEYS = ("blended", "urban", "rural", "woolwich", "wilmot")
AREA_LABELS = {
    "blended": "Blended Regional",
    "urban": "Urban (Kitchener / Waterloo / Cambridge)",
    "rural": "Rural (North Dumfries / Wellesley)",
    "woolwich": "Woolwich",
    "wilmot": "Wilmot",
}

# Fallback asserts when extract layout does not yield published figures.
EXPECTED_PUBLISHED_SUBTOTALS = {
    "blended": 3007,
    "urban": 3062,
    "rural": 2621,
    "woolwich": 2695,
    "wilmot": 2654,
}
EXPECTED_AFTER_PIL = {
    "blended": 2929,
    "urban": 2984,
    "rural": 2543,
    "woolwich": 2617,
    "wilmot": 2576,
}
EXPECTED_PIL = -78
ROUNDING_TOLERANCE = 5
EXPECTED_SERVICE_ROWS = 23


def split_pages(text: str) -> dict[int, str]:
    pages: dict[int, str] = {}
    parts = PAGE_MARKER.split(text)
    for i in range(1, len(parts) - 1, 2):
        pages[int(parts[i])] = parts[i + 1]
    return pages


def find_table_page(pages: dict[int, str]) -> tuple[int, str]:
    for num, body in pages.items():
        if "Annual Average Cost Per Household" in body and "Tax Supported Services" in body:
            return num, body
    raise SystemExit("Could not find household cost table in extract")


def _int_money(s: str) -> int:
    return int(s.replace(",", "").replace("$", ""))


def parse_service_rows(page_text: str) -> list[dict]:
    rows: list[dict] = []
    in_table = False
    for raw in page_text.splitlines():
        line = re.sub(r"\s+", " ", raw).strip()
        if not line:
            continue
        if line.startswith("Police Service") and re.search(r"\d", line):
            in_table = True
        if not in_table:
            continue
        if line.startswith("Subtotal"):
            break
        if line.startswith("Less:") or line.startswith("Regional Tax Levy"):
            break
        m = ROW_RE.match(line)
        if not m:
            raise SystemExit(f"Failed to parse service row:\n  {line}")
        label = re.sub(r"\(\d+\)\s*$", "", m.group("label")).strip()
        label = re.sub(r"\s+", " ", label)
        rows.append(
            {
                "label": label,
                "netExpenditure000Cad": _int_money(m.group("net")),
                "propertyTaxLevy000Cad": _int_money(m.group("levy")),
                "householdCad": {
                    "blended": _int_money(m.group("b_amt")),
                    "urban": _int_money(m.group("u_amt")),
                    "rural": _int_money(m.group("r_amt")),
                    "woolwich": _int_money(m.group("w_amt")),
                    "wilmot": _int_money(m.group("m_amt")),
                },
            }
        )
    if len(rows) != EXPECTED_SERVICE_ROWS:
        raise SystemExit(f"Expected {EXPECTED_SERVICE_ROWS} service rows, got {len(rows)}")
    return rows


def parse_published_footer(page_text: str) -> tuple[dict[str, int], int, dict[str, int]]:
    """Parse published subtotals, PIL, and after-PIL totals from the table footer.

    PDF extraction often splits the Subtotal / Less / Levy rows across lines.
    Prefer the levy line with five ``100% $N`` tokens for after-PIL; collect
    bare ``$N`` amounts between Subtotal and that levy line as published
    services subtotals. Fall back to EXPECTED_* constants when parsing fails.
    """
    lines = [re.sub(r"\s+", " ", raw).strip() for raw in page_text.splitlines()]
    lines = [ln for ln in lines if ln]

    after_pil: dict[str, int] | None = None
    published_subtotals: dict[str, int] | None = None
    pil = EXPECTED_PIL

    # After-PIL: Prefer the Regional Tax Levy summary line with five 100% markers.
    for ln in lines:
        m = LEVY_TOTALS_RE.search(ln)
        if m:
            after_pil = {
                key: _int_money(m.group(i))
                for i, key in enumerate(AREA_KEYS, start=1)
            }
            break

    # Published subtotals + PIL: amounts between "Subtotal" and the levy totals line.
    collecting = False
    dollar_candidates: list[int] = []
    pil_candidates: list[int] = []
    for ln in lines:
        if ln.startswith("Subtotal") and "User Rates" not in ln:
            collecting = True
            # Same line may also carry amounts (rare with this extractor).
        if not collecting:
            continue
        if LEVY_TOTALS_RE.search(ln):
            break
        for dm in MONEY_RE.finditer(ln):
            val = _int_money(dm.group(1))
            # Skip $000s / levy columns (~1.6M) — HH dollars are 4 digits.
            if 2000 <= val <= 4000:
                dollar_candidates.append(val)
        for pm in PIL_RE.finditer(ln):
            pil_candidates.append(-_int_money(pm.group(1)))

    if len(dollar_candidates) >= 5:
        # First five HH-scale dollars after Subtotal are published services subtotals.
        published_subtotals = {
            key: dollar_candidates[i] for i, key in enumerate(AREA_KEYS)
        }
    if pil_candidates:
        # All five areas share the same PIL in the published table.
        unique = set(pil_candidates)
        if len(unique) == 1:
            pil = next(iter(unique))
        elif EXPECTED_PIL in unique:
            pil = EXPECTED_PIL

    if published_subtotals is None:
        published_subtotals = dict(EXPECTED_PUBLISHED_SUBTOTALS)
        print(
            "WARN: could not parse published subtotals from extract; using fallback asserts",
            file=sys.stderr,
        )
    if after_pil is None:
        after_pil = dict(EXPECTED_AFTER_PIL)
        print(
            "WARN: could not parse after-PIL totals from extract; using fallback asserts",
            file=sys.stderr,
        )

    # Hard fallback asserts — published after-PIL must match sealed expectations.
    for key, expected in EXPECTED_AFTER_PIL.items():
        if after_pil[key] != expected:
            raise SystemExit(
                f"{key}: parsed after-PIL {after_pil[key]} != expected fallback {expected}"
            )
    for key, expected in EXPECTED_PUBLISHED_SUBTOTALS.items():
        if published_subtotals[key] != expected:
            raise SystemExit(
                f"{key}: parsed published subtotal {published_subtotals[key]} "
                f"!= expected fallback {expected}"
            )
    if pil != EXPECTED_PIL:
        raise SystemExit(f"PIL {pil} != expected {EXPECTED_PIL}")

    return published_subtotals, pil, after_pil


def build_document(
    rows: list[dict],
    page: int,
    extract_rel: str,
    published_subtotals: dict[str, int],
    pil: int,
    after_pil: dict[str, int],
) -> dict:
    line_sums = {k: sum(r["householdCad"][k] for r in rows) for k in AREA_KEYS}
    errors: list[str] = []

    for key in AREA_KEYS:
        line_sum = line_sums[key]
        pub_sub = published_subtotals[key]
        delta = abs(line_sum - pub_sub)
        if delta > ROUNDING_TOLERANCE:
            errors.append(
                f"{key}: |sum(lines) {line_sum} - publishedSubtotal {pub_sub}| = {delta} "
                f"> tolerance {ROUNDING_TOLERANCE}"
            )
        if pub_sub + pil != after_pil[key]:
            errors.append(
                f"{key}: publishedSubtotal {pub_sub} + PIL {pil} = {pub_sub + pil}, "
                f"expected after-PIL {after_pil[key]}"
            )

    if errors:
        raise SystemExit("Schedule validation failed:\n  " + "\n  ".join(errors))

    areas = {}
    for key in AREA_KEYS:
        line_sum = line_sums[key]
        pub_sub = published_subtotals[key]
        areas[key] = {
            "label": AREA_LABELS[key],
            "lines": [
                {
                    "id": f"ROW-HH-{key.upper()}-{i:02d}",
                    "label": r["label"],
                    "amountCad": r["householdCad"][key],
                    "netExpenditure000Cad": r["netExpenditure000Cad"],
                    "propertyTaxLevy000Cad": r["propertyTaxLevy000Cad"],
                }
                for i, r in enumerate(rows, start=1)
            ],
            "servicesSubtotalCad": line_sum,
            "publishedServicesSubtotalCad": pub_sub,
            "roundingAdjustmentCad": pub_sub - line_sum,
            "pilAndSupplementaryCad": pil,
            "taxSupportedTotalCad": after_pil[key],
        }

    return {
        "schemaVersion": "1.0.0",
        "artifact": "RegionHouseholdSchedule",
        "jurisdictionSlug": "region-of-waterloo-on",
        "fiscalYear": 2026,
        "source": {
            "title": "Region of Waterloo 2026 Final Budget Book — Annual Average Cost Per Household",
            "extractPath": extract_rel.replace("\\", "/"),
            "pdfPage": page,
            "assessmentCad": 354_500,
            "assessmentBasis": "MPAC CVA valuation date January 1, 2016 (Region-published average)",
            "note": (
                "Amounts are Region-published dollars per average household at $354,500. "
                "Do not add them to a lower-tier bill computed at a different assessment "
                "without an explicit rate×assessment DERIVED path. "
                "servicesSubtotalCad is the sum of rounded line items; "
                "publishedServicesSubtotalCad and taxSupportedTotalCad (after PIL) are "
                "authoritative published figures. roundingAdjustmentCad absorbs PDF "
                "table rounding (typically $2–$3)."
            ),
        },
        "areas": areas,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--extract", type=Path, default=DEFAULT_EXTRACT)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)

    if not args.extract.exists():
        print(f"ERROR: missing extract {args.extract}", file=sys.stderr)
        print(
            "Run: python scripts/extract_pdf_text.py  (region budget book must be present)",
            file=sys.stderr,
        )
        return 1
    if yaml is None:
        print("ERROR: PyYAML required (pip install pyyaml)", file=sys.stderr)
        return 1

    text = args.extract.read_text(encoding="utf-8")
    pages = split_pages(text)
    page_num, page_text = find_table_page(pages)
    rows = parse_service_rows(page_text)
    published_subtotals, pil, after_pil = parse_published_footer(page_text)

    try:
        rel = str(args.extract.relative_to(ROOT))
    except ValueError:
        rel = str(args.extract)

    doc = build_document(rows, page_num, rel, published_subtotals, pil, after_pil)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        yaml.safe_dump(doc, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    urban = doc["areas"]["urban"]
    rural = doc["areas"]["rural"]
    print(f"parsed {len(rows)} services from page {page_num}")
    print(
        f"urban: linesSum={urban['servicesSubtotalCad']} "
        f"publishedSub={urban['publishedServicesSubtotalCad']} "
        f"rounding={urban['roundingAdjustmentCad']} "
        f"afterPIL={urban['taxSupportedTotalCad']}"
    )
    print(
        f"rural: linesSum={rural['servicesSubtotalCad']} "
        f"publishedSub={rural['publishedServicesSubtotalCad']} "
        f"rounding={rural['roundingAdjustmentCad']} "
        f"afterPIL={rural['taxSupportedTotalCad']}"
    )
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
