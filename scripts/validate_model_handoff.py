#!/usr/bin/env python3
"""Validate one provider-neutral candidate without network or canonical writes."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from national.model_handoff import (  # noqa: E402
    ModelHandoffError,
    validate_handoff_files,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Validate an untrusted municipal evidence candidate against one "
            "hash-bound job. Makes no network requests and writes no data."
        )
    )
    parser.add_argument("--job", required=True, type=Path)
    parser.add_argument("--candidate", required=True, type=Path)
    parser.add_argument(
        "--packet",
        type=Path,
        help="Required manifest-pinned packet for extract-candidates jobs.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = validate_handoff_files(
            args.job,
            args.candidate,
            args.packet,
        )
    except ModelHandoffError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2
    print(
        json.dumps(
            result,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
