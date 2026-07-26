"""Offline hard gate for the Waterloo-plus-neighbours geography registry.

The checked-in registry is a normalized snapshot of Ontario's official lower,
single and upper-tier municipal boundary layers. Validation never calls the
network and never writes a report, so the same command is safe in CI and on a
reviewer's machine:

    python scripts/validate_regional_registry.py
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REGISTRY = ROOT / "geography" / "ontario-waterloo-test-ring.json"
DEFAULT_LOCK = ROOT / "geography" / "ontario-waterloo-test-ring.sources.lock.json"

SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*-on$")
CODE_RE = re.compile(r"^\d{4}$")
ADMIN_CODE_RE = re.compile(r"^\d{5}$")
UNSUPPORTED_IDENTITY_STATUS = "unsupported"

OFFICIAL_WATERLOO_CODES = {
    "cambridge-on": "3006",
    "kitchener-on": "3012",
    "north-dumfries-on": "3001",
    "waterloo-on": "3016",
    "wellesley-on": "3024",
    "wilmot-on": "3018",
    "woolwich-on": "3029",
}

EXPECTED_FIRST_RING = {
    "blandford-blenheim-on",
    "brant-county-on",
    "centre-wellington-on",
    "east-zorra-tavistock-on",
    "guelph-eramosa-on",
    "hamilton-on",
    "mapleton-on",
    "perth-east-on",
    "puslinch-on",
}

OFFICIAL_SOURCE_METADATA = {
    "ontario-municlow-layer-14": {
        "publisher": "Government of Ontario",
        "datasetTitle": "Municipal Boundary - Lower and Single Tier",
        "datasetUrl": "https://data.ontario.ca/en/dataset/municipal-boundaries",
        "serviceUrl": (
            "https://ws.lioservices.lrc.gov.on.ca/arcgis2/rest/services/"
            "LIO_OPEN_DATA/LIO_Open03/MapServer/14"
        ),
        "layer": 14,
        "layerName": "Municipal Bnd Lower And Single",
        "serviceVersion": "10.91",
        "effectiveDatetime": "2024-02-15T10:26:33Z",
        "licenseUrl": "https://www.ontario.ca/page/open-government-licence-ontario",
        "identityFields": [
            "ASSESSMENT_CODE",
            "MUNID",
            "MAH_CODE",
            "MUNICIPAL_NAME",
            "MUNICIPAL_NAME_FR",
            "MUNICIPAL_NAME_SHORTFORM",
            "MUNICIPAL_NAME_SHORTFORM_FR",
            "MUNICIPAL_TYPE",
            "MUNICIPAL_TYPE_FR",
            "UPPER_TIER_MUNICIPALITY",
            "UPPER_TIER_MUNICIPALITY_FR",
            "EFFECTIVE_DATETIME",
        ],
        "queryFormat": "ArcGIS REST JSON",
    },
    "ontario-municupper-layer-13": {
        "publisher": "Government of Ontario",
        "datasetTitle": "Municipal Boundary - Upper Tier and District",
        "datasetUrl": "https://data.ontario.ca/en/dataset/municipal-boundaries",
        "serviceUrl": (
            "https://ws.lioservices.lrc.gov.on.ca/arcgis2/rest/services/"
            "LIO_OPEN_DATA/LIO_Open03/MapServer/13"
        ),
        "layer": 13,
        "layerName": "Municipal Bnd Upper And Dist",
        "serviceVersion": "10.91",
        "effectiveDatetime": "2024-02-15T10:28:18Z",
        "licenseUrl": "https://www.ontario.ca/page/open-government-licence-ontario",
        "identityFields": [
            "ASSESSMENT_CODE",
            "MUNID",
            "MAH_CODE",
            "MUNICIPAL_NAME",
            "MUNICIPAL_NAME_FR",
            "MUNICIPAL_NAME_SHORTFORM",
            "MUNICIPAL_NAME_SHORTFORM_FR",
            "MUNICIPAL_TYPE",
            "MUNICIPAL_TYPE_FR",
            "EFFECTIVE_DATETIME",
        ],
        "queryFormat": "ArcGIS REST JSON",
    },
}

REQUIRED_JURISDICTION_FIELDS = {
    "slug",
    "assessmentCode",
    "municipalId",
    "mahCode",
    "nameEn",
    "nameFr",
    "shortNameEn",
    "shortNameFr",
    "tier",
    "parentSlug",
    "role",
}


def _canonical_sha256(document: Any) -> str:
    """Hash JSON semantics, independent of checkout line endings or indentation."""

    payload = json.dumps(
        document,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _top_level_scalar(path: Path, key: str) -> str | None:
    """Read a simple top-level YAML scalar without adding a YAML dependency."""

    pattern = re.compile(rf"^{re.escape(key)}:\s*(.*?)\s*$")
    for line in path.read_text(encoding="utf-8").splitlines():
        match = pattern.match(line)
        if not match:
            continue
        raw = match.group(1).split("  #", 1)[0].strip()
        if raw in {"", "null", "~"}:
            return None
        if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in {'"', "'"}:
            return raw[1:-1]
        return raw
    return None


def _top_level_list(path: Path, key: str) -> list[str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    marker = re.compile(rf"^{re.escape(key)}:\s*(?:#.*)?$")
    item = re.compile(r"^\s{2}-\s+(.+?)\s*$")
    start = next((index for index, line in enumerate(lines) if marker.match(line)), None)
    if start is None:
        return []

    values: list[str] = []
    for line in lines[start + 1 :]:
        if line and not line[0].isspace():
            break
        match = item.match(line)
        if match:
            raw = match.group(1).split("  #", 1)[0].strip()
            if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in {'"', "'"}:
                raw = raw[1:-1]
            values.append(raw)
    return values


def _section_scalar(path: Path, section: str, key: str) -> str | None:
    """Read a scalar one level below a top-level YAML mapping."""

    lines = path.read_text(encoding="utf-8").splitlines()
    marker = re.compile(rf"^{re.escape(section)}:\s*(?:#.*)?$")
    item = re.compile(rf"^\s{{2}}{re.escape(key)}:\s*(.*?)\s*$")
    start = next((index for index, line in enumerate(lines) if marker.match(line)), None)
    if start is None:
        return None
    for line in lines[start + 1 :]:
        if line and not line[0].isspace():
            break
        match = item.match(line)
        if not match:
            continue
        raw = match.group(1).split("  #", 1)[0].strip()
        if raw in {"", "null", "~"}:
            return None
        if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in {'"', "'"}:
            return raw[1:-1]
        return raw
    return None


def _utc_datetime(value: Any, label: str, errors: list[str]) -> datetime | None:
    if not isinstance(value, str) or not value.endswith("Z"):
        errors.append(f"{label} must be an ISO-8601 UTC timestamp ending in 'Z'")
        return None
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        errors.append(f"{label} is not a valid ISO-8601 timestamp")
        return None
    if parsed.tzinfo != timezone.utc:
        errors.append(f"{label} must be UTC")
        return None
    return parsed


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_registry(
    registry: dict[str, Any],
    *,
    root: Path = ROOT,
    check_corpus: bool = True,
) -> list[str]:
    errors: list[str] = []

    required_top = {
        "schemaVersion",
        "registryId",
        "country",
        "subdivision",
        "effectiveDate",
        "sourceLock",
        "anchor",
        "method",
        "jurisdictions",
        "touchesBySlug",
    }
    missing_top = sorted(required_top - registry.keys())
    if missing_top:
        errors.append(f"registry missing fields: {', '.join(missing_top)}")
        return errors

    if registry["schemaVersion"] != "regional-geography-registry-1.0.0":
        errors.append(f"unsupported schemaVersion {registry['schemaVersion']!r}")
    if registry["country"] != "CA" or registry["subdivision"] != "ON":
        errors.append("registry scope must be CA/ON")
    if registry.get("method", {}).get("runtimeNetworkRequired") is not False:
        errors.append("regional validation must remain offline")

    rows = registry["jurisdictions"]
    if not isinstance(rows, list):
        return errors + ["jurisdictions must be an array"]

    by_slug: dict[str, dict[str, Any]] = {}
    by_code: dict[str, str] = {}
    by_municipal_id: dict[str, str] = {}
    by_mah_code: dict[str, str] = {}
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            errors.append(f"jurisdictions[{index}] must be an object")
            continue
        missing = sorted(REQUIRED_JURISDICTION_FIELDS - row.keys())
        if missing:
            errors.append(
                f"jurisdictions[{index}] missing fields: {', '.join(missing)}"
            )
            continue

        slug = row["slug"]
        code = row["assessmentCode"]
        if not isinstance(slug, str) or not SLUG_RE.fullmatch(slug):
            errors.append(f"invalid Ontario slug {slug!r}")
            continue
        if slug in by_slug:
            errors.append(f"duplicate slug {slug!r}")
        by_slug[slug] = row

        if not isinstance(code, str) or not CODE_RE.fullmatch(code):
            errors.append(f"{slug}: assessmentCode must be a four-digit string")
        elif code in by_code:
            errors.append(
                f"duplicate assessmentCode {code!r}: {by_code[code]!r} and {slug!r}"
            )
        else:
            by_code[code] = slug

        for field in ("municipalId", "mahCode"):
            value = row[field]
            if not isinstance(value, str) or not ADMIN_CODE_RE.fullmatch(value):
                errors.append(f"{slug}: {field} must be a five-digit string")
                continue
            index = by_municipal_id if field == "municipalId" else by_mah_code
            if value in index:
                errors.append(
                    f"duplicate {field} {value!r}: {index[value]!r} and {slug!r}"
                )
            else:
                index[value] = slug
        for field in ("nameEn", "nameFr", "shortNameEn", "shortNameFr"):
            if not isinstance(row[field], str) or not row[field].strip():
                errors.append(f"{slug}: {field} must be a non-empty string")

        tier = row["tier"]
        parent = row["parentSlug"]
        if tier not in {"lower-tier", "single-tier", "upper-tier"}:
            errors.append(f"{slug}: invalid tier {tier!r}")
        if tier == "lower-tier" and not parent:
            errors.append(f"{slug}: lower-tier record requires parentSlug")
        if tier in {"single-tier", "upper-tier"} and parent is not None:
            errors.append(f"{slug}: {tier} record must have null parentSlug")
        role = row["role"]
        if role not in {
            "anchor-upper-tier",
            "waterloo-member",
            "first-ring",
            "parent-authority",
        }:
            errors.append(f"{slug}: invalid role {role!r}")
        if role in {"anchor-upper-tier", "parent-authority"} and tier != "upper-tier":
            errors.append(f"{slug}: role {role!r} requires upper-tier")
        if role == "waterloo-member" and tier != "lower-tier":
            errors.append(f"{slug}: waterloo-member requires lower-tier")
        if role == "first-ring" and tier not in {"lower-tier", "single-tier"}:
            errors.append(f"{slug}: first-ring requires lower- or single-tier")

    codes = [row.get("assessmentCode") for row in rows if isinstance(row, dict)]
    if codes != sorted(codes):
        errors.append("jurisdictions must be ordered by assessmentCode")

    for slug, row in by_slug.items():
        parent = row["parentSlug"]
        if parent is None:
            continue
        if parent not in by_slug:
            errors.append(f"{slug}: parentSlug {parent!r} is absent from registry")
        elif by_slug[parent]["tier"] != "upper-tier":
            errors.append(f"{slug}: parentSlug {parent!r} is not upper-tier")

    anchor = registry["anchor"]
    anchor_members = set(anchor.get("memberSlugs", []))
    expected_members = set(OFFICIAL_WATERLOO_CODES)
    if anchor_members != expected_members:
        errors.append(
            "anchor.memberSlugs must be exactly the seven Waterloo lower tiers"
        )
    upper_slug = anchor.get("upperTierSlug")
    if upper_slug != "region-of-waterloo-on":
        errors.append("anchor.upperTierSlug must be 'region-of-waterloo-on'")

    for slug, expected_code in OFFICIAL_WATERLOO_CODES.items():
        row = by_slug.get(slug)
        if row is None:
            errors.append(f"missing Waterloo member {slug!r}")
            continue
        if row["assessmentCode"] != expected_code:
            errors.append(
                f"{slug}: expected official assessmentCode {expected_code}, "
                f"got {row['assessmentCode']!r}"
            )
        if row["parentSlug"] != upper_slug:
            errors.append(f"{slug}: parent must be {upper_slug!r}")
        if row["role"] != "waterloo-member":
            errors.append(f"{slug}: role must be 'waterloo-member'")

    touches = registry["touchesBySlug"]
    if not isinstance(touches, dict):
        return errors + ["touchesBySlug must be an object"]
    if set(touches) != expected_members:
        errors.append("touchesBySlug keys must be exactly the seven anchor members")

    derived_first_ring: set[str] = set()
    for slug, neighbours in touches.items():
        if not isinstance(neighbours, list):
            errors.append(f"{slug}: neighbours must be an array")
            continue
        if neighbours != sorted(neighbours):
            errors.append(f"{slug}: neighbours must be sorted")
        if len(neighbours) != len(set(neighbours)):
            errors.append(f"{slug}: neighbours contain duplicates")
        for neighbour in neighbours:
            if neighbour == slug:
                errors.append(f"{slug}: self-touch is invalid")
            if neighbour not in by_slug:
                errors.append(f"{slug}: unknown touching slug {neighbour!r}")
                continue
            if neighbour in anchor_members:
                reverse = touches.get(neighbour, [])
                if slug not in reverse:
                    errors.append(
                        f"asymmetric anchor adjacency: {slug!r} -> {neighbour!r}"
                    )
            else:
                derived_first_ring.add(neighbour)

    declared_first_ring = {
        slug for slug, row in by_slug.items() if row["role"] == "first-ring"
    }
    if derived_first_ring != declared_first_ring:
        errors.append(
            "first-ring roles do not equal non-anchor endpoints in touchesBySlug"
        )
    if declared_first_ring != EXPECTED_FIRST_RING:
        errors.append("first ring does not match the locked Ontario geometry result")

    if check_corpus:
        errors.extend(_validate_existing_corpus(by_slug, root))

    return errors


def _validate_existing_corpus(
    by_slug: dict[str, dict[str, Any]], root: Path
) -> list[str]:
    errors: list[str] = []
    corpus_root = root / "corpus"
    for slug, row in by_slug.items():
        pack = corpus_root / slug / "pack.yaml"
        if not pack.exists():
            continue

        pack_slug = _top_level_scalar(pack, "slug")
        if pack_slug != slug:
            errors.append(f"{pack}: slug is {pack_slug!r}, expected {slug!r}")

        # Existing upper-tier bridge packs may carry null codes. Every lower- or
        # single-tier pack must either carry the official code or explicitly mark
        # identity as unsupported while remaining blocked from sealed/published use.
        pack_identity_status = _top_level_scalar(pack, "identityStatus")
        if row["tier"] != "upper-tier":
            pack_code = _top_level_scalar(pack, "assessmentCode")
            publication_status = _section_scalar(pack, "publication", "status")
            if pack_identity_status not in {
                None,
                "verified",
                UNSUPPORTED_IDENTITY_STATUS,
            }:
                errors.append(
                    f"{pack}: identityStatus {pack_identity_status!r} is unsupported"
                )
            if pack_code is None:
                if pack_identity_status != UNSUPPORTED_IDENTITY_STATUS:
                    errors.append(
                        f"{pack}: missing assessmentCode; declare the official code "
                        "or identityStatus: unsupported"
                    )
            elif pack_code != row["assessmentCode"]:
                errors.append(
                    f"{pack}: assessmentCode is {pack_code!r}, "
                    f"expected {row['assessmentCode']!r}"
                )
            if pack_identity_status == UNSUPPORTED_IDENTITY_STATUS:
                if publication_status not in {"draft", "withdrawn"}:
                    errors.append(
                        f"{pack}: identityStatus unsupported requires publication.status "
                        "draft or withdrawn"
                    )

        parents = _top_level_list(pack, "parentBodies")
        expected_parent = row["parentSlug"]
        expected_parents = [expected_parent] if expected_parent else []
        if parents != expected_parents:
            errors.append(
                f"{pack}: parentBodies is {parents!r}, expected {expected_parents!r}"
            )

        build_inputs = pack.parent / "build-inputs.yaml"
        if build_inputs.exists():
            if row["tier"] != "upper-tier":
                input_code = _top_level_scalar(build_inputs, "assessmentCode")
                input_identity_status = _top_level_scalar(
                    build_inputs, "identityStatus"
                )
                if input_code is None:
                    if not (
                        input_identity_status == UNSUPPORTED_IDENTITY_STATUS
                        and pack_identity_status == UNSUPPORTED_IDENTITY_STATUS
                    ):
                        errors.append(
                            f"{build_inputs}: missing assessmentCode; declare the "
                            "official code or block both input and pack with "
                            "identityStatus: unsupported"
                        )
                elif input_code != row["assessmentCode"]:
                    errors.append(
                        f"{build_inputs}: assessmentCode is {input_code!r}, "
                        f"expected {row['assessmentCode']!r}"
                    )
                if (
                    input_identity_status == UNSUPPORTED_IDENTITY_STATUS
                    and pack_identity_status != UNSUPPORTED_IDENTITY_STATUS
                ):
                    errors.append(
                        f"{build_inputs}: unsupported identity requires the pack to "
                        "also declare identityStatus: unsupported"
                    )
            input_parents = _top_level_list(build_inputs, "parentBodies")
            if input_parents != expected_parents:
                errors.append(
                    f"{build_inputs}: parentBodies is {input_parents!r}, "
                    f"expected {expected_parents!r}"
                )
    return errors


def _registry_touch_codes(
    registry: dict[str, Any], errors: list[str]
) -> dict[str, list[str]]:
    rows = registry.get("jurisdictions")
    anchor = registry.get("anchor")
    touches = registry.get("touchesBySlug")
    if not isinstance(rows, list) or not isinstance(anchor, dict):
        errors.append("cannot derive locked topology from malformed registry")
        return {}
    if not isinstance(touches, dict):
        errors.append("cannot derive locked topology without touchesBySlug")
        return {}

    by_slug = {
        row.get("slug"): row.get("assessmentCode")
        for row in rows
        if isinstance(row, dict)
        and isinstance(row.get("slug"), str)
        and isinstance(row.get("assessmentCode"), str)
    }
    member_slugs = anchor.get("memberSlugs")
    if not isinstance(member_slugs, list):
        errors.append("cannot derive locked topology without anchor.memberSlugs")
        return {}

    result: dict[str, list[str]] = {}
    for slug in member_slugs:
        code = by_slug.get(slug)
        neighbours = touches.get(slug)
        if not isinstance(code, str) or not isinstance(neighbours, list):
            errors.append(f"cannot derive locked topology for {slug!r}")
            continue
        neighbour_codes: list[str] = []
        for neighbour in neighbours:
            neighbour_code = by_slug.get(neighbour)
            if not isinstance(neighbour_code, str):
                errors.append(
                    f"cannot derive locked topology for unknown neighbour {neighbour!r}"
                )
                continue
            neighbour_codes.append(neighbour_code)
        result[code] = sorted(neighbour_codes)
    return dict(sorted(result.items()))


def _canonical_touch_edges(
    touch_map: Any, label: str, errors: list[str]
) -> list[str]:
    if not isinstance(touch_map, dict):
        errors.append(f"{label} must be an object")
        return []

    edges: set[str] = set()
    anchor_codes = set(touch_map)
    for anchor_code, neighbours in touch_map.items():
        if not isinstance(anchor_code, str) or not CODE_RE.fullmatch(anchor_code):
            errors.append(f"{label} has invalid anchor code {anchor_code!r}")
            continue
        if not isinstance(neighbours, list):
            errors.append(f"{label}.{anchor_code} must be an array")
            continue
        if neighbours != sorted(neighbours):
            errors.append(f"{label}.{anchor_code} must be sorted")
        if len(neighbours) != len(set(neighbours)):
            errors.append(f"{label}.{anchor_code} contains duplicate neighbours")
        for neighbour_code in neighbours:
            if (
                not isinstance(neighbour_code, str)
                or not CODE_RE.fullmatch(neighbour_code)
            ):
                errors.append(
                    f"{label}.{anchor_code} has invalid neighbour {neighbour_code!r}"
                )
                continue
            if neighbour_code == anchor_code:
                errors.append(f"{label}.{anchor_code} contains a self-touch")
                continue
            if (
                neighbour_code in anchor_codes
                and anchor_code not in touch_map.get(neighbour_code, [])
            ):
                errors.append(
                    f"{label} has asymmetric anchor edge "
                    f"{anchor_code!r} -> {neighbour_code!r}"
                )
            edges.add("|".join(sorted((anchor_code, neighbour_code))))
    return sorted(edges)


def validate_source_lock(
    registry_path: Path,
    lock: dict[str, Any],
    *,
    registry: dict[str, Any] | None = None,
) -> list[str]:
    errors: list[str] = []
    required = {
        "schemaVersion",
        "registryPath",
        "registryCanonicalSha256",
        "lockedAt",
        "sources",
        "derivation",
    }
    missing = sorted(required - lock.keys())
    if missing:
        return [f"source lock missing fields: {', '.join(missing)}"]
    if lock["schemaVersion"] != "regional-geography-source-lock-1.0.0":
        errors.append(f"unsupported source lock version {lock['schemaVersion']!r}")
    expected_path = str(registry_path.relative_to(ROOT)).replace("\\", "/")
    if lock["registryPath"] != expected_path:
        errors.append(
            f"source lock registryPath is {lock['registryPath']!r}, "
            f"expected {expected_path!r}"
        )
    if registry is None:
        registry = load_json(registry_path)
    actual_hash = _canonical_sha256(registry)
    if lock["registryCanonicalSha256"] != actual_hash:
        errors.append(
            "canonical registry hash does not match source lock "
            f"(expected {lock['registryCanonicalSha256']}, got {actual_hash})"
        )
    locked_at = _utc_datetime(lock.get("lockedAt"), "source lock lockedAt", errors)

    sources = lock.get("sources")
    if not isinstance(sources, list) or len(sources) != len(OFFICIAL_SOURCE_METADATA):
        errors.append("source lock must declare the lower/single and upper layers")
    else:
        ids = [source.get("id") for source in sources if isinstance(source, dict)]
        if ids != list(OFFICIAL_SOURCE_METADATA):
            errors.append("source lock official layers are missing or out of order")
        for source in sources:
            if not isinstance(source, dict):
                errors.append("source lock source entries must be objects")
                continue
            source_id = source.get("id")
            expected = OFFICIAL_SOURCE_METADATA.get(source_id)
            if expected is None:
                errors.append(f"unexpected official source id {source_id!r}")
                continue
            for field, expected_value in expected.items():
                if source.get(field) != expected_value:
                    errors.append(
                        f"{source_id}: {field} is {source.get(field)!r}, "
                        f"expected {expected_value!r}"
                    )
            retrieved_at = _utc_datetime(
                source.get("retrievedAt"), f"{source_id}.retrievedAt", errors
            )
            effective_at = _utc_datetime(
                source.get("effectiveDatetime"),
                f"{source_id}.effectiveDatetime",
                errors,
            )
            if locked_at is not None and retrieved_at != locked_at:
                errors.append(f"{source_id}: retrievedAt must equal source lock lockedAt")
            if (
                effective_at is not None
                and effective_at.date().isoformat() != registry.get("effectiveDate")
            ):
                errors.append(
                    f"{source_id}: effective date does not match registry.effectiveDate"
                )
            if (
                retrieved_at is not None
                and effective_at is not None
                and effective_at > retrieved_at
            ):
                errors.append(f"{source_id}: effectiveDatetime is after retrievedAt")

    derivation = lock.get("derivation", {})
    if not isinstance(derivation, dict):
        return errors + ["source lock derivation must be an object"]
    if derivation.get("spatialRelation") != "esriSpatialRelTouches":
        errors.append("source lock spatial relation must be esriSpatialRelTouches")
    if derivation.get("runtimeNetworkRequired") is not False:
        errors.append("source lock must declare runtimeNetworkRequired false")
    if derivation.get("geometrySource") != "ontario-municlow-layer-14":
        errors.append("source lock geometrySource must be the official lower-tier layer")

    rows = registry.get("jurisdictions")
    rows = rows if isinstance(rows, list) else []
    anchor = registry.get("anchor")
    anchor = anchor if isinstance(anchor, dict) else {}
    by_slug = {
        row.get("slug"): row.get("assessmentCode")
        for row in rows
        if isinstance(row, dict)
    }
    member_slugs = anchor.get("memberSlugs")
    member_slugs = member_slugs if isinstance(member_slugs, list) else []
    expected_anchor_codes = sorted(
        code for slug in member_slugs if isinstance((code := by_slug.get(slug)), str)
    )
    if derivation.get("anchorAssessmentCodes") != expected_anchor_codes:
        errors.append(
            "source lock anchorAssessmentCodes do not match registry anchor members"
        )
    if expected_anchor_codes != sorted(OFFICIAL_WATERLOO_CODES.values()):
        errors.append("registry anchor codes do not match the official Waterloo cohort")

    expected_touch_map = _registry_touch_codes(registry, errors)
    locked_touch_map = derivation.get("touchesByAssessmentCode")
    locked_edges = _canonical_touch_edges(
        locked_touch_map, "derivation.touchesByAssessmentCode", errors
    )
    if locked_touch_map != expected_touch_map:
        errors.append(
            "registry touchesBySlug does not match the exact source-locked topology"
        )
    if derivation.get("touchesByAssessmentCodeCanonicalSha256") != _canonical_sha256(
        locked_touch_map
    ):
        errors.append("source-locked touch-map canonical hash is invalid")
    if derivation.get("normalizedTouchEdgesCanonicalSha256") != _canonical_sha256(
        locked_edges
    ):
        errors.append("source-locked normalized edge canonical hash is invalid")

    first_ring_count = sum(
        isinstance(row, dict) and row.get("role") == "first-ring" for row in rows
    )
    expected_counts = {
        "normalizedJurisdictionCount": len(rows),
        "firstRingMunicipalityCount": first_ring_count,
        "normalizedTouchEdgeCount": len(locked_edges),
    }
    for field, expected_value in expected_counts.items():
        if derivation.get(field) != expected_value:
            errors.append(
                f"source lock {field} is {derivation.get(field)!r}, "
                f"expected {expected_value}"
            )
    return errors


def main(argv: list[str]) -> int:
    registry_path = Path(argv[1]).resolve() if len(argv) > 1 else DEFAULT_REGISTRY
    lock_path = Path(argv[2]).resolve() if len(argv) > 2 else DEFAULT_LOCK

    errors: list[str] = []
    try:
        registry = load_json(registry_path)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: cannot read registry: {exc}", file=sys.stderr)
        return 1
    try:
        lock = load_json(lock_path)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: cannot read source lock: {exc}", file=sys.stderr)
        return 1

    errors.extend(validate_registry(registry))
    errors.extend(validate_source_lock(registry_path, lock, registry=registry))

    if errors:
        print(
            json.dumps(
                {
                    "ok": False,
                    "registry": str(registry_path.relative_to(ROOT)).replace("\\", "/"),
                    "errors": errors,
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return 1

    first_ring_count = sum(
        row["role"] == "first-ring" for row in registry["jurisdictions"]
    )
    print(
        json.dumps(
            {
                "ok": True,
                "registry": str(registry_path.relative_to(ROOT)).replace("\\", "/"),
                "waterlooMembers": len(registry["anchor"]["memberSlugs"]),
                "firstRingMunicipalities": first_ring_count,
                "runtimeNetworkRequired": False,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
