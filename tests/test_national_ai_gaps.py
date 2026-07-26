from __future__ import annotations

import hashlib
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from national.ai_gaps import (
    AIGapError,
    AIGapPolicy,
    BoundedExcerpt,
    DeterministicGap,
    build_ai_gap_packet,
    build_ai_gap_queue,
    estimated_token_ceiling,
    maximum_cost_microusd,
)
from national.cache import ContentAddressedSourceCache
from national.models import canonical_sha256


class NationalAIGapTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.cache = ContentAddressedSourceCache(Path(self.temporary.name))
        self.source_payload = b"%PDF-locked-official-source"
        self.source_snapshot = self.cache.store(
            source_id="oshawa-2026-tax-bylaw",
            payload=self.source_payload,
            media_type="application/pdf",
            request_url="https://www.oshawa.ca/tax-bylaw.pdf",
        )
        self.excerpt_text = "Residential tax class | General rate | 0.012345"
        self.document = (
            "Official by-law heading\n"
            + self.excerpt_text
            + "\nCertification and signatures"
        )
        self._lock_document(self.document)
        start = self.document.index(self.excerpt_text)
        self.excerpt = BoundedExcerpt.from_document(
            self.document,
            start_char=start,
            end_char=start + len(self.excerpt_text),
            locator="page 4, table 2, row Residential",
        )
        self.gap = self._gap_for(self.document)

    def _lock_document(self, document: str) -> None:
        self.cache.store_normalized_text(
            source_snapshot=self.source_snapshot,
            normalized_text=document,
            normalizer_id="auditback-pdf-text",
            normalizer_version="1.0.0",
        )

    def _gap_for(self, document: str, *, gap_id: str = "oshawa-2026-tax-rate") -> DeterministicGap:
        return DeterministicGap(
            gap_id=gap_id,
            entity_id="ca:gov:on:municipal:3518013",
            gap_code="table-layout-not-supported",
            requested_fields=("residentialTaxRate",),
            source_id=self.source_snapshot.source_id,
            source_sha256=self.source_snapshot.sha256,
            normalized_text_sha256=hashlib.sha256(
                document.encode("utf-8")
            ).hexdigest(),
            deterministic_attempts=(
                "structured API lookup: no endpoint published",
                "PDF table parser: merged header cells unsupported",
            ),
        )

    def _packet(
        self,
        gap: DeterministicGap | None = None,
        excerpts: list[BoundedExcerpt] | None = None,
        policy: AIGapPolicy | None = None,
    ) -> dict:
        return build_ai_gap_packet(
            gap or self.gap,
            excerpts or [self.excerpt],
            policy=policy or AIGapPolicy(enabled=True),
            explicit_opt_in=True,
            normalized_text_resolver=self.cache,
        )

    @staticmethod
    def _excerpt_dict(excerpt: BoundedExcerpt) -> dict:
        return {
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

    def test_ai_is_disabled_without_double_opt_in(self) -> None:
        with self.assertRaisesRegex(AIGapError, "explicit opt-in"):
            build_ai_gap_packet(
                self.gap,
                [self.excerpt],
                policy=AIGapPolicy(),
                explicit_opt_in=True,
                normalized_text_resolver=self.cache,
            )
        with self.assertRaisesRegex(AIGapError, "explicit opt-in"):
            build_ai_gap_packet(
                self.gap,
                [self.excerpt],
                policy=AIGapPolicy(enabled=True),
                explicit_opt_in=False,
                normalized_text_resolver=self.cache,
            )

    def test_packet_is_bounded_deterministic_and_cannot_auto_publish(self) -> None:
        policy = AIGapPolicy(enabled=True)
        first = self._packet(policy=policy)
        second = self._packet(policy=policy)

        self.assertEqual(first, second)
        self.assertFalse(first["excerpts"][0]["isFullDocument"])
        self.assertFalse(first["publication"]["mayAutoPublish"])
        self.assertTrue(first["publication"]["humanReviewRequired"])
        queue = build_ai_gap_queue(
            [first],
            policy=policy,
            normalized_text_resolver=self.cache,
        )
        self.assertEqual(
            first["budget"]["maximumCostMicrousd"],
            queue["budget"]["maximumCostMicrousd"],
        )

    def test_full_document_is_rejected(self) -> None:
        document = "This is the whole document."
        self._lock_document(document)
        whole_document = BoundedExcerpt.from_document(
            document,
            start_char=0,
            end_char=len(document),
            locator="entire document",
        )
        with self.assertRaisesRegex(AIGapError, "full-document"):
            self._packet(self._gap_for(document), [whole_document])
        with self.assertRaisesRegex(AIGapError, "cannot be enabled"):
            AIGapPolicy(enabled=True, allow_full_documents=True)

    def test_split_excerpts_cannot_cover_the_whole_document_at_construction(self) -> None:
        document = "0123456789abcdefghij"
        self._lock_document(document)
        first = BoundedExcerpt.from_document(
            document,
            start_char=0,
            end_char=10,
            locator="first half",
        )
        second = BoundedExcerpt.from_document(
            document,
            start_char=10,
            end_char=len(document),
            locator="second half",
        )
        with self.assertRaisesRegex(AIGapError, "including split excerpts"):
            self._packet(self._gap_for(document), [first, second])

    def test_queue_rejects_rehashed_split_document_bypass(self) -> None:
        policy = AIGapPolicy(enabled=True)
        packet = self._packet(policy=policy)
        midpoint = len(self.document) // 2
        excerpts = [
            BoundedExcerpt.from_document(
                self.document,
                start_char=0,
                end_char=midpoint,
                locator="first split",
            ),
            BoundedExcerpt.from_document(
                self.document,
                start_char=midpoint,
                end_char=len(self.document),
                locator="second split",
            ),
        ]
        excerpt_rows = [self._excerpt_dict(excerpt) for excerpt in excerpts]
        input_tokens = estimated_token_ceiling(
            "\n".join(excerpt.text for excerpt in excerpts)
        )
        changed = {
            **packet,
            "excerpts": excerpt_rows,
            "budget": {
                "estimatedInputTokensCeiling": input_tokens,
                "maxOutputTokens": policy.max_output_tokens,
                "maximumCostMicrousd": maximum_cost_microusd(
                    input_tokens,
                    policy.max_output_tokens,
                    policy,
                ),
            },
        }
        changed["packetCanonicalSha256"] = canonical_sha256(
            {
                key: value
                for key, value in changed.items()
                if key != "packetCanonicalSha256"
            }
        )
        with self.assertRaisesRegex(AIGapError, "including split excerpts"):
            build_ai_gap_queue(
                [changed],
                policy=policy,
                normalized_text_resolver=self.cache,
            )

    def test_excerpt_and_queue_budgets_fail_closed(self) -> None:
        document = "x" * 200
        self._lock_document(document)
        long_excerpt = BoundedExcerpt.from_document(
            document,
            start_char=0,
            end_char=101,
            locator="page 1",
        )
        with self.assertRaisesRegex(AIGapError, "excerpt exceeds"):
            self._packet(
                self._gap_for(document),
                [long_excerpt],
                AIGapPolicy(enabled=True, max_excerpt_chars=100),
            )

        packet = self._packet()
        with self.assertRaisesRegex(AIGapError, "per-run limit"):
            build_ai_gap_queue(
                [packet, {**packet, "packetCanonicalSha256": "b" * 64}],
                policy=AIGapPolicy(enabled=True, max_packets_per_run=1),
                normalized_text_resolver=self.cache,
            )

    def test_queue_recomputes_claimed_and_aggregate_budgets(self) -> None:
        policy = AIGapPolicy(enabled=True)
        packet = self._packet(policy=policy)
        tampered = {
            **packet,
            "budget": {
                **packet["budget"],
                "estimatedInputTokensCeiling": -1,
            },
        }
        tampered["packetCanonicalSha256"] = canonical_sha256(
            {
                key: value
                for key, value in tampered.items()
                if key != "packetCanonicalSha256"
            }
        )
        with self.assertRaisesRegex(AIGapError, "token budget is invalid"):
            build_ai_gap_queue(
                [tampered],
                policy=policy,
                normalized_text_resolver=self.cache,
            )

    def test_queue_verifies_excerpt_against_locked_normalized_document(self) -> None:
        policy = AIGapPolicy(enabled=True)
        packet = self._packet(policy=policy)
        changed_text = "X" + packet["excerpts"][0]["text"][1:]
        tampered = {
            **packet,
            "excerpts": [
                {
                    **packet["excerpts"][0],
                    "text": changed_text,
                    "excerptTextSha256": hashlib.sha256(
                        changed_text.encode("utf-8")
                    ).hexdigest(),
                }
            ],
        }
        tampered["packetCanonicalSha256"] = canonical_sha256(
            {
                key: value
                for key, value in tampered.items()
                if key != "packetCanonicalSha256"
            }
        )
        with self.assertRaisesRegex(AIGapError, "locked normalized text"):
            build_ai_gap_queue(
                [tampered],
                policy=policy,
                normalized_text_resolver=self.cache,
            )

        second_packet = self._packet(
            replace(self.gap, gap_id="oshawa-2026-tax-rate-second-check"),
            policy=policy,
        )
        with self.assertRaisesRegex(AIGapError, "aggregate output-token"):
            build_ai_gap_queue(
                [packet, second_packet],
                policy=replace(policy, max_run_output_tokens=500),
                normalized_text_resolver=self.cache,
            )

    def test_queue_rejects_fabricated_source_identity_after_rehash(self) -> None:
        policy = AIGapPolicy(enabled=True)
        packet = self._packet(policy=policy)
        for source_change in (
            {"sourceId": "fabricated-source"},
            {"snapshotSha256": "b" * 64},
        ):
            with self.subTest(source_change=source_change):
                changed = {
                    **packet,
                    "source": {**packet["source"], **source_change},
                }
                changed["packetCanonicalSha256"] = canonical_sha256(
                    {
                        key: value
                        for key, value in changed.items()
                        if key != "packetCanonicalSha256"
                    }
                )
                with self.assertRaisesRegex(AIGapError, "verified locked source"):
                    build_ai_gap_queue(
                        [changed],
                        policy=policy,
                        normalized_text_resolver=self.cache,
                    )

    def test_queue_revalidates_packet_content(self) -> None:
        policy = AIGapPolicy(enabled=True)
        packet = self._packet(policy=policy)
        tampered = {
            **packet,
            "publication": {
                "mayAutoPublish": True,
                "humanReviewRequired": False,
            },
        }
        with self.assertRaisesRegex(AIGapError, "canonical hash"):
            build_ai_gap_queue(
                [tampered],
                policy=policy,
                normalized_text_resolver=self.cache,
            )

    def test_policy_cannot_disable_human_review(self) -> None:
        with self.assertRaisesRegex(AIGapError, "cannot be disabled"):
            AIGapPolicy(enabled=True, human_review_required=False)


if __name__ == "__main__":
    unittest.main()
