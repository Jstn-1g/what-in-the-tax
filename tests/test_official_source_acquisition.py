from __future__ import annotations

import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from scripts.acquire_official_sources import (
    MAX_DOWNLOAD_BYTES,
    OfficialSourceError,
    SourceLock,
    acquire_source,
    discover_locks,
    download_source,
    inspect_payload,
    load_reviewed_lock,
    sha256_bytes,
    validate_source_url,
    verify_offline,
)


HEADERS = ["MARSYEAR", "ASSESSMENT_CODE", "VALUE_TEXT"]
OFFICIAL_URL = (
    "https://efis.fma.csc.gov.on.ca/fir/MultiYearReport/fir_data_2025.zip"
)


def _zip_bytes(
    csv_bytes: bytes,
    *,
    member: str = "fir_data_2025.csv",
    extra_member: bool = False,
) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(
        output,
        "w",
        compression=zipfile.ZIP_DEFLATED,
    ) as archive:
        archive.writestr(member, csv_bytes)
        if extra_member:
            archive.writestr("unexpected.csv", b"a,b\n1,2\n")
    return output.getvalue()


def _csv_bytes(rows: list[tuple[str, str, str]]) -> bytes:
    output = io.StringIO(newline="")
    output.write(",".join(HEADERS) + "\r\n")
    for row in rows:
        output.write(",".join(row) + "\r\n")
    return output.getvalue().encode("utf-8")


def _lock_document(payload: bytes, *, row_count: int, record_count: int) -> dict:
    return {
        "schemaVersion": "official-source-lock-1.0.0",
        "reviewStatus": "reviewed",
        "reviewedAt": "2026-07-26T20:00:00-04:00",
        "jurisdiction": "CA-ON",
        "sourceId": "on-fir-2025",
        "fiscalYear": 2025,
        "url": OFFICIAL_URL,
        "mediaType": "application/zip",
        "byteLength": len(payload),
        "sha256": sha256_bytes(payload),
        "localPath": "source-pdfs/fir/fir_data_2025.zip",
        "archiveMember": "fir_data_2025.csv",
        "encoding": "utf-8",
        "headers": HEADERS,
        "fiscalYearField": "MARSYEAR",
        "recordIdField": "ASSESSMENT_CODE",
        "rowCount": row_count,
        "recordCount": record_count,
        "retrievedAt": "2026-07-26T20:00:00-04:00",
        "licence": {
            "name": "Open Government Licence – Ontario",
            "url": (
                "https://www.ontario.ca/page/"
                "open-government-licence-ontario"
            ),
            "attribution": (
                "Contains information licensed under the "
                "Open Government Licence – Ontario."
            ),
        },
        "runtimeAiRequired": False,
    }


def _write_lock(
    root: Path,
    payload: bytes,
    *,
    row_count: int,
    record_count: int,
    mutate=None,
) -> tuple[SourceLock, Path]:
    document = _lock_document(
        payload,
        row_count=row_count,
        record_count=record_count,
    )
    if mutate:
        mutate(document)
    path = root / "sources" / "locks" / "ca-on" / "source.lock.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(document), encoding="utf-8")
    return load_reviewed_lock(path, project_root=root), path


class _FakeResponse:
    def __init__(
        self,
        data: bytes,
        *,
        content_type: str = "application/zip",
        content_length: str | None = None,
        final_url: str = OFFICIAL_URL,
    ) -> None:
        self._stream = io.BytesIO(data)
        self._final_url = final_url
        self.headers = {
            "Content-Type": content_type,
            "Content-Encoding": "identity",
        }
        if content_length is not None:
            self.headers["Content-Length"] = content_length

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self, size: int = -1) -> bytes:
        return self._stream.read(size)

    def geturl(self) -> str:
        return self._final_url


class _FakeOpener:
    def __init__(self, response: _FakeResponse) -> None:
        self.response = response
        self.calls = 0

    def open(self, request, timeout):
        self.calls += 1
        return self.response


