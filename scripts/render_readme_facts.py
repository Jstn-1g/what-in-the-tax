#!/usr/bin/env python3
"""Regenerate the counted claims in README.md from the artifacts that own them.

A tool whose whole proposition is "nothing is stated without evidence" had
hand-written counts in its own README, and they had already drifted at N=1: the
FIR year-selection sentence said 129 / 273 / 34 / 8 while the registry said
130 / 273 / 33 / 8. Prose cannot be trusted to track an artifact it never reads.

Each region of README.md between a pair of

    <!-- generated:NAME -->
    <!-- /generated:NAME -->

markers is rewritten from the artifact that owns those numbers. Interpretive
prose stays hand-written and human-reviewed; only figures and identifiers are
machine-supplied. Every figure is bound to a ledger id, so a renamed entry or a
changed amount fails this script rather than silently rewriting the README into
agreement with itself -- a generator that quietly adopts whatever it finds is a
worse instrument than the hand-written prose it replaced.

    python scripts/render_readme_facts.py           # rewrite README.md
    python scripts/render_readme_facts.py --check   # exit 1 if it would change

--check runs in release validation, so drift is a red build rather than
something a reader discovers.
"""

from __future__ import annotations

import argparse
import difflib
import json
import os
import re
import sys
import tempfile
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
README = ROOT / "README.md"
LEDGER = ROOT / "data" / "evidence-ledger.json"
AUDIT = ROOT / "data" / "citation-audit.json"
HISTORY = ROOT / "web" / "public" / "registry" / "ontario-municipal-history.json"
PACKS = ROOT / "web" / "public" / "packs"

# Hard citation-audit tiers, kept in one place so this file and PUBLISH.md
# cannot disagree about what counts as a failure.
HARD_TIERS = ("not-found", "wrong-page", "bad-page-number")


class ReadmeFactsError(RuntimeError):
    """A README claim could no longer be bound to the artifact behind it."""


def load(path: Path) -> dict:
    if not path.is_file():
        raise ReadmeFactsError(f"missing artifact: {path.relative_to(ROOT)}")
    return json.loads(path.read_text(encoding="utf-8"))


def money(value: float) -> str:
    return f"{value:,.0f}"


def amount_of(ledger: dict, fact_id: str) -> float:
    """Look an amount up by id across facts and derived rows, or fail loudly."""
    for row in ledger["facts"] + ledger["derived"]:
        if row.get("id") == fact_id:
            amount = row.get("amountCad")
            if amount is None:
                raise ReadmeFactsError(f"{fact_id} carries no amountCad")
            return amount
    raise ReadmeFactsError(
        f"README cites ledger id {fact_id}, which is no longer in the ledger. "
        "Update scripts/render_readme_facts.py deliberately rather than "
        "letting the README describe an entry that does not exist."
    )


# The numbers come from the ledger; the meanings are reviewed prose. Binding
# them by id is the point: these four figures are within 1.2% of each other and
# conflating any two of them is the most likely way this project publishes a
# wrong number that still looks right.
RECONCILIATION = (
    ("ND-LEVY-2026-ADOPTED", "municipal levy — rate × assessment, what appears on a tax bill"),
    ("ND-TAXATION-REVENUE-2026", "total taxation revenue — levy plus supplementaries and PILs"),
    ("DRV-ND-DEPT-SUM", "expenditure base — funded by taxation *plus* non-tax corporate revenue"),
    ("ND-BUDGET-REQUIREMENT-TAXBYLAW-2026", None),  # rendered with a computed delta
)


