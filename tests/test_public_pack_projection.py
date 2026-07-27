import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "build_public_packs.py"
SPEC = importlib.util.spec_from_file_location("build_public_packs", MODULE_PATH)
assert SPEC and SPEC.loader
PUBLIC_PACKS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PUBLIC_PACKS)


class PublicPackProjectionTests(unittest.TestCase):
    def test_uses_canonical_root_data(self):
        self.assertEqual(PUBLIC_PACKS.DATA_ROOT, ROOT / "data")

    def test_missing_audit_rows_are_explicitly_unverifiable(self):
        audit = {"results": [{"id": "FACT-A", "tier": "verbatim"}]}
        projected = PUBLIC_PACKS.project_audit(audit, {"FACT-A", "FACT-B"})

        self.assertEqual(
            projected["results"],
            [
                {"id": "FACT-A", "tier": "verbatim"},
                {"id": "FACT-B", "tier": "unverifiable"},
            ],
        )
        self.assertEqual(projected["counts"], {"unverifiable": 1, "verbatim": 1})

    def test_duplicate_audit_rows_are_rejected(self):
        audit = {
            "results": [
                {"id": "FACT-A", "tier": "verbatim"},
                {"id": "FACT-A", "tier": "normalized"},
            ]
        }
        with self.assertRaisesRegex(ValueError, "duplicate citation audit row"):
            PUBLIC_PACKS.project_audit(audit, {"FACT-A"})

    def test_receipt_projection_removes_nested_editorial_fields(self):
        receipt = json.loads(
            (ROOT / "data" / "taxpayer-receipt.json").read_text(encoding="utf-8")
        )
        receipt["uiModelHints"]["internalComment"] = "do not publish"
        receipt["profiles"]["supportedAverageHousehold"]["township"][
            "editorialRationale"
        ] = "do not publish"
        receipt["uiModelHints"].pop("showGapsAsFirstClassUi", None)
        receipt["uiModelHints"].pop("forbidFillerAllocation", None)
        projected = PUBLIC_PACKS.project_receipt(receipt)

        hints = projected["uiModelHints"]
        self.assertIs(hints["showGapsAsFirstClassUi"], True)
        self.assertIs(hints["forbidFillerAllocation"], True)
        self.assertNotIn("materialityFloorCad", hints)
        self.assertNotIn("materialityNote", hints)
        self.assertNotIn("flaggedDefinition", hints)
        self.assertNotIn("internalComment", json.dumps(projected))

    def test_legacy_gap_gets_conservative_public_disposition(self):
        ledger = {
            "evidencePolicy": {"rules": []},
            "sources": [],
            "facts": [],
            "derived": [],
            "gaps": [
                {
                    "id": "GAP-1",
                    "kind": "missing_document",
                    "title": "Missing",
                    "detail": "Needs evidence.",
                    "blocks": [],
                    "neededEvidence": ["A document"],
                },
                {
                    "id": "GAP-2",
                    "kind": "structural_context",
                    "title": "Context",
                    "detail": "Not a missing source.",
                    "blocks": [],
                    "neededEvidence": [],
                    "disposition": "not_applicable",
                },
            ],
        }

        projected, _ = PUBLIC_PACKS.project_evidence(ledger, {})

        self.assertEqual(
            [gap["disposition"] for gap in projected["gaps"]],
            ["missing_evidence", "not_applicable"],
        )

    def test_rejects_receipt_year_outside_configured_current_year(self):
        def fake_load(path):
            if path.name == "taxpayer-receipt.json":
                return {
                    "jurisdiction": {"slug": "kitchener-on"},
                    "fiscalYear": 2025,
                    "currency": "CAD",
                }
            return {}

        with patch.object(PUBLIC_PACKS, "load_json", side_effect=fake_load):
            with self.assertRaisesRegex(
                ValueError,
                "must equal the configured current evidence year 2026",
            ):
                PUBLIC_PACKS.build_pack("kitchener-on", Path("."))

    def test_unexpected_json_artifacts_are_found_and_safely_removed(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_root = Path(temp_dir)
            expected = output_root / "kitchener-on.json"
            retired = output_root / "retired-on.json"
            nested_dir = output_root / "old"
            nested_dir.mkdir()
            nested = nested_dir / "retired.json"
            unrelated = output_root / "README.txt"
            for path in (expected, retired, nested):
                path.write_text("{}", encoding="utf-8")
            unrelated.write_text("keep", encoding="utf-8")

            original_inputs = PUBLIC_PACKS.PACK_INPUTS
            try:
                PUBLIC_PACKS.PACK_INPUTS = {"kitchener-on": Path(".")}
                unexpected = PUBLIC_PACKS.unexpected_json_artifacts(output_root)
                self.assertEqual(set(unexpected), {retired, nested})
                PUBLIC_PACKS.remove_unexpected_json_artifacts(
                    unexpected, output_root
                )
            finally:
                PUBLIC_PACKS.PACK_INPUTS = original_inputs

            self.assertTrue(expected.exists())
            self.assertTrue(unrelated.exists())
            self.assertFalse(retired.exists())
            self.assertFalse(nested.exists())


if __name__ == "__main__":
    unittest.main()
