from __future__ import annotations

import json
import unittest
from pathlib import Path

from scripts.build_municipal_dissolutions import (
    DissolutionBuildError,
    OUTPUT,
    _parse_gaining_losing,
    _parse_legacy_alphabetical,
    build,
)

ROOT = Path(__file__).resolve().parents[1]


class MunicipalDissolutionArtifactTests(unittest.TestCase):
    """The committed artifact is exactly what the locked sources derive."""

    def test_the_committed_artifact_is_fresh(self) -> None:
        artifact = build()
        payload = json.dumps(artifact, indent=2, ensure_ascii=False) + "\n"
        self.assertEqual(
            OUTPUT.read_text(encoding="utf-8"),
            payload,
            "municipal-dissolutions.json is stale; rerun "
            "scripts/build_municipal_dissolutions.py",
        )

    def test_the_machine_era_has_exactly_the_known_taxing_dissolutions(self) -> None:
        # Gordon Tp and Barrie Island Tp amalgamated as Gordon/Barrie Island
        # effective 2009-01-01 - the only taxing-municipality dissolution the
        # locked 2006-2025 editions record for Ontario. If this list grows, a
        # source changed and the crosswalk needs a matching entry, which the
        # web test enforces.
        artifact = build()
        taxing = [
            (event["dissolved"], event["successor"], event["effectiveDate"])
            for event in artifact["events"]
            if event["leviedPropertyTax"]
        ]
        self.assertEqual(
            taxing,
            [
                ("Barrie Island", "Gordon/Barrie Island", "2009-01-01"),
                ("Gordon", "Gordon/Barrie Island", "2009-01-01"),
            ],
        )

    def test_every_event_names_its_source_and_line(self) -> None:
        artifact = build()
        self.assertGreater(len(artifact["events"]), 0)
        for event in artifact["events"]:
            self.assertTrue(event["sourceId"].startswith("statcan-il-"))
            self.assertGreater(event["sourceLine"], 0)
            self.assertNotIn(" ", event["sgcCode"])


class PlantedDefectTests(unittest.TestCase):
    """Each refusal proven by the defect it exists to refuse."""

    def test_bytes_that_do_not_match_their_lock_refuse_to_parse(self) -> None:
        # The builder hashes the payload against the reviewed lock before
        # parsing a single row. Plant the defect: a lock whose digest cannot
        # match the bytes on disk.
        import tempfile

        import scripts.build_municipal_dissolutions as module

        fake = json.loads(
            (module.LOCK_DIR / "statcan-il-2016-2021.lock.json").read_text(
                encoding="utf-8"
            )
        )
        fake["sha256"] = "0" * 64
        original_lock_dir = module.LOCK_DIR
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            (tmp_path / "statcan-il-2016-2021.lock.json").write_text(
                json.dumps(fake), encoding="utf-8"
            )
            module.LOCK_DIR = tmp_path
            try:
                with self.assertRaisesRegex(DissolutionBuildError, "unpinned"):
                    module._locked_bytes("statcan-il-2016-2021")
            finally:
                module.LOCK_DIR = original_lock_dir

    def test_a_dissolution_without_a_successor_remark_refuses(self) -> None:
        rows = 'Someplace,,TP,4,01/01/2009,35 51 024,412,"no remark here"\r\n'
        with self.assertRaisesRegex(DissolutionBuildError, "no parseable successor"):
            _parse_legacy_alphabetical(rows.encode("cp1252"), "test-source")

    def test_the_legacy_parser_reads_the_gordon_shape(self) -> None:
        rows = (
            "Gordon,,TP,4,01/01/2009,35 51 024,412,"
            '"Now part of (dissolution) - Maintenant partie de (dissolution) - '
            'Gordon/Barrie Island, MU"\r\n'
        )
        events = _parse_legacy_alphabetical(rows.encode("cp1252"), "test-source")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["dissolved"], "Gordon")
        self.assertEqual(events[0]["successor"], "Gordon/Barrie Island")
        self.assertEqual(events[0]["effectiveDate"], "2009-01-01")
        self.assertTrue(events[0]["leviedPropertyTax"])

    def test_the_modern_parser_only_reads_ontario_rows(self) -> None:
        header = "h1,h2,h3,h4,h5,h6,h7,h8,h9,h10,h11,h12,h13\r\n"
        quebec = "2401001,Gainer,MU,5A,desc,2401002,Loser,MU,4,Dissolution,10,01/01/2020,f1\r\n"
        ontario = "3501001,Gainer,MU,5A,desc,3501002,Loser,TP,4,Dissolution,10,01/01/2020,f1\r\n"
        data = (header + quebec + ontario).encode("cp1252")
        events = _parse_gaining_losing(
            data, "test-source", skip=0, losing_code_column=8,
            losing_code_is_description=False,
        )
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["sgcCode"], "3501002")


if __name__ == "__main__":
    unittest.main()