def render_reconciliation(ledger: dict, **_: object) -> str:
    base = amount_of(ledger, "DRV-ND-DEPT-SUM")
    taxation = amount_of(ledger, "ND-TAXATION-REVENUE-2026")
    corporate = amount_of(ledger, "ND-CORPORATE-REVENUES-2026")
    adopted = amount_of(ledger, "ND-LEVY-2026-ADOPTED")
    recital = amount_of(ledger, "ND-BUDGET-REQUIREMENT-TAXBYLAW-2026")

    # The identity the allocation rests on. The builder asserts it too; asserting
    # it again here means the README cannot state it while it is false.
    if abs((taxation + corporate) - base) > 0.5:
        raise ReadmeFactsError(
            f"allocation base {base} no longer equals taxation {taxation} + "
            f"corporate revenues {corporate}. The README says it ties exactly."
        )

    delta = adopted - recital
    lines = [
        f"The township allocation base is **{money(base)}**, which ties exactly to the binder's own",
        f"published total: taxation {money(taxation)} + corporate revenues {money(corporate)}, Net Budget 0.",
        "The generator asserts this identity and so does this README renderer.",
        "",
        "Four figures are easy to conflate and are deliberately kept distinct:",
        "",
        "| figure | ledger id | meaning |",
        "|---|---|---|",
    ]
    for fact_id, meaning in RECONCILIATION:
        if meaning is None:
            meaning = (
                f"the tax-rate by-law's recital, ${money(abs(delta))} "
                f"{'below' if delta > 0 else 'above'} the adopted levy — recorded, not reconciled"
            )
        lines.append(f"| {money(amount_of(ledger, fact_id))} | `{fact_id}` | {meaning} |")
    return "\n".join(lines)


def render_open_gaps(ledger: dict, **_: object) -> str:
    gaps = sorted(ledger["gaps"], key=lambda g: g["id"])
    with_trail = [g for g in gaps if g.get("searchTrail")]
    lines = [f"{len(gaps)} open, from the ledger's own `gaps` list:", ""]
    for gap in gaps:
        trail = " *(search trail recorded)*" if gap.get("searchTrail") else ""
        lines.append(f"- `{gap['id']}` — {gap['title']}{trail}")
    lines.append("")
    if len(with_trail) == len(gaps):
        lines.append("Every open gap records where we looked.")
    else:
        # The README used to claim all of them did. It is a smaller
        # embarrassment to publish the real number than to be caught at it.
        verb = "carries" if len(with_trail) == 1 else "carry"
        lines.append(
            f"{len(with_trail)} of {len(gaps)} {verb} a `searchTrail` recording where we "
            "looked. The rest record what is missing and what would close them, but not yet "
            "the search."
        )
    closed = sorted(ledger["closedGaps"], key=lambda g: g["id"])
    lines.append("")
    lines.append(
        f"Closed and retained in `closedGaps` rather than deleted, so the audit trail survives "
        f"({len(closed)}): " + ", ".join(f"`{g['id']}`" for g in closed) + "."
    )
    return "\n".join(lines)


def render_ledger_counts(ledger: dict, audit: dict, packs: int, **_: object) -> str:
    counts = audit.get("counts", {})
    hard = sum(counts.get(tier, 0) for tier in HARD_TIERS)
    tiers = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    audited = sum(counts.values())
    return "\n".join(
        [
            f"- Draft previews published: **{packs}** Ontario packs.",
            f"- North Dumfries ledger: **{len(ledger['facts'])}** facts, "
            f"{len(ledger['derived'])} derived rows, {len(ledger['findings'])} findings, "
            f"{len(ledger['gaps'])} open gaps, {len(ledger['closedGaps'])} closed gaps.",
            f"- Citation audit over {audited} cited facts: **{hard}** hard failures "
            f"({', '.join(HARD_TIERS)}). Binding tiers — "
            + ", ".join(f"{tier} {n}" for tier, n in tiers)
            + ".",
            "- Every finding carries `billImpactCad: null`. No exception exists in the policy "
            "and none is reachable in the builder.",
        ]
    )


