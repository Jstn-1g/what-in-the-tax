"""Parse RT Residential City / Region / Education rates from a page-marked extract.

Deterministic — no LLM. Accepts either decimal rates (0.00411164) or
percent-style rates (0.437426%) as municipalities publish both.
"""

from __future__ import annotations

import re
from pathlib import Path

PAGE_MARKER = re.compile(r"=====\s*PAGE\s+(\d+)\s*=====")

# Row with class token + four rate columns (city, region, education, total).
# Handles "RT", "R T", "RTEP", "Residential" lead-ins.
ROW_RE = re.compile(
    r"(?P<label>(?:Residential|R\s*T|RT|RTEP)[^\n]{0,80}?)"
    r"(?P<city>\d+\.\d+)\s*%?\s+"
    r"(?P<region>\d+\.\d+)\s*%?\s+"
    r"(?P<edu>\d+\.\d+)\s*%?\s+"
    r"(?P<total>\d+\.\d+)\s*%?",
    re.IGNORECASE,
)


def split_pages(text: str) -> dict[int, str]:
    pages: dict[int, str] = {}
    parts = PAGE_MARKER.split(text)
    for i in range(1, len(parts) - 1, 2):
        pages[int(parts[i])] = parts[i + 1]
    return pages


def _to_decimal(raw: str, *, as_percent_hint: bool) -> float:
    val = float(raw)
    # Percent form used by Waterloo HTML (0.437426%) vs decimal (0.00437426).
    if as_percent_hint or (0.05 < val < 50):
        return round(val / 100.0, 8)
    return val


def parse_rt_rates_from_text(
    text: str,
    *,
    page: int | None = None,
    prefer_percent: bool | None = None,
) -> dict:
    """
    Return {city, region, education, total, page, excerpt, label}.

    If prefer_percent is None, auto-detect from magnitude of matched numbers.
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
            hint = prefer_percent
            if hint is None:
                hint = any(float(x) > 0.05 for x in raws)
            city = _to_decimal(raws[0], as_percent_hint=bool(hint))
            region = _to_decimal(raws[1], as_percent_hint=bool(hint))
            edu = _to_decimal(raws[2], as_percent_hint=bool(hint))
            total = _to_decimal(raws[3], as_percent_hint=bool(hint))
            if abs((city + region + edu) - total) > 1e-6:
                continue
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
    prefer_percent: bool | None = None,
) -> dict:
    if not extract_path.exists():
        raise SystemExit(f"RT rate parse: missing extract {extract_path}")
    return parse_rt_rates_from_text(
        extract_path.read_text(encoding="utf-8"),
        page=page,
        prefer_percent=prefer_percent,
    )
