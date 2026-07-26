"""Build AuditBack's Canada-wide registry from locally locked official payloads.

There is intentionally no HTTP or AI client in this command. A scheduled
transport job may obtain official API/download bytes, but this build receives
explicit paths and expected SHA-256 hashes, stores them content-addressed, and
parses them offline.

Example:
    python scripts/build_national_registry.py \
      --sgc-csv C:/downloads/sgc-cgt-2021-structure-eng.csv \
      --sgc-sha256 <64 lowercase hex characters> \
      --cache-dir C:/auditback-source-cache \
      --output national/build/registry.json \
      --source-lock-output national/build/sources.lock.json
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from national.adapters import (  # noqa: E402
    AdapterError,
    CanonicalDirectoryJsonAdapter,
    StatCanSgcStructureCsvAdapter,
)
from national.cache import CacheError, ContentAddressedSourceCache  # noqa: E402
from national.models import canonical_sha256  # noqa: E402
from national.registry import NationalRegistryBuilder, RegistryError  # noqa: E402


DEFAULT_CATALOG = ROOT / "national" / "source_catalog.json"
DEFAULT_COVERAGE_PLAN = ROOT / "national" / "coverage_plan.json"
SGC_SOURCE_ID = "statcan-sgc-2021-structure-en"


class BuildError(ValueError):
    """A local build input or manifest is invalid."""


def _load_object(path: Path, *, label: str) -> dict[str, Any]:
    try:
        value: Any = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise BuildError(f"cannot read {label}: {path}") from exc
    except json.JSONDecodeError as exc:
        raise BuildError(f"{label} is invalid JSON: {path}: {exc.msg}") from exc
    if not isinstance(value, dict):
        raise BuildError(f"{label} must be a JSON object: {path}")
    return value


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        indent=2,
    ) + "\n"
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        newline="\n",
        dir=path.parent,
        prefix=f".{path.name}.",
        delete=False,
    ) as handle:
        temporary = Path(handle.name)
        handle.write(payload)
        handle.flush()
    try:
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _catalog_source(catalog: dict[str, Any], source_id: str) -> dict[str, Any]:
    rows = catalog.get("sources")
    if not isinstance(rows, list):
        raise BuildError("source catalog must contain a sources array")
    matches = [
        item
        for item in rows
        if isinstance(item, dict) and item.get("sourceId") == source_id
    ]
    if len(matches) != 1:
        raise BuildError(f"source catalog must contain exactly one {source_id!r} row")
    result = matches[0]
    required = {
        "sourceId",
        "mediaType",
        "requestUrl",
        "adapterId",
        "adapterVersion",
        "approvedSha256",
    }
    missing = sorted(required - result.keys())
    if missing:
        raise BuildError(
            f"source catalog row {source_id!r} missing fields: {', '.join(missing)}"
        )
    return result


def _load_directory_manifest(
    path: Path,
    *,
    cache: ContentAddressedSourceCache,
    catalog: dict[str, Any],
) -> tuple[list[Any], list[Any]]:
    manifest = _load_object(path, label="directory manifest")
    rows = manifest.get("sources")
    if not isinstance(rows, list):
        raise BuildError("directory manifest must contain a sources array")
    bodies: list[Any] = []
    snapshots: list[Any] = []
    for index, raw in enumerate(rows):
        label = f"directory manifest sources[{index}]"
        if not isinstance(raw, dict):
            raise BuildError(f"{label} must be an object")
        required = {"sourceId", "path", "sha256", "requestUrl"}
        missing = sorted(required - raw.keys())
        if missing:
            raise BuildError(f"{label} missing fields: {', '.join(missing)}")
        source_path = Path(raw["path"])
        if not source_path.is_absolute():
            source_path = path.parent / source_path
        try:
            payload = source_path.read_bytes()
        except OSError as exc:
            raise BuildError(f"{label} cannot read {source_path}") from exc
        catalog_row = _catalog_source(catalog, raw["sourceId"])
        adapters = {
            CanonicalDirectoryJsonAdapter.adapter_id: CanonicalDirectoryJsonAdapter,
        }
        adapter_type = adapters.get(catalog_row["adapterId"])
        if adapter_type is None:
            raise BuildError(
                f"{label} selects unsupported adapter {catalog_row['adapterId']!r}"
            )
        if raw["requestUrl"] != catalog_row["requestUrl"]:
            raise BuildError(f"{label} requestUrl differs from source catalog")
        if raw["sha256"] != catalog_row["approvedSha256"]:
            raise BuildError(f"{label} sha256 differs from approved source catalog hash")
        adapter = adapter_type()
        snapshot = cache.store(
            source_id=raw["sourceId"],
            payload=payload,
            media_type=catalog_row["mediaType"],
            request_url=raw["requestUrl"],
            expected_sha256=raw["sha256"],
            retrieved_at=raw.get("retrievedAt"),
            effective_date=raw.get("effectiveDate"),
            etag=raw.get("etag"),
            last_modified=raw.get("lastModified"),
        )
        result = adapter.parse(cache.load(snapshot), snapshot)
        bodies.extend(result.governing_bodies)
        snapshots.append(snapshot)
    return bodies, snapshots


def build(args: argparse.Namespace) -> dict[str, Any]:
    catalog_path = Path(args.catalog)
    coverage_path = Path(args.coverage_plan)
    catalog = _load_object(catalog_path, label="source catalog")
    coverage_plan = _load_object(coverage_path, label="coverage plan")
    source = _catalog_source(catalog, SGC_SOURCE_ID)
    if source["adapterId"] != StatCanSgcStructureCsvAdapter.adapter_id:
        raise BuildError(
            f"source catalog row {SGC_SOURCE_ID!r} selects an unsupported adapter"
        )
    if source.get("classificationVersion") != args.classification_version:
        raise BuildError(
            "classification version differs from the locked SGC source catalog entry"
        )
    if source["approvedSha256"] != args.sgc_sha256:
        raise BuildError(
            "SGC sha256 differs from the approved source catalog release hash"
        )

    sgc_path = Path(args.sgc_csv)
    try:
        sgc_payload = sgc_path.read_bytes()
    except OSError as exc:
        raise BuildError(f"cannot read SGC CSV: {sgc_path}") from exc

    cache = ContentAddressedSourceCache(Path(args.cache_dir))
    sgc_snapshot = cache.store(
        source_id=SGC_SOURCE_ID,
        payload=sgc_payload,
        media_type=source["mediaType"],
        request_url=source["requestUrl"],
        expected_sha256=args.sgc_sha256,
        retrieved_at=args.retrieved_at,
        effective_date=args.effective_date,
    )
    sgc_result = StatCanSgcStructureCsvAdapter(
        classification_year=args.classification_version
    ).parse(cache.load(sgc_snapshot), sgc_snapshot)

    governing_bodies: list[Any] = []
    snapshots: list[Any] = [sgc_snapshot]
    if args.directory_manifest:
        directory_bodies, directory_snapshots = _load_directory_manifest(
            Path(args.directory_manifest),
            cache=cache,
            catalog=catalog,
        )
        governing_bodies.extend(directory_bodies)
        snapshots.extend(directory_snapshots)

    registry = NationalRegistryBuilder(
        classification_version=args.classification_version,
        source_catalog=catalog,
        coverage_plan=coverage_plan,
        scope=args.scope,
    ).build(
        geographies=sgc_result.geographies,
        governing_bodies=governing_bodies,
        snapshots=snapshots,
    )
    ordered_snapshots = sorted(
        snapshots,
        key=lambda snapshot: (snapshot.source_id, snapshot.sha256),
    )
    source_lock: dict[str, Any] = {
        "schemaVersion": "auditback-national-source-lock-1.0.0",
        "sourceCatalogCanonicalSha256": canonical_sha256(catalog),
        "coveragePlanCanonicalSha256": canonical_sha256(coverage_plan),
        "snapshots": [snapshot.to_dict() for snapshot in ordered_snapshots],
    }
    source_lock["sourceLockCanonicalSha256"] = canonical_sha256(source_lock)
    _write_json(Path(args.output), registry)
    _write_json(Path(args.source_lock_output), source_lock)
    return registry


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build the offline AuditBack national registry (0 AI tokens)"
    )
    parser.add_argument("--sgc-csv", required=True, help="Local official SGC structure CSV")
    parser.add_argument(
        "--sgc-sha256",
        required=True,
        help="Expected lowercase SHA-256 for the SGC CSV",
    )
    parser.add_argument(
        "--cache-dir",
        required=True,
        help="Content-addressed official-source cache directory",
    )
    parser.add_argument("--output", required=True, help="Registry JSON output path")
    parser.add_argument(
        "--source-lock-output",
        required=True,
        help="Source snapshot lock JSON output path",
    )
    parser.add_argument(
        "--directory-manifest",
        help="Optional local manifest of official directory JSON overlays",
    )
    parser.add_argument("--catalog", default=str(DEFAULT_CATALOG))
    parser.add_argument("--coverage-plan", default=str(DEFAULT_COVERAGE_PLAN))
    parser.add_argument("--classification-version", default="2021")
    parser.add_argument(
        "--scope",
        choices=("production", "test"),
        default="production",
        help=(
            "Registry scope. Production enforces all 13 provinces/territories "
            "and all seven canonical layers; test is only for reduced fixtures."
        ),
    )
    parser.add_argument(
        "--retrieved-at",
        help="Optional transport timestamp; omit for reproducible ordinary builds",
    )
    parser.add_argument("--effective-date")
    return parser


def main() -> int:
    parser = make_parser()
    args = parser.parse_args()
    try:
        registry = build(args)
    except (AdapterError, BuildError, CacheError, RegistryError, ValueError) as exc:
        parser.exit(1, f"ERROR: {exc}\n")
    print(
        "Built national registry: "
        f"{registry['counts']['geographies']} geographies, "
        f"{registry['counts']['governingBodies']} verified governing bodies."
    )
    print("Runtime network calls: 0. AI calls: 0. AI tokens: 0.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
