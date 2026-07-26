"""Deterministic province and territory rollout planning.

This module validates tracked jurisdiction onboarding packets against the
national source catalog and coverage plan. It deliberately performs no network
requests, has no model client, and never promotes a planned source or an
unfinished onboarding packet into a publication claim.
"""

from __future__ import annotations

import ast
import base64
import csv
import hashlib
import json
import os
import re
import secrets
import subprocess
import sys
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Mapping

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError

from .models import (
    BODY_TYPES,
    PROVINCE_TERRITORY_ISO_BY_SGC,
    PROVINCE_TERRITORY_ISO_CODES,
    canonical_sha256,
)
from .registry import APPROVED_LICENCE_STATUSES


ROLLOUT_SCHEMA_VERSION = "auditback-jurisdiction-rollout-1.0.0"
ROLLOUT_REPORT_SCHEMA_VERSION = "auditback-national-rollout-report-1.0.0"
MUNICIPAL_LAYER = "municipal-regional-governments"
CANONICAL_MUNICIPAL_BODY_TYPES = {
    "municipal-government",
    "regional-government",
}
STAGE_IDS = (
    "official-source-identified",
    "reuse-approved",
    "transport-pinned",
    "adapter-tested",
    "exact-crosswalk-reviewed",
    "exceptions-reviewed",
    "count-reconciled",
    "publication-approved",
)
STAGE_STATUSES = {
    "not-started",
    "in-progress",
    "blocked",
    "complete",
}
ROLLOUT_STATUSES = {
    "not-started",
    "source-discovery",
    "adapter-needed",
    "partial",
    "complete",
    "not-applicable",
}
PATH_RE = re.compile(r"^(?!/)(?![A-Za-z]:)(?!.*(?:^|/)\.\.(?:/|$))(?!.*\\).+$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
DATE_RE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
RELEASE_REFERENCE_RE = re.compile(
    r"^https://github\.com/Jstn-1g/tax-receipt-prototype/"
    r"(?:commit/[0-9a-f]{40}|releases/tag/[^\s]+|pull/[1-9][0-9]*)$"
)
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
ROLLOUT_SCHEMA_PATH = (
    REPOSITORY_ROOT / "national" / "schemas" / "jurisdiction-rollout.schema.json"
)
CANONICAL_DIRECTORY_SCHEMA_PATH = (
    REPOSITORY_ROOT
    / "national"
    / "schemas"
    / "canonical-government-directory.schema.json"
)
VERIFIED_DIRECTORY_SCHEMA_PATH = (
    REPOSITORY_ROOT
    / "national"
    / "schemas"
    / "verified-jurisdiction-directory.schema.json"
)
SGC_GEOGRAPHY_INDEX_PATH = (
    REPOSITORY_ROOT / "national" / "sgc_2021_geography_index.json"
)
SGC_GEOGRAPHY_INDEX_SCHEMA_PATH = (
    REPOSITORY_ROOT
    / "national"
    / "schemas"
    / "sgc-geography-index.schema.json"
)
SGC_GEOGRAPHY_INDEX_CANONICAL_SHA256 = (
    "791b93a143cadcc3c6089702cbd523527a1b4e5480197e3a1a9cead3d30a6585"
)
SOURCE_ROLES = {
    "governing-body-roster",
    "legal-authority",
    "boundary-crosswalk",
    "code-history",
    "relationship-reference",
    "control-total",
}
IDENTITY_SOURCE_ROLES = {
    "governing-body-roster",
    "legal-authority",
}
CROSSWALK_SOURCE_ROLES = {
    "governing-body-roster",
    "legal-authority",
    "boundary-crosswalk",
    "code-history",
}
CLASSIFICATION_HEADERS = (
    "sourceId",
    "sourceRecordKey",
    "officialLegalType",
    "canonicalBodyType",
    "tier",
    "parentBodyId",
    "layerDisposition",
    "effectiveFrom",
    "effectiveTo",
    "reviewer",
    "status",
    "notes",
)
CROSSWALK_HEADERS = (
    "bodyId",
    "officialExternalId",
    "sourceId",
    "snapshotSha256",
    "sourceRecordKey",
    "sgcGeographyId",
    "matchMethod",
    "reviewer",
    "status",
    "notes",
)
CANONICAL_ID_RE = re.compile(r"^ca:[a-z0-9][a-z0-9:._-]+$")
SGC_GEOGRAPHY_ID_RE = re.compile(
    r"^ca:sgc:(?P<year>[0-9]{4}):"
    r"(?P<level>region|province-territory|census-division|census-subdivision):"
    r"(?P<code>[0-9]+)$"
)
PARTIAL_EVIDENCE_STAGES = STAGE_IDS[:6]
IDENTITY_FIELD_MAP_KEYS = (
    "externalId",
    "officialName",
    "officialLegalType",
    "officialUrl",
)


class RolloutError(ValueError):
    """The tracked rollout plan is incomplete, contradictory, or unsafe."""


@dataclass(frozen=True, slots=True)
class RolloutInputs:
    catalog: dict[str, Any]
    coverage_plan: dict[str, Any]
    manifests: dict[str, dict[str, Any]]


@dataclass(frozen=True, slots=True)
class ValidatedSourceLock:
    canonical_sha256: str
    snapshots: dict[str, dict[str, Any]]
    payloads: dict[str, bytes]
    record_key_fields: dict[str, str]
    record_collection_paths: dict[str, str]
    official_legal_type_fields: dict[str, str | None]
    identity_field_maps: dict[str, dict[str, str] | None]
    external_id_namespaces: dict[str, str | None]


@dataclass(frozen=True, slots=True)
class ValidatedDirectory:
    raw_sha256: str
    canonical_sha256: str
    source_lock_sha256: str
    records: tuple[dict[str, Any], ...]
    document: dict[str, Any]


@dataclass(frozen=True, slots=True)
class ValidatedSgcIndex:
    classification_version: str
    geography_ids: frozenset[str]
    parent_by_id: dict[str, str | None]


def load_json_object(path: Path, *, label: str) -> dict[str, Any]:
    try:
        value: Any = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise RolloutError(f"cannot read {label}: {path}") from exc
    except json.JSONDecodeError as exc:
        raise RolloutError(f"{label} is invalid JSON: {path}: {exc.msg}") from exc
    if not isinstance(value, dict):
        raise RolloutError(f"{label} must be a JSON object: {path}")
    return value


def load_rollout_manifests(root: Path) -> dict[str, dict[str, Any]]:
    if not root.is_dir():
        raise RolloutError(f"jurisdiction rollout directory does not exist: {root}")
    manifests: dict[str, dict[str, Any]] = {}
    for path in sorted(root.glob("*/rollout.json")):
        code = path.parent.name
        if code in manifests:
            raise RolloutError(f"duplicate jurisdiction rollout packet for {code}")
        manifests[code] = load_json_object(path, label=f"{code} rollout packet")
    if not manifests:
        raise RolloutError(f"no jurisdiction rollout packets found under {root}")
    return manifests


def load_rollout_inputs(
    *,
    catalog_path: Path,
    coverage_plan_path: Path,
    jurisdictions_root: Path,
) -> RolloutInputs:
    return RolloutInputs(
        catalog=load_json_object(catalog_path, label="source catalog"),
        coverage_plan=load_json_object(coverage_plan_path, label="coverage plan"),
        manifests=load_rollout_manifests(jurisdictions_root),
    )


def _validate_manifest_schemas(manifests: Mapping[str, dict[str, Any]]) -> None:
    schema = load_json_object(
        ROLLOUT_SCHEMA_PATH,
        label="jurisdiction rollout schema",
    )
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as exc:
        raise RolloutError("jurisdiction rollout schema is invalid") from exc
    validator = Draft202012Validator(schema)
    for code in sorted(manifests):
        errors = sorted(
            validator.iter_errors(manifests[code]),
            key=lambda error: tuple(str(item) for item in error.absolute_path),
        )
        if errors:
            error = errors[0]
            location = ".".join(str(item) for item in error.absolute_path)
            suffix = f".{location}" if location else ""
            raise RolloutError(
                f"{code} rollout{suffix} violates the rollout schema: "
                f"{error.message}"
            )


def _verified_directory_validator() -> Draft202012Validator:
    canonical_schema = load_json_object(
        CANONICAL_DIRECTORY_SCHEMA_PATH,
        label="canonical government directory schema",
    )
    verified_schema = load_json_object(
        VERIFIED_DIRECTORY_SCHEMA_PATH,
        label="verified jurisdiction directory schema",
    )
    try:
        Draft202012Validator.check_schema(canonical_schema)
        Draft202012Validator.check_schema(verified_schema)
        verified_schema["$defs"] = {
            **verified_schema.get("$defs", {}),
            **canonical_schema["$defs"],
        }
        verified_schema["properties"]["records"]["items"]["properties"]["body"] = (
            canonical_schema["$defs"]["governingBody"]
        )
    except (KeyError, SchemaError, ValueError) as exc:
        raise RolloutError("verified directory schemas are invalid") from exc
    return Draft202012Validator(verified_schema)


def _catalog_by_id(catalog: dict[str, Any]) -> tuple[
    dict[str, dict[str, Any]],
    set[str],
]:
    if (
        catalog.get("schemaVersion")
        != "auditback-national-source-catalog-1.0.0"
    ):
        raise RolloutError("source catalog schemaVersion is unsupported")
    result: dict[str, dict[str, Any]] = {}
    active_ids: set[str] = set()
    for field, active in (("sources", True), ("plannedSources", False)):
        rows = catalog.get(field, [])
        if not isinstance(rows, list):
            raise RolloutError(f"source catalog {field} must be an array")
        for index, row in enumerate(rows):
            if not isinstance(row, dict):
                raise RolloutError(f"source catalog {field}[{index}] must be an object")
            source_id = row.get("sourceId")
            if not isinstance(source_id, str) or not source_id:
                raise RolloutError(
                    f"source catalog {field}[{index}].sourceId must be a string"
                )
            if source_id in result:
                raise RolloutError(f"duplicate source catalog id {source_id!r}")
            for required_field in (
                "publisher",
                "title",
                "jurisdiction",
                "coverageLayer",
                "landingPageUrl",
                "licenseStatus",
            ):
                value = row.get(required_field)
                if not isinstance(value, str) or not value.strip():
                    raise RolloutError(
                        f"{source_id}: {required_field} must be a non-empty string"
                    )
            if not row["landingPageUrl"].startswith("https://"):
                raise RolloutError(f"{source_id}: landingPageUrl must use HTTPS")
            license_url = row.get("licenseUrl")
            if license_url is not None and (
                not isinstance(license_url, str)
                or not license_url.startswith("https://")
            ):
                raise RolloutError(
                    f"{source_id}: licenseUrl must be HTTPS when present"
                )
            if not isinstance(row.get("reuseReviewRequired"), bool):
                raise RolloutError(
                    f"{source_id}: reuseReviewRequired must be boolean"
                )
            if active:
                for required_field in (
                    "requestUrl",
                    "mediaType",
                    "adapterId",
                    "adapterVersion",
                    "recordKeyField",
                    "recordCollectionPath",
                    "approvedSha256",
                ):
                    value = row.get(required_field)
                    if not isinstance(value, str) or not value.strip():
                        raise RolloutError(
                            f"{source_id}: active source requires {required_field}"
                        )
                if not row["requestUrl"].startswith("https://"):
                    raise RolloutError(f"{source_id}: requestUrl must use HTTPS")
                if SHA256_RE.fullmatch(row["approvedSha256"]) is None:
                    raise RolloutError(
                        f"{source_id}: active source approvedSha256 must be "
                        "lowercase SHA-256 hex"
                    )
                if row.get("runtimeNetworkRequired") is not False:
                    raise RolloutError(
                        f"{source_id}: active adapter must not require runtime network"
                    )
                if not row["recordKeyField"].strip():
                    raise RolloutError(
                        f"{source_id}: active source recordKeyField is required"
                    )
                if (
                    row["recordCollectionPath"] != "$"
                    and re.fullmatch(
                        r"^\$\.[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)*$",
                        row["recordCollectionPath"],
                    )
                    is None
                ):
                    raise RolloutError(
                        f"{source_id}: recordCollectionPath must be $ or a simple "
                        "JSON object path"
                    )
                official_legal_type_field = row.get("officialLegalTypeField")
                if official_legal_type_field is not None and (
                    not isinstance(official_legal_type_field, str)
                    or not official_legal_type_field.strip()
                ):
                    raise RolloutError(
                        f"{source_id}: officialLegalTypeField must be a non-empty "
                        "string when present"
                    )
                identity_field_map = row.get("identityFieldMap")
                external_id_namespace = row.get("externalIdNamespace")
                if (identity_field_map is None) != (
                    external_id_namespace is None
                ):
                    raise RolloutError(
                        f"{source_id}: identityFieldMap and externalIdNamespace "
                        "must be declared together"
                    )
                if identity_field_map is not None:
                    if (
                        type(identity_field_map) is not dict
                        or tuple(sorted(identity_field_map))
                        != tuple(sorted(IDENTITY_FIELD_MAP_KEYS))
                        or any(
                            type(value) is not str or not value.strip()
                            for value in identity_field_map.values()
                        )
                        or len(set(identity_field_map.values()))
                        != len(IDENTITY_FIELD_MAP_KEYS)
                    ):
                        raise RolloutError(
                            f"{source_id}: identityFieldMap must declare four "
                            "distinct non-empty official source fields"
                        )
                    if (
                        identity_field_map["externalId"]
                        != row["recordKeyField"]
                    ):
                        raise RolloutError(
                            f"{source_id}: identityFieldMap.externalId must equal "
                            "recordKeyField"
                        )
                    if (
                        official_legal_type_field is not None
                        and identity_field_map["officialLegalType"]
                        != official_legal_type_field
                    ):
                        raise RolloutError(
                            f"{source_id}: identityFieldMap.officialLegalType must "
                            "equal officialLegalTypeField"
                        )
                    if (
                        type(external_id_namespace) is not str
                        or re.fullmatch(
                            r"^[a-z0-9]+(?:[._-][a-z0-9]+)*$",
                            external_id_namespace,
                        )
                        is None
                    ):
                        raise RolloutError(
                            f"{source_id}: externalIdNamespace is invalid"
                        )
            else:
                status = row.get("status")
                if status not in {"source-discovery", "adapter-needed"}:
                    raise RolloutError(
                        f"{source_id}: planned source status must be "
                        "source-discovery or adapter-needed"
                    )
            result[source_id] = row
            if active:
                active_ids.add(source_id)
    return result, active_ids


def _coverage_by_code(coverage_plan: dict[str, Any]) -> dict[str, dict[str, Any]]:
    if (
        coverage_plan.get("schemaVersion")
        != "auditback-national-coverage-plan-1.0.0"
    ):
        raise RolloutError("coverage plan schemaVersion is unsupported")
    rows = coverage_plan.get("jurisdictions")
    if not isinstance(rows, list):
        raise RolloutError("coverage plan jurisdictions must be an array")
    result: dict[str, dict[str, Any]] = {}
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise RolloutError(f"coverage jurisdictions[{index}] must be an object")
        code = row.get("code")
        if not isinstance(code, str) or not code:
            raise RolloutError(f"coverage jurisdictions[{index}].code is required")
        if code in result:
            raise RolloutError(f"duplicate coverage jurisdiction {code}")
        result[code] = row
    return result


def _validate_sgc_geography_index(
    *,
    catalog_by_id: Mapping[str, dict[str, Any]],
    active_source_ids: set[str],
    coverage_plan: dict[str, Any],
) -> ValidatedSgcIndex:
    document = load_json_object(
        SGC_GEOGRAPHY_INDEX_PATH,
        label="pinned SGC geography index",
    )
    schema = load_json_object(
        SGC_GEOGRAPHY_INDEX_SCHEMA_PATH,
        label="SGC geography index schema",
    )
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as exc:
        raise RolloutError("SGC geography index schema is invalid") from exc
    errors = sorted(
        Draft202012Validator(schema).iter_errors(document),
        key=lambda error: tuple(str(item) for item in error.absolute_path),
    )
    if errors:
        error = errors[0]
        location = ".".join(str(item) for item in error.absolute_path)
        suffix = f".{location}" if location else ""
        raise RolloutError(
            f"pinned SGC geography index{suffix} violates its schema: "
            f"{error.message}"
        )

    digest_input = {
        field: value
        for field, value in document.items()
        if field != "indexCanonicalSha256"
    }
    observed_digest = canonical_sha256(digest_input)
    if document["indexCanonicalSha256"] != observed_digest:
        raise RolloutError("pinned SGC geography index self-digest is invalid")
    if observed_digest != SGC_GEOGRAPHY_INDEX_CANONICAL_SHA256:
        raise RolloutError(
            "pinned SGC geography index differs from the reviewed release digest"
        )

    classification_version = coverage_plan.get("classificationVersion")
    if (
        not isinstance(classification_version, str)
        or classification_version != document["classificationVersion"]
    ):
        raise RolloutError(
            "coverage plan classificationVersion differs from the pinned SGC index"
        )
    source = document["source"]
    source_id = source["sourceId"]
    catalog_source = catalog_by_id.get(source_id)
    if catalog_source is None or source_id not in active_source_ids:
        raise RolloutError(
            "pinned SGC index source must be active in the source catalog"
        )
    if (
        catalog_source.get("jurisdiction") != "CA"
        or catalog_source.get("coverageLayer") != "national-geography-baseline"
        or catalog_source.get("classificationVersion") != classification_version
        or catalog_source.get("approvedSha256") != source["sha256"]
    ):
        raise RolloutError(
            "pinned SGC index source differs from the active catalog release"
        )

    geography_ids = document["geographyIds"]
    if geography_ids != sorted(geography_ids):
        raise RolloutError("pinned SGC geography IDs must be sorted")
    geography_id_set = frozenset(geography_ids)
    if len(geography_id_set) != len(geography_ids):
        raise RolloutError("pinned SGC geography IDs must be unique")

    observed_counts = {
        "region": 0,
        "province-territory": 0,
        "census-division": 0,
        "census-subdivision": 0,
    }
    parent_by_id: dict[str, str | None] = {}
    for geography_id in geography_ids:
        match = SGC_GEOGRAPHY_ID_RE.fullmatch(geography_id)
        if match is None or match.group("year") != classification_version:
            raise RolloutError(
                f"pinned SGC index contains malformed geography ID {geography_id!r}"
            )
        level = match.group("level")
        code = match.group("code")
        observed_counts[level] += 1
        if level == "province-territory":
            if PROVINCE_TERRITORY_ISO_BY_SGC.get(code) is None:
                raise RolloutError(
                    f"pinned SGC index contains unknown province code {code!r}"
                )
            parent_id = (
                f"ca:sgc:{classification_version}:region:{code[:1]}"
            )
        elif level == "census-division":
            if PROVINCE_TERRITORY_ISO_BY_SGC.get(code[:2]) is None:
                raise RolloutError(
                    f"pinned SGC index contains unknown division province "
                    f"prefix {code[:2]!r}"
                )
            parent_id = (
                f"ca:sgc:{classification_version}:province-territory:{code[:2]}"
            )
        elif level == "census-subdivision":
            if PROVINCE_TERRITORY_ISO_BY_SGC.get(code[:2]) is None:
                raise RolloutError(
                    f"pinned SGC index contains unknown subdivision province "
                    f"prefix {code[:2]!r}"
                )
            parent_id = (
                f"ca:sgc:{classification_version}:census-division:{code[:4]}"
            )
        else:
            parent_id = None
        parent_by_id[geography_id] = parent_id
        if parent_id is not None and parent_id not in geography_id_set:
            raise RolloutError(
                f"pinned SGC index is missing parent {parent_id!r} for "
                f"{geography_id!r}"
            )

    if document["counts"] != observed_counts:
        raise RolloutError(
            "pinned SGC index counts differ from its geography IDs"
        )
    if coverage_plan.get("expectedGeographyCounts") != observed_counts:
        raise RolloutError(
            "coverage plan expectedGeographyCounts differs from the pinned SGC index"
        )
    return ValidatedSgcIndex(
        classification_version=classification_version,
        geography_ids=geography_id_set,
        parent_by_id=parent_by_id,
    )


def _require_string(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RolloutError(f"{label} must be a non-empty string")
    return value


def _require_optional_repo_path(value: Any, *, label: str) -> str | None:
    if value is None:
        return None
    path = _require_string(value, label=label)
    if PATH_RE.fullmatch(path) is None:
        raise RolloutError(f"{label} must be a safe repository-relative path")
    return path


def _existing_repo_file(path: str, *, label: str) -> Path:
    resolved = (REPOSITORY_ROOT / path).resolve()
    try:
        resolved.relative_to(REPOSITORY_ROOT.resolve())
    except ValueError as exc:
        raise RolloutError(f"{label} resolves outside the repository") from exc
    if not resolved.is_file():
        raise RolloutError(f"{label} does not exist as a repository file: {path}")
    if resolved.stat().st_size < 1:
        raise RolloutError(f"{label} must not be empty: {path}")
    return resolved


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_snapshot_date(value: Any, *, label: str, date_only: bool) -> None:
    if not isinstance(value, str) or not value.strip():
        raise RolloutError(f"{label} must be a non-empty ISO date")
    try:
        if date_only:
            date.fromisoformat(value)
        else:
            datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        kind = "date" if date_only else "date-time"
        raise RolloutError(f"{label} must be a valid ISO {kind}") from exc


def _validate_source_lock(
    *,
    path: str,
    label: str,
    source_ids: list[str],
    catalog_by_id: Mapping[str, dict[str, Any]],
    source_bundle_canonical_sha256: str,
    coverage_layer_canonical_sha256: str,
) -> ValidatedSourceLock:
    document = load_json_object(
        _existing_repo_file(path, label=label),
        label=label,
    )
    if set(document) != {
        "schemaVersion",
        "sourceBundleCanonicalSha256",
        "coverageLayerCanonicalSha256",
        "snapshots",
        "sourceLockCanonicalSha256",
    }:
        raise RolloutError(f"{label} must use the exact source-lock contract")
    if (
        document.get("schemaVersion")
        != "auditback-jurisdiction-source-lock-1.0.0"
    ):
        raise RolloutError(
            f"{label}.schemaVersion must be "
            "auditback-jurisdiction-source-lock-1.0.0"
        )
    if (
        document.get("sourceBundleCanonicalSha256")
        != source_bundle_canonical_sha256
    ):
        raise RolloutError(f"{label} is not bound to the current source bundle")
    if (
        document.get("coverageLayerCanonicalSha256")
        != coverage_layer_canonical_sha256
    ):
        raise RolloutError(f"{label} is not bound to the current coverage layer")
    claimed_digest = document.get("sourceLockCanonicalSha256")
    if not isinstance(claimed_digest, str) or SHA256_RE.fullmatch(claimed_digest) is None:
        raise RolloutError(f"{label}.sourceLockCanonicalSha256 is required")
    digest_input = dict(document)
    del digest_input["sourceLockCanonicalSha256"]
    if canonical_sha256(digest_input) != claimed_digest:
        raise RolloutError(f"{label} canonical digest does not match its contents")
    snapshots = document.get("snapshots")
    if not isinstance(snapshots, list):
        raise RolloutError(f"{label}.snapshots must be an array")
    by_source: dict[str, dict[str, Any]] = {}
    payloads: dict[str, bytes] = {}
    for index, snapshot in enumerate(snapshots):
        if not isinstance(snapshot, dict):
            raise RolloutError(f"{label}.snapshots[{index}] must be an object")
        source_id = snapshot.get("sourceId")
        if not isinstance(source_id, str) or not source_id:
            raise RolloutError(f"{label}.snapshots[{index}].sourceId is required")
        if source_id in by_source:
            raise RolloutError(f"{label} has duplicate snapshot for {source_id}")
        allowed_snapshot_fields = {
            "sourceId",
            "sha256",
            "byteLength",
            "mediaType",
            "requestUrl",
            "retrievedAt",
            "effectiveDate",
            "etag",
            "lastModified",
            "objectPath",
        }
        if not set(snapshot).issubset(allowed_snapshot_fields):
            raise RolloutError(
                f"{label}.snapshots[{index}] contains unsupported fields"
            )
        by_source[source_id] = snapshot
    if set(by_source) != set(source_ids):
        missing = sorted(set(source_ids) - set(by_source))
        extra = sorted(set(by_source) - set(source_ids))
        details = []
        if missing:
            details.append(f"missing {', '.join(missing)}")
        if extra:
            details.append(f"unexpected {', '.join(extra)}")
        raise RolloutError(
            f"{label} snapshots must exactly match the source bundle: "
            + "; ".join(details)
        )
    for source_id in source_ids:
        snapshot = by_source[source_id]
        source = catalog_by_id[source_id]
        if snapshot.get("sha256") != source["approvedSha256"]:
            raise RolloutError(
                f"{label}: {source_id} snapshot hash differs from the active catalog"
            )
        if snapshot.get("requestUrl") != source["requestUrl"]:
            raise RolloutError(
                f"{label}: {source_id} request URL differs from the active catalog"
            )
        if snapshot.get("mediaType") != source["mediaType"]:
            raise RolloutError(
                f"{label}: {source_id} media type differs from the active catalog"
            )
        byte_length = snapshot.get("byteLength")
        if (
            isinstance(byte_length, bool)
            or not isinstance(byte_length, int)
            or byte_length < 1
        ):
            raise RolloutError(
                f"{label}: {source_id} snapshot requires a positive byteLength"
            )
        retrieved_at = snapshot.get("retrievedAt")
        effective_date = snapshot.get("effectiveDate")
        if retrieved_at is None and effective_date is None:
            raise RolloutError(
                f"{label}: {source_id} snapshot requires retrievedAt or effectiveDate"
            )
        if retrieved_at is not None:
            _validate_snapshot_date(
                retrieved_at,
                label=f"{label}: {source_id}.retrievedAt",
                date_only=False,
            )
        if effective_date is not None:
            _validate_snapshot_date(
                effective_date,
                label=f"{label}: {source_id}.effectiveDate",
                date_only=True,
            )
        object_path = _require_optional_repo_path(
            snapshot.get("objectPath"),
            label=f"{label}: {source_id}.objectPath",
        )
        if object_path is None:
            raise RolloutError(
                f"{label}: {source_id} snapshot requires a locked objectPath"
            )
        payload_path = _existing_repo_file(
            object_path,
            label=f"{label}: {source_id}.objectPath",
        )
        if payload_path.stat().st_size != byte_length:
            raise RolloutError(
                f"{label}: {source_id} payload byte length differs from its lock"
            )
        if _sha256_file(payload_path) != snapshot["sha256"]:
            raise RolloutError(
                f"{label}: {source_id} payload hash differs from its lock"
            )
        payloads[source_id] = payload_path.read_bytes()
    return ValidatedSourceLock(
        canonical_sha256=claimed_digest,
        snapshots=by_source,
        payloads=payloads,
        record_key_fields={
            source_id: catalog_by_id[source_id]["recordKeyField"]
            for source_id in source_ids
        },
        record_collection_paths={
            source_id: catalog_by_id[source_id]["recordCollectionPath"]
            for source_id in source_ids
        },
        official_legal_type_fields={
            source_id: catalog_by_id[source_id].get("officialLegalTypeField")
            for source_id in source_ids
        },
        identity_field_maps={
            source_id: catalog_by_id[source_id].get("identityFieldMap")
            for source_id in source_ids
        },
        external_id_namespaces={
            source_id: catalog_by_id[source_id].get("externalIdNamespace")
            for source_id in source_ids
        },
    )


def _validate_adapter_code_contract(
    *,
    module_path: str,
    test_path: str,
    adapter_id: str,
    adapter_version: str,
    label: str,
) -> None:
    module_file = _existing_repo_file(module_path, label=f"{label}.modulePath")
    test_file = _existing_repo_file(test_path, label=f"{label}.testPath")
    try:
        module_tree = ast.parse(
            module_file.read_text(encoding="utf-8"),
            filename=module_path,
        )
        test_tree = ast.parse(
            test_file.read_text(encoding="utf-8"),
            filename=test_path,
        )
    except (OSError, UnicodeDecodeError, SyntaxError) as exc:
        raise RolloutError(f"{label} module and test must be valid UTF-8 Python") from exc

    declared: dict[str, str] = {}
    build_function_seen = False
    for node in ast.walk(module_tree):
        if (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == "build_verified_directory"
        ):
            build_function_seen = True
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        value = node.value
        if not isinstance(value, ast.Constant) or not isinstance(value.value, str):
            continue
        for target in targets:
            if isinstance(target, ast.Name) and target.id in {
                "adapter_id",
                "adapter_version",
            }:
                declared[target.id] = value.value
    if declared.get("adapter_id") != adapter_id:
        raise RolloutError(f"{label}.modulePath does not declare the adapter ID")
    if declared.get("adapter_version") != adapter_version:
        raise RolloutError(f"{label}.modulePath does not declare the adapter version")
    if not build_function_seen:
        raise RolloutError(
            f"{label}.modulePath must define build_verified_directory"
        )

    def has_process_exit(tree: ast.AST) -> bool:
        for node in ast.walk(tree):
            if isinstance(node, ast.Raise):
                raised = node.exc
                if isinstance(raised, ast.Name) and raised.id == "SystemExit":
                    return True
                if (
                    isinstance(raised, ast.Call)
                    and isinstance(raised.func, ast.Name)
                    and raised.func.id == "SystemExit"
                ):
                    return True
            if not isinstance(node, ast.Call):
                continue
            function = node.func
            if isinstance(function, ast.Name) and function.id in {"exit", "quit"}:
                return True
            if isinstance(function, ast.Attribute) and function.attr in {
                "_exit",
                "exit",
            }:
                return True
        return False

    if has_process_exit(module_tree):
        raise RolloutError(
            f"{label}.modulePath must not terminate the validation process"
        )
    if has_process_exit(test_tree):
        raise RolloutError(
            f"{label}.testPath must not terminate the test process"
        )

    module_name = module_path[:-3].replace("/", ".")
    module_parent, _, module_leaf = module_name.rpartition(".")
    imports_module = False
    test_case_seen = False
    for node in ast.walk(test_tree):
        if isinstance(node, ast.Import):
            imports_module = imports_module or any(
                alias.name == module_name for alias in node.names
            )
        elif isinstance(node, ast.ImportFrom):
            imports_module = imports_module or (
                node.module == module_name
                or (
                    node.module == module_parent
                    and any(alias.name == module_leaf for alias in node.names)
                )
            )
        elif isinstance(node, ast.ClassDef):
            is_test_case = any(
                (
                    isinstance(base, ast.Name)
                    and base.id == "TestCase"
                )
                or (
                    isinstance(base, ast.Attribute)
                    and base.attr == "TestCase"
                )
                for base in node.bases
            )
            if is_test_case:
                test_case_seen = test_case_seen or any(
                    isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and item.name.startswith("test_")
                    for item in node.body
                )
    if not imports_module:
        raise RolloutError(f"{label}.testPath must import the declared adapter module")
    if not test_case_seen:
        raise RolloutError(
            f"{label}.testPath must contain at least one unittest.TestCase test"
        )

    offline_runner = """
import contextlib
import io
import os
import socket
import subprocess
import sys
import unittest

def blocked(*args, **kwargs):
    raise OSError("AuditBack adapter test guard blocked external I/O")

class OfflineSocket(socket.socket):
    def connect(self, *args, **kwargs):
        return blocked(*args, **kwargs)

    def connect_ex(self, *args, **kwargs):
        return blocked(*args, **kwargs)

socket.socket = OfflineSocket
socket.create_connection = blocked
socket.getaddrinfo = blocked
subprocess.Popen = blocked
os.system = blocked

capture = io.StringIO()
with contextlib.redirect_stdout(capture), contextlib.redirect_stderr(capture):
    suite = unittest.defaultTestLoader.discover(
        sys.argv[1],
        pattern=sys.argv[2],
    )
    result = unittest.TextTestRunner(stream=capture, verbosity=1).run(suite)
if not result.wasSuccessful() or result.testsRun < 1:
    sys.stderr.write(capture.getvalue())
    raise SystemExit(1)
sys.stdout.write(
    "AUDITBACK_TEST_RESULT:__RESULT_TOKEN__:" + str(result.testsRun) + "\\n"
)
"""
    test_parent = str(Path(test_path).parent)
    test_pattern = Path(test_path).name
    result_token = secrets.token_hex(32)
    offline_runner = offline_runner.replace("__RESULT_TOKEN__", result_token)
    environment = os.environ.copy()
    environment["AUDITBACK_OFFLINE"] = "1"
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment["PYTHONNOUSERSITE"] = "1"
    environment["PYTHONPATH"] = str(REPOSITORY_ROOT)
    try:
        completed = subprocess.run(
            [
                sys.executable,
                "-c",
                offline_runner,
                test_parent,
                test_pattern,
            ],
            cwd=REPOSITORY_ROOT,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
            env=environment,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RolloutError(f"{label}.testPath could not be executed offline") from exc
    expected_prefix = f"AUDITBACK_TEST_RESULT:{result_token}:"
    result_text = completed.stdout.strip()
    valid_result = (
        result_text.startswith(expected_prefix)
        and result_text.removeprefix(expected_prefix).isdigit()
        and int(result_text.removeprefix(expected_prefix)) > 0
        and "\n" not in result_text
    )
    if completed.returncode != 0 or not valid_result:
        detail = (completed.stderr or completed.stdout).strip()
        if len(detail) > 800:
            detail = detail[-800:]
        suffix = f": {detail}" if detail else ""
        raise RolloutError(f"{label}.testPath failed its offline test run{suffix}")


def _execute_provider_contract(
    *,
    module_path: str,
    code: str,
    source_lock: ValidatedSourceLock,
    directory: ValidatedDirectory,
    label: str,
) -> None:
    module_file = _existing_repo_file(module_path, label=f"{label}.modulePath")
    provider_runner = """
import base64
import contextlib
import importlib.util
import io
import json
import math
import os
import socket
import subprocess
import sys

def blocked(*args, **kwargs):
    raise OSError("AuditBack provider guard blocked external I/O")

class OfflineSocket(socket.socket):
    def connect(self, *args, **kwargs):
        return blocked(*args, **kwargs)

    def connect_ex(self, *args, **kwargs):
        return blocked(*args, **kwargs)

def require_plain_json(value, path="$"):
    value_type = type(value)
    if value is None or value_type in {str, bool, int}:
        return
    if value_type is float:
        if not math.isfinite(value):
            raise TypeError(path + " contains a non-finite number")
        return
    if value_type is list:
        for index, item in enumerate(value):
            require_plain_json(item, path + "[" + str(index) + "]")
        return
    if value_type is dict:
        for key, item in value.items():
            if type(key) is not str:
                raise TypeError(path + " contains a non-string object key")
            require_plain_json(item, path + "." + key)
        return
    raise TypeError(path + " contains a non-JSON type")

socket.socket = OfflineSocket
socket.create_connection = blocked
socket.getaddrinfo = blocked
subprocess.Popen = blocked
os.system = blocked

request = json.loads(sys.stdin.read())
payloads = {
    source_id: base64.b64decode(payload)
    for source_id, payload in request["payloads"].items()
}
capture = io.StringIO()
with contextlib.redirect_stdout(capture), contextlib.redirect_stderr(capture):
    spec = importlib.util.spec_from_file_location(
        "national.providers._auditback_runtime",
        sys.argv[1],
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("provider module cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    builder = getattr(module, "build_verified_directory", None)
    if not callable(builder):
        raise TypeError("build_verified_directory is not callable")
    result = builder(
        payloads=payloads,
        snapshots=request["snapshots"],
        jurisdiction=request["jurisdiction"],
        source_lock_canonical_sha256=(
            request["sourceLockCanonicalSha256"]
        ),
    )
    require_plain_json(result)
serialized = json.dumps(
    result,
    allow_nan=False,
    ensure_ascii=False,
    separators=(",", ":"),
    sort_keys=True,
)
sys.stdout.write(
    "AUDITBACK_PROVIDER_RESULT:__RESULT_TOKEN__:" + serialized + "\\n"
)
"""
    request = {
        "payloads": {
            source_id: base64.b64encode(payload).decode("ascii")
            for source_id, payload in source_lock.payloads.items()
        },
        "snapshots": source_lock.snapshots,
        "jurisdiction": code,
        "sourceLockCanonicalSha256": source_lock.canonical_sha256,
    }
    environment = os.environ.copy()
    environment["AUDITBACK_OFFLINE"] = "1"
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment["PYTHONNOUSERSITE"] = "1"
    environment["PYTHONPATH"] = str(REPOSITORY_ROOT)

    def run_once() -> dict[str, Any]:
        token = secrets.token_hex(32)
        runner = provider_runner.replace("__RESULT_TOKEN__", token)
        try:
            completed = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    runner,
                    str(module_file),
                ],
                cwd=REPOSITORY_ROOT,
                input=json.dumps(request, separators=(",", ":"), sort_keys=True),
                capture_output=True,
                text=True,
                timeout=120,
                check=False,
                env=environment,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise RolloutError(
                f"{label}.modulePath could not be executed in isolation"
            ) from exc
        prefix = f"AUDITBACK_PROVIDER_RESULT:{token}:"
        output = completed.stdout.strip()
        if (
            completed.returncode != 0
            or not output.startswith(prefix)
            or "\n" in output
        ):
            detail = (completed.stderr or completed.stdout).strip()
            if len(detail) > 800:
                detail = detail[-800:]
            suffix = f": {detail}" if detail else ""
            raise RolloutError(
                f"{label}.modulePath failed isolated provider execution{suffix}"
            )
        try:
            result = json.loads(output.removeprefix(prefix))
        except json.JSONDecodeError as exc:
            raise RolloutError(
                f"{label}.modulePath returned invalid JSON"
            ) from exc
        if type(result) is not dict:
            raise RolloutError(
                f"{label}.modulePath must return a plain verified-directory object"
            )
        return result

    first = run_once()
    second = run_once()
    if first != second:
        raise RolloutError(f"{label}.modulePath produced nondeterministic output")
    if first != directory.document:
        raise RolloutError(
            f"{label}.modulePath output differs from the reviewed directory artifact"
        )


def _locked_structured_records(
    *,
    source_id: str,
    source_lock: ValidatedSourceLock,
    label: str,
) -> list[dict[str, str]]:
    payload = source_lock.payloads[source_id]
    media_type = source_lock.snapshots[source_id]["mediaType"].lower()
    collection_path = source_lock.record_collection_paths[source_id]
    record_key_field = source_lock.record_key_fields[source_id]

    def scalar_text(value: Any, *, field: str) -> str:
        if value is None or type(value) not in {str, int, float, bool}:
            raise RolloutError(
                f"{label} field {field!r} must resolve to a scalar source value"
            )
        return str(value).strip()

    records: list[dict[str, str]]
    if media_type in {"text/csv", "application/csv"}:
        if collection_path != "$":
            raise RolloutError(
                f"{label} CSV source recordCollectionPath must be $"
            )
        try:
            text = payload.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = payload.decode("cp1252")
        reader = csv.DictReader(text.splitlines())
        headers = reader.fieldnames or []
        if record_key_field not in headers:
            raise RolloutError(
                f"{label} recordKeyField {record_key_field!r} is absent from "
                "the locked CSV headers"
            )
        records = [
            {
                field: (value or "").strip()
                for field, value in row.items()
                if field is not None
            }
            for row in reader
        ]
    elif media_type == "application/json" or media_type.endswith("+json"):
        try:
            collection: Any = json.loads(payload)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RolloutError(
                f"{label} locked JSON source payload is invalid"
            ) from exc
        if collection_path != "$":
            for segment in collection_path.removeprefix("$.").split("."):
                if not isinstance(collection, dict) or segment not in collection:
                    raise RolloutError(
                        f"{label} recordCollectionPath does not exist in locked JSON"
                    )
                collection = collection[segment]
        if not isinstance(collection, list) or any(
            not isinstance(record, dict) for record in collection
        ):
            raise RolloutError(
                f"{label} JSON recordCollectionPath must select an array of objects"
            )
        records = []
        for index, record in enumerate(collection):
            normalized: dict[str, str] = {}
            for field, value in record.items():
                if type(field) is not str:
                    raise RolloutError(
                        f"{label} JSON record {index} has a non-string field"
                    )
                normalized[field] = scalar_text(value, field=field)
            records.append(normalized)
    else:
        raise RolloutError(
            f"{label} requires a locked CSV or JSON evidence payload; opaque "
            "formats must first produce a separately locked normalized evidence "
            "source"
        )

    keys: set[str] = set()
    for index, record in enumerate(records):
        record_key = record.get(record_key_field, "").strip()
        if not record_key:
            raise RolloutError(
                f"{label} record {index} has an empty catalogued record key"
            )
        if record_key in keys:
            raise RolloutError(
                f"{label} contains duplicate record key {record_key!r}"
            )
        keys.add(record_key)
    if not records:
        raise RolloutError(f"{label} contains no structured source records")
    return records


def _validate_evidence_payload_binding(
    *,
    evidence: Mapping[str, Any],
    source_lock: ValidatedSourceLock,
    label: str,
) -> dict[str, str]:
    source_id = evidence["sourceId"]
    source_fields = evidence["sourceFields"]
    record_key_field = source_lock.record_key_fields[source_id]
    if source_fields[0] != record_key_field:
        raise RolloutError(
            f"{label}.sourceFields[0] must equal the catalogued recordKeyField "
            f"{record_key_field!r}"
        )
    records = _locked_structured_records(
        source_id=source_id,
        source_lock=source_lock,
        label=label,
    )
    missing_fields = [
        field
        for field in source_fields
        if any(field not in record for record in records)
    ]
    if missing_fields:
        raise RolloutError(
            f"{label}.sourceFields are absent from the locked record contract: "
            f"{', '.join(missing_fields)}"
        )
    matches = [
        record
        for record in records
        if record[record_key_field] == evidence["recordKey"]
    ]
    if len(matches) != 1:
        raise RolloutError(
            f"{label}.recordKey must select exactly one locked structured record "
            f"via the catalogued key field {record_key_field!r}"
        )
    return {
        field: matches[0][field]
        for field in source_fields
    }


def _validate_directory_output(
    *,
    path: str,
    raw_sha256: str,
    canonical_digest: str,
    label: str,
    code: str,
    sgc_code: str,
    canonical_body_types: list[str],
    source_ids: list[str],
    source_roles: Mapping[str, list[str]],
    source_lock: ValidatedSourceLock,
    sgc_index: ValidatedSgcIndex,
    adapter_id: str,
    adapter_version: str,
) -> ValidatedDirectory:
    resolved = _existing_repo_file(path, label=label)
    if SHA256_RE.fullmatch(raw_sha256) is None:
        raise RolloutError(f"{label} raw SHA-256 is invalid")
    observed_raw_sha256 = _sha256_file(resolved)
    if observed_raw_sha256 != raw_sha256:
        raise RolloutError(f"{label} raw SHA-256 differs from the output manifest")
    document = load_json_object(resolved, label=label)
    if SHA256_RE.fullmatch(canonical_digest) is None:
        raise RolloutError(f"{label} canonical SHA-256 is invalid")
    observed_canonical_sha256 = canonical_sha256(document)
    if observed_canonical_sha256 != canonical_digest:
        raise RolloutError(
            f"{label} canonical SHA-256 differs from the output manifest"
        )
    validator = _verified_directory_validator()
    errors = sorted(
        validator.iter_errors(document),
        key=lambda error: tuple(str(item) for item in error.absolute_path),
    )
    if errors:
        error = errors[0]
        location = ".".join(str(item) for item in error.absolute_path)
        suffix = f".{location}" if location else ""
        raise RolloutError(
            f"{label}{suffix} violates the verified directory schema: "
            f"{error.message}"
        )
    if document["candidateOnly"] is not False:
        raise RolloutError(f"{label}.candidateOnly must be false after review")
    if document["jurisdiction"] != code:
        raise RolloutError(f"{label}.jurisdiction must be {code}")
    if document["sourceLockCanonicalSha256"] != source_lock.canonical_sha256:
        raise RolloutError(f"{label} is not bound to the verified source lock")
    if document["adapter"] != {"id": adapter_id, "version": adapter_version}:
        raise RolloutError(f"{label} adapter identity differs from the manifest")

    records = tuple(document["records"])
    body_by_id: dict[str, dict[str, Any]] = {}
    external_ids: dict[tuple[str, str], str] = {}
    relationship_source_values: dict[
        tuple[str, str],
        tuple[set[str], str],
    ] = {}
    for index, record in enumerate(records):
        row_label = f"{label}.records[{index}]"
        body = record["body"]
        provenance = record["provenance"]
        body_id = body["id"]
        if body_id in body_by_id:
            raise RolloutError(f"{row_label}.body.id duplicates {body_id!r}")
        body_by_id[body_id] = body
        if body["bodyType"] not in canonical_body_types:
            raise RolloutError(
                f"{row_label}.body.bodyType is outside the jurisdiction manifest"
            )
        if body["provinceTerritory"] != code:
            raise RolloutError(
                f"{row_label}.body.provinceTerritory must be {code}"
            )
        for namespace, value in body["externalIds"].items():
            identity = (namespace, value)
            if identity in external_ids:
                raise RolloutError(
                    f"{row_label} reuses official external ID {identity!r} "
                    f"from {external_ids[identity]!r}"
                )
            external_ids[identity] = body_id
        for field in ("effectiveFrom", "effectiveTo"):
            value = body[field]
            if value is not None:
                _validate_snapshot_date(
                    value,
                    label=f"{row_label}.body.{field}",
                    date_only=True,
                )
        if (
            body["effectiveFrom"] is not None
            and body["effectiveTo"] is not None
            and date.fromisoformat(body["effectiveTo"])
            < date.fromisoformat(body["effectiveFrom"])
        ):
            raise RolloutError(
                f"{row_label}.body.effectiveTo precedes effectiveFrom"
            )
        for geography_id in body["governsGeographyIds"]:
            match = SGC_GEOGRAPHY_ID_RE.fullmatch(geography_id)
            if (
                match is None
                or match.group("year") != sgc_index.classification_version
                or match.group("level")
                not in {"census-division", "census-subdivision"}
                or not match.group("code").startswith(sgc_code)
            ):
                raise RolloutError(
                    f"{row_label} has a non-jurisdictional or malformed SGC "
                    f"geography ID {geography_id!r}"
                )
            if geography_id not in sgc_index.geography_ids:
                raise RolloutError(
                    f"{row_label} geography ID {geography_id!r} is absent from "
                    "the pinned official SGC index"
                )
        source_id = provenance["sourceId"]
        if source_id not in source_ids:
            raise RolloutError(
                f"{row_label}.provenance.sourceId is outside the source bundle"
            )
        if not set(source_roles[source_id]).intersection(IDENTITY_SOURCE_ROLES):
            raise RolloutError(
                f"{row_label}.provenance.sourceId is not an identity source"
            )
        snapshot = source_lock.snapshots[source_id]
        if provenance["snapshotSha256"] != snapshot["sha256"]:
            raise RolloutError(
                f"{row_label}.provenance snapshot differs from the source lock"
            )
        if (
            provenance["adapterId"] != adapter_id
            or provenance["adapterVersion"] != adapter_version
        ):
            raise RolloutError(
                f"{row_label}.provenance adapter differs from the manifest"
            )
        identity_record = _validate_evidence_payload_binding(
            evidence=provenance,
            source_lock=source_lock,
            label=f"{row_label}.provenance",
        )
        identity_field_map = provenance["identityFieldMap"]
        catalog_identity_field_map = source_lock.identity_field_maps[source_id]
        external_id_namespace = source_lock.external_id_namespaces[source_id]
        if (
            catalog_identity_field_map is None
            or external_id_namespace is None
        ):
            raise RolloutError(
                f"{row_label}.provenance.sourceId requires a catalogued "
                "identityFieldMap and externalIdNamespace"
            )
        if identity_field_map != catalog_identity_field_map:
            raise RolloutError(
                f"{row_label}.provenance.identityFieldMap differs from the "
                "catalogued identity contract"
            )
        missing_identity_fields = [
            source_field
            for source_field in identity_field_map.values()
            if source_field not in provenance["sourceFields"]
        ]
        if missing_identity_fields:
            raise RolloutError(
                f"{row_label}.provenance.identityFieldMap references fields "
                "outside sourceFields"
            )
        official_external_values = set(body["externalIds"].values())
        if provenance["recordKey"] not in official_external_values:
            raise RolloutError(
                f"{row_label}.provenance.recordKey must equal one of the body's "
                "official external ID values"
            )
        if official_external_values.isdisjoint(identity_record.values()):
            raise RolloutError(
                f"{row_label}.provenance source row does not contain a body "
                "official external ID"
            )
        exact_identity_values = {
            canonical_field: identity_record[source_field]
            for canonical_field, source_field in identity_field_map.items()
        }
        expected_external_ids = {
            external_id_namespace: exact_identity_values["externalId"]
        }
        if body["externalIds"] != expected_external_ids:
            raise RolloutError(
                f"{row_label}.body.externalIds differ from the exact catalogued "
                "namespace and locked source field"
            )
        if set(body["officialNames"].values()) != {
            exact_identity_values["officialName"]
        }:
            raise RolloutError(
                f"{row_label}.body.officialName differs from the exact locked "
                "source field or adds unverified values"
            )
        identity_comparisons = {
            "officialLegalType": body["officialLegalType"],
            "officialUrl": body["officialUrl"],
        }
        for canonical_field, observed_value in identity_comparisons.items():
            if observed_value != exact_identity_values[canonical_field]:
                raise RolloutError(
                    f"{row_label}.body.{canonical_field} differs from the exact "
                    "locked source field"
                )

        geography_evidence = provenance["geographyEvidence"]
        evidence_geographies = {
            evidence["geographyId"] for evidence in geography_evidence
        }
        if evidence_geographies != set(body["governsGeographyIds"]):
            raise RolloutError(
                f"{row_label}.provenance.geographyEvidence must prove every and "
                "only the body's exact geography IDs"
            )
        for evidence_index, evidence in enumerate(geography_evidence):
            evidence_label = (
                f"{row_label}.provenance.geographyEvidence[{evidence_index}]"
            )
            evidence_source_id = evidence["sourceId"]
            if evidence_source_id not in source_ids:
                raise RolloutError(
                    f"{evidence_label}.sourceId is outside the source bundle"
                )
            if not set(source_roles[evidence_source_id]).intersection(
                CROSSWALK_SOURCE_ROLES
            ):
                raise RolloutError(
                    f"{evidence_label}.sourceId is not approved to prove exact "
                    "crosswalks"
                )
            if (
                evidence["snapshotSha256"]
                != source_lock.snapshots[evidence_source_id]["sha256"]
            ):
                raise RolloutError(
                    f"{evidence_label} snapshot differs from the source lock"
                )
            geography_record = _validate_evidence_payload_binding(
                evidence=evidence,
                source_lock=source_lock,
                label=evidence_label,
            )
            geography_values = set(geography_record.values())
            if official_external_values.isdisjoint(geography_values):
                raise RolloutError(
                    f"{evidence_label} source row does not contain a body "
                    "official external ID"
                )
            geography_match = SGC_GEOGRAPHY_ID_RE.fullmatch(
                evidence["geographyId"]
            )
            if (
                geography_match is None
                or (
                    geography_match.group("code") not in geography_values
                    and evidence["geographyId"] not in geography_values
                )
            ):
                raise RolloutError(
                    f"{evidence_label} source row does not contain the claimed "
                    "official geography code"
                )

        relationship_evidence = provenance["relationshipEvidence"]
        evidence_parents = {
            evidence["parentBodyId"] for evidence in relationship_evidence
        }
        if evidence_parents != set(body["parentBodyIds"]):
            raise RolloutError(
                f"{row_label}.provenance.relationshipEvidence must prove every "
                "and only the body's parent relationships"
            )
        for evidence_index, evidence in enumerate(relationship_evidence):
            evidence_label = (
                f"{row_label}.provenance.relationshipEvidence[{evidence_index}]"
            )
            evidence_source_id = evidence["sourceId"]
            if evidence_source_id not in source_ids:
                raise RolloutError(
                    f"{evidence_label}.sourceId is outside the source bundle"
                )
            if "relationship-reference" not in source_roles[evidence_source_id]:
                raise RolloutError(
                    f"{evidence_label}.sourceId is not approved to prove "
                    "parent relationships"
                )
            if (
                evidence["snapshotSha256"]
                != source_lock.snapshots[evidence_source_id]["sha256"]
            ):
                raise RolloutError(
                    f"{evidence_label} snapshot differs from the source lock"
                )
            relationship_record = _validate_evidence_payload_binding(
                evidence=evidence,
                source_lock=source_lock,
                label=evidence_label,
            )
            relationship_source_values[
                (body_id, evidence["parentBodyId"])
            ] = (set(relationship_record.values()), evidence_label)

    for body_id, body in body_by_id.items():
        for parent_id in body["parentBodyIds"]:
            parent = body_by_id.get(parent_id)
            if parent is None:
                raise RolloutError(
                    f"{label}: {body_id} references unknown parent {parent_id!r}"
                )
            if (
                parent["bodyType"] != "regional-government"
                or parent["governmentTier"] != "upper-tier"
                or parent["provinceTerritory"] != code
            ):
                raise RolloutError(
                    f"{label}: lower-tier body {body_id!r} requires an exact "
                    "same-jurisdiction upper-tier regional parent"
                )
            relationship_values, relationship_label = (
                relationship_source_values[(body_id, parent_id)]
            )
            if set(body["externalIds"].values()).isdisjoint(
                relationship_values
            ):
                raise RolloutError(
                    f"{relationship_label} source row does not contain a child "
                    "official external ID"
                )
            if set(parent["externalIds"].values()).isdisjoint(
                relationship_values
            ):
                raise RolloutError(
                    f"{relationship_label} source row does not contain the parent "
                    "official external ID"
                )
            for child_geography_id in body["governsGeographyIds"]:
                current_geography_id: str | None = child_geography_id
                contained = False
                while current_geography_id is not None:
                    if current_geography_id in parent["governsGeographyIds"]:
                        contained = True
                        break
                    current_geography_id = sgc_index.parent_by_id.get(
                        current_geography_id
                    )
                if not contained:
                    raise RolloutError(
                        f"{label}: lower-tier body {body_id!r} geography "
                        f"{child_geography_id!r} is outside parent "
                        f"{parent_id!r}'s governed SGC hierarchy"
                    )

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(body_id: str) -> None:
        if body_id in visited:
            return
        if body_id in visiting:
            raise RolloutError(
                f"{label}: governing-body parent relationship cycle includes "
                f"{body_id!r}"
            )
        visiting.add(body_id)
        for parent_id in body_by_id[body_id]["parentBodyIds"]:
            visit(parent_id)
        visiting.remove(body_id)
        visited.add(body_id)

    for body_id in sorted(body_by_id):
        visit(body_id)

    return ValidatedDirectory(
        raw_sha256=observed_raw_sha256,
        canonical_sha256=observed_canonical_sha256,
        source_lock_sha256=source_lock.canonical_sha256,
        records=records,
        document=document,
    )


def _read_review_csv(
    *,
    path: str,
    label: str,
    headers: tuple[str, ...],
) -> list[dict[str, str]]:
    resolved = _existing_repo_file(path, label=label)
    try:
        with resolved.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if tuple(reader.fieldnames or ()) != headers:
                raise RolloutError(
                    f"{label} must use the exact reviewed column contract"
                )
            rows = list(reader)
    except UnicodeDecodeError as exc:
        raise RolloutError(f"{label} must be UTF-8 CSV") from exc
    if not rows:
        raise RolloutError(f"{label} must contain at least one reviewed row")
    return rows


def _validate_classification_review(
    *,
    path: str,
    label: str,
    source_ids: list[str],
    canonical_body_types: list[str],
) -> list[dict[str, str]]:
    rows = _read_review_csv(
        path=path,
        label=label,
        headers=CLASSIFICATION_HEADERS,
    )
    emitting_decision_seen = False
    for index, row in enumerate(rows, start=2):
        row_label = f"{label} row {index}"
        for field in (
            "sourceId",
            "sourceRecordKey",
            "officialLegalType",
            "layerDisposition",
            "reviewer",
            "status",
        ):
            if not row[field].strip():
                raise RolloutError(f"{row_label}.{field} is required")
        if row["sourceId"] not in source_ids:
            raise RolloutError(f"{row_label}.sourceId is outside the source bundle")
        if row["status"] not in {"approved", "routed", "excluded"}:
            raise RolloutError(
                f"{row_label}.status must be approved, routed, or excluded"
            )
        disposition = row["layerDisposition"]
        if disposition not in {
            "emit-municipal-layer",
            "route-other-layer",
            "geography-only",
            "non-government",
            "excluded-with-reason",
        }:
            raise RolloutError(f"{row_label}.layerDisposition is unsupported")
        expected_status = {
            "emit-municipal-layer": "approved",
            "route-other-layer": "routed",
            "geography-only": "routed",
            "non-government": "excluded",
            "excluded-with-reason": "excluded",
        }[disposition]
        if row["status"] != expected_status:
            raise RolloutError(
                f"{row_label}.status must be {expected_status!r} for "
                f"{disposition!r}"
            )
        if disposition == "emit-municipal-layer":
            emitting_decision_seen = True
            if row["canonicalBodyType"] not in canonical_body_types:
                raise RolloutError(
                    f"{row_label}.canonicalBodyType is not approved by the manifest"
                )
            if not row["tier"].strip():
                raise RolloutError(
                    f"{row_label}.tier is required for emitted governments"
                )
        elif row["canonicalBodyType"].strip():
            raise RolloutError(
                f"{row_label}.canonicalBodyType must be blank outside the "
                "municipal layer"
            )
        for field in ("effectiveFrom", "effectiveTo"):
            value = row[field].strip()
            if value and DATE_RE.fullmatch(value) is None:
                raise RolloutError(f"{row_label}.{field} must be YYYY-MM-DD")
        if (
            disposition != "emit-municipal-layer"
            and not row["notes"].strip()
        ):
            raise RolloutError(
                f"{row_label}.notes must explain non-municipal disposition"
            )
    if not emitting_decision_seen:
        raise RolloutError(
            f"{label} must approve at least one municipal-layer legal type"
        )
    return rows


def _validate_roster_inventory(
    *,
    rows: list[dict[str, str]],
    source_lock: ValidatedSourceLock,
    source_roles: Mapping[str, list[str]],
    label: str,
) -> None:
    reviewed_by_source: dict[str, set[str]] = {}
    reviewed_rows_by_source: dict[str, dict[str, dict[str, str]]] = {}
    for index, row in enumerate(rows, start=2):
        identity = (row["sourceId"], row["sourceRecordKey"])
        reviewed = reviewed_by_source.setdefault(row["sourceId"], set())
        if row["sourceRecordKey"] in reviewed:
            raise RolloutError(
                f"{label} row {index} duplicates source record {identity!r}"
            )
        reviewed.add(row["sourceRecordKey"])
        reviewed_rows_by_source.setdefault(row["sourceId"], {})[
            row["sourceRecordKey"]
        ] = row

    for source_id, roles in source_roles.items():
        if "governing-body-roster" not in roles:
            continue
        records = _locked_structured_records(
            source_id=source_id,
            source_lock=source_lock,
            label=f"{label}: {source_id} roster inventory",
        )
        record_key_field = source_lock.record_key_fields[source_id]
        official_legal_type_field = (
            source_lock.official_legal_type_fields[source_id]
        )
        if official_legal_type_field is None:
            raise RolloutError(
                f"{label}: governing-body roster {source_id!r} requires a "
                "catalogued officialLegalTypeField"
            )
        if any(official_legal_type_field not in record for record in records):
            raise RolloutError(
                f"{label}: roster {source_id!r} does not contain catalogued "
                f"officialLegalTypeField {official_legal_type_field!r}"
            )
        official_keys = {
            record[record_key_field]
            for record in records
        }
        reviewed_keys = reviewed_by_source.get(source_id, set())
        if reviewed_keys != official_keys:
            missing = sorted(official_keys - reviewed_keys)
            extra = sorted(reviewed_keys - official_keys)
            details: list[str] = []
            if missing:
                details.append(
                    f"{len(missing)} locked roster record(s) are unreviewed"
                )
            if extra:
                details.append(
                    f"{len(extra)} review record(s) are absent from the roster"
                )
            raise RolloutError(
                f"{label}: every locked governing-body roster record must be "
                "emitted, routed, or explicitly excluded: "
                + "; ".join(details)
            )
        for record in records:
            record_key = record[record_key_field]
            decision = reviewed_rows_by_source[source_id][record_key]
            if (
                decision["officialLegalType"].strip()
                != record[official_legal_type_field]
            ):
                raise RolloutError(
                    f"{label}: classification for {source_id}:{record_key} "
                    "differs from the locked official legal type"
                )


def _validate_crosswalk_review(
    *,
    path: str,
    label: str,
    source_ids: list[str],
    catalog_by_id: Mapping[str, dict[str, Any]],
) -> list[dict[str, str]]:
    rows = _read_review_csv(
        path=path,
        label=label,
        headers=CROSSWALK_HEADERS,
    )
    seen_matches: set[tuple[str, str]] = set()
    seen_unmatched: set[tuple[str, str, str]] = set()
    for index, row in enumerate(rows, start=2):
        row_label = f"{label} row {index}"
        for field in (
            "officialExternalId",
            "sourceId",
            "snapshotSha256",
            "sourceRecordKey",
            "matchMethod",
            "reviewer",
            "status",
        ):
            if not row[field].strip():
                raise RolloutError(f"{row_label}.{field} is required")
        if row["sourceId"] not in source_ids:
            raise RolloutError(f"{row_label}.sourceId is outside the source bundle")
        if SHA256_RE.fullmatch(row["snapshotSha256"]) is None:
            raise RolloutError(
                f"{row_label}.snapshotSha256 must be lowercase SHA-256 hex"
            )
        if row["snapshotSha256"] != catalog_by_id[row["sourceId"]].get(
            "approvedSha256"
        ):
            raise RolloutError(
                f"{row_label}.snapshotSha256 differs from the active catalog"
            )
        if row["matchMethod"] not in {
            "exact-official-code",
            "explicitly-unmatched",
        }:
            raise RolloutError(f"{row_label}.matchMethod is unsupported")
        if row["status"] not in {"matched", "unmatched-reviewed"}:
            raise RolloutError(f"{row_label}.status is unsupported")
        if row["matchMethod"] == "exact-official-code":
            if (
                row["status"] != "matched"
                or not row["bodyId"].strip()
                or not row["sgcGeographyId"].strip()
            ):
                raise RolloutError(
                    f"{row_label}: exact matches require bodyId, SGC ID, "
                    "and matched status"
                )
            if CANONICAL_ID_RE.fullmatch(row["bodyId"]) is None:
                raise RolloutError(f"{row_label}.bodyId is not canonical")
            if SGC_GEOGRAPHY_ID_RE.fullmatch(row["sgcGeographyId"]) is None:
                raise RolloutError(
                    f"{row_label}.sgcGeographyId is not an exact SGC identity"
                )
            match_identity = (row["bodyId"], row["sgcGeographyId"])
            if match_identity in seen_matches:
                raise RolloutError(f"{row_label} duplicates an exact body crosswalk")
            seen_matches.add(match_identity)
        elif row["status"] != "unmatched-reviewed":
            raise RolloutError(
                f"{row_label}: unmatched rows require unmatched-reviewed status"
            )
        else:
            if row["bodyId"].strip() or row["sgcGeographyId"].strip():
                raise RolloutError(
                    f"{row_label}: unmatched rows must not claim body or SGC IDs"
                )
            unmatched_identity = (
                row["sourceId"],
                row["sourceRecordKey"],
                row["officialExternalId"],
            )
            if unmatched_identity in seen_unmatched:
                raise RolloutError(f"{row_label} duplicates an unmatched source row")
            seen_unmatched.add(unmatched_identity)
    return rows


def _crosslink_classification_review(
    *,
    rows: list[dict[str, str]],
    directory: ValidatedDirectory,
    label: str,
) -> None:
    approved_emissions: dict[tuple[str, str], dict[str, str]] = {}
    for index, row in enumerate(rows, start=2):
        if (
            row["layerDisposition"] != "emit-municipal-layer"
            or row["status"] != "approved"
        ):
            continue
        identity = (row["sourceId"], row["sourceRecordKey"])
        if identity in approved_emissions:
            raise RolloutError(
                f"{label} row {index} duplicates an approved source identity"
            )
        approved_emissions[identity] = row

    observed: set[tuple[str, str]] = set()
    for index, record in enumerate(directory.records):
        body = record["body"]
        provenance = record["provenance"]
        identity = (provenance["sourceId"], provenance["recordKey"])
        decision = approved_emissions.get(identity)
        if decision is None:
            raise RolloutError(
                f"{label} has no approved classification for directory record "
                f"{body['id']!r}"
            )
        observed.add(identity)
        expected_parent = ";".join(sorted(body["parentBodyIds"]))
        comparisons = {
            "officialLegalType": body["officialLegalType"],
            "canonicalBodyType": body["bodyType"],
            "tier": body["governmentTier"],
            "parentBodyId": expected_parent,
            "effectiveFrom": body["effectiveFrom"] or "",
            "effectiveTo": body["effectiveTo"] or "",
        }
        for field, expected in comparisons.items():
            if decision[field].strip() != expected:
                raise RolloutError(
                    f"{label} classification for {body['id']!r} has {field} "
                    "that differs from the verified directory"
                )
    extra = sorted(set(approved_emissions) - observed)
    if extra:
        raise RolloutError(
            f"{label} contains approved emitted rows absent from the directory"
        )


def _crosslink_crosswalk_review(
    *,
    rows: list[dict[str, str]],
    directory: ValidatedDirectory,
    source_lock: ValidatedSourceLock,
    source_roles: Mapping[str, list[str]],
    label: str,
    sgc_code: str,
) -> int:
    records = {
        record["body"]["id"]: record
        for record in directory.records
    }
    bodies = {
        body_id: record["body"]
        for body_id, record in records.items()
    }
    geography_evidence = {
        (body_id, evidence["geographyId"]): evidence
        for body_id, record in records.items()
        for evidence in record["provenance"]["geographyEvidence"]
    }
    expected = {
        (body_id, geography_id)
        for body_id, body in bodies.items()
        for geography_id in body["governsGeographyIds"]
    }
    observed: set[tuple[str, str]] = set()
    unmatched_count = 0
    for index, row in enumerate(rows, start=2):
        row_label = f"{label} row {index}"
        snapshot = source_lock.snapshots.get(row["sourceId"])
        if snapshot is None or snapshot["sha256"] != row["snapshotSha256"]:
            raise RolloutError(
                f"{row_label} is not bound to a verified source snapshot"
            )
        if not set(source_roles[row["sourceId"]]).intersection(
            CROSSWALK_SOURCE_ROLES
        ):
            raise RolloutError(
                f"{row_label}.sourceId is not approved to prove exact crosswalks"
            )
        if row["matchMethod"] == "explicitly-unmatched":
            unmatched_count += 1
            continue
        body = bodies.get(row["bodyId"])
        if body is None:
            raise RolloutError(
                f"{row_label}.bodyId is absent from the verified directory"
            )
        exact_external_ids = {
            f"{namespace}:{value}"
            for namespace, value in body["externalIds"].items()
        }
        if row["officialExternalId"] not in exact_external_ids:
            raise RolloutError(
                f"{row_label}.officialExternalId is not bound to the body record"
            )
        evidence = geography_evidence.get(
            (row["bodyId"], row["sgcGeographyId"])
        )
        if evidence is None:
            raise RolloutError(
                f"{row_label} has no matching provider-emitted geography evidence"
            )
        evidence_values = {
            "sourceId": evidence["sourceId"],
            "snapshotSha256": evidence["snapshotSha256"],
            "sourceRecordKey": evidence["recordKey"],
        }
        for field, expected_value in evidence_values.items():
            if row[field] != expected_value:
                raise RolloutError(
                    f"{row_label}.{field} differs from provider-emitted geography "
                    "evidence"
                )
        geography_match = SGC_GEOGRAPHY_ID_RE.fullmatch(row["sgcGeographyId"])
        if (
            geography_match is None
            or geography_match.group("code").startswith(sgc_code) is False
        ):
            raise RolloutError(
                f"{row_label}.sgcGeographyId is outside the jurisdiction"
            )
        observed.add((row["bodyId"], row["sgcGeographyId"]))
    if observed != expected:
        missing = sorted(expected - observed)
        extra = sorted(observed - expected)
        details = []
        if missing:
            details.append(f"missing {len(missing)} directory crosswalk(s)")
        if extra:
            details.append(f"contains {len(extra)} non-directory crosswalk(s)")
        raise RolloutError(
            f"{label} does not exactly cover the verified directory: "
            + "; ".join(details)
        )
    return unmatched_count


def _validate_exceptions_review(
    *,
    path: str,
    label: str,
    code: str,
    source_ids: list[str],
) -> None:
    document = load_json_object(
        _existing_repo_file(path, label=label),
        label=label,
    )
    if (
        document.get("schemaVersion")
        != "auditback-jurisdiction-exceptions-1.0.0"
    ):
        raise RolloutError(f"{label}.schemaVersion is unsupported")
    if set(document) != {
        "schemaVersion",
        "jurisdiction",
        "candidateOnly",
        "reviewer",
        "reviewedAt",
        "exceptions",
    }:
        raise RolloutError(f"{label} must use the exact exceptions contract")
    if document.get("candidateOnly") is not False:
        raise RolloutError(f"{label}.candidateOnly must be false after review")
    if document.get("jurisdiction") != code:
        raise RolloutError(f"{label}.jurisdiction must be {code}")
    reviewer = document.get("reviewer")
    reviewed_at = document.get("reviewedAt")
    if not isinstance(reviewer, str) or not reviewer.strip():
        raise RolloutError(f"{label}.reviewer is required")
    if not isinstance(reviewed_at, str) or DATE_RE.fullmatch(reviewed_at) is None:
        raise RolloutError(f"{label}.reviewedAt must be YYYY-MM-DD")
    exceptions = document.get("exceptions")
    if not isinstance(exceptions, list):
        raise RolloutError(f"{label}.exceptions must be an array")
    for index, row in enumerate(exceptions):
        row_label = f"{label}.exceptions[{index}]"
        if not isinstance(row, dict):
            raise RolloutError(f"{row_label} must be an object")
        for field in ("sourceId", "sourceRecordKey", "disposition", "reason"):
            value = row.get(field)
            if not isinstance(value, str) or not value.strip():
                raise RolloutError(f"{row_label}.{field} is required")
        if row["sourceId"] not in source_ids:
            raise RolloutError(f"{row_label}.sourceId is outside the source bundle")


def _validate_reconciliation(
    *,
    path: str,
    label: str,
    code: str,
    source_ids: list[str],
    canonical_body_types: list[str],
    expected_count: int,
    reviewed_unmatched_count: int,
    directory: ValidatedDirectory,
    source_roles: Mapping[str, list[str]],
) -> None:
    document = load_json_object(
        _existing_repo_file(path, label=label),
        label=label,
    )
    if (
        document.get("schemaVersion")
        != "auditback-jurisdiction-reconciliation-1.0.0"
    ):
        raise RolloutError(f"{label}.schemaVersion is unsupported")
    if set(document) != {
        "schemaVersion",
        "jurisdiction",
        "candidateOnly",
        "asOfDate",
        "officialControlTotals",
        "emittedCounts",
        "unmatchedCount",
        "reconciled",
        "reviewer",
    }:
        raise RolloutError(f"{label} must use the exact reconciliation contract")
    if document.get("candidateOnly") is not False:
        raise RolloutError(f"{label}.candidateOnly must be false after review")
    if document.get("jurisdiction") != code:
        raise RolloutError(f"{label}.jurisdiction must be {code}")
    if document.get("reconciled") is not True:
        raise RolloutError(f"{label}.reconciled must be true")
    as_of_date = document.get("asOfDate")
    reviewer = document.get("reviewer")
    if not isinstance(as_of_date, str) or DATE_RE.fullmatch(as_of_date) is None:
        raise RolloutError(f"{label}.asOfDate must be YYYY-MM-DD")
    if not isinstance(reviewer, str) or not reviewer.strip():
        raise RolloutError(f"{label}.reviewer is required")
    if document.get("unmatchedCount") != reviewed_unmatched_count:
        raise RolloutError(
            f"{label}.unmatchedCount must equal the reviewed crosswalk gaps "
            f"({reviewed_unmatched_count})"
        )
    if reviewed_unmatched_count != 0:
        raise RolloutError(
            f"{label}: complete reconciliation requires zero unmatched rows"
        )
    control_totals = document.get("officialControlTotals")
    emitted_counts = document.get("emittedCounts")
    if not isinstance(control_totals, list) or not control_totals:
        raise RolloutError(f"{label}.officialControlTotals must not be empty")
    if not isinstance(emitted_counts, list) or not emitted_counts:
        raise RolloutError(f"{label}.emittedCounts must not be empty")

    def positive_count(row: Any, *, row_label: str, field: str) -> int:
        if not isinstance(row, dict):
            raise RolloutError(f"{row_label} must be an object")
        count = row.get(field)
        if isinstance(count, bool) or not isinstance(count, int) or count < 1:
            raise RolloutError(f"{row_label}.{field} must be a positive integer")
        return count

    official_total = 0
    official_identities: set[tuple[str, str, str]] = set()
    for index, row in enumerate(control_totals):
        row_label = f"{label}.officialControlTotals[{index}]"
        official_total += positive_count(
            row,
            row_label=row_label,
            field="expectedActiveCount",
        )
        if row.get("sourceId") not in source_ids:
            raise RolloutError(f"{row_label}.sourceId is outside the source bundle")
        if "control-total" not in source_roles[row["sourceId"]]:
            raise RolloutError(
                f"{row_label}.sourceId is not approved as a control-total source"
            )
        for field in ("officialLegalType", "sourceRecordKey"):
            value = row.get(field)
            if not isinstance(value, str) or not value.strip():
                raise RolloutError(f"{row_label}.{field} is required")
        official_identity = (
            row["sourceId"],
            row["officialLegalType"],
            row["sourceRecordKey"],
        )
        if official_identity in official_identities:
            raise RolloutError(f"{row_label} duplicates an official control total")
        official_identities.add(official_identity)

    actual_by_type: dict[str, int] = {}
    for record in directory.records:
        body = record["body"]
        if body["status"] == "active":
            body_type = body["bodyType"]
            actual_by_type[body_type] = actual_by_type.get(body_type, 0) + 1
    actual_total = sum(actual_by_type.values())
    emitted_by_type: dict[str, int] = {}
    for index, row in enumerate(emitted_counts):
        row_label = f"{label}.emittedCounts[{index}]"
        count = positive_count(row, row_label=row_label, field="count")
        body_type = row.get("canonicalBodyType")
        if body_type not in canonical_body_types:
            raise RolloutError(
                f"{row_label}.canonicalBodyType is not approved by the manifest"
            )
        if body_type in emitted_by_type:
            raise RolloutError(
                f"{row_label}.canonicalBodyType duplicates an emitted subtotal"
            )
        emitted_by_type[body_type] = count
    if emitted_by_type != actual_by_type:
        raise RolloutError(
            f"{label}.emittedCounts must equal active records derived from the "
            "verified directory"
        )
    if official_total != expected_count or actual_total != expected_count:
        raise RolloutError(
            f"{label}: official, directory-derived, and manifest counts must all equal "
            f"{expected_count}"
        )


def _validate_publication_approval(
    *,
    path: str,
    raw_sha256: str,
    label: str,
    code: str,
    reviewer: str,
    approved_at: str,
    release_reference: str,
    expected_count: int,
    source_lock: ValidatedSourceLock,
    directory: ValidatedDirectory,
) -> None:
    if RELEASE_REFERENCE_RE.fullmatch(release_reference) is None:
        raise RolloutError(
            f"{label}.releaseReference must be a commit, release, or pull-request "
            "URL in the configured AuditBack GitHub repository"
        )
    resolved = _existing_repo_file(path, label=label)
    if SHA256_RE.fullmatch(raw_sha256) is None:
        raise RolloutError(f"{label} SHA-256 is invalid")
    if _sha256_file(resolved) != raw_sha256:
        raise RolloutError(f"{label} SHA-256 differs from the approval manifest")
    document = load_json_object(resolved, label=label)
    required_fields = {
        "schemaVersion",
        "jurisdiction",
        "candidateOnly",
        "decision",
        "reviewer",
        "approvedAt",
        "releaseReference",
        "sourceLockCanonicalSha256",
        "directorySha256",
        "directoryCanonicalSha256",
        "expectedVerifiedBodyCount",
    }
    if set(document) != required_fields:
        raise RolloutError(f"{label} must use the exact publication contract")
    if (
        document.get("schemaVersion")
        != "auditback-jurisdiction-publication-approval-1.0.0"
    ):
        raise RolloutError(f"{label}.schemaVersion is unsupported")
    expected_values = {
        "jurisdiction": code,
        "candidateOnly": False,
        "decision": "approved",
        "reviewer": reviewer,
        "approvedAt": approved_at,
        "releaseReference": release_reference,
        "sourceLockCanonicalSha256": source_lock.canonical_sha256,
        "directorySha256": directory.raw_sha256,
        "directoryCanonicalSha256": directory.canonical_sha256,
        "expectedVerifiedBodyCount": expected_count,
    }
    for field, expected in expected_values.items():
        if document.get(field) != expected:
            raise RolloutError(
                f"{label}.{field} differs from the approved rollout evidence"
            )


def _validate_stage_sequence(
    manifest: dict[str, Any],
    *,
    label: str,
) -> dict[str, str]:
    raw_stages = manifest.get("stages")
    if not isinstance(raw_stages, list):
        raise RolloutError(f"{label}.stages must be an array")
    stage_ids: list[str] = []
    status_by_id: dict[str, str] = {}
    incomplete_seen = False
    in_progress_count = 0
    for index, raw in enumerate(raw_stages):
        stage_label = f"{label}.stages[{index}]"
        if not isinstance(raw, dict):
            raise RolloutError(f"{stage_label} must be an object")
        stage_id = _require_string(raw.get("id"), label=f"{stage_label}.id")
        status = _require_string(raw.get("status"), label=f"{stage_label}.status")
        if status not in STAGE_STATUSES:
            raise RolloutError(f"{stage_label}.status is unsupported: {status!r}")
        if stage_id in status_by_id:
            raise RolloutError(f"{label} has duplicate stage {stage_id!r}")
        notes = raw.get("notes")
        if notes is not None and (not isinstance(notes, str) or not notes.strip()):
            raise RolloutError(f"{stage_label}.notes must be non-empty when set")
        if status in {"blocked", "in-progress"} and not notes:
            raise RolloutError(
                f"{stage_label}.notes is required when {status}"
            )
        if status == "in-progress":
            in_progress_count += 1
        is_done = status == "complete"
        if incomplete_seen and is_done:
            raise RolloutError(
                f"{label}: completed stage {stage_id!r} follows unfinished work"
            )
        if incomplete_seen and status != "not-started":
            raise RolloutError(
                f"{label}: only the first unfinished stage may be active or blocked"
            )
        if not is_done and not incomplete_seen:
            incomplete_seen = True
        stage_ids.append(stage_id)
        status_by_id[stage_id] = status
    if tuple(stage_ids) != STAGE_IDS:
        raise RolloutError(
            f"{label}.stages must use the canonical ordered stage list"
        )
    if in_progress_count > 1:
        raise RolloutError(f"{label} cannot have more than one in-progress stage")
    return status_by_id


def validate_rollout_contract(
    *,
    catalog: dict[str, Any],
    coverage_plan: dict[str, Any],
    manifests: Mapping[str, dict[str, Any]],
) -> None:
    """Validate all 13 tracked onboarding packets and their release gates."""

    _validate_manifest_schemas(manifests)
    catalog_by_id, active_source_ids = _catalog_by_id(catalog)
    coverage_by_code = _coverage_by_code(coverage_plan)
    sgc_index = _validate_sgc_geography_index(
        catalog_by_id=catalog_by_id,
        active_source_ids=active_source_ids,
        coverage_plan=coverage_plan,
    )
    manifest_codes = set(manifests)
    if manifest_codes != PROVINCE_TERRITORY_ISO_CODES:
        missing = sorted(PROVINCE_TERRITORY_ISO_CODES - manifest_codes)
        extra = sorted(manifest_codes - PROVINCE_TERRITORY_ISO_CODES)
        raise RolloutError(
            "rollout packets must contain the exact 13 province/territory codes "
            f"(missing={missing}, extra={extra})"
        )
    if set(coverage_by_code) != PROVINCE_TERRITORY_ISO_CODES:
        raise RolloutError("coverage plan must contain the exact 13 jurisdictions")

    required_layers = coverage_plan.get("requiredLayers")
    if not isinstance(required_layers, list) or MUNICIPAL_LAYER not in required_layers:
        raise RolloutError(
            f"coverage plan must require {MUNICIPAL_LAYER!r}"
        )

    for code in sorted(manifests):
        manifest = manifests[code]
        label = f"{code} rollout"
        if manifest.get("schemaVersion") != ROLLOUT_SCHEMA_VERSION:
            raise RolloutError(
                f"{label}.schemaVersion must be {ROLLOUT_SCHEMA_VERSION!r}"
            )
        jurisdiction = manifest.get("jurisdiction")
        if not isinstance(jurisdiction, dict):
            raise RolloutError(f"{label}.jurisdiction must be an object")
        if jurisdiction.get("code") != code:
            raise RolloutError(f"{label}.jurisdiction.code must match its directory")
        name = _require_string(jurisdiction.get("name"), label=f"{label}.name")
        if coverage_by_code[code].get("name") != name:
            raise RolloutError(f"{label}.name differs from the coverage plan")
        sgc_code = _require_string(
            jurisdiction.get("sgcCode"),
            label=f"{label}.jurisdiction.sgcCode",
        )
        if not sgc_code.isdigit() or len(sgc_code) != 2:
            raise RolloutError(f"{label}.jurisdiction.sgcCode must be two digits")
        if PROVINCE_TERRITORY_ISO_BY_SGC.get(sgc_code) != code:
            raise RolloutError(
                f"{label}.jurisdiction.sgcCode {sgc_code!r} does not identify {code}"
            )
        if jurisdiction.get("isoSubdivision") != f"CA-{code}":
            raise RolloutError(
                f"{label}.jurisdiction.isoSubdivision must be CA-{code}"
            )
        if manifest.get("coverageLayer") != MUNICIPAL_LAYER:
            raise RolloutError(f"{label}.coverageLayer must be {MUNICIPAL_LAYER!r}")

        coverage_layers = coverage_by_code[code].get("layers")
        if not isinstance(coverage_layers, dict):
            raise RolloutError(f"{code} coverage layers must be an object")
        layer = coverage_layers.get(MUNICIPAL_LAYER)
        if not isinstance(layer, dict):
            raise RolloutError(f"{code} coverage plan is missing {MUNICIPAL_LAYER}")
        rollout_status = manifest.get("status")
        if rollout_status not in ROLLOUT_STATUSES:
            raise RolloutError(f"{label}.status is unsupported")
        if rollout_status == "not-applicable" or layer.get("status") == "not-applicable":
            raise RolloutError(
                f"{label}: municipal/regional government coverage cannot be "
                "not-applicable for a Canadian province or territory"
            )
        if rollout_status != layer.get("status"):
            raise RolloutError(
                f"{label}.status must match the coverage-plan layer status"
            )

        primary_source_ids = manifest.get("primarySourceIds")
        if (
            not isinstance(primary_source_ids, list)
            or not primary_source_ids
            or any(not isinstance(item, str) or not item for item in primary_source_ids)
        ):
            raise RolloutError(f"{label}.primarySourceIds must be a non-empty array")
        if len(primary_source_ids) != len(set(primary_source_ids)):
            raise RolloutError(f"{label}.primarySourceIds contains duplicates")
        primary_sources: list[dict[str, Any]] = []
        for source_id in primary_source_ids:
            source = catalog_by_id.get(source_id)
            if source is None:
                raise RolloutError(
                    f"{label} references unknown source {source_id!r}"
                )
            if source.get("jurisdiction") != code:
                raise RolloutError(
                    f"{label} source {source_id!r} belongs to another jurisdiction"
                )
            if source.get("coverageLayer") != MUNICIPAL_LAYER:
                raise RolloutError(
                    f"{label} source {source_id!r} belongs to another layer"
                )
            primary_sources.append(source)

        source_roles = manifest.get("sourceRoles")
        if not isinstance(source_roles, dict):
            raise RolloutError(f"{label}.sourceRoles must be an object")
        if set(source_roles) != set(primary_source_ids):
            raise RolloutError(
                f"{label}.sourceRoles must name exactly the primarySourceIds"
            )
        identity_source_present = False
        for source_id in primary_source_ids:
            roles = source_roles[source_id]
            if (
                not isinstance(roles, list)
                or not roles
                or any(role not in SOURCE_ROLES for role in roles)
                or len(roles) != len(set(roles))
            ):
                raise RolloutError(
                    f"{label}.sourceRoles.{source_id} must contain unique "
                    "supported source roles"
                )
            identity_source_present = identity_source_present or bool(
                set(roles) & IDENTITY_SOURCE_ROLES
            )
        body_types = manifest.get("canonicalBodyTypes")
        if (
            not isinstance(body_types, list)
            or not body_types
            or not set(body_types).issubset(CANONICAL_MUNICIPAL_BODY_TYPES)
            or len(body_types) != len(set(body_types))
            or any(item not in BODY_TYPES for item in body_types)
        ):
            raise RolloutError(
                f"{label}.canonicalBodyTypes must contain unique, applicable "
                "municipal/regional government types"
            )

        status_by_stage = _validate_stage_sequence(manifest, label=label)
        source_stage_status = status_by_stage["official-source-identified"]
        partial_evidence_complete = all(
            status_by_stage[stage_id] == "complete"
            for stage_id in PARTIAL_EVIDENCE_STAGES
        )
        if source_stage_status != "complete":
            allowed_statuses = (
                {"not-started"}
                if source_stage_status == "not-started"
                else {"source-discovery"}
            )
            if rollout_status not in allowed_statuses:
                raise RolloutError(
                    f"{label}: overall status must reflect unfinished source "
                    "discovery"
                )
        elif not partial_evidence_complete and rollout_status != "adapter-needed":
            raise RolloutError(
                f"{label}: status remains adapter-needed until source bytes, "
                "adapter output, crosswalks, and exceptions are verified"
            )
        elif (
            partial_evidence_complete
            and status_by_stage["publication-approved"] != "complete"
            and rollout_status != "partial"
        ):
            raise RolloutError(
                f"{label}: verified positive directory evidence without publication "
                "approval must be reported as partial"
            )
        if (
            status_by_stage["official-source-identified"] == "complete"
            and not identity_source_present
        ):
            raise RolloutError(
                f"{label}: a complete source bundle requires a governing-body "
                "roster or legal authority"
            )
        unidentified_sources = [
            source_id
            for source_id, source in zip(primary_source_ids, primary_sources)
            if source.get("status") == "source-discovery"
        ]
        if (
            status_by_stage["official-source-identified"] == "complete"
            and unidentified_sources
        ):
            raise RolloutError(
                f"{label}: official-source-identified cannot be complete while "
                f"sources remain in discovery: {', '.join(unidentified_sources)}"
            )
        all_reuse_approved = all(
            source.get("reuseReviewRequired") is False
            and source.get("licenseStatus") in APPROVED_LICENCE_STATUSES
            for source in primary_sources
        )
        reuse_status = status_by_stage["reuse-approved"]
        if reuse_status == "complete" and not all_reuse_approved:
            raise RolloutError(
                f"{label}: reuse-approved cannot be complete until every primary "
                "source has an approved licence"
            )
        if (
            status_by_stage["official-source-identified"] == "complete"
            and all_reuse_approved
            and reuse_status != "complete"
        ):
            raise RolloutError(
                f"{label}: reuse-approved must reflect the catalogued approved licence"
            )

        layer_source_ids = layer.get("sourceIds")
        if not isinstance(layer_source_ids, list) or any(
            not isinstance(source_id, str) for source_id in layer_source_ids
        ):
            raise RolloutError(f"{code} coverage sourceIds must be a string array")
        if rollout_status in {
            "not-started",
            "source-discovery",
            "adapter-needed",
        } and layer_source_ids:
            raise RolloutError(
                f"{label}: non-evidence coverage status must not name locked sourceIds"
            )
        if rollout_status in {"partial", "complete"}:
            if set(layer_source_ids) != set(primary_source_ids):
                raise RolloutError(
                    f"{label}: evidence coverage sourceIds must exactly match the "
                    "reviewed source bundle"
                )
            if any(source_id not in active_source_ids for source_id in layer_source_ids):
                raise RolloutError(
                    f"{label}: coverage sourceIds must be active and hash-pinned"
                )
            if not partial_evidence_complete:
                raise RolloutError(
                    f"{label}: {rollout_status} coverage requires completed transport, "
                    "adapter, crosswalk, and exception evidence"
                )

        source_bundle_digest = canonical_sha256(
            {
                source_id: catalog_by_id[source_id]
                for source_id in sorted(primary_source_ids)
            }
        )
        coverage_layer_digest = canonical_sha256(
            {
                "jurisdiction": code,
                "coverageLayer": MUNICIPAL_LAYER,
                "coverage": layer,
            }
        )
        transport = manifest.get("transport")
        if not isinstance(transport, dict):
            raise RolloutError(f"{label}.transport must be an object")
        source_lock_path = _require_optional_repo_path(
            transport.get("sourceLockPath"),
            label=f"{label}.transport.sourceLockPath",
        )
        validated_source_lock: ValidatedSourceLock | None = None
        if status_by_stage["transport-pinned"] == "complete":
            if any(source_id not in active_source_ids for source_id in primary_source_ids):
                raise RolloutError(
                    f"{label}: transport-pinned requires active hash-pinned sources"
                )
            if source_lock_path is None:
                raise RolloutError(
                    f"{label}: transport-pinned requires sourceLockPath"
                )
            validated_source_lock = _validate_source_lock(
                path=source_lock_path,
                label=f"{label}.transport.sourceLockPath",
                source_ids=primary_source_ids,
                catalog_by_id=catalog_by_id,
                source_bundle_canonical_sha256=source_bundle_digest,
                coverage_layer_canonical_sha256=coverage_layer_digest,
            )
        elif source_lock_path is not None:
            raise RolloutError(
                f"{label}: sourceLockPath remains null until transport-pinned"
            )

        adapter = manifest.get("adapter")
        if not isinstance(adapter, dict):
            raise RolloutError(f"{label}.adapter must be an object")
        adapter_id = adapter.get("adapterId")
        adapter_version = adapter.get("adapterVersion")
        module_path = _require_optional_repo_path(
            adapter.get("modulePath"),
            label=f"{label}.adapter.modulePath",
        )
        test_path = _require_optional_repo_path(
            adapter.get("testPath"),
            label=f"{label}.adapter.testPath",
        )
        fixture_paths = adapter.get("fixturePaths")
        if not isinstance(fixture_paths, list):
            raise RolloutError(f"{label}.adapter.fixturePaths must be an array")
        for index, path in enumerate(fixture_paths):
            if not isinstance(path, str):
                raise RolloutError(
                    f"{label}.adapter.fixturePaths[{index}] must be a string"
                )
            _require_optional_repo_path(
                path,
                label=f"{label}.adapter.fixturePaths[{index}]",
            )
        if status_by_stage["adapter-tested"] == "complete":
            for field_name, value in (
                ("adapterId", adapter_id),
                ("adapterVersion", adapter_version),
                ("modulePath", module_path),
                ("testPath", test_path),
            ):
                _require_string(value, label=f"{label}.adapter.{field_name}")
            if not fixture_paths:
                raise RolloutError(
                    f"{label}: adapter-tested requires at least one fixture"
                )
            if not module_path.startswith(
                "national/providers/"
            ) or not module_path.endswith(".py"):
                raise RolloutError(
                    f"{label}.adapter.modulePath must identify Python code under "
                    "national/providers/"
                )
            if not test_path.startswith("tests/test_national_") or not test_path.endswith(
                ".py"
            ):
                raise RolloutError(
                    f"{label}.adapter.testPath must identify a national test module"
                )
            _validate_adapter_code_contract(
                module_path=module_path,
                test_path=test_path,
                adapter_id=adapter_id,
                adapter_version=adapter_version,
                label=f"{label}.adapter",
            )
            for index, path in enumerate(fixture_paths):
                allowed_fixture_prefixes = (
                    "tests/fixtures/",
                    f"national/jurisdictions/{code}/fixtures/",
                )
                if not path.startswith(allowed_fixture_prefixes):
                    raise RolloutError(
                        f"{label}.adapter.fixturePaths[{index}] must be under an "
                        "approved fixture directory"
                    )
                _existing_repo_file(
                    path,
                    label=f"{label}.adapter.fixturePaths[{index}]",
                )
            for source in primary_sources:
                if (
                    source.get("adapterId") != adapter_id
                    or source.get("adapterVersion") != adapter_version
                ):
                    raise RolloutError(
                        f"{label}: adapter identity must match every active source "
                        "in the bundle"
                    )
        elif any(
            value is not None
            for value in (adapter_id, adapter_version, module_path, test_path)
        ):
            raise RolloutError(
                f"{label}: adapter identity fields remain null until adapter-tested"
            )

        output = manifest.get("output")
        if not isinstance(output, dict):
            raise RolloutError(f"{label}.output must be an object")
        directory_path = _require_optional_repo_path(
            output.get("directoryPath"),
            label=f"{label}.output.directoryPath",
        )
        directory_sha256 = output.get("directorySha256")
        directory_canonical_sha256 = output.get("directoryCanonicalSha256")
        validated_directory: ValidatedDirectory | None = None
        if status_by_stage["adapter-tested"] == "complete":
            if validated_source_lock is None:
                raise RolloutError(
                    f"{label}: adapter output requires a verified source lock"
                )
            for field_name, value in (
                ("directoryPath", directory_path),
                ("directorySha256", directory_sha256),
                ("directoryCanonicalSha256", directory_canonical_sha256),
            ):
                _require_string(value, label=f"{label}.output.{field_name}")
            validated_directory = _validate_directory_output(
                path=directory_path,
                raw_sha256=directory_sha256,
                canonical_digest=directory_canonical_sha256,
                label=f"{label}.output.directoryPath",
                code=code,
                sgc_code=sgc_code,
                canonical_body_types=body_types,
                source_ids=primary_source_ids,
                source_roles=source_roles,
                source_lock=validated_source_lock,
                sgc_index=sgc_index,
                adapter_id=adapter_id,
                adapter_version=adapter_version,
            )
            _execute_provider_contract(
                module_path=module_path,
                code=code,
                source_lock=validated_source_lock,
                directory=validated_directory,
                label=f"{label}.adapter",
            )
        elif any(
            value is not None
            for value in (
                directory_path,
                directory_sha256,
                directory_canonical_sha256,
            )
        ):
            raise RolloutError(
                f"{label}: output evidence remains null until adapter-tested"
            )

        reconciliation = manifest.get("reconciliation")
        if not isinstance(reconciliation, dict):
            raise RolloutError(f"{label}.reconciliation must be an object")
        expected_count = reconciliation.get("expectedVerifiedBodyCount")
        if expected_count is not None and (
            isinstance(expected_count, bool)
            or not isinstance(expected_count, int)
            or expected_count <= 0
        ):
            raise RolloutError(
                f"{label}.expectedVerifiedBodyCount must be null or positive"
            )
        review_paths: dict[str, str | None] = {}
        for field in (
            "classificationDecisionPath",
            "crosswalkReviewPath",
            "exceptionsPath",
            "reconciliationPath",
        ):
            review_paths[field] = _require_optional_repo_path(
                reconciliation.get(field),
                label=f"{label}.reconciliation.{field}",
            )
        crosswalk_rows: list[dict[str, str]] | None = None
        reviewed_unmatched_count: int | None = None
        if status_by_stage["exact-crosswalk-reviewed"] == "complete":
            path = review_paths["crosswalkReviewPath"]
            if path is None:
                raise RolloutError(
                    f"{label}: exact-crosswalk-reviewed requires crosswalkReviewPath"
                )
            crosswalk_rows = _validate_crosswalk_review(
                path=path,
                label=f"{label}.reconciliation.crosswalkReviewPath",
                source_ids=primary_source_ids,
                catalog_by_id=catalog_by_id,
            )
            if validated_directory is None or validated_source_lock is None:
                raise RolloutError(
                    f"{label}: crosswalk review requires verified directory output"
                )
            reviewed_unmatched_count = _crosslink_crosswalk_review(
                rows=crosswalk_rows,
                directory=validated_directory,
                source_lock=validated_source_lock,
                source_roles=source_roles,
                label=f"{label}.reconciliation.crosswalkReviewPath",
                sgc_code=sgc_code,
            )
        classification_rows: list[dict[str, str]] | None = None
        if status_by_stage["exceptions-reviewed"] == "complete":
            for field in ("classificationDecisionPath", "exceptionsPath"):
                path = review_paths[field]
                if path is None:
                    raise RolloutError(
                        f"{label}: exceptions-reviewed requires {field}"
                    )
            classification_rows = _validate_classification_review(
                path=review_paths["classificationDecisionPath"],
                label=f"{label}.reconciliation.classificationDecisionPath",
                source_ids=primary_source_ids,
                canonical_body_types=body_types,
            )
            if validated_directory is None or validated_source_lock is None:
                raise RolloutError(
                    f"{label}: classification review requires verified source and "
                    "directory output"
                )
            _validate_roster_inventory(
                rows=classification_rows,
                source_lock=validated_source_lock,
                source_roles=source_roles,
                label=f"{label}.reconciliation.classificationDecisionPath",
            )
            _crosslink_classification_review(
                rows=classification_rows,
                directory=validated_directory,
                label=f"{label}.reconciliation.classificationDecisionPath",
            )
            _validate_exceptions_review(
                path=review_paths["exceptionsPath"],
                label=f"{label}.reconciliation.exceptionsPath",
                code=code,
                source_ids=primary_source_ids,
            )
        if status_by_stage["count-reconciled"] == "complete":
            if expected_count is None:
                raise RolloutError(
                    f"{label}: count-reconciled requires expectedVerifiedBodyCount"
                )
            if validated_directory is None:
                raise RolloutError(
                    f"{label}: count reconciliation requires verified directory output"
                )
            for field in (
                "classificationDecisionPath",
                "crosswalkReviewPath",
                "exceptionsPath",
                "reconciliationPath",
            ):
                path = review_paths[field]
                if path is None:
                    raise RolloutError(
                        f"{label}: count-reconciled requires {field}"
                    )
            _validate_reconciliation(
                path=review_paths["reconciliationPath"],
                label=f"{label}.reconciliation.reconciliationPath",
                code=code,
                source_ids=primary_source_ids,
                canonical_body_types=body_types,
                expected_count=expected_count,
                reviewed_unmatched_count=(
                    reviewed_unmatched_count
                    if reviewed_unmatched_count is not None
                    else 0
                ),
                directory=validated_directory,
                source_roles=source_roles,
            )

        if rollout_status in {"partial", "complete"}:
            if validated_directory is None:
                raise RolloutError(
                    f"{label}: evidence coverage requires verified directory output"
                )
            active_records = sum(
                1
                for record in validated_directory.records
                if record["body"]["status"] == "active"
            )
            if active_records < 1:
                raise RolloutError(
                    f"{label}: evidence coverage requires at least one active "
                    "verified governing body"
                )

        publication_ready = status_by_stage["publication-approved"] == "complete"
        publication_approval = manifest.get("publicationApproval")
        if not isinstance(publication_approval, dict):
            raise RolloutError(f"{label}.publicationApproval must be an object")
        approval_values = {
            field: publication_approval.get(field)
            for field in ("reviewer", "approvedAt", "releaseReference")
        }
        approval_artifact_path = _require_optional_repo_path(
            publication_approval.get("artifactPath"),
            label=f"{label}.publicationApproval.artifactPath",
        )
        approval_artifact_sha256 = publication_approval.get("artifactSha256")
        if publication_ready:
            if rollout_status != "complete" or layer.get("status") != "complete":
                raise RolloutError(
                    f"{label}: publication approval requires complete coverage"
                )
            if any(status_by_stage[stage_id] != "complete" for stage_id in STAGE_IDS):
                raise RolloutError(
                    f"{label}: publication approval requires every stage complete"
                )
            if any(source_id not in active_source_ids for source_id in primary_source_ids):
                raise RolloutError(
                    f"{label}: publication approval requires active hash-pinned sources"
                )
            if expected_count is None:
                raise RolloutError(
                    f"{label}: publication approval requires a positive body count"
                )
            if validated_source_lock is None or validated_directory is None:
                raise RolloutError(
                    f"{label}: publication approval requires verified source and "
                    "directory evidence"
                )
            for field, value in approval_values.items():
                _require_string(
                    value,
                    label=f"{label}.publicationApproval.{field}",
                )
            if DATE_RE.fullmatch(approval_values["approvedAt"]) is None:
                raise RolloutError(
                    f"{label}.publicationApproval.approvedAt must be YYYY-MM-DD"
                )
            _validate_snapshot_date(
                approval_values["approvedAt"],
                label=f"{label}.publicationApproval.approvedAt",
                date_only=True,
            )
            if approval_artifact_path is None:
                raise RolloutError(
                    f"{label}: publication approval requires artifactPath"
                )
            _require_string(
                approval_artifact_sha256,
                label=f"{label}.publicationApproval.artifactSha256",
            )
            _validate_publication_approval(
                path=approval_artifact_path,
                raw_sha256=approval_artifact_sha256,
                label=f"{label}.publicationApproval.artifactPath",
                code=code,
                reviewer=approval_values["reviewer"],
                approved_at=approval_values["approvedAt"],
                release_reference=approval_values["releaseReference"],
                expected_count=expected_count,
                source_lock=validated_source_lock,
                directory=validated_directory,
            )
        elif rollout_status == "complete":
            raise RolloutError(
                f"{label}: complete coverage requires publication-approved=complete"
            )
        elif any(
            value is not None
            for value in (
                *approval_values.values(),
                approval_artifact_path,
                approval_artifact_sha256,
            )
        ):
            raise RolloutError(
                f"{label}: publication approval metadata remains null until approval"
            )

        scope_notes = manifest.get("scopeNotes")
        if (
            not isinstance(scope_notes, list)
            or not scope_notes
            or any(not isinstance(item, str) or not item.strip() for item in scope_notes)
        ):
            raise RolloutError(f"{label}.scopeNotes must be a non-empty string array")


def build_rollout_report(
    *,
    catalog: dict[str, Any],
    coverage_plan: dict[str, Any],
    manifests: Mapping[str, dict[str, Any]],
) -> dict[str, Any]:
    validate_rollout_contract(
        catalog=catalog,
        coverage_plan=coverage_plan,
        manifests=manifests,
    )
    catalog_by_id, active_source_ids = _catalog_by_id(catalog)
    coverage_by_code = _coverage_by_code(coverage_plan)
    rows: list[dict[str, Any]] = []
    for code in sorted(manifests):
        manifest = manifests[code]
        stages = manifest["stages"]
        completed = sum(1 for stage in stages if stage["status"] == "complete")
        stage_status = {stage["id"]: stage["status"] for stage in stages}
        primary_ids = list(manifest["primarySourceIds"])
        blockers = [
            stage["id"]
            for stage in stages
            if stage["status"] != "complete"
        ]
        rows.append(
            {
                "code": code,
                "name": manifest["jurisdiction"]["name"],
                "coverageStatus": coverage_by_code[code]["layers"][MUNICIPAL_LAYER][
                    "status"
                ],
                "rolloutStatus": manifest["status"],
                "completedStageCount": completed,
                "stageCount": len(STAGE_IDS),
                "primarySourceIds": primary_ids,
                "sourceApproval": (
                    "verified-source-lock"
                    if stage_status["transport-pinned"] == "complete"
                    else "catalog-approved-unlocked"
                    if all(source_id in active_source_ids for source_id in primary_ids)
                    else "planned"
                ),
                "reuseReviewRequired": any(
                    catalog_by_id[source_id].get("reuseReviewRequired") is not False
                    for source_id in primary_ids
                ),
                "publicationReady": manifest["stages"][-1]["status"] == "complete",
                "blockers": blockers,
            }
        )

    report: dict[str, Any] = {
        "schemaVersion": ROLLOUT_REPORT_SCHEMA_VERSION,
        "country": "CA",
        "coverageLayer": MUNICIPAL_LAYER,
        "method": {
            "runtimeNetworkRequired": False,
            "runtimeAiRequired": False,
            "publicationFromThisReportAllowed": False,
        },
        "inputDigests": {
            "sourceCatalogCanonicalSha256": canonical_sha256(catalog),
            "coveragePlanCanonicalSha256": canonical_sha256(coverage_plan),
            "jurisdictionRolloutsCanonicalSha256": canonical_sha256(
                {code: manifests[code] for code in sorted(manifests)}
            ),
        },
        "summary": {
            "jurisdictionsTracked": len(rows),
            "jurisdictionsPublicationReady": sum(
                1 for row in rows if row["publicationReady"]
            ),
            "jurisdictionsWithPlannedPrimarySources": sum(
                1 for row in rows if row["sourceApproval"] == "planned"
            ),
            "jurisdictionsWithCatalogApprovedUnlockedSources": sum(
                1
                for row in rows
                if row["sourceApproval"] == "catalog-approved-unlocked"
            ),
            "jurisdictionsWithVerifiedSourceLocks": sum(
                1 for row in rows if row["sourceApproval"] == "verified-source-lock"
            ),
            "jurisdictionsRequiringReuseReview": sum(
                1 for row in rows if row["reuseReviewRequired"]
            ),
        },
        "jurisdictions": rows,
    }
    report["reportCanonicalSha256"] = canonical_sha256(report)
    return report


def render_rollout_table(report: dict[str, Any]) -> str:
    lines = [
        "CODE  JURISDICTION                COVERAGE          STAGES  SOURCE   NEXT GATE",
        "----  --------------------------  ----------------  ------  -------  --------------------------",
    ]
    for row in report["jurisdictions"]:
        next_gate = row["blockers"][0] if row["blockers"] else "publication-ready"
        source = {
            "verified-source-lock": "locked",
            "catalog-approved-unlocked": "catalog",
            "planned": "planned",
        }[row["sourceApproval"]]
        lines.append(
            f"{row['code']:<4}  "
            f"{row['name'][:26]:<26}  "
            f"{row['coverageStatus']:<16}  "
            f"{row['completedStageCount']}/{row['stageCount']:<3}  "
            f"{source:<7}  "
            f"{next_gate}"
        )
    summary = report["summary"]
    lines.extend(
        [
            "",
            (
                "Tracked: "
                f"{summary['jurisdictionsTracked']} jurisdictions; "
                f"publication-ready: {summary['jurisdictionsPublicationReady']}; "
                "runtime network: 0; AI calls: 0; AI tokens: 0."
            ),
        ]
    )
    return "\n".join(lines)


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def scaffold_jurisdiction_workspace(
    *,
    code: str,
    output: Path,
    catalog: dict[str, Any],
    coverage_plan: dict[str, Any],
    manifests: Mapping[str, dict[str, Any]],
) -> tuple[Path, ...]:
    """Create a candidate-only offline workspace without overwriting anything."""

    validate_rollout_contract(
        catalog=catalog,
        coverage_plan=coverage_plan,
        manifests=manifests,
    )
    code = code.upper()
    manifest = manifests.get(code)
    if manifest is None:
        raise RolloutError(f"unsupported Canadian province/territory code {code!r}")
    if output.exists():
        raise RolloutError(f"refusing to overwrite existing scaffold path: {output}")
    output.mkdir(parents=True)
    catalog_by_id, active_source_ids = _catalog_by_id(catalog)
    source_candidates = {
        "schemaVersion": "auditback-source-candidates-1.0.0",
        "jurisdiction": code,
        "candidateOnly": True,
        "sources": [
            {
                "sourceId": source_id,
                "catalogStatus": (
                    "catalog-approved-unlocked"
                    if source_id in active_source_ids
                    else "planned"
                ),
                "landingPageUrl": catalog_by_id[source_id]["landingPageUrl"],
                "transport": catalog_by_id[source_id].get("transport"),
                "licenseStatus": catalog_by_id[source_id]["licenseStatus"],
                "reuseReviewRequired": catalog_by_id[source_id][
                    "reuseReviewRequired"
                ],
                "roles": manifest["sourceRoles"][source_id],
                "requestUrl": catalog_by_id[source_id].get("requestUrl"),
                "mediaType": catalog_by_id[source_id].get("mediaType"),
                "adapterId": catalog_by_id[source_id].get("adapterId"),
                "adapterVersion": catalog_by_id[source_id].get("adapterVersion"),
                "approvedSha256": catalog_by_id[source_id].get("approvedSha256"),
            }
            for source_id in manifest["primarySourceIds"]
        ],
    }
    canonical_directory = {
        "schemaVersion": "auditback-verified-jurisdiction-directory-1.0.0",
        "jurisdiction": code,
        "candidateOnly": True,
        "adapter": {"id": None, "version": None},
        "sourceLockCanonicalSha256": None,
        "records": [],
    }
    exceptions = {
        "schemaVersion": "auditback-jurisdiction-exceptions-1.0.0",
        "jurisdiction": code,
        "candidateOnly": True,
        "reviewer": None,
        "reviewedAt": None,
        "exceptions": [],
    }
    reconciliation = {
        "schemaVersion": "auditback-jurisdiction-reconciliation-1.0.0",
        "jurisdiction": code,
        "candidateOnly": True,
        "asOfDate": None,
        "officialControlTotals": [],
        "emittedCounts": [],
        "unmatchedCount": None,
        "reconciled": False,
        "reviewer": None,
    }
    publication_approval = {
        "schemaVersion": "auditback-jurisdiction-publication-approval-1.0.0",
        "jurisdiction": code,
        "candidateOnly": True,
        "decision": None,
        "reviewer": None,
        "approvedAt": None,
        "releaseReference": None,
        "sourceLockCanonicalSha256": None,
        "directorySha256": None,
        "directoryCanonicalSha256": None,
        "expectedVerifiedBodyCount": None,
    }
    readme = (
        f"# {manifest['jurisdiction']['name']} onboarding workspace\n\n"
        "This directory is candidate-only. Nothing here can be published until "
        "the tracked rollout packet, source catalog, coverage plan, exact "
        "crosswalk review, reconciliation count, and independent approvals all "
        "pass.\n\n"
        "1. Confirm the official source and its reuse terms.\n"
        "2. Record the stable HTTPS request URL and downloaded SHA-256.\n"
        "3. Normalize official identifiers into `canonical-directory.json`.\n"
        "4. Record legal-type, tier, relationship, lifecycle, and layer-routing "
        "decisions in `classification-decisions.csv`.\n"
        "5. Complete `crosswalk-review.csv` using exact official codes only.\n"
        "6. Record dissolutions, shared services, and non-municipal areas in "
        "`exceptions.json`, then reconcile dated type totals in "
        "`reconciliation.json`.\n"
        "7. Add minimal fixtures and adapter tests before changing any rollout "
        "stage to complete.\n"
        "8. Leave `publication-approval.json` candidate-only until an independent "
        "human approval is bound to the same source lock and directory hashes.\n\n"
        "Do not use names or AI output to auto-match governments to geographies.\n"
    )
    paths = (
        output / "README.md",
        output / "source-candidates.json",
        output / "canonical-directory.json",
        output / "classification-decisions.csv",
        output / "crosswalk-review.csv",
        output / "exceptions.json",
        output / "reconciliation.json",
        output / "publication-approval.json",
    )
    paths[0].write_text(readme, encoding="utf-8", newline="\n")
    _write_json(paths[1], source_candidates)
    _write_json(paths[2], canonical_directory)
    with paths[3].open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(
            [
                "sourceId",
                "sourceRecordKey",
                "officialLegalType",
                "canonicalBodyType",
                "tier",
                "parentBodyId",
                "layerDisposition",
                "effectiveFrom",
                "effectiveTo",
                "reviewer",
                "status",
                "notes",
            ]
        )
    with paths[4].open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(
            [
                "bodyId",
                "officialExternalId",
                "sourceId",
                "snapshotSha256",
                "sourceRecordKey",
                "sgcGeographyId",
                "matchMethod",
                "reviewer",
                "status",
                "notes",
            ]
        )
    _write_json(paths[5], exceptions)
    _write_json(paths[6], reconciliation)
    _write_json(paths[7], publication_approval)
    return paths
