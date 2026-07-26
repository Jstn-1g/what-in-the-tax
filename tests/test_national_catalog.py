from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / "national" / "source_catalog.json"
COVERAGE_PATH = ROOT / "national" / "coverage_plan.json"
PROVINCES_TERRITORIES = {
    "AB",
    "BC",
    "MB",
    "NB",
    "NL",
    "NS",
    "NT",
    "NU",
    "ON",
    "PE",
    "QC",
    "SK",
    "YT",
}


class NationalSourceCatalogTests(unittest.TestCase):
    def setUp(self) -> None:
        self.catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
        self.coverage = json.loads(COVERAGE_PATH.read_text(encoding="utf-8"))

    def test_plan_has_official_municipal_source_for_all_thirteen_jurisdictions(
        self,
    ) -> None:
        planned = self.catalog["plannedSources"]
        covered = {
            row["jurisdiction"]
            for row in planned
            if row["coverageLayer"] == "municipal-regional-governments"
        }
        self.assertEqual(PROVINCES_TERRITORIES, covered)

    def test_plan_includes_current_statcan_and_isc_national_layers(self) -> None:
        by_id = {
            row["sourceId"]: row
            for row in self.catalog["plannedSources"]
        }
        self.assertEqual(
            "current-csd-geography",
            by_id["statcan-csd-boundaries-2025"]["coverageLayer"],
        )
        self.assertEqual(
            "indigenous-governments",
            by_id["isc-first-nations-location"]["coverageLayer"],
        )

    def test_every_planned_source_has_official_url_and_explicit_reuse_gate(
        self,
    ) -> None:
        for row in self.catalog["plannedSources"]:
            with self.subTest(source=row["sourceId"]):
                self.assertTrue(row["landingPageUrl"].startswith("https://"))
                self.assertIsInstance(row["licenseStatus"], str)
                self.assertTrue(row["licenseStatus"])
                self.assertIsInstance(row["reuseReviewRequired"], bool)
                if not row["reuseReviewRequired"]:
                    self.assertTrue(row["licenseUrl"].startswith("https://"))

    def test_active_source_is_version_and_release_hash_pinned(self) -> None:
        active = self.catalog["sources"]
        self.assertEqual(1, len(active))
        source = active[0]
        self.assertEqual("2021", source["classificationVersion"])
        self.assertRegex(source["approvedSha256"], r"^[0-9a-f]{64}$")
        self.assertFalse(source["runtimeNetworkRequired"])
        self.assertEqual("open-licence-confirmed", source["licenseStatus"])
        self.assertTrue(source["licenseUrl"].startswith("https://"))
        self.assertFalse(source["reuseReviewRequired"])

    def test_every_jurisdiction_explicitly_declares_every_required_layer(self) -> None:
        required = set(self.coverage["requiredLayers"])
        jurisdictions = self.coverage["jurisdictions"]
        self.assertEqual(
            PROVINCES_TERRITORIES,
            {row["code"] for row in jurisdictions},
        )
        for row in jurisdictions:
            with self.subTest(jurisdiction=row["code"]):
                self.assertEqual(required, set(row["layers"]))
                for layer, value in row["layers"].items():
                    self.assertIn(
                        value["status"],
                        {
                            "complete",
                            "source-discovery",
                            "adapter-needed",
                            "partial",
                            "not-applicable",
                        },
                    )
                    if layer != "national-geography-baseline":
                        self.assertNotEqual("complete", value["status"])


if __name__ == "__main__":
    unittest.main()
