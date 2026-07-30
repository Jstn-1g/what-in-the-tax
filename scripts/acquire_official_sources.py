"""Acquire or verify hash-locked official source snapshots.

The reviewed lock files are the authority. A network response that differs
from a lock is preserved as an unreviewed candidate and never replaces either
the active lock or an existing local snapshot.

Examples:
    python scripts/acquire_official_sources.py --offline
    python scripts/acquire_official_sources.py on-fir-2025

This module is deliberately deterministic and uses no AI service at runtime.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import BinaryIO, Iterable


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LOCK_DIR = ROOT / "sources" / "locks"
DEFAULT_CANDIDATE_DIR = ROOT / "sources" / "candidates"

LOCK_SCHEMA_VERSION = "official-source-lock-1.0.0"
MAX_DOWNLOAD_BYTES = 32 * 1024 * 1024
MAX_ARCHIVE_MEMBER_BYTES = 256 * 1024 * 1024
MAX_ARCHIVE_COMPRESSION_RATIO = 100
MAX_CSV_FIELD_CHARS = 1024 * 1024
DOWNLOAD_CHUNK_BYTES = 64 * 1024
DOWNLOAD_TIMEOUT_SECONDS = 30

SOURCE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")
JURISDICTION_RE = re.compile(r"^[A-Z]{2}(?:-[A-Z0-9]{1,3})+$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
MEDIA_TYPE_RE = re.compile(
    r"^[a-z0-9][a-z0-9!#$&^_.+-]*/[a-z0-9][a-z0-9!#$&^_.+-]*$"
)

# Download URLs are reviewed at the host and path-prefix level. Redirects are
# subjected to the same checks, so HTTPS cannot be downgraded or sent to an
# unrelated host.
HTTPS_SOURCE_ALLOWLIST: dict[str, tuple[str, ...]] = {
    "data.ontario.ca": (
        "/dataset/62e83cbc-0731-4d66-abdc-2f2b31bcd76c/resource/"
        "6783a586-6b05-4a73-9663-e60a6963c91e/download/",
    ),
    "efis.fma.csc.gov.on.ca": ("/fir/MultiYearReport/",),
    # Statistics Canada 92F0009X - Interim List of Changes to Municipal
    # Boundaries, Status and Names. The official record of dissolutions and
    # amalgamations; feeds the former-municipalities crosswalk. Path-scoped to
    # that one publication, per the review on issue #34.
    "www150.statcan.gc.ca": (
        "/n1/pub/92f0009x/",
        # Full-table CSV downloads (17-10-0155 population estimates by CSD -
        # the product the North Dumfries ledger has cited by name since July
        # without ever locking it).
        "/n1/tbl/csv/",
    ),
}

ALLOWED_ZIP_COMPRESSION = {
    zipfile.ZIP_STORED,
    zipfile.ZIP_DEFLATED,
}


class OfficialSourceError(ValueError):
    """Raised when a source, lock, or response fails a deterministic gate."""


@dataclass(frozen=True)
class SourceLock:
    """A validated, reviewed source lock."""

    path: Path
    document: dict
    local_path: Path

    @property
    def source_id(self) -> str:
        return self.document["sourceId"]

    @property
    def url(self) -> str:
        return self.document["url"]

    @property
    def media_type(self) -> str:
        return self.document["mediaType"]

    @property
    def byte_length(self) -> int:
        return self.document["byteLength"]

    @property
    def sha256(self) -> str:
        return self.document["sha256"]


@dataclass(frozen=True)
class Download:
    """A bounded network response held for inspection before installation."""

    data: bytes
    final_url: str
    media_type: str


class _AllowlistedRedirectHandler(urllib.request.HTTPRedirectHandler):
    max_repeats = 2
    max_redirections = 5

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validate_source_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def canonical_json(document: dict) -> str:
    return json.dumps(document, indent=2, ensure_ascii=False, sort_keys=True) + "\n"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _require_plain_int(
    document: dict,
    field: str,
    *,
    minimum: int = 0,
    maximum: int | None = None,
) -> int:
    value = document.get(field)
    if type(value) is not int:  # bool is not an accepted integer here
        raise OfficialSourceError(f"{field} must be an integer")
    if value < minimum or (maximum is not None and value > maximum):
        raise OfficialSourceError(f"{field} is outside its allowed bounds")
    return value


# Adopting a source is a named-human attestation, and until now the lock
# recorded that a review happened and when, but never who. In a solo repository
# the reviewer is implicit. In a public one it is the only link in the
# provenance chain that lives outside the artifact - recoverable, if at all,
# from git authorship - and docs/ONTARIO-COMPLETION.md section 6 names it as a
# prerequisite for opening the project to contributors.
#
# The boundary is a date rather than a migration on purpose. Rewriting the four
# existing locks to name a reviewer would mean inventing an attestation for a
# review that happened before anyone was asked to sign it, which is the exact
# failure this field exists to prevent. So locks reviewed before this instant
# stay valid and are reported as unattributed, and every review from here on
# has to name someone.
ATTRIBUTION_REQUIRED_FROM = datetime(2026, 7, 29, tzinfo=timezone.utc)


def _validate_reviewer(document: dict, path: Path, reviewed_at: datetime) -> None:
    """Require a named reviewer for anything reviewed under the policy."""

    reviewer = document.get("reviewedBy")
    if reviewed_at < ATTRIBUTION_REQUIRED_FROM:
        # Grandfathered. Absent is allowed; present must still be usable, so a
        # blank string cannot pass itself off as attribution.
        if reviewer is not None and (
            not isinstance(reviewer, str) or not reviewer.strip()
        ):
            raise OfficialSourceError(
                f"reviewedBy in {path} must be a non-empty string when present"
            )
        return
    if not isinstance(reviewer, str) or not reviewer.strip():
        raise OfficialSourceError(
            f"lock {path} was reviewed at {reviewed_at.isoformat()} and must name "
            'its reviewer: add "reviewedBy": "<name of the person who reviewed '
            'the source>". Adopting a source is an attestation, and an '
            "attestation nobody signed is not one."
        )


def is_attributed(document: dict) -> bool:
    """Whether this lock records who reviewed it, for reporting gaps honestly."""

    reviewer = document.get("reviewedBy")
    return isinstance(reviewer, str) and bool(reviewer.strip())


def _parse_reviewed_at(value: object, field: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise OfficialSourceError(f"{field} must be an RFC 3339 timestamp")
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise OfficialSourceError(
            f"{field} must be an RFC 3339 timestamp"
        ) from exc
    if parsed.tzinfo is None:
        raise OfficialSourceError(f"{field} must include a UTC offset")
    return parsed


def validate_source_url(value: object) -> str:
    """Validate an official source URL against the HTTPS allowlist."""

    if not isinstance(value, str) or not value:
        raise OfficialSourceError("url must be a non-empty string")
    parsed = urllib.parse.urlsplit(value)
    if (
        parsed.scheme != "https"
        or parsed.username is not None
        or parsed.password is not None
        or parsed.port not in (None, 443)
        or parsed.query
        or parsed.fragment
    ):
        raise OfficialSourceError(
            "source URL must be allowlisted HTTPS without credentials, query, or fragment"
        )
    host = (parsed.hostname or "").casefold()
    prefixes = HTTPS_SOURCE_ALLOWLIST.get(host)
    if not prefixes or not any(parsed.path.startswith(prefix) for prefix in prefixes):
        raise OfficialSourceError(
            f"source URL is outside the official HTTPS allowlist: {value!r}"
        )
    return value


# The reuse licences a lock may claim, by exact URL. This was a single
# hardcoded Ontario URL, which quietly meant no source outside Ontario's open
# data programme could ever be locked - including Statistics Canada, whose
# interim-list files are the only official record of municipal dissolutions.
# An allowlist keeps the property that mattered (a lock cannot claim an
# unreviewed licence) without hardcoding one province's licence as the only
# reviewable one in a project that intends to cover the country.
REVIEWED_LICENCE_URLS = frozenset(
    {
        "https://www.ontario.ca/page/open-government-licence-ontario",
        "https://www.statcan.gc.ca/en/reference/licence",
    }
)


def _validate_licence(value: object) -> None:
    if not isinstance(value, dict):
        raise OfficialSourceError("licence must be an object")
    if not isinstance(value.get("name"), str) or not value["name"].strip():
        raise OfficialSourceError("licence.name must be a non-empty string")
    licence_url = value.get("url")
    if licence_url not in REVIEWED_LICENCE_URLS:
        raise OfficialSourceError(
            f"licence.url is not a reviewed licence: {licence_url!r}"
        )
    if (
        not isinstance(value.get("attribution"), str)
        or not value["attribution"].strip()
    ):
        raise OfficialSourceError(
            "licence.attribution must be a non-empty string"
        )


def _safe_project_path(
    value: object,
    *,
    project_root: Path,
    approved_root: Path,
    label: str,
) -> Path:
    if not isinstance(value, str) or not value:
        raise OfficialSourceError(f"{label} must be a project-relative path")
    if "\\" in value:
        raise OfficialSourceError(f"{label} must use forward slashes")
    pure = PurePosixPath(value)
    if pure.is_absolute() or any(part in ("", ".", "..") for part in pure.parts):
        raise OfficialSourceError(f"{label} is not a safe project-relative path")
    candidate = (project_root / Path(*pure.parts)).resolve(strict=False)
    approved = approved_root.resolve(strict=False)
    try:
        candidate.relative_to(approved)
    except ValueError as exc:
        raise OfficialSourceError(f"{label} escapes {approved_root}") from exc
    return candidate


def load_reviewed_lock(
    path: Path,
    *,
    project_root: Path = ROOT,
) -> SourceLock:
    """Load and fully validate one reviewed source lock."""

    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise OfficialSourceError(f"cannot read lock {path}: {exc}") from exc
    if not isinstance(document, dict):
        raise OfficialSourceError(f"lock {path} must contain an object")
    if document.get("schemaVersion") != LOCK_SCHEMA_VERSION:
        raise OfficialSourceError(f"unsupported lock schema in {path}")
    if document.get("reviewStatus") != "reviewed":
        raise OfficialSourceError(f"lock is not reviewed: {path}")
    reviewed_at = _parse_reviewed_at(document.get("reviewedAt"), "reviewedAt")
    _parse_reviewed_at(document.get("retrievedAt"), "retrievedAt")
    _validate_reviewer(document, path, reviewed_at)

    jurisdiction = document.get("jurisdiction")
    if not isinstance(jurisdiction, str) or not JURISDICTION_RE.fullmatch(
        jurisdiction
    ):
        raise OfficialSourceError("jurisdiction is invalid")
    source_id = document.get("sourceId")
    if not isinstance(source_id, str) or not SOURCE_ID_RE.fullmatch(source_id):
        raise OfficialSourceError("sourceId is invalid")

    fiscal_year = document.get("fiscalYear")
    if fiscal_year is not None and (
        type(fiscal_year) is not int or not 1900 <= fiscal_year <= 2100
    ):
        raise OfficialSourceError("fiscalYear must be null or a four-digit year")
    validate_source_url(document.get("url"))

    media_type = document.get("mediaType")
    if not isinstance(media_type, str) or not MEDIA_TYPE_RE.fullmatch(media_type):
        raise OfficialSourceError("mediaType is invalid")
    byte_length = _require_plain_int(
        document,
        "byteLength",
        minimum=1,
        maximum=MAX_DOWNLOAD_BYTES,
    )
    sha256 = document.get("sha256")
    if not isinstance(sha256, str) or not SHA256_RE.fullmatch(sha256):
        raise OfficialSourceError("sha256 must be 64 lowercase hexadecimal digits")

    archive_member = document.get("archiveMember")
    if media_type == "application/zip":
        _validate_archive_member_name(archive_member, source_id=source_id)
    elif archive_member is not None:
        raise OfficialSourceError("archiveMember must be null for a non-ZIP source")

    # Optional. When present it pins the bytes *inside* the archive, which is
    # what the data actually is; the container digest above only pins how those
    # bytes happened to be packaged on the day they were reviewed.
    archive_member_sha256 = document.get("archiveMemberSha256")
    if archive_member_sha256 is not None:
        if media_type != "application/zip":
            raise OfficialSourceError(
                "archiveMemberSha256 is only meaningful for a ZIP source"
            )
        if not isinstance(archive_member_sha256, str) or not SHA256_RE.fullmatch(
            archive_member_sha256
        ):
            raise OfficialSourceError(
                "archiveMemberSha256 must be 64 lowercase hexadecimal digits"
            )

    row_count = _require_plain_int(document, "rowCount", minimum=1)
    record_count = _require_plain_int(document, "recordCount", minimum=1)
    if record_count > row_count:
        raise OfficialSourceError("recordCount cannot exceed rowCount")

    encoding = document.get("encoding")
    if encoding not in ("utf-8", "utf-8-sig"):
        raise OfficialSourceError("encoding must be utf-8 or utf-8-sig")
    headers = document.get("headers")
    if (
        not isinstance(headers, list)
        or not headers
        or any(not isinstance(header, str) or not header for header in headers)
        or len(set(headers)) != len(headers)
    ):
        raise OfficialSourceError("headers must be a non-empty unique string list")
    record_field = document.get("recordIdField")
    if record_field not in headers:
        raise OfficialSourceError("recordIdField must name a reviewed header")
    max_extra_columns = document.get("maxExtraColumns", 0)
    if (
        type(max_extra_columns) is not int
        or max_extra_columns < 0
        or max_extra_columns > 4
    ):
        raise OfficialSourceError("maxExtraColumns must be an integer from 0 to 4")
    fiscal_year_field = document.get("fiscalYearField")
    if fiscal_year is None:
        if fiscal_year_field is not None:
            raise OfficialSourceError(
                "fiscalYearField must be null when fiscalYear is null"
            )
    elif fiscal_year_field not in headers:
        raise OfficialSourceError("fiscalYearField must name a reviewed header")

    if document.get("runtimeAiRequired") is not False:
        raise OfficialSourceError("runtimeAiRequired must be false")
    _validate_licence(document.get("licence"))

    local_path = _safe_project_path(
        document.get("localPath"),
        project_root=project_root,
        approved_root=project_root / "source-pdfs",
        label="localPath",
    )
    # The lock's byte length is used by offline verification, while this global
    # bound controls revised remote candidates.
    if byte_length > MAX_DOWNLOAD_BYTES:
        raise OfficialSourceError("locked source exceeds the download bound")
    return SourceLock(path=path, document=document, local_path=local_path)


def discover_locks(
    lock_dir: Path = DEFAULT_LOCK_DIR,
    *,
    project_root: Path = ROOT,
    source_ids: Iterable[str] = (),
) -> list[SourceLock]:
    requested = set(source_ids)
    invalid = sorted(item for item in requested if not SOURCE_ID_RE.fullmatch(item))
    if invalid:
        raise OfficialSourceError(f"invalid requested source IDs: {invalid}")
    paths = sorted(lock_dir.rglob("*.lock.json"))
    if not paths:
        raise OfficialSourceError(f"no source locks found under {lock_dir}")
    locks = [
        load_reviewed_lock(path, project_root=project_root)
        for path in paths
    ]
    ids = [lock.source_id for lock in locks]
    duplicates = sorted(source_id for source_id in set(ids) if ids.count(source_id) > 1)
    if duplicates:
        raise OfficialSourceError(f"duplicate source IDs in locks: {duplicates}")
    if requested:
        missing = sorted(requested - set(ids))
        if missing:
            raise OfficialSourceError(f"unknown source IDs: {missing}")
        locks = [lock for lock in locks if lock.source_id in requested]
    return sorted(
        locks,
        key=lambda lock: (
            lock.document["jurisdiction"],
            -(
                lock.document["fiscalYear"]
                if lock.document["fiscalYear"] is not None
                else 0
            ),
            lock.source_id,
        ),
    )


def _validate_archive_member_name(value: object, *, source_id: str) -> str:
    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        raise OfficialSourceError(
            f"{source_id}: archiveMember must be a safe POSIX path"
        )
    member = PurePosixPath(value)
    if (
        member.is_absolute()
        or any(part in ("", ".", "..") for part in member.parts)
        or len(member.parts) != 1
    ):
        raise OfficialSourceError(
            f"{source_id}: nested or traversing archiveMember is forbidden"
        )
    return value


def _scan_csv(
    raw: BinaryIO,
    lock: SourceLock,
) -> tuple[int, int]:
    document = lock.document
    previous_limit = csv.field_size_limit()
    csv.field_size_limit(MAX_CSV_FIELD_CHARS)
    try:
        text = io.TextIOWrapper(
            raw,
            encoding=document["encoding"],
            errors="strict",
            newline="",
        )
        reader = csv.DictReader(text)
        if reader.fieldnames != document["headers"]:
            raise OfficialSourceError(
                f"{lock.source_id}: CSV headers changed; refusing to infer a schema"
            )
        row_count = 0
        record_ids: set[str] = set()
        for row_number, row in enumerate(reader, start=2):
            row_count += 1
            if None in row:
                extras = row.pop(None)
                max_extra = document.get("maxExtraColumns", 0)
                if (
                    not isinstance(extras, list)
                    or len(extras) > max_extra
                    or any(
                        not isinstance(value, str)
                        or len(value) > MAX_CSV_FIELD_CHARS
                        for value in extras
                    )
                ):
                    raise OfficialSourceError(
                        f"{lock.source_id}: row {row_number} has unreviewed "
                        "extra columns"
                    )
            if any(value is None for value in row.values()):
                raise OfficialSourceError(
                    f"{lock.source_id}: row {row_number} has missing columns"
                )
            record_id = (row.get(document["recordIdField"]) or "").strip()
            if not record_id or "\x00" in record_id:
                raise OfficialSourceError(
                    f"{lock.source_id}: row {row_number} has an invalid record ID"
                )
            record_ids.add(record_id)
            fiscal_year = document["fiscalYear"]
            if fiscal_year is not None:
                observed_year = (
                    row.get(document["fiscalYearField"]) or ""
                ).strip()
                if observed_year != str(fiscal_year):
                    raise OfficialSourceError(
                        f"{lock.source_id}: row {row_number} contains fiscal year "
                        f"{observed_year!r}, expected {fiscal_year}"
                    )
        return row_count, len(record_ids)
    except (UnicodeError, csv.Error) as exc:
        raise OfficialSourceError(
            f"{lock.source_id}: CSV encoding or syntax is invalid: {exc}"
        ) from exc
    finally:
        csv.field_size_limit(previous_limit)


class _HashingReader(io.RawIOBase):
    """Digest every byte that passes through, without a second read.

    A ZIP member stream is not seekable, so hashing the payload separately
    would mean decompressing it twice. Wrapping the stream keeps the cost at
    one pass over data that is already being scanned.
    """

    def __init__(self, inner: BinaryIO) -> None:
        self._inner = inner
        self._digest = hashlib.sha256()
        self._read = 0

    def readable(self) -> bool:
        return True

    def readinto(self, buffer) -> int:  # type: ignore[override]
        chunk = self._inner.read(len(buffer))
        count = len(chunk)
        if count:
            buffer[:count] = chunk
            self._digest.update(chunk)
            self._read += count
        return count

    @property
    def bytes_read(self) -> int:
        return self._read

    def hexdigest(self) -> str:
        return self._digest.hexdigest()


def _inspect_zip(data: bytes, lock: SourceLock) -> tuple[int, int, str]:
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except (OSError, zipfile.BadZipFile) as exc:
        raise OfficialSourceError(
            f"{lock.source_id}: response is not a valid ZIP archive"
        ) from exc
    with archive:
        members = archive.infolist()
        expected_name = lock.document["archiveMember"]
        # A lock may declare companion members the publisher ships alongside
        # the data - StatCan full-table zips carry a *_MetaData.csv next to the
        # table. The member SET is still exact: anything undeclared appearing,
        # or anything declared missing, refuses. Only the primary member is
        # scanned and hashed; companions are acknowledged, not trusted.
        declared = lock.document.get("archiveCompanionMembers") or []
        if not isinstance(declared, list) or not all(
            isinstance(name, str) and name for name in declared
        ):
            raise OfficialSourceError(
                f"{lock.source_id}: archiveCompanionMembers must be a list of names"
            )
        expected_set = {expected_name, *declared}
        observed = [member.filename for member in members]
        if sorted(observed) != sorted(expected_set) or observed.count(expected_name) != 1:
            raise OfficialSourceError(
                f"{lock.source_id}: ZIP members changed: {observed!r}"
            )
        member = next(m for m in members if m.filename == expected_name)
        _validate_archive_member_name(member.filename, source_id=lock.source_id)
        if member.is_dir() or member.flag_bits & 0x1:
            raise OfficialSourceError(
                f"{lock.source_id}: ZIP member is a directory or is encrypted"
            )
        if member.compress_type not in ALLOWED_ZIP_COMPRESSION:
            raise OfficialSourceError(
                f"{lock.source_id}: unsupported ZIP compression method"
            )
        unix_type = (member.external_attr >> 16) & 0o170000
        if unix_type not in (0, 0o100000):
            raise OfficialSourceError(
                f"{lock.source_id}: ZIP member is not a regular file"
            )
        if member.file_size > MAX_ARCHIVE_MEMBER_BYTES:
            raise OfficialSourceError(
                f"{lock.source_id}: ZIP member exceeds the expansion bound"
            )
        if member.file_size and member.compress_size == 0:
            raise OfficialSourceError(
                f"{lock.source_id}: ZIP member has an invalid compression size"
            )
        if (
            member.compress_size
            and member.file_size / member.compress_size
            > MAX_ARCHIVE_COMPRESSION_RATIO
        ):
            raise OfficialSourceError(
                f"{lock.source_id}: ZIP compression ratio exceeds the safety bound"
            )
        try:
            with archive.open(member, "r") as raw:
                hashing = _HashingReader(raw)
                row_count, record_count = _scan_csv(
                    io.BufferedReader(hashing), lock
                )
                # Assert the digest covers the whole member rather than trusting
                # that the CSV scan happened to reach EOF. A partial read would
                # otherwise produce a confident digest of an incomplete payload,
                # which is worse than no digest at all.
                if hashing.bytes_read != member.file_size:
                    raise OfficialSourceError(
                        f"{lock.source_id}: hashed {hashing.bytes_read} of "
                        f"{member.file_size} member bytes"
                    )
                return row_count, record_count, hashing.hexdigest()
        except (OSError, RuntimeError, zipfile.BadZipFile) as exc:
            raise OfficialSourceError(
                f"{lock.source_id}: cannot safely read the ZIP member"
            ) from exc


def inspect_payload(data: bytes, lock: SourceLock) -> dict:
    """Apply structural, archive, header, encoding, and row gates."""

    if not data:
        raise OfficialSourceError(f"{lock.source_id}: source is empty")
    if len(data) > MAX_DOWNLOAD_BYTES:
        raise OfficialSourceError(
            f"{lock.source_id}: source exceeds the download bound"
        )
    archive_member_sha256: str | None = None
    if lock.media_type == "application/zip":
        row_count, record_count, archive_member_sha256 = _inspect_zip(data, lock)
    elif lock.media_type in ("text/csv", "application/csv"):
        row_count, record_count = _scan_csv(io.BytesIO(data), lock)
    else:
        raise OfficialSourceError(
            f"{lock.source_id}: unsupported locked media type {lock.media_type!r}"
        )
    return {
        "byteLength": len(data),
        "sha256": sha256_bytes(data),
        "rowCount": row_count,
        "recordCount": record_count,
        "archiveMemberSha256": archive_member_sha256,
    }


def _lock_differences(lock: SourceLock, observed: dict) -> dict:
    """Report what actually changed, not merely what was repackaged.

    Ontario re-exports its FIR archives on a schedule. The CSV inside can be
    byte-identical while the ZIP around it carries new timestamps, which changes
    the container digest and nothing else. Treating that as a source change
    quarantines an unchanged file and spends a human review on a non-event.

    When the lock pins the payload and the payload still matches, container
    drift is recorded as reproducibility metadata rather than a difference. A
    lock without archiveMemberSha256 keeps the original all-fields comparison,
    so nothing loosens implicitly.
    """

    document = lock.document
    locked_member = document.get("archiveMemberSha256")
    observed_member = observed.get("archiveMemberSha256")
    payload_pinned = isinstance(locked_member, str)
    payload_matches = payload_pinned and locked_member == observed_member

    fields = ["rowCount", "recordCount"]
    if not payload_matches:
        # Without a verified payload the container digest is the only evidence
        # available, so it stays authoritative.
        fields = ["byteLength", "sha256"] + fields

    differences = {
        field: {
            "locked": document[field],
            "observed": observed[field],
        }
        for field in fields
        if document[field] != observed[field]
    }

    if payload_pinned and not payload_matches:
        # A changed payload is the real finding and must be named as such,
        # never left to be inferred from a container mismatch.
        differences["archiveMemberSha256"] = {
            "locked": locked_member,
            "observed": observed_member,
        }
    return differences


def _read_bounded_file(path: Path) -> bytes:
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise OfficialSourceError(f"cannot stat local source {path}: {exc}") from exc
    if size > MAX_DOWNLOAD_BYTES:
        raise OfficialSourceError(f"local source exceeds the download bound: {path}")
    try:
        with path.open("rb") as handle:
            data = handle.read(MAX_DOWNLOAD_BYTES + 1)
    except OSError as exc:
        raise OfficialSourceError(f"cannot read local source {path}: {exc}") from exc
    if len(data) > MAX_DOWNLOAD_BYTES:
        raise OfficialSourceError(f"local source exceeds the download bound: {path}")
    return data


def verify_offline(lock: SourceLock) -> dict:
    """Verify a local snapshot without making a network request."""

    if not lock.local_path.is_file():
        raise OfficialSourceError(
            f"{lock.source_id}: missing local snapshot {lock.local_path}"
        )
    observed = inspect_payload(_read_bounded_file(lock.local_path), lock)
    differences = _lock_differences(lock, observed)
    if differences:
        raise OfficialSourceError(
            f"{lock.source_id}: local snapshot differs from reviewed lock: "
            f"{differences!r}"
        )
    return {
        "status": "verified-offline",
        "sourceId": lock.source_id,
        "localPath": lock.document["localPath"],
        **observed,
    }


def _response_media_type(response) -> str:
    content_type = response.headers.get("Content-Type", "")
    return content_type.split(";", 1)[0].strip().casefold()


def download_source(
    url: str,
    *,
    opener=None,
    timeout: int = DOWNLOAD_TIMEOUT_SECONDS,
) -> Download:
    """Download one allowlisted HTTPS response within the global byte bound."""

    validate_source_url(url)
    if opener is None:
        opener = urllib.request.build_opener(_AllowlistedRedirectHandler())
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/zip, application/csv, text/csv",
            "User-Agent": "TaxReceiptOfficialSourceAcquirer/1.0",
        },
        method="GET",
    )
    try:
        response_context = opener.open(request, timeout=timeout)
        with response_context as response:
            final_url = response.geturl()
            validate_source_url(final_url)
            content_encoding = response.headers.get("Content-Encoding", "identity")
            if content_encoding.casefold() not in ("", "identity"):
                raise OfficialSourceError(
                    "compressed HTTP transfer encodings are not accepted"
                )
            content_length = response.headers.get("Content-Length")
            if content_length is not None:
                try:
                    declared_length = int(content_length)
                except ValueError as exc:
                    raise OfficialSourceError(
                        "HTTP Content-Length is invalid"
                    ) from exc
                if declared_length < 0 or declared_length > MAX_DOWNLOAD_BYTES:
                    raise OfficialSourceError(
                        "HTTP response exceeds the download bound"
                    )
            media_type = _response_media_type(response)
            chunks: list[bytes] = []
            total = 0
            while True:
                chunk = response.read(DOWNLOAD_CHUNK_BYTES)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_DOWNLOAD_BYTES:
                    raise OfficialSourceError(
                        "HTTP response exceeds the download bound"
                    )
                chunks.append(chunk)
    except OfficialSourceError:
        raise
    except (OSError, urllib.error.URLError) as exc:
        raise OfficialSourceError(f"official source download failed: {exc}") from exc
    return Download(
        data=b"".join(chunks),
        final_url=final_url,
        media_type=media_type,
    )


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def _exclusive_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError:
        if path.read_bytes() != data:
            raise OfficialSourceError(f"refusing to replace existing file: {path}")
    except OSError as exc:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
        raise OfficialSourceError(f"cannot safely write {path}: {exc}") from exc


def _candidate_paths(
    lock: SourceLock,
    observed_hash: str,
    candidate_dir: Path,
    *,
    project_root: Path,
) -> tuple[Path, Path]:
    approved = candidate_dir.resolve(strict=False)
    try:
        approved.relative_to(project_root.resolve(strict=False))
    except ValueError as exc:
        raise OfficialSourceError(
            "candidate directory must stay within the project root"
        ) from exc
    stem = f"{lock.source_id}.{observed_hash[:16]}.candidate"
    return approved / f"{stem}.bin", approved / f"{stem}.json"


def _preserve_candidate(
    lock: SourceLock,
    download: Download,
    observed: dict,
    differences: dict,
    *,
    candidate_dir: Path,
    project_root: Path,
    observed_at: str,
) -> dict:
    payload_path, metadata_path = _candidate_paths(
        lock,
        observed["sha256"],
        candidate_dir,
        project_root=project_root,
    )
    proposed_lock = dict(lock.document)
    proposed_lock.update(observed)
    proposed_lock["retrievedAt"] = observed_at
    proposed_lock["reviewStatus"] = "candidate-unreviewed"
    # Carry the reviewer slot, emptied. A candidate has by definition not been
    # reviewed, so inheriting the previous reviewer's name would attribute this
    # payload to someone who never saw it. Emptying it also shows whoever adopts
    # this candidate exactly which field they are expected to fill.
    proposed_lock["reviewedBy"] = None
    candidate = {
        "schemaVersion": "official-source-candidate-1.0.0",
        "status": "candidate-unreviewed",
        "sourceId": lock.source_id,
        "activeLock": lock.path.relative_to(project_root).as_posix(),
        "activeLocalPath": lock.document["localPath"],
        "candidatePayload": payload_path.relative_to(project_root).as_posix(),
        "observedAt": observed_at,
        "finalUrl": download.final_url,
        "mediaType": download.media_type,
        "differences": differences,
        "proposedLock": proposed_lock,
        "reviewRequired": (
            "Inspect the candidate and update the reviewed lock manually. "
            "This acquisition did not replace active bytes or lock metadata."
        ),
    }
    _exclusive_write(payload_path, download.data)
    _exclusive_write(metadata_path, canonical_json(candidate).encode("utf-8"))
    return {
        "status": "candidate",
        "sourceId": lock.source_id,
        "candidate": metadata_path.relative_to(project_root).as_posix(),
        **observed,
    }


def acquire_source(
    lock: SourceLock,
    *,
    opener=None,
    candidate_dir: Path = DEFAULT_CANDIDATE_DIR,
    project_root: Path = ROOT,
    observed_at: str | None = None,
) -> dict:
    """Acquire a source, installing only exact reviewed bytes."""

    download = download_source(lock.url, opener=opener)
    if download.media_type != lock.media_type:
        raise OfficialSourceError(
            f"{lock.source_id}: HTTP media type {download.media_type!r} "
            f"does not match reviewed {lock.media_type!r}"
        )
    observed = inspect_payload(download.data, lock)
    differences = _lock_differences(lock, observed)
    if differences:
        return _preserve_candidate(
            lock,
            download,
            observed,
            differences,
            candidate_dir=candidate_dir,
            project_root=project_root,
            observed_at=observed_at or _utc_now(),
        )

    if lock.local_path.exists():
        local_result = verify_offline(lock)
        return {
            **local_result,
            "status": "already-verified",
        }
    _exclusive_write(lock.local_path, download.data)
    return {
        "status": "installed",
        "sourceId": lock.source_id,
        "localPath": lock.document["localPath"],
        **observed,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_ids", nargs="*", metavar="SOURCE_ID")
    parser.add_argument(
        "--lock-dir",
        type=Path,
        default=DEFAULT_LOCK_DIR,
        help="directory containing reviewed *.lock.json files",
    )
    parser.add_argument(
        "--candidate-dir",
        type=Path,
        default=DEFAULT_CANDIDATE_DIR,
        help="project-local directory for unreviewed changed-source candidates",
    )
    parser.add_argument(
        "--offline",
        "--verify-offline",
        action="store_true",
        dest="offline",
        help="verify local snapshots without any network requests",
    )
    args = parser.parse_args(argv)

    try:
        locks = discover_locks(
            args.lock_dir,
            project_root=ROOT,
            source_ids=args.source_ids,
        )
        results = [
            (
                verify_offline(lock)
                if args.offline
                else acquire_source(
                    lock,
                    candidate_dir=args.candidate_dir,
                    project_root=ROOT,
                )
            )
            for lock in locks
        ]
    except OfficialSourceError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(canonical_json({"results": results}), end="")
    return 2 if any(result["status"] == "candidate" for result in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
