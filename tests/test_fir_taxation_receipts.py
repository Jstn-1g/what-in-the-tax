"""What the Schedule 26A builder refuses, and why.

The education-rate gate refuses nobody on today's data, which is the point of
adding it now - it costs nothing and catches the year a filing goes wrong. But
a gate that has never refused anything has not been shown to work, so every
refusal path here is exercised against a planted defect rather than trusted.

The upper-tier case is tested for its *wording* as well as its behaviour. An
upper tier has no residential levy because it does not levy on assessment
directly, not because its filing is incomplete, and a receipt that reports the
first as the second would be telling a reader something false about how their
municipality is governed.
"""

from __future__ import annotations

import json
import os
import unittest
from unittest.mock import patch

from scripts.build_fir_taxation_receipts import (
    EDUCATION_RATE_EXPECTED,
    EDUCATION_RATE_TOLERANCE,
    build_receipt,
    render_json,
    resolve_built_at,
)

CVA = 1_000_000_000.0
LOWER = 3_000_000.0
UPPER = 5_000_000.0


def entry(
    *,
    tier: str = "LT",
    education_rate: float = EDUCATION_RATE_EXPECTED,
    total_override: float | None = None,
    residential: bool = True,
    include_education: bool = True,
) -> dict:
    """A coherent filing, with exactly one thing wrong when asked for."""
    education = CVA * education_rate
    classes: dict[str, dict[str, float]] = {}
    if residential:
        row = {
            "16": CVA,
            "02": CVA,
            "04": LOWER,
            "05": UPPER,
            "03": total_override
            if total_override is not None
            else LOWER + UPPER + education,
        }
        if include_education:
            row["06"] = education
        classes["0010"] = row
    return {
        "assessmentCode": "9999",
        "classes": classes,
        "name": "Example Tp",
        "tier": tier,
        "sgcCode": "3599999",
    }


def build(**kwargs):
    return build_receipt("2024", entry(**kwargs), "a" * 64, "b" * 64, "fir.zip", None)


class TaxationReceiptGates(unittest.TestCase):
    def test_a_clean_filing_is_receipted_with_its_shares(self) -> None:
        receipt, reason = build()
        self.assertIsNone(reason)
        assert receipt is not None
        res = receipt["residential"]
        self.assertEqual(res["taxableAssessmentCvaCad"], CVA)
        self.assertEqual(res["municipalLowerOrSingleTierCad"], LOWER)
        self.assertEqual(res["municipalUpperTierCad"], UPPER)
        # Shares are of the printed total, and they account for all of it.
        self.assertAlmostEqual(sum(res["shares"].values()), 1.0, places=5)
        self.assertAlmostEqual(res["educationRate"], EDUCATION_RATE_EXPECTED, places=8)

    def test_education_rate_outside_the_provincial_constant_is_refused(self) -> None:
        # The one check that is not self-referential: the province sets this
        # rate, so missing it means the filing disagrees with something its
        # author does not control.
        receipt, reason = build(education_rate=EDUCATION_RATE_EXPECTED * 1.5)
        self.assertIsNone(receipt)
        assert reason is not None
        self.assertIn("education rate", reason)
        self.assertIn("province-wide", reason)

    def test_the_gate_names_the_rate_it_saw(self) -> None:
        # A refusal a human cannot act on is barely better than a silent drop.
        _, reason = build(education_rate=0.002)
        assert reason is not None
        self.assertIn("0.2000%", reason)

    def test_a_filing_just_inside_the_tolerance_is_kept(self) -> None:
        receipt, reason = build(
            education_rate=EDUCATION_RATE_EXPECTED + EDUCATION_RATE_TOLERANCE * 0.8
        )
        self.assertIsNone(reason)
        self.assertIsNotNone(receipt)

    def test_a_filing_just_outside_the_tolerance_is_refused(self) -> None:
        receipt, reason = build(
            education_rate=EDUCATION_RATE_EXPECTED + EDUCATION_RATE_TOLERANCE * 1.2
        )
        self.assertIsNone(receipt)
        self.assertIsNotNone(reason)

    def test_parts_that_disagree_with_the_printed_total_are_refused(self) -> None:
        # Fail hard on integrity. A published total that is not the sum of its
        # published parts is the single worst thing this project could emit.
        receipt, reason = build(total_override=LOWER + UPPER + 1_530_000.0 + 5_000.0)
        self.assertIsNone(receipt)
        assert reason is not None
        self.assertIn("parts sum to", reason)
        self.assertIn("Residential", reason)

    def test_a_one_cent_disagreement_is_tolerated(self) -> None:
        # FIR amounts are whole dollars; refusing on rounding would refuse
        # honest filings and teach everyone to ignore the gate.
        receipt, reason = build(total_override=LOWER + UPPER + 1_530_000.0 + 0.01)
        self.assertIsNone(reason)
        self.assertIsNotNone(receipt)

    def test_an_upper_tier_is_not_receipted_and_is_not_called_incomplete(self) -> None:
        receipt, reason = build(tier="UT")
        self.assertIsNone(receipt)
        assert reason is not None
        self.assertIn("does not levy on assessment directly", reason)
        # The distinction the wording has to carry: this is a fact about the
        # tier structure, not an absence of evidence.
        self.assertNotIn("missing", reason.lower())
        self.assertNotIn("no ", reason.lower()[:3])

    def test_a_filing_with_no_residential_assessment_is_refused(self) -> None:
        receipt, reason = build(residential=False)
        self.assertIsNone(receipt)
        assert reason is not None
        self.assertIn("CVA", reason)

    def test_a_filing_with_no_education_levy_is_refused(self) -> None:
        receipt, reason = build(include_education=False)
        self.assertIsNone(receipt)
        assert reason is not None
        self.assertIn("education", reason)


class TaxationReceiptDeterminism(unittest.TestCase):
    def test_content_builds_carry_no_wall_clock_timestamp(self) -> None:
        first, _ = build()
        second, _ = build()
        assert first is not None and second is not None
        self.assertNotIn("builtAt", first)
        self.assertEqual(json.dumps(first, sort_keys=True), json.dumps(second, sort_keys=True))

    def test_render_json_is_stable_and_newline_terminated(self) -> None:
        receipt, _ = build()
        assert receipt is not None
        rendered = render_json(receipt)
        self.assertTrue(rendered.endswith("\n"))
        self.assertEqual(rendered, render_json(receipt))

    def test_source_date_epoch_is_canonical_utc(self) -> None:
        with patch.dict(os.environ, {"SOURCE_DATE_EPOCH": "0"}, clear=False):
            self.assertEqual(resolve_built_at(), "1970-01-01T00:00:00+00:00")

    def test_naive_timestamps_fail_closed(self) -> None:
        with self.assertRaisesRegex(Exception, "timezone"):
            resolve_built_at("2026-07-25T16:00:00")


if __name__ == "__main__":
    unittest.main()
