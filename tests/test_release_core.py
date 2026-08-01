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

from build_release_bundle import ReleaseBuildError, build_release
from verify_data_release import (
    ReleaseVerificationError,
    find_sensitive_strings,
    git_identity,
    json_bytes,
    load_release_plan,
    verify_release_plan,
)
from verify_release_manifest import (
    ManifestVerificationError,
    verify_release_directory,
)


SGC_BYTES = b"""Level,Hierarchical structure,Code,Class title
1,Geographical region of Canada,3,Ontario
2,Province and territory,35,Ontario
3,Census division,3518,Durham
4,Census subdivision,3518013,Oshawa
"""

SECURITY_HEADERS = {
    "Content-Security-Policy": (
        "default-src 'self'; base-uri 'self'; object-src 'none'; "
        "frame-ancestors 'none'; script-src 'self'"
    ),
    "Permissions-Policy": "camera=(), geolocation=(), microphone=()",
    "Referrer-Policy": "no-referrer",
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "X-Robots-Tag": "noindex, nofollow",
}


def digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


class ReleaseFixture:
    def __init__(
        self,
        root: Path,
        *,
        approved: bool = False,
        deployment_attested: bool | None = None,
    ) -> None:
        self.root = root
        (root / "inputs").mkdir(parents=True)
        (root / "artifacts").mkdir()
        source = root / "inputs" / "sgc.csv"
        source.write_bytes(SGC_BYTES)
        artifact_payload = (
            json.dumps(
                {"schemaVersion": "fixture-1", "records": [{"id": "safe"}]},
                sort_keys=True,
                indent=2,
            )
            + "\n"
        ).encode()
        artifact = root / "artifacts" / "registry.json"
        artifact.write_bytes(artifact_payload)
        candidate = not approved
        deployment_candidate = not (
            approved if deployment_attested is None else deployment_attested
        )
        approval = {
            "schemaVersion": "auditback-release-publication-approval-1.0.0",
            "releaseId": "fixture-release",
            "candidateOnly": candidate,
            "decision": None if candidate else "approved",
            "publisher": None if candidate else "Fixture Publisher",
            "publisherContact": None if candidate else "corrections@example.invalid",
            "approvedBy": None if candidate else "Fixture Reviewer",
            "approvedAt": None if candidate else "2026-07-25T12:00:00Z",
            "releaseReference": None if candidate else "fixture/approved",
            "license": None if candidate else "Fixture open licence",
            "correctionsUrl": (
                None if candidate else "https://example.invalid/corrections"
            ),
        }
        deployment = {
            "schemaVersion": "auditback-release-deployment-1.0.0",
            "releaseId": "fixture-release",
            "candidateOnly": deployment_candidate,
            "baseUrl": (
                None
                if deployment_candidate
                else "https://example.invalid/releases/fixture/"
            ),
            "immutableVersion": None if deployment_candidate else "fixture-v1",
            "rollbackUrl": (
                None
                if deployment_candidate
                else "https://example.invalid/rollback/"
            ),
        }
        (root / "approval.json").write_text(
            json.dumps(approval, sort_keys=True), encoding="utf-8"
        )
        (root / "deployment.json").write_text(
            json.dumps(deployment, sort_keys=True), encoding="utf-8"
        )
        builder = (
            "from pathlib import Path; "
            "count=Path('build-count.txt'); "
            "count.write_text(str(int(count.read_text())+1) if count.exists() else '1'); "
            "p=Path('build/site'); p.mkdir(parents=True, exist_ok=True); "
            "(p/'index.html').write_bytes(b'<!doctype html><title>Fixture</title>\\n'); "
            "(p/'privacy.txt').write_bytes(b'No personal data is collected.\\n'); "
            "(p/'_headers').write_bytes(b'/*\\n  X-Content-Type-Options: nosniff\\n')"
        )
        self.plan = {
            "schemaVersion": "auditback-data-release-plan-1.0.0",
            "releaseId": "fixture-release",
            "releaseTimestamp": "2026-07-26T12:00:00Z",
            "toolVersions": {
                "engine": "fixture-engine/1",
                "extractor": "fixture-extractor/1",
                "normalizationLadder": "fixture-normalizer/1",
                "siteBuilder": "fixture-site-builder/1",
            },
            "sources": [
                {
                    "id": "fixture-sgc",
                    "path": "inputs/sgc.csv",
                    "sha256": digest(SGC_BYTES),
                    "byteLength": len(SGC_BYTES),
                    "mediaType": "text/csv",
                    "requestUrl": "https://example.invalid/sgc.csv",
                    "adapter": {
                        "id": "statcan-sgc-structure-csv",
                        "version": "1.0.0",
                        "options": {"classificationYear": "2021"},
                    },
                }
            ],
            "artifacts": [
                {
                    "id": "fixture-registry",
                    "path": "artifacts/registry.json",
                    "sha256": digest(artifact_payload),
                    "byteLength": len(artifact_payload),
                    "mediaType": "application/json",
                    "visibility": "public",
                }
            ],
            "site": {
                "buildCommand": [sys.executable, "-c", builder],
                "buildTimeoutSeconds": 30,
                "workingDirectory": ".",
                "outputDirectory": "build/site",
                "requiredFiles": [
                    "index.html",
                    "privacy.txt",
                    "_headers",
                    "packs/registry.json",
                ],
                "publicArtifactCopies": [
                    {
                        "artifactId": "fixture-registry",
                        "target": "packs/registry.json",
                    }
                ],
                "securityHeaders": SECURITY_HEADERS,
            },
            "publicationApprovalPath": "approval.json",
            "deploymentPath": "deployment.json",
        }
        self.plan_path = root / "release-plan.json"
        self.write_plan()

    def write_plan(self) -> None:
        self.plan_path.write_text(
            json.dumps(self.plan, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )


class ReleaseVerificationTests(unittest.TestCase):
    def test_git_identity_hashes_raw_diff_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
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
            tracked = root / "tracked.txt"
            tracked.write_bytes(b"locked\n")
            subprocess.run(["git", "add", "tracked.txt"], cwd=root, check=True)
            subprocess.run(["git", "commit", "-qm", "fixture"], cwd=root, check=True)

            clean = git_identity(root)
            self.assertEqual(clean["trackedTreeState"], "clean")
            self.assertEqual(clean["trackedDiffSha256"], digest(b""))

            tracked.write_bytes(b"changed\r\n")
            dirty = git_identity(root)
            self.assertEqual(dirty["trackedTreeState"], "dirty")
            self.assertNotEqual(dirty["trackedDiffSha256"], clean["trackedDiffSha256"])

    def test_locked_inputs_and_adapter_are_verified_twice_deterministically(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = ReleaseFixture(Path(temporary))
            first = verify_release_plan(
                fixture.plan_path, project_root=fixture.root
            )
            second = verify_release_plan(
                fixture.plan_path, project_root=fixture.root
            )

            self.assertEqual(json_bytes(first), json_bytes(second))
            self.assertEqual(first["counts"]["adapterRuns"], 2)
            self.assertEqual(
                first["sources"][0]["adapter"]["counts"]["geographies"], 4
            )
            self.assertEqual(first["runtimeNetworkCalls"], 0)

    def test_changed_source_bytes_fail_the_lock(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = ReleaseFixture(Path(temporary))
            (fixture.root / "inputs" / "sgc.csv").write_bytes(SGC_BYTES + b"\n")
            with self.assertRaisesRegex(
                ReleaseVerificationError, "source fixture-sgc hash mismatch"
            ):
                verify_release_plan(fixture.plan_path, project_root=fixture.root)

    def test_duplicate_json_keys_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "release-plan.json"
            path.write_text(
                '{"schemaVersion":"x","schemaVersion":"y"}', encoding="utf-8"
            )
            with self.assertRaisesRegex(
                ReleaseVerificationError, "duplicate JSON key"
            ):
                load_release_plan(path, project_root=root)

    def test_sensitive_values_are_found_even_under_safe_keys(self) -> None:
        matches = find_sensitive_strings(
            {
                "publisher": {
                    "name": "Project publisher",
                    "bio": "Contact alice@example.com or 519-555-0123.",
                }
            }
        )
        self.assertIn("$.publisher.bio (email address)", matches)
        self.assertIn("$.publisher.bio (telephone number)", matches)

    def test_published_corrections_contact_is_exempt_only_in_place(self) -> None:
        published = "mailto:corrections@whatinthetax.com"
        self.assertEqual(
            find_sensitive_strings(
                {"receipt": {"correctionsRoute": {"url": published}}}
            ),
            [],
        )
        self.assertEqual(
            find_sensitive_strings({"publisher": {"bio": published}}),
            ["$.publisher.bio (email address)"],
        )
        self.assertEqual(
            find_sensitive_strings(
                {
                    "receipt": {
                        "correctionsRoute": {"url": "mailto:alice@example.com"}
                    }
                }
            ),
            ["$.receipt.correctionsRoute.url (email address)"],
        )


class ReleaseBundleTests(unittest.TestCase):
    def test_exact_prebuilt_public_artifact_is_bound_without_duplication(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = ReleaseFixture(Path(temporary))
            payload = b"<!doctype html><title>Fixture</title>\n"
            artifact = fixture.root / "artifacts" / "index.html"
            artifact.write_bytes(payload)
            fixture.plan["artifacts"][0].update(
                {
                    "path": "artifacts/index.html",
                    "sha256": digest(payload),
                    "byteLength": len(payload),
                    "mediaType": "text/html",
                }
            )
            fixture.plan["site"]["publicArtifactCopies"] = [
                {"artifactId": "fixture-registry", "target": "index.html"}
            ]
            fixture.plan["site"]["requiredFiles"].remove("packs/registry.json")
            fixture.write_plan()

            output = build_release(
                fixture.plan_path,
                project_root=fixture.root,
                release_root=fixture.root / "release",
            )
            self.assertEqual((output / "site" / "index.html").read_bytes(), payload)

    def test_mismatched_prebuilt_public_artifact_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = ReleaseFixture(Path(temporary))
            fixture.plan["site"]["publicArtifactCopies"] = [
                {"artifactId": "fixture-registry", "target": "index.html"}
            ]
            fixture.write_plan()

            with self.assertRaisesRegex(
                ReleaseBuildError, "differs from pinned public artifact"
            ):
                build_release(
                    fixture.plan_path,
                    project_root=fixture.root,
                    release_root=fixture.root / "release",
                )

    def test_candidate_release_builds_once_and_seals_recursively(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = ReleaseFixture(Path(temporary))
            output = build_release(
                fixture.plan_path,
                project_root=fixture.root,
                release_root=fixture.root / "release",
            )

            self.assertEqual(
                (fixture.root / "build-count.txt").read_text(encoding="utf-8"),
                "1",
            )
            result = verify_release_directory(
                output,
                project_root=fixture.root,
                release_root=fixture.root / "release",
            )
            self.assertEqual(result["result"], "ok")
            manifest = json.loads((output / "manifest.json").read_text())
            self.assertEqual(manifest["publicationStatus"], "candidate")
            self.assertEqual(manifest["deploymentStatus"], "candidate")
            self.assertEqual(
                manifest["files"][-1]["path"], "verification.json"
            )
            routes = {
                route
                for entry in manifest["files"]
                for route in entry["routes"]
            }
            self.assertIn("/", routes)
            self.assertNotIn("/index.html", routes)
            self.assertNotIn("/_headers", routes)
            with self.assertRaisesRegex(
                ManifestVerificationError, "publication approval"
            ):
                verify_release_directory(
                    output,
                    project_root=fixture.root,
                    release_root=fixture.root / "release",
                    require_publication_approval=True,
                )

    def test_publish_gate_accepts_approved_release_with_pending_deployment(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = ReleaseFixture(
                Path(temporary),
                approved=True,
                deployment_attested=False,
            )
            output = build_release(
                fixture.plan_path,
                project_root=fixture.root,
                release_root=fixture.root / "release",
            )
            result = verify_release_directory(
                output,
                project_root=fixture.root,
                release_root=fixture.root / "release",
                require_publication_approval=True,
            )
            self.assertEqual(result["result"], "ok")

    def test_manifest_disk_check_rejects_extra_and_changed_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = ReleaseFixture(Path(temporary))
            output = build_release(
                fixture.plan_path,
                project_root=fixture.root,
                release_root=fixture.root / "release",
            )
            extra = output / "site" / "extra.txt"
            extra.write_bytes(b"stale")
            with self.assertRaisesRegex(
                ManifestVerificationError, "unmanifested on disk"
            ):
                verify_release_directory(
                    output,
                    project_root=fixture.root,
                    release_root=fixture.root / "release",
                )
            extra.unlink()
            (output / "site" / "privacy.txt").write_bytes(b"changed")
            with self.assertRaisesRegex(
                ManifestVerificationError, "SHA-256 mismatch|byte"
            ):
                verify_release_directory(
                    output,
                    project_root=fixture.root,
                    release_root=fixture.root / "release",
                )

    def test_public_copy_rejects_nested_pii_key_and_leaves_no_release(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = ReleaseFixture(Path(temporary))
            payload = b'{"safe":{"owner_name":"private"}}\n'
            artifact = fixture.root / "artifacts" / "registry.json"
            artifact.write_bytes(payload)
            fixture.plan["artifacts"][0]["sha256"] = digest(payload)
            fixture.plan["artifacts"][0]["byteLength"] = len(payload)
            fixture.write_plan()

            with self.assertRaisesRegex(
                ReleaseBuildError, r"PII-ish public JSON keys.*owner_name"
            ):
                build_release(
                    fixture.plan_path,
                    project_root=fixture.root,
                    release_root=fixture.root / "release",
                )
            self.assertFalse(
                (fixture.root / "release" / "fixture-release").exists()
            )

    def test_public_copy_rejects_sensitive_value_and_leaves_no_release(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = ReleaseFixture(Path(temporary))
            payload = b'{"description":"Contact alice@example.com"}\n'
            artifact = fixture.root / "artifacts" / "registry.json"
            artifact.write_bytes(payload)
            fixture.plan["artifacts"][0]["sha256"] = digest(payload)
            fixture.plan["artifacts"][0]["byteLength"] = len(payload)
            fixture.write_plan()

            with self.assertRaisesRegex(
                ReleaseBuildError, r"sensitive public JSON values.*email address"
            ):
                build_release(
                    fixture.plan_path,
                    project_root=fixture.root,
                    release_root=fixture.root / "release",
                )
            self.assertFalse(
                (fixture.root / "release" / "fixture-release").exists()
            )

    def test_internal_artifact_cannot_be_copied_publicly(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = ReleaseFixture(Path(temporary))
            fixture.plan["artifacts"][0]["visibility"] = "internal"
            fixture.write_plan()
            with self.assertRaisesRegex(
                ReleaseBuildError, "internal artifact .* cannot enter public"
            ):
                build_release(
                    fixture.plan_path,
                    project_root=fixture.root,
                    release_root=fixture.root / "release",
                )

    def test_existing_release_is_immutable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = ReleaseFixture(Path(temporary))
            release_root = fixture.root / "release"
            first = build_release(
                fixture.plan_path,
                project_root=fixture.root,
                release_root=release_root,
            )
            manifest_before = (first / "manifest.json").read_bytes()
            with self.assertRaisesRegex(
                ReleaseBuildError, "immutable release destination already exists"
            ):
                build_release(
                    fixture.plan_path,
                    project_root=fixture.root,
                    release_root=release_root,
                )
            self.assertEqual(
                (first / "manifest.json").read_bytes(), manifest_before
            )


class CheckedInReleasePlanTests(unittest.TestCase):
    def test_public_artifact_hashes_bind_checked_in_bytes(self) -> None:
        plan = json.loads(
            (ROOT / "release" / "release-plan.json").read_text(encoding="utf-8")
        )
        for artifact in plan["artifacts"]:
            with self.subTest(artifact=artifact["id"]):
                payload = (ROOT / artifact["path"]).read_bytes()
                self.assertEqual(artifact["byteLength"], len(payload))
                self.assertEqual(artifact["sha256"], digest(payload))

    def test_public_release_text_is_pinned_to_lf(self) -> None:
        attributes = (ROOT / ".gitattributes").read_text(encoding="utf-8")
        self.assertIn("web/public/** text eol=lf", attributes.splitlines())


if __name__ == "__main__":
    unittest.main()
