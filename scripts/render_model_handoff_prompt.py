#!/usr/bin/env python3
"""Render one complete, provider-neutral prompt to stdout."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from national.model_handoff import (  # noqa: E402
    CANDIDATE_SCHEMA_PATH,
    ModelHandoffError,
    load_strict_json,
    validate_job,
)


INSTRUCTION_PATH = ROOT / "handoffs" / "PROMPT.md"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Render a bounded municipal evidence prompt. Makes no network "
            "requests, invokes no model, and writes no data."
        )
    )
    parser.add_argument("--job", required=True, type=Path)
    parser.add_argument(
        "--packet",
        type=Path,
        help="Required manifest-pinned packet for extract-candidates jobs.",
    )
    return parser


def render_prompt(job_path: Path, packet_path: Path | None = None) -> str:
    job = validate_job(load_strict_json(job_path))
    schema = load_strict_json(CANDIDATE_SCHEMA_PATH)
    instruction = INSTRUCTION_PATH.read_text(encoding="utf-8").strip()
    sections = [
        instruction,
        "## JOB_JSON\n\n"
        + json.dumps(
            job,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ),
    ]
    if job["taskType"] == "extract-candidates":
        if packet_path is None:
            raise ModelHandoffError(
                "extract-candidates prompt rendering requires --packet"
            )
        from national.subscription_provider_runner import (  # noqa: E402
            validate_prefetched_packet,
        )

        packet = validate_prefetched_packet(
            job,
            load_strict_json(packet_path),
            require_trusted=True,
        )
        sections.append(
            "## PREFETCHED_PACKET_JSON\n\n"
            + json.dumps(
                packet,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
        )
    elif packet_path is not None:
        raise ModelHandoffError(
            "discover-sources prompt rendering does not accept --packet"
        )
    sections.append(
        "## OUTPUT_SCHEMA_JSON\n\n"
        + json.dumps(
            schema,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    prompt = "\n\n".join(sections) + "\n"
    prompt_bytes = len(prompt.encode("utf-8"))
    limit = int(job["budget"]["maxPromptUtf8Bytes"])
    if prompt_bytes > limit:
        raise ModelHandoffError(
            f"rendered prompt is {prompt_bytes} UTF-8 bytes; job limit is {limit}"
        )
    return prompt


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        prompt = render_prompt(args.job, args.packet)
    except (ModelHandoffError, OSError) as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2
    sys.stdout.write(prompt)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
