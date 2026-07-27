#!/usr/bin/env python3
"""Fetch every manifest route and compare exact deployed response bytes."""

from __future__ import annotations

import argparse
import hashlib
import ipaddress
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlsplit, urlunsplit


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from verify_data_release import (  # noqa: E402
    DEPLOYMENT_VERIFIER_VERSION,
    ReleaseVerificationError,
    load_json_strict,
    sha256_file,
    write_json_atomic,
)
from verify_release_manifest import verify_release_directory  # noqa: E402


class DeployedReleaseError(ReleaseVerificationError):
    """A deployed response differed from the sealed release."""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> None:
        return None


def _normal_header(value: str) -> str:
    return " ".join(value.strip().split())


def _content_type_matches(observed: str, expected: str) -> bool:
    observed_parts = [part.strip() for part in observed.split(";")]
    if observed_parts[0].casefold() != expected.casefold():
        return False
    parameters: dict[str, str] = {}
    for part in observed_parts[1:]:
        if "=" not in part:
            return False
        name, value = (field.strip().casefold() for field in part.split("=", 1))
        if name in parameters:
            return False
        parameters[name] = value.strip('"')
    return not parameters or parameters == {"charset": "utf-8"}


def _validate_base_url(value: str, *, allow_http_loopback: bool = False) -> str:
    parsed = urlsplit(value)
    permitted_http = False
    if allow_http_loopback and parsed.scheme == "http" and parsed.hostname:
        try:
            permitted_http = ipaddress.ip_address(parsed.hostname).is_loopback
        except ValueError:
            permitted_http = parsed.hostname.casefold() == "localhost"
    if (
        (parsed.scheme != "https" and not permitted_http)
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise DeployedReleaseError(
            "deployment base URL must be HTTPS without credentials, query, or fragment"
        )
    path = parsed.path or "/"
    if not path.endswith("/"):
        path += "/"
    return urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))


def _route_url(base_url: str, route: str) -> str:
    parsed = urlsplit(base_url)
    base_path = parsed.path
    route_path = route.removeprefix("/")
    combined = base_path + route_path
    candidate = urlunsplit((parsed.scheme, parsed.netloc, combined, "", ""))
    checked = urlsplit(candidate)
    if checked.scheme != parsed.scheme or checked.netloc != parsed.netloc:
        raise DeployedReleaseError(f"route escaped deployment origin: {route!r}")
    if not checked.path.startswith(base_path):
        raise DeployedReleaseError(f"route escaped deployment base path: {route!r}")
    return candidate


def fetch_response(url: str, *, timeout: float) -> tuple[int, dict[str, str], bytes]:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "*/*",
            "Accept-Encoding": "identity",
            "Cache-Control": "no-cache",
            "User-Agent": DEPLOYMENT_VERIFIER_VERSION,
        },
        method="GET",
    )
    opener = urllib.request.build_opener(_NoRedirect)
    try:
        with opener.open(request, timeout=timeout) as response:
            status = int(response.status)
            headers = {
                name.casefold(): value
                for name, value in response.headers.items()
            }
            body = response.read()
    except urllib.error.HTTPError as exc:
        raise DeployedReleaseError(
            f"{url} returned HTTP {exc.code}; redirects and errors are refused"
        ) from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise DeployedReleaseError(f"cannot fetch {url}: {exc}") from exc
    return status, headers, body


