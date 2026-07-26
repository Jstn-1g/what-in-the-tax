"""Bounded, opt-in packets for unresolved evidence gaps.

This module does not call an AI service. It only creates deterministic queue
packets after non-AI adapters have failed and a human or rule-based process has
selected small, locatable excerpts.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Iterable

from .cache import CacheError, ContentAddressedSourceCache
from .models import canonical_sha256, require_canonical_id, require_sha256, require_source_id


class AIGapError(ValueError):
    """An AI gap packet was not explicitly authorized or exceeded its budget."""


@dataclass(frozen=True, slots=True)
class AIGapPolicy:
    enabled: bool = False
    allow_full_documents: bool = False
    max_excerpts: int = 3
    max_excerpt_chars: int = 1_600
    max_total_excerpt_chars: int = 4_800
    max_estimated_input_tokens: int = 2_000
    max_output_tokens: int = 500
    max_packets_per_run: int = 25
    max_run_estimated_input_tokens: int = 10_000
    max_run_output_tokens: int = 2_500
    input_rate_ceiling_microusd_per_million_tokens: int = 5_000_000
    output_rate_ceiling_microusd_per_million_tokens: int = 20_000_000
    max_run_cost_microusd: int = 100_000
    human_review_required: bool = True

    def __post_init__(self) -> None:
        limits = {
            "max_excerpts": self.max_excerpts,
            "max_excerpt_chars": self.max_excerpt_chars,
            "max_total_excerpt_chars": self.max_total_excerpt_chars,
            "max_estimated_input_tokens": self.max_estimated_input_tokens,
            "max_output_tokens": self.max_output_tokens,
            "max_packets_per_run": self.max_packets_per_run,
            "max_run_estimated_input_tokens": self.max_run_estimated_input_tokens,
            "max_run_output_tokens": self.max_run_output_tokens,
            "input_rate_ceiling_microusd_per_million_tokens": (
                self.input_rate_ceiling_microusd_per_million_tokens
            ),
            "output_rate_ceiling_microusd_per_million_tokens": (
                self.output_rate_ceiling_microusd_per_million_tokens
            ),
            "max_run_cost_microusd": self.max_run_cost_microusd,
        }
        for label, value in limits.items():
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise AIGapError(f"{label} must be a positive integer")
        if not self.human_review_required:
            raise AIGapError("human_review_required cannot be disabled")
        if self.allow_full_documents:
            raise AIGapError("allow_full_documents cannot be enabled")


@dataclass(frozen=True, slots=True)
class BoundedExcerpt:
    text: str
    locator: str
    document_char_count: int
    start_char: int
    end_char: int
    document_text_sha256: str

    def __post_init__(self) -> None:
        if not self.text.strip():
            raise AIGapError("excerpt text is required")
        if not self.locator.strip():
            raise AIGapError("excerpt locator is required")
        require_sha256(
            self.document_text_sha256,
            label="excerpt document_text_sha256",
        )
        for label, value in (
            ("document_char_count", self.document_char_count),
            ("start_char", self.start_char),
            ("end_char", self.end_char),
        ):
            if isinstance(value, bool) or not isinstance(value, int):
                raise AIGapError(f"{label} must be an integer")
        if self.start_char < 0 or self.end_char <= self.start_char:
            raise AIGapError("excerpt character offsets are invalid")
        if self.end_char > self.document_char_count:
            raise AIGapError("excerpt ends after the normalized document")
        if self.end_char - self.start_char != len(self.text):
            raise AIGapError("excerpt offsets do not match excerpt text length")

    @classmethod
    def from_document(
        cls,
        document_text: str,
        *,
        start_char: int,
        end_char: int,
        locator: str,
    ) -> "BoundedExcerpt":
        if not isinstance(document_text, str):
            raise AIGapError("normalized document text must be a string")
        if (
            isinstance(start_char, bool)
            or isinstance(end_char, bool)
            or not isinstance(start_char, int)
            or not isinstance(end_char, int)
            or start_char < 0
            or end_char <= start_char
            or end_char > len(document_text)
        ):
            raise AIGapError("excerpt character offsets are invalid")
        return cls(
            text=document_text[start_char:end_char],
            locator=locator,
            document_char_count=len(document_text),
            start_char=start_char,
            end_char=end_char,
            document_text_sha256=hashlib.sha256(
                document_text.encode("utf-8")
            ).hexdigest(),
        )


@dataclass(frozen=True, slots=True)
class DeterministicGap:
    gap_id: str
    entity_id: str
    gap_code: str
    requested_fields: tuple[str, ...]
    source_id: str
    source_sha256: str
    normalized_text_sha256: str
    deterministic_attempts: tuple[str, ...]

    def __post_init__(self) -> None:
        require_canonical_id(self.entity_id, label="gap entity_id")
        require_source_id(self.source_id)
        require_sha256(self.source_sha256, label="gap source_sha256")
        require_sha256(
            self.normalized_text_sha256,
            label="gap normalized_text_sha256",
        )
        if not self.gap_id or not self.gap_code:
            raise AIGapError("gap_id and gap_code are required")
        if not self.requested_fields:
            raise AIGapError("requested_fields must not be empty")
        if not self.deterministic_attempts:
            raise AIGapError("at least one deterministic attempt is required")


def estimated_token_ceiling(text: str) -> int:
    """Strict tokenizer-independent ceiling using UTF-8 byte count."""

    return len(text.encode("utf-8"))


def maximum_cost_microusd(
    input_tokens: int,
    output_tokens: int,
    policy: AIGapPolicy,
) -> int:
    """Price-ceiling cost using integer arithmetic and configured rate caps."""

    input_cost = (
        input_tokens
        * policy.input_rate_ceiling_microusd_per_million_tokens
        + 999_999
    ) // 1_000_000
    output_cost = (
        output_tokens
        * policy.output_rate_ceiling_microusd_per_million_tokens
        + 999_999
    ) // 1_000_000
    return input_cost + output_cost


def _covered_character_count(intervals: Iterable[tuple[int, int]]) -> int:
    """Return the size of the union of half-open character intervals."""

    ordered = sorted(intervals)
    if not ordered:
        return 0
    covered = 0
    current_start, current_end = ordered[0]
    for start, end in ordered[1:]:
        if start <= current_end:
            current_end = max(current_end, end)
            continue
        covered += current_end - current_start
        current_start, current_end = start, end
    return covered + current_end - current_start


def _resolve_locked_document(
    *,
    source_id: str,
    source_sha256: str,
    normalized_text_sha256: str,
    resolver: ContentAddressedSourceCache,
) -> str:
    if not isinstance(resolver, ContentAddressedSourceCache):
        raise AIGapError(
            "a content-addressed normalized-text lock resolver is required"
        )
    try:
        return resolver.resolve_normalized_text(
            source_id,
            source_sha256,
            normalized_text_sha256,
        )
    except (CacheError, ValueError) as exc:
        raise AIGapError(
            "normalized text is not bound to a verified locked source snapshot"
        ) from exc


def build_ai_gap_packet(
    gap: DeterministicGap,
    excerpts: Iterable[BoundedExcerpt],
    *,
    policy: AIGapPolicy,
    explicit_opt_in: bool,
    normalized_text_resolver: ContentAddressedSourceCache,
) -> dict[str, Any]:
    if not explicit_opt_in or not policy.enabled:
        raise AIGapError("AI gap queue requires both enabled policy and explicit opt-in")
    selected = list(excerpts)
    if not selected:
        raise AIGapError("AI gap packet requires at least one selected excerpt")
    if len(selected) > policy.max_excerpts:
        raise AIGapError(f"excerpt count exceeds policy limit {policy.max_excerpts}")
    normalized_document = _resolve_locked_document(
        source_id=gap.source_id,
        source_sha256=gap.source_sha256,
        normalized_text_sha256=gap.normalized_text_sha256,
        resolver=normalized_text_resolver,
    )
    intervals: list[tuple[int, int]] = []
    for excerpt in selected:
        if excerpt.document_text_sha256 != gap.normalized_text_sha256:
            raise AIGapError(
                "excerpt normalized-document hash differs from the locked gap text"
            )
        if len(excerpt.text) > policy.max_excerpt_chars:
            raise AIGapError(
                f"excerpt exceeds policy limit {policy.max_excerpt_chars} characters"
            )
        if excerpt.document_char_count != len(normalized_document):
            raise AIGapError("excerpt document length differs from locked normalized text")
        if (
            normalized_document[excerpt.start_char : excerpt.end_char]
            != excerpt.text
        ):
            raise AIGapError("excerpt does not match the locked normalized text")
        intervals.append((excerpt.start_char, excerpt.end_char))
    if _covered_character_count(intervals) >= len(normalized_document):
        raise AIGapError("full-document AI input is disabled, including split excerpts")
    total_chars = sum(len(excerpt.text) for excerpt in selected)
    if total_chars > policy.max_total_excerpt_chars:
        raise AIGapError(
            f"total excerpt text exceeds policy limit {policy.max_total_excerpt_chars}"
        )

    input_text = "\n".join(excerpt.text for excerpt in selected)
    estimated_tokens = estimated_token_ceiling(input_text)
    if estimated_tokens > policy.max_estimated_input_tokens:
        raise AIGapError(
            "estimated input tokens exceed policy limit "
            f"{policy.max_estimated_input_tokens}"
        )
    core: dict[str, Any] = {
        "schemaVersion": "auditback-ai-gap-packet-1.0.0",
        "gapId": gap.gap_id,
        "entityId": gap.entity_id,
        "gapCode": gap.gap_code,
        "requestedFields": list(gap.requested_fields),
        "source": {
            "sourceId": gap.source_id,
            "snapshotSha256": gap.source_sha256,
            "normalizedTextSha256": gap.normalized_text_sha256,
        },
        "deterministicAttempts": list(gap.deterministic_attempts),
        "excerpts": [
            {
                "locator": excerpt.locator,
                "text": excerpt.text,
                "excerptChars": len(excerpt.text),
                "documentChars": excerpt.document_char_count,
                "startChar": excerpt.start_char,
                "endChar": excerpt.end_char,
                "documentTextSha256": excerpt.document_text_sha256,
                "excerptTextSha256": hashlib.sha256(
                    excerpt.text.encode("utf-8")
                ).hexdigest(),
                "isFullDocument": False,
            }
            for excerpt in selected
        ],
        "budget": {
            "estimatedInputTokensCeiling": estimated_tokens,
            "maxOutputTokens": policy.max_output_tokens,
        },
        "publication": {
            "mayAutoPublish": False,
            "humanReviewRequired": policy.human_review_required,
        },
    }
    maximum_cost = maximum_cost_microusd(
        estimated_tokens,
        policy.max_output_tokens,
        policy,
    )
    core["budget"]["maximumCostMicrousd"] = maximum_cost
    core["packetCanonicalSha256"] = canonical_sha256(core)
    return core


def build_ai_gap_queue(
    packets: Iterable[dict[str, Any]],
    *,
    policy: AIGapPolicy,
    normalized_text_resolver: ContentAddressedSourceCache,
) -> dict[str, Any]:
    if not policy.enabled:
        raise AIGapError("AI gap queue cannot be assembled while policy is disabled")
    provided = list(packets)
    if any(not isinstance(item, dict) for item in provided):
        raise AIGapError("every AI gap packet must be an object")
    rows = sorted(
        provided,
        key=lambda item: item.get("packetCanonicalSha256", ""),
    )
    if len(rows) > policy.max_packets_per_run:
        raise AIGapError(
            f"packet count exceeds per-run limit {policy.max_packets_per_run}"
        )
    total_input_tokens = 0
    total_output_tokens = 0
    total_cost_microusd = 0
    for item in rows:
        if item.get("schemaVersion") != "auditback-ai-gap-packet-1.0.0":
            raise AIGapError("AI gap queue contains an unsupported packet schema")
        claimed_hash = item.get("packetCanonicalSha256")
        without_hash = {
            key: value
            for key, value in item.items()
            if key != "packetCanonicalSha256"
        }
        if claimed_hash != canonical_sha256(without_hash):
            raise AIGapError("AI gap packet canonical hash does not match its content")
        excerpts = item.get("excerpts")
        if not isinstance(excerpts, list) or not excerpts:
            raise AIGapError("AI gap packet must contain bounded excerpts")
        if len(excerpts) > policy.max_excerpts:
            raise AIGapError("AI gap packet exceeds excerpt-count policy")
        total_chars = 0
        excerpt_texts: list[str] = []
        source = item.get("source")
        if not isinstance(source, dict):
            raise AIGapError("AI gap packet source binding is missing")
        source_id = source.get("sourceId")
        source_sha256 = source.get("snapshotSha256")
        normalized_text_sha256 = source.get("normalizedTextSha256")
        try:
            require_source_id(source_id)
            require_sha256(source_sha256, label="packet snapshotSha256")
            require_sha256(
                normalized_text_sha256,
                label="packet normalizedTextSha256",
            )
        except ValueError as exc:
            raise AIGapError(str(exc)) from exc
        normalized_document = _resolve_locked_document(
            source_id=source_id,
            source_sha256=source_sha256,
            normalized_text_sha256=normalized_text_sha256,
            resolver=normalized_text_resolver,
        )
        intervals: list[tuple[int, int]] = []
        for excerpt in excerpts:
            if not isinstance(excerpt, dict) or not isinstance(excerpt.get("text"), str):
                raise AIGapError("AI gap packet contains an invalid excerpt")
            if excerpt.get("isFullDocument") is not False:
                raise AIGapError("AI gap queue refuses full-document packets")
            excerpt_chars = len(excerpt["text"])
            if excerpt_chars > policy.max_excerpt_chars:
                raise AIGapError("AI gap packet exceeds excerpt-length policy")
            start_char = excerpt.get("startChar")
            end_char = excerpt.get("endChar")
            document_chars = excerpt.get("documentChars")
            if any(
                isinstance(value, bool) or not isinstance(value, int)
                for value in (start_char, end_char, document_chars)
            ):
                raise AIGapError("AI gap packet contains invalid excerpt offsets")
            if (
                start_char < 0
                or end_char <= start_char
                or end_char > document_chars
                or end_char - start_char != excerpt_chars
            ):
                raise AIGapError("AI gap packet excerpt offsets do not match text")
            if document_chars != len(normalized_document):
                raise AIGapError("AI gap packet document character count is invalid")
            if normalized_document[start_char:end_char] != excerpt["text"]:
                raise AIGapError(
                    "AI gap packet excerpt does not match the locked normalized text"
                )
            if (
                not policy.allow_full_documents
                and start_char == 0
                and end_char == document_chars
            ):
                raise AIGapError("AI gap queue refuses full-document packets")
            if (
                excerpt.get("documentTextSha256") != normalized_text_sha256
                or excerpt.get("excerptTextSha256")
                != hashlib.sha256(excerpt["text"].encode("utf-8")).hexdigest()
            ):
                raise AIGapError("AI gap packet excerpt hash binding is invalid")
            if excerpt.get("excerptChars") != excerpt_chars:
                raise AIGapError("AI gap packet excerpt character count is invalid")
            total_chars += excerpt_chars
            excerpt_texts.append(excerpt["text"])
            intervals.append((start_char, end_char))
        if _covered_character_count(intervals) >= len(normalized_document):
            raise AIGapError(
                "AI gap queue refuses full-document packets, including split excerpts"
            )
        if total_chars > policy.max_total_excerpt_chars:
            raise AIGapError("AI gap packet exceeds total excerpt policy")
        publication = item.get("publication")
        if (
            not isinstance(publication, dict)
            or publication.get("mayAutoPublish") is not False
            or publication.get("humanReviewRequired") is not True
        ):
            raise AIGapError("AI gap packet must require review and forbid auto-publication")
        budget = item.get("budget")
        if not isinstance(budget, dict):
            raise AIGapError("AI gap packet budget is missing")
        recomputed_input_tokens = estimated_token_ceiling("\n".join(excerpt_texts))
        claimed_input_tokens = budget.get("estimatedInputTokensCeiling")
        output_tokens = budget.get("maxOutputTokens")
        if (
            isinstance(claimed_input_tokens, bool)
            or not isinstance(claimed_input_tokens, int)
            or claimed_input_tokens < 1
            or claimed_input_tokens != recomputed_input_tokens
            or claimed_input_tokens > policy.max_estimated_input_tokens
            or isinstance(output_tokens, bool)
            or not isinstance(output_tokens, int)
            or output_tokens < 1
            or output_tokens > policy.max_output_tokens
        ):
            raise AIGapError("AI gap packet token budget is invalid")
        recomputed_cost = maximum_cost_microusd(
            recomputed_input_tokens,
            output_tokens,
            policy,
        )
        if budget.get("maximumCostMicrousd") != recomputed_cost:
            raise AIGapError("AI gap packet cost ceiling is invalid")
        total_input_tokens += recomputed_input_tokens
        total_output_tokens += output_tokens
        total_cost_microusd += recomputed_cost
    packet_ids = [item.get("packetCanonicalSha256") for item in rows]
    if any(not isinstance(item, str) for item in packet_ids):
        raise AIGapError("every packet must have a canonical hash")
    if len(packet_ids) != len(set(packet_ids)):
        raise AIGapError("AI gap queue contains duplicate packets")
    if total_input_tokens > policy.max_run_estimated_input_tokens:
        raise AIGapError("AI gap queue exceeds aggregate input-token policy")
    if total_output_tokens > policy.max_run_output_tokens:
        raise AIGapError("AI gap queue exceeds aggregate output-token policy")
    if total_cost_microusd > policy.max_run_cost_microusd:
        raise AIGapError("AI gap queue exceeds aggregate cost policy")
    queue: dict[str, Any] = {
        "schemaVersion": "auditback-ai-gap-queue-1.0.0",
        "enabled": policy.enabled,
        "invokesModel": False,
        "packetCount": len(rows),
        "budget": {
            "estimatedInputTokensCeiling": total_input_tokens,
            "maxOutputTokens": total_output_tokens,
            "maximumCostMicrousd": total_cost_microusd,
            "runInputTokenLimit": policy.max_run_estimated_input_tokens,
            "runOutputTokenLimit": policy.max_run_output_tokens,
            "runCostLimitMicrousd": policy.max_run_cost_microusd,
        },
        "packets": rows,
    }
    queue["queueCanonicalSha256"] = canonical_sha256(queue)
    return queue
