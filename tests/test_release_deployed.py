from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))

from build_release_bundle import build_release
from test_release_core import ReleaseFixture, SECURITY_HEADERS
from verify_data_release import content_type_for_path
from verify_deployed_release import (
    DeployedReleaseError,
    verify_deployed_release,
)


class LocalDeployment:
    def __init__(self, release_dir: Path) -> None:
        self.release_dir = release_dir
        self.calls: list[str] = []
        self.mutate = None

    def __call__(
        self, url: str, _timeout: float
    ) -> tuple[int, dict[str, str], bytes]:
        self.calls.append(url)
        path = urlsplit(url).path
        prefix = "/releases/fixture/"
        if not path.startswith(prefix):
            raise AssertionError(f"escaped fixture prefix: {path}")
        route = path.removeprefix(prefix)
        relative = "index.html" if route in {"", "index.html"} else route
        body = (self.release_dir / "site" / relative).read_bytes()
        headers = {
            **SECURITY_HEADERS,
            "Content-Type": content_type_for_path(f"site/{relative}"),
            "Content-Length": str(len(body)),
        }
        status = 200
        if self.mutate is not None:
            status, headers, body = self.mutate(relative, status, headers, body)
        return status, headers, body


class DeployedReleaseTests(unittest.TestCase):
    def build(
        self,
        root: Path,
        *,
        approved: bool = True,
        deployment_attested: bool | None = None,
    ) -> Path:
        fixture = ReleaseFixture(
            root,
            approved=approved,
            deployment_attested=deployment_attested,
        )
        return build_release(
            fixture.plan_path,
            project_root=root,
            release_root=root / "release",
        )

    def test_every_route_matches_exact_bytes_type_and_headers(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            release = self.build(root)
            deployment = LocalDeployment(release)
            result = verify_deployed_release(
                release,
                project_root=root,
                release_root=root / "release",
                fetcher=deployment,
            )

            self.assertEqual(result["result"], "ok")
            self.assertEqual(result["routeCount"], 3)
            paths = [urlsplit(url).path for url in deployment.calls]
            self.assertIn("/releases/fixture/", paths)
            self.assertNotIn("/releases/fixture/index.html", paths)
            self.assertNotIn("/releases/fixture/_headers", paths)

    def test_candidate_release_cannot_pass_publish_gate(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            release = self.build(root, approved=False)
            deployment = LocalDeployment(release)
            with self.assertRaisesRegex(
                DeployedReleaseError, "candidate/pending release"
            ):
                verify_deployed_release(
                    release,
                    project_root=root,
                    release_root=root / "release",
                    base_url="https://example.invalid/releases/fixture/",
                    fetcher=deployment,
                )
            self.assertEqual(deployment.calls, [])

    def test_approved_release_can_be_verified_at_inactive_candidate_preview(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            release = self.build(
                root,
                approved=True,
                deployment_attested=False,
            )
            deployment = LocalDeployment(release)
            result = verify_deployed_release(
                release,
                project_root=root,
                release_root=root / "release",
                base_url="https://example.invalid/releases/fixture/",
                allow_candidate_deployment=True,
                fetcher=deployment,
            )
            self.assertEqual(result["deploymentBinding"], "candidate-preview")

    def test_candidate_deployment_requires_explicit_preview_flag(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            release = self.build(
                root,
                approved=True,
                deployment_attested=False,
            )
            deployment = LocalDeployment(release)
            with self.assertRaisesRegex(
                DeployedReleaseError, "candidate or incomplete"
            ):
                verify_deployed_release(
                    release,
                    project_root=root,
                    release_root=root / "release",
                    base_url="https://example.invalid/releases/fixture/",
                    fetcher=deployment,
                )
            self.assertEqual(deployment.calls, [])

    def test_spa_html_fallback_for_json_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            release = self.build(root)
            deployment = LocalDeployment(release)

            def fallback(relative, status, headers, body):
                if relative.endswith(".json"):
                    fallback_body = (release / "site" / "index.html").read_bytes()
                    headers["Content-Type"] = "text/html; charset=utf-8"
                    headers["Content-Length"] = str(len(fallback_body))
                    return status, headers, fallback_body
                return status, headers, body

            deployment.mutate = fallback
            with self.assertRaisesRegex(
                DeployedReleaseError, "body length differs|body SHA-256 differs"
            ):
                verify_deployed_release(
                    release,
                    project_root=root,
                    release_root=root / "release",
                    fetcher=deployment,
                )

    def test_wrong_content_type_is_rejected_even_when_body_matches(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            release = self.build(root)
            deployment = LocalDeployment(release)

            def wrong_type(relative, status, headers, body):
                if relative.endswith(".json"):
                    headers["Content-Type"] = "text/html; charset=utf-8"
                return status, headers, body

            deployment.mutate = wrong_type
            with self.assertRaisesRegex(DeployedReleaseError, "Content-Type differs"):
                verify_deployed_release(
                    release,
                    project_root=root,
                    release_root=root / "release",
                    fetcher=deployment,
                )

    def test_utf8_charset_parameter_is_accepted_for_textual_routes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            release = self.build(root)
            deployment = LocalDeployment(release)

            def add_charset(relative, status, headers, body):
                if relative.endswith((".html", ".json", ".txt")):
                    headers["Content-Type"] += "; charset=utf-8"
                return status, headers, body

            deployment.mutate = add_charset
            result = verify_deployed_release(
                release,
                project_root=root,
                release_root=root / "release",
                fetcher=deployment,
            )
            self.assertEqual(result["result"], "ok")

    def test_security_header_drift_on_one_route_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            release = self.build(root)
            deployment = LocalDeployment(release)

            def weaken(relative, status, headers, body):
                if relative == "privacy.txt":
                    headers["Content-Security-Policy"] += "; script-src https:"
                return status, headers, body

            deployment.mutate = weaken
            with self.assertRaisesRegex(
                DeployedReleaseError, "security header .* differs"
            ):
                verify_deployed_release(
                    release,
                    project_root=root,
                    release_root=root / "release",
                    fetcher=deployment,
                )

    def test_platform_injected_bare_noindex_is_accepted(self) -> None:
        # Cloudflare replaces the declared X-Robots-Tag with a bare "noindex"
        # on workers.dev and version-preview hostnames. The verifier accepts
        # any value carrying the noindex token; every other header stays
        # byte-exact.
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            release = self.build(root)
            deployment = LocalDeployment(release)

            def inject(relative, status, headers, body):
                headers["X-Robots-Tag"] = "noindex"
                return status, headers, body

            deployment.mutate = inject
            verify_deployed_release(
                release,
                project_root=root,
                release_root=root / "release",
                fetcher=deployment,
            )

    def test_robots_header_without_noindex_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            release = self.build(root)
            deployment = LocalDeployment(release)

            def weaken(relative, status, headers, body):
                if relative == "privacy.txt":
                    headers["X-Robots-Tag"] = "nofollow"
                return status, headers, body

            deployment.mutate = weaken
            with self.assertRaisesRegex(
                DeployedReleaseError, "lacks noindex"
            ):
                verify_deployed_release(
                    release,
                    project_root=root,
                    release_root=root / "release",
                    fetcher=deployment,
                )

    def test_redirect_is_not_accepted(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            release = self.build(root)
            deployment = LocalDeployment(release)

            def redirect(relative, status, headers, body):
                if relative == "index.html":
                    status = 302
                return status, headers, body

            deployment.mutate = redirect
            with self.assertRaisesRegex(DeployedReleaseError, "HTTP 302"):
                verify_deployed_release(
                    release,
                    project_root=root,
                    release_root=root / "release",
                    fetcher=deployment,
                )


if __name__ == "__main__":
    unittest.main()
