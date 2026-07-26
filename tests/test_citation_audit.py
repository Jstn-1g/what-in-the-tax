from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

from scripts.audit_citations import (
    audit_ledger,
    classify,
    numbers_present,
    row_bound,
)


class CitationClassificationTests(unittest.TestCase):
    def test_numbers_do_not_bind_across_unrelated_words(self) -> None:
        present, missing = numbers_present(["1234"], "1 apples 234")
        self.assertFalse(present)
        self.assertEqual(missing, ["1234"])

    def test_french_grouping_and_decimal_match_canonical_amount(self) -> None:
        present, missing = numbers_present(["1,234.56"], "Montant : 1 234,56 $")
        self.assertTrue(present)
        self.assertEqual(missing, [])

    def test_unicode_label_can_be_row_bound(self) -> None:
        excerpt = "Total sécurité incendie ... 1 234"
        page = "Sécurité incendie — total des services 1,234\nAutre service 987"
        self.assertTrue(row_bound(excerpt, page))
        self.assertEqual(classify(excerpt, page, page)[0], "row-bound")

    def test_numbers_without_label_are_weak(self) -> None:
        excerpt = "Fire services ... 1,234"
        page = "Police services 1,234\nFire services 999"
        self.assertEqual(classify(excerpt, page, page)[0], "numbers-only")


class CitationBindingTests(unittest.TestCase):
    def _fixture(
        self,
        root: Path,
        *,
        correct_hashes: bool = True,
        include_hashes: bool = True,
    ) -> dict:
        source_bytes = b"%PDF deterministic fixture"
        extract_bytes = b"===== PAGE 1 =====\nFire services 1,234\n"
        (root / "official.pdf").write_bytes(source_bytes)
        (root / "official.txt").write_bytes(extract_bytes)
        source = {
            "id": "official",
            "localPath": "official.pdf",
            "extractedText": "official.txt",
        }
        if include_hashes:
            source.update(
                {
                    "sha256": (
                        hashlib.sha256(source_bytes).hexdigest()
                        if correct_hashes
                        else "0" * 64
                    ),
                    "bytes": len(source_bytes),
                    "extractedTextSha256": hashlib.sha256(
                        extract_bytes
                    ).hexdigest(),
                }
            )
        return {
            "sources": [source],
            "facts": [
                {
                    "id": "FIRE",
                    "sourceId": "official",
                    "page": 1,
                    "amountCad": 1234,
                    "excerpt": "Fire services 1,234",
                }
            ],
        }

    def test_bound_source_and_extract_have_no_binding_issues(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            report = audit_ledger(
                self._fixture(Path(directory)), root=Path(directory)
            )
        self.assertTrue(report["ok"])
        self.assertEqual(report["results"][0]["tier"], "verbatim")
        self.assertEqual(report["results"][0]["bindingIssues"], [])

    def test_missing_hashes_are_reported_without_hiding_content_match(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            report = audit_ledger(
                self._fixture(Path(directory), include_hashes=False),
                root=Path(directory),
            )
        result = report["results"][0]
        self.assertEqual(result["tier"], "verbatim")
        self.assertCountEqual(
            result["bindingIssues"],
            [
                "source-sha256-missing",
                "source-bytes-missing",
                "extract-sha256-missing",
            ],
        )

    def test_declared_hash_mismatch_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            report = audit_ledger(
                self._fixture(Path(directory), correct_hashes=False),
                root=Path(directory),
            )
        self.assertIn(
            "source-sha256-mismatch", report["results"][0]["bindingIssues"]
        )

    def test_amount_sign_mismatch_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ledger = self._fixture(root)
            ledger["facts"][0]["amountCad"] = -1234
            report = audit_ledger(ledger, root=root)
        self.assertIn("amount-sign-mismatch", report["results"][0]["bindingIssues"])

    def test_parentheses_bind_a_negative_amount(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ledger = self._fixture(root)
            ledger["facts"][0].update(
                amountCad=-1234,
                excerpt="Fire services (1,234)",
            )
            extract = b"===== PAGE 1 =====\nFire services (1,234)\n"
            (root / "official.txt").write_bytes(extract)
            ledger["sources"][0]["extractedTextSha256"] = hashlib.sha256(
                extract
            ).hexdigest()
            report = audit_ledger(ledger, root=root)
        self.assertNotIn("amount-sign-mismatch", report["results"][0]["bindingIssues"])

    def test_missing_extract_fails_closed_as_unverifiable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ledger = self._fixture(root)
            (root / "official.txt").unlink()
            report = audit_ledger(ledger, root=root)
        self.assertEqual(report["results"][0]["tier"], "unverifiable")
        self.assertIn("extract-file-missing", report["results"][0]["bindingIssues"])

    def test_extract_path_cannot_escape_root(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ledger = self._fixture(root)
            ledger["sources"][0]["extractedText"] = "../outside.txt"
            report = audit_ledger(ledger, root=root)
        self.assertEqual(report["results"][0]["tier"], "unverifiable")
        self.assertTrue(
            any(
                issue.startswith("extract-file-missing:path escapes")
                for issue in report["results"][0]["bindingIssues"]
            )
        )


if __name__ == "__main__":
    unittest.main()
