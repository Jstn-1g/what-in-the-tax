from __future__ import annotations

import csv
import io
import json
import tempfile
import unittest
import zipfile
from collections import Counter
from pathlib import Path

from scripts.build_ontario_fir_public_index import (
    DEFAULT_INPUT,
    DEFAULT_OUTPUT,
    EXPECTED_CSV_MEMBER,
    EXPECTED_HEADERS,
    EXPECTED_RECORD_COUNT,
    EXPECTED_TIER_COUNTS,
    EXPECTED_CSV_SHA256,
    REVIEWED_ZIP_SHA256,
    IndexBuildError,
    build_index,
    render_index,
)


def fixture_row(
    code: str,
    name: str,
    tier: str,
    *,
    year: str = "2023",
    updated: str = "20260724",
) -> dict[str, str]:
    row = {header: "" for header in EXPECTED_HEADERS}
    row.update(
        {
            "MARSYEAR": year,
            "ASSESSMENT_CODE": code,
            "MUNICIPALITY_DESC": name,
            "MUNID": str(int(code) * 10),
            "SGC_CODE": code,
            "MTYPE_CODE": "0",
            "TIER_CODE": tier,
            "LAST_UPDATE_DATE": updated,
            "SLC": "slc.02X.L0020.C01.02",
            "DATATYPE_DESC": "text",
            "VALUE_TEXT": "omitted from public index",
        }
    )
    return row


