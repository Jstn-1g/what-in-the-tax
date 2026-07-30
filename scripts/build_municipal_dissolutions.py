"""Derive Ontario municipal dissolutions from the locked StatCan interim lists.

Statistics Canada 92F0009X is the official record of changes to municipal
boundaries, status and names. Four machine-readable editions are committed and
hash-locked (sources/locks/ca-on/statcan-il-*.lock.json, reviewed by a named
person). This builder parses those exact bytes - it refuses to parse anything
whose digest does not match its lock - and emits every dissolution event
(change code 4) as a derived artifact.

The artifact answers two questions the hand-curated former-municipalities
crosswalk cannot answer for itself:

  1. Is every crosswalk entry inside the covered window confirmed by the
     official record?
  2. Does the official record carry a dissolution the crosswalk is missing?

A web test holds both directions. Events are classified by whether the
dissolved place levied property tax: Indian reserves (IRI), unorganized areas
(NO) and settlements (S-E) never did, and only taxing places belong in the
crosswalk.

The two legacy editions (2006-2011, 2011-2016) are bilingual layouts locked as
structure: document; the era-specific parsing lives here, in the open, where
the artifact's method section declares it. Editions before 2006 exist only as
a locked PDF and stay hand-curated.

Deterministic; no AI calls; no network.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCK_DIR = ROOT / "sources" / "locks" / "ca-on"
OUTPUT = ROOT / "web" / "src" / "data" / "municipal-dissolutions.json"

# Census-subdivision types that never levied their own property tax. A
# dissolution of one of these is real and reported, but it does not belong in
# a crosswalk of places whose taxes moved to a successor's bill.
NON_TAXING_TYPES = frozenset({"IRI", "NO", "S-E", "S-É", "SE"})

DISSOLUTION_CODE = "4"

# "Now part of (dissolution) - Maintenant partie de (dissolution) - Chapple , TP"
REMARK_SUCCESSOR = re.compile(
    r"\(dissolution\)[^-]*-\s*(?P<name>[^-]+?)\s*,\s*(?P<type>[A-ZÉ-]{1,4})\s*$"
)


class DissolutionBuildError(RuntimeError):
    """A locked input failed verification or an event could not be read."""


def _locked_bytes(source_id: str) -> tuple[bytes, dict]:
    """The exact reviewed bytes for one lock, refused on any mismatch."""

    lock_path = LOCK_DIR / f"{source_id}.lock.json"
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    payload_path = ROOT / lock["localPath"]
    data = payload_path.read_bytes()
    if hashlib.sha256(data).hexdigest() != lock["sha256"]:
        raise DissolutionBuildError(
            f"{source_id}: local bytes do not match the reviewed lock; "
            "refusing to parse unpinned data"
        )
    return data, lock


def _rows(data: bytes) -> list[list[str]]:
    text = data.decode("cp1252")
    return list(csv.reader(text.splitlines()))


def _event(
    dissolved: str,
    dissolved_type: str,
    successor: str,
    successor_type: str,
    effective: str,
    source_id: str,
    line: int,
    sgc: str,
) -> dict:
    day, month, year = effective.strip().split("/")
    return {
        "dissolved": dissolved.strip(),
        "dissolvedType": dissolved_type.strip(),
        "successor": successor.strip(),
        "successorType": successor_type.strip(),
        "effectiveDate": f"{year}-{month}-{day}",
        "leviedPropertyTax": dissolved_type.strip() not in NON_TAXING_TYPES,
        "sourceId": source_id,
        "sourceLine": line,
        # The legacy tables print "35 51 024" where the modern ones print
        # "3551024"; one format, or the cross-edition dedupe below is blind.
        "sgcCode": sgc.replace(" ", "").strip(),
    }


def _parse_legacy_alphabetical(data: bytes, source_id: str) -> list[dict]:
    """The 2006-2011 and 2011-2016 Table 1 layout.

    Subject rows carry the place name in column 0 and, for dissolutions, a
    bilingual remark naming the successor. Paired-event rows repeat the same
    event with names in column 1 and no remark; the subject rows are the
    complete record, so only they are read, and the remark is the successor
    authority. A code-4 subject row whose remark cannot be parsed is an error,
    not a skip - silence here would drop a dissolution on the floor.
    """

    events: list[dict] = []
    for line_number, row in enumerate(_rows(data), start=1):
        if len(row) < 7:
            continue
        name = row[0].strip()
        code = row[3].strip()
        if not name or code != DISSOLUTION_CODE:
            continue
        remark = (row[7] if len(row) > 7 else "").strip()
        match = REMARK_SUCCESSOR.search(remark)
        if not match:
            raise DissolutionBuildError(
                f"{source_id} line {line_number}: dissolution of {name!r} has "
                f"no parseable successor remark: {remark!r}"
            )
        events.append(
            _event(
                dissolved=name,
                dissolved_type=row[2],
                successor=match.group("name"),
                successor_type=match.group("type"),
                effective=row[4],
                source_id=source_id,
                line=line_number,
                sgc=row[5],
            )
        )
    return events


def _parse_gaining_losing(
    data: bytes,
    source_id: str,
    *,
    skip: int,
    losing_code_column: int,
    losing_code_is_description: bool,
) -> list[dict]:
    """The 2016-2021 and 2025 gaining/losing column layout, Ontario rows only."""

    events: list[dict] = []
    rows = _rows(data)
    for line_number, row in enumerate(rows[skip + 1 :], start=skip + 2):
        if len(row) <= losing_code_column:
            continue
        losing_uid = row[5].strip()
        if not losing_uid.startswith("35"):
            continue
        code = row[losing_code_column].strip()
        is_dissolution = (
            "dissolution" in code.lower()
            if losing_code_is_description
            else code == DISSOLUTION_CODE
        )
        if not is_dissolution:
            continue
        events.append(
            _event(
                dissolved=row[6],
                dissolved_type=row[7],
                successor=row[1],
                successor_type=row[2],
                effective=row[-2],
                source_id=source_id,
                line=line_number,
                sgc=losing_uid,
            )
        )
    return events


def build() -> dict:
    events: list[dict] = []
    sources: list[dict] = []

    parsers = (
        ("statcan-il-2006-2011-t1", lambda d: _parse_legacy_alphabetical(d, "statcan-il-2006-2011-t1")),
        ("statcan-il-2011-2016-t1", lambda d: _parse_legacy_alphabetical(d, "statcan-il-2011-2016-t1")),
        (
            "statcan-il-2016-2021",
            lambda d: _parse_gaining_losing(
                d, "statcan-il-2016-2021", skip=2, losing_code_column=8,
                losing_code_is_description=False,
            ),
        ),
        (
            "statcan-il-2025",
            lambda d: _parse_gaining_losing(
                d, "statcan-il-2025", skip=0, losing_code_column=9,
                losing_code_is_description=True,
            ),
        ),
    )
    for source_id, parse in parsers:
        data, lock = _locked_bytes(source_id)
        found = parse(data)
        events.extend(found)
        sources.append(
            {
                "sourceId": source_id,
                "sha256": lock["sha256"],
                "reviewedBy": lock["reviewedBy"],
                "eventsFound": len(found),
            }
        )

    # The legacy tables state each event twice (alphabetical subject rows for
    # both directions); the same dissolution keyed by place and date is one
    # event. Nothing else may collide - identical keys with different
    # successors would mean the record disagrees with itself.
    deduped: dict[tuple[str, str], dict] = {}
    for event in events:
        key = (event["sgcCode"], event["effectiveDate"])
        existing = deduped.get(key)
        if existing is None:
            deduped[key] = event
        elif (existing["dissolved"], existing["successor"]) != (
            event["dissolved"],
            event["successor"],
        ):
            raise DissolutionBuildError(
                f"conflicting records for {key}: {existing} vs {event}"
            )

    ordered = sorted(
        deduped.values(), key=lambda e: (e["effectiveDate"], e["dissolved"])
    )
    return {
        "schemaVersion": "municipal-dissolutions-1.0.0",
        "jurisdiction": "CA-ON",
        "method": {
            "description": (
                "Every change-code-4 (dissolution) event in the hash-locked "
                "StatCan 92F0009X interim lists, parsed from the exact "
                "reviewed bytes. Editions before 2006 exist only as a locked "
                "PDF; that era stays hand-curated in the crosswalk."
            ),
            "coverageStart": "2006-01-02",
            "coverageEnd": "2025-01-01",
            "nonTaxingTypes": sorted(NON_TAXING_TYPES),
            "runtimeAiRequired": False,
        },
        "sources": sources,
        "events": ordered,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)

    artifact = build()
    payload = json.dumps(artifact, indent=2, ensure_ascii=False) + "\n"
    if args.check:
        current = OUTPUT.read_text(encoding="utf-8") if OUTPUT.is_file() else None
        if current != payload:
            print(
                "ERROR: municipal-dissolutions.json is stale; rerun "
                "scripts/build_municipal_dissolutions.py",
                file=sys.stderr,
            )
            return 1
        print(f"municipal dissolutions are fresh: {len(artifact['events'])} events")
        return 0
    OUTPUT.write_text(payload, encoding="utf-8", newline="\n")
    taxing = sum(1 for e in artifact["events"] if e["leviedPropertyTax"])
    print(
        f"wrote {OUTPUT.relative_to(ROOT)}: {len(artifact['events'])} events, "
        f"{taxing} of them taxing municipalities"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
