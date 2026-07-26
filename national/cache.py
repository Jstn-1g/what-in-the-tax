"""Content-addressed storage for official source payloads.

Transport is intentionally out of scope. Callers may download through an
approved API client or scheduled job, then hand the bytes to this cache. Builds
and tests only read locked bytes and therefore never depend on live websites.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .models import (
    ModelValidationError,
    SourceSnapshot,
    canonical_json_bytes,
    require_sha256,
    require_source_id,
)


class CacheError(ValueError):
    """A source snapshot was missing, changed, or escaped its cache boundary."""


@dataclass(frozen=True, slots=True)
class NormalizedTextLock:
    """Identity of deterministic normalized text derived from one source snapshot."""

    source_snapshot: SourceSnapshot
    normalized_text_sha256: str
    normalized_text_char_count: int
    normalized_text_byte_length: int
    normalizer_id: str
    normalizer_version: str

    def __post_init__(self) -> None:
        require_sha256(
            self.normalized_text_sha256,
            label="normalized text sha256",
        )
        for label, value in (
            ("normalized_text_char_count", self.normalized_text_char_count),
            ("normalized_text_byte_length", self.normalized_text_byte_length),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ModelValidationError(f"{label} must be a non-negative integer")
        require_source_id(self.normalizer_id)
        if not isinstance(self.normalizer_version, str) or not self.normalizer_version:
            raise ModelValidationError("normalizer_version must be a non-empty string")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": "auditback-normalized-text-lock-1.0.0",
            "sourceSnapshot": self.source_snapshot.to_dict(),
            "normalizedText": {
                "sha256": self.normalized_text_sha256,
                "charCount": self.normalized_text_char_count,
                "byteLength": self.normalized_text_byte_length,
            },
            "normalizer": {
                "id": self.normalizer_id,
                "version": self.normalizer_version,
            },
        }


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _write_once(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != payload:
            raise CacheError(f"immutable cache path already contains different bytes: {path}")
        return
    with tempfile.NamedTemporaryFile(
        mode="wb",
        dir=path.parent,
        prefix=f".{path.name}.",
        delete=False,
    ) as handle:
        temporary = Path(handle.name)
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    try:
        try:
            # The hard-link create is atomic and refuses to replace an existing
            # immutable lock, including when two transport jobs race.
            os.link(temporary, path)
        except FileExistsError:
            if path.read_bytes() != payload:
                raise CacheError(
                    f"immutable cache path already contains different bytes: {path}"
                )
    finally:
        if temporary.exists():
            temporary.unlink()


class ContentAddressedSourceCache:
    """Store payloads by SHA-256 and immutable source-specific snapshot locks."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve(strict=False)

    def object_path(self, sha256: str) -> Path:
        digest = require_sha256(sha256, label="object sha256")
        return self.root / "objects" / digest[:2] / digest

    def snapshot_path(self, source_id: str, sha256: str) -> Path:
        safe_source_id = require_source_id(source_id)
        digest = require_sha256(sha256, label="snapshot sha256")
        return self.root / "snapshots" / safe_source_id / f"{digest}.json"

    def normalized_object_path(self, sha256: str) -> Path:
        digest = require_sha256(sha256, label="normalized object sha256")
        return self.root / "normalized-objects" / digest[:2] / f"{digest}.txt"

    def normalized_lock_path(
        self,
        source_id: str,
        source_sha256: str,
        normalized_text_sha256: str,
    ) -> Path:
        safe_source_id = require_source_id(source_id)
        source_digest = require_sha256(source_sha256, label="source snapshot sha256")
        text_digest = require_sha256(
            normalized_text_sha256,
            label="normalized text sha256",
        )
        return (
            self.root
            / "normalized-locks"
            / safe_source_id
            / source_digest
            / f"{text_digest}.json"
        )

    def store(
        self,
        *,
        source_id: str,
        payload: bytes,
        media_type: str,
        request_url: str,
        expected_sha256: str | None = None,
        retrieved_at: str | None = None,
        effective_date: str | None = None,
        etag: str | None = None,
        last_modified: str | None = None,
    ) -> SourceSnapshot:
        if not isinstance(payload, bytes):
            raise CacheError("payload must be bytes")
        digest = sha256_bytes(payload)
        if expected_sha256 is not None:
            expected = require_sha256(expected_sha256, label="expected_sha256")
            if digest != expected:
                raise CacheError(
                    f"source hash mismatch: expected {expected}, observed {digest}"
                )
        snapshot = SourceSnapshot(
            source_id=source_id,
            sha256=digest,
            byte_length=len(payload),
            media_type=media_type,
            request_url=request_url,
            retrieved_at=retrieved_at,
            effective_date=effective_date,
            etag=etag,
            last_modified=last_modified,
        )
        _write_once(self.object_path(digest), payload)
        lock = json.dumps(
            snapshot.to_dict(),
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
        ).encode("utf-8") + b"\n"
        _write_once(self.snapshot_path(source_id, digest), lock)
        return snapshot

    def load(self, snapshot: SourceSnapshot) -> bytes:
        path = self.object_path(snapshot.sha256)
        if not path.is_file():
            raise CacheError(f"cached object is missing: {snapshot.sha256}")
        payload = path.read_bytes()
        observed = sha256_bytes(payload)
        if observed != snapshot.sha256:
            raise CacheError(
                f"cached object hash mismatch: expected {snapshot.sha256}, observed {observed}"
            )
        if len(payload) != snapshot.byte_length:
            raise CacheError(
                f"cached object length mismatch: expected {snapshot.byte_length}, "
                f"observed {len(payload)}"
            )
        return payload

    def load_snapshot(self, source_id: str, sha256: str) -> SourceSnapshot:
        path = self.snapshot_path(source_id, sha256)
        if not path.is_file():
            raise CacheError(f"source snapshot lock is missing: {path}")
        try:
            raw: Any = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise CacheError(f"source snapshot lock is invalid JSON: {path}") from exc
        if not isinstance(raw, dict):
            raise CacheError("source snapshot lock must be an object")
        try:
            snapshot = SourceSnapshot(
                source_id=raw["sourceId"],
                sha256=raw["sha256"],
                byte_length=raw["byteLength"],
                media_type=raw["mediaType"],
                request_url=raw["requestUrl"],
                retrieved_at=raw.get("retrievedAt"),
                effective_date=raw.get("effectiveDate"),
                etag=raw.get("etag"),
                last_modified=raw.get("lastModified"),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise CacheError(f"source snapshot lock has invalid fields: {path}") from exc
        if snapshot.source_id != source_id:
            raise CacheError(
                "source snapshot lock identity does not match its source path"
            )
        if snapshot.sha256 != sha256:
            raise CacheError(
                "source snapshot lock digest does not match its digest path"
            )
        if canonical_json_bytes(snapshot.to_dict()) != canonical_json_bytes(raw):
            raise CacheError("source snapshot lock contains unsupported fields")
        return snapshot

    def store_normalized_text(
        self,
        *,
        source_snapshot: SourceSnapshot,
        normalized_text: str,
        normalizer_id: str,
        normalizer_version: str,
    ) -> NormalizedTextLock:
        """Lock normalized text only after verifying its source lock and bytes."""

        if not isinstance(normalized_text, str):
            raise CacheError("normalized_text must be a string")
        try:
            locked_snapshot = self.load_snapshot(
                source_snapshot.source_id,
                source_snapshot.sha256,
            )
        except (CacheError, ModelValidationError) as exc:
            raise CacheError("normalized text requires a verified source snapshot lock") from exc
        if locked_snapshot != source_snapshot:
            raise CacheError("source snapshot differs from its verified cache lock")
        self.load(locked_snapshot)
        text_bytes = normalized_text.encode("utf-8")
        text_sha256 = sha256_bytes(text_bytes)
        try:
            lock = NormalizedTextLock(
                source_snapshot=locked_snapshot,
                normalized_text_sha256=text_sha256,
                normalized_text_char_count=len(normalized_text),
                normalized_text_byte_length=len(text_bytes),
                normalizer_id=normalizer_id,
                normalizer_version=normalizer_version,
            )
        except ModelValidationError as exc:
            raise CacheError(str(exc)) from exc
        _write_once(self.normalized_object_path(text_sha256), text_bytes)
        lock_bytes = (
            json.dumps(
                lock.to_dict(),
                ensure_ascii=False,
                sort_keys=True,
                indent=2,
            ).encode("utf-8")
            + b"\n"
        )
        _write_once(
            self.normalized_lock_path(
                locked_snapshot.source_id,
                locked_snapshot.sha256,
                text_sha256,
            ),
            lock_bytes,
        )
        return lock

    def resolve_normalized_text(
        self,
        source_id: str,
        source_sha256: str,
        normalized_text_sha256: str,
    ) -> str:
        """Resolve text through exact source, source-lock, and text-lock identities."""

        try:
            lock_path = self.normalized_lock_path(
                source_id,
                source_sha256,
                normalized_text_sha256,
            )
        except ModelValidationError as exc:
            raise CacheError(str(exc)) from exc
        if not lock_path.is_file():
            raise CacheError("normalized-text lock is missing for source snapshot identity")
        try:
            raw: Any = json.loads(lock_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise CacheError("normalized-text lock is unreadable or invalid JSON") from exc
        try:
            snapshot_raw = raw["sourceSnapshot"]
            normalized_raw = raw["normalizedText"]
            normalizer_raw = raw["normalizer"]
            if not all(
                isinstance(value, dict)
                for value in (snapshot_raw, normalized_raw, normalizer_raw)
            ):
                raise TypeError("lock components must be objects")
            snapshot = SourceSnapshot(
                source_id=snapshot_raw["sourceId"],
                sha256=snapshot_raw["sha256"],
                byte_length=snapshot_raw["byteLength"],
                media_type=snapshot_raw["mediaType"],
                request_url=snapshot_raw["requestUrl"],
                retrieved_at=snapshot_raw.get("retrievedAt"),
                effective_date=snapshot_raw.get("effectiveDate"),
                etag=snapshot_raw.get("etag"),
                last_modified=snapshot_raw.get("lastModified"),
            )
            lock = NormalizedTextLock(
                source_snapshot=snapshot,
                normalized_text_sha256=normalized_raw["sha256"],
                normalized_text_char_count=normalized_raw["charCount"],
                normalized_text_byte_length=normalized_raw["byteLength"],
                normalizer_id=normalizer_raw["id"],
                normalizer_version=normalizer_raw["version"],
            )
        except (KeyError, TypeError, ModelValidationError) as exc:
            raise CacheError("normalized-text lock has invalid fields") from exc
        if canonical_json_bytes(lock.to_dict()) != canonical_json_bytes(raw):
            raise CacheError("normalized-text lock contains unsupported fields")
        if (
            lock.source_snapshot.source_id != source_id
            or lock.source_snapshot.sha256 != source_sha256
            or lock.normalized_text_sha256 != normalized_text_sha256
        ):
            raise CacheError("normalized-text lock identity does not match its path")
        trusted_snapshot = self.load_snapshot(source_id, source_sha256)
        if trusted_snapshot != lock.source_snapshot:
            raise CacheError("normalized-text lock source metadata is not trusted")
        self.load(trusted_snapshot)
        text_path = self.normalized_object_path(normalized_text_sha256)
        if not text_path.is_file():
            raise CacheError("normalized text object is missing")
        text_bytes = text_path.read_bytes()
        if (
            sha256_bytes(text_bytes) != normalized_text_sha256
            or len(text_bytes) != lock.normalized_text_byte_length
        ):
            raise CacheError("normalized text object identity is invalid")
        try:
            text = text_bytes.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise CacheError("normalized text object is not UTF-8") from exc
        if len(text) != lock.normalized_text_char_count:
            raise CacheError("normalized text character count is invalid")
        return text
