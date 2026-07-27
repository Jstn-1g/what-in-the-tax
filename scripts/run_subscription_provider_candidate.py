"""Dry-run a bounded provider handoff or execute one Claude subscription turn.

The default is a no-model dry run. Live use requires both --execute and
--confirm-subscription-usage. No API credential is accepted, and live output is
written only to stdout as an unverified candidate JSON object.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from national.model_handoff import load_strict_json  # noqa: E402
from national.models import canonical_json_bytes  # noqa: E402
from national.subscription_provider_runner import (  # noqa: E402
    ALLOWED_MODELS,
    DEFAULT_TIMEOUT_SECONDS,
    SubscriptionProviderError,
    run_subscription_provider,
)


def _object(path: Path, *, label: str) -> dict[str, Any]:
    value = load_strict_json(path)
    if not isinstance(value, dict):
        raise SubscriptionProviderError(f"{label} must be a JSON object")
    return value


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Prepare or run one source-only municipal evidence classification "
            "through a saved local subscription. Claude is the only automatic "
            "live route; Antigravity is dry-run/manual only. Dry-run is the "
            "default; API credentials and CI are refused."
        )
    )
    parser.add_argument("--job", required=True, type=Path)
    parser.add_argument("--packet", required=True, type=Path)
    parser.add_argument("--provider", required=True, choices=("agy", "claude"))
    parser.add_argument(
        "--model",
        help=(
            "Pinned subscription model. Omit for the economical reviewed "
            "default for the selected provider."
        ),
    )
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=DEFAULT_TIMEOUT_SECONDS,
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Consume subscription usage for exactly one non-retried turn.",
    )
    parser.add_argument(
        "--confirm-subscription-usage",
        action="store_true",
        help="Second explicit live-use confirmation; required with --execute.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.model is not None and args.model not in ALLOWED_MODELS[args.provider]:
            allowed = ", ".join(sorted(ALLOWED_MODELS[args.provider]))
            raise SubscriptionProviderError(
                f"--model must be one of the reviewed {args.provider} models: "
                f"{allowed}"
            )
        result = run_subscription_provider(
            _object(args.job, label="job"),
            _object(args.packet, label="prefetched packet"),
            provider=args.provider,
            model=args.model,
            execute=args.execute,
            confirm_subscription_usage=args.confirm_subscription_usage,
            timeout_seconds=args.timeout_seconds,
        )
        sys.stdout.buffer.write(canonical_json_bytes(result) + b"\n")
        return 0
    except SubscriptionProviderError as exc:
        print(f"subscription provider run refused: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
