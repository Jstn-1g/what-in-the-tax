"""Fail-closed national registry assembly and coverage accounting."""

from __future__ import annotations

from collections import Counter
from typing import Any, Iterable

from .models import (
    GoverningBodyRecord,
    GeographyRecord,
    PROVINCE_TERRITORY_ISO_BY_SGC,
    PROVINCE_TERRITORY_ISO_CODES,
    SourceSnapshot,
    canonical_sha256,
)


class RegistryError(ValueError):
    """Normalized sources conflict or make an unsupported coverage claim."""


ALLOWED_LAYER_STATUSES = {
    "not-started",
    "source-discovery",
    "adapter-needed",
    "partial",
    "complete",
    "not-applicable",
}
BODY_TYPES_BY_COVERAGE_LAYER = {
    "federal-province-territory-governments": {
        "federal-government",
        "province-territory-government",
    },
    "municipal-regional-governments": {
        "municipal-government",
        "regional-government",
    },
    "indigenous-governments": {"indigenous-government"},
    "education-tax-authorities": {"school-authority"},
    "special-purpose-tax-authorities": {"special-purpose-authority"},
}
CANONICAL_REQUIRED_LAYERS = (
    "national-geography-baseline",
    "current-csd-geography",
    "federal-province-territory-governments",
    "municipal-regional-governments",
    "indigenous-governments",
    "education-tax-authorities",
    "special-purpose-tax-authorities",
)
APPROVED_LICENCE_STATUSES = {
    "cc-by-4.0-confirmed",
    "open-government-licence-confirmed",
    "open-licence-confirmed",
}


