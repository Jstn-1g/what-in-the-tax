from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))

from build_release_bundle import build_release
from create_deployment_attestation import (
    DeploymentAttestationError,
    create_deployment_attestation,
    main,
)
from test_release_core import ReleaseFixture
from verify_data_release import load_json_strict, sha256_file


NEW_VERSION = "11111111-2222-3333-4444-555555555555"
PREVIOUS_VERSION = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
PREVIEW_URL = "https://11111111.example.workers.dev/"
PRODUCTION_URL = "https://example.workers.dev/"
DEPLOYED_AT = "2026-07-27T03:04:05Z"


class DeploymentAttestationTests(unittest.TestCase):
    def build_release_and_reports(
        self, root: Path
    ) -> tuple[Path, Path, Path, str]:
        fixture = ReleaseFixture(root)
        subprocess.run(["git", "init", "-q"], cwd=root, check=True)
        subprocess.run(
            ["git", "config", "user.email", "release-test@example.invalid"],
            cwd=root,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Release Test"],
            cwd=root,
            check=True,
        )
        subprocess.run(["git", "add", "."], cwd=root, check=True)
        subprocess.run(
            ["git", "commit", "-qm", "sealed fixture"], cwd=root, check=True
        )
        release = build_release(
            fixture.plan_path,
            project_root=root,
            release_root=root / "release",
        )
        manifest = load_json_strict(
            release / "manifest.json", label="fixture manifest"
        )
        manifest_hash = sha256_file(release / "manifest.json")
        commit_sha = manifest["git"]["commit"]

        def write_report(path: Path, base_url: str) -> None:
            report = {
                "schemaVersion": (
                    "auditback-deployed-release-verification-1.0.0"
                ),
                "releaseId": manifest["releaseId"],
                "releaseTimestamp": manifest["releaseTimestamp"],
                "baseUrl": base_url,
                "deploymentBinding": "candidate-preview",
                "manifestSha256": manifest_hash,
                "result": "ok",
                "routeCount": 1,
                "routes": [
                    {
                        "route": "/",
                        "path": "site/index.html",
                        "sha256": hashlib.sha256(b"fixture").hexdigest(),
                    }
                ],
                "checker": "verify-deployed-release/1.0.0",
            }
            path.write_text(
                json.dumps(report, sort_keys=True, indent=2) + "\n",
                encoding="utf-8",
            )

        reports = root / "deployment-verifications"
        reports.mkdir()
        preview = reports / "preview.json"
        production = reports / "production.json"
        write_report(preview, PREVIEW_URL)
        write_report(production, PRODUCTION_URL)
        return release, preview, production, commit_sha

    def attest(
        self,
        root: Path,
        release: Path,
        preview: Path,
        production: Path,
        sealed_commit_sha: str,
        **overrides,
    ):
        arguments = {
            "preview_verification": preview,
            "production_verification": production,
            "commit_sha": sealed_commit_sha,
            "new_version_id": NEW_VERSION,
            "previous_version_id": PREVIOUS_VERSION,
            "preview_url": PREVIEW_URL,
            "production_url": PRODUCTION_URL,
            "validation_run_id": "987654321",
            "deployed_at": DEPLOYED_AT,
            "project_root": root,
            "release_root": root / "release",
        }
        arguments.update(overrides)
        return create_deployment_attestation(release, **arguments)

    def test_attestation_binds_seal_commit_versions_urls_and_reports(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            release, preview, production, commit_sha = (
                self.build_release_and_reports(root)
            )

            first = self.attest(
                root, release, preview, production, commit_sha
            )
            second = self.attest(
                root, release, preview, production, commit_sha
            )

            self.assertEqual(first, second)
            self.assertEqual(first["result"], "attested")
            self.assertEqual(first["manifestSha256"], sha256_file(release / "manifest.json"))
            self.assertEqual(first["commitSha"], commit_sha)
            self.assertEqual(first["newVersionId"], NEW_VERSION)
            self.assertEqual(first["previousVersionId"], PREVIOUS_VERSION)
            self.assertEqual(first["previewVerificationSha256"], sha256_file(preview))
            self.assertEqual(
                first["productionVerificationSha256"], sha256_file(production)
            )
            self.assertEqual(first["deployedAt"], DEPLOYED_AT)

    def test_report_result_release_manifest_and_base_url_are_all_enforced(self) -> None:
        mutations = {
            "result": ("result", "failed", "result is not ok"),
            "release": ("releaseId", "other-release", "releaseId differs"),
            "manifest": ("manifestSha256", "0" * 64, "manifest hash differs"),
            "base": (
                "baseUrl",
                "https://wrong.example.invalid/",
                "baseUrl differs",
            ),
        }
        for name, (field, value, message) in mutations.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                release, preview, production, commit_sha = (
                    self.build_release_and_reports(root)
                )
                report = load_json_strict(preview, label="preview")
                report[field] = value
                preview.write_text(
                    json.dumps(report, sort_keys=True, indent=2) + "\n",
                    encoding="utf-8",
                )
                with self.assertRaisesRegex(DeploymentAttestationError, message):
                    self.attest(
                        root, release, preview, production, commit_sha
                    )

    def test_invalid_cloudflare_id_commit_timestamp_and_urls_are_rejected(self) -> None:
        cases = {
            "version": (
                {"new_version_id": "not-a-version"},
                "UUID-shaped",
            ),
            "same-version": (
                {"new_version_id": PREVIOUS_VERSION},
                "must differ",
            ),
            "commit": (
                {"commit_sha": "0" * 40},
                "differs from the sealed manifest",
            ),
            "timestamp": (
                {"deployed_at": "2026-02-30T03:04:05Z"},
                "not a real UTC timestamp",
            ),
            "preview-url": (
                {"preview_url": "http://11111111.example.workers.dev/"},
                "must be HTTPS",
            ),
            "same-url": (
                {"preview_url": PRODUCTION_URL},
                "must differ",
            ),
            "run-id": (
                {"validation_run_id": "0"},
                "positive decimal",
            ),
        }
        for name, (overrides, message) in cases.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                release, preview, production, commit_sha = (
                    self.build_release_and_reports(root)
                )
                with self.assertRaisesRegex(DeploymentAttestationError, message):
                    self.attest(
                        root,
                        release,
                        preview,
                        production,
                        commit_sha,
                        **overrides,
                    )

    def test_cli_refuses_output_inside_seal_and_does_not_write(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            release, preview, production, commit_sha = (
                self.build_release_and_reports(root)
            )
            output = release / "post-deployment-attestation.json"
            result = main(
                [
                    "--release-dir",
                    str(release),
                    "--preview-verification",
                    str(preview),
                    "--production-verification",
                    str(production),
                    "--commit-sha",
                    commit_sha,
                    "--new-version-id",
                    NEW_VERSION,
                    "--previous-version-id",
                    PREVIOUS_VERSION,
                    "--preview-url",
                    PREVIEW_URL,
                    "--production-url",
                    PRODUCTION_URL,
                    "--validation-run-id",
                    "987654321",
                    "--deployed-at",
                    DEPLOYED_AT,
                    "--output",
                    str(output),
                ],
                project_root=root,
            )
            self.assertEqual(result, 1)
            self.assertFalse(output.exists())

    def test_cli_writes_one_external_immutable_attestation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            release, preview, production, commit_sha = (
                self.build_release_and_reports(root)
            )
            output = root / "deployment-attestations" / "fixture-release.json"
            arguments = [
                "--release-dir",
                str(release),
                "--preview-verification",
                str(preview),
                "--production-verification",
                str(production),
                "--commit-sha",
                commit_sha,
                "--new-version-id",
                NEW_VERSION,
                "--previous-version-id",
                PREVIOUS_VERSION,
                "--preview-url",
                PREVIEW_URL,
                "--production-url",
                PRODUCTION_URL,
                "--validation-run-id",
                "987654321",
                "--deployed-at",
                DEPLOYED_AT,
                "--output",
                str(output),
            ]

            self.assertEqual(main(arguments, project_root=root), 0)
            attestation = load_json_strict(output, label="attestation")
            self.assertEqual(attestation["result"], "attested")
            original_hash = sha256_file(output)

            self.assertEqual(main(arguments, project_root=root), 1)
            self.assertEqual(sha256_file(output), original_hash)


if __name__ == "__main__":
    unittest.main()
