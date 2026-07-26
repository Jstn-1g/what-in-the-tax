from __future__ import annotations

import hashlib
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from national.cache import CacheError, ContentAddressedSourceCache


class NationalSourceCacheTests(unittest.TestCase):
    def test_round_trip_is_content_addressed_and_offline(self) -> None:
        payload = b"official,csv\n001,Example\n"
        digest = hashlib.sha256(payload).hexdigest()
        with tempfile.TemporaryDirectory() as temporary:
            cache = ContentAddressedSourceCache(Path(temporary))
            with patch("socket.socket.connect") as connect:
                snapshot = cache.store(
                    source_id="official-source",
                    payload=payload,
                    media_type="text/csv",
                    request_url="https://government.example/data.csv",
                    expected_sha256=digest,
                )
                loaded = cache.load(snapshot)
            connect.assert_not_called()

            self.assertEqual(payload, loaded)
            self.assertTrue(cache.object_path(digest).is_file())
            self.assertEqual(
                snapshot,
                cache.load_snapshot("official-source", digest),
            )

    def test_expected_hash_mismatch_fails_before_storage(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            cache = ContentAddressedSourceCache(Path(temporary))
            with self.assertRaisesRegex(CacheError, "source hash mismatch"):
                cache.store(
                    source_id="official-source",
                    payload=b"changed",
                    media_type="text/plain",
                    request_url="https://government.example/data.txt",
                    expected_sha256="0" * 64,
                )
            self.assertFalse((Path(temporary) / "objects").exists())

    def test_tampered_cached_object_fails_closed(self) -> None:
        payload = b"original"
        with tempfile.TemporaryDirectory() as temporary:
            cache = ContentAddressedSourceCache(Path(temporary))
            snapshot = cache.store(
                source_id="official-source",
                payload=payload,
                media_type="application/octet-stream",
                request_url="https://government.example/data.bin",
            )
            cache.object_path(snapshot.sha256).write_bytes(b"tampered")
            with self.assertRaisesRegex(CacheError, "hash mismatch"):
                cache.load(snapshot)

    def test_snapshot_lock_is_immutable_for_identical_payload(self) -> None:
        payload = b"same bytes"
        with tempfile.TemporaryDirectory() as temporary:
            cache = ContentAddressedSourceCache(Path(temporary))
            cache.store(
                source_id="official-source",
                payload=payload,
                media_type="text/plain",
                request_url="https://government.example/data.txt",
                retrieved_at="2026-01-01T00:00:00Z",
            )
            with self.assertRaisesRegex(CacheError, "immutable cache path"):
                cache.store(
                    source_id="official-source",
                    payload=payload,
                    media_type="text/plain",
                    request_url="https://government.example/data.txt",
                    retrieved_at="2026-01-02T00:00:00Z",
                )

    def test_snapshot_lock_content_must_match_its_path_identity(self) -> None:
        payload = b"official"
        with tempfile.TemporaryDirectory() as temporary:
            cache = ContentAddressedSourceCache(Path(temporary))
            snapshot = cache.store(
                source_id="source-a",
                payload=payload,
                media_type="text/plain",
                request_url="https://government.example/data.txt",
            )
            copied_path = cache.snapshot_path("source-b", snapshot.sha256)
            copied_path.parent.mkdir(parents=True)
            shutil.copyfile(
                cache.snapshot_path("source-a", snapshot.sha256),
                copied_path,
            )
            with self.assertRaisesRegex(CacheError, "identity does not match"):
                cache.load_snapshot("source-b", snapshot.sha256)

    def test_normalized_text_is_bound_to_verified_source_snapshot(self) -> None:
        payload = b"official source bytes"
        normalized = "Official normalized text\nwith deterministic spacing."
        with tempfile.TemporaryDirectory() as temporary:
            cache = ContentAddressedSourceCache(Path(temporary))
            snapshot = cache.store(
                source_id="official-source",
                payload=payload,
                media_type="application/pdf",
                request_url="https://government.example/source.pdf",
            )
            lock = cache.store_normalized_text(
                source_snapshot=snapshot,
                normalized_text=normalized,
                normalizer_id="auditback-pdf-text",
                normalizer_version="1.0.0",
            )
            self.assertEqual(
                normalized,
                cache.resolve_normalized_text(
                    snapshot.source_id,
                    snapshot.sha256,
                    lock.normalized_text_sha256,
                ),
            )

    def test_normalized_text_cannot_bind_to_fabricated_source_identity(self) -> None:
        payload = b"official source bytes"
        normalized = "normalized"
        with tempfile.TemporaryDirectory() as temporary:
            cache = ContentAddressedSourceCache(Path(temporary))
            snapshot = cache.store(
                source_id="official-source",
                payload=payload,
                media_type="application/pdf",
                request_url="https://government.example/source.pdf",
            )
            lock = cache.store_normalized_text(
                source_snapshot=snapshot,
                normalized_text=normalized,
                normalizer_id="auditback-pdf-text",
                normalizer_version="1.0.0",
            )
            with self.assertRaisesRegex(CacheError, "lock is missing"):
                cache.resolve_normalized_text(
                    "fabricated-source",
                    snapshot.sha256,
                    lock.normalized_text_sha256,
                )
            with self.assertRaisesRegex(CacheError, "lock is missing"):
                cache.resolve_normalized_text(
                    snapshot.source_id,
                    "f" * 64,
                    lock.normalized_text_sha256,
                )

    def test_tampered_normalized_text_object_fails_closed(self) -> None:
        payload = b"official source bytes"
        normalized = "normalized"
        with tempfile.TemporaryDirectory() as temporary:
            cache = ContentAddressedSourceCache(Path(temporary))
            snapshot = cache.store(
                source_id="official-source",
                payload=payload,
                media_type="application/pdf",
                request_url="https://government.example/source.pdf",
            )
            lock = cache.store_normalized_text(
                source_snapshot=snapshot,
                normalized_text=normalized,
                normalizer_id="auditback-pdf-text",
                normalizer_version="1.0.0",
            )
            cache.normalized_object_path(lock.normalized_text_sha256).write_text(
                "tampered",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(CacheError, "object identity is invalid"):
                cache.resolve_normalized_text(
                    snapshot.source_id,
                    snapshot.sha256,
                    lock.normalized_text_sha256,
                )


if __name__ == "__main__":
    unittest.main()
