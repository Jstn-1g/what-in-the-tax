from __future__ import annotations

import unittest

from scripts.validate_pack import (
    apply_sources_lock,
    check_citation_gate,
    check_derived_calculations,
    check_identity_and_context,
    check_ids_resolve,
)


def _identity_fixture() -> tuple[dict, dict, dict]:
    pack = {
        "slug": "example-on",
        "name": "Township of Example",
        "level": "lower-tier",
        "fiscalYear": 2026,
        "currency": "CAD",
        "assessmentCode": "9999",
    }
    ledger = {
        "schemaVersion": "2.0.0",
        "artifact": "EvidenceLedger",
        "fiscalYear": 2026,
        "currency": "CAD",
        "jurisdiction": {
            "slug": "example-on",
            "name": "Township of Example",
            "level": "lower-tier",
            "assessmentCode": "9999",
        },
        "sources": [],
        "facts": [],
        "derived": [],
    }
    receipt = {
        "schemaVersion": "2.0.0",
        "artifact": "TaxpayerReceipt",
        "fiscalYear": 2026,
        "currency": "CAD",
        "evidencePolicyRef": "data/example/evidence-ledger.json",
        "jurisdiction": {
            "slug": "example-on",
            "displayName": "Township of Example",
            "level": "lower-tier",
        },
    }
    return pack, ledger, receipt


class IdentityTests(unittest.TestCase):
    def test_consistent_identity_year_and_currency_pass(self) -> None:
        pack, ledger, receipt = _identity_fixture()
        errors, warnings = check_identity_and_context(
            pack,
            ledger,
            receipt,
            directory_slug="example-on",
            ledger_rel="data/example/evidence-ledger.json",
            strict=True,
        )
        self.assertEqual(errors, [])
        self.assertEqual(warnings, [])

    def test_slug_assessment_year_and_currency_mismatches_fail(self) -> None:
        pack, ledger, receipt = _identity_fixture()
        ledger["jurisdiction"]["assessmentCode"] = "0001"
        receipt["jurisdiction"]["slug"] = "other-on"
        receipt["fiscalYear"] = 2025
        receipt["currency"] = "USD"
        errors, _ = check_identity_and_context(
            pack,
            ledger,
            receipt,
            directory_slug="example-on",
            ledger_rel="data/example/evidence-ledger.json",
            strict=False,
        )
        joined = "\n".join(errors)
        self.assertIn("slug mismatch", joined)
        self.assertIn("assessmentCode mismatch", joined)
        self.assertIn("fiscal year mismatch", joined)
        self.assertIn("currency mismatch", joined)

    def test_missing_context_warns_in_draft_and_fails_when_strict(self) -> None:
        pack, ledger, receipt = _identity_fixture()
        del ledger["fiscalYear"]
        del receipt["currency"]
        draft_errors, draft_warnings = check_identity_and_context(
            pack,
            ledger,
            receipt,
            directory_slug="example-on",
            ledger_rel="data/example/evidence-ledger.json",
            strict=False,
        )
        strict_errors, _ = check_identity_and_context(
            pack,
            ledger,
            receipt,
            directory_slug="example-on",
            ledger_rel="data/example/evidence-ledger.json",
            strict=True,
        )
        self.assertEqual(draft_errors, [])
        self.assertEqual(len(draft_warnings), 2)
        self.assertEqual(len(strict_errors), 2)