class NationalRegistryBuilder:
    """Combine official layers by exact identifiers, never names."""

    schema_version = "auditback-national-registry-1.0.0"

    def __init__(
        self,
        *,
        classification_version: str,
        source_catalog: dict[str, Any],
        coverage_plan: dict[str, Any] | None = None,
        scope: str = "production",
    ) -> None:
        if not classification_version.isdigit() or len(classification_version) != 4:
            raise RegistryError("classification_version must be four digits")
        self.classification_version = classification_version
        self.source_catalog = source_catalog
        if scope not in {"production", "test"}:
            raise RegistryError("scope must be 'production' or explicit non-production 'test'")
        self.scope = scope
        if not isinstance(coverage_plan, dict):
            raise RegistryError("coverage_plan must be an explicit object")
        self.coverage_plan = coverage_plan
        plan_version = self.coverage_plan.get("classificationVersion")
        if plan_version != classification_version:
            raise RegistryError(
                "coverage plan classificationVersion must match the registry build"
            )

    def build(
        self,
        *,
        geographies: Iterable[GeographyRecord],
        governing_bodies: Iterable[GoverningBodyRecord],
        snapshots: Iterable[SourceSnapshot],
    ) -> dict[str, Any]:
        geography_rows = sorted(geographies, key=lambda item: item.geography_id)
        body_rows = sorted(governing_bodies, key=lambda item: item.body_id)
        snapshot_rows = sorted(snapshots, key=lambda item: (item.source_id, item.sha256))

        geography_by_id = self._unique_by_id(
            geography_rows,
            key=lambda item: item.geography_id,
            label="geography",
        )
        body_by_id = self._unique_by_id(
            body_rows,
            key=lambda item: item.body_id,
            label="governing body",
        )
        catalog_by_source = self._validate_source_catalog()
        snapshot_by_identity = self._validate_snapshots(
            snapshot_rows,
            catalog_by_source,
        )
        self._validate_geography_identities(geography_rows)
        self._validate_hierarchy(geography_rows, geography_by_id)
        self._validate_body_crosswalks(body_rows, geography_by_id)
        self._validate_external_ids(body_rows)
        self._validate_provenance(
            [*geography_rows, *body_rows],
            snapshot_by_identity,
            catalog_by_source,
        )

        coverage = self._build_coverage(
            geography_rows,
            body_rows,
            snapshot_rows,
            catalog_by_source,
        )
        document: dict[str, Any] = {
            "schemaVersion": self.schema_version,
            "country": "CA",
            "buildScope": self.scope,
            "classification": {
                "system": "Statistics Canada Standard Geographical Classification",
                "version": self.classification_version,
            },
            "method": {
                "runtimeNetworkRequired": False,
                "runtimeAiRequired": False,
                "identityMerge": "exact-official-identifiers-only",
                "statisticalAreasAreGovernments": False,
            },
            "sourceSnapshots": [snapshot.to_dict() for snapshot in snapshot_rows],
            "geographies": [record.to_dict() for record in geography_rows],
            "governingBodies": [record.to_dict() for record in body_rows],
            "coverage": coverage,
            "counts": {
                "geographies": len(geography_rows),
                "governingBodies": len(body_rows),
                "sourceSnapshots": len(snapshot_rows),
                "geographyLevels": {
                    level: sum(1 for item in geography_rows if item.level == level)
                    for level in (
                        "region",
                        "province-territory",
                        "census-division",
                        "census-subdivision",
                    )
                },
                "governingBodyTypes": dict(
                    sorted(Counter(item.body_type for item in body_rows).items())
                ),
            },
        }
        document["registryCanonicalSha256"] = canonical_sha256(document)
        return document

    @staticmethod
    def _unique_by_id(rows: list[Any], *, key: Any, label: str) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for row in rows:
            identity = key(row)
            if identity in result:
                raise RegistryError(f"duplicate {label} id {identity!r}")
            result[identity] = row
        return result

    def _validate_source_catalog(self) -> dict[str, dict[str, Any]]:
        rows = self.source_catalog.get("sources")
        if not isinstance(rows, list):
            raise RegistryError("source catalog must contain a sources array")
        required = {
            "sourceId",
            "publisher",
            "jurisdiction",
            "coverageLayer",
            "requestUrl",
            "mediaType",
            "adapterId",
            "adapterVersion",
            "runtimeNetworkRequired",
            "approvedSha256",
            "licenseStatus",
            "licenseUrl",
            "reuseReviewRequired",
        }
        by_source: dict[str, dict[str, Any]] = {}
        for index, raw in enumerate(rows):
            if not isinstance(raw, dict):
                raise RegistryError(f"source catalog sources[{index}] must be an object")
            missing = sorted(required - raw.keys())
            if missing:
                raise RegistryError(
                    f"source catalog sources[{index}] missing fields: {', '.join(missing)}"
                )
            source_id = raw["sourceId"]
            if not isinstance(source_id, str) or not source_id:
                raise RegistryError(f"source catalog sources[{index}] has invalid sourceId")
            if source_id in by_source:
                raise RegistryError(f"duplicate source catalog id {source_id!r}")
            if raw["runtimeNetworkRequired"] is not False:
                raise RegistryError(
                    f"{source_id}: source parsing must not require runtime network access"
                )
            if not isinstance(raw["requestUrl"], str) or not raw["requestUrl"].startswith(
                "https://"
            ):
                raise RegistryError(f"{source_id}: requestUrl must use HTTPS")
            if (
                not isinstance(raw["licenseStatus"], str)
                or not raw["licenseStatus"]
            ):
                raise RegistryError(f"{source_id}: licenseStatus must be a non-empty string")
            if (
                not isinstance(raw["licenseUrl"], str)
                or not raw["licenseUrl"].startswith("https://")
            ):
                raise RegistryError(f"{source_id}: licenseUrl must use HTTPS")
            if not isinstance(raw["reuseReviewRequired"], bool):
                raise RegistryError(f"{source_id}: reuseReviewRequired must be boolean")
            if raw.get("publicSafe") is True:
                self._validate_source_reuse_approval(source_id, raw)
            for field in (
                "publisher",
                "jurisdiction",
                "coverageLayer",
                "mediaType",
                "adapterId",
                "adapterVersion",
            ):
                if not isinstance(raw[field], str) or not raw[field]:
                    raise RegistryError(f"{source_id}: {field} must be a non-empty string")
            if raw["jurisdiction"] not in {
                "CA",
                *PROVINCE_TERRITORY_ISO_CODES,
            }:
                raise RegistryError(
                    f"{source_id}: jurisdiction must be CA or a Canadian "
                    "province/territory code"
                )
            approved_sha256 = raw["approvedSha256"]
            if (
                not isinstance(approved_sha256, str)
                or len(approved_sha256) != 64
                or any(character not in "0123456789abcdef" for character in approved_sha256)
            ):
                raise RegistryError(
                    f"{source_id}: approvedSha256 must be lowercase SHA-256 hex"
                )
            if raw["coverageLayer"] == "national-geography-baseline":
                if raw.get("classificationVersion") != self.classification_version:
                    raise RegistryError(
                        f"{source_id}: classificationVersion does not match build version "
                        f"{self.classification_version}"
                    )
            multi_rule = raw.get("multiJurisdictionRule")
            if multi_rule is not None:
                if not isinstance(multi_rule, dict):
                    raise RegistryError(
                        f"{source_id}: multiJurisdictionRule must be an object"
                    )
                allowed = multi_rule.get("allowedProvinceTerritories")
                basis = multi_rule.get("basis")
                if (
                    not isinstance(allowed, list)
                    or not allowed
                    or not all(
                        isinstance(code, str)
                        and code in PROVINCE_TERRITORY_ISO_CODES
                        for code in allowed
                    )
                    or len(allowed) != len(set(allowed))
                    or not isinstance(basis, str)
                    or not basis.strip()
                ):
                    raise RegistryError(
                        f"{source_id}: multiJurisdictionRule requires unique Canadian "
                        "province/territory codes and a documented basis"
                    )
            by_source[source_id] = raw
        return by_source

    @staticmethod
    def _validate_source_reuse_approval(
        source_id: str,
        catalog_row: dict[str, Any],
    ) -> None:
        if catalog_row["reuseReviewRequired"] is not False:
            raise RegistryError(
                f"{source_id}: complete/public-safe coverage requires reuseReviewRequired=false"
            )
        if catalog_row["licenseStatus"] not in APPROVED_LICENCE_STATUSES:
            raise RegistryError(
                f"{source_id}: licence status {catalog_row['licenseStatus']!r} "
                "is not approved for complete/public-safe coverage"
            )

    @staticmethod
    def _validate_snapshots(
        rows: list[SourceSnapshot],
        catalog_by_source: dict[str, dict[str, Any]],
    ) -> dict[tuple[str, str], SourceSnapshot]:
        by_identity: dict[tuple[str, str], SourceSnapshot] = {}
        source_hashes: dict[str, str] = {}
        for snapshot in rows:
            catalog_row = catalog_by_source.get(snapshot.source_id)
            if catalog_row is None:
                raise RegistryError(
                    f"source snapshot {snapshot.source_id!r} is absent from source catalog"
                )
            if snapshot.request_url != catalog_row["requestUrl"]:
                raise RegistryError(
                    f"{snapshot.source_id}: snapshot request URL differs from source catalog"
                )
            if snapshot.media_type != catalog_row["mediaType"]:
                raise RegistryError(
                    f"{snapshot.source_id}: snapshot media type differs from source catalog"
                )
            if snapshot.sha256 != catalog_row["approvedSha256"]:
                raise RegistryError(
                    f"{snapshot.source_id}: snapshot hash is not the approved release hash"
                )
            identity = (snapshot.source_id, snapshot.sha256)
            if identity in by_identity:
                raise RegistryError(
                    f"duplicate source snapshot {snapshot.source_id}/{snapshot.sha256}"
                )
            prior_hash = source_hashes.get(snapshot.source_id)
            if prior_hash is not None and prior_hash != snapshot.sha256:
                raise RegistryError(
                    f"source {snapshot.source_id!r} has multiple active snapshots "
                    "in one build"
                )
            source_hashes[snapshot.source_id] = snapshot.sha256
            by_identity[identity] = snapshot
        return by_identity

    def _validate_geography_identities(
        self,
        rows: list[GeographyRecord],
    ) -> None:
        for row in rows:
            expected_id = (
                f"ca:sgc:{self.classification_version}:{row.level}:{row.sgc_code}"
            )
            if row.geography_id != expected_id:
                raise RegistryError(
                    f"{row.geography_id}: SGC geography id/version does not match "
                    f"build classification {self.classification_version}"
                )
            expected_pt_code = (
                row.sgc_code
                if row.level == "province-territory"
                else row.sgc_code[:2]
                if row.level in {"census-division", "census-subdivision"}
                else None
            )
            expected_iso = (
                PROVINCE_TERRITORY_ISO_BY_SGC.get(expected_pt_code)
                if expected_pt_code is not None
                else None
            )
            if (
                row.province_territory_code != expected_pt_code
                or row.province_territory_iso != expected_iso
            ):
                raise RegistryError(
                    f"{row.geography_id}: province/territory codes do not match "
                    "the SGC code prefix"
                )

    @staticmethod
    def _validate_hierarchy(
        rows: list[GeographyRecord],
        by_id: dict[str, GeographyRecord],
    ) -> None:
        expected_parent_level = {
            "province-territory": "region",
            "census-division": "province-territory",
            "census-subdivision": "census-division",
        }
        for row in rows:
            if row.level == "region":
                if row.parent_id is not None:
                    raise RegistryError(f"{row.geography_id}: region cannot have a parent")
                continue
            if row.parent_id is None:
                raise RegistryError(f"{row.geography_id}: parent is required")
            parent = by_id.get(row.parent_id)
            if parent is None:
                raise RegistryError(f"{row.geography_id}: parent is absent")
            if parent.level != expected_parent_level[row.level]:
                raise RegistryError(
                    f"{row.geography_id}: expected {expected_parent_level[row.level]} "
                    f"parent, found {parent.level}"
                )
            parent_code_length = {
                "province-territory": 1,
                "census-division": 2,
                "census-subdivision": 4,
            }[row.level]
            expected_parent_code = row.sgc_code[:parent_code_length]
            if parent.sgc_code != expected_parent_code:
                raise RegistryError(
                    f"{row.geography_id}: parent SGC code must be prefix "
                    f"{expected_parent_code!r}"
                )

    @staticmethod
    def _validate_body_crosswalks(
        rows: list[GoverningBodyRecord],
        geography_by_id: dict[str, GeographyRecord],
    ) -> None:
        for body in rows:
            if (
                body.body_type == "federal-government"
                and body.province_territory_iso is not None
            ):
                raise RegistryError(
                    f"{body.body_id}: federal-government must be Canada-scoped "
                    "with no province/territory"
                )
            if (
                body.body_type != "federal-government"
                and body.province_territory_iso is None
            ):
                raise RegistryError(
                    f"{body.body_id}: a non-federal governing body must declare "
                    "a province/territory"
                )
            if body.body_type != "federal-government" and not body.geography_ids:
                raise RegistryError(
                    f"{body.body_id}: a non-federal governing body must have at "
                    "least one exact geography crosswalk"
                )
            for geography_id in body.geography_ids:
                geography = geography_by_id.get(geography_id)
                if geography is None:
                    raise RegistryError(
                        f"{body.body_id}: unknown exact geography crosswalk {geography_id!r}"
                    )
                if (
                    body.province_territory_iso is not None
                    and geography.province_territory_iso
                    != body.province_territory_iso
                ):
                    raise RegistryError(
                        f"{body.body_id}: province {body.province_territory_iso} "
                        f"cannot govern geography in {geography.province_territory_iso}"
                    )

    @staticmethod
    def _validate_external_ids(rows: list[GoverningBodyRecord]) -> None:
        seen: dict[tuple[str, str], str] = {}
        for body in rows:
            for identifier in body.external_ids:
                other = seen.get(identifier)
                if other is not None:
                    raise RegistryError(
                        f"official external id {identifier!r} belongs to both "
                        f"{other!r} and {body.body_id!r}"
                    )
                seen[identifier] = body.body_id

    def _validate_provenance(
        self,
        rows: list[GeographyRecord | GoverningBodyRecord],
        snapshots: dict[tuple[str, str], SourceSnapshot],
        catalog_by_source: dict[str, dict[str, Any]],
    ) -> None:
        for row in rows:
            provenance = row.provenance
            identity = (provenance.source_id, provenance.snapshot_sha256)
            if identity not in snapshots:
                raise RegistryError(
                    f"{getattr(row, 'geography_id', getattr(row, 'body_id', 'record'))}: "
                    "provenance references an unlocked source snapshot"
                )
            catalog_row = catalog_by_source[provenance.source_id]
            if self.scope == "production":
                self._validate_source_reuse_approval(
                    provenance.source_id,
                    catalog_row,
                )
            if provenance.adapter_id != catalog_row["adapterId"]:
                raise RegistryError(
                    f"{provenance.source_id}: record adapter ID differs from source catalog"
                )
            if provenance.adapter_version != catalog_row["adapterVersion"]:
                raise RegistryError(
                    f"{provenance.source_id}: record adapter version differs from source catalog"
                )
            if isinstance(row, GoverningBodyRecord):
                source_jurisdiction = catalog_row["jurisdiction"]
                body_jurisdiction = row.province_territory_iso
                if row.body_type == "federal-government" and (
                    body_jurisdiction is not None or source_jurisdiction != "CA"
                ):
                    raise RegistryError(
                        f"{row.body_id}: federal-government must be Canada-scoped "
                        "and proven by a CA source"
                    )
                if body_jurisdiction is None:
                    if (
                        row.body_type != "federal-government"
                        or source_jurisdiction != "CA"
                    ):
                        raise RegistryError(
                            f"{row.body_id}: body without a province/territory must "
                            "be a federal government proven by a CA source"
                        )
                elif source_jurisdiction == body_jurisdiction:
                    pass
                elif source_jurisdiction == "CA":
                    rule = catalog_row.get("multiJurisdictionRule")
                    allowed = (
                        rule.get("allowedProvinceTerritories")
                        if isinstance(rule, dict)
                        else None
                    )
                    if not isinstance(allowed, list) or body_jurisdiction not in allowed:
                        raise RegistryError(
                            f"{row.body_id}: CA source requires an explicit documented "
                            f"multi-jurisdiction rule for {body_jurisdiction}"
                        )
                else:
                    raise RegistryError(
                        f"{row.body_id}: source jurisdiction {source_jurisdiction} "
                        f"does not match body jurisdiction {body_jurisdiction}"
                    )
                allowed_types = BODY_TYPES_BY_COVERAGE_LAYER.get(
                    catalog_row["coverageLayer"]
                )
                if allowed_types is not None and row.body_type not in allowed_types:
                    raise RegistryError(
                        f"{row.body_id}: body type {row.body_type!r} is not supported "
                        f"by source layer {catalog_row['coverageLayer']!r}"
                    )

    def _build_coverage(
        self,
        geographies: list[GeographyRecord],
        bodies: list[GoverningBodyRecord],
        snapshots: list[SourceSnapshot],
        catalog_by_source: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        plan_rows = self.coverage_plan.get("jurisdictions")
        required_layers = self.coverage_plan.get("requiredLayers")
        if not isinstance(plan_rows, list) or not isinstance(required_layers, list):
            raise RegistryError(
                "coverage plan must contain jurisdictions and requiredLayers arrays"
            )
        if not all(isinstance(layer, str) and layer for layer in required_layers):
            raise RegistryError("requiredLayers must contain non-empty strings")
        if len(required_layers) != len(set(required_layers)):
            raise RegistryError("requiredLayers must not contain duplicates")
        if not required_layers:
            raise RegistryError("requiredLayers must not be empty")
        if self.scope == "production" and required_layers != list(
            CANONICAL_REQUIRED_LAYERS
        ):
            raise RegistryError(
                "production coverage requires the canonical seven requiredLayers"
            )
        expected_counts = self.coverage_plan.get("expectedGeographyCounts")
        if not isinstance(expected_counts, dict):
            raise RegistryError("coverage plan must contain expectedGeographyCounts")
        observed_counts = Counter(item.level for item in geographies)
        for level in (
            "region",
            "province-territory",
            "census-division",
            "census-subdivision",
        ):
            expected = expected_counts.get(level)
            if isinstance(expected, bool) or not isinstance(expected, int) or expected < 0:
                raise RegistryError(
                    f"expectedGeographyCounts.{level} must be a non-negative integer"
                )
            if observed_counts[level] != expected:
                raise RegistryError(
                    f"{level} count mismatch: expected {expected}, "
                    f"observed {observed_counts[level]}"
                )
        source_ids = {snapshot.source_id for snapshot in snapshots}
        jurisdiction_codes: set[str] = set()
        body_counts = Counter(
            body.province_territory_iso
            for body in bodies
            if body.province_territory_iso is not None
        )
        csd_counts = Counter(
            geography.province_territory_iso
            for geography in geographies
            if geography.level == "census-subdivision"
            and geography.province_territory_iso is not None
        )
        results: list[dict[str, Any]] = []
        for raw in plan_rows:
            if not isinstance(raw, dict):
                raise RegistryError("coverage jurisdiction rows must be objects")
            code = raw.get("code")
            if not isinstance(code, str) or len(code) != 2:
                raise RegistryError("coverage jurisdiction code must be a two-letter string")
            if code in jurisdiction_codes:
                raise RegistryError(f"duplicate coverage jurisdiction {code!r}")
            jurisdiction_codes.add(code)
            name = raw.get("name")
            if not isinstance(name, str) or not name.strip():
                raise RegistryError(f"{code}: jurisdiction name must be a non-empty string")
            raw_layers = raw.get("layers", {})
            if not isinstance(raw_layers, dict):
                raise RegistryError(f"{code}: layers must be an object")
            missing_layers = sorted(set(required_layers) - set(raw_layers))
            extra_layers = sorted(set(raw_layers) - set(required_layers))
            if missing_layers or extra_layers:
                details: list[str] = []
                if missing_layers:
                    details.append(f"missing {', '.join(missing_layers)}")
                if extra_layers:
                    details.append(f"unexpected {', '.join(extra_layers)}")
                raise RegistryError(
                    f"{code}: layers must explicitly match requiredLayers "
                    f"({'; '.join(details)})"
                )
            expected_csd_count = raw.get("expectedCensusSubdivisionCount")
            if (
                isinstance(expected_csd_count, bool)
                or not isinstance(expected_csd_count, int)
                or expected_csd_count < 0
            ):
                raise RegistryError(
                    f"{code}: expectedCensusSubdivisionCount must be "
                    "a non-negative integer"
                )
            layers: list[dict[str, Any]] = []
            for layer_id in required_layers:
                value = raw_layers[layer_id]
                if not isinstance(value, dict):
                    raise RegistryError(f"{code}/{layer_id}: layer must be an object")
                if "status" not in value or "sourceIds" not in value:
                    raise RegistryError(
                        f"{code}/{layer_id}: status and sourceIds are required"
                    )
                status = value["status"]
                layer_source_ids = value["sourceIds"]
                if status not in ALLOWED_LAYER_STATUSES:
                    raise RegistryError(f"{code}/{layer_id}: unsupported status {status!r}")
                if not isinstance(layer_source_ids, list) or not all(
                    isinstance(item, str) for item in layer_source_ids
                ):
                    raise RegistryError(f"{code}/{layer_id}: sourceIds must be a string array")
                if len(layer_source_ids) != len(set(layer_source_ids)):
                    raise RegistryError(
                        f"{code}/{layer_id}: sourceIds must not contain duplicates"
                    )
                missing_sources = sorted(set(layer_source_ids) - source_ids)
                if status == "complete" and missing_sources:
                    raise RegistryError(
                        f"{code}/{layer_id}: complete coverage references unlocked sources "
                        f"{', '.join(missing_sources)}"
                    )
                if status == "complete" and not layer_source_ids:
                    raise RegistryError(
                        f"{code}/{layer_id}: complete coverage requires a locked source"
                    )
                for source_id in layer_source_ids:
                    catalog_row = catalog_by_source.get(source_id)
                    if catalog_row is None:
                        raise RegistryError(
                            f"{code}/{layer_id}: source {source_id!r} is absent "
                            "from source catalog"
                        )
                    if catalog_row["coverageLayer"] != layer_id:
                        raise RegistryError(
                            f"{code}/{layer_id}: source {source_id!r} is catalogued "
                            f"for {catalog_row['coverageLayer']!r}"
                        )
                    if catalog_row["jurisdiction"] not in {"CA", code}:
                        raise RegistryError(
                            f"{code}/{layer_id}: source {source_id!r} belongs to "
                            f"jurisdiction {catalog_row['jurisdiction']!r}"
                        )
                    if status == "complete":
                        self._validate_source_reuse_approval(source_id, catalog_row)
                if (
                    status == "complete"
                    and layer_id == "national-geography-baseline"
                    and csd_counts[code] != expected_csd_count
                ):
                    raise RegistryError(
                        f"{code}/{layer_id}: expected {expected_csd_count} census "
                        f"subdivisions, observed {csd_counts[code]}"
                    )
                body_types = BODY_TYPES_BY_COVERAGE_LAYER.get(layer_id)
                if status == "complete" and body_types is not None:
                    expected_bodies = value.get("expectedVerifiedBodyCount")
                    if (
                        isinstance(expected_bodies, bool)
                        or not isinstance(expected_bodies, int)
                        or expected_bodies < 1
                    ):
                        raise RegistryError(
                            f"{code}/{layer_id}: complete administrative coverage "
                            "requires a positive expectedVerifiedBodyCount"
                        )
                    observed_bodies = sum(
                        1
                        for body in bodies
                        if body.body_type in body_types
                        and body.province_territory_iso == code
                        and body.provenance.source_id in layer_source_ids
                    )
                    if observed_bodies != expected_bodies:
                        raise RegistryError(
                            f"{code}/{layer_id}: expected {expected_bodies} verified "
                            f"bodies, observed {observed_bodies}"
                        )
                layers.append(
                    {
                        "layer": layer_id,
                        "status": status,
                        "sourceIds": sorted(layer_source_ids),
                    }
                )
            coverage_status = (
                "complete"
                if layers
                and all(
                    item["status"] in {"complete", "not-applicable"} for item in layers
                )
                else "partial"
                if any(item["status"] in {"partial", "complete"} for item in layers)
                else "planned"
            )
            results.append(
                {
                    "provinceTerritory": code,
                    "name": name,
                    "status": coverage_status,
                    "censusSubdivisionBaselineCount": csd_counts[code],
                    "expectedCensusSubdivisionBaselineCount": expected_csd_count,
                    "verifiedGoverningBodyCount": body_counts[code],
                    "layers": layers,
                }
            )
        if not jurisdiction_codes:
            raise RegistryError("coverage plan must include at least one jurisdiction")
        if self.scope == "production" and jurisdiction_codes != PROVINCE_TERRITORY_ISO_CODES:
            missing = sorted(PROVINCE_TERRITORY_ISO_CODES - jurisdiction_codes)
            extra = sorted(jurisdiction_codes - PROVINCE_TERRITORY_ISO_CODES)
            details: list[str] = []
            if missing:
                details.append(f"missing {', '.join(missing)}")
            if extra:
                details.append(f"unexpected {', '.join(extra)}")
            raise RegistryError(
                "production coverage requires the exact 13 province/territory codes "
                f"({'; '.join(details)})"
            )
        return {
            "claim": (
                "Coverage is complete only when every required administrative layer "
                "is backed by a locked official source. Census geography alone is a baseline."
            ),
            "requiredLayers": required_layers,
            "jurisdictions": sorted(
                results,
                key=lambda item: item["provinceTerritory"],
            ),
        }
