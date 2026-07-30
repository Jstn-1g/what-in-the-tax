from __future__ import annotations

import hashlib
import tempfile
import unittest
import zipfile
from pathlib import Path

from scripts.audit_citations import (
    _amount_binding_issue,
    inspect_source,
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


class MagnitudeProseBindingTests(unittest.TestCase):
    """Budget prose writes round figures in words, and the audit has to read it.

    "new debt financing proposed [$5 million] to finance the Twin Pad Project"
    is the correct page for a $5,000,000 fact, and the digit variants never
    matched it, so a citation pointing at exactly the right page was reported as
    amount-not-on-cited-page - a hard failure, and a false one.

    The loosening is deliberately narrow. Prose binds only when it renders the
    figure exactly; a rounded "$5 million" must never bind 5,043,210, because
    treating a rounding as proof of a precise figure is the overclaim this audit
    exists to catch.
    """

    def issue(self, amount, text):
        return _amount_binding_issue({"amountCad": amount}, text)

    def test_exact_prose_binds_the_figure(self) -> None:
        self.assertIsNone(
            self.issue(5_000_000, "new debt financing proposed [$5 million] here")
        )

    def test_a_rounded_prose_figure_never_binds(self) -> None:
        # The case that keeps this honest.
        self.assertEqual(
            self.issue(5_043_210, "new debt financing proposed [$5 million] here"),
            "amount-not-on-cited-page",
        )

    def test_one_decimal_place_binds_when_exact(self) -> None:
        self.assertIsNone(self.issue(1_500_000, "a $1.5 million reserve"))

    def test_the_wrong_magnitude_word_does_not_bind(self) -> None:
        self.assertEqual(
            self.issue(5_000_000, "a $5 thousand grant"),
            "amount-not-on-cited-page",
        )

    def test_digit_matching_is_unchanged(self) -> None:
        self.assertIsNone(self.issue(5_000_000, "total of 5,000,000 dollars"))
        self.assertEqual(
            self.issue(5_000_000, "nothing numeric here"),
            "amount-not-on-cited-page",
        )

    def test_the_single_letter_abbreviation_binds(self) -> None:
        # The Region's own summary prints "Property Taxes $887 M".
        self.assertIsNone(self.issue(887_000_000, "Property Taxes $887 M"))

    def test_the_abbreviation_needs_a_word_boundary(self) -> None:
        # "887 Metres" must never bind $887,000,000.
        self.assertEqual(
            self.issue(887_000_000, "887 Metres of watermain"),
            "amount-not-on-cited-page",
        )

    def test_a_rounded_abbreviation_never_binds(self) -> None:
        self.assertEqual(
            self.issue(887_329_000, "Property Taxes $887 M"),
            "amount-not-on-cited-page",
        )


class ScaleFactorBindingTests(unittest.TestCase):
    """printedValue x scaleFactor == canonicalValue, made checkable.

    Budget books print large figures in thousands: the Region's page prints
    887,329 where the canonical amount is 887,329,000. scaleFactor declares
    that relationship; nothing is inferred from how nicely numbers divide.
    """

    def issue(self, fact, text):
        return _amount_binding_issue(fact, text)

    def test_a_declared_scale_binds_the_printed_figure(self) -> None:
        fact = {"amountCad": 887_329_000, "scaleFactor": 1000}
        self.assertIsNone(self.issue(fact, "$1,612,760 $887,329 100%"))

    def test_the_canonical_amount_alone_does_not_bind_a_scaled_page(self) -> None:
        fact = {"amountCad": 887_329_000}
        self.assertEqual(
            self.issue(fact, "$1,612,760 $887,329 100%"),
            "amount-not-on-cited-page",
        )

    def test_inexact_division_cannot_borrow_the_clean_printed_figure(self) -> None:
        # 887,329,432 / 1000 is not 887,329; a truncated rendering matching
        # the page is a different number being on the page.
        fact = {"amountCad": 887_329_432, "scaleFactor": 1000}
        self.assertEqual(
            self.issue(fact, "$1,612,760 $887,329 100%"),
            "amount-not-on-cited-page",
        )

    def test_a_nonsense_scale_is_an_issue_not_a_pass(self) -> None:
        for bad in (0, -1000, True):
            with self.subTest(scale=bad):
                self.assertEqual(
                    self.issue({"amountCad": 887_329_000, "scaleFactor": bad}, "887,329"),
                    "scale-factor-invalid",
                )

    def test_the_truncation_hole_is_closed_for_unscaled_facts_too(self) -> None:
        # int(298.54) used to offer "298" as a variant.
        self.assertEqual(
            self.issue({"amountCad": 298.54}, "line item 298 units"),
            "amount-not-on-cited-page",
        )
        self.assertIsNone(self.issue({"amountCad": 298.54}, "totals 298.54 here"))


class ArchiveMemberExtractTests(unittest.TestCase):
    """A ZIP member as its own extract, bound by a declared digest.

    The container hash pins the archive; the member digest pins the text the
    audit actually reads. Nothing is read unpinned: every failure mode here
    must yield no extract text, and the digest issues are hard errors in the
    publication validator rather than quiet downgrades to unverifiable.
    """

    MEMBER = '"2025","North Dumfries (TP), Ontario","13051"\r\n'.encode("utf-8")

    def _write_zip(self, root: Path, *, member: str = "table.csv", data: bytes | None = None) -> bytes:
        payload = self.MEMBER if data is None else data
        with zipfile.ZipFile(root / "table.zip", "w") as archive:
            archive.writestr(member, payload)
        return payload

    @staticmethod
    def _source(digest: str | None, *, member: str | None = "table.csv") -> dict:
        source = {"id": "statcan-test", "localPath": "table.zip"}
        if member is not None:
            source["archiveMember"] = member
        if digest is not None:
            source["archiveMemberSha256"] = digest
        return source

    def test_a_digest_bound_member_is_the_extract(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            payload = self._write_zip(root)
            digest = hashlib.sha256(payload).hexdigest()
            binding, text = inspect_source(self._source(digest), root)
            self.assertEqual(text, payload.decode("utf-8"))
            self.assertTrue(binding["extractReadable"])
            self.assertNotIn("extract-path-missing", binding["issues"])
            self.assertNotIn("extract-sha256-missing", binding["issues"])

    def test_a_bom_never_reaches_the_extract_text(self) -> None:
        data = "\ufeff" + self.MEMBER.decode("utf-8")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            payload = self._write_zip(root, data=data.encode("utf-8"))
            digest = hashlib.sha256(payload).hexdigest()
            _, text = inspect_source(self._source(digest), root)
            self.assertEqual(text, self.MEMBER.decode("utf-8"))

    def test_a_tampered_member_yields_no_extract_and_is_named(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_zip(root, data=self.MEMBER + b"tampered")
            stale_digest = hashlib.sha256(self.MEMBER).hexdigest()
            binding, text = inspect_source(self._source(stale_digest), root)
            self.assertIsNone(text)
            self.assertIn("archive-member-sha256-mismatch", binding["issues"])
            self.assertFalse(binding["extractReadable"])

    def test_a_member_without_a_digest_is_never_read(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_zip(root)
            binding, text = inspect_source(self._source(None), root)
            self.assertIsNone(text)
            self.assertIn("archive-member-sha256-missing", binding["issues"])

    def test_a_vanished_member_is_named(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            payload = self._write_zip(root, member="other.csv")
            digest = hashlib.sha256(payload).hexdigest()
            binding, text = inspect_source(self._source(digest), root)
            self.assertIsNone(text)
            self.assertIn("archive-member-missing", binding["issues"])

    def test_every_archive_issue_is_a_publication_error(self) -> None:
        # The audit degrades; the publication validator must refuse. If one of
        # these strings falls out of HASH_MISMATCH_ISSUES, a tampered or
        # unpinned member quietly becomes an "unverifiable" warning instead.
        from scripts.validate_pack import HASH_MISMATCH_ISSUES

        self.assertLessEqual(
            {
                "archive-member-sha256-missing",
                "archive-member-sha256-mismatch",
                "archive-member-missing",
                "archive-member-invalid",
            },
            HASH_MISMATCH_ISSUES,
        )
