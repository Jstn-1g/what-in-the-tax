#!/usr/bin/env python3
"""Re-derive every entry in a sealed release manifest from disk."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from lib.path_safety import PathSafetyError, resolve_under_root  # noqa: E402
from verify_data_release import (  # noqa: E402
    MANIFEST_VERIFIER_VERSION,
    ReleaseVerificationError,
    content_type_for_path,
    load_json_strict,
    normalize_bundle_path,
    normalized_path_identity,
    routes_for_release_path,
    reject_symlink_components,
    sha256_file,
    validate_json_schema,
    validate_security_headers,
    walk_regular_files,
)


MANIFEST_SCHEMA = (
    ROOT / "national" / "schemas" / "data-release-manifest.schema.json"
)
APPROVAL_SCHEMA = (
    ROOT / "national" / "schemas" / "release-publication-approval.schema.json"
)
DEPLOYMENT_SCHEMA = (
    ROOT / "national" / "schemas" / "release-deployment.schema.json"
)
REQUIRED_ROOT_FILES = frozenset(
    {"deployment.json", "publication-approval.json", "verification.json"}
)


class ManifestVerificationError(ReleaseVerificationError):
    """The release manifest and release directory did not agree exactly."""


def _safe_release_dir(
    value: Path,
    *,
    project_root: Path,
    release_root: Path,
) -> Path:
    lexical = value if value.is_absolute() else project_root / value
    reject_symlink_components(
        lexical, root=project_root, label="release directory"
    )
    try:
        return resolve_under_root(
            value,
            project_root=project_root,
            approved_root=release_root,
            label="release directory",
            allow_absolute=value.is_absolute(),
        )
    except PathSafetyError as exc:
        raise ManifestVerificationError(str(exc)) from exc


def verify_release_directory(
    release_dir: Path,
    *,
    project_root: Path = ROOT,
    release_root: Path | None = None,
    require_publication_approval: bool = False,
    require_deployment_attestation: bool = False,
) -> dict[str, Any]:
    project_root = project_root.resolve(strict=False)
    approved = (release_root or project_root / "release").resolve(strict=False)
    directory = _safe_release_dir(
        release_dir,
        project_root=project_root,
        release_root=approved,
    )
    files = walk_regular_files(
        directory,
        project_root=project_root,
        label="sealed release",
    )
    manifest_path = directory / "manifest.json"
    if manifest_path not in files:
        raise ManifestVerificationError("sealed release is missing manifest.json")
    manifest = load_json_strict(manifest_path, label="release manifest")
    validate_json_schema(manifest, MANIFEST_SCHEMA, label="release manifest")
    validate_security_headers(manifest["securityHeaders"])

    manifest_entries: dict[str, dict[str, Any]] = {}
    identities: dict[str, str] = {}
    route_owners: dict[str, str] = {}
    for index, entry in enumerate(manifest["files"]):
        path = normalize_bundle_path(
            entry["path"], label=f"manifest files[{index}].path"
        )
        identity = normalized_path_identity(path)
        if identity in identities:
            raise ManifestVerificationError(
                f"duplicate/colliding manifest paths "
                f"{identities[identity]!r} and {path!r}"
            )
        identities[identity] = path
        manifest_entries[path] = entry
        expected_routes = routes_for_release_path(path)
        if entry["routes"] != expected_routes:
            raise ManifestVerificationError(
                f"{path}: routes are not the deterministic path-derived routes; "
                f"expected {expected_routes!r}"
            )
        for route in entry["routes"]:
            owner = route_owners.get(route)
            if owner is not None:
                raise ManifestVerificationError(
                    f"route {route!r} belongs to both {owner!r} and {path!r}"
                )
            route_owners[route] = path

    disk_paths = {
        path.relative_to(directory).as_posix()
        for path in files
        if path != manifest_path
    }
    declared_paths = set(manifest_entries)
    if disk_paths != declared_paths:
        missing = sorted(declared_paths - disk_paths)
        extra = sorted(disk_paths - declared_paths)
        details: list[str] = []
        if missing:
            details.append("missing from disk: " + ", ".join(missing))
        if extra:
            details.append("unmanifested on disk: " + ", ".join(extra))
        raise ManifestVerificationError(
            "manifest/disk mismatch in both-directions check ("
            + "; ".join(details)
            + ")"
        )
    missing_roots = sorted(REQUIRED_ROOT_FILES - disk_paths)
    if missing_roots:
        raise ManifestVerificationError(
            "release is missing required root files: " + ", ".join(missing_roots)
        )
    if not any(path.startswith("site/") for path in disk_paths):
        raise ManifestVerificationError("release contains no public site files")

    for relative in sorted(disk_paths):
        path = directory / Path(*PurePathParts(relative))
        entry = manifest_entries[relative]
        observed_size = path.stat().st_size
        if observed_size != entry["byteLength"]:
            raise ManifestVerificationError(
                f"{relative}: expected {entry['byteLength']} bytes, "
                f"observed {observed_size}"
            )
        observed_hash = sha256_file(path)
        if observed_hash != entry["sha256"]:
            raise ManifestVerificationError(
                f"{relative}: SHA-256 mismatch; expected {entry['sha256']}, "
                f"observed {observed_hash}"
            )
        expected_type = content_type_for_path(relative)
        if entry["contentType"] != expected_type:
            raise ManifestVerificationError(
                f"{relative}: content type must be {expected_type!r}"
            )

    verification_hash = manifest_entries["verification.json"]["sha256"]
    if manifest["verificationSha256"] != verification_hash:
        raise ManifestVerificationError(
            "manifest verificationSha256 differs from verification.json entry"
        )
    verification = load_json_strict(
        directory / "verification.json", label="release verification"
    )
    if verification.get("result") != "ok":
        raise ManifestVerificationError("release verification result is not ok")
    if verification.get("releaseId") != manifest["releaseId"]:
        raise ManifestVerificationError(
            "release verification identity differs from manifest"
        )
    if verification.get("plan", {}).get("sha256") != manifest["planSha256"]:
        raise ManifestVerificationError(
            "release verification plan hash differs from manifest"
        )
    if verification.get("git") != manifest["git"]:
        raise ManifestVerificationError(
            "release verification Git identity differs from manifest"
        )
    if verification.get("tools") != manifest["tools"]:
        raise ManifestVerificationError(
            "release verification tool versions differ from manifest"
        )
    approval = load_json_strict(
        directory / "publication-approval.json", label="publication-approval.json"
    )
    deployment = load_json_strict(
        directory / "deployment.json", label="deployment.json"
    )
    validate_json_schema(
        approval, APPROVAL_SCHEMA, label="publication approval"
    )
    validate_json_schema(
        deployment, DEPLOYMENT_SCHEMA, label="deployment descriptor"
    )
    for name, document in (
        ("publication-approval.json", approval),
        ("deployment.json", deployment),
    ):
        if document.get("releaseId") != manifest["releaseId"]:
            raise ManifestVerificationError(f"{name} releaseId differs from manifest")
    expected_publication_status = (
        "candidate" if approval["candidateOnly"] else "approved"
    )
    expected_deployment_status = (
        "candidate" if deployment["candidateOnly"] else "attested"
    )
    if manifest["publicationStatus"] != expected_publication_status:
        raise ManifestVerificationError(
            "manifest publicationStatus differs from approval record"
        )
    if manifest["deploymentStatus"] != expected_deployment_status:
        raise ManifestVerificationError(
            "manifest deploymentStatus differs from deployment record"
        )
    if require_publication_approval and (
        manifest["publicationStatus"] != "approved"
        or approval["candidateOnly"] is not False
        or approval["decision"] != "approved"
    ):
        raise ManifestVerificationError(
            "release does not have sealed publication approval"
        )
    if require_deployment_attestation and (
        manifest["deploymentStatus"] != "attested"
        or deployment["candidateOnly"] is not False
    ):
        raise ManifestVerificationError(
            "release does not have a sealed deployment attestation"
        )

    return {
        "schemaVersion": "auditback-release-manifest-check-1.0.0",
        "releaseId": manifest["releaseId"],
        "manifestSha256": sha256_file(manifest_path),
        "fileCount": len(disk_paths),
        "routeCount": sum(len(entry["routes"]) for entry in manifest_entries.values()),
        "checker": MANIFEST_VERIFIER_VERSION,
        "result": "ok",
    }


def PurePathParts(value: str) -> tuple[str, ...]:
    """Convert a validated POSIX path without accepting host separators."""

    return tuple(value.split("/"))


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Verify a sealed release manifest against disk in both directions"
    )
    parser.add_argument("--release-dir", type=Path, required=True)
    parser.add_argument(
        "--require-publication-approval",
        action="store_true",
        help="Fail unless the sealed release has a completed publication approval",
    )
    parser.add_argument(
        "--require-deployment-attestation",
        action="store_true",
        help="Fail unless the sealed release has a completed deployment descriptor",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = make_parser().parse_args(argv)
    try:
        result = verify_release_directory(
            args.release_dir,
            require_publication_approval=args.require_publication_approval,
            require_deployment_attestation=args.require_deployment_attestation,
        )
    except (OSError, ReleaseVerificationError, ValueError) as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 1
    print(
        f"Verified sealed release {result['releaseId']}: "
        f"{result['fileCount']} files, {result['routeCount']} routes."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
