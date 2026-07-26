"""Parse residential tax rates from a page-marked extract.

Deterministic — no LLM. Source rates must have an explicit unit: a printed
suffix (for example ``%``), ``rate_unit``, or the legacy ``prefer_percent``
configuration. Magnitude-based unit guessing is intentionally forbidden.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from pathlib import Path

PAGE_MARKER = re.compile(r"=====\s*PAGE\s+(\d+)\s*=====")

NUMBER = r"\d+(?:[.,]\d+)?"
UNIT_SUFFIX = r"(?:%|percent|per\s+cent|mills?)"

# Row with class token + four rate columns (city, region, education, total).
# Handles "RT", "R T", "RTEP", "Residential" lead-ins.
ROW_RE = re.compile(
    r"(?P<label>(?:Residential|R\s*T|RT|RTEP)[^\n]{0,80}?)"
    rf"(?P<city>{NUMBER})\s*(?P<city_suffix>{UNIT_SUFFIX})?\s+"
    rf"(?P<region>{NUMBER})\s*(?P<region_suffix>{UNIT_SUFFIX})?\s+"
    rf"(?P<edu>{NUMBER})\s*(?P<edu_suffix>{UNIT_SUFFIX})?\s+"
    rf"(?P<total>{NUMBER})\s*(?P<total_suffix>{UNIT_SUFFIX})?",
    re.IGNORECASE,
)

RATE_UNIT_FACTORS = {
    "decimal": Decimal("1"),
    "percent": Decimal("0.01"),
    "mill": Decimal("0.001"),
}
RATE_UNIT_ALIASES = {
    "decimal": "decimal",
    "rate": "decimal",
    "percent": "percent",
    "percentage": "percent",
    "%": "percent",
    "mill": "mill",
    "mills": "mill",
    "per-thousand": "mill",
    "per_1000": "mill",
}
RATE_SUM_TOLERANCE = Decimal("0.0000000001")


def split_pages(text: str) -> dict[int, str]:
    pages: dict[int, str] = {}
    parts = PAGE_MARKER.split(text)
    for i in range(1, len(parts) - 1, 2):
        pages[int(parts[i])] = parts[i + 1]
    return pages


def normalize_rate_unit(unit: str) -> str:
    """Return a canonical rate unit or fail closed for an unknown unit."""

    key = str(unit).strip().lower().replace(" ", "-")
    try:
        return RATE_UNIT_ALIASES[key]
    except KeyError as exc:
        allowed = ", ".join(RATE_UNIT_FACTORS)
        raise SystemExit(
            f"RT rate parse: unsupported rate unit {unit!r}; expected {allowed}"
        ) from exc


def rate_to_decimal(raw: str | int | Decimal, *, unit: str) -> Decimal:
    """Convert an explicitly-unitized source rate to a canonical decimal rate."""

    canonical_unit = normalize_rate_unit(unit)
    normalized = str(raw).strip()
    if "," in normalized and "." not in normalized:
        normalized = normalized.replace(",", ".")
    try:
        value = Decimal(normalized)
    except InvalidOperation as exc:
        raise SystemExit(f"RT rate parse: invalid rate value {raw!r}") from exc
    if not value.is_finite() or value < 0:
        raise SystemExit(f"RT rate parse: rate must be a finite non-negative value: {raw!r}")
    return value * RATE_UNIT_FACTORS[canonical_unit]


def _suffix_unit(suffix: str | None) -> str | None:
    if not suffix:
        return None
    normalized = re.sub(r"\s+", " ", suffix.strip().lower())
    if normalized in {"%", "percent", "per cent"}:
        return "percent"
    if normalized in {"mill", "mills"}:
        return "mill"
    raise SystemExit(f"RT rate parse: unsupported printed rate suffix {suffix!r}")


def _resolve_rate_unit(
    match: re.Match[str],
    *,
    rate_unit: str | None,
    prefer_percent: bool | None,
) -> tuple[str, str]:
    configured = normalize_rate_unit(rate_unit) if rate_unit is not None else None
    legacy = (
        ("percent" if prefer_percent else "decimal")
        if prefer_percent is not None
        else None
    )
    if configured is not None and legacy is not None and configured != legacy:
        raise SystemExit(
            "RT rate parse: rate_unit conflicts with legacy prefer_percent declaration"
        )

    suffixes = [
        _suffix_unit(match.group(f"{field}_suffix"))
        for field in ("city", "region", "edu", "total")
    ]
    printed = [unit for unit in suffixes if unit is not None]
    if printed and len(printed) != len(suffixes):
        raise SystemExit(
            "RT rate parse: mixed marked and unmarked values; declare one unit for the row"
        )
    if len(set(printed)) > 1:
        raise SystemExit("RT rate parse: mixed rate units in residential row")
    printed_unit = printed[0] if printed else None

    declared = configured or legacy
    if declared is not None and printed_unit is not None and declared != printed_unit:
        raise SystemExit(
            f"RT rate parse: configured {declared} unit conflicts with printed "
            f"{printed_unit} suffix"
        )
    resolved = printed_unit or declared
    if resolved is None:
        raise SystemExit(
            "RT rate parse: ambiguous unmarked rates; set rate_unit to "
            "'decimal', 'percent', or 'mill'"
        )

    declarations: list[str] = []
    if printed_unit is not None:
        declarations.append("printed_suffix")
    if configured is not None:
        declarations.append("config.rateUnit")
    elif legacy is not None:
        declarations.append("legacy.preferPercent")
    return resolved, "+".join(declarations)


def parse_rt_rates_from_text(
    text: str,
    *,
    page: int | None = None,
    rate_unit: str | None = None,
    prefer_percent: bool | None = None,
) -> dict:
    """
    Return canonical Decimal rates plus source-unit metadata.

    ``prefer_percent`` remains as an explicit legacy declaration. It is never
    used as a magnitude hint.
    """
    bodies: list[tuple[int | None, str]]
    if page is not None:
        pages = split_pages(text)
        if page not in pages:
            raise SystemExit(f"RT rate parse: page {page} missing from extract")
        bodies = [(page, pages[page])]
    else:
        pages = split_pages(text)
        if pages:
            bodies = list(pages.items())
        else:
            bodies = [(None, text)]

    candidates: list[dict] = []
    for pnum, body in bodies:
        for m in ROW_RE.finditer(body):
            label = re.sub(r"\s+", " ", m.group("label")).strip()
            # Skip farm / managed forest style rows that share the regex loosely.
            low = label.lower()
            if "farm" in low and "residential" not in low:
                continue
            if "forest" in low:
                continue
            raws = [m.group("city"), m.group("region"), m.group("edu"), m.group("total")]
            resolved_unit, declaration = _resolve_rate_unit(
                m,
                rate_unit=rate_unit,
                prefer_percent=prefer_percent,
            )
            city = rate_to_decimal(raws[0], unit=resolved_unit)
            region = rate_to_decimal(raws[1], unit=resolved_unit)
            edu = rate_to_decimal(raws[2], unit=resolved_unit)
            total = rate_to_decimal(raws[3], unit=resolved_unit)
            rate_sum = city + region + edu
            if abs(rate_sum - total) > RATE_SUM_TOLERANCE:
                raise SystemExit(
                    f"RT rate parse: component sum {rate_sum} does not match total {total}"
                )
            # Prefer true residential / RT / RTEP
            score = 0
            if re.search(r"\bRT\b|RTEP|Residential", label, re.I):
                score += 2
            if "new multi" in low:
                score -= 1
            excerpt = re.sub(r"\s+", " ", m.group(0)).strip()
            candidates.append(
                {
                    "city": city,
                    "region": region,
                    "education": edu,
                    "total": total,
                    "page": pnum or 1,
                    "excerpt": excerpt[:240],
                    "label": label,
                    "sourceUnit": resolved_unit,
                    "unitDeclaration": declaration,
                    "score": score,
                }
            )

    if not candidates:
        raise SystemExit("RT rate parse: no residential row found")
    candidates.sort(key=lambda c: c["score"], reverse=True)
    best = candidates[0]
    best.pop("score", None)
    return best


def parse_rt_rates_from_extract(
    extract_path: Path,
    *,
    page: int | None = None,
    rate_unit: str | None = None,
    prefer_percent: bool | None = None,
) -> dict:
    if not extract_path.exists():
        raise SystemExit(f"RT rate parse: missing extract {extract_path}")
    return parse_rt_rates_from_text(
        extract_path.read_text(encoding="utf-8"),
        page=page,
        rate_unit=rate_unit,
        prefer_percent=prefer_percent,
    )
