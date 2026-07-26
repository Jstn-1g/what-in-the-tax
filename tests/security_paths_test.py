from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from subprocess import CompletedProcess
from unittest import mock

import yaml
from pypdf import PdfWriter


REPO_ROOT = Path(__file__).resolve().parents[1]


def load_script(name: str, relative_path: str):
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / relative_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load {relative_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


extract_pdf_text = load_script(
    "security_test_extract_pdf_text", "scripts/extract_pdf_text.py"
)
seal_pack = load_script("security_test_seal_pack", "scripts/seal_pack.py")
validate_pack = load_script("security_test_validate_pack", "scripts/validate_pack.py")


def write_pdf(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    with path.open("wb") as handle:
        writer.write(handle)


class ExtractPathSecurityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base = Path(self.temp_dir.name)
        self.root = self.base / "repo"
        self.source_root = self.root / "source-pdfs"
        self.extract_root = self.root / "data" / "_extracts"
        self.source_root.mkdir(parents=True)
        self.extract_root.mkdir(parents=True)
        self.pdf = self.source_root / "input.pdf"
        write_pdf(self.pdf)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def run_extract(self, args: list[str]) -> int:
        with (
            mock.patch.object(extract_pdf_text, "ROOT", self.root),
            mock.patch.object(extract_pdf_text, "SOURCE", self.source_root),
            mock.patch.object(extract_pdf_text, "OUT", self.extract_root),
        ):
            return extract_pdf_text.main(args)

    def write_manifest(self, document: dict) -> Path:
        path = self.base / "manifest.yaml"
        path.write_text(yaml.safe_dump(document), encoding="utf-8")
        return path

    def test_manifest_absolute_output_cannot_escape_extract_root(self) -> None:
        escaped = self.base / "escaped.txt"
        manifest = self.write_manifest(
            {
                "files": [
                    {
                        "pdf": "source-pdfs/input.pdf",
                        "out": str(escaped),
                    }
                ]
            }
        )

        rc = self.run_extract(["--manifest", str(manifest)])

        self.assertEqual(2, rc)
        self.assertFalse(escaped.exists())

    def test_manifest_parent_output_cannot_escape_extract_root(self) -> None:
        escaped = self.base / "escaped.txt"
        manifest = self.write_manifest(
            {
                "files": [
                    {
                        "pdf": "source-pdfs/input.pdf",
                        "out": "../escaped.txt",
                    }
                ]
            }
        )

        rc = self.run_extract(["--manifest", str(manifest)])

        self.assertEqual(2, rc)
        self.assertFalse(escaped.exists())

    def test_manifest_absolute_input_cannot_read_outside_source_root(self) -> None:
        outside_pdf = self.base / "outside" / "input.pdf"
        write_pdf(outside_pdf)
        output = self.extract_root / "stolen.txt"
        manifest = self.write_manifest(
            {
                "files": [
                    {
                        "pdf": str(outside_pdf),
                        "out": "data/_extracts/stolen.txt",
                    }
                ]
            }
        )

        rc = self.run_extract(["--manifest", str(manifest)])

        self.assertEqual(2, rc)
        self.assertFalse(output.exists())

    def test_pack_slug_traversal_is_rejected_before_manifest_load(self) -> None:
        malicious_pack = self.root / "evil"
        malicious_pack.mkdir()
        (malicious_pack / "build-inputs.yaml").write_text(
            yaml.safe_dump(
                {
                    "extract": {
                        "files": [
                            {
                                "pdf": "source-pdfs/input.pdf",
                                "out": "data/_extracts/escaped.txt",
                            }
                        ]
                    }
                }
            ),
            encoding="utf-8",
        )

        rc = self.run_extract(["--pack", "../evil"])

        self.assertEqual(2, rc)
        self.assertFalse((self.extract_root / "escaped.txt").exists())

    def test_output_symlink_cannot_escape_extract_root(self) -> None:
        outside = self.base / "outside"
        outside.mkdir()
        link = self.extract_root / "linked"
        try:
            os.symlink(outside, link, target_is_directory=True)
        except OSError as exc:
            self.skipTest(f"directory symlinks unavailable: {exc}")
        manifest = self.write_manifest(
            {
                "files": [
                    {
                        "pdf": "source-pdfs/input.pdf",
                        "out": "data/_extracts/linked/escaped.txt",
                    }
                ]
            }
        )

        rc = self.run_extract(["--manifest", str(manifest)])

        self.assertEqual(2, rc)
        self.assertFalse((outside / "escaped.txt").exists())

    def test_input_symlink_cannot_escape_source_root(self) -> None:
        outside_pdf = self.base / "outside" / "input.pdf"
        write_pdf(outside_pdf)
        link = self.source_root / "linked.pdf"
        try:
            os.symlink(outside_pdf, link)
        except OSError as exc:
            self.skipTest(f"file symlinks unavailable: {exc}")
        output = self.extract_root / "stolen.txt"
        manifest = self.write_manifest(
            {
                "files": [
                    {
                        "pdf": "source-pdfs/linked.pdf",
                        "out": "data/_extracts/stolen.txt",
                    }
                ]
            }
        )

        rc = self.run_extract(["--manifest", str(manifest)])

        self.assertEqual(2, rc)
        self.assertFalse(output.exists())

    def test_valid_manifest_extracts_under_approved_roots(self) -> None:
        output = self.extract_root / "valid" / "input.txt"
        manifest = self.write_manifest(
            {
                "files": [
                    {
                        "pdf": "source-pdfs/input.pdf",
                        "out": "data/_extracts/valid/input.txt",
                    }
                ]
            }
        )

        rc = self.run_extract(["--manifest", str(manifest)])

        self.assertEqual(0, rc)
        self.assertTrue(output.exists())
        self.assertIn("===== PAGE 1 =====", output.read_text(encoding="utf-8"))

    def test_documented_explicit_pdf_workflow_remains_valid(self) -> None:
        output = self.extract_root / "explicit" / "input.txt"

        rc = self.run_extract(
            [
                str(Path("source-pdfs") / "input.pdf"),
                "--out-dir",
                str(Path("data") / "_extracts" / "explicit"),
            ]
        )

        self.assertEqual(0, rc)
        self.assertTrue(output.exists())


class SealPathSecurityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base = Path(self.temp_dir.name)
        self.root = self.base / "repo"
        self.data_root = self.root / "data"
        self.corpus_root = self.root / "corpus"
        self.receipts_root = self.root / "receipts"
        self.slug = "safe-town-on"
        self.pack_dir = self.corpus_root / self.slug
        self.pack_dir.mkdir(parents=True)
        self.receipts_root.mkdir(parents=True)
        self.data_dir = self.data_root / "safe"
        self.data_dir.mkdir(parents=True)
        self.ledger = self.data_dir / "evidence-ledger.json"
        self.receipt = self.data_dir / "taxpayer-receipt.json"
        self.audit = self.data_dir / "citation-audit.json"
        self.report = self.pack_dir / "validation-report.json"
        for path, document in (
            (self.ledger, {"kind": "ledger"}),
            (self.receipt, {"kind": "receipt"}),
            (self.audit, {"kind": "audit"}),
            (self.report, {"ok": True}),
        ):
            path.write_text(json.dumps(document), encoding="utf-8")
        self.write_pack()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def write_pack(
        self,
        *,
        pack_dir: Path | None = None,
        slug: str | None = None,
        year: object = 2026,
        ledger: str = "data/safe/evidence-ledger.json",
        receipt: str = "data/safe/taxpayer-receipt.json",
        source_lock: str | None = None,
    ) -> Path:
        target = pack_dir or self.pack_dir
        target.mkdir(parents=True, exist_ok=True)
        path = target / "pack.json"
        artifacts = {
            "ledger": ledger,
            "receipt": receipt,
        }
        if source_lock is not None:
            artifacts["sourcesLock"] = source_lock
        path.write_text(
            json.dumps(
                {
                    "slug": slug or self.slug,
                    "fiscalYear": year,
                    "artifacts": artifacts,
                }
            ),
            encoding="utf-8",
        )
        return path

    def run_seal(self, slug: str | None = None, revision: str = "1"):
        with (
            mock.patch.object(seal_pack, "ROOT", self.root),
            mock.patch.object(
                seal_pack.subprocess,
                "run",
                return_value=CompletedProcess(args=[], returncode=0),
            ) as validate,
            mock.patch.object(seal_pack, "git_rev", return_value="a" * 40),
        ):
            rc = seal_pack.main(
                ["seal_pack.py", slug if slug is not None else self.slug, revision]
            )
        return rc, validate

    def test_absolute_artifact_path_cannot_be_copied_into_seal(self) -> None:
        outside = self.base / "outside"
        outside.mkdir()
        secret = outside / "secret.json"
        secret.write_text('{"secret": true}', encoding="utf-8")
        (outside / "citation-audit.json").write_text("{}", encoding="utf-8")
        self.write_pack(ledger=str(secret))

        rc, _ = self.run_seal()

        self.assertEqual(1, rc)
        self.assertFalse((self.receipts_root / self.slug / "2026" / "1").exists())

    def test_parent_artifact_path_cannot_be_copied_into_seal(self) -> None:
        outside = self.base / "outside"
        outside.mkdir()
        secret = outside / "secret.json"
        secret.write_text('{"secret": true}', encoding="utf-8")
        (outside / "citation-audit.json").write_text("{}", encoding="utf-8")
        self.write_pack(ledger="../outside/secret.json")

        rc, _ = self.run_seal()

        self.assertEqual(1, rc)
        self.assertFalse((self.receipts_root / self.slug / "2026" / "1").exists())

    def test_slug_traversal_is_rejected_before_validator_runs(self) -> None:
        malicious_dir = self.root / "evil"
        self.write_pack(pack_dir=malicious_dir, slug="../evil")
        (malicious_dir / "validation-report.json").write_text("{}", encoding="utf-8")

        rc, validate = self.run_seal("../evil")

        self.assertEqual(1, rc)
        validate.assert_not_called()
        self.assertFalse((malicious_dir / "2026" / "1").exists())

    def test_year_traversal_cannot_escape_receipts_root(self) -> None:
        self.write_pack(year="../../escaped-seal")

        rc, _ = self.run_seal()

        self.assertEqual(1, rc)
        self.assertFalse((self.root / "escaped-seal" / "1").exists())

    def test_non_positive_revision_is_rejected(self) -> None:
        rc, validate = self.run_seal(revision="-1")

        self.assertEqual(1, rc)
        validate.assert_not_called()
        self.assertFalse((self.receipts_root / self.slug / "2026" / "-1").exists())

    def test_artifact_symlink_cannot_read_outside_data_root(self) -> None:
        outside = self.base / "outside"
        outside.mkdir()
        secret = outside / "secret.json"
        secret.write_text('{"secret": true}', encoding="utf-8")
        link = self.data_dir / "linked-ledger.json"
        try:
            os.symlink(secret, link)
        except OSError as exc:
            self.skipTest(f"file symlinks unavailable: {exc}")
        self.write_pack(ledger="data/safe/linked-ledger.json")

        rc, _ = self.run_seal()

        self.assertEqual(1, rc)
        self.assertFalse((self.receipts_root / self.slug / "2026" / "1").exists())

    def test_output_symlink_cannot_escape_receipts_root(self) -> None:
        outside = self.base / "outside"
        outside.mkdir()
        link = self.receipts_root / self.slug
        try:
            os.symlink(outside, link, target_is_directory=True)
        except OSError as exc:
            self.skipTest(f"directory symlinks unavailable: {exc}")

        rc, _ = self.run_seal()

        self.assertEqual(1, rc)
        self.assertFalse((outside / "2026" / "1").exists())

    def test_pack_change_during_validation_is_rejected(self) -> None:
        pack_path = self.pack_dir / "pack.json"

        def mutate_pack(*_args, **_kwargs):
            pack_path.write_text('{"slug": "changed-on"}', encoding="utf-8")
            return CompletedProcess(args=[], returncode=0)

        with (
            mock.patch.object(seal_pack, "ROOT", self.root),
            mock.patch.object(
                seal_pack.subprocess,
                "run",
                side_effect=mutate_pack,
            ),
            mock.patch.object(seal_pack, "git_rev", return_value="a" * 40),
        ):
            rc = seal_pack.main(["seal_pack.py", self.slug, "1"])

        self.assertEqual(1, rc)
        self.assertFalse((self.receipts_root / self.slug / "2026" / "1").exists())

    def test_seal_forces_strict_validation(self) -> None:
        rc, validate = self.run_seal()

        self.assertEqual(0, rc)
        command = validate.call_args.args[0]
        self.assertIn("--strict", command)

    def test_strict_validation_failure_blocks_draft_seal(self) -> None:
        with (
            mock.patch.object(seal_pack, "ROOT", self.root),
            mock.patch.object(
                seal_pack.subprocess,
                "run",
                return_value=CompletedProcess(args=[], returncode=1),
            ) as validate,
            mock.patch.object(seal_pack, "git_rev", return_value="a" * 40),
        ):
            rc = seal_pack.main(["seal_pack.py", self.slug, "1"])

        self.assertEqual(1, rc)
        self.assertIn("--strict", validate.call_args.args[0])
        self.assertFalse((self.receipts_root / self.slug / "2026" / "1").exists())

    def test_declared_source_lock_is_copied_and_manifest_hashed(self) -> None:
        source_lock = self.pack_dir / "sources.lock.json"
        source_lock.write_text('{"schemaVersion":"source-lock-1.0.0"}', encoding="utf-8")
        self.write_pack(
            source_lock=f"corpus/{self.slug}/sources.lock.json",
        )

        rc, _ = self.run_seal()

        output = self.receipts_root / self.slug / "2026" / "1"
        manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
        copied_lock = output / "sources.lock.json"
        self.assertEqual(0, rc)
        self.assertEqual(source_lock.read_bytes(), copied_lock.read_bytes())
        self.assertEqual(
            seal_pack.sha256_file(copied_lock),
            manifest["files"]["sources.lock.json"],
        )

    def test_declared_source_lock_cannot_escape_pack_directory(self) -> None:
        outside = self.corpus_root / "other-on" / "sources.lock.json"
        outside.parent.mkdir()
        outside.write_text("{}", encoding="utf-8")
        self.write_pack(source_lock="corpus/other-on/sources.lock.json")

        rc, validate = self.run_seal()

        self.assertEqual(1, rc)
        validate.assert_not_called()
        self.assertFalse((self.receipts_root / self.slug / "2026" / "1").exists())

    def test_missing_declared_source_lock_is_rejected_before_validation(self) -> None:
        self.write_pack(
            source_lock=f"corpus/{self.slug}/missing-sources.lock.json",
        )

        rc, validate = self.run_seal()

        self.assertEqual(1, rc)
        validate.assert_not_called()
        self.assertFalse((self.receipts_root / self.slug / "2026" / "1").exists())

    def test_declared_source_lock_symlink_cannot_escape_pack_directory(self) -> None:
        outside = self.base / "outside-source-lock.json"
        outside.write_text('{"secret":true}', encoding="utf-8")
        link = self.pack_dir / "sources.lock.json"
        try:
            os.symlink(outside, link)
        except OSError as exc:
            self.skipTest(f"file symlinks unavailable: {exc}")
        self.write_pack(
            source_lock=f"corpus/{self.slug}/sources.lock.json",
        )

        rc, validate = self.run_seal()

        self.assertEqual(1, rc)
        validate.assert_not_called()
        self.assertFalse((self.receipts_root / self.slug / "2026" / "1").exists())

    def test_source_lock_change_during_validation_is_rejected(self) -> None:
        source_lock = self.pack_dir / "sources.lock.json"
        source_lock.write_text('{"version":1}', encoding="utf-8")
        self.write_pack(
            source_lock=f"corpus/{self.slug}/sources.lock.json",
        )

        def mutate_source_lock(*_args, **_kwargs):
            source_lock.write_text('{"version":2}', encoding="utf-8")
            return CompletedProcess(args=[], returncode=0)

        with (
            mock.patch.object(seal_pack, "ROOT", self.root),
            mock.patch.object(
                seal_pack.subprocess,
                "run",
                side_effect=mutate_source_lock,
            ),
            mock.patch.object(seal_pack, "git_rev", return_value="a" * 40),
        ):
            rc = seal_pack.main(["seal_pack.py", self.slug, "1"])

        self.assertEqual(1, rc)
        self.assertFalse((self.receipts_root / self.slug / "2026" / "1").exists())

    def test_valid_pack_seals_under_receipts_root(self) -> None:
        rc, validate = self.run_seal()

        output = self.receipts_root / self.slug / "2026" / "1"
        self.assertEqual(0, rc)
        validate.assert_called_once()
        self.assertTrue((output / "manifest.json").exists())
        self.assertEqual(
            {"kind": "ledger"},
            json.loads((output / "evidence-ledger.json").read_text(encoding="utf-8")),
        )


class StrictValidatorIntegrationTests(unittest.TestCase):
    def test_strict_flag_promotes_draft_provenance_warnings_to_errors(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "repo"
            slug = "warning-town-on"
            pack_dir = root / "corpus" / slug
            data_dir = root / "data" / "warning-town"
            pack_dir.mkdir(parents=True)
            data_dir.mkdir(parents=True)
            ledger_rel = "data/warning-town/evidence-ledger.json"
            receipt_rel = "data/warning-town/taxpayer-receipt.json"
            (pack_dir / "pack.json").write_text(
                json.dumps(
                    {
                        "slug": slug,
                        "name": "Warning Town",
                        "level": "lower-tier",
                        "fiscalYear": 2026,
                        "currency": "CAD",
                        "assessmentCode": "9999",
                        "publication": {"status": "draft"},
                        "artifacts": {
                            "ledger": ledger_rel,
                            "receipt": receipt_rel,
                        },
                    }
                ),
                encoding="utf-8",
            )
            (data_dir / "evidence-ledger.json").write_text(
                json.dumps(
                    {
                        "schemaVersion": "2.0.0",
                        "artifact": "EvidenceLedger",
                        "fiscalYear": 2026,
                        "currency": "CAD",
                        "jurisdiction": {
                            "slug": slug,
                            "name": "Warning Town",
                            "level": "lower-tier",
                            "assessmentCode": "9999",
                        },
                        "sources": [
                            {
                                "id": "SOURCE",
                                "title": "Remote source",
                                "url": "https://example.invalid/source.pdf",
                            }
                        ],
                        "facts": [
                            {
                                "id": "FACT",
                                "sourceId": "SOURCE",
                                "page": 1,
                                "label": "Example amount",
                                "amountCad": 1,
                                "excerpt": "$1",
                            }
                        ],
                        "derived": [],
                        "gaps": [],
                    }
                ),
                encoding="utf-8",
            )
            (data_dir / "taxpayer-receipt.json").write_text(
                json.dumps(
                    {
                        "schemaVersion": "2.0.0",
                        "artifact": "TaxpayerReceipt",
                        "fiscalYear": 2026,
                        "currency": "CAD",
                        "evidencePolicyRef": ledger_rel,
                        "jurisdiction": {
                            "slug": slug,
                            "displayName": "Warning Town",
                            "level": "lower-tier",
                        },
                        "profiles": {
                            "sample": {
                                "sourceFactId": "FACT",
                            }
                        },
                        "findings": [],
                    }
                ),
                encoding="utf-8",
            )

            with mock.patch.object(validate_pack, "ROOT", root):
                draft_rc = validate_pack.main(
                    ["validate_pack.py", slug, "--no-write"]
                )
                strict_rc = validate_pack.main(
                    ["validate_pack.py", slug, "--strict", "--no-write"]
                )

        self.assertEqual(0, draft_rc)
        self.assertEqual(1, strict_rc)


if __name__ == "__main__":
    unittest.main()
