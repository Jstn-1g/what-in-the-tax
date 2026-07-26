from __future__ import annotations

import hashlib
import json
import unittest

from national.adapters import (
    AdapterError,
    CanonicalDirectoryJsonAdapter,
    StatCanSgcStructureCsvAdapter,
)
from national.models import SourceSnapshot


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
        payload = json.dumps(document).encode()
        result = CanonicalDirectoryJsonAdapter().parse(
            payload,
            snapshot(payload, "ontario-municipal-directory"),
        )

        self.assertEqual(1, len(result.governing_bodies))
        body = result.governing_bodies[0]
        self.assertEqual("municipal-government", body.body_type)
        self.assertEqual((("ontario-mah", "1813"),), body.external_ids)
        self.assertEqual((("en-CA", "City of Oshawa"),), body.official_names)

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
                payload = json.dumps(document).encode("utf-8")
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
        payload = json.dumps(document).encode("utf-8")
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
        payload = json.dumps(document).encode("utf-8")
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
                payload = json.dumps(document).encode("utf-8")
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
        payload = json.dumps(document).encode()
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
        payload = json.dumps(document).encode("utf-8")
        with self.assertRaises(AdapterError):
            CanonicalDirectoryJsonAdapter().parse(
                payload,
                snapshot(payload, "ontario-municipal-directory"),
            )


if __name__ == "__main__":
    unittest.main()
