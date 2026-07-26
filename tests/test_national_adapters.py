from __future__ import annotations

import hashlib
import json
import unittest
from dataclasses import replace

from national.adapters import (
    AdapterError,
    CanonicalDirectoryJsonAdapter,
    StatCanSgcStructureCsvAdapter,
)
from national.models import (
    ALLOWED_GOVERNMENT_TIERS_BY_BODY_TYPE,
    GOVERNMENT_TIERS,
    GoverningBodyRecord,
    ModelValidationError,
    ProvenanceRef,
    SourceSnapshot,
)


SGC_SAMPLE = b"""Level,Hierarchical structure,Code,Class title
1,Geographical region of Canada,3,Ontario
2,Province and territory,35,Ontario
3,Census division,3518,Durham
4,Census subdivision,3518013,Oshawa
"""


def snapshot(payload: bytes, source_id: str = "statcan-sgc-2021-structure-en") -> SourceSnapshot:
    return SourceSnapshot(
        source_id=source_id,
        sha256=hashlib.sha256(payload).hexdigest(),
        byte_length=len(payload),
        media_type="text/csv",
        request_url="https://www.statcan.gc.ca/example.csv",
    )


def canonical_payload(document: dict) -> bytes:
    document.setdefault(
        "schemaVersion",
        "auditback-canonical-government-directory-3.0.0",
    )
    for record in document.get("records", []):
        body_type = record.get("bodyType")
        record.setdefault("officialLegalType", "Federal government" if body_type == "federal-government" else "Municipality")
        record.setdefault("governmentTier", "national" if body_type == "federal-government" else "single-tier")
        record.setdefault("parentBodyIds", [])
        record.setdefault("effectiveFrom", None)
        record.setdefault("effectiveTo", None)
    return json.dumps(document).encode("utf-8")


class GoverningBodyModelTests(unittest.TestCase):
    def setUp(self) -> None:
        self.body = GoverningBodyRecord(
            body_id="ca:gov:on:municipal:3518013",
            body_type="municipal-government",
            status="active",
            official_names=(("en-CA", "City of Oshawa"),),
            province_territory_iso="ON",
            official_url="https://www.oshawa.ca/",
            external_ids=(("ontario-mah", "1813"),),
            geography_ids=("ca:sgc:2021:census-subdivision:3518013",),
            official_legal_type="City",
            government_tier="single-tier",
            parent_body_ids=(),
            effective_from=None,
            effective_to=None,
            provenance=ProvenanceRef(
                source_id="ontario-municipal-directory",
                snapshot_sha256="0" * 64,
                record_key="MAH:1813",
                source_fields=("bodyType", "governmentTier"),
                transform="exact canonical field mapping",
                adapter_id="canonical-government-directory-json",
                adapter_version="3.0.0",
            ),
        )

    def test_model_rejects_false_scope_and_crosswalk_identities(self) -> None:
        with self.assertRaisesRegex(
            ModelValidationError,
            "at least one exact geography",
        ):
            replace(self.body, geography_ids=())

        with self.assertRaisesRegex(ModelValidationError, "Canada-scoped"):
            replace(
                self.body,
                body_type="federal-government",
                government_tier="national",
                geography_ids=(),
            )

    def test_model_closes_the_body_type_tier_matrix(self) -> None:
        for body_type, allowed_tiers in sorted(
            ALLOWED_GOVERNMENT_TIERS_BY_BODY_TYPE.items()
        ):
            for tier in sorted(GOVERNMENT_TIERS):
                kwargs = {
                    "body_type": body_type,
                    "government_tier": tier,
                    "province_territory_iso": (
                        None if body_type == "federal-government" else "ON"
                    ),
                    "geography_ids": (
                        ()
                        if body_type == "federal-government"
                        else self.body.geography_ids
                    ),
                    "parent_body_ids": (
                        ("ca:gov:on:regional:parent",)
                        if tier == "lower-tier"
                        else ()
                    ),
                }
                with self.subTest(body_type=body_type, tier=tier):
                    if tier in allowed_tiers:
                        replace(self.body, **kwargs)
                    else:
                        with self.assertRaisesRegex(
                            ModelValidationError,
                            "incompatible",
                        ):
                            replace(self.body, **kwargs)

    def test_model_reserves_parents_for_lower_tier_municipalities(self) -> None:
        with self.assertRaisesRegex(ModelValidationError, "requires at least one"):
            replace(self.body, government_tier="lower-tier")

        with self.assertRaisesRegex(ModelValidationError, "reserved for lower-tier"):
            replace(
                self.body,
                parent_body_ids=("ca:gov:on:regional:parent",),
            )