class OfficialSourceAcquisitionTests(unittest.TestCase):
    def test_reviewed_ontario_locks_cover_current_and_2025_to_2023(self) -> None:
        root = Path(__file__).resolve().parents[1]
        locks = discover_locks(root / "sources" / "locks", project_root=root)

        self.assertEqual(
            [lock.source_id for lock in locks],
            [
                "on-fir-2025",
                "on-fir-2024",
                "on-fir-2023",
                "on-municipalities-current",
            ],
        )
        for lock in locks:
            with self.subTest(lock=lock.source_id):
                document = lock.document
                self.assertEqual(document["jurisdiction"], "CA-ON")
                self.assertEqual(document["reviewStatus"], "reviewed")
                self.assertFalse(document["runtimeAiRequired"])
                for field in (
                    "fiscalYear",
                    "url",
                    "mediaType",
                    "byteLength",
                    "sha256",
                    "archiveMember",
                    "rowCount",
                    "recordCount",
                    "retrievedAt",
                    "licence",
                ):
                    self.assertIn(field, document)

    def test_offline_verify_checks_exact_local_bytes_and_counts(self) -> None:
        payload = _zip_bytes(_csv_bytes([("2025", "3001", "ok")]))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            lock, _ = _write_lock(
                root,
                payload,
                row_count=1,
                record_count=1,
            )
            lock.local_path.parent.mkdir(parents=True)
            lock.local_path.write_bytes(payload)

            result = verify_offline(lock)

            self.assertEqual(result["status"], "verified-offline")
            self.assertEqual(result["rowCount"], 1)
            self.assertEqual(result["recordCount"], 1)

    def test_offline_verify_rejects_changed_local_bytes(self) -> None:
        payload = _zip_bytes(_csv_bytes([("2025", "3001", "ok")]))
        changed = _zip_bytes(
            _csv_bytes(
                [
                    ("2025", "3001", "ok"),
                    ("2025", "3024", "new"),
                ]
            )
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            lock, _ = _write_lock(
                root,
                payload,
                row_count=1,
                record_count=1,
            )
            lock.local_path.parent.mkdir(parents=True)
            lock.local_path.write_bytes(changed)

            with self.assertRaisesRegex(
                OfficialSourceError,
                "differs from reviewed lock",
            ):
                verify_offline(lock)

    def test_changed_download_creates_candidate_without_replacing_active(self) -> None:
        active = _zip_bytes(_csv_bytes([("2025", "3001", "active")]))
        changed = _zip_bytes(
            _csv_bytes(
                [
                    ("2025", "3001", "active"),
                    ("2025", "3024", "candidate"),
                ]
            )
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            lock, lock_path = _write_lock(
                root,
                active,
                row_count=1,
                record_count=1,
            )
            lock_before = lock_path.read_bytes()
            lock.local_path.parent.mkdir(parents=True)
            lock.local_path.write_bytes(active)
            opener = _FakeOpener(_FakeResponse(changed))

            result = acquire_source(
                lock,
                opener=opener,
                candidate_dir=root / "sources" / "candidates",
                project_root=root,
                observed_at="2026-07-27T01:00:00Z",
            )

            self.assertEqual(result["status"], "candidate")
            self.assertEqual(lock.local_path.read_bytes(), active)
            self.assertEqual(lock_path.read_bytes(), lock_before)
            metadata = json.loads((root / result["candidate"]).read_text("utf-8"))
            self.assertEqual(metadata["status"], "candidate-unreviewed")
            self.assertEqual(
                metadata["proposedLock"]["sha256"],
                sha256_bytes(changed),
            )
            self.assertEqual(metadata["proposedLock"]["rowCount"], 2)
            self.assertIn("reviewRequired", metadata)

    def test_exact_download_installs_only_when_target_is_missing(self) -> None:
        payload = _zip_bytes(_csv_bytes([("2025", "3001", "ok")]))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            lock, _ = _write_lock(
                root,
                payload,
                row_count=1,
                record_count=1,
            )
            result = acquire_source(
                lock,
                opener=_FakeOpener(_FakeResponse(payload)),
                candidate_dir=root / "sources" / "candidates",
                project_root=root,
            )

            self.assertEqual(result["status"], "installed")
            self.assertEqual(lock.local_path.read_bytes(), payload)

    def test_https_allowlist_rejects_downgrade_query_and_other_hosts(self) -> None:
        rejected = [
            OFFICIAL_URL.replace("https://", "http://"),
            OFFICIAL_URL + "?download=1",
            "https://example.com/fir_data_2025.zip",
            (
                "https://efis.fma.csc.gov.on.ca/"
                "unreviewed/fir_data_2025.zip"
            ),
        ]
        for url in rejected:
            with self.subTest(url=url):
                with self.assertRaises(OfficialSourceError):
                    validate_source_url(url)

        self.assertEqual(validate_source_url(OFFICIAL_URL), OFFICIAL_URL)

    def test_download_enforces_declared_byte_bound(self) -> None:
        response = _FakeResponse(
            b"small",
            content_length=str(MAX_DOWNLOAD_BYTES + 1),
        )
        with self.assertRaisesRegex(OfficialSourceError, "download bound"):
            download_source(OFFICIAL_URL, opener=_FakeOpener(response))

    def test_zip_member_path_count_and_compression_are_bounded(self) -> None:
        safe = _zip_bytes(_csv_bytes([("2025", "3001", "ok")]))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            lock, _ = _write_lock(
                root,
                safe,
                row_count=1,
                record_count=1,
            )
            malicious_payloads = [
                _zip_bytes(
                    _csv_bytes([("2025", "3001", "ok")]),
                    member="../fir_data_2025.csv",
                ),
                _zip_bytes(
                    _csv_bytes([("2025", "3001", "ok")]),
                    extra_member=True,
                ),
                _zip_bytes(
                    b"MARSYEAR,ASSESSMENT_CODE,VALUE_TEXT\n"
                    + b"A" * (2 * 1024 * 1024)
                ),
            ]
            for payload in malicious_payloads:
                with self.subTest(size=len(payload)):
                    with self.assertRaises(OfficialSourceError):
                        inspect_payload(payload, lock)

    def test_csv_headers_year_and_encoding_are_strict(self) -> None:
        safe = _zip_bytes(_csv_bytes([("2025", "3001", "ok")]))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            lock, _ = _write_lock(
                root,
                safe,
                row_count=1,
                record_count=1,
            )
            invalid_payloads = [
                _zip_bytes(b"changed,headers\n2025,3001\n"),
                _zip_bytes(_csv_bytes([("2024", "3001", "wrong year")])),
                _zip_bytes(b"\xff\xfe\xfd"),
            ]
            for payload in invalid_payloads:
                with self.subTest(payload=payload[:12]):
                    with self.assertRaises(OfficialSourceError):
                        inspect_payload(payload, lock)

    def test_lock_rejects_traversing_member_and_unreviewed_status(self) -> None:
        payload = _zip_bytes(_csv_bytes([("2025", "3001", "ok")]))
        mutations = [
            lambda document: document.update(
                {"archiveMember": "../fir_data_2025.csv"}
            ),
            lambda document: document.update({"reviewStatus": "candidate"}),
            lambda document: document.update(
                {"localPath": "../outside/fir_data_2025.zip"}
            ),
        ]
        for index, mutate in enumerate(mutations):
            with self.subTest(index=index), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                with self.assertRaises(OfficialSourceError):
                    _write_lock(
                        root,
                        payload,
                        row_count=1,
                        record_count=1,
                        mutate=mutate,
                    )


if __name__ == "__main__":
    unittest.main()
