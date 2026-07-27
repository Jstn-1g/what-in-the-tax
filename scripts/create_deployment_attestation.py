#!/usr/bin/env python3
"""Create an external attestation after an exact Cloudflare promotion."""

from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import unquote, urlsplit, urlunsplit


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from verify_data_release import (  # noqa: E402
    ReleaseVerificationError,
    load_json_strict,
    require_regular_file,
    safe_project_path,
    sha256_file,
    validate_json_schema,
    write_json_atomic,
)
from verify_release_manifest import verify_release_directory  # noqa: E402


ATTESTATION_SCHEMA = (
    ROOT / "national" / "schemas" / "post-deployment-attestation.schema.json"
)
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
CLOUDFLARE_VERSION_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-"
    r"[0-9a-f]{4}-[0-9a-f]{12}$"
)
RUN_ID_RE = re.compile(r"^[1-9][0-9]*$")
UTC_SECONDS_RE = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T"
    r"[0-9]{2}:[0-9]{2}:[0-9]{2}Z$"
)


class DeploymentAttestationError(ReleaseVerificationError):
    """A deployment attestation input did not bind the sealed release."""


def _validate_https_url(value: str, *, label: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or "\\" in value
        or any(ord(character) < 0x20 for character in value)
    ):
        raise DeploymentAttestationError(f"{label} must be a plain HTTPS URL")
    try:
        parsed = urlsplit(value)
        parsed_port = parsed.port
    except ValueError as exc:
        raise DeploymentAttestationError(f"{label} is not a valid HTTPS URL") from exc
    if (
        parsed.scheme != "https"
        or not parsed.netloc
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise DeploymentAttestationError(
            f"{label} must be HTTPS without credentials, query, or fragment"
        )
    if parsed_port is not None and parsed_port != 443:
        raise DeploymentAttestationError(f"{label} must use the standard HTTPS port")
    try:
        decoded_path = unquote(parsed.path, errors="strict")
    except UnicodeError as exc:
        raise DeploymentAttestationError(f"{label} has an invalid encoded path") from exc
    path_parts = PurePosixPath(decoded_path or "/").parts
    if any(part in {".", ".."} for part in path_parts):
        raise DeploymentAttestationError(f"{label} contains an unsafe path component")
    path = parsed.path or "/"
    if not path.endswith("/"):
        path += "/"
    return urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))


def _validate_timestamp(value: str) -> str:
    if not isinstance(value, str) or UTC_SECONDS_RE.fullmatch(value) is None:
        raise DeploymentAttestationError(
            "deployedAt must be an explicit UTC timestamp to whole seconds"
        )
    try:
        datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as exc:
        raise DeploymentAttestationError("deployedAt is not a real UTC timestamp") from exc
    return value


def _validate_verification_report(
    path: Path,
    *,
    role: str,
    project_root: Path,
    release_id: str,
    manifest_sha256: str,
    expected_base_url: str,
) -> str:
    report_path = safe_project_path(
        path,
        project_root=project_root,
        label=f"{role} verification report",
        allow_absolute=True,
    )
    require_regular_file(
        report_path,
        project_root=project_root,
        label=f"{role} verification report",
    )
    report = load_json_strict(
        report_path, label=f"{role} deployment verification report"
    )
    if not isinstance(report, dict):
        raise DeploymentAttestationError(f"{role} verification report must be an object")
    if report.get("schemaVersion") != (
        "auditback-deployed-release-verification-1.0.0"
    ):
        raise DeploymentAttestationError(
            f"{role} verification report has an unsupported schemaVersion"
        )
    if report.get("result") != "ok":
        raise DeploymentAttestationError(
            f"{role} verification report result is not ok"
        )
    if report.get("releaseId") != release_id:
        raise DeploymentAttestationError(
            f"{role} verification report releaseId differs from the manifest"
        )
    reported_manifest = report.get("manifestSha256")
    if (
        not isinstance(reported_manifest, str)
        or SHA256_RE.fullmatch(reported_manifest) is None
        or reported_manifest != manifest_sha256
    ):
        raise DeploymentAttestationError(
            f"{role} verification report manifest hash differs from the seal"
        )
    reported_base = report.get("baseUrl")
    if not isinstance(reported_base, str):
        raise DeploymentAttestationError(
            f"{role} verification report baseUrl is missing"
        )
    normalized_reported_base = _validate_https_url(
        reported_base, label=f"{role} verification report baseUrl"
    )
    if normalized_reported_base != expected_base_url:
        raise DeploymentAttestationError(
            f"{role} verification report baseUrl differs from the supplied URL"
        )
    route_count = report.get("routeCount")
    routes = report.get("routes")
    if (
        isinstance(route_count, bool)
        or not isinstance(route_count, int)
        or route_count < 1
        or not isinstance(routes, list)
        or len(routes) != route_count
    ):
        raise DeploymentAttestationError(
            f"{role} verification report has an invalid route count"
        )
    return sha256_file(report_path)