class StatCanSgcAdapterTests(unittest.TestCase):
    def test_builds_exact_hierarchy_without_promoting_csd_to_government(self) -> None:
        result = StatCanSgcStructureCsvAdapter().parse(
            SGC_SAMPLE,
            snapshot(SGC_SAMPLE),
        )

        self.assertEqual(4, len(result.geographies))
        oshawa = result.geographies[-1]
        self.assertEqual("3518013", oshawa.sgc_code)
        self.assertEqual("ON", oshawa.province_territory_iso)
        self.assertEqual(
            "ca:sgc:2021:census-division:3518",
            oshawa.parent_id,
        )
        self.assertEqual(
            "requires-official-directory-match",
            oshawa.to_dict()["governingBodyVerification"],
        )
        self.assertEqual((), result.governing_bodies)

    def test_preserves_leading_zeroes(self) -> None:
        payload = b"""Level,Hierarchical structure,Code,Class title
1,Geographical region of Canada,1,Atlantic
2,Province and territory,10,Newfoundland and Labrador
3,Census division,1001,Division No. 1
4,Census subdivision,1001101,"Division No. 1, Subd. V"
"""
        result = StatCanSgcStructureCsvAdapter().parse(payload, snapshot(payload))
        self.assertEqual("1001101", result.geographies[-1].sgc_code)

    def test_accepts_official_statcan_windows_1252_accents(self) -> None:
        payload = """Level,Hierarchical structure,Code,Class title
1,Geographical region of Canada,2,Quebec
2,Province and territory,24,Quebec
3,Census division,2401,Les \u00celes-de-la-Madeleine
4,Census subdivision,2401023,L'\u00cele-d'Entr\u00e9e
""".encode("cp1252")
        result = StatCanSgcStructureCsvAdapter().parse(payload, snapshot(payload))
        self.assertEqual("L'\u00cele-d'Entr\u00e9e", result.geographies[-1].name_en)

    def test_schema_drift_fails_closed(self) -> None:
        changed = SGC_SAMPLE.replace(b"Class title", b"Name")
        with self.assertRaisesRegex(AdapterError, "unexpected SGC columns"):
            StatCanSgcStructureCsvAdapter().parse(changed, snapshot(changed))

    def test_missing_parent_fails_closed(self) -> None:
        missing = b"""Level,Hierarchical structure,Code,Class title
4,Census subdivision,3518013,Oshawa
"""
        with self.assertRaisesRegex(AdapterError, "parent .* is absent"):
            StatCanSgcStructureCsvAdapter().parse(missing, snapshot(missing))


