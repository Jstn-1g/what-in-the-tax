from __future__ import annotations

import hashlib
import json
import unittest
from dataclasses import replace

from national.adapters import (
    CanonicalDirectoryJsonAdapter,
    StatCanSgcStructureCsvAdapter,
)
from national.models import SourceSnapshot
from national.models import PROVINCE_TERRITORY_ISO_CODES
from national.registry import (
    CANONICAL_REQUIRED_LAYERS,
    NationalRegistryBuilder,
    RegistryError,
)


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
DIRECTORY_PAYLOAD = json.dumps(DIRECTORY_DOCUMENT).encode()


def make_snapshot(payload: bytes, source_id: str, media_type: str) -> SourceSnapshot:
    return SourceSnapshot(
        source_id=source_id,
        sha256=hashlib.sha256(payload).hexdigest(),
        byte_length=len(payload),
        media_type=media_type,
        request_url=f"https://government.example/{source_id}",
    )


def coverage(
    *,
    baseline_status: str = "complete",
    baseline_sources: list[str] | None = None,
    jurisdiction: str = "ON",
) -> dict:
    return {
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
                "code": jurisdiction,
                "name": "Ontario" if jurisdiction == "ON" else jurisdiction,
                "expectedCensusSubdivisionCount": 1,
                "layers": {
                    "national-geography-baseline": {
                        "status": baseline_status,
                        "sourceIds": (
                            ["statcan-sgc-2021-structure-en"]
                            if baseline_sources is None
                            else baseline_sources
                        ),
                    },
                    "municipal-regional-governments": {
                        "status": "adapter-needed",
                        "sourceIds": [],
                    },
                },
            }
        ],
    }


def source_catalog() -> dict:
    return {
        "sources": [
            {
                "sourceId": "statcan-sgc-2021-structure-en",
                "publisher": "Statistics Canada",
                "jurisdiction": "CA",
                "coverageLayer": "national-geography-baseline",
                "classificationVersion": "2021",
                "requestUrl": (
                    "https://government.example/"
                    "statcan-sgc-2021-structure-en"
                ),
                "mediaType": "text/csv",
                "adapterId": "statcan-sgc-structure-csv",
                "adapterVersion": "1.0.0",
                "runtimeNetworkRequired": False,
                "approvedSha256": hashlib.sha256(SGC_SAMPLE).hexdigest(),
                "licenseStatus": "open-licence-confirmed",
                "licenseUrl": "https://government.example/open-licence",
                "reuseReviewRequired": False,
            },
            {
                "sourceId": "ontario-municipal-directory",
                "publisher": "Government of Ontario",
                "jurisdiction": "ON",
                "coverageLayer": "municipal-regional-governments",
                "requestUrl": (
                    "https://government.example/"
                    "ontario-municipal-directory"
                ),
                "mediaType": "application/json",
                "adapterId": "canonical-government-directory-json",
                "adapterVersion": "2.0.0",
                "runtimeNetworkRequired": False,
                "approvedSha256": hashlib.sha256(DIRECTORY_PAYLOAD).hexdigest(),
                "licenseStatus": "open-government-licence-confirmed",
                "licenseUrl": "https://government.example/open-licence",
                "reuseReviewRequired": False,
            },
        ]
    }


def production_coverage_without_nunavut() -> dict:
    jurisdictions = []
    for code in sorted(PROVINCE_TERRITORY_ISO_CODES - {"NU"}):
        layers = {
            layer: {
                "status": (
                    "complete"
                    if layer == "national-geography-baseline"
                    else "not-started"
                ),
                "sourceIds": (
                    ["statcan-sgc-2021-structure-en"]
                    if layer == "national-geography-baseline"
                    else []
                ),
            }
            for layer in CANONICAL_REQUIRED_LAYERS
        }
        jurisdictions.append(
            {
                "code": code,
                "name": code,
                "expectedCensusSubdivisionCount": 1 if code == "ON" else 0,
                "layers": layers,
            }
        )
    return {
        "classificationVersion": "2021",
        "expectedGeographyCounts": {
            "region": 1,
            "province-territory": 1,
            "census-division": 1,
            "census-subdivision": 1,
        },
        "requiredLayers": list(CANONICAL_REQUIRED_LAYERS),
        "jurisdictions": jurisdictions,
    }


