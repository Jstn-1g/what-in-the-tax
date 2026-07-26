from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.lib.path_safety import PathSafetyError
from scripts.lock_pack_sources import build_source_lock


class SourceLockTests(unittest.TestCase):
    def test_binds_source_and_extract_bytes_deterministically(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source-pdfs" / "source.pdf"
            extract = root / "data" / "_extracts" / "source.txt"
            ledger = root / "data" / "evidence-ledger.json"
            source.parent.mkdir(parents=True)
            extract.parent.mkdir(parents=True)
            source.write_bytes(b"official source bytes")
            extract.write_text("page-bound extract", encoding="utf-8")
            ledger.write_text(
                json.dumps(
                    {
                        "sources": [
                            {
                                "id": "official",
                                "url": "https://example.invalid/source.pdf",
                                "localPath": "source-pdfs/source.pdf",
                                "extractedText": "data/_extracts/source.txt",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            first = build_source_lock(ledger, project_root=root)
            second = build_source_lock(ledger, project_root=root)

            self.assertEqual(first, second)
            entry = first["sources"][0]
            self.assertEqual(entry["lockStatus"], "source-and-extract")
            self.assertEqual(len(entry["sha256"]), 64)
            self.assertEqual(len(entry["extractedTextSha256"]), 64)

    def test_remote_source_stays_explicitly_unlocked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ledger = root / "data" / "evidence-ledger.json"
            ledger.parent.mkdir(parents=True)
            ledger.write_text(
                json.dumps({"sources": [{"id": "remote", "url": "https://example.invalid"}]}),
                encoding="utf-8",
            )

            lock = build_source_lock(ledger, project_root=root)

            self.assertEqual(lock["sources"][0]["lockStatus"], "remote-unlocked")

    def test_pack_paths_cannot_escape_approved_roots(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ledger = root / "data" / "evidence-ledger.json"
            ledger.parent.mkdir(parents=True)
            ledger.write_text(
                json.dumps(
                    {
                        "sources": [
                            {
                                "id": "malicious",
                                "localPath": "../outside.pdf",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaises(PathSafetyError):
                build_source_lock(ledger, project_root=root)


if __name__ == "__main__":
    unittest.main()
