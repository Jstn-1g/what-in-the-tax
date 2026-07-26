from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "build_national_registry.py"
SGC_SAMPLE = b"""Level,Hierarchical structure,Code,Class title
1,Geographical region of Canada,3,Ontario
2,Province and territory,35,Ontario
3,Census division,3518,Durham
4,Census subdivision,3518013,Oshawa
"""


class NationalRegistryCliTests(unittest.TestCase):
    def test_cli_build_is_offline_reproducible_and_zero_ai(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            work = Path(temporary)
            sgc_path = work / "sgc.csv"
            sgc_path.write_bytes(SGC_SAMPLE)
            digest = hashlib.sha256(SGC_SAMPLE).hexdigest()
            coverage_path = work / "coverage.json"
            coverage_path.write_text(
                json.dumps(
                    {
                        "classificationVersion": "2021",
                        "expectedGeographyCounts": {
                            "region": 1,
                            "province-territory": 1,
                            "census-division": 1,
                            "census-subdivision": 1,
                        },
                        "requiredLayers": ["national-geography-baseline"],
                        "jurisdictions": [
                            {
                                "code": "ON",
                                "name": "Ontario",
                                "expectedCensusSubdivisionCount": 1,
                                "layers": {
                                    "national-geography-baseline": {
                                        "status": "complete",
                                        "sourceIds": [
                                            "statcan-sgc-2021-structure-en"
                                        ],
                                    }
                                },
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            catalog_path = work / "catalog.json"
            catalog_path.write_text(
                json.dumps(
                    {
                        "sources": [
                            {
                                "sourceId": "statcan-sgc-2021-structure-en",
                                "publisher": "Statistics Canada",
                                "jurisdiction": "CA",
                                "coverageLayer": "national-geography-baseline",
                                "classificationVersion": "2021",
                                "requestUrl": (
                                    "https://www.statcan.gc.ca/en/"
                                    "statistical-programs/document/"
                                    "sgc-cgt-2021-structure-eng.csv"
                                ),
                                "mediaType": "text/csv",
                                "adapterId": "statcan-sgc-structure-csv",
                                "adapterVersion": "1.0.0",
                                "runtimeNetworkRequired": False,
                                "approvedSha256": digest,
                                "licenseStatus": "open-licence-confirmed",
                                "licenseUrl": (
                                    "https://www.statcan.gc.ca/en/"
                                    "reference/copyright-permission"
                                ),
                                "reuseReviewRequired": False,
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            output = work / "registry.json"
            lock = work / "sources.lock.json"
            command = [
                sys.executable,
                str(SCRIPT),
                "--sgc-csv",
                str(sgc_path),
                "--sgc-sha256",
                digest,
                "--cache-dir",
                str(work / "cache"),
                "--output",
                str(output),
                "--source-lock-output",
                str(lock),
                "--coverage-plan",
                str(coverage_path),
                "--catalog",
                str(catalog_path),
                "--scope",
                "test",
            ]
            first = subprocess.run(
                command,
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(0, first.returncode, first.stderr)
            self.assertIn("AI calls: 0. AI tokens: 0.", first.stdout)
            first_bytes = output.read_bytes()

            second = subprocess.run(
                command,
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(0, second.returncode, second.stderr)
            self.assertEqual(first_bytes, output.read_bytes())
            registry = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(4, registry["counts"]["geographies"])
            self.assertFalse(registry["method"]["runtimeNetworkRequired"])
            self.assertFalse(registry["method"]["runtimeAiRequired"])
            self.assertEqual("test", registry["buildScope"])

    def test_cli_rejects_unpinned_changed_source(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            work = Path(temporary)
            sgc_path = work / "sgc.csv"
            sgc_path.write_bytes(SGC_SAMPLE)
            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--sgc-csv",
                    str(sgc_path),
                    "--sgc-sha256",
                    "0" * 64,
                    "--cache-dir",
                    str(work / "cache"),
                    "--output",
                    str(work / "registry.json"),
                    "--source-lock-output",
                    str(work / "sources.lock.json"),
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(1, result.returncode)
            self.assertIn("differs from the approved source catalog", result.stderr)


if __name__ == "__main__":
    unittest.main()