def verify_deployed_release(
    release_dir: Path,
    *,
    project_root: Path = ROOT,
    release_root: Path | None = None,
    base_url: str | None = None,
    timeout: float = 20.0,
    fetcher: Callable[[str, float], tuple[int, dict[str, str], bytes]] | None = None,
    allow_http_loopback: bool = False,
    allow_candidate_deployment: bool = False,
) -> dict[str, Any]:
    local = verify_release_directory(
        release_dir,
        project_root=project_root,
        release_root=release_root,
    )
    directory = (
        release_dir
        if release_dir.is_absolute()
        else project_root.resolve(strict=False) / release_dir
    ).resolve(strict=False)
    manifest_path = directory / "manifest.json"
    manifest = load_json_strict(manifest_path, label="release manifest")
    deployment = load_json_strict(
        directory / "deployment.json", label="deployment descriptor"
    )
    approval = load_json_strict(
        directory / "publication-approval.json", label="publication approval"
    )
    if (
        manifest["publicationStatus"] != "approved"
        or approval.get("candidateOnly") is not False
        or approval.get("decision") != "approved"
    ):
        raise DeployedReleaseError(
            "candidate/pending release cannot pass the publication deployment gate"
        )
    deployment_is_attested = (
        manifest["deploymentStatus"] == "attested"
        and deployment.get("candidateOnly") is False
        and bool(deployment.get("baseUrl"))
        and bool(deployment.get("immutableVersion"))
        and bool(deployment.get("rollbackUrl"))
    )
    deployment_is_candidate = (
        manifest["deploymentStatus"] == "candidate"
        and deployment.get("candidateOnly") is True
        and deployment.get("baseUrl") is None
        and deployment.get("immutableVersion") is None
        and deployment.get("rollbackUrl") is None
    )
    if deployment_is_attested:
        descriptor_base = _validate_base_url(
            deployment["baseUrl"],
            allow_http_loopback=allow_http_loopback,
        )
        if base_url is not None:
            requested_base = _validate_base_url(
                base_url,
                allow_http_loopback=allow_http_loopback,
            )
            if requested_base != descriptor_base:
                raise DeployedReleaseError(
                    "base URL override differs from the sealed deployment descriptor"
                )
        selected_base = descriptor_base
        deployment_binding = "sealed-attestation"
    elif allow_candidate_deployment and deployment_is_candidate:
        if base_url is None:
            raise DeployedReleaseError(
                "candidate preview verification requires an explicit base URL"
            )
        selected_base = _validate_base_url(
            base_url,
            allow_http_loopback=allow_http_loopback,
        )
        deployment_binding = "candidate-preview"
    else:
        raise DeployedReleaseError(
            "deployment descriptor is still candidate or incomplete"
        )
    security_headers = {
        name.casefold(): _normal_header(value)
        for name, value in manifest["securityHeaders"].items()
    }
    route_results: list[dict[str, Any]] = []
    perform_fetch = fetcher or (
        lambda url, seconds: fetch_response(url, timeout=seconds)
    )
    for entry in manifest["files"]:
        for route in entry["routes"]:
            url = _route_url(selected_base, route)
            status, raw_headers, body = perform_fetch(url, timeout)
            headers = {
                name.casefold(): _normal_header(value)
                for name, value in raw_headers.items()
            }
            if status != 200:
                raise DeployedReleaseError(
                    f"{route} returned HTTP {status}, expected 200"
                )
            if len(body) != entry["byteLength"]:
                raise DeployedReleaseError(
                    f"{route} body length differs: expected {entry['byteLength']}, "
                    f"observed {len(body)}"
                )
            observed_hash = hashlib.sha256(body).hexdigest()
            if observed_hash != entry["sha256"]:
                raise DeployedReleaseError(
                    f"{route} body SHA-256 differs: expected {entry['sha256']}, "
                    f"observed {observed_hash}"
                )
            content_type = headers.get("content-type")
            if content_type is None or not _content_type_matches(
                content_type, entry["contentType"]
            ):
                raise DeployedReleaseError(
                    f"{route} Content-Type differs: expected "
                    f"{entry['contentType']!r}, observed {content_type!r}"
                )
            content_encoding = headers.get("content-encoding")
            if content_encoding not in (None, "identity"):
                raise DeployedReleaseError(
                    f"{route} ignored identity encoding: {content_encoding!r}"
                )
            for name, expected in security_headers.items():
                observed = headers.get(name)
                if observed != expected:
                    raise DeployedReleaseError(
                        f"{route} security header {name!r} differs: "
                        f"expected {expected!r}, observed {observed!r}"
                    )
            declared_length = headers.get("content-length")
            if declared_length is not None:
                try:
                    parsed_length = int(declared_length)
                except ValueError as exc:
                    raise DeployedReleaseError(
                        f"{route} has invalid Content-Length {declared_length!r}"
                    ) from exc
                if parsed_length != len(body):
                    raise DeployedReleaseError(
                        f"{route} Content-Length differs from response bytes"
                    )
            route_results.append(
                {
                    "route": route,
                    "path": entry["path"],
                    "sha256": observed_hash,
                    "byteLength": len(body),
                    "contentType": content_type,
                    "securityHeaders": "exact",
                }
            )
    if not route_results:
        raise DeployedReleaseError("manifest contains no deployable routes")
    return {
        "schemaVersion": "auditback-deployed-release-verification-1.0.0",
        "releaseId": manifest["releaseId"],
        "releaseTimestamp": manifest["releaseTimestamp"],
        "baseUrl": selected_base,
        "deploymentBinding": deployment_binding,
        "manifestSha256": local["manifestSha256"],
        "result": "ok",
        "routeCount": len(route_results),
        "routes": route_results,
        "checker": DEPLOYMENT_VERIFIER_VERSION,
    }


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Verify deployed bytes, media types, and headers against a seal"
    )
    parser.add_argument("--release-dir", type=Path, required=True)
    parser.add_argument("--base-url")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument(
        "--allow-candidate-deployment",
        action="store_true",
        help=(
            "Verify an approved release at an explicit inactive preview URL "
            "before the separate post-deployment attestation exists"
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = make_parser().parse_args(argv)
    try:
        if args.timeout <= 0 or args.timeout > 120:
            raise DeployedReleaseError("timeout must be in (0, 120] seconds")
        result = verify_deployed_release(
            args.release_dir,
            base_url=args.base_url,
            timeout=args.timeout,
            allow_candidate_deployment=args.allow_candidate_deployment,
        )
        if args.output is not None:
            release = args.release_dir.resolve(strict=False)
            output = args.output.resolve(strict=False)
            try:
                output.relative_to(release)
            except ValueError:
                pass
            else:
                raise DeployedReleaseError(
                    "deployment verification output cannot mutate the sealed release"
                )
            try:
                output.relative_to(ROOT.resolve(strict=False))
            except ValueError as exc:
                raise DeployedReleaseError(
                    "deployment verification output must stay in the project"
                ) from exc
            write_json_atomic(output, result)
    except (OSError, ReleaseVerificationError, ValueError) as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 1
    print(
        f"Verified deployed release {result['releaseId']}: "
        f"{result['routeCount']} exact routes."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
