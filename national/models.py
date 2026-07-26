"""Typed records shared by national source adapters and registry builds."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import date
from typing import Any


SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
SOURCE_ID_RE = re.compile(r"^[a-z0-9]+(?:[._-][a-z0-9]+)*$")
CANONICAL_ID_RE = re.compile(r"^ca:[a-z0-9][a-z0-9:._-]+$")
SGC_CODE_LENGTHS = {
    "region": 1,
    "province-territory": 2,
    "census-division": 4,
    "census-subdivision": 7,
}
BODY_TYPES = {
    "federal-government",
    "province-territory-government",
    "municipal-government",
    "regional-government",
    "indigenous-government",
    "school-authority",
    "special-purpose-authority",
}
BODY_STATUSES = {"active", "inactive", "transitional"}
GOVERNMENT_TIERS = {
    "national",
    "province-territory",
    "single-tier",
    "lower-tier",
    "upper-tier",
    "overlapping",
    "indigenous",
    "special-purpose",
}
ALLOWED_GOVERNMENT_TIERS_BY_BODY_TYPE = {
    "federal-government": frozenset({"national"}),
    "province-territory-government": frozenset({"province-territory"}),
    "municipal-government": frozenset({"single-tier", "lower-tier"}),
    "regional-government": frozenset({"upper-tier", "overlapping"}),
    "indigenous-government": frozenset({"indigenous"}),
    "school-authority": frozenset({"special-purpose", "overlapping"}),
    "special-purpose-authority": frozenset({"special-purpose", "overlapping"}),
}
PROVINCE_TERRITORY_ISO_CODES = {
    "AB",
    "BC",
    "MB",
    "NB",
    "NL",
    "NS",
    "NT",
    "NU",
    "ON",
    "PE",
    "QC",
    "SK",
    "YT",
}
PROVINCE_TERRITORY_ISO_BY_SGC = {
    "10": "NL",
    "11": "PE",
    "12": "NS",
    "13": "NB",
    "24": "QC",
    "35": "ON",
    "46": "MB",
    "47": "SK",
    "48": "AB",
    "59": "BC",
    "60": "YT",
    "61": "NT",
    "62": "NU",
}


class ModelValidationError(ValueError):
    """A normalized national record violated a closed schema boundary."""


def canonical_json_bytes(value: Any) -> bytes:
    """Serialize JSON semantics reproducibly across platforms."""

    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def require_sha256(value: str, *, label: str) -> str:
    if not isinstance(value, str) or SHA256_RE.fullmatch(value) is None:
        raise ModelValidationError(f"{label} must be a lowercase SHA-256 hex digest")
    return value


def require_source_id(value: str) -> str:
    if not isinstance(value, str) or SOURCE_ID_RE.fullmatch(value) is None:
        raise ModelValidationError(
            "source_id must contain lowercase letters, digits, dots, underscores, or hyphens"
        )
    return value


def require_canonical_id(value: str, *, label: str) -> str:
    if not isinstance(value, str) or CANONICAL_ID_RE.fullmatch(value) is None:
        raise ModelValidationError(f"{label} must be a namespaced ca: identifier")
    return value


def require_bcp47_tag(value: str, *, label: str = "language tag") -> str:
    """Validate the canonical subset of BCP 47 used by official-name records.

    The registry accepts an ISO 639 language, optional script, optional region,
    and optional variants, plus the explicit ``und`` tag. Requiring canonical
    case makes duplicate detection deterministic without attempting to infer or
    translate a source's language.
    """

    if not isinstance(value, str) or not value:
        raise ModelValidationError(f"{label} must be a BCP-47 language tag or 'und'")
    if value == "und":
        return value
    parts = value.split("-")
    if not (2 <= len(parts[0]) <= 3 and parts[0].isalpha() and parts[0].islower()):
        raise ModelValidationError(f"{label} must be a canonical BCP-47 tag or 'und'")
    index = 1
    if index < len(parts) and len(parts[index]) == 4 and parts[index].isalpha():
        script = parts[index]
        if script != script.title():
            raise ModelValidationError(f"{label} script subtag must use title case")
        index += 1
    if index < len(parts):
        region = parts[index]
        if (len(region) == 2 and region.isalpha()) or (
            len(region) == 3 and region.isdigit()
        ):
            if region.isalpha() and region != region.upper():
                raise ModelValidationError(f"{label} region subtag must use uppercase")
            index += 1
    for variant in parts[index:]:
        if not variant.isalnum() or not (
            5 <= len(variant) <= 8
            or (len(variant) == 4 and variant[0].isdigit())
        ):
            raise ModelValidationError(f"{label} contains an invalid BCP-47 variant")
        if variant != variant.lower():
            raise ModelValidationError(f"{label} variant subtags must use lowercase")
    return value


@dataclass(frozen=True, slots=True)
class SourceSnapshot:
    """Immutable identity and transport metadata for one official payload."""

    source_id: str
    sha256: str
    byte_length: int
    media_type: str
    request_url: str
    retrieved_at: str | None = None
    effective_date: str | None = None
    etag: str | None = None
    last_modified: str | None = None

    def __post_init__(self) -> None:
        require_source_id(self.source_id)
        require_sha256(self.sha256, label="snapshot sha256")
        if (
            isinstance(self.byte_length, bool)
            or not isinstance(self.byte_length, int)
            or self.byte_length < 0
        ):
            raise ModelValidationError("byte_length must be a non-negative integer")
        if not self.media_type:
            raise ModelValidationError("media_type is required")
        if not self.request_url.startswith("https://"):
            raise ModelValidationError("official source request_url must use HTTPS")
        for label, value in (
            ("retrieved_at", self.retrieved_at),
            ("effective_date", self.effective_date),
            ("etag", self.etag),
            ("last_modified", self.last_modified),
        ):
            if value is not None and (not isinstance(value, str) or not value):
                raise ModelValidationError(f"{label} must be a non-empty string when set")

    def to_dict(self) -> dict[str, Any]:
        value: dict[str, Any] = {
            "sourceId": self.source_id,
            "sha256": self.sha256,
            "byteLength": self.byte_length,
            "mediaType": self.media_type,
            "requestUrl": self.request_url,
        }
        for key, item in (
            ("retrievedAt", self.retrieved_at),
            ("effectiveDate", self.effective_date),
            ("etag", self.etag),
            ("lastModified", self.last_modified),
        ):
            if item is not None:
                value[key] = item
        return value


@dataclass(frozen=True, slots=True)
class ProvenanceRef:
    """A field-level pointer back to one source row in one locked snapshot."""

    source_id: str
    snapshot_sha256: str
    record_key: str
    source_fields: tuple[str, ...]
    transform: str
    adapter_id: str
    adapter_version: str

    def __post_init__(self) -> None:
        require_source_id(self.source_id)
        require_sha256(self.snapshot_sha256, label="provenance snapshot_sha256")
        if not self.record_key:
            raise ModelValidationError("record_key is required")
        if not self.source_fields:
            raise ModelValidationError("source_fields must not be empty")
        if not self.transform or not self.adapter_id or not self.adapter_version:
            raise ModelValidationError("transform, adapter_id, and adapter_version are required")

    def to_dict(self) -> dict[str, Any]:
        return {
            "sourceId": self.source_id,
            "snapshotSha256": self.snapshot_sha256,
            "recordKey": self.record_key,
            "sourceFields": list(self.source_fields),
            "transform": self.transform,
            "adapterId": self.adapter_id,
            "adapterVersion": self.adapter_version,
        }


@dataclass(frozen=True, slots=True)
class GeographyRecord:
    """One official geographic unit; not necessarily a governing body."""

    geography_id: str
    level: str
    sgc_code: str
    name_en: str
    parent_id: str | None
    province_territory_code: str | None
    province_territory_iso: str | None
    provenance: ProvenanceRef

    def __post_init__(self) -> None:
        require_canonical_id(self.geography_id, label="geography_id")
        expected_length = SGC_CODE_LENGTHS.get(self.level)
        if expected_length is None:
            raise ModelValidationError(f"unsupported geography level {self.level!r}")
        if not self.sgc_code.isdigit() or len(self.sgc_code) != expected_length:
            raise ModelValidationError(
                f"{self.level} SGC code must be a {expected_length}-digit string"
            )
        if not self.name_en.strip():
            raise ModelValidationError("name_en is required")
        if self.parent_id is not None:
            require_canonical_id(self.parent_id, label="parent_id")
        if self.province_territory_code is not None:
            if (
                not self.province_territory_code.isdigit()
                or len(self.province_territory_code) != 2
            ):
                raise ModelValidationError(
                    "province_territory_code must be a two-digit string"
                )
        if (
            self.province_territory_iso is not None
            and self.province_territory_iso not in PROVINCE_TERRITORY_ISO_CODES
        ):
            raise ModelValidationError("province_territory_iso is not a Canadian code")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.geography_id,
            "kind": "official-geography",
            "level": self.level,
            "codes": {
                "sgc": self.sgc_code,
                "provinceTerritory": self.province_territory_code,
                "isoSubdivision": self.province_territory_iso,
            },
            # This adapter consumes Statistics Canada's explicitly English SGC
            # release. The language tag is therefore source-derived, not guessed.
            "officialNames": {"en-CA": self.name_en},
            "parentId": self.parent_id,
            # A CSD can be a municipality or an area treated as equivalent for
            # statistical purposes. It is never promoted to a government here.
            "governingBodyVerification": (
                "requires-official-directory-match"
                if self.level in {"census-division", "census-subdivision"}
                else "not-applicable"
            ),
            "provenance": self.provenance.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class GoverningBodyRecord:
    """A body confirmed by an official administrative directory."""

    body_id: str
    body_type: str
    status: str
    official_names: tuple[tuple[str, str], ...]
    province_territory_iso: str | None
    official_url: str
    external_ids: tuple[tuple[str, str], ...]
    geography_ids: tuple[str, ...]
    official_legal_type: str
    government_tier: str
    parent_body_ids: tuple[str, ...]
    effective_from: str | None
    effective_to: str | None
    provenance: ProvenanceRef

    def __post_init__(self) -> None:
        require_canonical_id(self.body_id, label="body_id")
        if self.body_type not in BODY_TYPES:
            raise ModelValidationError(f"unsupported body_type {self.body_type!r}")
        if self.status not in BODY_STATUSES:
            raise ModelValidationError(f"unsupported body status {self.status!r}")
        if (
            not isinstance(self.official_legal_type, str)
            or not self.official_legal_type.strip()
        ):
            raise ModelValidationError("official_legal_type is required")
        if self.government_tier not in GOVERNMENT_TIERS:
            raise ModelValidationError(
                f"unsupported government_tier {self.government_tier!r}"
            )
        if (
            self.government_tier
            not in ALLOWED_GOVERNMENT_TIERS_BY_BODY_TYPE[self.body_type]
        ):
            raise ModelValidationError(
                f"government_tier {self.government_tier!r} is incompatible "
                f"with body_type {self.body_type!r}"
            )
        if not self.official_names:
            raise ModelValidationError("at least one official name is required")
        language_tags: set[str] = set()
        for language_tag, official_name in self.official_names:
            require_bcp47_tag(language_tag, label="official name language tag")
            if language_tag in language_tags:
                raise ModelValidationError(
                    f"duplicate official name language tag {language_tag!r}"
                )
            if not isinstance(official_name, str) or not official_name.strip():
                raise ModelValidationError("official names must be non-empty strings")
            language_tags.add(language_tag)
        if (
            self.province_territory_iso is not None
            and self.province_territory_iso not in PROVINCE_TERRITORY_ISO_CODES
        ):
            raise ModelValidationError("province_territory_iso is not a Canadian code")
        if self.body_type == "federal-government":
            if self.province_territory_iso is not None:
                raise ModelValidationError(
                    "federal-government must be Canada-scoped with no "
                    "province_territory_iso"
                )
        elif self.province_territory_iso is None:
            raise ModelValidationError(
                "a non-federal governing body must declare province_territory_iso"
            )
        if not self.official_url.startswith("https://"):
            raise ModelValidationError("official_url must use HTTPS")
        if not self.external_ids:
            raise ModelValidationError("at least one official external identifier is required")
        namespaces: set[str] = set()
        for namespace, value in self.external_ids:
            require_source_id(namespace)
            if not value:
                raise ModelValidationError("external identifier value is required")
            if namespace in namespaces:
                raise ModelValidationError(f"duplicate external identifier namespace {namespace!r}")
            namespaces.add(namespace)
        for geography_id in self.geography_ids:
            require_canonical_id(geography_id, label="geography_id")
        if len(self.geography_ids) != len(set(self.geography_ids)):
            raise ModelValidationError("governing body geography_ids must not contain duplicates")
        if self.body_type != "federal-government" and not self.geography_ids:
            raise ModelValidationError(
                "a non-federal governing body requires at least one exact "
                "geography crosswalk"
            )
        if len(self.parent_body_ids) != len(set(self.parent_body_ids)):
            raise ModelValidationError(
                "governing body parent_body_ids must not contain duplicates"
            )
        for parent_body_id in self.parent_body_ids:
            require_canonical_id(parent_body_id, label="parent_body_id")
            if parent_body_id == self.body_id:
                raise ModelValidationError("governing body cannot be its own parent")
        if self.government_tier == "lower-tier" and not self.parent_body_ids:
            raise ModelValidationError(
                "lower-tier governing body requires at least one exact parent body"
            )
        if self.government_tier != "lower-tier" and self.parent_body_ids:
            raise ModelValidationError(
                "parent_body_ids are reserved for lower-tier municipal bodies"
            )
        parsed_dates: dict[str, date] = {}
        for label, value in (
            ("effective_from", self.effective_from),
            ("effective_to", self.effective_to),
        ):
            if value is None:
                continue
            if not isinstance(value, str):
                raise ModelValidationError(f"{label} must be an ISO date or null")
            try:
                parsed_dates[label] = date.fromisoformat(value)
            except ValueError as exc:
                raise ModelValidationError(
                    f"{label} must be an ISO date in YYYY-MM-DD form"
                ) from exc
        if (
            "effective_from" in parsed_dates
            and "effective_to" in parsed_dates
            and parsed_dates["effective_to"] < parsed_dates["effective_from"]
        ):
            raise ModelValidationError(
                "effective_to cannot be earlier than effective_from"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.body_id,
            "kind": "governing-body",
            "bodyType": self.body_type,
            "status": self.status,
            "officialNames": dict(sorted(self.official_names)),
            "provinceTerritory": self.province_territory_iso,
            "officialUrl": self.official_url,
            "externalIds": [
                {"namespace": namespace, "value": value}
                for namespace, value in sorted(self.external_ids)
            ],
            "governsGeographyIds": sorted(self.geography_ids),
            "officialLegalType": self.official_legal_type,
            "governmentTier": self.government_tier,
            "parentBodyIds": sorted(self.parent_body_ids),
            "effectiveFrom": self.effective_from,
            "effectiveTo": self.effective_to,
            "provenance": self.provenance.to_dict(),
        }
