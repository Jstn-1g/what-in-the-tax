"""Build the pinned SGC 2021 geography index from a local official CSV.

This command is deliberately offline. The caller supplies previously
downloaded Statistics Canada bytes and their expected SHA-256 digest. The
builder verifies both against the active national source catalog before using
the existing SGC adapter to derive the index.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from national.adapters import AdapterError, StatCanSgcStructureCsvAdapter  # noqa: E402
from national.models import (  # noqa: E402
    ModelValidationError,
    SourceSnapshot,
    canonical_sha256,
)


SCHEMA_VERSION = "auditback-sgc-geography-index-1.0.0"
CLASSIFICATION_VERSION = "2021"
SOURCE_ID = "statcan-sgc-2021-structure-en"
LEVELS = (
    "region",
    "province-territory",
    "census-division",
    "census-subdivision",
)
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
DEFAULT_CATALOG = ROOT / "national" / "source_catalog.json"
DEFAULT_SCHEMA = ROOT / "national" / "schemas" / "sgc-geography-index.schema.json"
DEFAULT_OUTPUT = ROOT / "national" / "sgc_2021_geography_index.json"


class BuildError(ValueError):
    """The local SGC input or its pinned metadata is invalid."""


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


def _catalog_source(catalog: dict[str, Any]) -> dict[str, Any]:
    rows = catalog.get("sources")
    if not isinstance(rows, list):
        raise BuildError("source catalog must contain a sources array")
    matches = [
        row
        for row in rows
        if isinstance(row, dict) and row.get("sourceId") == SOURCE_ID
    ]
    if len(matches) != 1:
        raise BuildError(f"source catalog must contain exactly one {SOURCE_ID!r} row")

    source = matches[0]
    required = {
        "sourceId",
        "classificationVersion",
        "requestUrl",
        "mediaType",
        "adapterId",
        "adapterVersion",
        "approvedSha256",
    }
    missing = sorted(required - source.keys())
    if missing:
        raise BuildError(
            f"source catalog row {SOURCE_ID!r} missing fields: {', '.join(missing)}"
        )
    if source["classificationVersion"] != CLASSIFICATION_VERSION:
        raise BuildError(
            f"{SOURCE_ID}: classificationVersion must be {CLASSIFICATION_VERSION!r}"
        )
    if source["adapterId"] != StatCanSgcStructureCsvAdapter.adapter_id:
        raise BuildError(f"{SOURCE_ID}: source catalog selects an unsupported adapter")
    if source["adapterVersion"] != StatCanSgcStructureCsvAdapter.adapter_version:
        raise BuildError(f"{SOURCE_ID}: source catalog adapter version is unsupported")
    if not isinstance(source["requestUrl"], str) or not source["requestUrl"].startswith(
        "https://"
    ):
        raise BuildError(f"{SOURCE_ID}: source catalog requestUrl must use HTTPS")
    if not isinstance(source["mediaType"], str) or not source["mediaType"]:
        raise BuildError(f"{SOURCE_ID}: source catalog mediaType must be non-empty")
    if (
        not isinstance(source["approvedSha256"], str)
        or SHA256_RE.fullmatch(source["approvedSha256"]) is None
    ):
        raise BuildError(f"{SOURCE_ID}: source catalog approvedSha256 is invalid")
    return source


def _read_verified_payload(path: Path, expected_sha256: str) -> bytes:
    if SHA256_RE.fullmatch(expected_sha256) is None:
        raise BuildError("--sgc-sha256 must be a lowercase SHA-256 hex digest")
    try:
        payload = path.read_bytes()
    except OSError as exc:
        raise BuildError(f"cannot read SGC CSV: {path}") from exc
    observed_sha256 = hashlib.sha256(payload).hexdigest()
    if observed_sha256 != expected_sha256:
        raise BuildError(
            "SGC CSV SHA-256 mismatch: "
            f"expected {expected_sha256}, observed {observed_sha256}"
        )
    return payload


def _validate_schema(document: dict[str, Any], schema_path: Path) -> None:
    schema = _load_object(schema_path, label="SGC geography index schema")
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as exc:
        raise BuildError(f"SGC geography index schema is invalid: {exc.message}") from exc

    errors = sorted(
        Draft202012Validator(schema).iter_errors(document),
        key=lambda error: tuple(str(part) for part in error.absolute_path),
    )
    if errors:
        error = errors[0]
        location = ".".join(str(part) for part in error.absolute_path) or "$"
        raise BuildError(f"generated index fails schema at {location}: {error.message}")


def _validate_index(document: dict[str, Any]) -> None:
    geography_ids = document["geographyIds"]
    if geography_ids != sorted(geography_ids):
        raise BuildError("generated geographyIds are not sorted")
    if len(geography_ids) != len(set(geography_ids)):
        raise BuildError("generated geographyIds are not unique")

    observed_counts: Counter[str] = Counter()
    prefix = f"ca:sgc:{CLASSIFICATION_VERSION}:"
    for geography_id in geography_ids:
        if not geography_id.startswith(prefix):
            raise BuildError(f"generated geography ID has the wrong version: {geography_id}")
        level_and_code = geography_id.removeprefix(prefix)
        level = level_and_code.rsplit(":", 1)[0]
        if level not in LEVELS:
            raise BuildError(f"generated geography ID has an unknown level: {geography_id}")
        observed_counts[level] += 1
    expected_counts = {level: observed_counts[level] for level in LEVELS}
    if document["counts"] != expected_counts:
        raise BuildError("generated geography counts do not match geographyIds")

    digest_input = {
        key: value
        for key, value in document.items()
        if key != "indexCanonicalSha256"
    }
    if document["indexCanonicalSha256"] != canonical_sha256(digest_input):
        raise BuildError("generated indexCanonicalSha256 is invalid")


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


def build(args: argparse.Namespace) -> dict[str, Any]:
    expected_sha256 = args.sgc_sha256
    if not isinstance(expected_sha256, str):
        raise BuildError("--sgc-sha256 must be a lowercase SHA-256 hex digest")

    catalog = _load_object(Path(args.catalog), label="source catalog")
    source = _catalog_source(catalog)
    if expected_sha256 != source["approvedSha256"]:
        raise BuildError("SGC sha256 differs from the active source catalog release hash")
    payload = _read_verified_payload(Path(args.sgc_csv), expected_sha256)

    snapshot = SourceSnapshot(
        source_id=SOURCE_ID,
        sha256=expected_sha256,
        byte_length=len(payload),
        media_type=source["mediaType"],
        request_url=source["requestUrl"],
    )
    result = StatCanSgcStructureCsvAdapter(
        classification_year=CLASSIFICATION_VERSION
    ).parse(payload, snapshot)
    geography_ids = sorted(record.geography_id for record in result.geographies)
    counts = Counter(record.level for record in result.geographies)
    index: dict[str, Any] = {
        "schemaVersion": SCHEMA_VERSION,
        "classificationVersion": CLASSIFICATION_VERSION,
        "source": {
            "sourceId": SOURCE_ID,
            "sha256": expected_sha256,
        },
        "counts": {level: counts[level] for level in LEVELS},
        "geographyIds": geography_ids,
    }
    index["indexCanonicalSha256"] = canonical_sha256(index)
    _validate_index(index)
    _validate_schema(index, Path(args.schema))
    _write_json(Path(args.output), index)
    return index


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build the pinned offline SGC 2021 geography index (0 AI tokens)"
    )
    parser.add_argument("--sgc-csv", required=True, help="Local official SGC structure CSV")
    parser.add_argument(
        "--sgc-sha256",
        required=True,
        help="Expected lowercase SHA-256 for the local SGC CSV",
    )
    parser.add_argument("--catalog", default=str(DEFAULT_CATALOG))
    parser.add_argument("--schema", default=str(DEFAULT_SCHEMA))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    return parser


def main() -> int:
    parser = make_parser()
    args = parser.parse_args()
    try:
        index = build(args)
    except (AdapterError, BuildError, ModelValidationError, ValueError) as exc:
        parser.exit(1, f"ERROR: {exc}\n")
    print(
        "Built pinned SGC geography index: "
        f"{len(index['geographyIds'])} geography IDs."
    )
    print("Runtime network calls: 0. AI calls: 0. AI tokens: 0.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