def render_fir_selection(history: dict, **_: object) -> str:
    coverage = history["coverage"]
    records = history["records"]
    total = coverage["currentMunicipalities"]
    if total != len(records):
        raise ReadmeFactsError(
            f"registry says {total} current municipalities but carries {len(records)} records"
        )
    by_year = coverage["latestFirYearCounts"]
    if sum(by_year.values()) != total:
        raise ReadmeFactsError(
            f"latest-FIR-year counts sum to {sum(by_year.values())}, not {total}"
        )
    years = sorted((y for y in by_year if y != "unavailable"), reverse=True)
    newest, *fallbacks = years
    parts = [f"{by_year[newest]} currently select {newest}"]
    parts += [f"{by_year[y]} fall back to {y}" for y in fallbacks]
    parts.append(f"{by_year['unavailable']} have no record in that window")
    paragraph = (
        f"The resident search starts from Ontario's current {total}-municipality list. "
        "Each municipality then selects its newest record from the hash-pinned "
        + ", ".join(years[:-1])
        + f" and {years[-1]} FIR bulk files: "
        + ", ".join(parts[:-1])
        + f", and {parts[-1]}. All available years are retained for context. FIR "
        "records are historical filings, not receipts, current tax by-laws, or "
        "formal audits."
    )
    return textwrap.fill(paragraph, width=92)


# Some counts read better as words than as a generated block. Those sentences
# stay hand-written, but they do not get to go stale quietly: if the artifact
# moves, this fails and a human rewrites the sentence deliberately.
PROSE_BINDINGS = (
    ("draft previews for six Ontario municipalities", "packs", 6),
    ("Six Ontario receipts are available", "packs", 6),
)


def check_prose(text: str, context: dict) -> None:
    for phrase, key, expected in PROSE_BINDINGS:
        actual = context[key]
        if phrase in text and actual != expected:
            raise ReadmeFactsError(
                f"README says {phrase!r}, but {key} is now {actual}, not {expected}. "
                "Rewrite that sentence and update PROSE_BINDINGS."
            )
        if phrase not in text and actual == expected:
            raise ReadmeFactsError(
                f"PROSE_BINDINGS still watches {phrase!r}, which is no longer in README.md. "
                "Remove the binding rather than leaving a check that guards nothing."
            )


RENDERERS = {
    "fir-selection": render_fir_selection,
    "ledger-counts": render_ledger_counts,
    "reconciliation": render_reconciliation,
    "open-gaps": render_open_gaps,
}


def rendered_readme() -> str:
    text = README.read_text(encoding="utf-8")
    context = dict(
        ledger=load(LEDGER),
        audit=load(AUDIT),
        history=load(HISTORY),
        packs=len(list(PACKS.glob("*.json"))),
    )
    check_prose(text, context)
    for name, render in RENDERERS.items():
        open_tag = f"<!-- generated:{name} -->"
        close_tag = f"<!-- /generated:{name} -->"
        pattern = re.compile(
            rf"{re.escape(open_tag)}.*?{re.escape(close_tag)}", re.DOTALL
        )
        if len(pattern.findall(text)) != 1:
            raise ReadmeFactsError(
                f"README.md must contain exactly one generated:{name} block"
            )
        replacement = f"{open_tag}\n{render(**context)}\n{close_tag}"
        text = pattern.sub(lambda _: replacement, text, count=1)
    return text


def write_atomic(path: Path, payload: str) -> None:
    handle, tmp_name = tempfile.mkstemp(
        dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp"
    )
    tmp = Path(tmp_name)
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="do not write; exit 1 with a diff if README.md is out of date",
    )
    args = parser.parse_args()

    try:
        updated = rendered_readme()
    except ReadmeFactsError as error:
        print(f"::error::{error}", file=sys.stderr)
        return 1

    current = README.read_text(encoding="utf-8")
    if updated == current:
        print("README.md generated blocks are current.")
        return 0
    if args.check:
        diff = difflib.unified_diff(
            current.splitlines(True),
            updated.splitlines(True),
            fromfile="README.md (committed)",
            tofile="README.md (regenerated)",
        )
        sys.stderr.writelines(diff)
        print(
            "::error::README.md states counts that no longer match the artifacts. "
            "Run python scripts/render_readme_facts.py and commit the result.",
            file=sys.stderr,
        )
        return 1
    write_atomic(README, updated)
    print("README.md generated blocks updated.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
