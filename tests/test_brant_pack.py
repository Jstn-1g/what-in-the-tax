from __future__ import annotations

import json
import subprocess
import sys
import unittest
from decimal import Decimal
from pathlib import Path

import yaml

from scripts.audit_citations import audit_ledger
from scripts.lock_pack_sources import build_source_lock
from scripts.validate_pack import (
    check_derived_calculations,
    check_ids_resolve,
)


ROOT = Path(__file__).resolve().parents[1]
PACK_PATH = ROOT / "corpus" / "brant-county-on" / "pack.yaml"
LOCK_PATH = ROOT / "corpus" / "brant-county-on" / "sources.lock.json"
LEDGER_PATH = ROOT / "data" / "brant" / "evidence-ledger.json"
RECEIPT_PATH = ROOT / "data" / "brant" / "taxpayer-receipt.json"
AUDIT_PATH = ROOT / "data" / "brant" / "citation-audit.json"


class BrantPublicationCandidateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.pack = yaml.safe_load(PACK_PATH.read_text(encoding="utf-8"))
        cls.source_lock = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
        cls.ledger = json.loads(LEDGER_PATH.read_text(encoding="utf-8"))
        cls.receipt = json.loads(RECEIPT_PATH.read_text(encoding="utf-8"))
        cls.audit = json.loads(AUDIT_PATH.read_text(encoding="utf-8"))

    def test_identity_year_currency_and_tier_are_explicit(self) -> None:
        self.assertEqual(self.pack["fiscalYear"], 2026)
        self.assertEqual(self.ledger["fiscalYear"], 2026)
        self.assertEqual(self.receipt["fiscalYear"], 2026)
        self.assertEqual(self.pack["currency"], "CAD")
        self.assertEqual(self.ledger["currency"], "CAD")
        self.assertEqual(self.receipt["currency"], "CAD")
        self.assertEqual(self.pack["publication"]["status"], "draft")
        self.assertEqual(self.pack["publication"]["tier"], 0)
        self.assertEqual(
            self.receipt["coverage"]["status"],
            "complete-for-declared-tier-0-scope",
        )

    def test_tier_zero_has_no_claims_or_open_gaps(self) -> None:
        self.assertEqual(self.ledger["gaps"], [])
        self.assertEqual(self.receipt["findings"], [])
        self.assertEqual(self.receipt["coverage"]["findingsCount"], 0)
        self.assertEqual(self.receipt["coverage"]["openGapsCount"], 0)
        self.assertFalse(
            self.receipt["uiModelHints"]["showGapsAsFirstClassUi"]
        )

    def test_project_metadata_does_not_imply_official_endorsement(self) -> None:
        publisher = self.receipt["publisher"]
        self.assertEqual(publisher["name"], "What in the Tax? project")
        self.assertIn("not the County of Brant", publisher["role"])
        self.assertEqual(self.receipt["license"]["spdx"], "MIT")
        self.assertIn(
            "not relicensed",
            self.receipt["license"]["sourceDocuments"],
        )
        self.assertEqual(
            self.receipt["publicationApproval"]["status"],
            "pending-named-human-approval",
        )
        self.assertIsNone(
            self.receipt["publicationApproval"]["approvedBy"]
        )
        self.assertEqual(
            self.receipt["correctionsRoute"],
            {
                "type": "email",
                "url": "mailto:corrections@whatinthetax.com",
                "status": "active",
            },
        )

    def test_every_fact_is_receipt_driving_and_resolves(self) -> None:
        errors, load_bearing, fact_ids = check_ids_resolve(
            self.ledger, self.receipt
        )
        self.assertEqual(errors, [])
        self.assertEqual(len(fact_ids), 20)
        self.assertEqual(load_bearing & fact_ids, fact_ids)
        for fact in self.ledger["facts"]:
            self.assertIsInstance(fact.get("sourceId"), str)
            self.assertGreater(fact.get("page", 0), 0)
            self.assertTrue(fact.get("excerpt"))

    def test_all_derived_expressions_recompute_without_warnings(self) -> None:
        errors, warnings = check_derived_calculations(self.ledger)
        self.assertEqual(errors, [])
        self.assertEqual(warnings, [])

    def test_source_and_extract_lock_is_fresh_and_complete(self) -> None:
        self.assertEqual(
            build_source_lock(LEDGER_PATH, project_root=ROOT),
            self.source_lock,
        )
        self.assertEqual(len(self.source_lock["sources"]), 2)
        for source in self.ledger["sources"]:
            self.assertEqual(source["fiscalYear"], 2026)
            self.assertEqual(source["currency"], "CAD")
            self.assertEqual(source["publisher"], "County of Brant")
            self.assertEqual(source["license"], "unspecified")
            self.assertEqual(len(source["sha256"]), 64)
            self.assertEqual(len(source["extractedTextSha256"]), 64)
            self.assertGreater(source["bytes"], 0)
        for source in self.source_lock["sources"]:
            self.assertEqual(source["lockStatus"], "source-and-extract")
            self.assertEqual(len(source["sha256"]), 64)
            self.assertEqual(len(source["extractedTextSha256"]), 64)

    def test_citation_audit_has_full_hash_binding(self) -> None:
        recomputed = audit_ledger(self.ledger, root=ROOT)
        self.assertTrue(recomputed["ok"])
        self.assertEqual(recomputed["counts"], {"verbatim": 18, "normalized": 2})
        self.assertEqual(recomputed["bindingIssueCounts"], {})
        self.assertEqual(
            {row["id"] for row in recomputed["results"]},
            {row["id"] for row in self.ledger["facts"]},
        )
        self.assertTrue(
            all(not row["bindingIssues"] for row in recomputed["results"])
        )
        self.assertEqual(self.audit, recomputed)

    def test_control_totals_and_receipt_cents_reconcile(self) -> None:
        facts = {row["id"]: row for row in self.ledger["facts"]}
        departments = [
            row
            for fact_id, row in facts.items()
            if fact_id.startswith("BRANT-DEPT-")
        ]
        self.assertEqual(
            sum(Decimal(str(row["amountCad"])) for row in departments),
            Decimal("92457575"),
        )
        profile = self.receipt["profiles"]["supportedAverageHousehold"]
        county_lines = profile["township"]["lineItems"]
        self.assertEqual(
            sum(Decimal(str(row["amountCad"])) for row in county_lines),
            Decimal("4295.33"),
        )
        self.assertEqual(
            sum(
                Decimal(str(row["amountCad"]))
                for row in profile["combinedAtAssessment"]["components"]
            ),
            Decimal("4893.56"),
        )
        reconciliations = {
            row["id"]: row for row in self.ledger["reconciliations"]
        }
        self.assertEqual(
            reconciliations["REC-BRANT-DEPARTMENT-CONTROL-2026"]["status"],
            "exact",
        )
        self.assertEqual(
            Decimal(
                str(
                    reconciliations[
                        "REC-BRANT-BUDGET-ILLUSTRATION-2026"
                    ]["amountCad"]
                )
            ),
            Decimal("0.02"),
        )

    def test_strict_pack_gate_has_zero_errors_and_warnings(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / "validate_pack.py"),
                "brant-county-on",
                "--strict",
                "--no-write",
            ],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('"ok": true', result.stdout)
        self.assertIn('"errors": 0', result.stdout)
        self.assertIn('"warnings": 0', result.stdout)


if __name__ == "__main__":
    unittest.main()
