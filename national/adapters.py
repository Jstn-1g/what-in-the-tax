"""Offline adapters from locked official payloads to normalized records."""

from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass
from typing import Any, Protocol

from .models import (
    GoverningBodyRecord,
    GeographyRecord,
    ModelValidationError,
    PROVINCE_TERRITORY_ISO_BY_SGC,
    ProvenanceRef,
    SourceSnapshot,
)


class AdapterError(ValueError):
    """An official payload could not be normalized without guessing."""


@dataclass(frozen=True, slots=True)
class AdapterResult:
    geographies: tuple[GeographyRecord, ...] = ()
    governing_bodies: tuple[GoverningBodyRecord, ...] = ()
    deterministic_gaps: tuple[dict[str, Any], ...] = ()


class ProviderAdapter(Protocol):
    adapter_id: str
    adapter_version: str

    def parse(self, payload: bytes, snapshot: SourceSnapshot) -> AdapterResult:
        """Parse a locked source payload without network access."""


def _decode_utf8_sig(payload: bytes) -> str:
    try:
        return payload.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise AdapterError("official payload must be UTF-8 or UTF-8 with BOM") from exc


def _decode_statcan_sgc(payload: bytes) -> str:
    """Decode the published SGC CSV, which is currently Windows-1252."""

    try:
        return payload.decode("utf-8-sig")
    except UnicodeDecodeError:
        # This fallback is adapter-specific, not a permissive global guess.
        # The locked official 2021 English CSV contains cp1252 accents.
        return payload.decode("cp1252")


class StatCanSgcStructureCsvAdapter:
    """Parse Statistics Canada's SGC 2021 classification structure CSV.

    The classification gives a complete national geography spine, but CSDs
    remain geography records until an administrative directory confirms the
    corresponding governing body.
    """

    adapter_id = "statcan-sgc-structure-csv"
    adapter_version = "1.0.0"
    REQUIRED_COLUMNS = ("Level", "Hierarchical structure", "Code", "Class title")
    LEVELS = {
        "1": "region",
        "2": "province-territory",
        "3": "census-division",
        "4": "census-subdivision",
    }

    def __init__(self, *, classification_year: str = "2021") -> None:
        if not classification_year.isdigit() or len(classification_year) != 4:
            raise AdapterError("classification_year must be four digits")
        self.classification_year = classification_year

    def parse(self, payload: bytes, snapshot: SourceSnapshot) -> AdapterResult:
        reader = csv.DictReader(io.StringIO(_decode_statcan_sgc(payload), newline=""))
        if reader.fieldnames != list(self.REQUIRED_COLUMNS):
            raise AdapterError(
                "unexpected SGC columns; expected exactly "
                + ", ".join(self.REQUIRED_COLUMNS)
            )

        geographies: list[GeographyRecord] = []
        seen: set[str] = set()
        for line_number, row in enumerate(reader, start=2):
            raw_level = (row.get("Level") or "").strip()
            level = self.LEVELS.get(raw_level)
            code = (row.get("Code") or "").strip()
            name = (row.get("Class title") or "").strip()
            hierarchy = (row.get("Hierarchical structure") or "").strip()
            if level is None:
                raise AdapterError(f"line {line_number}: unsupported SGC level {raw_level!r}")
            expected_hierarchy = {
                "region": "Geographical region of Canada",
                "province-territory": "Province and territory",
                "census-division": "Census division",
                "census-subdivision": "Census subdivision",
            }[level]
            if hierarchy != expected_hierarchy:
                raise AdapterError(
                    f"line {line_number}: hierarchy {hierarchy!r} does not match level {raw_level}"
                )

            geography_id = f"ca:sgc:{self.classification_year}:{level}:{code}"
            if geography_id in seen:
                raise AdapterError(f"line {line_number}: duplicate SGC code {code!r}")
            seen.add(geography_id)

            parent_code: str | None
            parent_level: str | None
            if level == "region":
                parent_code, parent_level = None, None
            elif level == "province-territory":
                parent_code, parent_level = code[:1], "region"
            elif level == "census-division":
                parent_code, parent_level = code[:2], "province-territory"
            else:
                parent_code, parent_level = code[:4], "census-division"
            parent_id = (
                f"ca:sgc:{self.classification_year}:{parent_level}:{parent_code}"
                if parent_code is not None
                else None
            )
            pt_code = (
                code
                if level == "province-territory"
                else code[:2] if level in {"census-division", "census-subdivision"} else None
            )
            provenance = ProvenanceRef(
                source_id=snapshot.source_id,
                snapshot_sha256=snapshot.sha256,
                record_key=f"line:{line_number}:code:{code}",
                source_fields=self.REQUIRED_COLUMNS,
                transform="exact CSV fields; parent derived from documented SGC code prefixes",
                adapter_id=self.adapter_id,
                adapter_version=self.adapter_version,
            )
            try:
                record = GeographyRecord(
                    geography_id=geography_id,
                    level=level,
                    sgc_code=code,
                    name_en=name,
                    parent_id=parent_id,
                    province_territory_code=pt_code,
                    province_territory_iso=(
                        PROVINCE_TERRITORY_ISO_BY_SGC.get(pt_code)
                        if pt_code is not None
                        else None
                    ),
                    provenance=provenance,
                )
            except ModelValidationError as exc:
                raise AdapterError(f"line {line_number}: {exc}") from exc
            geographies.append(record)

        if not geographies:
            raise AdapterError("SGC payload contains no records")
        known_ids = {record.geography_id for record in geographies}
        for record in geographies:
            if record.parent_id is not None and record.parent_id not in known_ids:
                raise AdapterError(
                    f"{record.geography_id}: parent {record.parent_id} is absent"
                )
        return AdapterResult(geographies=tuple(geographies))