class CanonicalDirectoryAdapterTests(unittest.TestCase):
    def test_candidate_only_directory_cannot_be_ingested(self) -> None:
        payload = json.dumps(
            {
                "candidateOnly": True,
                "records": [],
            }
        ).encode("utf-8")
        with self.assertRaisesRegex(AdapterError, "candidate-only"):
            CanonicalDirectoryJsonAdapter().parse(
                payload,
                snapshot(payload, "ontario-municipal-directory"),
            )

    def test_normalizes_official_body_with_exact_crosswalk(self) -> None:
        document = {
            "records": [
                {
                    "id": "ca:gov:on:municipal:3518013",
                    "bodyType": "municipal-government",
                    "status": "active",
                    "officialNames": {"en-CA": "City of Oshawa"},
                    "provinceTerritory": "ON",
                    "officialUrl": "https://www.oshawa.ca/",
                    "externalIds": {"ontario-mah": "1813"},
                    "governsGeographyIds": [
                        "ca:sgc:2021:census-subdivision:3518013"
                    ],
                    "sourceRecordKey": "MAH:1813",
                }
            ]
        }
        payload = canonical_payload(document)
        result = CanonicalDirectoryJsonAdapter().parse(
            payload,
            snapshot(payload, "ontario-municipal-directory"),
        )

        self.assertEqual(1, len(result.governing_bodies))
        body = result.governing_bodies[0]
        self.assertEqual("municipal-government", body.body_type)
        self.assertEqual((("ontario-mah", "1813"),), body.external_ids)
        self.assertEqual((("en-CA", "City of Oshawa"),), body.official_names)
        self.assertEqual("Municipality", body.official_legal_type)
        self.assertEqual("single-tier", body.government_tier)
        self.assertEqual((), body.parent_body_ids)

    def test_requires_legal_type_tier_relationship_and_effective_dates(self) -> None:
        record = {
            "id": "ca:gov:on:municipal:3518013",
            "bodyType": "municipal-government",
            "status": "active",
            "officialNames": {"en-CA": "City of Oshawa"},
            "provinceTerritory": "ON",
            "officialUrl": "https://www.oshawa.ca/",
            "externalIds": {"ontario-mah": "1813"},
            "governsGeographyIds": [
                "ca:sgc:2021:census-subdivision:3518013"
            ],
        }
        payload = json.dumps(
            {
                "schemaVersion": "auditback-canonical-government-directory-3.0.0",
                "records": [record],
            }
        ).encode("utf-8")
        with self.assertRaisesRegex(AdapterError, "missing fields"):
            CanonicalDirectoryJsonAdapter().parse(
                payload,
                snapshot(payload, "ontario-municipal-directory"),
            )

    def test_accepts_a_single_source_bound_french_or_undetermined_official_name(
        self,
    ) -> None:
        for tag, name in (
            ("fr-CA", "Municipalité de Saint-Exemple"),
            ("und", "Tla'amin Nation"),
            ("iu-Cans-CA", "ᐃᖃᓗᐃᑦ"),
        ):
            with self.subTest(language_tag=tag):
                document = {
                    "records": [
                        {
                            "id": f"ca:gov:qc:municipal:{tag.lower()}",
                            "bodyType": "municipal-government",
                            "status": "active",
                            "officialNames": {tag: name},
                            "provinceTerritory": "QC",
                            "officialUrl": "https://government.example/body",
                            "externalIds": {"official-directory": tag},
                            "governsGeographyIds": [
                                "ca:sgc:2021:census-subdivision:3518013"
                            ],
                        }
                    ]
                }
                payload = canonical_payload(document)
                body = CanonicalDirectoryJsonAdapter().parse(
                    payload,
                    snapshot(payload, "quebec-municipal-directory"),
                ).governing_bodies[0]
                self.assertEqual(((tag, name),), body.official_names)

    def test_non_federal_body_requires_an_exact_geography_crosswalk(self) -> None:
        document = {
            "records": [
                {
                    "id": "ca:gov:on:municipal:3518013",
                    "bodyType": "municipal-government",
                    "status": "active",
                    "officialNames": {"en-CA": "City of Oshawa"},
                    "provinceTerritory": "ON",
                    "officialUrl": "https://www.oshawa.ca/",
                    "externalIds": {"ontario-mah": "1813"},
                    "governsGeographyIds": [],
                }
            ]
        }
        payload = canonical_payload(document)
        with self.assertRaisesRegex(AdapterError, "at least one exact geography"):
            CanonicalDirectoryJsonAdapter().parse(
                payload,
                snapshot(payload, "ontario-municipal-directory"),
            )

    def test_federal_body_cannot_claim_a_province_scope(self) -> None:
        document = {
            "records": [
                {
                    "id": "ca:gov:federal:test",
                    "bodyType": "federal-government",
                    "status": "active",
                    "officialNames": {"en-CA": "Government of Canada"},
                    "provinceTerritory": "ON",
                    "officialUrl": "https://www.canada.ca/",
                    "externalIds": {"canada-directory": "federal"},
                    "governsGeographyIds": [],
                }
            ]
        }
        payload = canonical_payload(document)
        with self.assertRaisesRegex(AdapterError, "Canada-scoped"):
            CanonicalDirectoryJsonAdapter().parse(
                payload,
                snapshot(payload, "ontario-municipal-directory"),
            )

    def test_rejects_unlabelled_or_invalid_language_names(self) -> None:
        for official_names in (
            {},
            {"name": "Invented English translation"},
            {"en_CA": "Invalid separator"},
        ):
            with self.subTest(official_names=official_names):
                document = {
                    "records": [
                        {
                            "id": "ca:gov:qc:municipal:test",
                            "bodyType": "municipal-government",
                            "status": "active",
                            "officialNames": official_names,
                            "provinceTerritory": "QC",
                            "officialUrl": "https://government.example/body",
                            "externalIds": {"official-directory": "1"},
                            "governsGeographyIds": [],
                        }
                    ]
                }
                payload = canonical_payload(document)
                with self.assertRaises(AdapterError):
                    CanonicalDirectoryJsonAdapter().parse(
                        payload,
                        snapshot(payload, "quebec-municipal-directory"),
                    )

    def test_body_requires_an_official_identifier(self) -> None:
        document = {
            "records": [
                {
                    "id": "ca:gov:on:municipal:3518013",
                    "bodyType": "municipal-government",
                    "status": "active",
                    "officialNames": {"en-CA": "City of Oshawa"},
                    "provinceTerritory": "ON",
                    "officialUrl": "https://www.oshawa.ca/",
                    "externalIds": {},
                    "governsGeographyIds": [
                        "ca:sgc:2021:census-subdivision:3518013"
                    ],
                }
            ]
        }
        payload = canonical_payload(document)
        with self.assertRaisesRegex(AdapterError, "official external identifier"):
            CanonicalDirectoryJsonAdapter().parse(
                payload,
                snapshot(payload, "ontario-municipal-directory"),
            )

    def test_malformed_canonical_types_are_wrapped_as_adapter_errors(self) -> None:
        document = {
            "records": [
                {
                    "id": "ca:gov:on:municipal:3518013",
                    "bodyType": ["municipal-government"],
                    "status": "active",
                    "officialNames": {"en-CA": "City of Oshawa"},
                    "provinceTerritory": "ON",
                    "officialUrl": ["https://www.oshawa.ca/"],
                    "externalIds": {"ontario-mah": "1813"},
                    "governsGeographyIds": [],
                }
            ]
        }
        payload = canonical_payload(document)
        with self.assertRaises(AdapterError):
            CanonicalDirectoryJsonAdapter().parse(
                payload,
                snapshot(payload, "ontario-municipal-directory"),
            )


if __name__ == "__main__":
    unittest.main()
