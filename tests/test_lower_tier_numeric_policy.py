from copy import deepcopy
from decimal import Decimal
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.build_lower_tier_pack import (  # noqa: E402
    build_pack,
    calculate_bill_stack,
    load_inputs,
    resolve_artifact_directories,
    resolve_inputs_path,
)


WATERLOO_RATES = {
    "city_rate": Decimal("0.00437426"),
    "region_rate": Decimal("0.00841834"),
    "education_rate": Decimal("0.00153000"),
    "total_rate": Decimal("0.01432260"),
}


class BillRoundingPolicyTests(unittest.TestCase):
    def test_source_declared_total_rounding_reproduces_published_total(self):
        bill = calculate_bill_stack(
            assessment=405000,
            **WATERLOO_RATES,
            rounding={
                "strategy": "total",
                "method": "half-up",
                "quantumCad": "0.01",
                "source": "Official Waterloo worked example",
            },
        )

        self.assertEqual(bill["componentSum"], Decimal("5800.66"))
        self.assertEqual(bill["totalRateAmount"], Decimal("5800.65"))
        self.assertEqual(bill["combined"], Decimal("5800.65"))
        self.assertEqual(bill["roundingAdjustment"], Decimal("-0.01"))
        self.assertTrue(bill["policy"]["sourceDeclared"])
        self.assertTrue(bill["policy"]["sealedEligible"])

    def test_source_declared_component_rounding_is_explicit(self):
        bill = calculate_bill_stack(
            assessment=405000,
            **WATERLOO_RATES,
            rounding={
                "strategy": "component",
                "method": "half-up",
                "quantumCad": "0.01",
                "source": "Source requires each authority amount rounded first",
            },
        )

        self.assertEqual(bill["combined"], Decimal("5800.66"))
        self.assertEqual(bill["roundingAdjustment"], Decimal("0.00"))
        self.assertEqual(
            bill["componentVsTotalRateDelta"],
            Decimal("0.01"),
        )

    def test_half_up_decimal_rounding_handles_exact_half_cent(self):
        bill = calculate_bill_stack(
            assessment=100,
            city_rate="0.00005",
            region_rate="0.00005",
            education_rate="0.00005",
            total_rate="0.00015",
            rounding={
                "strategy": "component",
                "method": "half-up",
                "quantumCad": "0.01",
                "source": "Worked example declares half-up cents",
            },
        )

        self.assertEqual(bill["city"], Decimal("0.01"))
        self.assertEqual(bill["region"], Decimal("0.01"))
        self.assertEqual(bill["education"], Decimal("0.01"))
        self.assertEqual(bill["combined"], Decimal("0.03"))

    def test_explicit_rounding_policy_requires_a_source(self):
        with self.assertRaisesRegex(SystemExit, "rounding.source is required"):
            calculate_bill_stack(
                assessment=405000,
                **WATERLOO_RATES,
                rounding={
                    "strategy": "total",
                    "method": "half-up",
                    "quantumCad": "0.01",
                },
            )


class ControlTotalSemanticsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base_cfg = load_inputs(resolve_inputs_path("waterloo-on"))

    def test_untyped_legacy_levy_does_not_emit_absolute_levy_fact(self):
        cfg = deepcopy(self.base_cfg)
        cfg["controlTotal"].pop("measureType", None)
        cfg["controlTotal"]["assessmentMeasureType"] = "reference_scenario"
        ledger, receipt = build_pack(cfg)

        fact_ids = {item["id"] for item in ledger["facts"]}
        gap_ids = {item["id"] for item in ledger["gaps"]}
        self.assertNotIn("WAT-LEVY-2026", fact_ids)
        self.assertIn("GAP-WAT-LEVY-ABSOLUTE", gap_ids)
        self.assertNotIn("WAT-AVG-ASSESSMENT-2026", fact_ids)
        self.assertIn("WAT-REFERENCE-ASSESSMENT-2026", fact_ids)
        self.assertIn(
            "not a published City of Waterloo average",
            receipt["profiles"]["supportedAverageHousehold"]["description"],
        )

    def test_typed_controls_emit_distinct_measure_types(self):
        cfg = deepcopy(self.base_cfg)
        cfg["rates"]["rateUnit"] = "percent"
        cfg["rates"]["rounding"] = {
            "strategy": "total",
            "method": "half-up",
            "quantumCad": "0.01",
            "source": "Official Waterloo worked example",
        }
        cfg["controlTotal"].update(
            {
                "measureType": "absolute_levy",
                "assessmentMeasureType": "published_average",
                "levyIncreaseCad": 3_000_000,
                "levyIncreaseExcerpt": "tax levy increase of $3 million",
                "averageHouseholdIncreaseCad": "106.92",
                "averageHouseholdIncreaseExcerpt": (
                    "Property Tax Increase - City of Waterloo $106.92"
                ),
            }
        )
        cfg["controlTotal"].pop("taxIncreaseCad", None)

        ledger, receipt = build_pack(cfg)
        self.assertEqual(ledger["currency"], "CAD")
        self.assertEqual(receipt["currency"], "CAD")
        facts = {item["id"]: item for item in ledger["facts"]}
        self.assertEqual(facts["WAT-LEVY-2026"]["measureType"], "absolute_levy")
        self.assertEqual(
            facts["WAT-AVG-ASSESSMENT-2026"]["measureType"],
            "published_average",
        )
        self.assertEqual(
            facts["WAT-LEVY-INCREASE-CAD-2026"]["measureType"],
            "levy_increase",
        )
        self.assertEqual(
            facts["WAT-AVG-HOUSEHOLD-INCREASE-CAD-2026"]["measureType"],
            "average_household_increase",
        )
        policy = receipt["profiles"]["supportedAverageHousehold"][
            "combinedAtAssessment"
        ]["calculationPolicy"]
        self.assertEqual(policy["roundingAdjustmentCad"], -0.01)
        self.assertTrue(policy["rounding"]["sealedEligible"])
        self.assertTrue(policy["assessment"]["sealedEligible"])

    def test_published_average_rejects_non_local_source_authority(self):
        cfg = deepcopy(self.base_cfg)
        cfg["controlTotal"]["assessmentMeasureType"] = "published_average"
        cfg["controlTotal"]["assessmentSourceId"] = "row-2026-book"

        with self.assertRaisesRegex(
            SystemExit,
            "published_average assessment requires a source issued",
        ):
            build_pack(cfg)

    def test_currency_must_be_explicit(self):
        cfg = deepcopy(self.base_cfg)
        cfg.pop("currency", None)

        with self.assertRaisesRegex(SystemExit, "currency is required"):
            build_pack(cfg)

    def test_measure_specific_increase_excerpts_take_precedence(self):
        cfg = load_inputs(resolve_inputs_path("cambridge-on"))
        ledger, _ = build_pack(cfg)
        facts = {item["id"]: item for item in ledger["facts"]}

        self.assertIn(
            "2.44 per cent",
            facts["CAM-TAX-INCREASE-PCT-2026"]["excerpt"],
        )
        self.assertIn(
            "$3 million",
            facts["CAM-LEVY-INCREASE-CAD-2026"]["excerpt"],
        )
        self.assertIn(
            "$42",
            facts["CAM-AVG-HOUSEHOLD-INCREASE-CAD-2026"]["excerpt"],
        )


class OutputPathSafetyTests(unittest.TestCase):
    def test_valid_data_directory_resolves_under_both_roots(self):
        data, web = resolve_artifact_directories(
            {"slug": "sample-on", "dataDir": "data/sample"}
        )

        self.assertEqual(data, (ROOT / "data" / "sample").resolve())
        self.assertEqual(web, (ROOT / "web" / "src" / "data" / "sample").resolve())

    def test_parent_traversal_is_rejected_before_writes(self):
        with self.assertRaisesRegex(SystemExit, "must not contain"):
            resolve_artifact_directories(
                {"slug": "sample-on", "dataDir": "data/../outside"}
            )

    def test_absolute_output_path_is_rejected_before_writes(self):
        with self.assertRaisesRegex(SystemExit, "project-relative"):
            resolve_artifact_directories(
                {"slug": "sample-on", "dataDir": str((ROOT / "data").resolve())}
            )


if __name__ == "__main__":
    unittest.main()