class CanonicalDirectoryJsonAdapter:
    """Normalize one already-mapped official administrative directory.

    Province-specific adapters should convert source fields into this small
    canonical contract. Records must carry an official ID and exact SGC
    geography IDs when a crosswalk exists; name-only/fuzzy matching is refused.
    """

    adapter_id = "canonical-government-directory-json"
    adapter_version = "2.0.0"

    def parse(self, payload: bytes, snapshot: SourceSnapshot) -> AdapterResult:
        try:
            document = json.loads(_decode_utf8_sig(payload))
        except json.JSONDecodeError as exc:
            raise AdapterError(f"directory JSON is invalid: {exc.msg}") from exc
        if not isinstance(document, dict) or not isinstance(document.get("records"), list):
            raise AdapterError("directory JSON must contain a records array")

        records: list[GoverningBodyRecord] = []
        seen: set[str] = set()
        for index, raw in enumerate(document["records"]):
            label = f"records[{index}]"
            if not isinstance(raw, dict):
                raise AdapterError(f"{label} must be an object")
            required = {
                "id",
                "bodyType",
                "status",
                "officialNames",
                "officialUrl",
                "externalIds",
                "governsGeographyIds",
            }
            missing = sorted(required - raw.keys())
            if missing:
                raise AdapterError(f"{label} missing fields: {', '.join(missing)}")
            body_id = raw["id"]
            if not isinstance(body_id, str):
                raise AdapterError(f"{label}.id must be a string")
            if body_id in seen:
                raise AdapterError(f"{label}: duplicate body id {body_id!r}")
            seen.add(body_id)
            body_type = raw["bodyType"]
            if not isinstance(body_type, str):
                raise AdapterError(f"{label}.bodyType must be a string")
            province_territory = raw.get("provinceTerritory")
            if body_type == "federal-government":
                if province_territory is not None:
                    raise AdapterError(
                        f"{label}: federal-government must be Canada-scoped with "
                        "provinceTerritory=null"
                    )
            elif not isinstance(province_territory, str) or not province_territory:
                raise AdapterError(
                    f"{label}: non-federal governing body must declare "
                    "provinceTerritory"
                )
            external = raw["externalIds"]
            geography_ids = raw["governsGeographyIds"]
            official_names = raw["officialNames"]
            if not isinstance(external, dict) or not all(
                isinstance(key, str) and isinstance(value, str)
                for key, value in external.items()
            ):
                raise AdapterError(f"{label}.externalIds must be a string mapping")
            if not isinstance(official_names, dict) or not official_names or not all(
                isinstance(key, str) and isinstance(value, str)
                for key, value in official_names.items()
            ):
                raise AdapterError(
                    f"{label}.officialNames must be a non-empty language-tag mapping"
                )
            if not isinstance(geography_ids, list) or not all(
                isinstance(value, str) for value in geography_ids
            ):
                raise AdapterError(f"{label}.governsGeographyIds must be a string array")
            if body_type != "federal-government" and not geography_ids:
                raise AdapterError(
                    f"{label}.governsGeographyIds must contain at least one exact "
                    "geography crosswalk for a non-federal governing body"
                )
            source_fields = raw.get(
                "sourceFields",
                [
                    "id",
                    "bodyType",
                    "status",
                    "officialNames",
                    "officialUrl",
                    "externalIds",
                    "governsGeographyIds",
                ],
            )
            if not isinstance(source_fields, list) or not all(
                isinstance(value, str) and value for value in source_fields
            ):
                raise AdapterError(f"{label}.sourceFields must be a non-empty string array")

            provenance = ProvenanceRef(
                source_id=snapshot.source_id,
                snapshot_sha256=snapshot.sha256,
                record_key=str(raw.get("sourceRecordKey") or f"records[{index}]"),
                source_fields=tuple(source_fields),
                transform=str(raw.get("transform") or "exact canonical field mapping"),
                adapter_id=self.adapter_id,
                adapter_version=self.adapter_version,
            )
            try:
                record = GoverningBodyRecord(
                    body_id=body_id,
                    body_type=body_type,
                    status=raw["status"],
                    official_names=tuple(sorted(official_names.items())),
                    province_territory_iso=province_territory,
                    official_url=raw["officialUrl"],
                    external_ids=tuple(sorted(external.items())),
                    geography_ids=tuple(sorted(geography_ids)),
                    provenance=provenance,
                )
            except (ModelValidationError, TypeError, AttributeError) as exc:
                raise AdapterError(f"{label}: {exc}") from exc
            records.append(record)
        return AdapterResult(governing_bodies=tuple(records))
