"""
Deterministic citation audit — does the cited page actually say what the FACT claims?

Jurisdiction-agnostic: depends only on the evidence-ledger schema (sources[] with
extractedText, facts[] with sourceId/page/excerpt/amountCad), never on Ontario
specifics. This is the portable verification gate the receipt promise needs —
"every dollar traces to a page in a published document" is currently upheld by
careful human work; this makes it machine-checkable.

No model calls. No network. Pure text matching, so its verdicts are reproducible
by any third party holding the same extracts.

Match tiers, strongest first:
  verbatim         excerpt appears exactly on the cited page
  normalized       matches after whitespace/case collapse (PDF extraction noise)
  alnum            matches after stripping all non-alphanumerics (ligature/spacing loss)
  numbers-only     the excerpt's numeric tokens are all on the cited page, but the
                   wording is not — i.e. the FIGURE is verifiable, the QUOTE is a
                   reconstruction. Honest, but not a verbatim quote.
  wrong-page       found elsewhere in the same document, NOT on the cited page
  not-found        not in the document at all  -> HARD FAIL
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] if (Path(__file__).resolve().parents[1] / "data").exists() else Path.cwd()

PAGE_MARKER = re.compile(r"=====\s*PAGE\s+(\d+)\s*=====")
NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")


def split_pages(text: str) -> dict[int, str]:
    """Split an extract into {page_number: text} using the extractor's markers."""
    pages: dict[int, str] = {}
    parts = PAGE_MARKER.split(text)
    # parts = [pre, "1", body1, "2", body2, ...]
    for i in range(1, len(parts) - 1, 2):
        try:
            pages[int(parts[i])] = parts[i + 1]
        except ValueError:
            continue
    return pages


def norm_ws(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower()


def norm_alnum(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def number_tokens(s: str) -> list[str]:
    return [m.group(0).replace(",", "") for m in NUMBER.finditer(s)]


def digits_only(s: str) -> str:
    """Collapse a text to digits and decimal points only.

    PDF extraction routinely corrupts numeric tokens by inserting whitespace
    inside them ("201, 669", "( 126,300)", "138, 629" — all observed in the
    North Dumfries binder via pypdf). Any verification that strips only commas
    reports false failures on figures that are genuinely printed on the page.
    Stripping every separator is the only sound comparison basis for
    machine-extracted PDF text.
    """
    return re.sub(r"[^0-9.]", "", s)


def numbers_present(needles: list[str], haystack: str) -> tuple[bool, list[str]]:
    """Every numeric token must appear, tolerating separator corruption."""
    hay = digits_only(haystack)
    missing = [n for n in needles if digits_only(n) not in hay]
    return (not missing), missing


def classify(excerpt: str, cited_page_text: str, doc_text: str) -> tuple[str, str]:
    if not excerpt:
        return "no-excerpt", "fact carries no excerpt to verify"

    if excerpt in cited_page_text:
        return "verbatim", ""
    if norm_ws(excerpt) in norm_ws(cited_page_text):
        return "normalized", "matched after whitespace/case collapse"
    if norm_alnum(excerpt) and norm_alnum(excerpt) in norm_alnum(cited_page_text):
        return "alnum", "matched after stripping non-alphanumerics (PDF spacing/ligature loss)"

    needles = number_tokens(excerpt)
    if needles:
        ok, missing = numbers_present(needles, cited_page_text)
        if ok:
            return "numbers-only", f"all {len(needles)} numeric token(s) present on the cited page; wording differs (excerpt is a reconstruction, not a quote)"

    # Is it anywhere else in the document?
    if norm_alnum(excerpt) and norm_alnum(excerpt) in norm_alnum(doc_text):
        return "wrong-page", "text found in the document but NOT on the cited page"
    if needles:
        ok, _ = numbers_present(needles, doc_text)
        if ok:
            return "wrong-page", "numeric tokens found in the document but NOT on the cited page"

    return "not-found", "neither the wording nor the numeric tokens appear in the cited document"


TIER_ORDER = ["verbatim", "normalized", "alnum", "numbers-only", "no-excerpt", "wrong-page", "not-found"]
HARD_FAIL = {"not-found", "wrong-page"}


def main(argv: list[str]) -> int:
    ledger_path = Path(argv[1]) if len(argv) > 1 else ROOT / "data" / "evidence-ledger.json"
    base = ledger_path.resolve().parents[1]
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))

    sources = {s["id"]: s for s in ledger.get("sources", [])}
    extracts: dict[str, tuple[dict[int, str], str]] = {}
    for sid, src in sources.items():
        rel = src.get("extractedText")
        if not rel:
            continue
        p = (base / rel)
        if not p.exists():
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        extracts[sid] = (split_pages(text), text)

    results = []
    for f in ledger.get("facts", []):
        sid = f.get("sourceId")
        page = f.get("page")
        excerpt = (f.get("excerpt") or "").strip()
        entry = {"id": f.get("id"), "sourceId": sid, "page": page, "amountCad": f.get("amountCad")}

        if sid not in extracts:
            entry.update(tier="unverifiable", note=f"no local extract for source '{sid}' (url-only or missing PDF)")
            results.append(entry)
            continue

        pages, doc = extracts[sid]
        if page is None:
            page_text = doc
            page_note = "no page cited; searched whole document"
        elif page not in pages:
            entry.update(tier="bad-page-number", note=f"cited page {page} does not exist in the extract ({len(pages)} pages)")
            results.append(entry)
            continue
        else:
            page_text = pages[page]
            page_note = ""

        tier, note = classify(excerpt, page_text, doc)

        # An amount claim should also be findable where it is cited.
        amount_note = ""
        amt = f.get("amountCad")
        if isinstance(amt, (int, float)) and amt:
            variants = {f"{int(amt):,}", str(int(amt)), f"{amt:,.2f}", f"{amt:.2f}"}
            hay_digits = digits_only(page_text)
            if not any(digits_only(v) in hay_digits for v in variants):
                amount_note = f"amountCad {amt} not literally present on the cited page (may be a subtotal or reformatted)"

        entry.update(tier=tier, note="; ".join(x for x in [note, page_note, amount_note] if x))
        results.append(entry)

    counts: dict[str, int] = {}
    for r in results:
        counts[r["tier"]] = counts.get(r["tier"], 0) + 1

    print(f"citation audit: {len(results)} facts")
    for tier in TIER_ORDER + [t for t in counts if t not in TIER_ORDER]:
        if counts.get(tier):
            print(f"  {tier:>16}: {counts[tier]}")

    failures = [r for r in results if r["tier"] in HARD_FAIL or r["tier"] == "bad-page-number"]
    if failures:
        print("\nHARD FAILURES (a cited page does not support the claim):")
        for r in failures:
            print(f"  {r['id']} [{r['sourceId']} p{r['page']}] {r['tier']}: {r['note']}")

    weak = [r for r in results if r["tier"] in {"numbers-only", "unverifiable", "no-excerpt"}]
    if weak:
        print("\nWEAKER-THAN-VERBATIM (honest, but not a quote):")
        for r in weak:
            print(f"  {r['id']} [{r['sourceId']} p{r['page']}] {r['tier']}: {r['note']}")

    out = ledger_path.parent / "citation-audit.json"
    out.write_text(json.dumps({"counts": counts, "results": results}, indent=1), encoding="utf-8")
    print(f"\nwrote {out}")

    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
