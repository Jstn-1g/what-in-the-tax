from __future__ import annotations

import json
import os
import unittest
from unittest.mock import patch

from scripts.build_fir_fleet_dry_run import (
    SLC_GG_BEFORE,
    SLC_POP,
    build_stub,
    resolve_built_at,
)


class FirReproducibilityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.rows = {
            "municipalityDesc": "Example Tp",
            "tierCode": "LT",
            "rows": {
                SLC_POP: {"amount": 4_000},
                SLC_GG_BEFORE: {"amount": 1_000_000},
            },
        }

    def test_default_content_has_no_wall_clock_timestamp(self) -> None:
        first = build_stub("2023", "9999", self.rows, "a" * 64, "fir.zip")
        second = build_stub("2023", "9999", self.rows, "a" * 64, "fir.zip")

        self.assertIsNotNone(first)
        self.assertEqual(first, second)
        self.assertNotIn("builtAt", first)
        self.assertEqual(
            json.dumps(first, sort_keys=True),
            json.dumps(second, sort_keys=True),
        )

    def test_source_date_epoch_is_canonical_utc(self) -> None:
        with patch.dict(os.environ, {"SOURCE_DATE_EPOCH": "0"}, clear=False):
            self.assertEqual(resolve_built_at(), "1970-01-01T00:00:00+00:00")

    def test_explicit_build_timestamp_is_normalized(self) -> None:
        self.assertEqual(
            resolve_built_at("2026-07-25T16:00:00-04:00"),
            "2026-07-25T20:00:00+00:00",
        )

    def test_naive_or_invalid_timestamps_fail_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "timezone"):
            resolve_built_at("2026-07-25T20:00:00")
        with patch.dict(os.environ, {"SOURCE_DATE_EPOCH": "tomorrow"}, clear=False):
            with self.assertRaisesRegex(ValueError, "integer"):
                resolve_built_at()


if __name__ == "__main__":
    unittest.main()
