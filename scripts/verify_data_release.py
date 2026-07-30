#!/usr/bin/env python3
"""Verify a release plan entirely from locked local bytes.

The verifier never acquires data. Every source and derived artifact is pinned by
raw SHA-256 and byte length. Supported adapters are constructed twice and their
canonical JSON results must be byte-identical.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import socket
import subprocess
import sys
import unicodedata
import zipfile
from contextlib import contextmanager
from pathlib import Path, PurePosixPath
from typing import Any, Iterator
from unittest.mock import patch
from urllib.parse import quote

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from lib.path_safety import PathSafetyError, resolve_under_root, validate_slug  # noqa: E402
from national.adapters import (  # noqa: E402
    CanonicalDirectoryJsonAdapter,
    StatCanSgcStructureCsvAdapter,
)
from national.models import SourceSnapshot  # noqa: E402


PLAN_SCHEMA = ROOT / "national" / "schemas" / "data-release-plan.schema.json"
CHECKER_VERSION = "verify-data-release/1.0.0"
MANIFEST_VERIFIER_VERSION = "verify-release-manifest/1.0.0"
BUNDLER_VERSION = "build-release-bundle/1.0.0"
DEPLOYMENT_VERIFIER_VERSION = "verify-deployed-release/1.0.0"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
ASCII_BUNDLE_PATH_RE = re.compile(r"^[A-Za-z0-9._~/-]+$", re.ASCII)
CONTROL_FILES = frozenset({"_headers", "_redirects"})

CONTENT_TYPES = {
    ".css": "text/css",
    ".csv": "text/csv",
    ".gif": "image/gif",
    ".html": "text/html",
    ".ico": "image/x-icon",
    ".jpeg": "image/jpeg",
    ".jpg": "image/jpeg",
    ".js": "text/javascript",
    ".json": "application/json",
    ".map": "application/json",
    ".mjs": "text/javascript",
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".svg": "image/svg+xml",
    ".txt": "text/plain",
    ".wasm": "application/wasm",
    ".webp": "image/webp",
    ".woff": "font/woff",
    ".woff2": "font/woff2",
    ".xml": "application/xml",
}

PII_KEY_NORMAL_FORMS = frozenset(
    {
        "accountid",
        "accountno",
        "accountnumber",
        "address",
        "complainttext",
        "customerid",
        "disputetext",
        "email",
        "emailaddress",
        "homeaddress",
        "ipaddress",
        "mailingaddress",
        "owner",
        "ownername",
        "phone",
        "phonenumber",
        "postaladdress",
        "rollno",
        "rollnumber",
        "streetaddress",
        "taxpayername",
        "telephone",
        "closedgaps",
        "extractedtext",
        "localpath",
        "password",
        "searchtrail",
        "secret",
        "suppressed",
        "token",
    }
)
FORBIDDEN_PUBLIC_NAMES = frozenset(
    {
        ".env",
        "attestations.jsonl",
        "corrections.jsonl",
        "disputes.jsonl",
        "evidence-ledger.json",
        "review.jsonl",
        "sources.lock.json",
    }
)
FORBIDDEN_PUBLIC_SUFFIXES = frozenset(
    {".db", ".key", ".log", ".map", ".pem", ".sqlite", ".sqlite3"}
)
FORBIDDEN_PUBLIC_DIRECTORIES = frozenset(
    {".git", "_extracts", "extracts", "node_modules", "source-pdfs"}
)
REQUIRED_SECURITY_HEADERS = frozenset(
    {
        "content-security-policy",
        "permissions-policy",
        "referrer-policy",
        "strict-transport-security",
        "x-content-type-options",
        "x-frame-options",
    }
)
TEXT_SCAN_SUFFIXES = frozenset(
    {".css", ".csv", ".html", ".js", ".json", ".mjs", ".svg", ".txt", ".xml"}
)
# The one address the project deliberately publishes: the corrections route a
# published receipt must carry on its face (PUBLISH.md). Exempt only this exact
# value at exactly a correctionsRoute.url position — the same address anywhere
# else, or any other address in that position, still refuses.
PUBLISHED_CONTACT_ALLOWLIST = frozenset({"mailto:corrections@whatinthetax.com"})
SENSITIVE_TEXT_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "email address",
        re.compile(
            r"(?<![A-Za-z0-9._%+-])[A-Za-z0-9._%+-]+@"
            r"[A-Za-z0-9.-]+\.[A-Za-z]{2,}(?![A-Za-z0-9.-])"
        ),
    ),
    (
        "telephone number",
        re.compile(
            r"(?<!\d)(?:\+?1[\s.-]?)?\(?[2-9]\d{2}\)?"
            r"[\s.-]\d{3}[\s.-]\d{4}(?!\d)"
        ),
    ),
    (
        "Canadian postal code",
        re.compile(
            r"(?<![A-Za-z0-9])[ABCEGHJ-NPRSTVXY]\d[ABCEGHJ-NPRSTVWXYZ]"
            r"[ -]?\d[ABCEGHJ-NPRSTVWXYZ]\d(?![A-Za-z0-9])",
            re.IGNORECASE,
        ),
    ),
    (
        "local filesystem path",
        re.compile(
            r"(?:[A-Za-z]:[\\/](?:Users|Documents and Settings)[\\/]"
            r"|/(?:home|Users)/[A-Za-z0-9._-]+/)",
            re.IGNORECASE,
        ),
    ),
    (
        "private key or access token",
        re.compile(
            r"(?:-----BEGIN [A-Z ]*PRIVATE KEY-----"
            r"|github_pat_[A-Za-z0-9_]{8,}"
            r"|ghp_[A-Za-z0-9]{16,}"
            r"|xox[baprs]-[A-Za-z0-9-]{10,}"
            r"|sk-(?:proj-)?[A-Za-z0-9_-]{12,}"
            r"|AKIA[0-9A-Z]{16}"
            r"|Bearer\s+[A-Za-z0-9._~+/-]{16,})"
        ),
    ),
)


class ReleaseVerificationError(ValueError):
    """A release input or deterministic invariant failed."""


def _duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ReleaseVerificationError(f"duplicate JSON key {key!r}")
        value[key] = item
    return value


def load_json_strict(path: Path, *, label: str) -> Any:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise ReleaseVerificationError(f"cannot read {label}: {path}") from exc

    def reject_constant(value: str) -> None:
        raise ReleaseVerificationError(
            f"{label} contains non-finite JSON number {value}"
        )

    try:
        return json.loads(
            text,
            object_pairs_hook=_duplicate_pairs,
            parse_constant=reject_constant,
        )
    except json.JSONDecodeError as exc:
        raise ReleaseVerificationError(
            f"{label} is invalid JSON at line {exc.lineno}: {exc.msg}"
        ) from exc


def json_bytes(value: Any) -> bytes:
    try:
        return (
            json.dumps(
                value,
                ensure_ascii=False,
                sort_keys=True,
                indent=2,
                allow_nan=False,
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ReleaseVerificationError(
            "release metadata is not strict JSON"
        ) from exc


def sha256_archive_member(path: Path, member: str, *, label: str) -> str:
    """SHA-256 of one member inside a zip, without holding it all in memory."""
    digest = hashlib.sha256()
    try:
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            if names != [member]:
                raise ReleaseVerificationError(
                    f"{label} archive members are {names!r}; expected [{member!r}]"
                )
            with archive.open(member) as raw_member:
                for chunk in iter(lambda: raw_member.read(1 << 20), b""):
                    digest.update(chunk)
    except (OSError, KeyError, zipfile.BadZipFile) as exc:
        raise ReleaseVerificationError(
            f"{label} cannot read {member}: {exc}"
        ) from exc
    return digest.hexdigest()


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_json_schema(
    document: Any,
    schema_path: Path,
    *,
    label: str,
) -> None:
    schema = load_json_strict(schema_path, label=f"{label} schema")
    errors = sorted(
        Draft202012Validator(schema).iter_errors(document),
        key=lambda error: tuple(str(part) for part in error.absolute_path),
    )
    if errors:
        error = errors[0]
        location = ".".join(str(part) for part in error.absolute_path) or "<root>"
        raise ReleaseVerificationError(
            f"{label} schema violation at {location}: {error.message}"
        )


def safe_project_path(
    value: str | Path,
    *,
    project_root: Path,
    label: str,
    base: Path | None = None,
    allow_absolute: bool = False,
) -> Path:
    try:
        candidate = Path(value)
    except TypeError as exc:
        raise ReleaseVerificationError(f"{label} must be a filesystem path") from exc
    lexical = (
        candidate
        if candidate.is_absolute()
        else (base or project_root) / candidate
    )
    reject_symlink_components(lexical, root=project_root, label=label)
    try:
        path = resolve_under_root(
            value,
            project_root=project_root,
            approved_root=project_root,
            label=label,
            base=base,
            allow_absolute=allow_absolute,
        )
    except PathSafetyError as exc:
        raise ReleaseVerificationError(str(exc)) from exc
    reject_symlink_components(path, root=project_root, label=label)
    return path


def reject_symlink_components(path: Path, *, root: Path, label: str) -> None:
    root_resolved = root.resolve(strict=False)
    try:
        relative = path.absolute().relative_to(root.absolute())
    except ValueError as exc:
        raise ReleaseVerificationError(f"{label} escapes project root") from exc
    current = root.absolute()
    if current.is_symlink():
        raise ReleaseVerificationError(f"{label} root must not be a symlink")
    for part in relative.parts:
        current /= part
        if current.is_symlink():
            raise ReleaseVerificationError(f"{label} must not use a symlink: {current}")
    try:
        path.resolve(strict=False).relative_to(root_resolved)
    except ValueError as exc:
        raise ReleaseVerificationError(f"{label} escapes project root") from exc


def require_regular_file(path: Path, *, project_root: Path, label: str) -> Path:
    reject_symlink_components(path, root=project_root, label=label)
    if not path.is_file():
        raise ReleaseVerificationError(f"{label} is not a regular file: {path}")
    return path


def project_relative(path: Path, project_root: Path) -> str:
    try:
        return path.resolve(strict=False).relative_to(
            project_root.resolve(strict=False)
        ).as_posix()
    except ValueError as exc:
        raise ReleaseVerificationError(f"path escapes project: {path}") from exc


def normalize_bundle_path(value: object, *, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ReleaseVerificationError(f"{label} must be a non-empty path")
    if "\\" in value or "\x00" in value or "?" in value or "#" in value:
        raise ReleaseVerificationError(f"{label} must be a plain POSIX path")
    if value.startswith("/") or value.startswith("//") or "%" in value:
        raise ReleaseVerificationError(f"{label} must be an unencoded relative path")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ReleaseVerificationError(f"{label} contains an unsafe path component")
    normalized = unicodedata.normalize("NFC", path.as_posix())
    if normalized != value:
        raise ReleaseVerificationError(f"{label} must use NFC-normalized POSIX text")
    if ASCII_BUNDLE_PATH_RE.fullmatch(normalized) is None:
        raise ReleaseVerificationError(f"{label} must use portable ASCII path characters")
    windows_devices = {
        "aux",
        "con",
        "nul",
        "prn",
        *(f"com{number}" for number in range(1, 10)),
        *(f"lpt{number}" for number in range(1, 10)),
    }
    for part in path.parts:
        if part.endswith((".", " ")):
            raise ReleaseVerificationError(f"{label} has a trailing dot or space")
        if part.split(".", 1)[0].casefold() in windows_devices:
            raise ReleaseVerificationError(f"{label} uses a reserved device name")
    return normalized


def normalized_path_identity(value: str) -> str:
    return unicodedata.normalize("NFC", value).casefold()


def content_type_for_path(path: str) -> str:
    return CONTENT_TYPES.get(PurePosixPath(path).suffix.lower(), "application/octet-stream")


def routes_for_release_path(path: str) -> list[str]:
    normalized = normalize_bundle_path(path, label="manifest file path")
    if not normalized.startswith("site/"):
        return []
    relative = normalized.removeprefix("site/")
    if PurePosixPath(relative).name in CONTROL_FILES:
        return []
    if relative == "index.html":
        # Cloudflare Static Assets canonicalizes /index.html to / with a 307.
        # The manifest verifies the canonical byte-serving route only.
        return ["/"]
    return ["/" + quote(relative, safe="/-._~")]


def walk_regular_files(root: Path, *, project_root: Path, label: str) -> list[Path]:
    reject_symlink_components(root, root=project_root, label=label)
    if not root.is_dir():
        raise ReleaseVerificationError(f"{label} is not a directory: {root}")
    files: list[Path] = []
    seen: dict[str, str] = {}
    for directory, names, filenames in os.walk(root, followlinks=False):
        names.sort()
        filenames.sort()
        directory_path = Path(directory)
        if not names and not filenames:
            raise ReleaseVerificationError(
                f"{label} contains unmanifestable empty directory: {directory_path}"
            )
        for name in list(names):
            child = directory_path / name
            if child.is_symlink():
                raise ReleaseVerificationError(
                    f"{label} contains symlink directory: {child}"
                )
        for name in filenames:
            child = directory_path / name
            if child.is_symlink() or not child.is_file():
                raise ReleaseVerificationError(
                    f"{label} contains symlink or special file: {child}"
                )
            relative = normalize_bundle_path(
                child.relative_to(root).as_posix(),
                label=f"{label} file",
            )
            identity = normalized_path_identity(relative)
            other = seen.get(identity)
            if other is not None:
                raise ReleaseVerificationError(
                    f"{label} has colliding paths {other!r} and {relative!r}"
                )
            seen[identity] = relative
            files.append(child)
    return sorted(files, key=lambda item: item.relative_to(root).as_posix())


def _normal_key(value: str) -> str:
    return "".join(character for character in value.casefold() if character.isalnum())


def find_pii_keys(value: Any, *, location: str = "$") -> list[str]:
    matches: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_location = f"{location}.{key}"
            if _normal_key(key) in PII_KEY_NORMAL_FORMS:
                matches.append(child_location)
            matches.extend(find_pii_keys(child, location=child_location))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            matches.extend(find_pii_keys(child, location=f"{location}[{index}]"))
    return matches


def find_sensitive_strings(value: Any, *, location: str = "$") -> list[str]:
    matches: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            matches.extend(
                find_sensitive_strings(child, location=f"{location}.{key}")
            )
    elif isinstance(value, list):
        for index, child in enumerate(value):
            matches.extend(
                find_sensitive_strings(child, location=f"{location}[{index}]")
            )
    elif isinstance(value, str):
        if (
            location.endswith(".correctionsRoute.url")
            and value in PUBLISHED_CONTACT_ALLOWLIST
        ):
            return matches
        for label, pattern in SENSITIVE_TEXT_PATTERNS:
            if pattern.search(value):
                matches.append(f"{location} ({label})")
    return matches


def find_sensitive_text(value: str) -> list[str]:
    return [
        label
        for label, pattern in SENSITIVE_TEXT_PATTERNS
        if pattern.search(value)
    ]


def validate_security_headers(raw: dict[str, str]) -> dict[str, str]:
    headers: dict[str, str] = {}
    for name, value in raw.items():
        lower = name.casefold()
        if lower in headers:
            raise ReleaseVerificationError(
                f"duplicate security header ignoring case: {name}"
            )
        headers[lower] = value.strip()
    missing = sorted(REQUIRED_SECURITY_HEADERS - set(headers))
    if missing:
        raise ReleaseVerificationError(
            "release plan is missing required security headers: "
            + ", ".join(missing)
        )
    csp_directives: dict[str, list[str]] = {}
    for raw_directive in headers["content-security-policy"].split(";"):
        fields = raw_directive.strip().split()
        if not fields:
            continue
        name, values = fields[0].casefold(), fields[1:]
        if name in csp_directives:
            raise ReleaseVerificationError(
                f"Content-Security-Policy repeats directive {name}"
            )
        csp_directives[name] = values
    required_csp = {
        "default-src": ["'self'"],
        "base-uri": ["'self'"],
        "object-src": ["'none'"],
        "frame-ancestors": ["'none'"],
        "script-src": ["'self'"],
    }
    if any(csp_directives.get(name) != values for name, values in required_csp.items()):
        raise ReleaseVerificationError(
            "Content-Security-Policy is missing a required closed directive"
        )
    flattened_csp = [
        value
        for values in csp_directives.values()
        for value in values
    ]
    if any(
        value in {"'unsafe-eval'", "*"}
        or value.startswith(("http:", "https:"))
        for value in flattened_csp
    ):
        raise ReleaseVerificationError(
            "Content-Security-Policy permits an unsafe script/resource origin"
        )
    if headers["referrer-policy"].casefold() != "no-referrer":
        raise ReleaseVerificationError("Referrer-Policy must be exactly no-referrer")
    if headers["x-content-type-options"].casefold() != "nosniff":
        raise ReleaseVerificationError("X-Content-Type-Options must be exactly nosniff")
    if headers["x-frame-options"].casefold() != "deny":
        raise ReleaseVerificationError("X-Frame-Options must be exactly DENY")
    hsts_parts = {
        part.strip().casefold()
        for part in headers["strict-transport-security"].split(";")
        if part.strip()
    }
    max_age_parts = [
        part for part in hsts_parts if part.startswith("max-age=")
    ]
    try:
        max_age = int(max_age_parts[0].split("=", 1)[1])
    except (IndexError, ValueError) as exc:
        raise ReleaseVerificationError(
            "Strict-Transport-Security has no valid max-age"
        ) from exc
    if len(max_age_parts) != 1 or max_age < 31536000 or "includesubdomains" not in hsts_parts:
        raise ReleaseVerificationError(
            "Strict-Transport-Security must pin at least one year and include subdomains"
        )
    permissions = headers["permissions-policy"].casefold().replace(" ", "")
    for feature in ("camera=()", "geolocation=()", "microphone=()"):
        if feature not in permissions:
            raise ReleaseVerificationError(
                f"Permissions-Policy must disable {feature.removesuffix('=()')}"
            )
    return headers


def inspect_public_file(path: Path, *, relative: str) -> None:
    parts = {part.casefold() for part in PurePosixPath(relative).parts[:-1]}
    forbidden_directories = sorted(parts & FORBIDDEN_PUBLIC_DIRECTORIES)
    if forbidden_directories:
        raise ReleaseVerificationError(
            f"internal directory cannot be public: {relative}"
        )
    name = PurePosixPath(relative).name.casefold()
    if name in FORBIDDEN_PUBLIC_NAMES:
        raise ReleaseVerificationError(f"internal file cannot be public: {relative}")
    if PurePosixPath(name).suffix in FORBIDDEN_PUBLIC_SUFFIXES:
        raise ReleaseVerificationError(f"sensitive file cannot be public: {relative}")
    stem_key = _normal_key(PurePosixPath(name).stem)
    if stem_key in PII_KEY_NORMAL_FORMS:
        raise ReleaseVerificationError(f"PII-ish filename cannot be public: {relative}")
    if path.suffix.casefold() == ".json":
        document = load_json_strict(path, label=f"public JSON {relative}")
        key_matches = find_pii_keys(document)
        if key_matches:
            raise ReleaseVerificationError(
                "PII-ish public JSON keys in "
                f"{relative}: {', '.join(key_matches[:10])}"
            )
        value_matches = find_sensitive_strings(document)
        if value_matches:
            raise ReleaseVerificationError(
                "sensitive public JSON values in "
                f"{relative}: {', '.join(value_matches[:10])}"
            )
    elif path.suffix.casefold() in TEXT_SCAN_SUFFIXES:
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeError as exc:
            raise ReleaseVerificationError(
                f"public text file is not UTF-8: {relative}"
            ) from exc
        matches = find_sensitive_text(text)
        if matches:
            raise ReleaseVerificationError(
                f"sensitive text in {relative}: {', '.join(matches)}"
            )


def _plain_adapter_result(result: Any) -> dict[str, Any]:
    gaps: list[Any] = []
    for item in result.deterministic_gaps:
        if not isinstance(item, dict):
            raise ReleaseVerificationError("adapter gap output must be plain JSON objects")
        gaps.append(item)
    return {
        "geographies": [item.to_dict() for item in result.geographies],
        "governingBodies": [item.to_dict() for item in result.governing_bodies],
        "deterministicGaps": gaps,
    }


@contextmanager
def network_disabled() -> Iterator[None]:
    def blocked(*_args: Any, **_kwargs: Any) -> None:
        raise ReleaseVerificationError(
            "network access is forbidden during offline adapter verification"
        )

    with (
        patch.object(socket, "socket", side_effect=blocked),
        patch.object(socket, "create_connection", side_effect=blocked),
    ):
        yield


def _adapter_instance(spec: dict[str, Any]) -> Any:
    adapter_id = spec["id"]
    options = spec.get("options") or {}
    if adapter_id == StatCanSgcStructureCsvAdapter.adapter_id:
        unknown = sorted(set(options) - {"classificationYear"})
        if unknown:
            raise ReleaseVerificationError(
                f"{adapter_id} has unsupported options: {', '.join(unknown)}"
            )
        adapter = StatCanSgcStructureCsvAdapter(
            classification_year=str(options.get("classificationYear", "2021"))
        )
    elif adapter_id == CanonicalDirectoryJsonAdapter.adapter_id:
        if options:
            raise ReleaseVerificationError(f"{adapter_id} does not accept options")
        adapter = CanonicalDirectoryJsonAdapter()
    else:
        raise ReleaseVerificationError(f"unsupported release adapter {adapter_id!r}")
    if adapter.adapter_version != spec["version"]:
        raise ReleaseVerificationError(
            f"{adapter_id} version mismatch: plan={spec['version']!r}, "
            f"runtime={adapter.adapter_version!r}"
        )
    return adapter


def _adapter_twice(
    spec: dict[str, Any],
    payload: bytes,
    snapshot: SourceSnapshot,
) -> tuple[str, dict[str, int]]:
    outputs: list[bytes] = []
    plain: dict[str, Any] | None = None
    with network_disabled():
        for _ in range(2):
            adapter = _adapter_instance(spec)
            plain = _plain_adapter_result(adapter.parse(bytes(payload), snapshot))
            outputs.append(
                json.dumps(
                    plain,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                    allow_nan=False,
                ).encode("utf-8")
            )
    if outputs[0] != outputs[1]:
        raise ReleaseVerificationError(
            f"adapter {spec['id']} produced different bytes across two runs"
        )
    assert plain is not None
    return sha256_bytes(outputs[0]), {
        "geographies": len(plain["geographies"]),
        "governingBodies": len(plain["governingBodies"]),
        "deterministicGaps": len(plain["deterministicGaps"]),
    }


def _json_counts(path: Path) -> dict[str, int]:
    if path.suffix.casefold() != ".json":
        return {}
    document = load_json_strict(path, label=f"JSON artifact {path.name}")
    result: dict[str, int] = {}
    if isinstance(document, list):
        result["records"] = len(document)
    elif isinstance(document, dict):
        for key in sorted(document):
            value = document[key]
            if isinstance(value, list):
                result[key] = len(value)
        counts = document.get("counts")
        if isinstance(counts, dict):
            for key in sorted(counts):
                value = counts[key]
                if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
                    result[f"declared.{key}"] = value
    return result


def git_identity(project_root: Path) -> dict[str, Any]:
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=project_root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        if len(commit) != 40 or any(character not in "0123456789abcdef" for character in commit):
            raise ValueError("invalid Git commit")
        diff = subprocess.run(
            ["git", "diff", "--binary", "HEAD", "--", "."],
            cwd=project_root,
            check=True,
            capture_output=True,
        ).stdout
        return {
            "commit": commit,
            "trackedTreeState": "dirty" if diff else "clean",
            "trackedDiffSha256": sha256_bytes(diff),
        }
    except (FileNotFoundError, OSError, subprocess.CalledProcessError, ValueError):
        return {
            "commit": None,
            "trackedTreeState": "unavailable",
            "trackedDiffSha256": None,
        }


def load_release_plan(
    plan_path: Path,
    *,
    project_root: Path = ROOT,
) -> tuple[dict[str, Any], Path, str]:
    project_root = project_root.resolve(strict=False)
    safe_plan = safe_project_path(
        plan_path,
        project_root=project_root,
        label="release plan",
        allow_absolute=plan_path.is_absolute(),
    )
    require_regular_file(safe_plan, project_root=project_root, label="release plan")
    plan = load_json_strict(safe_plan, label="release plan")
    validate_json_schema(plan, PLAN_SCHEMA, label="release plan")
    validate_slug(plan["releaseId"], label="release id")

    ids: set[str] = set()
    paths: set[str] = set()
    for group in ("sources", "artifacts"):
        for item in plan[group]:
            if item["id"] in ids:
                raise ReleaseVerificationError(
                    f"duplicate source/artifact id {item['id']!r}"
                )
            ids.add(item["id"])
            identity = normalized_path_identity(item["path"])
            if identity in paths:
                raise ReleaseVerificationError(
                    f"duplicate source/artifact path {item['path']!r}"
                )
            paths.add(identity)

    required_files: set[str] = set()
    for raw in plan["site"]["requiredFiles"]:
        value = normalize_bundle_path(raw, label="site required file")
        identity = normalized_path_identity(value)
        if identity in required_files:
            raise ReleaseVerificationError(f"duplicate required site path {value!r}")
        required_files.add(identity)

    targets: set[str] = set()
    for copy_spec in plan["site"]["publicArtifactCopies"]:
        target = normalize_bundle_path(
            copy_spec["target"], label="public artifact target"
        )
        identity = normalized_path_identity(target)
        if identity in targets:
            raise ReleaseVerificationError(
                f"duplicate public artifact target {target!r}"
            )
        targets.add(identity)

    validate_security_headers(plan["site"]["securityHeaders"])
    return plan, safe_plan, sha256_file(safe_plan)


def verify_release_plan(
    plan_path: Path,
    *,
    project_root: Path = ROOT,
) -> dict[str, Any]:
    project_root = project_root.resolve(strict=False)
    plan, safe_plan, plan_sha = load_release_plan(
        plan_path, project_root=project_root
    )
    checks: list[dict[str, Any]] = []
    sources: list[dict[str, Any]] = []
    artifacts: list[dict[str, Any]] = []
    total_source_bytes = 0
    total_artifact_bytes = 0
    adapter_runs = 0

    for raw in plan["sources"]:
        source_path = safe_project_path(
            raw["path"], project_root=project_root, label=f"source {raw['id']}"
        )
        require_regular_file(
            source_path, project_root=project_root, label=f"source {raw['id']}"
        )
        payload = source_path.read_bytes()
        observed_hash = sha256_bytes(payload)
        # When the plan pins the archive member, that digest is the check and
        # the container digest is cited identity only. Ontario re-zips
        # identical data, which changes the container and its length while
        # every byte the release is derived from stays the same. This mirrors
        # acquire_official_sources.py, which already decides this way.
        locked_member = raw.get("archiveMemberSha256")
        member_name = raw.get("archiveMember")
        if isinstance(locked_member, str) and isinstance(member_name, str):
            observed_member = sha256_archive_member(
                source_path, member_name, label=f"source {raw['id']}"
            )
            if observed_member != locked_member:
                raise ReleaseVerificationError(
                    f"source {raw['id']} payload hash mismatch: expected "
                    f"{locked_member}, observed {observed_member}"
                )
        else:
            if observed_hash != raw["sha256"]:
                raise ReleaseVerificationError(
                    f"source {raw['id']} hash mismatch: expected {raw['sha256']}, "
                    f"observed {observed_hash}"
                )
            if len(payload) != raw["byteLength"]:
                raise ReleaseVerificationError(
                    f"source {raw['id']} byte length mismatch: expected "
                    f"{raw['byteLength']}, observed {len(payload)}"
                )
        entry: dict[str, Any] = {
            "id": raw["id"],
            "path": project_relative(source_path, project_root),
            "sha256": observed_hash,
            "byteLength": len(payload),
            "mediaType": raw["mediaType"],
        }
        checks.append(
            {
                "id": f"source:{raw['id']}:locked-bytes",
                "scope": raw["id"],
                "outcome": "ok",
                "rederived": "raw SHA-256 and byte length from local source bytes",
            }
        )
        adapter_spec = raw.get("adapter")
        if adapter_spec:
            snapshot = SourceSnapshot(
                source_id=raw["id"],
                sha256=observed_hash,
                byte_length=len(payload),
                media_type=raw["mediaType"],
                request_url=raw["requestUrl"],
                retrieved_at=raw.get("retrievedAt"),
                effective_date=raw.get("effectiveDate"),
                etag=raw.get("etag"),
                last_modified=raw.get("lastModified"),
            )
            output_hash, counts = _adapter_twice(adapter_spec, payload, snapshot)
            entry["adapter"] = {
                "id": adapter_spec["id"],
                "version": adapter_spec["version"],
                "canonicalOutputSha256": output_hash,
                "counts": counts,
                "runs": 2,
            }
            checks.append(
                {
                    "id": f"source:{raw['id']}:adapter-determinism",
                    "scope": raw["id"],
                    "outcome": "ok",
                    "rederived": (
                        "two fresh adapter instances over copied locked bytes "
                        "produced byte-identical canonical JSON"
                    ),
                }
            )
            adapter_runs += 2
        else:
            checks.append(
                {
                    "id": f"source:{raw['id']}:adapter-determinism",
                    "scope": raw["id"],
                    "outcome": "not-applicable",
                    "rederived": "release plan declares no parser for this opaque source",
                }
            )
        sources.append(entry)
        total_source_bytes += len(payload)

    for raw in plan["artifacts"]:
        artifact_path = safe_project_path(
            raw["path"], project_root=project_root, label=f"artifact {raw['id']}"
        )
        require_regular_file(
            artifact_path,
            project_root=project_root,
            label=f"artifact {raw['id']}",
        )
        observed_hash = sha256_file(artifact_path)
        observed_size = artifact_path.stat().st_size
        if observed_hash != raw["sha256"]:
            raise ReleaseVerificationError(
                f"artifact {raw['id']} hash mismatch: expected {raw['sha256']}, "
                f"observed {observed_hash}"
            )
        if observed_size != raw["byteLength"]:
            raise ReleaseVerificationError(
                f"artifact {raw['id']} byte length mismatch: expected "
                f"{raw['byteLength']}, observed {observed_size}"
            )
        counts = _json_counts(artifact_path)
        artifacts.append(
            {
                "id": raw["id"],
                "path": project_relative(artifact_path, project_root),
                "sha256": observed_hash,
                "byteLength": observed_size,
                "mediaType": raw["mediaType"],
                "visibility": raw["visibility"],
                "counts": counts,
            }
        )
        checks.append(
            {
                "id": f"artifact:{raw['id']}:locked-bytes",
                "scope": raw["id"],
                "outcome": "ok",
                "rederived": (
                    "raw SHA-256, byte length, and deterministic JSON record counts"
                ),
            }
        )
        total_artifact_bytes += observed_size

    git = git_identity(project_root)
    tools = {
        **plan["toolVersions"],
        "checker": CHECKER_VERSION,
        "bundler": BUNDLER_VERSION,
        "manifestVerifier": MANIFEST_VERIFIER_VERSION,
        "deploymentVerifier": DEPLOYMENT_VERIFIER_VERSION,
        "python": platform.python_version(),
    }
    return {
        "schemaVersion": "auditback-data-release-verification-1.0.0",
        "releaseId": plan["releaseId"],
        "releaseTimestamp": plan["releaseTimestamp"],
        "result": "ok",
        "plan": {
            "path": project_relative(safe_plan, project_root),
            "sha256": plan_sha,
        },
        "checks": checks,
        "sources": sources,
        "artifacts": artifacts,
        "counts": {
            "sources": len(sources),
            "sourceBytes": total_source_bytes,
            "artifacts": len(artifacts),
            "artifactBytes": total_artifact_bytes,
            "adapterRuns": adapter_runs,
            "checks": len(checks),
        },
        "tools": tools,
        "git": git,
        "runtimeNetworkCalls": 0,
    }


def write_json_atomic(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json_bytes(value)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    if temporary.exists():
        raise ReleaseVerificationError(f"temporary output already exists: {temporary}")
    try:
        with temporary.open("xb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Verify locked release data without network access"
    )
    parser.add_argument(
        "--plan",
        type=Path,
        default=ROOT / "release" / "release-plan.json",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "release" / "verification.json",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = make_parser().parse_args(argv)
    try:
        verification = verify_release_plan(args.plan)
        output = safe_project_path(
            args.output,
            project_root=ROOT,
            label="verification output",
            allow_absolute=args.output.is_absolute(),
        )
        write_json_atomic(output, verification)
    except (OSError, ReleaseVerificationError, ValueError) as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 1
    print(
        f"Verified {verification['counts']['sources']} locked sources and "
        f"{verification['counts']['artifacts']} artifacts; network calls: 0."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
