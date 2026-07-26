from __future__ import annotations

import copy
import hashlib
import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

from national.adapters import (
    CanonicalDirectoryJsonAdapter,
    StatCanSgcStructureCsvAdapter,
)
from national.models import SourceSnapshot
from national.registry import NationalRegistryBuilder


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "national" / "schemas" / "registry.schema.json"
SGC_SAMPLE = b"""Level,Hierarchical structure,Code,Class title
1,Geographical region of Canada,3,Ontario
2,Province and territory,35,Ontario
3,Census division,3518,Durham
4,Census subdivision,3518013,Oshawa
"""
DIRECTORY_DOCUMENT = {
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
        }
    ]
}
DIRECTORY_PAYLOAD = json.dumps(DIRECTORY_DOCUMENT).encode("utf-8")


def snapshot(payload: bytes, source_id: str, media_type: str) -> SourceSnapshot:
    return SourceSnapshot(
        source_id=source_id,
        sha256=hashlib.sha256(payload).hexdigest(),
        byte_length=len(payload),
        media_type=media_type,
        request_url=f"https://government.example/{source_id}",
    )


class NationalRegistrySchemaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(cls.schema)
        cls.validator = Draft202012Validator(cls.schema)

        sgc_snapshot = snapshot(
            SGC_SAMPLE,
            "statcan-sgc-2021-structure-en",
            "text/csv",
        )
        directory_snapshot = snapshot(
            DIRECTORY_PAYLOAD,
            "ontario-municipal-directory",
            "application/json",
        )
        geographies = StatCanSgcStructureCsvAdapter().parse(
            SGC_SAMPLE,
            sgc_snapshot,
        ).geographies
        bodies = CanonicalDirectoryJsonAdapter().parse(
            DIRECTORY_PAYLOAD,
            directory_snapshot,
        ).governing_bodies
        catalog = {
            "sources": [
                {
                    "sourceId": sgc_snapshot.source_id,
                    "publisher": "Statistics Canada",
                    "jurisdiction": "CA",
                    "coverageLayer": "national-geography-baseline",
                    "classificationVersion": "2021",
                    "requestUrl": sgc_snapshot.request_url,
                    "mediaType": sgc_snapshot.media_type,
                    "adapterId": "statcan-sgc-structure-csv",
                    "adapterVersion": "1.0.0",
                    "runtimeNetworkRequired": False,
                    "approvedSha256": sgc_snapshot.sha256,
                    "licenseStatus": "open-licence-confirmed",
                    "licenseUrl": "https://government.example/open-licence",
                    "reuseReviewRequired": False,
                },
                {
                    "sourceId": directory_snapshot.source_id,
                    "publisher": "Government of Ontario",
                    "jurisdiction": "ON",
                    "coverageLayer": "municipal-regional-governments",
                    "requestUrl": directory_snapshot.request_url,
                    "mediaType": directory_snapshot.media_type,
                    "adapterId": "canonical-government-directory-json",
                    "adapterVersion": "2.0.0",
                    "runtimeNetworkRequired": False,
                    "approvedSha256": directory_snapshot.sha256,
                    "licenseStatus": "open-government-licence-confirmed",
                    "licenseUrl": "https://government.example/open-licence",
                    "reuseReviewRequired": False,
                },
            ]
        }
        coverage = {
            "classificationVersion": "2021",
            "expectedGeographyCounts": {
                "region": 1,
                "province-territory": 1,
                "census-division": 1,
                "census-subdivision": 1,
            },
            "requiredLayers": [
                "national-geography-baseline",
                "municipal-regional-governments",
            ],
            "jurisdictions": [
                {
                    "code": "ON",
                    "name": "Ontario",
                    "expectedCensusSubdivisionCount": 1,
                    "layers": {
                        "national-geography-baseline": {
                            "status": "complete",
                            "sourceIds": [sgc_snapshot.source_id],
                        },
                        "municipal-regional-governments": {
                            "status": "partial",
                            "sourceIds": [directory_snapshot.source_id],
                        },
                    },
                }
            ],
        }
        cls.registry = NationalRegistryBuilder(
            classification_version="2021",
            source_catalog=catalog,
            coverage_plan=coverage,
            scope="test",
        ).build(
            geographies=geographies,
            governing_bodies=bodies,
            snapshots=[sgc_snapshot, directory_snapshot],
        )

    def assertSchemaInvalid(self, instance: dict) -> None:
        self.assertTrue(
            list(self.validator.iter_errors(instance)),
            "expected registry schema validation to fail",
        )

    def test_builder_output_matches_hardened_schema(self) -> None:
        self.validator.validate(self.registry)

    def test_zero_row_empty_coverage_and_counts_document_is_rejected(self) -> None:
        empty = {
            "schemaVersion": "auditback-national-registry-1.0.0",
            "country": "CA",
            "buildScope": "test",
            "classification": {
                "system": "Statistics Canada Standard Geographical Classification",
                "version": "2021",
            },
            "method": {
                "runtimeNetworkRequired": False,
                "runtimeAiRequired": False,
                "identityMerge": "exact-official-identifiers-only",
                "statisticalAreasAreGovernments": False,
            },
            "sourceSnapshots": [],
            "geographies": [],
            "governingBodies": [],
            "coverage": {},
            "counts": {},
            "registryCanonicalSha256": "0" * 64,
        }
        self.assertSchemaInvalid(empty)

    def test_integrity_critical_nested_shapes_are_constrained(self) -> None:
        mutations = []
        empty_coverage = copy.deepcopy(self.registry)
        empty_coverage["coverage"] = {}
        mutations.append(empty_coverage)
        empty_counts = copy.deepcopy(self.registry)
        empty_counts["counts"] = {}
        mutations.append(empty_counts)
        bad_codes = copy.deepcopy(self.registry)
        bad_codes["geographies"][0]["codes"] = {}
        mutations.append(bad_codes)
        no_names = copy.deepcopy(self.registry)
        no_names["governingBodies"][0]["officialNames"] = {}
        mutations.append(no_names)
        invalid_name_tag = copy.deepcopy(self.registry)
        invalid_name_tag["governingBodies"][0]["officialNames"] = {
            "name": "Unlabelled translation"
        }
        mutations.append(invalid_name_tag)
        no_external_ids = copy.deepcopy(self.registry)
        no_external_ids["governingBodies"][0]["externalIds"] = []
        mutations.append(no_external_ids)

        for index, mutation in enumerate(mutations):
            with self.subTest(mutation=index):
                self.assertSchemaInvalid(mutation)

    def test_production_schema_refuses_reduced_jurisdiction_scope(self) -> None:
        changed = copy.deepcopy(self.registry)
        changed["buildScope"] = "production"
        self.assertSchemaInvalid(changed)


if __name__ == "__main__":
    unittest.main()
