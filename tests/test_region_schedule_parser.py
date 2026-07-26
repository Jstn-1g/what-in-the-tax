from __future__ import annotations

import unittest

from scripts.parse_row_household_schedule import parse_published_footer


VALID_FOOTER = """
Subtotal
$3,007 $3,062 $2,621 $2,695 $2,654
Less: Payments in Lieu & Supplementary Taxes ($78) ($78) ($78) ($78) ($78)
Regional Tax Levy 100% $2,929 100% $2,984 100% $2,543 100% $2,617 100% $2,576
"""


class RegionScheduleFooterTests(unittest.TestCase):
    def test_parses_locked_source_values(self) -> None:
        subtotals, pil, totals = parse_published_footer(VALID_FOOTER)

        self.assertEqual(subtotals["rural"], 2_621)
        self.assertEqual(pil, -78)
        self.assertEqual(totals["urban"], 2_984)

    def test_missing_subtotals_fail_instead_of_using_expected_values(self) -> None:
        missing = """
        Subtotal
        Less: Payments in Lieu & Supplementary Taxes ($78)
        Regional Tax Levy 100% $2,929 100% $2,984 100% $2,543 100% $2,617 100% $2,576
        """
        with self.assertRaisesRegex(SystemExit, "published household subtotals"):
            parse_published_footer(missing)

    def test_missing_levy_totals_fail_instead_of_using_expected_values(self) -> None:
        missing = """
        Subtotal
        $3,007 $3,062 $2,621 $2,695 $2,654
        Less: Payments in Lieu & Supplementary Taxes ($78)
        """
        with self.assertRaisesRegex(SystemExit, "Regional Tax Levy totals"):
            parse_published_footer(missing)

    def test_ambiguous_pil_fails_closed(self) -> None:
        ambiguous = VALID_FOOTER.replace(
            "($78) ($78) ($78) ($78) ($78)",
            "($78) ($79) ($78) ($78) ($78)",
        )
        with self.assertRaisesRegex(SystemExit, "Ambiguous PIL"):
            parse_published_footer(ambiguous)


if __name__ == "__main__":
    unittest.main()
