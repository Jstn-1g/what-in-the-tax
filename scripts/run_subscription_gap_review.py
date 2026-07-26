"""Prepare or run one local ChatGPT-subscription evidence-gap review.

The default is a no-model dry run.  A live run requires both --execute and
--confirm-subscription-usage, a checked-in enabled policy, a source-bound queue,
and one exact packet hash.  It never accepts or creates an API key.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from national.cache import ContentAddressedSourceCache  # noqa: E402
from national.models import canonical_json_bytes  # noqa: E402
from national.subscription_worker import (  # noqa: E402
    ALLOWED_MODELS,
    DEFAULT_MODEL,
    SubscriptionRunFailure,
    SubscriptionWorkerError,
    assert_local_operator_environment,
    authorize_subscription_packet,
    claim_subscription_attempt,
    finish_subscription_attempt,
    load_strict_json,
    persist_subscription_candidate,
    run_subscription_packet,
)


def _object(path: Path, *, label: str) -> dict[str, Any]:
    value = load_strict_json(path)
    if not isinstance(value, dict):
        raise SubscriptionWorkerError(f"{label} must be a JSON object")
    return value


def _observed_usage(candidate: dict[str, Any]) -> dict[str, int]:
    usage = candidate.get("subscriptionUsage")
    if not isinstance(usage, dict):
        raise SubscriptionWorkerError(
            "verified candidate has no observable subscription usage"
        )
    keys = (
        "inputTokens",
        "cachedInputTokens",
        "outputTokens",
        "totalTokens",
    )
    return {key: usage[key] for key in keys}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Dry-run or process one bounded evidence packet using the local "
            "ChatGPT/Codex subscription. No API key or API billing is allowed."
        )
    )
    parser.add_argument("--queue", required=True, type=Path)
    parser.add_argument(
        "--packet-sha256",
        required=True,
        help="Exact packetCanonicalSha256 to select; only one packet is processed.",
    )
    parser.add_argument(
        "--source-cache",
        required=True,
        type=Path,
        help="Content-addressed cache containing the queue's locked normalized text.",
    )
    parser.add_argument(
        "--model",
        choices=sorted(ALLOWED_MODELS),
        default=DEFAULT_MODEL,
        help=(
            "Subscription model. The economical first lane is gpt-5.4-mini; "
            "gpt-5.6-luna is the manual escalation lane."
        ),
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Consume ChatGPT subscription usage for this one selected packet.",
    )
    parser.add_argument(
        "--confirm-subscription-usage",
        action="store_true",
        help="Second live-run opt-in; required with --execute.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.confirm_subscription_usage and not args.execute:
            raise SubscriptionWorkerError(
                "--confirm-subscription-usage is meaningful only with --execute"
            )
        if args.execute and not args.confirm_subscription_usage:
            raise SubscriptionWorkerError(
                "--execute requires --confirm-subscription-usage"
            )
        queue_document = _object(args.queue, label="AI-gap queue")
        authorization = authorize_subscription_packet(
            queue_document,
            args.packet_sha256,
            normalized_text_resolver=ContentAddressedSourceCache(
                args.source_cache
            ),
        )
        packet = authorization.packet
        dry_run = run_subscription_packet(
            authorization,
            execute=False,
            model=args.model,
        )
        if not args.execute:
            sys.stdout.buffer.write(canonical_json_bytes(dry_run) + b"\n")
            return 0

        assert_local_operator_environment()
        attempt = claim_subscription_attempt(
            authorization,
            model=args.model,
        )
        result: dict[str, Any] | None = None
        try:
            result = run_subscription_packet(
                attempt,
                execute=True,
                confirm_subscription_usage=args.confirm_subscription_usage,
                model=args.model,
            )
            destination = persist_subscription_candidate(attempt, result)
            finish_subscription_attempt(
                attempt,
                status="completed",
                candidate=result,
                observed_usage=_observed_usage(result),
            )
            summary = {
                "completed": True,
                "apiKeyUsed": False,
                "apiBillingUsed": False,
                "authMode": "chatgpt-subscription",
                "packetCanonicalSha256": packet["packetCanonicalSha256"],
                "candidatePath": str(destination),
                "attemptCanonicalSha256": (
                    attempt.attempt_canonical_sha256
                ),
                "publicationStatus": "pending-human-review",
            }
            sys.stdout.buffer.write(canonical_json_bytes(summary) + b"\n")
            return 0
        except SubscriptionRunFailure as exc:
            finish_subscription_attempt(
                attempt,
                status="failed",
                failure_code=exc.failure_code,
                observed_usage=exc.observed_usage,
            )
            raise
        except SubscriptionWorkerError:
            observed_usage = (
                _observed_usage(result)
                if result is not None
                else None
            )
            finish_subscription_attempt(
                attempt,
                status="failed",
                failure_code=(
                    "post-turn-local-persistence-failed"
                    if observed_usage is not None
                    else "subscription-worker-refused"
                ),
                observed_usage=observed_usage,
            )
            raise
    except SubscriptionWorkerError as exc:
        print(f"subscription review refused: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
