"""
Deterministic citation and source-binding audit.

The audit deliberately separates two questions:

1. Does the cited page support the claim?
2. Are the official source bytes and the extracted text cryptographically bound?

Draft packs can use the resulting weaknesses as a work queue.  The publication
validator promotes the same weaknesses to hard failures when a receipt-driving
fact belongs to a sealed or published pack.

No model calls.  No network.  The result is reproducible by any third party
holding the same source bytes and extracts.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import zipfile
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

PAGE_MARKER = re.compile(r"=====\s*PAGE\s+(\d+)\s*=====")
NUMBER = re.compile(
    r"(?<!\d)(?:\d{1,3}(?:[ ,\u00a0\u202f]\d{3})+|\d+)(?:[.,]\d+)?(?!\d)"
)
SHA256 = re.compile(r"^[0-9a-fA-F]{64}$")

STRONG_TIERS = frozenset({"verbatim", "normalized", "alnum", "row-bound"})
WEAK_TIERS = frozenset(
    {
        "numbers-only",
        "no-excerpt",
        "unverifiable",
        "bad-page-number",
        "wrong-page",
        "not-found",
    }
)
HARD_CITATION_TIERS = frozenset({"not-found", "wrong-page", "bad-page-number"})


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def split_pages(text: str) -> dict[int, str]:
    """Split an extract into ``{page_number: text}`` using extractor markers."""
    pages: dict[int, str] = {}
    parts = PAGE_MARKER.split(text)
    for index in range(1, len(parts) - 1, 2):
        try:
            pages[int(parts[index])] = parts[index + 1]
        except ValueError:
            continue
    return pages


def norm_ws(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().casefold()


def norm_alnum(value: str) -> str:
    return "".join(character for character in value.casefold() if character.isalnum())


def number_tokens(value: str) -> list[str]:
    return [match.group(0) for match in NUMBER.finditer(value)]


def digits_only(value: str) -> str:
    """Collapse one row/token to digits and decimal points.

    This remains useful for a single extracted line, where whitespace and
    punctuation can split a printed number without accidentally joining digits
    from unrelated rows.
    """

    return re.sub(r"[^0-9.]", "", value)


def canonical_number(value: str) -> str:
    """Normalize English/French Canadian grouping and decimal separators."""

    compact = re.sub(r"[\s\u00a0\u202f$()\-−]", "", value)
    if "," in compact and "." in compact:
        decimal_separator = "," if compact.rfind(",") > compact.rfind(".") else "."
        grouping_separator = "." if decimal_separator == "," else ","
        compact = compact.replace(grouping_separator, "")
        compact = compact.replace(decimal_separator, ".")
    elif "," in compact:
        pieces = compact.split(",")
        # A single 3-digit suffix is the common English grouping form (1,234).
        if len(pieces) == 2 and len(pieces[1]) != 3:
            compact = ".".join(pieces)
        else:
            compact = "".join(pieces)
    return compact


def _number_pattern(value: str) -> re.Pattern[str]:
    """Build a conservative PDF-noise-tolerant pattern for one numeric token."""

    canonical = canonical_number(value)
    integer, dot, fraction = canonical.partition(".")
    separator = r"[\s,\u00a0\u202f]*"
    body = separator.join(re.escape(character) for character in integer)
    if dot:
        body += r"\s*[.,]\s*" + r"\s*".join(
            re.escape(character) for character in fraction
        )
    return re.compile(rf"(?<!\d){body}(?!\d)")


def numbers_present(needles: list[str], haystack: str) -> tuple[bool, list[str]]:
    """Require every numeric token without concatenating unrelated page digits."""

    missing = [needle for needle in needles if not _number_pattern(needle).search(haystack)]
    return (not missing), missing


def label_words(excerpt: str) -> list[str]:
    """Substantive Unicode alphabetic tokens from an excerpt."""

    return [
        word.casefold()
        for word in re.findall(r"[^\W\d_]{4,}", excerpt, flags=re.UNICODE)
    ]


def row_bound(excerpt: str, page_text: str) -> bool:
    """Check that the amount(s) and label words share one extracted row."""

    words = label_words(excerpt)
    needles = number_tokens(excerpt)
    if not words or not needles:
        return False
    required_word_count = max(2, int(round(0.6 * len(words))))
    for line in page_text.splitlines():
        if not line.strip():
            continue
        if not all(_number_pattern(needle).search(line) for needle in needles):
            continue
        lowered = line.casefold()
        if sum(1 for word in words if word in lowered) >= required_word_count:
            return True
    return False


def classify(excerpt: str, cited_page_text: str, document_text: str) -> tuple[str, str]:
    if not excerpt:
        return "no-excerpt", "fact carries no excerpt to verify"

    if excerpt in cited_page_text:
        return "verbatim", ""
    if norm_ws(excerpt) in norm_ws(cited_page_text):
        return "normalized", "matched after whitespace/case collapse"
    normalized_excerpt = norm_alnum(excerpt)
    if normalized_excerpt and normalized_excerpt in norm_alnum(cited_page_text):
        return (
            "alnum",
            "matched after stripping non-alphanumerics (PDF spacing/ligature loss)",
        )

    needles = number_tokens(excerpt)
    if needles:
        present, _ = numbers_present(needles, cited_page_text)
        if present:
            if row_bound(excerpt, cited_page_text):
                return (
                    "row-bound",
                    "amount and label words co-occur on one line of the cited page",
                )
            return (
                "numbers-only",
                f"all {len(needles)} numeric token(s) are on the cited page, "
                "but their binding to the label is unverified",
            )

    if normalized_excerpt and normalized_excerpt in norm_alnum(document_text):
        return "wrong-page", "text found in the document but not on the cited page"
    if needles:
        present, _ = numbers_present(needles, document_text)
        if present:
            return (
                "wrong-page",
                "numeric tokens found in the document but not on the cited page",
            )

    return (
        "not-found",
        "neither the wording nor the numeric tokens appear in the cited document",
    )


def _resolve_inside(root: Path, declared_path: str) -> tuple[Path | None, str | None]:
    try:
        candidate = Path(declared_path)
    except (OSError, ValueError) as exc:
        return None, f"invalid path: {exc}"
    if candidate.is_absolute():
        return None, "absolute paths are not allowed"
    resolved_root = root.resolve()
    try:
        resolved = (resolved_root / candidate).resolve()
    except (OSError, ValueError) as exc:
        return None, f"invalid path: {exc}"
    try:
        resolved.relative_to(resolved_root)
    except ValueError:
        return None, "path escapes the evidence root"
    return resolved, None


def _check_bound_file(
    source: dict[str, Any],
    *,
    path_field: str,
    hash_field: str,
    root: Path,
    missing_path_issue: str,
    missing_file_issue: str,
    missing_hash_issue: str,
    bad_hash_issue: str,
    mismatch_issue: str,
) -> tuple[Path | None, dict[str, Any], list[str]]:
    declared_path = source.get(path_field)
    declared_hash = source.get(hash_field)
    result: dict[str, Any] = {
        "declaredPath": declared_path,
        "declaredSha256": declared_hash,
        "actualSha256": None,
    }
    issues: list[str] = []

    if not isinstance(declared_path, str) or not declared_path.strip():
        issues.append(missing_path_issue)
        return None, result, issues

    path, path_error = _resolve_inside(root, declared_path)
    if path_error:
        issues.append(f"{missing_file_issue}:{path_error}")
        return None, result, issues
    if path is None or not path.is_file():
        issues.append(missing_file_issue)
        return None, result, issues

    try:
        actual_hash = sha256_file(path)
    except OSError as exc:
        issues.append(f"{missing_file_issue}:unreadable:{exc}")
        return None, result, issues
    result["actualSha256"] = actual_hash
    if not isinstance(declared_hash, str) or not declared_hash.strip():
        issues.append(missing_hash_issue)
    elif not SHA256.fullmatch(declared_hash):
        issues.append(bad_hash_issue)
    elif declared_hash.casefold() != actual_hash:
        issues.append(mismatch_issue)
    return path, result, issues


def inspect_source(source: dict[str, Any], root: Path) -> tuple[dict[str, Any], str | None]:
    """Inspect official bytes and extract bindings for one ledger source."""

    source_path, source_file, source_issues = _check_bound_file(
        source,
        path_field="localPath",
        hash_field="sha256",
        root=root,
        missing_path_issue="source-path-missing",
        missing_file_issue="source-file-missing",
        missing_hash_issue="source-sha256-missing",
        bad_hash_issue="source-sha256-invalid",
        mismatch_issue="source-sha256-mismatch",
    )
    extract_path, extract_file, extract_issues = _check_bound_file(
        source,
        path_field="extractedText",
        hash_field="extractedTextSha256",
        root=root,
        missing_path_issue="extract-path-missing",
        missing_file_issue="extract-file-missing",
        missing_hash_issue="extract-sha256-missing",
        bad_hash_issue="extract-sha256-invalid",
        mismatch_issue="extract-sha256-mismatch",
    )
    source_file["declaredBytes"] = source.get("bytes")
    source_file["actualBytes"] = source_path.stat().st_size if source_path else None
    if source_path is not None:
        declared_bytes = source.get("bytes")
        if declared_bytes is None:
            source_issues.append("source-bytes-missing")
        elif (
            isinstance(declared_bytes, bool)
            or not isinstance(declared_bytes, int)
            or declared_bytes < 0
        ):
            source_issues.append("source-bytes-invalid")
        elif declared_bytes != source_path.stat().st_size:
            source_issues.append("source-bytes-mismatch")

    # Retained for diagnostics without exposing absolute workstation paths.
    binding = {
        "sourceId": source.get("id"),
        "sourceFile": source_file,
        "extractFile": extract_file,
        "issues": source_issues + extract_issues,
        "sourceReadable": source_path is not None,
        "extractReadable": extract_path is not None,
    }
    try:
        extract_text = (
            extract_path.read_text(encoding="utf-8", errors="replace")
            if extract_path is not None
            else None
        )
    except OSError as exc:
        binding["issues"].append(f"extract-file-missing:unreadable:{exc}")
        binding["extractReadable"] = False
        extract_text = None

    if extract_text is None and source.get("archiveMember") is not None:
        # A tabular archive member is its own extract. The container bytes are
        # already hash-bound above; the member digest declared here is
        # re-verified on every audit, and the text is read in memory rather
        # than committed as a multi-megabyte derived copy of a file the
        # repository already pins exactly. Nothing is read unpinned: a missing
        # or mismatched member digest yields no extract, and the publication
        # validator treats both as invalid declared bindings.
        member_text = _read_archive_member(source, source_path, binding["issues"])
        if member_text is not None:
            binding["extractReadable"] = True
            extract_text = member_text
            # The extract is not missing - it is the digest-bound member. The
            # path-shaped issues from the null extractedText field would say
            # otherwise, and hash-shaped extract bindings do not apply here.
            binding["issues"] = [
                issue
                for issue in binding["issues"]
                if issue not in ("extract-path-missing", "extract-sha256-missing")
            ]
    return binding, extract_text


def _read_archive_member(
    source: dict[str, Any], source_path: Path | None, issues: list[str]
) -> str | None:
    """Read a declared ZIP member as extract text, bound by its digest."""

    member_name = source.get("archiveMember")
    declared_hash = source.get("archiveMemberSha256")
    if source_path is None:
        issues.append("archive-member-source-unreadable")
        return None
    if not isinstance(member_name, str) or not member_name:
        issues.append("archive-member-invalid")
        return None
    if not isinstance(declared_hash, str) or not SHA256.fullmatch(declared_hash):
        issues.append("archive-member-sha256-missing")
        return None
    try:
        with zipfile.ZipFile(source_path) as archive:
            member_bytes = archive.read(member_name)
    except (OSError, KeyError, zipfile.BadZipFile):
        issues.append("archive-member-missing")
        return None
    if hashlib.sha256(member_bytes).hexdigest() != declared_hash.casefold():
        issues.append("archive-member-sha256-mismatch")
        return None
    return member_bytes.decode("utf-8-sig", errors="replace")


def _match_is_negative(match: re.Match[str], text: str) -> bool:
    prefix = text[max(0, match.start() - 16) : match.start()]
    suffix = text[match.end() : min(len(text), match.end() + 8)]
    has_minus = re.search(r"[-−]\s*\$?\s*$", prefix) is not None
    has_parentheses = (
        re.search(r"\(\s*\$?\s*$", prefix) is not None
        and re.match(r"\s*\)", suffix) is not None
    )
    return has_minus or has_parentheses


# Budget prose writes round figures in words: "new debt financing proposed
# [$5 million]". The digit variants below never match that, so a citation
# pointing at exactly the right page was reported as amount-not-on-cited-page -
# a hard failure, and a false one. docs/GENERALIZATION-PLAN.md records the same
# class of defect: the author was more accurate than the measurement.
#
# Only exact renderings are accepted. "5 million" binds 5,000,000 because the
# division is exact; it must never bind 5,043,210, because there the prose is a
# rounding and treating it as proof of the precise figure is the overclaim this
# audit exists to catch.
# Budget books use the word and the single-letter abbreviation interchangeably:
# the Region's own summary prints "Property Taxes $887 M". The abbreviation is
# matched with a trailing word boundary so "887 Metres" cannot bind.
_MAGNITUDES = (
    (1_000_000_000, ("billion", "B")),
    (1_000_000, ("million", "M")),
    (1_000, ("thousand", "K")),
)


def _magnitude_phrases(absolute: float) -> set[tuple[str, str]]:
    """(number, magnitude word or abbreviation) pairs that render this exactly."""

    phrases: set[tuple[str, str]] = set()
    for scale, words in _MAGNITUDES:
        if absolute < scale:
            continue
        quotient = absolute / scale
        # Exact multiples only, and only to one decimal place ("1.5 million"),
        # because a longer decimal is not how prose renders a figure anyway.
        for places in (0, 1):
            rendered = round(quotient, places)
            if abs(rendered * scale - absolute) > 1e-9:
                continue
            text = (
                f"{rendered:.{places}f}".rstrip("0").rstrip(".")
                if places
                else f"{int(rendered)}"
            )
            for word in words:
                phrases.add((text, word))
    return phrases


def _magnitude_pattern(number: str, word: str) -> re.Pattern[str]:
    # A single-letter abbreviation needs a trailing word boundary so "887 M"
    # binds and "887 Metres" does not. The spelled word does not, so plurals and
    # possessives still match.
    tail = r"\b" if len(word) == 1 else ""
    return re.compile(
        re.escape(number).replace(r"\.", r"\s*[.,]\s*")
        + r"\s*(?:-|–)?\s*"
        + re.escape(word)
        + tail,
        re.IGNORECASE if len(word) > 1 else 0,
    )


def _amount_binding_issue(fact: dict[str, Any], page_text: str) -> str | None:
    amount = fact.get("amountCad")
    if isinstance(amount, bool) or not isinstance(amount, (int, float)) or amount == 0:
        return None
    absolute = abs(amount)

    # Budget books print large figures in thousands: the Region's page 12 says
    # 887,329 where the fact's canonical amount is 887,329,000. A fact that
    # declares scaleFactor states that relationship explicitly - the page
    # prints canonical / scaleFactor - which is GENERALIZATION-PLAN 9.5's
    # "printedValue x scaleFactor == canonicalValue" made checkable. The
    # declaration is validated, never inferred: a nonsense scaleFactor is an
    # issue in its own right rather than silently ignored, and a canonical
    # amount that does not divide exactly gets decimal variants only, so
    # 887,329,432 at scale 1000 can never borrow the page's clean 887,329.
    scale = fact.get("scaleFactor")
    if scale is not None:
        if isinstance(scale, bool) or not isinstance(scale, (int, float)) or scale <= 0:
            return "scale-factor-invalid"
        scaled = absolute / scale
        absolute = scaled
    # Integer renderings only when the value IS an integer. int() truncates,
    # so a $298.54 fact used to offer "298" as a variant - and a scaled
    # 887,329,432 at scale 1000 would have offered the page's clean "887,329".
    # A truncated rendering matching the page is not the fact being on the
    # page; it is a different number being on the page.
    variants = {f"{absolute:,.2f}", f"{absolute:.2f}"}
    if float(absolute).is_integer():
        variants |= {f"{int(absolute):,}", str(int(absolute))}
    matches = [
        match
        for variant in variants
        for match in _number_pattern(variant).finditer(page_text)
    ]
    if not matches:
        matches = [
            match
            for number, word in _magnitude_phrases(absolute)
            for match in _magnitude_pattern(number, word).finditer(page_text)
        ]
    if not matches:
        return "amount-not-on-cited-page"
    expected_negative = amount < 0
    if any(_match_is_negative(match, page_text) == expected_negative for match in matches):
        return None
    return "amount-sign-mismatch"


def audit_ledger(ledger: dict[str, Any], *, root: Path = ROOT) -> dict[str, Any]:
    """Return a deterministic citation report without writing to disk."""

    sources: dict[str, dict[str, Any]] = {}
    duplicate_source_ids: set[str] = set()
    ledger_sources = ledger.get("sources", []) or []
    if not isinstance(ledger_sources, list):
        ledger_sources = []
    for source in ledger_sources:
        if not isinstance(source, dict):
            continue
        source_id = source.get("id")
        if not isinstance(source_id, str) or not source_id:
            continue
        if source_id in sources:
            duplicate_source_ids.add(source_id)
        sources[source_id] = source

    source_bindings: dict[str, dict[str, Any]] = {}
    extracts: dict[str, tuple[dict[int, str], str]] = {}
    for source_id, source in sources.items():
        binding, extract_text = inspect_source(source, root)
        if source_id in duplicate_source_ids:
            binding["issues"].append("duplicate-source-id")
        source_bindings[source_id] = binding
        if extract_text is not None:
            extracts[source_id] = (split_pages(extract_text), extract_text)

    results: list[dict[str, Any]] = []
    ledger_facts = ledger.get("facts", []) or []
    if not isinstance(ledger_facts, list):
        ledger_facts = []
    for fact in ledger_facts:
        if not isinstance(fact, dict):
            continue
        source_id = fact.get("sourceId")
        page = fact.get("page")
        excerpt = (fact.get("excerpt") or "").strip()
        entry: dict[str, Any] = {
            "id": fact.get("id"),
            "sourceId": source_id,
            "page": page,
            "amountCad": fact.get("amountCad"),
            "bindingIssues": [],
        }

        if not isinstance(source_id, str) or source_id not in sources:
            entry.update(
                tier="unverifiable",
                note=f"fact references missing source '{source_id}'",
                bindingIssues=["source-id-missing"],
            )
            results.append(entry)
            continue

        entry["bindingIssues"] = list(source_bindings[source_id]["issues"])
        if source_id not in extracts:
            entry.update(
                tier="unverifiable",
                note=f"no readable local extract for source '{source_id}'",
            )
            results.append(entry)
            continue

        pages, document_text = extracts[source_id]
        if page is None:
            page_text = document_text
            entry["bindingIssues"].append("page-citation-missing")
            page_note = "no page cited; searched the whole extract"
        elif page not in pages:
            entry.update(
                tier="bad-page-number",
                note=f"cited page {page} does not exist in the extract ({len(pages)} pages)",
            )
            results.append(entry)
            continue
        else:
            page_text = pages[page]
            page_note = ""

        tier, note = classify(excerpt, page_text, document_text)
        amount_issue = _amount_binding_issue(fact, page_text)
        if amount_issue:
            entry["bindingIssues"].append(amount_issue)
        # A strong tier says the excerpt is on the page and the amount is on the
        # page - two facts checked independently and never against each other.
        # An excerpt can be a genuine verbatim quote of a sentence that does not
        # contain the number, while the number sits elsewhere on the same page
        # in an unrelated row. That citation looks top-tier and evidences
        # nothing about the figure. Recorded per fact so it is visible and
        # countable; excerpts that carry no amount at all (definitions, dates)
        # are not the target and facts without an amount are exempt.
        if tier in STRONG_TIERS and not amount_issue:
            excerpt_issue = _amount_binding_issue(fact, excerpt)
            if excerpt_issue == "amount-not-on-cited-page":
                entry["bindingIssues"].append("amount-not-in-excerpt")
        entry["bindingIssues"] = sorted(set(entry["bindingIssues"]))
        entry.update(
            tier=tier,
            note="; ".join(part for part in (note, page_note) if part),
        )
        results.append(entry)

    counts = dict(Counter(result["tier"] for result in results))
    binding_issue_counts = dict(
        Counter(
            issue
            for result in results
            for issue in result.get("bindingIssues", [])
        )
    )
    failures = [
        result for result in results if result["tier"] in HARD_CITATION_TIERS
    ]
    return {
        "ok": not failures,
        "counts": counts,
        "bindingIssueCounts": binding_issue_counts,
        "results": results,
        "sourceBindings": list(source_bindings.values()),
    }


def write_audit(report: dict[str, Any], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "ledger",
        nargs="?",
        help="repo-relative or absolute evidence-ledger JSON path",
    )
    # Keep the documented historical spelling working.
    parser.add_argument("--ledger", dest="ledger_option", help=argparse.SUPPRESS)
    parser.add_argument("--output", help="write the JSON report to this path")
    parser.add_argument(
        "--no-write",
        action="store_true",
        help="run read-only; do not write citation-audit.json",
    )
    return parser.parse_args(argv[1:])


def main(argv: list[str]) -> int:
    args = _parse_args(argv)
    declared_ledger = args.ledger_option or args.ledger
    ledger_path = Path(declared_ledger) if declared_ledger else ROOT / "data" / "evidence-ledger.json"
    if not ledger_path.is_absolute():
        ledger_path = (Path.cwd() / ledger_path).resolve()
    try:
        ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: cannot load ledger {ledger_path}: {exc}", file=sys.stderr)
        return 1

    report = audit_ledger(ledger, root=ROOT)
    print(f"citation audit: {len(report['results'])} facts")
    for tier, count in sorted(report["counts"].items()):
        print(f"  {tier:>16}: {count}")

    failures = [
        result
        for result in report["results"]
        if result["tier"] in HARD_CITATION_TIERS
    ]
    if failures:
        print("\nHARD CITATION FAILURES:")
        for result in failures:
            print(
                f"  {result['id']} [{result['sourceId']} p{result['page']}] "
                f"{result['tier']}: {result['note']}"
            )

    weak = [
        result
        for result in report["results"]
        if result["tier"] in WEAK_TIERS or result.get("bindingIssues")
    ]
    if weak:
        print("\nWEAK OR UNBOUND EVIDENCE:")
        for result in weak:
            issues = ", ".join(result.get("bindingIssues", []))
            suffix = f"; binding: {issues}" if issues else ""
            print(
                f"  {result['id']} [{result['sourceId']} p{result['page']}] "
                f"{result['tier']}: {result['note']}{suffix}"
            )

    if not args.no_write:
        output = Path(args.output) if args.output else ledger_path.parent / "citation-audit.json"
        if not output.is_absolute():
            output = (Path.cwd() / output).resolve()
        write_audit(report, output)
        print(f"\nwrote {output}")

    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