class OntarioFirPublicIndexTests(unittest.TestCase):
    def write_zip(
        self,
        root: Path,
        rows: list[dict[str, str]],
        *,
        member: str = EXPECTED_CSV_MEMBER,
        headers: list[str] | None = None,
    ) -> Path:
        buffer = io.StringIO(newline="")
        writer = csv.DictWriter(buffer, fieldnames=headers or EXPECTED_HEADERS)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {field: row.get(field, "") for field in (headers or EXPECTED_HEADERS)}
            )
        path = root / "fixture.zip"
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(member, buffer.getvalue().encode("utf-8"))
        return path

    def cohort_rows(self) -> list[dict[str, str]]:
        return [
            fixture_row("3001", "North Dumfries Tp", "LT"),
            fixture_row("3024", "Wellesley Tp", "LT"),
            fixture_row("3018", "Wilmot Tp", "LT"),
            fixture_row("3029", "Woolwich Tp", "LT"),
        ]

    def test_checked_in_index_has_locked_counts_and_no_receipt_claim(self) -> None:
        index = json.loads(DEFAULT_OUTPUT.read_text(encoding="utf-8"))
        records = index["records"]

        self.assertEqual(EXPECTED_RECORD_COUNT, len(records))
        self.assertEqual(
            EXPECTED_TIER_COUNTS,
            dict(Counter(record["tier"] for record in records)),
        )
        self.assertEqual(
            EXPECTED_RECORD_COUNT,
            len({record["assessmentCode"] for record in records}),
        )
        self.assertEqual(
            EXPECTED_RECORD_COUNT,
            len({record["sourceName"] for record in records}),
        )
        # The artifact cites the reviewed release and is bound to the
        # payload, so it survives Ontario re-zipping identical data.
        self.assertEqual(REVIEWED_ZIP_SHA256, index["source"]["sha256"])
        self.assertEqual(
            EXPECTED_CSV_SHA256, index["source"]["archiveMemberSha256"]
        )
        self.assertFalse(index["isReceipt"])
        self.assertFalse(index["method"]["currentTaxBylaw"])
        self.assertFalse(index["method"]["containsFinancialMetrics"])
        self.assertFalse(index["method"]["runtimeAiRequired"])
        self.assertEqual("incomplete", index["coverage"]["status"])
        self.assertEqual(8, index["coverage"]["recordsNotPresent"])

    def test_checked_in_index_has_only_public_identity_fields(self) -> None:
        index = json.loads(DEFAULT_OUTPUT.read_text(encoding="utf-8"))
        allowed_record_fields = {
            "assessmentCode",
            "displayName",
            "sourceName",
            "typeLabel",
            "tier",
            "lastUpdated",
        }
        for record in index["records"]:
            self.assertEqual(allowed_record_fields, set(record))

        serialized = json.dumps(index)
        for forbidden in (
            "localZip",
            "source-pdfs",
            "VALUE_TEXT",
            "Telephone",
            "Email",
            "builtAt",
        ):
            self.assertNotIn(forbidden, serialized)

    def test_public_index_does_not_publish_a_rollout_sequence(self) -> None:
        """A published order commits the project to a queue it never promised.

        PURPOSE.md caps coverage by capacity rather than ambition, so the public
        artifact states what evidence exists and never what is scheduled next.
        """

        serialized = DEFAULT_OUTPUT.read_text(encoding="utf-8")
        index = json.loads(serialized)
        self.assertNotIn("rolloutPlan", index)
        for forbidden in ("rolloutPlan", "Queued after", "Next receipt target"):
            self.assertNotIn(forbidden, serialized)

    def test_small_fixture_build_is_deterministic_and_strips_only_suffix(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rows = self.cohort_rows()
            rows.extend(
                [
                    fixture_row("3016", "Waterloo C", "LT"),
                    fixture_row("3000", "Waterloo R", "UT"),
                    fixture_row("1831", "St Marys ST", "ST"),
                    fixture_row("2920", "Brant County", "ST"),
                ]
            )
            source = self.write_zip(root, rows)

            first = build_index(source, enforce_release_lock=False)
            second = build_index(source, enforce_release_lock=False)
            self.assertEqual(render_index(first), render_index(second))

            by_code = {
                record["assessmentCode"]: record for record in first["records"]
            }
            self.assertEqual("Waterloo", by_code["3016"]["displayName"])
            self.assertEqual("City", by_code["3016"]["typeLabel"])
            self.assertEqual("Regional Municipality", by_code["3000"]["typeLabel"])
            self.assertEqual("St Marys", by_code["1831"]["displayName"])
            self.assertEqual("Brant County", by_code["2920"]["displayName"])

    def test_changed_release_hash_fails_before_publication(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = self.write_zip(Path(tmp), self.cohort_rows())
            with self.assertRaisesRegex(IndexBuildError, "SHA-256 changed"):
                build_index(source)

    def test_schema_year_and_identity_conflicts_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            bad_headers = EXPECTED_HEADERS[:-1]
            source = self.write_zip(root, self.cohort_rows(), headers=bad_headers)
            with self.assertRaisesRegex(IndexBuildError, "headers changed"):
                build_index(source, enforce_release_lock=False)

            source = self.write_zip(
                root,
                [
                    fixture_row(
                        row["ASSESSMENT_CODE"],
                        row["MUNICIPALITY_DESC"],
                        row["TIER_CODE"],
                        year="2022",
                    )
                    for row in self.cohort_rows()
                ],
            )
            with self.assertRaisesRegex(IndexBuildError, "MARSYEAR"):
                build_index(source, enforce_release_lock=False)

            rows = self.cohort_rows()
            rows.append(fixture_row("3001", "Different Place Tp", "LT"))
            source = self.write_zip(root, rows)
            with self.assertRaisesRegex(IndexBuildError, "conflicting identity"):
                build_index(source, enforce_release_lock=False)

    def test_wrong_archive_member_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = self.write_zip(
                Path(tmp),
                self.cohort_rows(),
                member="renamed.csv",
            )
            with self.assertRaisesRegex(IndexBuildError, "archive members"):
                build_index(source, enforce_release_lock=False)

    @unittest.skipUnless(
        DEFAULT_INPUT.is_file(),
        "locked FIR source archive is intentionally not stored in git",
    )
    def test_local_locked_source_reproduces_checked_in_index(self) -> None:
        rebuilt = render_index(build_index(DEFAULT_INPUT))
        self.assertEqual(DEFAULT_OUTPUT.read_text(encoding="utf-8"), rebuilt)


if __name__ == "__main__":
    unittest.main()
