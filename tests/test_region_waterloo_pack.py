from __future__ import annotations

import copy
import hashlib
import json
import re
import subprocess
import sys
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

import yaml

from scripts.audit_citations import STRONG_TIERS, audit_ledger
from scripts.build_region_waterloo_pack import (
    DATA,
    PACK_PATH,
    RECEIPT_REL,
    ROOT,
    SCHEDULE,
    SOURCE_LOCK,
    _json_bytes,
    build_artifacts,
)
from scripts.lib.region_schedule import (
    AREA_KEYS,
    CURRENCY,
    EXPECTED_SERVICE_ROWS,
    FISCAL_YEAR,
    MUNICIPALITY_AREA_KEYS,
    RegionScheduleError,
    load_region_schedule,
    sha256_file,
    validate_schedule_document,
    verify_source_lock,
)


class RegionWaterlooGoldPackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.schedule = yaml.safe_load(SCHEDULE.read_text(encoding="utf-8"))
        cls.ledger = json.loads(
            (DATA / "evidence-ledger.json").read_text(encoding="utf-8")
        )
        cls.receipt = json.loads(
            (DATA / "taxpayer-receipt.json").read_text(encoding="utf-8")
        )
        cls.source_lock = json.loads(SOURCE_LOCK.read_text(encoding="utf-8"))

    def test_all_five_area_allocations_load_through_one_verified_lock(self) -> None:
        expected_totals = {
            "blended": 2_929,
            "urban": 2_984,
            "rural": 2_543,
            "woolwich": 2_617,
            "wilmot": 2_576,
        }
        for area_key in AREA_KEYS:
            with self.subTest(area_key=area_key):
                loaded = load_region_schedule(area_key)
                self.assertEqual(loaded["fiscalYear"], FISCAL_YEAR)
                self.assertEqual(loaded["currency"], CURRENCY)
                self.assertEqual(
                    loaded["area"]["taxSupportedTotalCad"],
                    expected_totals[area_key],
                )
                self.assertEqual(
                    len(loaded["area"]["lines"]), EXPECTED_SERVICE_ROWS
                )
                self.assertEqual(
                    loaded["sourceLock"]["ledgerSha256"],
                    sha256_file(DATA / "evidence-ledger.json"),
                )

    def test_schedule_coverage_is_complete_and_explicit(self) -> None:
        validation = validate_schedule_document(
            self.schedule,
            root=ROOT,
            schedule_path=SCHEDULE,
            verify_source_files=True,
        )
        self.assertEqual(len(validation["sourceTable"]["serviceRows"]), 23)
        self.assertEqual(self.schedule["coverage"]["areaKeys"], list(AREA_KEYS))
        self.assertEqual(
            self.schedule["coverage"]["municipalityAreaKeys"],
            MUNICIPALITY_AREA_KEYS,
        )
        self.assertEqual(self.schedule["coverage"]["householdAllocations"], 115)
        self.assertIn(
            "User-rate water and wastewater rows shown below the tax-supported table",
            self.schedule["coverage"]["excluded"],
        )
        self.assertIsNone(self.schedule["source"]["retrievedAt"])
        self.assertEqual(
            self.schedule["source"]["retrievalStatus"], "not-recorded"
        )

    def test_household_controls_reconcile_with_decimal(self) -> None:
        for area_key in AREA_KEYS:
            area = self.schedule["areas"][area_key]
            line_sum = sum(
                (Decimal(str(line["amountCad"])) for line in area["lines"]),
                Decimal("0"),
            )
            published = Decimal(str(area["publishedServicesSubtotalCad"]))
            rounding = Decimal(str(area["roundingAdjustmentCad"]))
            offset = Decimal(str(area["pilAndSupplementaryCad"]))
            after_offset = Decimal(str(area["taxSupportedTotalCad"]))
            with self.subTest(area_key=area_key):
                self.assertEqual(line_sum, Decimal(str(area["servicesSubtotalCad"])))
                self.assertEqual(line_sum + rounding, published)
                self.assertEqual(published + offset, after_offset)

    def test_program_gross_to_net_basis_reconciles_with_decimal(self) -> None:
        control = self.schedule["programBasisReconciliation"]
        service_levy = Decimal(
            str(control["publishedPropertyTaxLevySubtotal000Cad"])
        )
        general_revenue = Decimal(str(control["generalRevenueOffset000Cad"]))
        rounding = Decimal(
            str(control["regionalTaxLevyRoundingAdjustment000Cad"])
        )
        regional_levy = Decimal(str(control["publishedRegionalTaxLevy000Cad"]))
        self.assertEqual(
            service_levy + general_revenue + rounding, regional_levy
        )
        self.assertEqual(
            control["unit"],
            "CAD thousands",
            "program controls must never be read as household dollars",
        )
        self.assertEqual(
            Decimal(str(control["publishedNetExpenditureSubtotal000Cad"]))
            - Decimal(str(control["serviceLineNetExpenditureSum000Cad"])),
            Decimal(str(control["netExpenditureRoundingAdjustment000Cad"])),
        )

    def test_every_fact_has_a_locked_page_row_column_binding(self) -> None:
        self.assertEqual(len(self.ledger["facts"]), 177)
        household_ids = [
            fact["id"]
            for fact in self.ledger["facts"]
            if re.fullmatch(
                r"ROW-HH-(?:BLENDED|URBAN|RURAL|WOOLWICH|WILMOT)-\d{2}",
                fact["id"],
            )
        ]
        self.assertEqual(len(household_ids), 115)
        for fact in self.ledger["facts"]:
            with self.subTest(fact_id=fact["id"]):
                self.assertEqual(fact["sourceId"], "row-2026-book")
                self.assertEqual(fact["page"], 12)
                self.assertEqual(fact["fiscalYear"], 2026)
                self.assertEqual(fact["currency"], "CAD")
                self.assertTrue(fact["excerpt"])
                self.assertEqual(fact["binding"]["page"], 12)
                self.assertTrue(fact["binding"]["row"])
                self.assertTrue(fact["binding"]["column"])
                self.assertTrue(fact["binding"]["printedValue"])

    def test_citation_audit_has_only_strong_tiers_and_no_binding_issues(self) -> None:
        audit = audit_ledger(self.ledger, root=ROOT)
        self.assertTrue(audit["ok"])
        self.assertEqual(audit["bindingIssueCounts"], {})
        weak = [
            result
            for result in audit["results"]
            if result["tier"] not in STRONG_TIERS
        ]
        self.assertEqual(weak, [])

    def test_checked_in_artifacts_are_exact_deterministic_build_outputs(self) -> None:
        first = build_artifacts()
        second = build_artifacts()
        self.assertEqual(
            tuple(_json_bytes(value) for value in first),
            tuple(_json_bytes(value) for value in second),
        )
        ledger, receipt, source_lock = first
        self.assertEqual(
            _json_bytes(ledger), (DATA / "evidence-ledger.json").read_bytes()
        )
        self.assertEqual(
            _json_bytes(receipt), (DATA / "taxpayer-receipt.json").read_bytes()
        )
        self.assertEqual(_json_bytes(source_lock), SOURCE_LOCK.read_bytes())
        self.assertEqual(
            source_lock["ledgerSha256"],
            hashlib.sha256(_json_bytes(ledger)).hexdigest(),
        )
        self.assertEqual(
            source_lock["artifacts"]["receipt"]["path"], RECEIPT_REL
        )

    def test_lock_covers_every_primary_text_artifact_with_lf_bytes(self) -> None:
        for role in ("pack", "schedule", "ledger", "receipt"):
            locked = self.source_lock["artifacts"][role]
            path = ROOT / locked["path"]
            payload = path.read_bytes()
            with self.subTest(role=role):
                self.assertNotIn(b"\r\n", payload)
                self.assertEqual(locked["lineEndings"], "LF")
                self.assertEqual(locked["bytes"], len(payload))
                self.assertEqual(
                    locked["sha256"], hashlib.sha256(payload).hexdigest()
                )

    def test_region_extract_lock_is_stable_across_windows_and_git_bytes(self) -> None:
        extract_rel = "data/_extracts/2026_final_budget_book_region.txt"
        working_bytes = (ROOT / extract_rel).read_bytes()
        repository_bytes = subprocess.run(
            ["git", "show", f"HEAD:{extract_rel}"],
            cwd=ROOT,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        ).stdout
        self.assertNotIn(b"\r\n", working_bytes)
        self.assertEqual(working_bytes, repository_bytes)
        self.assertEqual(
            hashlib.sha256(working_bytes).hexdigest(),
            self.schedule["source"]["extractedTextSha256"],
        )
        attributes = (ROOT / ".gitattributes").read_text(encoding="utf-8")
        self.assertIn(
            "corpus/region-of-waterloo-on/** text eol=lf", attributes
        )
        self.assertIn("data/region-waterloo/** text eol=lf", attributes)

    def test_bad_page_and_decimal_unsafe_values_fail_closed(self) -> None:
        bad_page = copy.deepcopy(self.schedule)
        bad_page["source"]["pdfPage"] = 192
        bad_page["source"]["citedPages"] = [192]
        with self.assertRaisesRegex(RegionScheduleError, "outside"):
            validate_schedule_document(
                bad_page,
                root=ROOT,
                schedule_path=SCHEDULE,
                verify_source_files=False,
            )

        unsafe_number = copy.deepcopy(self.schedule)
        unsafe_number["areas"]["urban"]["lines"][0]["amountCad"] = 900.0
        with self.assertRaisesRegex(RegionScheduleError, "not float"):
            validate_schedule_document(
                unsafe_number,
                root=ROOT,
                schedule_path=SCHEDULE,
                verify_source_files=False,
            )

    def test_tampered_schedule_and_content_lock_fail_closed(self) -> None:
        tampered = copy.deepcopy(self.schedule)
        tampered["areas"]["urban"]["lines"][0]["amountCad"] += 1
        with self.assertRaisesRegex(RegionScheduleError, "service line sum"):
            validate_schedule_document(
                tampered,
                root=ROOT,
                schedule_path=SCHEDULE,
                verify_source_files=False,
            )

        bad_lock = copy.deepcopy(self.source_lock)
        bad_lock["artifacts"]["ledger"]["sha256"] = "0" * 64
        with tempfile.TemporaryDirectory() as temp_dir:
            lock_path = Path(temp_dir) / "sources.lock.json"
            lock_path.write_text(json.dumps(bad_lock), encoding="utf-8")
            with self.assertRaisesRegex(RegionScheduleError, "ledger.*SHA-256"):
                verify_source_lock(
                    self.schedule,
                    root=ROOT,
                    schedule_path=SCHEDULE,
                    source_lock_path=lock_path,
                )

    def test_strict_publication_gate_has_zero_errors_and_warnings(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                "scripts/validate_pack.py",
                "region-of-waterloo-on",
                "--strict",
                "--no-write",
            ],
            cwd=ROOT,
            check=False,
            text=True,
            capture_output=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        summary = json.loads(result.stdout.split("\n  WARNING:", 1)[0])
        self.assertTrue(summary["ok"])
        self.assertEqual(summary["errors"], 0)
        self.assertEqual(summary["warnings"], 0)

    def test_preview_status_and_absent_human_approval_are_preserved(self) -> None:
        pack = yaml.safe_load(PACK_PATH.read_text(encoding="utf-8"))
        self.assertEqual(pack["publication"]["status"], "draft")
        self.assertEqual(pack["publication"]["lifecycle"], "draft")
        self.assertIsNone(pack["publication"]["publisher"])
        self.assertIsNone(pack["publication"]["contact"])
        self.assertEqual(self.receipt["status"], "partial_evidence_based")
        self.assertEqual(self.receipt["findings"], [])


if __name__ == "__main__":
    unittest.main()
