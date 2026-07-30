from __future__ import annotations

import csv
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from scripts.build_ontario_municipal_history import (
    DEFAULT_MUNICIPALITIES_INPUT,
    DEFAULT_OUTPUT,
    EXPECTED_HEADERS,
    FIR_RELEASES,
    HistoryBuildError,
    _format_source_date,
    build_index,
    render_index,
)


def fir_row(
    year: int,
    code: str,
    name: str,
    tier: str = "LT",
    updated: str = "20260724",
) -> dict[str, str]:
    row = {header: "" for header in EXPECTED_HEADERS}
    row.update(
        {
            "MARSYEAR": str(year),
            "ASSESSMENT_CODE": code,
            "MUNICIPALITY_DESC": name,
            "MUNID": str(int(code) * 10),
            "SGC_CODE": code,
            "MTYPE_CODE": "0",
            "TIER_CODE": tier,
            "LAST_UPDATE_DATE": updated,
            "SLC": "slc.02X.L0020.C01.02",
            "DATATYPE_DESC": "text",
            "VALUE_TEXT": "not projected",
        }
    )
    return row


class OntarioMunicipalHistoryTests(unittest.TestCase):
    def write_municipalities(
        self,
        root: Path,
        records: list[tuple[str, str, str]],
    ) -> Path:
        path = root / "municipalities.csv"
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=[
                    "Municipality",
                    "Municipal status",
                    "Geographic area",
                ],
            )
            writer.writeheader()
            for name, status, area in records:
                writer.writerow(
                    {
                        "Municipality": (
                            f'<a title="{name}" '
                            f'href="https://example.test/{area.casefold()}">'
                            f"{name}</a>"
                        ),
                        "Municipal status": status,
                        "Geographic area": area,
                    }
                )
        return path

    def write_fir(
        self,
        root: Path,
        year: int,
        rows: list[dict[str, str]],
    ) -> Path:
        buffer = io.StringIO(newline="")
        writer = csv.DictWriter(buffer, fieldnames=EXPECTED_HEADERS)
        writer.writeheader()
        writer.writerows(rows)
        path = root / f"fir_data_{year}.zip"
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(
                f"fir_data_{year}.csv",
                buffer.getvalue().encode("utf-8"),
            )
        return path

    def build_fixture(self, root: Path) -> dict[str, object]:
        municipalities = self.write_municipalities(
            root,
            [
                ("North Dumfries, Township of", "Lower Tier", "Waterloo"),
                ("Wellesley, Township of", "Lower Tier", "Waterloo"),
                ("Wilmot, Township of", "Lower Tier", "Waterloo"),
                ("Woolwich, Township of", "Lower Tier", "Waterloo"),
            ],
        )
        base = [
            ("3001", "North Dumfries Tp"),
            ("3024", "Wellesley Tp"),
            ("3018", "Wilmot Tp"),
            ("3029", "Woolwich Tp"),
        ]
        fir_paths = {
            2023: self.write_fir(
                root,
                2023,
                [fir_row(2023, code, name) for code, name in base],
            ),
            2024: self.write_fir(
                root,
                2024,
                [
                    fir_row(2024, "3001", "North Dumfries Tp"),
                    fir_row(2024, "3024", "Wellesley Tp"),
                    fir_row(2024, "3029", "Woolwich Tp"),
                ],
            ),
            2025: self.write_fir(
                root,
                2025,
                [fir_row(2025, "3024", "Wellesley Tp")],
            ),
        }
        return build_index(
            municipalities,
            fir_paths,
            enforce_release_locks=False,
        )

    def test_checked_artifact_is_current_first_and_keeps_history(self) -> None:
        index = json.loads(DEFAULT_OUTPUT.read_text(encoding="utf-8"))
        self.assertEqual(444, index["coverage"]["currentMunicipalities"])
        self.assertEqual(436, index["coverage"]["withFirHistory"])
        self.assertEqual(8, index["coverage"]["withoutFirHistory"])
        # Ottawa C filed 2025 in the 2026-07-30 re-publication (issue #47),
        # so it moves from "latest 2024" to "latest 2025": 132 -> 133 and
        # 271 -> 270. The pair still totals 436, which is what says these two
        # numbers moved together rather than one of them drifting.
        self.assertEqual(
            {"2025": 133, "2024": 270, "2023": 33, "unavailable": 8},
            index["coverage"]["latestFirYearCounts"],
        )
        self.assertEqual(
            {"2025": 133, "2024": 403, "2023": 436},
            index["coverage"]["firYearRecordCounts"],
        )
        self.assertFalse(index["isReceipt"])
        self.assertFalse(index["method"]["containsFinancialMetrics"])
        self.assertFalse(index["method"]["runtimeAiRequired"])
        self.assertFalse(index["method"]["mixedYearFinancialComparisonsSupported"])

        by_code = {
            row["assessmentCode"]: row
            for row in index["records"]
            if row["assessmentCode"]
        }
        self.assertEqual(2025, by_code["3012"]["latestFirYear"])
        self.assertEqual(
            [2025, 2024, 2023],
            [item["fiscalYear"] for item in by_code["3012"]["firYears"]],
        )
        self.assertEqual(2024, by_code["3001"]["latestFirYear"])
        self.assertEqual(2025, by_code["3024"]["latestFirYear"])
        self.assertEqual(2023, by_code["3018"]["latestFirYear"])
        self.assertEqual(2024, by_code["3029"]["latestFirYear"])

        ignace = next(
            row
            for row in index["records"]
            if row["officialName"] == "Ignace, Township of"
        )
        self.assertIsNone(ignace["assessmentCode"])
        self.assertIsNone(ignace["latestFirYear"])
        self.assertEqual([], ignace["firYears"])

    def test_public_records_contain_identity_and_year_metadata_only(self) -> None:
        index = json.loads(DEFAULT_OUTPUT.read_text(encoding="utf-8"))
        allowed = {
            "directoryId",
            "assessmentCode",
            "displayName",
            "officialName",
            "sourceNameAliases",
            "typeLabel",
            "tier",
            "geographicArea",
            "latestFirYear",
            "firYears",
            "fallbackReason",
        }
        for record in index["records"]:
            self.assertEqual(allowed, set(record))
            years = [item["fiscalYear"] for item in record["firYears"]]
            self.assertEqual(sorted(years, reverse=True), years)
            self.assertEqual(len(years), len(set(years)))
            self.assertEqual(years[0] if years else None, record["latestFirYear"])

        serialized = json.dumps(index)
        for forbidden in (
            "AMOUNT",
            "VALUE_TEXT",
            "source-pdfs",
            "builtAt",
            "taxAmount",
        ):
            self.assertNotIn(forbidden, serialized)

    def test_latest_selection_is_per_municipality_and_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            first = self.build_fixture(root)
            second = self.build_fixture(root)
            self.assertEqual(render_index(first), render_index(second))

            by_code = {
                row["assessmentCode"]: row for row in first["records"]
            }
            self.assertEqual(2024, by_code["3001"]["latestFirYear"])
            self.assertEqual(2025, by_code["3024"]["latestFirYear"])
            self.assertEqual(2023, by_code["3018"]["latestFirYear"])
            self.assertEqual(2024, by_code["3029"]["latestFirYear"])
            self.assertEqual(
                {"2025": 1, "2024": 2, "2023": 1, "unavailable": 0},
                first["coverage"]["latestFirYearCounts"],
            )

    def test_release_hashes_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            municipalities = self.write_municipalities(
                root,
                [("Wellesley, Township of", "Lower Tier", "Waterloo")],
            )
            fir_paths = {
                year: self.write_fir(
                    root,
                    year,
                    [fir_row(year, "3024", "Wellesley Tp")],
                )
                for year in FIR_RELEASES
            }
            with self.assertRaisesRegex(
                HistoryBuildError,
                "municipality CSV SHA-256 changed",
            ):
                build_index(municipalities, fir_paths)

    def test_source_dates_are_calendar_dates(self) -> None:
        self.assertEqual("2026-07-24", _format_source_date("20260724"))
        with self.assertRaisesRegex(
            HistoryBuildError,
            "invalid FIR LAST_UPDATE_DATE",
        ):
            _format_source_date("20260230")

    @unittest.skipUnless(
        DEFAULT_MUNICIPALITIES_INPUT.is_file()
        and all(release.path.is_file() for release in FIR_RELEASES.values()),
        "locked Ontario source files are intentionally acquired outside Git",
    )
    def test_locked_sources_reproduce_checked_artifact(self) -> None:
        rebuilt = render_index(
            build_index(
                DEFAULT_MUNICIPALITIES_INPUT,
                {year: release.path for year, release in FIR_RELEASES.items()},
            )
        )
        self.assertEqual(DEFAULT_OUTPUT.read_text(encoding="utf-8"), rebuilt)


if __name__ == "__main__":
    unittest.main()
