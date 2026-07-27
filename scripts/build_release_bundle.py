#!/usr/bin/env python3
"""Build one public-only site and atomically seal a release directory."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from lib.path_safety import PathSafetyError, resolve_under_root  # noqa: E402
from verify_data_release import (  # noqa: E402
    BUNDLER_VERSION,
    ReleaseVerificationError,
    content_type_for_path,
    inspect_public_file,
    json_bytes,
    load_json_strict,
    load_release_plan,
    normalize_bundle_path,
    normalized_path_identity,
    project_relative,
    reject_symlink_components,
    routes_for_release_path,
    safe_project_path,
    sha256_file,
    validate_json_schema,
    validate_security_headers,
    verify_release_plan,
    walk_regular_files,
    write_json_atomic,
)
from verify_release_manifest import verify_release_directory  # noqa: E402


APPROVAL_SCHEMA = (
    ROOT / "national" / "schemas" / "release-publication-approval.schema.json"
)
DEPLOYMENT_SCHEMA = ROOT / "national" / "schemas" / "release-deployment.schema.json"


class ReleaseBuildError(ReleaseVerificationError):
    """The public release could not be built without weakening a gate."""


def _parse_timestamp(value: str, *, label: str) -> datetime:
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as exc:
        raise ReleaseBuildError(f"{label} must be canonical UTC RFC 3339") from exc


def _validate_https_url(value: str, *, label: str, trailing_slash: bool = False) -> None:
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ReleaseBuildError(
            f"{label} must be an HTTPS URL without credentials, query, or fragment"
        )
    if trailing_slash and not parsed.path.endswith("/"):
        raise ReleaseBuildError(f"{label} must end with '/'")


def _load_release_control(
    plan: dict[str, Any],
    *,
    project_root: Path,
) -> tuple[Path, dict[str, Any], Path, dict[str, Any]]:
    approval_path = safe_project_path(
        plan["publicationApprovalPath"],
        project_root=project_root,
        label="publication approval",
    )
    deployment_path = safe_project_path(
        plan["deploymentPath"],
        project_root=project_root,
        label="deployment descriptor",
    )
    approval = load_json_strict(approval_path, label="publication approval")
    deployment = load_json_strict(deployment_path, label="deployment descriptor")
    _validate_release_control_documents(plan, approval, deployment)
    return approval_path, approval, deployment_path, deployment


def _validate_release_control_documents(
    plan: dict[str, Any],
    approval: dict[str, Any],
    deployment: dict[str, Any],
) -> None:
    validate_json_schema(
        approval, APPROVAL_SCHEMA, label="publication approval"
    )
    validate_json_schema(
        deployment, DEPLOYMENT_SCHEMA, label="deployment descriptor"
    )
    release_id = plan["releaseId"]
    if approval["releaseId"] != release_id or deployment["releaseId"] != release_id:
        raise ReleaseBuildError(
            "publication approval and deployment descriptor must bind releaseId"
        )
    if not approval["candidateOnly"]:
        if approval["decision"] != "approved":
            raise ReleaseBuildError("non-candidate publication decision is not approved")
        if _parse_timestamp(
            approval["approvedAt"], label="publication approval approvedAt"
        ) > _parse_timestamp(plan["releaseTimestamp"], label="releaseTimestamp"):
            raise ReleaseBuildError("publication approval cannot postdate the release")
        _validate_https_url(approval["correctionsUrl"], label="correctionsUrl")
    if not deployment["candidateOnly"]:
        _validate_https_url(
            deployment["baseUrl"], label="deployment baseUrl", trailing_slash=True
        )
        _validate_https_url(deployment["rollbackUrl"], label="rollbackUrl")


def _safe_release_root(value: Path, *, project_root: Path) -> Path:
    lexical = value if value.is_absolute() else project_root / value
    reject_symlink_components(lexical, root=project_root, label="release root")
    try:
        root = resolve_under_root(
            value,
            project_root=project_root,
            approved_root=project_root,
            label="release root",
            allow_absolute=value.is_absolute(),
        )
    except PathSafetyError as exc:
        raise ReleaseBuildError(str(exc)) from exc
    if root == project_root:
        raise ReleaseBuildError("release root must not be the project root")
    reject_symlink_components(root, root=project_root, label="release root")
    return root


def _run_site_build(plan: dict[str, Any], *, project_root: Path) -> Path:
    site = plan["site"]
    working = safe_project_path(
        site["workingDirectory"],
        project_root=project_root,
        label="site build working directory",
    )
    if not working.is_dir():
        raise ReleaseBuildError(
            f"site build working directory does not exist: {working}"
        )
    output = safe_project_path(
        site["outputDirectory"],
        project_root=project_root,
        label="site build output",
    )
    command = list(site["buildCommand"])
    executable = shutil.which(command[0])
    if executable is None:
        raise ReleaseBuildError(
            f"site build executable was not found: {command[0]}"
        )
    command[0] = executable
    environment = os.environ.copy()
    environment.update(
        {
            "CI": "1",
            "NO_COLOR": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
            "npm_config_audit": "false",
            "npm_config_fund": "false",
            "npm_config_offline": "true",
            "SOURCE_DATE_EPOCH": str(
                int(
                    _parse_timestamp(
                        plan["releaseTimestamp"], label="releaseTimestamp"
                    ).timestamp()
                )
            ),
        }
    )
    try:
        completed = subprocess.run(
            command,
            cwd=working,
            env=environment,
            check=False,
            capture_output=True,
            text=True,
            timeout=site.get("buildTimeoutSeconds", 900),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ReleaseBuildError(f"site build could not complete: {exc}") from exc
    if completed.returncode != 0:
        stderr = completed.stderr.strip().splitlines()
        detail = stderr[-1] if stderr else f"exit {completed.returncode}"
        raise ReleaseBuildError(f"site build failed: {detail}")
    if not output.is_dir():
        raise ReleaseBuildError(f"site build did not create {output}")
    return output


def _copy_public_site(
    source_root: Path,
    destination_root: Path,
    *,
    project_root: Path,
) -> dict[str, str]:
    source_files = walk_regular_files(
        source_root, project_root=project_root, label="site build output"
    )
    if not source_files:
        raise ReleaseBuildError("site build output is empty")
    before = {
        path.relative_to(source_root).as_posix(): sha256_file(path)
        for path in source_files
    }
    destination_root.mkdir(parents=True)
    for source in source_files:
        relative = normalize_bundle_path(
            source.relative_to(source_root).as_posix(), label="public site path"
        )
        target = destination_root / Path(*relative.split("/"))
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            raise ReleaseBuildError(f"duplicate public site target {relative}")
        shutil.copyfile(source, target)
        try:
            inspect_public_file(target, relative=relative)
        except ReleaseVerificationError as exc:
            raise ReleaseBuildError(str(exc)) from exc
    after_files = walk_regular_files(
        source_root, project_root=project_root, label="site build output"
    )
    after = {
        path.relative_to(source_root).as_posix(): sha256_file(path)
        for path in after_files
    }
    if before != after:
        raise ReleaseBuildError("site build output changed while it was staged")
    return before


def _copy_public_artifacts(
    plan: dict[str, Any],
    site_root: Path,
    *,
    project_root: Path,
) -> None:
    artifacts = {item["id"]: item for item in plan["artifacts"]}
    for copy_spec in plan["site"]["publicArtifactCopies"]:
        artifact_id = copy_spec["artifactId"]
        artifact = artifacts.get(artifact_id)
        if artifact is None:
            raise ReleaseBuildError(
                f"public artifact copy references unknown id {artifact_id!r}"
            )
        if artifact["visibility"] != "public":
            raise ReleaseBuildError(
                f"internal artifact {artifact_id!r} cannot enter public site"
            )
        source = safe_project_path(
            artifact["path"],
            project_root=project_root,
            label=f"public artifact {artifact_id}",
        )
        target_relative = normalize_bundle_path(
            copy_spec["target"], label=f"public artifact {artifact_id} target"
        )
        target = site_root / Path(*target_relative.split("/"))
        if target.exists():
            if (
                not target.is_file()
                or target.stat().st_size != artifact["byteLength"]
                or sha256_file(target) != artifact["sha256"]
            ):
                raise ReleaseBuildError(
                    "site build output differs from pinned public artifact "
                    f"{artifact_id}: {target_relative}"
                )
            try:
                inspect_public_file(target, relative=target_relative)
            except ReleaseVerificationError as exc:
                raise ReleaseBuildError(str(exc)) from exc
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        if sha256_file(target) != artifact["sha256"]:
            raise ReleaseBuildError(
                f"public artifact {artifact_id} changed while it was copied"
            )
        try:
            inspect_public_file(target, relative=target_relative)
        except ReleaseVerificationError as exc:
            raise ReleaseBuildError(str(exc)) from exc


def _recheck_verified_inputs(
    verification: dict[str, Any],
    *,
    project_root: Path,
) -> None:
    for group in ("sources", "artifacts"):
        for item in verification[group]:
            path = safe_project_path(
                item["path"],
                project_root=project_root,
                label=f"rechecked {group[:-1]} {item['id']}",
            )
            if path.stat().st_size != item["byteLength"] or sha256_file(path) != item["sha256"]:
                raise ReleaseBuildError(
                    f"{group[:-1]} {item['id']} changed after verification"
                )


def _manifest_files(stage: Path, *, project_root: Path) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for path in walk_regular_files(
        stage, project_root=project_root, label="staged release"
    ):
        relative = normalize_bundle_path(
            path.relative_to(stage).as_posix(), label="release file path"
        )
        if relative == "manifest.json":
            raise ReleaseBuildError("manifest.json appeared before final sealing")
        entries.append(
            {
                "path": relative,
                "sha256": sha256_file(path),
                "byteLength": path.stat().st_size,
                "contentType": content_type_for_path(relative),
                "routes": routes_for_release_path(relative),
            }
        )
    return entries


def _cleanup_stage(stage: Path | None, release_root: Path) -> None:
    if stage is None or stage.is_symlink():
        return
    try:
        stage.resolve(strict=False).relative_to(release_root.resolve(strict=False))
    except ValueError:
        return
    if stage.exists() and stage.is_dir():
        shutil.rmtree(stage)


def build_release(
    plan_path: Path,
    *,
    project_root: Path = ROOT,
    release_root: Path | None = None,
) -> Path:
    project_root = project_root.resolve(strict=False)
    plan, _safe_plan, plan_sha = load_release_plan(
        plan_path, project_root=project_root
    )
    verification = verify_release_plan(plan_path, project_root=project_root)
    approval_path, approval, deployment_path, deployment = _load_release_control(
        plan, project_root=project_root
    )
    root = _safe_release_root(
        release_root or project_root / "release",
        project_root=project_root,
    )
    root.mkdir(parents=True, exist_ok=True)
    reject_symlink_components(root, root=project_root, label="release root")
    destination = root / plan["releaseId"]
    if destination.exists() or destination.is_symlink():
        raise ReleaseBuildError(
            f"immutable release destination already exists: {destination}"
        )

    output = safe_project_path(
        plan["site"]["outputDirectory"],
        project_root=project_root,
        label="site build output",
    )
    try:
        output.resolve(strict=False).relative_to(root.resolve(strict=False))
    except ValueError:
        pass
    else:
        raise ReleaseBuildError("site build output must be outside the release root")

    # This is the sole invocation of the site builder.
    built_site = _run_site_build(plan, project_root=project_root)
    stage: Path | None = Path(
        tempfile.mkdtemp(prefix=f".{plan['releaseId']}.", dir=root)
    )
    try:
        site_stage = stage / "site"
        _copy_public_site(
            built_site, site_stage, project_root=project_root
        )
        _copy_public_artifacts(plan, site_stage, project_root=project_root)

        required = {
            normalize_bundle_path(item, label="required site file")
            for item in plan["site"]["requiredFiles"]
        }
        actual = {
            path.relative_to(site_stage).as_posix()
            for path in walk_regular_files(
                site_stage, project_root=project_root, label="public site"
            )
        }
        missing = sorted(required - actual)
        if missing:
            raise ReleaseBuildError(
                "public site is missing required files: " + ", ".join(missing)
            )

        write_json_atomic(stage / "verification.json", verification)
        shutil.copyfile(approval_path, stage / "publication-approval.json")
        shutil.copyfile(deployment_path, stage / "deployment.json")
        _recheck_verified_inputs(verification, project_root=project_root)

        headers = plan["site"]["securityHeaders"]
        validate_security_headers(headers)
        entries = _manifest_files(stage, project_root=project_root)
        verification_entry = next(
            item for item in entries if item["path"] == "verification.json"
        )
        manifest = {
            "schemaVersion": "auditback-data-release-manifest-1.0.0",
            "releaseId": plan["releaseId"],
            "releaseTimestamp": plan["releaseTimestamp"],
            "planSha256": plan_sha,
            "verificationSha256": verification_entry["sha256"],
            "publicationStatus": (
                "candidate" if approval["candidateOnly"] else "approved"
            ),
            "deploymentStatus": (
                "candidate" if deployment["candidateOnly"] else "attested"
            ),
            "tools": verification["tools"],
            "git": verification["git"],
            "securityHeaders": headers,
            "files": entries,
        }
        # The manifest is intentionally the final file written.
        write_json_atomic(stage / "manifest.json", manifest)
        verify_release_directory(
            stage, project_root=project_root, release_root=root
        )
        stage.replace(destination)
        stage = None
    except Exception:
        _cleanup_stage(stage, root)
        raise
    return destination


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build once and atomically seal a public-only release"
    )
    parser.add_argument(
        "--plan",
        type=Path,
        default=ROOT / "release" / "release-plan.json",
    )
    parser.add_argument("--release-root", type=Path, default=ROOT / "release")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = make_parser().parse_args(argv)
    try:
        destination = build_release(
            args.plan,
            release_root=args.release_root,
        )
    except (
        OSError,
        ReleaseVerificationError,
        subprocess.SubprocessError,
        ValueError,
    ) as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 1
    print(
        f"Sealed public release {destination.relative_to(ROOT).as_posix()} "
        f"with {BUNDLER_VERSION}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