def production_coverage() -> dict:
    plan = production_coverage_without_nunavut()
    plan["jurisdictions"].append(
        {
            "code": "NU",
            "name": "Nunavut",
            "expectedCensusSubdivisionCount": 0,
            "layers": {
                layer: {
                    "status": (
                        "complete"
                        if layer == "national-geography-baseline"
                        else "not-started"
                    ),
                    "sourceIds": (
                        ["statcan-sgc-2021-structure-en"]
                        if layer == "national-geography-baseline"
                        else []
                    ),
                }
                for layer in CANONICAL_REQUIRED_LAYERS
            },
        }
    )
    plan["jurisdictions"].sort(key=lambda row: row["code"])
    return plan


class NationalRegistryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.sgc_snapshot = make_snapshot(
            SGC_SAMPLE,
            "statcan-sgc-2021-structure-en",
            "text/csv",
        )
        self.geographies = StatCanSgcStructureCsvAdapter().parse(
            SGC_SAMPLE,
            self.sgc_snapshot,
        ).geographies
        self.directory_snapshot = make_snapshot(
            DIRECTORY_PAYLOAD,
            "ontario-municipal-directory",
            "application/json",
        )
        self.bodies = CanonicalDirectoryJsonAdapter().parse(
            DIRECTORY_PAYLOAD,
            self.directory_snapshot,
        ).governing_bodies

    def test_registry_keeps_geography_and_government_separate(self) -> None:
        registry = NationalRegistryBuilder(
            classification_version="2021",
            source_catalog=source_catalog(),
            coverage_plan=coverage(),
            scope="test",
        ).build(
            geographies=self.geographies,
            governing_bodies=self.bodies,
            snapshots=[self.sgc_snapshot, self.directory_snapshot],
        )

        self.assertEqual(4, registry["counts"]["geographies"])
        self.assertEqual(1, registry["counts"]["governingBodies"])
        self.assertEqual("official-geography", registry["geographies"][-1]["kind"])
        self.assertEqual("governing-body", registry["governingBodies"][0]["kind"])
        self.assertEqual(
            {"en-CA": "City of Oshawa"},
            registry["governingBodies"][0]["officialNames"],
        )
        self.assertNotIn("name", registry["governingBodies"][0])
        self.assertEqual("test", registry["buildScope"])
        self.assertFalse(registry["method"]["statisticalAreasAreGovernments"])
        self.assertEqual(64, len(registry["registryCanonicalSha256"]))

    def test_identical_inputs_produce_identical_registry(self) -> None:
        builder = NationalRegistryBuilder(
            classification_version="2021",
            source_catalog=source_catalog(),
            coverage_plan=coverage(),
            scope="test",
        )
        kwargs = {
            "geographies": self.geographies,
            "governing_bodies": self.bodies,
            "snapshots": [self.sgc_snapshot, self.directory_snapshot],
        }
        self.assertEqual(builder.build(**kwargs), builder.build(**kwargs))

    def test_unknown_crosswalk_fails_instead_of_name_matching(self) -> None:
        body = self.bodies[0]
        changed = replace(
            body,
            geography_ids=("ca:sgc:2021:census-subdivision:3599999",),
        )
        with self.assertRaisesRegex(RegistryError, "unknown exact geography crosswalk"):
            NationalRegistryBuilder(
                classification_version="2021",
                source_catalog=source_catalog(),
                coverage_plan=coverage(),
                scope="test",
            ).build(
                geographies=self.geographies,
                governing_bodies=[changed],
                snapshots=[self.sgc_snapshot, self.directory_snapshot],
            )

    def test_complete_administrative_layer_rejects_an_empty_body_crosswalk(
        self,
    ) -> None:
        changed_coverage = coverage()
        changed_coverage["jurisdictions"][0]["layers"][
            "municipal-regional-governments"
        ] = {
            "status": "complete",
            "sourceIds": ["ontario-municipal-directory"],
            "expectedVerifiedBodyCount": 1,
        }
        body_without_crosswalk = replace(self.bodies[0], geography_ids=())

        with self.assertRaisesRegex(RegistryError, "at least one exact geography"):
            NationalRegistryBuilder(
                classification_version="2021",
                source_catalog=source_catalog(),
                coverage_plan=changed_coverage,
                scope="test",
            ).build(
                geographies=self.geographies,
                governing_bodies=[body_without_crosswalk],
                snapshots=[self.sgc_snapshot, self.directory_snapshot],
            )

    def test_federal_body_cannot_claim_a_province_scope(self) -> None:
        contradictory_body = replace(
            self.bodies[0],
            body_type="federal-government",
            geography_ids=(),
        )
        with self.assertRaisesRegex(RegistryError, "Canada-scoped"):
            NationalRegistryBuilder(
                classification_version="2021",
                source_catalog=source_catalog(),
                coverage_plan=coverage(),
                scope="test",
            ).build(
                geographies=self.geographies,
                governing_bodies=[contradictory_body],
                snapshots=[self.sgc_snapshot, self.directory_snapshot],
            )

    def test_complete_layer_requires_locked_source(self) -> None:
        with self.assertRaisesRegex(RegistryError, "unlocked sources"):
            NationalRegistryBuilder(
                classification_version="2021",
                source_catalog=source_catalog(),
                coverage_plan=coverage(baseline_sources=["missing-official-source"]),
                scope="test",
            ).build(
                geographies=self.geographies,
                governing_bodies=[],
                snapshots=[self.sgc_snapshot],
            )

    def test_snapshot_must_match_catalog_transport_identity(self) -> None:
        changed_catalog = source_catalog()
        changed_catalog["sources"][0]["requestUrl"] = (
            "https://government.example/different-file.csv"
        )
        with self.assertRaisesRegex(RegistryError, "request URL differs"):
            NationalRegistryBuilder(
                classification_version="2021",
                source_catalog=changed_catalog,
                coverage_plan=coverage(),
                scope="test",
            ).build(
                geographies=self.geographies,
                governing_bodies=[],
                snapshots=[self.sgc_snapshot],
            )

    def test_unapproved_source_release_hash_fails_closed(self) -> None:
        second_snapshot = make_snapshot(
            SGC_SAMPLE + b"\n",
            "statcan-sgc-2021-structure-en",
            "text/csv",
        )
        with self.assertRaisesRegex(RegistryError, "not the approved release hash"):
            NationalRegistryBuilder(
                classification_version="2021",
                source_catalog=source_catalog(),
                coverage_plan=coverage(),
                scope="test",
            ).build(
                geographies=self.geographies,
                governing_bodies=[],
                snapshots=[self.sgc_snapshot, second_snapshot],
            )

    def test_classification_version_cannot_relabel_a_2021_source(self) -> None:
        changed_coverage = coverage()
        changed_coverage["classificationVersion"] = "2026"
        with self.assertRaisesRegex(RegistryError, "classificationVersion"):
            NationalRegistryBuilder(
                classification_version="2026",
                source_catalog=source_catalog(),
                coverage_plan=changed_coverage,
                scope="test",
            ).build(
                geographies=self.geographies,
                governing_bodies=[],
                snapshots=[self.sgc_snapshot],
            )

    def test_complete_administrative_layer_requires_reconciled_body_count(self) -> None:
        changed_coverage = coverage()
        changed_coverage["jurisdictions"][0]["layers"][
            "municipal-regional-governments"
        ] = {
            "status": "complete",
            "sourceIds": ["ontario-municipal-directory"],
            "expectedVerifiedBodyCount": 1,
        }
        with self.assertRaisesRegex(RegistryError, "expected 1 verified bodies"):
            NationalRegistryBuilder(
                classification_version="2021",
                source_catalog=source_catalog(),
                coverage_plan=changed_coverage,
                scope="test",
            ).build(
                geographies=self.geographies,
                governing_bodies=[],
                snapshots=[self.sgc_snapshot, self.directory_snapshot],
            )

    def test_record_adapter_version_must_match_source_catalog(self) -> None:
        changed_catalog = source_catalog()
        changed_catalog["sources"][1]["adapterVersion"] = "9.9.9"
        with self.assertRaisesRegex(RegistryError, "adapter version differs"):
            NationalRegistryBuilder(
                classification_version="2021",
                source_catalog=changed_catalog,
                coverage_plan=coverage(),
                scope="test",
            ).build(
                geographies=self.geographies,
                governing_bodies=self.bodies,
                snapshots=[self.sgc_snapshot, self.directory_snapshot],
            )

    def test_body_cannot_crosswalk_to_another_province(self) -> None:
        body = self.bodies[0]
        changed = replace(
            body,
            province_territory_iso="QC",
        )
        with self.assertRaisesRegex(RegistryError, "cannot govern geography"):
            NationalRegistryBuilder(
                classification_version="2021",
                source_catalog=source_catalog(),
                coverage_plan=coverage(),
                scope="test",
            ).build(
                geographies=self.geographies,
                governing_bodies=[changed],
                snapshots=[self.sgc_snapshot, self.directory_snapshot],
            )

    def test_complete_layer_rejects_source_catalogued_for_other_purpose(self) -> None:
        changed_catalog = source_catalog()
        changed_catalog["sources"][0]["coverageLayer"] = (
            "municipal-regional-governments"
        )
        with self.assertRaisesRegex(RegistryError, "is catalogued for"):
            NationalRegistryBuilder(
                classification_version="2021",
                source_catalog=changed_catalog,
                coverage_plan=coverage(),
                scope="test",
            ).build(
                geographies=self.geographies,
                governing_bodies=[],
                snapshots=[self.sgc_snapshot],
            )

    def test_complete_baseline_requires_records_for_jurisdiction(self) -> None:
        with self.assertRaisesRegex(
            RegistryError,
            "expected 1 census subdivisions, observed 0",
        ):
            NationalRegistryBuilder(
                classification_version="2021",
                source_catalog=source_catalog(),
                coverage_plan=coverage(jurisdiction="BC"),
                scope="test",
            ).build(
                geographies=self.geographies,
                governing_bodies=[],
                snapshots=[self.sgc_snapshot],
            )

    def test_unlocked_record_provenance_fails_closed(self) -> None:
        with self.assertRaisesRegex(RegistryError, "unlocked source snapshot"):
            NationalRegistryBuilder(
                classification_version="2021",
                source_catalog=source_catalog(),
                coverage_plan=coverage(),
                scope="test",
            ).build(
                geographies=self.geographies,
                governing_bodies=self.bodies,
                snapshots=[self.sgc_snapshot],
            )

    def test_geography_classification_version_must_match_builder(self) -> None:
        changed_csd = replace(
            self.geographies[-1],
            geography_id="ca:sgc:2026:census-subdivision:3518013",
            parent_id="ca:sgc:2026:census-division:3518",
        )
        with self.assertRaisesRegex(RegistryError, "id/version"):
            NationalRegistryBuilder(
                classification_version="2021",
                source_catalog=source_catalog(),
                coverage_plan=coverage(),
                scope="test",
            ).build(
                geographies=[*self.geographies[:-1], changed_csd],
                governing_bodies=[],
                snapshots=[self.sgc_snapshot],
            )

    def test_body_provenance_source_jurisdiction_must_match_body(self) -> None:
        changed_catalog = source_catalog()
        changed_catalog["sources"][1]["jurisdiction"] = "QC"
        with self.assertRaisesRegex(
            RegistryError,
            "source jurisdiction QC does not match body jurisdiction ON",
        ):
            NationalRegistryBuilder(
                classification_version="2021",
                source_catalog=changed_catalog,
                coverage_plan=coverage(),
                scope="test",
            ).build(
                geographies=self.geographies,
                governing_bodies=self.bodies,
                snapshots=[self.sgc_snapshot, self.directory_snapshot],
            )

    def test_ca_body_source_requires_documented_multi_jurisdiction_rule(self) -> None:
        changed_catalog = source_catalog()
        changed_catalog["sources"][1]["jurisdiction"] = "CA"
        with self.assertRaisesRegex(RegistryError, "multi-jurisdiction rule"):
            NationalRegistryBuilder(
                classification_version="2021",
                source_catalog=changed_catalog,
                coverage_plan=coverage(),
                scope="test",
            ).build(
                geographies=self.geographies,
                governing_bodies=self.bodies,
                snapshots=[self.sgc_snapshot, self.directory_snapshot],
            )

    def test_active_source_requires_explicit_licence_fields(self) -> None:
        changed_catalog = source_catalog()
        del changed_catalog["sources"][0]["licenseUrl"]
        with self.assertRaisesRegex(RegistryError, "missing fields: licenseUrl"):
            NationalRegistryBuilder(
                classification_version="2021",
                source_catalog=changed_catalog,
                coverage_plan=coverage(),
                scope="test",
            ).build(
                geographies=self.geographies,
                governing_bodies=[],
                snapshots=[self.sgc_snapshot],
            )

    def test_pending_permission_cannot_support_complete_coverage(self) -> None:
        changed_catalog = source_catalog()
        changed_catalog["sources"][1].update(
            {
                "licenseStatus": "permission-review-required",
                "reuseReviewRequired": True,
            }
        )
        changed_coverage = coverage()
        changed_coverage["jurisdictions"][0]["layers"][
            "municipal-regional-governments"
        ] = {
            "status": "complete",
            "sourceIds": ["ontario-municipal-directory"],
            "expectedVerifiedBodyCount": 1,
        }
        with self.assertRaisesRegex(RegistryError, "reuseReviewRequired=false"):
            NationalRegistryBuilder(
                classification_version="2021",
                source_catalog=changed_catalog,
                coverage_plan=changed_coverage,
                scope="test",
            ).build(
                geographies=self.geographies,
                governing_bodies=self.bodies,
                snapshots=[self.sgc_snapshot, self.directory_snapshot],
            )

    def test_pending_source_cannot_emit_record_in_partial_production_layer(
        self,
    ) -> None:
        changed_catalog = source_catalog()
        changed_catalog["sources"][1].update(
            {
                "licenseStatus": "permission-review-required",
                "reuseReviewRequired": True,
                "publicSafe": False,
            }
        )
        changed_coverage = production_coverage()
        on_row = next(
            row
            for row in changed_coverage["jurisdictions"]
            if row["code"] == "ON"
        )
        on_row["layers"]["municipal-regional-governments"] = {
            "status": "partial",
            "sourceIds": ["ontario-municipal-directory"],
        }
        with self.assertRaisesRegex(RegistryError, "reuseReviewRequired=false"):
            NationalRegistryBuilder(
                classification_version="2021",
                source_catalog=changed_catalog,
                coverage_plan=changed_coverage,
            ).build(
                geographies=self.geographies,
                governing_bodies=self.bodies,
                snapshots=[self.sgc_snapshot, self.directory_snapshot],
            )

    def test_missing_required_layer_is_not_silently_defaulted(self) -> None:
        changed_coverage = coverage()
        del changed_coverage["jurisdictions"][0]["layers"][
            "municipal-regional-governments"
        ]
        with self.assertRaisesRegex(RegistryError, "explicitly match requiredLayers"):
            NationalRegistryBuilder(
                classification_version="2021",
                source_catalog=source_catalog(),
                coverage_plan=changed_coverage,
                scope="test",
            ).build(
                geographies=self.geographies,
                governing_bodies=[],
                snapshots=[self.sgc_snapshot],
            )

    def test_production_scope_requires_nunavut_and_all_thirteen_codes(self) -> None:
        with self.assertRaisesRegex(RegistryError, "exact 13.*missing NU"):
            NationalRegistryBuilder(
                classification_version="2021",
                source_catalog=source_catalog(),
                coverage_plan=production_coverage_without_nunavut(),
            ).build(
                geographies=self.geographies,
                governing_bodies=[],
                snapshots=[self.sgc_snapshot],
            )


if __name__ == "__main__":
    unittest.main()