def create_deployment_attestation(
    release_dir: Path,
    *,
    preview_verification: Path,
    production_verification: Path,
    commit_sha: str,
    new_version_id: str,
    previous_version_id: str,
    preview_url: str,
    production_url: str,
    validation_run_id: str,
    deployed_at: str,
    project_root: Path = ROOT,
    release_root: Path | None = None,
) -> dict[str, Any]:
    project_root = project_root.resolve(strict=False)
    release_root = (release_root or project_root / "release").resolve(strict=False)
    verified = verify_release_directory(
        release_dir,
        project_root=project_root,
        release_root=release_root,
    )
    directory = (
        release_dir
        if release_dir.is_absolute()
        else project_root / release_dir
    ).resolve(strict=False)
    manifest = load_json_strict(
        directory / "manifest.json", label="sealed release manifest"
    )
    manifest_sha256 = verified["manifestSha256"]

    if not isinstance(commit_sha, str) or COMMIT_RE.fullmatch(commit_sha) is None:
        raise DeploymentAttestationError("commitSha must be a lowercase 40-hex SHA")
    if manifest.get("git", {}).get("commit") != commit_sha:
        raise DeploymentAttestationError("commitSha differs from the sealed manifest")
    for label, value in (
        ("newVersionId", new_version_id),
        ("previousVersionId", previous_version_id),
    ):
        if (
            not isinstance(value, str)
            or CLOUDFLARE_VERSION_RE.fullmatch(value) is None
        ):
            raise DeploymentAttestationError(
                f"{label} must be a lowercase UUID-shaped Cloudflare version ID"
            )
    if new_version_id == previous_version_id:
        raise DeploymentAttestationError(
            "newVersionId and previousVersionId must differ"
        )
    if (
        not isinstance(validation_run_id, str)
        or RUN_ID_RE.fullmatch(validation_run_id) is None
    ):
        raise DeploymentAttestationError(
            "validationRunId must be a positive decimal identifier"
        )

    normalized_preview_url = _validate_https_url(preview_url, label="previewUrl")
    normalized_production_url = _validate_https_url(
        production_url, label="productionUrl"
    )
    if normalized_preview_url == normalized_production_url:
        raise DeploymentAttestationError("previewUrl and productionUrl must differ")

    preview_hash = _validate_verification_report(
        preview_verification,
        role="preview",
        project_root=project_root,
        release_id=manifest["releaseId"],
        manifest_sha256=manifest_sha256,
        expected_base_url=normalized_preview_url,
    )
    production_hash = _validate_verification_report(
        production_verification,
        role="production",
        project_root=project_root,
        release_id=manifest["releaseId"],
        manifest_sha256=manifest_sha256,
        expected_base_url=normalized_production_url,
    )
    if preview_hash == production_hash:
        raise DeploymentAttestationError(
            "preview and production verification reports must be distinct"
        )

    attestation = {
        "schemaVersion": "auditback-post-deployment-attestation-1.0.0",
        "result": "attested",
        "releaseId": manifest["releaseId"],
        "manifestSha256": manifest_sha256,
        "commitSha": commit_sha,
        "newVersionId": new_version_id,
        "previousVersionId": previous_version_id,
        "previewUrl": normalized_preview_url,
        "productionUrl": normalized_production_url,
        "validationRunId": validation_run_id,
        "previewVerificationSha256": preview_hash,
        "productionVerificationSha256": production_hash,
        "deployedAt": _validate_timestamp(deployed_at),
    }
    validate_json_schema(
        attestation,
        ATTESTATION_SCHEMA,
        label="post-deployment attestation",
    )
    return attestation


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Bind an exact Cloudflare promotion to a sealed release and two "
            "successful deployment verification reports"
        )
    )
    parser.add_argument("--release-dir", type=Path, required=True)
    parser.add_argument("--preview-verification", type=Path, required=True)
    parser.add_argument("--production-verification", type=Path, required=True)
    parser.add_argument("--commit-sha", required=True)
    parser.add_argument("--new-version-id", required=True)
    parser.add_argument("--previous-version-id", required=True)
    parser.add_argument("--preview-url", required=True)
    parser.add_argument("--production-url", required=True)
    parser.add_argument("--validation-run-id", required=True)
    parser.add_argument("--deployed-at", required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main(
    argv: list[str] | None = None,
    *,
    project_root: Path = ROOT,
) -> int:
    args = make_parser().parse_args(argv)
    try:
        project_root = project_root.resolve(strict=False)
        release_dir = (
            args.release_dir
            if args.release_dir.is_absolute()
            else project_root / args.release_dir
        ).resolve(strict=False)
        output = safe_project_path(
            args.output,
            project_root=project_root,
            label="attestation output",
            allow_absolute=True,
        )
        try:
            output.relative_to(release_dir)
        except ValueError:
            pass
        else:
            raise DeploymentAttestationError(
                "attestation output cannot be inside the sealed release"
            )
        if output.exists():
            raise DeploymentAttestationError(
                "attestation output already exists and will not be overwritten"
            )
        attestation = create_deployment_attestation(
            args.release_dir,
            preview_verification=args.preview_verification,
            production_verification=args.production_verification,
            commit_sha=args.commit_sha,
            new_version_id=args.new_version_id,
            previous_version_id=args.previous_version_id,
            preview_url=args.preview_url,
            production_url=args.production_url,
            validation_run_id=args.validation_run_id,
            deployed_at=args.deployed_at,
            project_root=project_root,
            release_root=project_root / "release",
        )
        write_json_atomic(output, attestation)
    except (OSError, ReleaseVerificationError, ValueError) as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 1
    print(
        f"Attested Cloudflare deployment {attestation['newVersionId']} "
        f"for sealed release {attestation['releaseId']}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
