from decimal import Decimal
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.lib.rt_rates import (  # noqa: E402
    parse_rt_rates_from_text,
    rate_to_decimal,
)


class ResidentialRateParserTests(unittest.TestCase):
    def test_printed_percent_handles_tiny_rates_without_magnitude_guessing(self):
        parsed = parse_rt_rates_from_text(
            "RT Residential 0.010% 0.020% 0.030% 0.060%"
        )

        self.assertEqual(parsed["city"], Decimal("0.00010"))
        self.assertEqual(parsed["region"], Decimal("0.00020"))
        self.assertEqual(parsed["education"], Decimal("0.00030"))
        self.assertEqual(parsed["total"], Decimal("0.00060"))
        self.assertEqual(parsed["sourceUnit"], "percent")
        self.assertEqual(parsed["unitDeclaration"], "printed_suffix")

    def test_explicit_decimal_unit_preserves_exact_decimal_values(self):
        parsed = parse_rt_rates_from_text(
            "RT Residential 0.00322187 0.00738314 0.00153000 0.01213501",
            rate_unit="decimal",
        )

        self.assertIsInstance(parsed["city"], Decimal)
        self.assertEqual(parsed["city"], Decimal("0.00322187"))
        self.assertEqual(parsed["total"], Decimal("0.01213501"))
        self.assertEqual(parsed["unitDeclaration"], "config.rateUnit")

    def test_explicit_mill_unit_converts_per_thousand_exactly(self):
        parsed = parse_rt_rates_from_text(
            "RT Residential 3.200 7.100 1.500 11.800",
            rate_unit="mill",
        )

        self.assertEqual(parsed["city"], Decimal("0.003200"))
        self.assertEqual(parsed["region"], Decimal("0.007100"))
        self.assertEqual(parsed["education"], Decimal("0.001500"))
        self.assertEqual(parsed["total"], Decimal("0.011800"))

    def test_printed_mill_suffix_is_an_explicit_source_unit(self):
        parsed = parse_rt_rates_from_text(
            "RT Residential 3.2 mills 7.1 mills 1.5 mills 11.8 mills"
        )

        self.assertEqual(parsed["total"], Decimal("0.0118"))
        self.assertEqual(parsed["unitDeclaration"], "printed_suffix")

    def test_unmarked_values_fail_closed_without_a_unit(self):
        with self.assertRaisesRegex(SystemExit, "ambiguous unmarked rates"):
            parse_rt_rates_from_text(
                "RT Residential 0.010 0.020 0.030 0.060"
            )

    def test_configured_unit_cannot_conflict_with_printed_suffix(self):
        with self.assertRaisesRegex(SystemExit, "conflicts with printed percent"):
            parse_rt_rates_from_text(
                "RT Residential 0.010% 0.020% 0.030% 0.060%",
                rate_unit="decimal",
            )

    def test_direct_conversion_never_uses_binary_float(self):
        value = rate_to_decimal("0.1", unit="percent")

        self.assertEqual(value, Decimal("0.001"))
        self.assertEqual(value * Decimal("100000"), Decimal("100.000"))


if __name__ == "__main__":
    unittest.main()