class ReferenceAndDerivedTests(unittest.TestCase):
    def test_receipt_references_expand_through_derived_inputs(self) -> None:
        ledger = {
            "sources": [{"id": "S"}],
            "facts": [
                {
                    "id": "ASSESSMENT",
                    "sourceId": "S",
                    "amountCad": 100,
                },
                {"id": "RATE", "sourceId": "S", "value": 0.01},
            ],
            "derived": [
                {
                    "id": "BILL",
                    "amountCad": 1,
                    "formula": "ASSESSMENT * RATE",
                    "inputs": ["ASSESSMENT", "RATE"],
                }
            ],
            "gaps": [],
            "closedGaps": [],
        }
        receipt = {"profiles": {"sample": {"sourceFactId": "BILL"}}}
        errors, load_bearing, fact_ids = check_ids_resolve(ledger, receipt)
        self.assertEqual(errors, [])
        self.assertEqual(load_bearing, {"BILL", "ASSESSMENT", "RATE"})
        self.assertEqual(fact_ids, {"ASSESSMENT", "RATE"})

    def test_machine_evaluable_expression_is_recomputed(self) -> None:
        ledger = {
            "facts": [
                {"id": "ASSESSMENT", "amountCad": 100},
                {"id": "RATE", "value": 0.01},
            ],
            "derived": [
                {
                    "id": "BILL",
                    "amountCad": 1.00,
                    "formula": "ASSESSMENT * RATE",
                    "inputs": ["ASSESSMENT", "RATE"],
                }
            ],
        }
        errors, warnings = check_derived_calculations(ledger)
        self.assertEqual(errors, [])
        self.assertEqual(warnings, [])

        ledger["derived"][0]["amountCad"] = 1.10
        errors, _ = check_derived_calculations(ledger)
        self.assertIn("does not recompute", errors[0])

    def test_formula_reference_must_be_declared_as_input(self) -> None:
        ledger = {
            "facts": [
                {"id": "ASSESSMENT", "amountCad": 100},
                {"id": "RATE", "value": 0.01},
            ],
            "derived": [
                {
                    "id": "BILL",
                    "amountCad": 1,
                    "formula": "ASSESSMENT * RATE",
                    "inputs": ["ASSESSMENT"],
                }
            ],
        }
        errors, _ = check_derived_calculations(ledger)
        self.assertIn("inputs does not declare", errors[0])

    def test_sum_identity_checks_control_total(self) -> None:
        ledger = {
            "facts": [
                {"id": "ONE", "amountCad": 4},
                {"id": "TWO", "amountCad": 6},
                {"id": "CONTROL", "amountCad": 10},
            ],
            "derived": [
                {
                    "id": "TOTAL",
                    "amountCad": 10,
                    "formula": "sum(component amounts) == CONTROL",
                    "inputs": ["ONE", "TWO", "CONTROL"],
                }
            ],
        }
        self.assertEqual(check_derived_calculations(ledger)[0], [])
        ledger["facts"][2]["amountCad"] = 11
        errors, _ = check_derived_calculations(ledger)
        self.assertTrue(any("identity fails" in error for error in errors))


class SourceLockAndCitationGateTests(unittest.TestCase):
    def test_sources_lock_overlays_hashes_and_checks_metadata(self) -> None:
        ledger = {
            "sources": [
                {
                    "id": "S",
                    "localPath": "source.pdf",
                    "extractedText": "source.txt",
                }
            ],
            "facts": [{"id": "F", "sourceId": "S"}],
        }
        source_lock = {
            "sources": [
                {
                    "id": "S",
                    "localPath": "source.pdf",
                    "sha256": "a" * 64,
                    "bytes": 12,
                    "extractedText": "source.txt",
                    "extractedTextSha256": "b" * 64,
                }
            ]
        }
        merged, errors, warnings = apply_sources_lock(
            ledger,
            source_lock,
            load_bearing_fact_ids={"F"},
            strict=True,
        )
        self.assertEqual(errors, [])
        self.assertEqual(warnings, [])
        self.assertEqual(merged["sources"][0]["sha256"], "a" * 64)
        self.assertEqual(merged["sources"][0]["bytes"], 12)
        self.assertNotIn("sha256", ledger["sources"][0])

    def test_missing_lock_is_warning_for_draft_and_error_for_sealed(self) -> None:
        ledger = {
            "sources": [{"id": "S"}],
            "facts": [{"id": "F", "sourceId": "S"}],
        }
        _, draft_errors, draft_warnings = apply_sources_lock(
            ledger, None, load_bearing_fact_ids={"F"}, strict=False
        )
        _, strict_errors, _ = apply_sources_lock(
            ledger, None, load_bearing_fact_ids={"F"}, strict=True
        )
        self.assertEqual(draft_errors, [])
        self.assertTrue(draft_warnings)
        self.assertTrue(strict_errors)

    def test_weak_or_unbound_load_bearing_fact_blocks_only_strict_pack(self) -> None:
        audit = {
            "results": [
                {
                    "id": "F",
                    "tier": "numbers-only",
                    "bindingIssues": ["extract-sha256-missing"],
                    "note": "weak",
                }
            ]
        }
        draft_errors, draft_warnings = check_citation_gate(
            audit, load_bearing_fact_ids={"F"}, strict=False
        )
        strict_errors, _ = check_citation_gate(
            audit, load_bearing_fact_ids={"F"}, strict=True
        )
        self.assertEqual(draft_errors, [])
        self.assertEqual(len(draft_warnings), 2)
        self.assertEqual(len(strict_errors), 2)

    def test_declared_hash_mismatch_always_fails(self) -> None:
        audit = {
            "results": [
                {
                    "id": "F",
                    "tier": "verbatim",
                    "bindingIssues": ["source-sha256-mismatch"],
                    "note": "",
                }
            ]
        }
        errors, _ = check_citation_gate(
            audit, load_bearing_fact_ids=set(), strict=False
        )
        self.assertEqual(len(errors), 1)
        self.assertIn("invalid declared binding", errors[0])


if __name__ == "__main__":
    unittest.main()
