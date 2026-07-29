from __future__ import annotations

import copy
import csv
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from jsonschema import Draft202012Validator

import national.rollout as rollout_module
from national.models import PROVINCE_TERRITORY_ISO_CODES, canonical_sha256
from national.rollout import (
    RolloutError,
    build_rollout_report,
    load_rollout_inputs,
    render_rollout_table,
    scaffold_jurisdiction_workspace,
    validate_rollout_contract,
)


ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "national" / "source_catalog.json"
COVERAGE = ROOT / "national" / "coverage_plan.json"
JURISDICTIONS = ROOT / "national" / "jurisdictions"
SCHEMA = ROOT / "national" / "schemas" / "jurisdiction-rollout.schema.json"
ROLLOUT_ARTIFACT_SCHEMAS = (
    ROOT / "national" / "schemas" / "jurisdiction-source-lock.schema.json",
    ROOT / "national" / "schemas" / "verified-jurisdiction-directory.schema.json",
    ROOT / "national" / "schemas" / "publication-approval.schema.json",
    ROOT / "national" / "schemas" / "sgc-geography-index.schema.json",
)
SGC_INDEX = ROOT / "national" / "sgc_2021_geography_index.json"
SCRIPT = ROOT / "scripts" / "manage_national_rollout.py"


class NationalRolloutTests(unittest.TestCase):
    def setUp(self) -> None:
        self.inputs = load_rollout_inputs(
            catalog_path=CATALOG,
            coverage_plan_path=COVERAGE,
            jurisdictions_root=JURISDICTIONS,
        )

    def _build_verified_on_promotion(
        self,
        root: Path,
        *,
        complete: bool,
    ) -> tuple[dict, dict, dict, dict[str, Path]]:
        catalog = copy.deepcopy(self.inputs.catalog)
        coverage = copy.deepcopy(self.inputs.coverage_plan)
        manifests = copy.deepcopy(self.inputs.manifests)
        adapter_id = "on-municipal-bundle"
        adapter_version = "1.0.0"
        source_payloads = {
            "on-mmah-municipalities": (
                b"id,name,type,url\n"
                b"1813,City of Oshawa,City,https://www.oshawa.ca/\n"
            ),
            "on-lio-municipal-boundaries": (
                b"record_key,id,sgc\nboundary-1813,1813,3518013\n"
            ),
        }
        source_paths: dict[str, str] = {}
        for source_id, payload in source_payloads.items():
            digest = hashlib.sha256(payload).hexdigest()
            relative = f"national/source-objects/{digest[:2]}/{digest}"
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(payload)
            source_paths[source_id] = relative

        promoted = []
        remaining = []
        for row in catalog["plannedSources"]:
            payload = source_payloads.get(row["sourceId"])
            if payload is None:
                remaining.append(row)
                continue
            row["requestUrl"] = row["landingPageUrl"]
            row["mediaType"] = "text/csv"
            row["adapterId"] = adapter_id
            row["adapterVersion"] = adapter_version
            row["recordKeyField"] = (
                "id"
                if row["sourceId"] == "on-mmah-municipalities"
                else "record_key"
            )
            row["recordCollectionPath"] = "$"
            if row["sourceId"] == "on-mmah-municipalities":
                row["officialLegalTypeField"] = "type"
                row["identityFieldMap"] = {
                    "externalId": "id",
                    "officialName": "name",
                    "officialLegalType": "type",
                    "officialUrl": "url",
                }
                row["externalIdNamespace"] = "on-mmah"
            row["approvedSha256"] = hashlib.sha256(payload).hexdigest()
            row["runtimeNetworkRequired"] = False
            promoted.append(row)
        catalog["plannedSources"] = remaining
        catalog["sources"].extend(promoted)

        on_coverage = next(
            row for row in coverage["jurisdictions"] if row["code"] == "ON"
        )
        on_coverage["layers"]["municipal-regional-governments"] = {
            "status": "complete" if complete else "partial",
            "sourceIds": list(source_payloads),
        }
        manifest = manifests["ON"]
        manifest["status"] = "complete" if complete else "partial"
        manifest["sourceRoles"] = {
            "on-mmah-municipalities": [
                "governing-body-roster",
                "control-total",
            ],
            "on-lio-municipal-boundaries": ["boundary-crosswalk"],
        }
        complete_stage_count = 8 if complete else 6
        for index, stage in enumerate(manifest["stages"]):
            stage["status"] = (
                "complete" if index < complete_stage_count else "not-started"
            )
            stage.pop("notes", None)

        module_path = "national/providers/on.py"
        test_path = "tests/test_national_on_provider.py"
        fixture_paths = [
            "national/jurisdictions/ON/fixtures/roster.csv",
            "national/jurisdictions/ON/fixtures/boundaries.csv",
        ]
        provider_source = """\
import csv
import io

adapter_id = "on-municipal-bundle"
adapter_version = "1.0.0"


def _rows(payload):
    return list(csv.DictReader(io.StringIO(payload.decode("utf-8"))))


def build_verified_directory(
    *,
    payloads,
    snapshots,
    jurisdiction,
    source_lock_canonical_sha256,
):
    roster = _rows(payloads["on-mmah-municipalities"])
    boundaries = {
        row["id"]: row
        for row in _rows(payloads["on-lio-municipal-boundaries"])
    }
    records = []
    for row in roster:
        boundary = boundaries[row["id"]]
        geography_id = (
            "ca:sgc:2021:census-subdivision:" + boundary["sgc"]
        )
        records.append(
            {
                "body": {
                    "id": "ca:gov:on:municipal:" + row["id"],
                    "bodyType": "municipal-government",
                    "status": "active",
                    "officialNames": {
                        "en-CA": row["name"]
                    },
                    "provinceTerritory": jurisdiction,
                    "officialUrl": row["url"],
                    "externalIds": {"on-mmah": row["id"]},
                    "governsGeographyIds": [geography_id],
                    "officialLegalType": row["type"],
                    "governmentTier": "single-tier",
                    "parentBodyIds": [],
                    "effectiveFrom": None,
                    "effectiveTo": None,
                },
                "provenance": {
                    "sourceId": "on-mmah-municipalities",
                    "snapshotSha256": snapshots[
                        "on-mmah-municipalities"
                    ]["sha256"],
                    "recordKey": row["id"],
                    "sourceFields": ["id", "name", "type", "url"],
                    "transform": "exact official field mapping",
                    "adapterId": adapter_id,
                    "adapterVersion": adapter_version,
                    "identityFieldMap": {
                        "externalId": "id",
                        "officialName": "name",
                        "officialLegalType": "type",
                        "officialUrl": "url",
                    },
                    "geographyEvidence": [
                        {
                            "sourceId": "on-lio-municipal-boundaries",
                            "snapshotSha256": snapshots[
                                "on-lio-municipal-boundaries"
                            ]["sha256"],
                            "recordKey": boundary["record_key"],
                            "sourceFields": ["record_key", "id", "sgc"],
                            "transform": "exact official code join",
                            "geographyId": geography_id,
                        }
                    ],
                    "relationshipEvidence": [],
                },
            }
        )
    return {
        "schemaVersion": (
            "auditback-verified-jurisdiction-directory-1.0.0"
        ),
        "jurisdiction": jurisdiction,
        "candidateOnly": False,
        "adapter": {"id": adapter_id, "version": adapter_version},
        "sourceLockCanonicalSha256": source_lock_canonical_sha256,
        "records": records,
    }
"""
        provider_test = """\
import hashlib
import unittest
from pathlib import Path

from national.providers import on as provider


class OntarioProviderTests(unittest.TestCase):
    def test_builds_locked_fixture(self):
        root = Path(__file__).resolve().parents[1]
        payloads = {
            "on-mmah-municipalities": (
                root
                / "national/jurisdictions/ON/fixtures/roster.csv"
            ).read_bytes(),
            "on-lio-municipal-boundaries": (
                root
                / "national/jurisdictions/ON/fixtures/boundaries.csv"
            ).read_bytes(),
        }
        snapshots = {
            source_id: {"sha256": hashlib.sha256(payload).hexdigest()}
            for source_id, payload in payloads.items()
        }
        result = provider.build_verified_directory(
            payloads=payloads,
            snapshots=snapshots,
            jurisdiction="ON",
            source_lock_canonical_sha256="a" * 64,
        )
        self.assertEqual(
            "City of Oshawa",
            result["records"][0]["body"]["officialNames"]["en-CA"],
        )
        self.assertEqual(
            "ca:sgc:2021:census-subdivision:3518013",
            result["records"][0]["provenance"][
                "geographyEvidence"
            ][0]["geographyId"],
        )


if __name__ == "__main__":
    unittest.main()
"""
        for relative, payload in (
            ("national/__init__.py", b""),
            ("national/providers/__init__.py", b""),
            (
                module_path,
                provider_source.encode("utf-8"),
            ),
            (
                test_path,
                provider_test.encode("utf-8"),
            ),
            (fixture_paths[0], source_payloads["on-mmah-municipalities"]),
            (
                fixture_paths[1],
                source_payloads["on-lio-municipal-boundaries"],
            ),
        ):
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(payload)
        manifest["adapter"] = {
            "adapterId": adapter_id,
            "adapterVersion": adapter_version,
            "modulePath": module_path,
            "testPath": test_path,
            "fixturePaths": fixture_paths,
        }

        source_lock_path = "national/jurisdictions/ON/sources.lock.json"
        source_lock = {
            "schemaVersion": "auditback-jurisdiction-source-lock-1.0.0",
            "sourceBundleCanonicalSha256": canonical_sha256(
                {
                    source_id: next(
                        row
                        for row in catalog["sources"]
                        if row["sourceId"] == source_id
                    )
                    for source_id in sorted(source_payloads)
                }
            ),
            "coverageLayerCanonicalSha256": canonical_sha256(
                {
                    "jurisdiction": "ON",
                    "coverageLayer": "municipal-regional-governments",
                    "coverage": on_coverage["layers"][
                        "municipal-regional-governments"
                    ],
                }
            ),
            "snapshots": [
                {
                    "sourceId": source_id,
                    "sha256": hashlib.sha256(payload).hexdigest(),
                    "byteLength": len(payload),
                    "mediaType": "text/csv",
                    "requestUrl": next(
                        row["requestUrl"]
                        for row in catalog["sources"]
                        if row["sourceId"] == source_id
                    ),
                    "effectiveDate": "2026-07-26",
                    "objectPath": source_paths[source_id],
                }
                for source_id, payload in source_payloads.items()
            ],
        }
        source_lock["sourceLockCanonicalSha256"] = canonical_sha256(source_lock)
        source_lock_target = root / source_lock_path
        source_lock_target.parent.mkdir(parents=True, exist_ok=True)
        source_lock_target.write_text(
            json.dumps(source_lock, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        manifest["transport"] = {"sourceLockPath": source_lock_path}

        directory_path = "national/jurisdictions/ON/verified-directory.json"
        directory = {
            "schemaVersion": "auditback-verified-jurisdiction-directory-1.0.0",
            "jurisdiction": "ON",
            "candidateOnly": False,
            "adapter": {"id": adapter_id, "version": adapter_version},
            "sourceLockCanonicalSha256": source_lock[
                "sourceLockCanonicalSha256"
            ],
            "records": [
                {
                    "body": {
                        "id": "ca:gov:on:municipal:1813",
                        "bodyType": "municipal-government",
                        "status": "active",
                        "officialNames": {"en-CA": "City of Oshawa"},
                        "provinceTerritory": "ON",
                        "officialUrl": "https://www.oshawa.ca/",
                        "externalIds": {"on-mmah": "1813"},
                        "governsGeographyIds": [
                            "ca:sgc:2021:census-subdivision:3518013"
                        ],
                        "officialLegalType": "City",
                        "governmentTier": "single-tier",
                        "parentBodyIds": [],
                        "effectiveFrom": None,
                        "effectiveTo": None,
                    },
                    "provenance": {
                        "sourceId": "on-mmah-municipalities",
                        "snapshotSha256": hashlib.sha256(
                            source_payloads["on-mmah-municipalities"]
                        ).hexdigest(),
                        "recordKey": "1813",
                        "sourceFields": ["id", "name", "type", "url"],
                        "transform": "exact official field mapping",
                        "adapterId": adapter_id,
                        "adapterVersion": adapter_version,
                        "identityFieldMap": {
                            "externalId": "id",
                            "officialName": "name",
                            "officialLegalType": "type",
                            "officialUrl": "url",
                        },
                        "geographyEvidence": [
                            {
                                "sourceId": "on-lio-municipal-boundaries",
                                "snapshotSha256": hashlib.sha256(
                                    source_payloads[
                                        "on-lio-municipal-boundaries"
                                    ]
                                ).hexdigest(),
                                "recordKey": "boundary-1813",
                                "sourceFields": [
                                    "record_key",
                                    "id",
                                    "sgc",
                                ],
                                "transform": "exact official code join",
                                "geographyId": (
                                    "ca:sgc:2021:census-subdivision:3518013"
                                ),
                            }
                        ],
                        "relationshipEvidence": [],
                    },
                }
            ],
        }
        directory_bytes = (
            json.dumps(directory, sort_keys=True, indent=2) + "\n"
        ).encode("utf-8")
        directory_target = root / directory_path
        directory_target.write_bytes(directory_bytes)
        manifest["output"] = {
            "directoryPath": directory_path,
            "directorySha256": hashlib.sha256(directory_bytes).hexdigest(),
            "directoryCanonicalSha256": canonical_sha256(directory),
        }

        evidence_root = root / "national/jurisdictions/ON/evidence"
        evidence_root.mkdir(parents=True)
        classification_path = (
            "national/jurisdictions/ON/evidence/classification.csv"
        )
        with (root / classification_path).open(
            "w",
            encoding="utf-8",
            newline="",
        ) as handle:
            writer = csv.writer(handle, lineterminator="\n")
            writer.writerow(rollout_module.CLASSIFICATION_HEADERS)
            writer.writerow(
                [
                    "on-mmah-municipalities",
                    "1813",
                    "City",
                    "municipal-government",
                    "single-tier",
                    "",
                    "emit-municipal-layer",
                    "",
                    "",
                    "reviewer@example.test",
                    "approved",
                    "",
                ]
            )
        crosswalk_path = "national/jurisdictions/ON/evidence/crosswalk.csv"
        with (root / crosswalk_path).open(
            "w",
            encoding="utf-8",
            newline="",
        ) as handle:
            writer = csv.writer(handle, lineterminator="\n")
            writer.writerow(rollout_module.CROSSWALK_HEADERS)
            writer.writerow(
                [
                    "ca:gov:on:municipal:1813",
                    "on-mmah:1813",
                    "on-lio-municipal-boundaries",
                    hashlib.sha256(
                        source_payloads["on-lio-municipal-boundaries"]
                    ).hexdigest(),
                    "boundary-1813",
                    "ca:sgc:2021:census-subdivision:3518013",
                    "exact-official-code",
                    "reviewer@example.test",
                    "matched",
                    "",
                ]
            )
        exceptions_path = "national/jurisdictions/ON/evidence/exceptions.json"
        (root / exceptions_path).write_text(
            json.dumps(
                {
                    "schemaVersion": "auditback-jurisdiction-exceptions-1.0.0",
                    "jurisdiction": "ON",
                    "candidateOnly": False,
                    "reviewer": "reviewer@example.test",
                    "reviewedAt": "2026-07-26",
                    "exceptions": [],
                },
                sort_keys=True,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        manifest["reconciliation"] = {
            "expectedVerifiedBodyCount": 1 if complete else None,
            "classificationDecisionPath": classification_path,
            "crosswalkReviewPath": crosswalk_path,
            "exceptionsPath": exceptions_path,
            "reconciliationPath": None,
        }
        reconciliation_path = (
            "national/jurisdictions/ON/evidence/reconciliation.json"
        )
        if complete:
            (root / reconciliation_path).write_text(
                json.dumps(
                    {
                        "schemaVersion": (
                            "auditback-jurisdiction-reconciliation-1.0.0"
                        ),
                        "jurisdiction": "ON",
                        "candidateOnly": False,
                        "asOfDate": "2026-07-26",
                        "officialControlTotals": [
                            {
                                "sourceId": "on-mmah-municipalities",
                                "officialLegalType": "City",
                                "sourceRecordKey": "control-total-2026",
                                "expectedActiveCount": 1,
                            }
                        ],
                        "emittedCounts": [
                            {
                                "canonicalBodyType": "municipal-government",
                                "count": 1,
                            }
                        ],
                        "unmatchedCount": 0,
                        "reconciled": True,
                        "reviewer": "reviewer@example.test",
                    },
                    sort_keys=True,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            manifest["reconciliation"]["reconciliationPath"] = reconciliation_path

            approval_path = (
                "national/jurisdictions/ON/evidence/publication-approval.json"
            )
            approval = {
                "schemaVersion": (
                    "auditback-jurisdiction-publication-approval-1.0.0"
                ),
                "jurisdiction": "ON",
                "candidateOnly": False,
                "decision": "approved",
                "reviewer": "reviewer@example.test",
                "approvedAt": "2026-07-26",
                "releaseReference": (
                    "https://github.com/Jstn-1g/"
                    "what-in-the-tax/pull/2"
                ),
                "sourceLockCanonicalSha256": source_lock[
                    "sourceLockCanonicalSha256"
                ],
                "directorySha256": manifest["output"]["directorySha256"],
                "directoryCanonicalSha256": manifest["output"][
                    "directoryCanonicalSha256"
                ],
                "expectedVerifiedBodyCount": 1,
            }
            approval_bytes = (
                json.dumps(approval, sort_keys=True, indent=2) + "\n"
            ).encode("utf-8")
            (root / approval_path).write_bytes(approval_bytes)
            manifest["publicationApproval"] = {
                "reviewer": approval["reviewer"],
                "approvedAt": approval["approvedAt"],
                "releaseReference": approval["releaseReference"],
                "artifactPath": approval_path,
                "artifactSha256": hashlib.sha256(approval_bytes).hexdigest(),
            }

        return catalog, coverage, manifests, {
            "sourceLock": source_lock_target,
            "directory": directory_target,
            "sourceObject": root / source_paths["on-mmah-municipalities"],
            "reconciliation": root / reconciliation_path,
            "provider": root / module_path,
            "providerTest": root / test_path,
            "crosswalk": root / crosswalk_path,
            "approval": root / (
                "national/jurisdictions/ON/evidence/publication-approval.json"
            ),
        }

    def test_all_thirteen_packets_validate_against_contract_and_schema(self) -> None:
        validate_rollout_contract(
            catalog=self.inputs.catalog,
            coverage_plan=self.inputs.coverage_plan,
            manifests=self.inputs.manifests,
        )
        self.assertEqual(
            PROVINCE_TERRITORY_ISO_CODES,
            set(self.inputs.manifests),
        )
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        for artifact_schema_path in ROLLOUT_ARTIFACT_SCHEMAS:
            with self.subTest(schema=artifact_schema_path.name):
                artifact_schema = json.loads(
                    artifact_schema_path.read_text(encoding="utf-8")
                )
                Draft202012Validator.check_schema(artifact_schema)
        validator = Draft202012Validator(schema)
        for code, manifest in self.inputs.manifests.items():
            with self.subTest(code=code):
                validator.validate(manifest)

    def test_report_is_honest_deterministic_and_zero_ai(self) -> None:
        first = build_rollout_report(
            catalog=self.inputs.catalog,
            coverage_plan=self.inputs.coverage_plan,
            manifests=self.inputs.manifests,
        )
        second = build_rollout_report(
            catalog=self.inputs.catalog,
            coverage_plan=self.inputs.coverage_plan,
            manifests=self.inputs.manifests,
        )
        self.assertEqual(first, second)
        self.assertEqual(13, first["summary"]["jurisdictionsTracked"])
        self.assertEqual(0, first["summary"]["jurisdictionsPublicationReady"])
        self.assertFalse(first["method"]["runtimeNetworkRequired"])
        self.assertFalse(first["method"]["runtimeAiRequired"])
        self.assertFalse(first["method"]["publicationFromThisReportAllowed"])
        self.assertIn("AI tokens: 0", render_rollout_table(first))

    def test_unknown_or_cross_jurisdiction_source_is_rejected(self) -> None:
        changed = copy.deepcopy(self.inputs.manifests)
        changed["ON"]["primarySourceIds"] = ["qc-mamh-municipal-directory"]
        with self.assertRaisesRegex(RolloutError, "another jurisdiction"):
            validate_rollout_contract(
                catalog=self.inputs.catalog,
                coverage_plan=self.inputs.coverage_plan,
                manifests=changed,
            )

    def test_later_stage_cannot_complete_before_an_earlier_gate(self) -> None:
        changed = copy.deepcopy(self.inputs.manifests)
        changed["ON"]["stages"][3]["status"] = "complete"
        with self.assertRaisesRegex(RolloutError, "follows unfinished work"):
            validate_rollout_contract(
                catalog=self.inputs.catalog,
                coverage_plan=self.inputs.coverage_plan,
                manifests=changed,
            )

    def test_mandatory_stage_cannot_be_not_applicable(self) -> None:
        changed = copy.deepcopy(self.inputs.manifests)
        changed["ON"]["stages"][2]["status"] = "not-applicable"
        with self.assertRaisesRegex(RolloutError, "violates the rollout schema"):
            validate_rollout_contract(
                catalog=self.inputs.catalog,
                coverage_plan=self.inputs.coverage_plan,
                manifests=changed,
            )

    def test_sgc_code_must_match_the_jurisdiction(self) -> None:
        changed = copy.deepcopy(self.inputs.manifests)
        changed["AB"]["jurisdiction"]["sgcCode"] = "35"
        with self.assertRaisesRegex(RolloutError, "does not identify AB"):
            validate_rollout_contract(
                catalog=self.inputs.catalog,
                coverage_plan=self.inputs.coverage_plan,
                manifests=changed,
            )

    def test_municipal_layer_cannot_be_marked_not_applicable(self) -> None:
        changed_manifests = copy.deepcopy(self.inputs.manifests)
        changed_coverage = copy.deepcopy(self.inputs.coverage_plan)
        changed_manifests["ON"]["status"] = "not-applicable"
        on_coverage = next(
            row
            for row in changed_coverage["jurisdictions"]
            if row["code"] == "ON"
        )
        on_coverage["layers"]["municipal-regional-governments"]["status"] = (
            "not-applicable"
        )
        with self.assertRaisesRegex(RolloutError, "cannot be not-applicable"):
            validate_rollout_contract(
                catalog=self.inputs.catalog,
                coverage_plan=changed_coverage,
                manifests=changed_manifests,
            )

    def test_source_discovery_cannot_be_called_identified(self) -> None:
        changed = copy.deepcopy(self.inputs.manifests)
        changed_coverage = copy.deepcopy(self.inputs.coverage_plan)
        changed["NL"]["stages"][0] = {
            "id": "official-source-identified",
            "status": "complete",
        }
        changed["NL"]["status"] = "adapter-needed"
        nl_coverage = next(
            row for row in changed_coverage["jurisdictions"] if row["code"] == "NL"
        )
        nl_coverage["layers"]["municipal-regional-governments"]["status"] = (
            "adapter-needed"
        )
        with self.assertRaisesRegex(RolloutError, "remain in discovery"):
            validate_rollout_contract(
                catalog=self.inputs.catalog,
                coverage_plan=changed_coverage,
                manifests=changed,
            )

    def test_active_source_requires_real_hash_pinned_metadata(self) -> None:
        changed_catalog = copy.deepcopy(self.inputs.catalog)
        del changed_catalog["sources"][0]["approvedSha256"]
        with self.assertRaisesRegex(
            RolloutError,
            "active source requires approvedSha256",
        ):
            validate_rollout_contract(
                catalog=changed_catalog,
                coverage_plan=self.inputs.coverage_plan,
                manifests=self.inputs.manifests,
            )

    def test_partial_status_requires_positive_verified_directory_evidence(self) -> None:
        changed_catalog = copy.deepcopy(self.inputs.catalog)
        promoted = []
        remaining = []
        for row in changed_catalog["plannedSources"]:
            if row["sourceId"] in {
                "on-mmah-municipalities",
                "on-lio-municipal-boundaries",
            }:
                row["requestUrl"] = row["landingPageUrl"]
                row["mediaType"] = "application/octet-stream"
                row["adapterId"] = "on-municipal-bundle"
                row["adapterVersion"] = "1.0.0"
                row["recordKeyField"] = (
                    "id"
                    if row["sourceId"] == "on-mmah-municipalities"
                    else "record_key"
                )
                row["recordCollectionPath"] = "$"
                if row["sourceId"] == "on-mmah-municipalities":
                    row["officialLegalTypeField"] = "type"
                row["approvedSha256"] = "a" * 64
                row["runtimeNetworkRequired"] = False
                promoted.append(row)
            else:
                remaining.append(row)
        changed_catalog["plannedSources"] = remaining
        changed_catalog["sources"].extend(promoted)

        changed_manifests = copy.deepcopy(self.inputs.manifests)
        changed_manifests["ON"]["status"] = "partial"
        changed_coverage = copy.deepcopy(self.inputs.coverage_plan)
        on_coverage = next(
            row
            for row in changed_coverage["jurisdictions"]
            if row["code"] == "ON"
        )
        on_coverage["layers"]["municipal-regional-governments"] = {
            "status": "partial",
            "sourceIds": [
                "on-mmah-municipalities",
                "on-lio-municipal-boundaries",
            ],
        }
        with self.assertRaisesRegex(RolloutError, "status remains adapter-needed"):
            validate_rollout_contract(
                catalog=changed_catalog,
                coverage_plan=changed_coverage,
                manifests=changed_manifests,
            )

    def test_verified_partial_and_complete_promotions_are_evidence_bound(self) -> None:
        for complete in (False, True):
            with self.subTest(complete=complete), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                catalog, coverage, manifests, _ = (
                    self._build_verified_on_promotion(root, complete=complete)
                )
                with patch.object(rollout_module, "REPOSITORY_ROOT", root):
                    validate_rollout_contract(
                        catalog=catalog,
                        coverage_plan=coverage,
                        manifests=manifests,
                    )
                    report = build_rollout_report(
                        catalog=catalog,
                        coverage_plan=coverage,
                        manifests=manifests,
                    )
                on_row = next(
                    row
                    for row in report["jurisdictions"]
                    if row["code"] == "ON"
                )
                self.assertEqual(complete, on_row["publicationReady"])

    def test_verified_promotion_rejects_source_payload_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            catalog, coverage, manifests, paths = (
                self._build_verified_on_promotion(root, complete=False)
            )
            paths["sourceObject"].write_bytes(b"tampered")
            with patch.object(rollout_module, "REPOSITORY_ROOT", root):
                with self.assertRaisesRegex(RolloutError, "payload byte length"):
                    validate_rollout_contract(
                        catalog=catalog,
                        coverage_plan=coverage,
                        manifests=manifests,
                    )

    def test_declared_adapter_test_must_execute_successfully(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            catalog, coverage, manifests, paths = (
                self._build_verified_on_promotion(root, complete=False)
            )
            paths["providerTest"].write_text(
                paths["providerTest"].read_text(encoding="utf-8")
                + "\n\nclass DeliberateFailure(unittest.TestCase):\n"
                + "    def test_failure(self):\n"
                + "        self.fail('declared test was executed')\n",
                encoding="utf-8",
            )
            with patch.object(rollout_module, "REPOSITORY_ROOT", root):
                with self.assertRaisesRegex(
                    RolloutError,
                    "failed its offline test run",
                ):
                    validate_rollout_contract(
                        catalog=catalog,
                        coverage_plan=coverage,
                        manifests=manifests,
                    )

    def test_adapter_test_cannot_exit_before_unittest_reports_results(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            catalog, coverage, manifests, paths = (
                self._build_verified_on_promotion(root, complete=False)
            )
            paths["providerTest"].write_text(
                "import sys\n"
                "from os import _exit as terminate\n"
                "import unittest\n"
                "from national.providers import on as provider\n\n"
                "class NeverExecuted(unittest.TestCase):\n"
                "    def test_failure(self):\n"
                "        self.fail('must execute')\n\n"
                "sys.__stdout__.write('AUDITBACK_TEST_RESULT:forged:1\\n')\n"
                "sys.__stdout__.flush()\n"
                "terminate(0)\n",
                encoding="utf-8",
            )
            with patch.object(rollout_module, "REPOSITORY_ROOT", root):
                with self.assertRaisesRegex(
                    RolloutError,
                    "failed its offline test run",
                ):
                    validate_rollout_contract(
                        catalog=catalog,
                        coverage_plan=coverage,
                        manifests=manifests,
                    )

    def test_provider_process_exit_cannot_green_the_rollout(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            catalog, coverage, manifests, paths = (
                self._build_verified_on_promotion(root, complete=False)
            )
            paths["provider"].write_text(
                "from os import _exit as terminate\n\n"
                "adapter_id = 'on-municipal-bundle'\n"
                "adapter_version = '1.0.0'\n\n"
                "def build_verified_directory(**kwargs):\n"
                "    terminate(0)\n",
                encoding="utf-8",
            )
            paths["providerTest"].write_text(
                "import unittest\n"
                "from national.providers import on as provider\n\n"
                "class ProviderContract(unittest.TestCase):\n"
                "    def test_callable(self):\n"
                "        self.assertTrue(callable("
                "provider.build_verified_directory))\n",
                encoding="utf-8",
            )
            with patch.object(rollout_module, "REPOSITORY_ROOT", root):
                with self.assertRaisesRegex(
                    RolloutError,
                    "failed isolated provider execution",
                ):
                    validate_rollout_contract(
                        catalog=catalog,
                        coverage_plan=coverage,
                        manifests=manifests,
                    )

    def test_provider_must_return_plain_json_not_spoofed_equality(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            catalog, coverage, manifests, paths = (
                self._build_verified_on_promotion(root, complete=False)
            )
            provider_source = paths["provider"].read_text(encoding="utf-8")
            provider_source = provider_source.replace(
                "def build_verified_directory(",
                "def _real_build_verified_directory(",
                1,
            )
            provider_source += (
                "\n\nclass LyingDirectory(dict):\n"
                "    def __eq__(self, other):\n"
                "        return True\n\n"
                "def build_verified_directory(**kwargs):\n"
                "    return LyingDirectory("
                "_real_build_verified_directory(**kwargs))\n"
            )
            paths["provider"].write_text(provider_source, encoding="utf-8")
            with patch.object(rollout_module, "REPOSITORY_ROOT", root):
                with self.assertRaisesRegex(
                    RolloutError,
                    "failed isolated provider execution",
                ):
                    validate_rollout_contract(
                        catalog=catalog,
                        coverage_plan=coverage,
                        manifests=manifests,
                    )

    def test_reviewed_directory_must_equal_fresh_provider_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            catalog, coverage, manifests, paths = (
                self._build_verified_on_promotion(root, complete=False)
            )
            directory = json.loads(
                paths["directory"].read_text(encoding="utf-8")
            )
            directory["records"][0]["body"]["status"] = "inactive"
            directory_bytes = (
                json.dumps(directory, sort_keys=True, indent=2) + "\n"
            ).encode("utf-8")
            paths["directory"].write_bytes(directory_bytes)
            manifests["ON"]["output"]["directorySha256"] = hashlib.sha256(
                directory_bytes
            ).hexdigest()
            manifests["ON"]["output"]["directoryCanonicalSha256"] = (
                canonical_sha256(directory)
            )
            with patch.object(rollout_module, "REPOSITORY_ROOT", root):
                with self.assertRaisesRegex(
                    RolloutError,
                    "output differs from the reviewed directory",
                ):
                    validate_rollout_contract(
                        catalog=catalog,
                        coverage_plan=coverage,
                        manifests=manifests,
                    )

    def test_provider_evidence_key_must_select_the_declared_source_field(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            catalog, coverage, manifests, paths = (
                self._build_verified_on_promotion(root, complete=False)
            )
            provider_source = paths["provider"].read_text(encoding="utf-8")
            paths["provider"].write_text(
                provider_source.replace(
                    'boundary["record_key"]',
                    '"1813"',
                ),
                encoding="utf-8",
            )
            directory = json.loads(
                paths["directory"].read_text(encoding="utf-8")
            )
            directory["records"][0]["provenance"]["geographyEvidence"][0][
                "recordKey"
            ] = "1813"
            directory_bytes = (
                json.dumps(directory, sort_keys=True, indent=2) + "\n"
            ).encode("utf-8")
            paths["directory"].write_bytes(directory_bytes)
            manifests["ON"]["output"]["directorySha256"] = hashlib.sha256(
                directory_bytes
            ).hexdigest()
            manifests["ON"]["output"]["directoryCanonicalSha256"] = (
                canonical_sha256(directory)
            )
            crosswalk_rows = paths["crosswalk"].read_text(
                encoding="utf-8"
            ).splitlines()
            crosswalk_rows[1] = crosswalk_rows[1].replace(
                "boundary-1813",
                "1813",
            )
            paths["crosswalk"].write_text(
                "\n".join(crosswalk_rows) + "\n",
                encoding="utf-8",
            )
            with patch.object(rollout_module, "REPOSITORY_ROOT", root):
                with self.assertRaisesRegex(
                    RolloutError,
                    "recordKey must select exactly one locked structured record",
                ):
                    validate_rollout_contract(
                        catalog=catalog,
                        coverage_plan=coverage,
                        manifests=manifests,
                    )

    def test_geography_evidence_value_must_match_the_locked_source_row(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            catalog, coverage, manifests, paths = (
                self._build_verified_on_promotion(root, complete=False)
            )
            false_geography_id = (
                "ca:sgc:2021:census-subdivision:3518017"
            )
            provider_source = paths["provider"].read_text(encoding="utf-8")
            paths["provider"].write_text(
                provider_source.replace(
                    '"ca:sgc:2021:census-subdivision:" + boundary["sgc"]',
                    f'"{false_geography_id}"',
                ),
                encoding="utf-8",
            )
            paths["providerTest"].write_text(
                paths["providerTest"].read_text(encoding="utf-8").replace(
                    "ca:sgc:2021:census-subdivision:3518013",
                    false_geography_id,
                ),
                encoding="utf-8",
            )
            directory = json.loads(
                paths["directory"].read_text(encoding="utf-8")
            )
            record = directory["records"][0]
            record["body"]["governsGeographyIds"] = [false_geography_id]
            record["provenance"]["geographyEvidence"][0][
                "geographyId"
            ] = false_geography_id
            directory_bytes = (
                json.dumps(directory, sort_keys=True, indent=2) + "\n"
            ).encode("utf-8")
            paths["directory"].write_bytes(directory_bytes)
            manifests["ON"]["output"]["directorySha256"] = hashlib.sha256(
                directory_bytes
            ).hexdigest()
            manifests["ON"]["output"]["directoryCanonicalSha256"] = (
                canonical_sha256(directory)
            )
            paths["crosswalk"].write_text(
                paths["crosswalk"].read_text(encoding="utf-8").replace(
                    "ca:sgc:2021:census-subdivision:3518013",
                    false_geography_id,
                ),
                encoding="utf-8",
            )
            with patch.object(rollout_module, "REPOSITORY_ROOT", root):
                with self.assertRaisesRegex(
                    RolloutError,
                    "does not contain the claimed official geography code",
                ):
                    validate_rollout_contract(
                        catalog=catalog,
                        coverage_plan=coverage,
                        manifests=manifests,
                    )

    def test_identity_fields_must_equal_the_selected_locked_source_row(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            catalog, coverage, manifests, paths = (
                self._build_verified_on_promotion(root, complete=False)
            )
            false_name = "City of Oshwawa"
            paths["provider"].write_text(
                paths["provider"].read_text(encoding="utf-8").replace(
                    '"en-CA": row["name"]',
                    f'"en-CA": "{false_name}"',
                ),
                encoding="utf-8",
            )
            paths["providerTest"].write_text(
                paths["providerTest"].read_text(encoding="utf-8").replace(
                    "City of Oshawa",
                    false_name,
                ),
                encoding="utf-8",
            )
            directory = json.loads(
                paths["directory"].read_text(encoding="utf-8")
            )
            directory["records"][0]["body"]["officialNames"]["en-CA"] = (
                false_name
            )
            directory_bytes = (
                json.dumps(directory, sort_keys=True, indent=2) + "\n"
            ).encode("utf-8")
            paths["directory"].write_bytes(directory_bytes)
            manifests["ON"]["output"]["directorySha256"] = hashlib.sha256(
                directory_bytes
            ).hexdigest()
            manifests["ON"]["output"]["directoryCanonicalSha256"] = (
                canonical_sha256(directory)
            )
            with patch.object(rollout_module, "REPOSITORY_ROOT", root):
                with self.assertRaisesRegex(
                    RolloutError,
                    "officialName differs from the exact locked source field",
                ):
                    validate_rollout_contract(
                        catalog=catalog,
                        coverage_plan=coverage,
                        manifests=manifests,
                    )

    def test_identity_field_map_must_equal_the_catalog_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            catalog, coverage, manifests, paths = (
                self._build_verified_on_promotion(root, complete=False)
            )
            directory = json.loads(
                paths["directory"].read_text(encoding="utf-8")
            )
            record = directory["records"][0]
            record["body"]["officialNames"]["en-CA"] = "1813"
            record["provenance"]["identityFieldMap"]["officialName"] = "id"
            directory_bytes = (
                json.dumps(directory, sort_keys=True, indent=2) + "\n"
            ).encode("utf-8")
            paths["directory"].write_bytes(directory_bytes)
            manifests["ON"]["output"]["directorySha256"] = hashlib.sha256(
                directory_bytes
            ).hexdigest()
            manifests["ON"]["output"]["directoryCanonicalSha256"] = (
                canonical_sha256(directory)
            )
            with patch.object(rollout_module, "REPOSITORY_ROOT", root):
                with self.assertRaisesRegex(
                    RolloutError,
                    "identityFieldMap differs from the catalogued identity contract",
                ):
                    validate_rollout_contract(
                        catalog=catalog,
                        coverage_plan=coverage,
                        manifests=manifests,
                    )

    def test_unverified_identity_values_cannot_be_appended(self) -> None:
        mutations = (
            (
                "name",
                lambda body: body["officialNames"].update(
                    {"fr-CA": "Ville d'Oshawa"}
                ),
                "officialName differs from the exact locked source field",
            ),
            (
                "external-id",
                lambda body: body["externalIds"].update({"other": "9999"}),
                "externalIds differ from the exact catalogued namespace",
            ),
        )
        for case, mutate, expected_error in mutations:
            with (
                self.subTest(case=case),
                tempfile.TemporaryDirectory() as temporary,
            ):
                root = Path(temporary)
                catalog, coverage, manifests, paths = (
                    self._build_verified_on_promotion(root, complete=False)
                )
                directory = json.loads(
                    paths["directory"].read_text(encoding="utf-8")
                )
                mutate(directory["records"][0]["body"])
                directory_bytes = (
                    json.dumps(directory, sort_keys=True, indent=2) + "\n"
                ).encode("utf-8")
                paths["directory"].write_bytes(directory_bytes)
                manifests["ON"]["output"]["directorySha256"] = hashlib.sha256(
                    directory_bytes
                ).hexdigest()
                manifests["ON"]["output"]["directoryCanonicalSha256"] = (
                    canonical_sha256(directory)
                )
                with patch.object(rollout_module, "REPOSITORY_ROOT", root):
                    with self.assertRaisesRegex(RolloutError, expected_error):
                        validate_rollout_contract(
                            catalog=catalog,
                            coverage_plan=coverage,
                            manifests=manifests,
                        )

    def test_classification_status_and_exclusion_reason_are_fail_closed(self) -> None:
        cases = (
            (
                "contradictory-status",
                "emit-municipal-layer",
                "excluded",
                "reviewed",
                "status must be 'approved'",
            ),
            (
                "reasonless-exclusion",
                "excluded-with-reason",
                "excluded",
                "",
                "notes must explain non-municipal disposition",
            ),
        )
        for case, disposition, status, notes, expected_error in cases:
            with (
                self.subTest(case=case),
                tempfile.TemporaryDirectory() as temporary,
            ):
                path = Path(temporary) / "classification.csv"
                with path.open("w", encoding="utf-8", newline="") as handle:
                    writer = csv.writer(handle, lineterminator="\n")
                    writer.writerow(rollout_module.CLASSIFICATION_HEADERS)
                    writer.writerow(
                        [
                            "on-mmah-municipalities",
                            "1813",
                            "City",
                            (
                                "municipal-government"
                                if disposition == "emit-municipal-layer"
                                else ""
                            ),
                            (
                                "single-tier"
                                if disposition == "emit-municipal-layer"
                                else ""
                            ),
                            "",
                            disposition,
                            "",
                            "",
                            "reviewer@example.test",
                            status,
                            notes,
                        ]
                    )
                    if disposition != "emit-municipal-layer":
                        writer.writerow(
                            [
                                "on-mmah-municipalities",
                                "1814",
                                "City",
                                "municipal-government",
                                "single-tier",
                                "",
                                "emit-municipal-layer",
                                "",
                                "",
                                "reviewer@example.test",
                                "approved",
                                "",
                            ]
                        )
                with (
                    patch.object(
                        rollout_module,
                        "REPOSITORY_ROOT",
                        Path(temporary),
                    ),
                    self.assertRaisesRegex(RolloutError, expected_error),
                ):
                    rollout_module._validate_classification_review(
                        path=path.name,
                        label="classification",
                        source_ids=["on-mmah-municipalities"],
                        canonical_body_types=["municipal-government"],
                    )

    def test_complete_rollout_accounts_for_every_locked_roster_record(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            catalog, coverage, manifests, paths = (
                self._build_verified_on_promotion(root, complete=True)
            )
            new_roster = (
                b"id,name,type,url\n"
                b"1813,City of Oshawa,City,https://www.oshawa.ca/\n"
                b"9999,City of Unemittedville,City,"
                b"https://example.gov.test/unemittedville/\n"
            )
            new_roster_sha256 = hashlib.sha256(new_roster).hexdigest()
            paths["sourceObject"].write_bytes(new_roster)
            roster_catalog = next(
                row
                for row in catalog["sources"]
                if row["sourceId"] == "on-mmah-municipalities"
            )
            roster_catalog["approvedSha256"] = new_roster_sha256

            source_lock = json.loads(
                paths["sourceLock"].read_text(encoding="utf-8")
            )
            roster_snapshot = next(
                row
                for row in source_lock["snapshots"]
                if row["sourceId"] == "on-mmah-municipalities"
            )
            roster_snapshot["sha256"] = new_roster_sha256
            roster_snapshot["byteLength"] = len(new_roster)
            source_ids = sorted(manifests["ON"]["primarySourceIds"])
            source_lock["sourceBundleCanonicalSha256"] = canonical_sha256(
                {
                    source_id: next(
                        row
                        for row in catalog["sources"]
                        if row["sourceId"] == source_id
                    )
                    for source_id in source_ids
                }
            )
            source_lock.pop("sourceLockCanonicalSha256")
            source_lock["sourceLockCanonicalSha256"] = canonical_sha256(
                source_lock
            )
            paths["sourceLock"].write_text(
                json.dumps(source_lock, sort_keys=True, indent=2) + "\n",
                encoding="utf-8",
            )

            directory = json.loads(
                paths["directory"].read_text(encoding="utf-8")
            )
            directory["sourceLockCanonicalSha256"] = source_lock[
                "sourceLockCanonicalSha256"
            ]
            directory["records"][0]["provenance"]["snapshotSha256"] = (
                new_roster_sha256
            )
            directory_bytes = (
                json.dumps(directory, sort_keys=True, indent=2) + "\n"
            ).encode("utf-8")
            paths["directory"].write_bytes(directory_bytes)
            manifests["ON"]["output"]["directorySha256"] = hashlib.sha256(
                directory_bytes
            ).hexdigest()
            manifests["ON"]["output"]["directoryCanonicalSha256"] = (
                canonical_sha256(directory)
            )

            provider_source = paths["provider"].read_text(encoding="utf-8")
            paths["provider"].write_text(
                provider_source.replace(
                    'roster = _rows(payloads["on-mmah-municipalities"])',
                    'roster = _rows(payloads["on-mmah-municipalities"])[:1]',
                ),
                encoding="utf-8",
            )

            approval = json.loads(
                paths["approval"].read_text(encoding="utf-8")
            )
            approval["sourceLockCanonicalSha256"] = source_lock[
                "sourceLockCanonicalSha256"
            ]
            approval["directorySha256"] = manifests["ON"]["output"][
                "directorySha256"
            ]
            approval["directoryCanonicalSha256"] = manifests["ON"]["output"][
                "directoryCanonicalSha256"
            ]
            approval_bytes = (
                json.dumps(approval, sort_keys=True, indent=2) + "\n"
            ).encode("utf-8")
            paths["approval"].write_bytes(approval_bytes)
            manifests["ON"]["publicationApproval"]["artifactSha256"] = (
                hashlib.sha256(approval_bytes).hexdigest()
            )

            with patch.object(rollout_module, "REPOSITORY_ROOT", root):
                with self.assertRaisesRegex(
                    RolloutError,
                    "locked roster record.*unreviewed",
                ):
                    validate_rollout_contract(
                        catalog=catalog,
                        coverage_plan=coverage,
                        manifests=manifests,
                    )

    def test_verified_directory_rejects_wrong_year_and_unknown_sgc_ids(self) -> None:
        invalid_ids = (
            "ca:sgc:9999:census-subdivision:3518013",
            "ca:sgc:2021:census-subdivision:3599999",
        )
        for invalid_id in invalid_ids:
            with (
                self.subTest(geography_id=invalid_id),
                tempfile.TemporaryDirectory() as temporary,
            ):
                root = Path(temporary)
                catalog, coverage, manifests, paths = (
                    self._build_verified_on_promotion(root, complete=False)
                )
                directory = json.loads(
                    paths["directory"].read_text(encoding="utf-8")
                )
                record = directory["records"][0]
                record["body"]["governsGeographyIds"] = [invalid_id]
                record["provenance"]["geographyEvidence"][0][
                    "geographyId"
                ] = invalid_id
                directory_bytes = (
                    json.dumps(directory, sort_keys=True, indent=2) + "\n"
                ).encode("utf-8")
                paths["directory"].write_bytes(directory_bytes)
                manifests["ON"]["output"]["directorySha256"] = hashlib.sha256(
                    directory_bytes
                ).hexdigest()
                manifests["ON"]["output"]["directoryCanonicalSha256"] = (
                    canonical_sha256(directory)
                )
                with patch.object(rollout_module, "REPOSITORY_ROOT", root):
                    with self.assertRaisesRegex(
                        RolloutError,
                        "pinned official SGC index|malformed SGC geography",
                    ):
                        validate_rollout_contract(
                            catalog=catalog,
                            coverage_plan=coverage,
                            manifests=manifests,
                        )

    def test_sgc_index_is_bound_to_reviewed_release_digest(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            changed = json.loads(SGC_INDEX.read_text(encoding="utf-8"))
            changed["geographyIds"][-1] = (
                "ca:sgc:2021:census-subdivision:5999999"
            )
            digest_input = {
                field: value
                for field, value in changed.items()
                if field != "indexCanonicalSha256"
            }
            changed["indexCanonicalSha256"] = canonical_sha256(digest_input)
            changed_path = Path(temporary) / "sgc-index.json"
            changed_path.write_text(
                json.dumps(changed, sort_keys=True, indent=2) + "\n",
                encoding="utf-8",
            )
            with patch.object(
                rollout_module,
                "SGC_GEOGRAPHY_INDEX_PATH",
                changed_path,
            ):
                with self.assertRaisesRegex(
                    RolloutError,
                    "reviewed release digest",
                ):
                    validate_rollout_contract(
                        catalog=self.inputs.catalog,
                        coverage_plan=self.inputs.coverage_plan,
                        manifests=self.inputs.manifests,
                    )

    def test_crosswalk_source_key_must_match_provider_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            catalog, coverage, manifests, paths = (
                self._build_verified_on_promotion(root, complete=False)
            )
            rows = paths["crosswalk"].read_text(encoding="utf-8").splitlines()
            rows[1] = rows[1].replace("boundary-1813", "fabricated-key")
            paths["crosswalk"].write_text("\n".join(rows) + "\n", encoding="utf-8")
            with patch.object(rollout_module, "REPOSITORY_ROOT", root):
                with self.assertRaisesRegex(
                    RolloutError,
                    "differs from provider-emitted geography evidence",
                ):
                    validate_rollout_contract(
                        catalog=catalog,
                        coverage_plan=coverage,
                        manifests=manifests,
                    )

    def test_publication_release_reference_must_be_reviewable_on_github(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            catalog, coverage, manifests, paths = (
                self._build_verified_on_promotion(root, complete=True)
            )
            approval = json.loads(
                paths["approval"].read_text(encoding="utf-8")
            )
            approval["releaseReference"] = "trust-me"
            approval_bytes = (
                json.dumps(approval, sort_keys=True, indent=2) + "\n"
            ).encode("utf-8")
            paths["approval"].write_bytes(approval_bytes)
            manifests["ON"]["publicationApproval"]["releaseReference"] = "trust-me"
            manifests["ON"]["publicationApproval"]["artifactSha256"] = (
                hashlib.sha256(approval_bytes).hexdigest()
            )
            with patch.object(rollout_module, "REPOSITORY_ROOT", root):
                with self.assertRaisesRegex(
                    RolloutError,
                    "violates the rollout schema",
                ):
                    validate_rollout_contract(
                        catalog=catalog,
                        coverage_plan=coverage,
                        manifests=manifests,
                    )

    def test_publication_rejects_asserted_counts_that_differ_from_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            catalog, coverage, manifests, paths = (
                self._build_verified_on_promotion(root, complete=True)
            )
            reconciliation = json.loads(
                paths["reconciliation"].read_text(encoding="utf-8")
            )
            reconciliation["emittedCounts"][0]["count"] = 999
            paths["reconciliation"].write_text(
                json.dumps(reconciliation, sort_keys=True, indent=2) + "\n",
                encoding="utf-8",
            )
            with patch.object(rollout_module, "REPOSITORY_ROOT", root):
                with self.assertRaisesRegex(
                    RolloutError,
                    "must equal active records derived",
                ):
                    validate_rollout_contract(
                        catalog=catalog,
                        coverage_plan=coverage,
                        manifests=manifests,
                    )

    def test_source_lock_gate_verifies_digest_and_snapshot_identity(self) -> None:
        source_id = "test-municipal-source"
        payload = b"official\n"
        source = {
            "approvedSha256": hashlib.sha256(payload).hexdigest(),
            "requestUrl": "https://government.example/municipalities.csv",
            "mediaType": "text/csv",
            "recordKeyField": "id",
            "recordCollectionPath": "$",
        }
        source_bundle_digest = "b" * 64
        coverage_layer_digest = "c" * 64
        lock = {
            "schemaVersion": "auditback-jurisdiction-source-lock-1.0.0",
            "sourceBundleCanonicalSha256": source_bundle_digest,
            "coverageLayerCanonicalSha256": coverage_layer_digest,
            "snapshots": [
                {
                    "sourceId": source_id,
                    "sha256": source["approvedSha256"],
                    "byteLength": len(payload),
                    "mediaType": source["mediaType"],
                    "requestUrl": source["requestUrl"],
                    "retrievedAt": "2026-07-26T12:00:00Z",
                    "objectPath": "objects/official.csv",
                }
            ],
        }
        lock["sourceLockCanonicalSha256"] = canonical_sha256(lock)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "sources.lock.json"
            (root / "objects").mkdir()
            (root / "objects" / "official.csv").write_bytes(payload)
            path.write_text(
                json.dumps(lock),
                encoding="utf-8",
            )
            with patch.object(rollout_module, "REPOSITORY_ROOT", root):
                rollout_module._validate_source_lock(
                    path=path.name,
                    label="test lock",
                    source_ids=[source_id],
                    catalog_by_id={source_id: source},
                    source_bundle_canonical_sha256=source_bundle_digest,
                    coverage_layer_canonical_sha256=coverage_layer_digest,
                )
                changed = copy.deepcopy(lock)
                changed["snapshots"][0]["byteLength"] = 0
                del changed["sourceLockCanonicalSha256"]
                changed["sourceLockCanonicalSha256"] = canonical_sha256(changed)
                path.write_text(json.dumps(changed), encoding="utf-8")
                with self.assertRaisesRegex(RolloutError, "positive byteLength"):
                    rollout_module._validate_source_lock(
                        path=path.name,
                        label="test lock",
                        source_ids=[source_id],
                        catalog_by_id={source_id: source},
                        source_bundle_canonical_sha256=source_bundle_digest,
                        coverage_layer_canonical_sha256=coverage_layer_digest,
                    )

    def test_schema_rejects_unknown_manifest_fields(self) -> None:
        changed = copy.deepcopy(self.inputs.manifests)
        changed["ON"]["publicationBypass"] = True
        with self.assertRaisesRegex(RolloutError, "violates the rollout schema"):
            validate_rollout_contract(
                catalog=self.inputs.catalog,
                coverage_plan=self.inputs.coverage_plan,
                manifests=changed,
            )

    def test_reuse_gate_must_match_catalogue_approval(self) -> None:
        changed = copy.deepcopy(self.inputs.manifests)
        changed["MB"]["stages"][1] = {
            "id": "reuse-approved",
            "status": "complete",
        }
        with self.assertRaisesRegex(RolloutError, "approved licence"):
            validate_rollout_contract(
                catalog=self.inputs.catalog,
                coverage_plan=self.inputs.coverage_plan,
                manifests=changed,
            )

    def test_scaffold_is_candidate_only_and_refuses_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "ON"
            paths = scaffold_jurisdiction_workspace(
                code="on",
                output=output,
                catalog=self.inputs.catalog,
                coverage_plan=self.inputs.coverage_plan,
                manifests=self.inputs.manifests,
            )
            self.assertEqual(8, len(paths))
            candidate = json.loads(
                (output / "canonical-directory.json").read_text(encoding="utf-8")
            )
            self.assertTrue(candidate["candidateOnly"])
            self.assertEqual(
                "auditback-verified-jurisdiction-directory-1.0.0",
                candidate["schemaVersion"],
            )
            self.assertEqual([], candidate["records"])
            header = (output / "crosswalk-review.csv").read_text(
                encoding="utf-8"
            ).splitlines()[0]
            self.assertIn("sgcGeographyId", header)
            self.assertIn("snapshotSha256", header)
            classification_header = (
                output / "classification-decisions.csv"
            ).read_text(encoding="utf-8").splitlines()[0]
            self.assertIn("officialLegalType", classification_header)
            reconciliation = json.loads(
                (output / "reconciliation.json").read_text(encoding="utf-8")
            )
            self.assertFalse(reconciliation["reconciled"])
            self.assertTrue(reconciliation["candidateOnly"])
            approval = json.loads(
                (output / "publication-approval.json").read_text(encoding="utf-8")
            )
            self.assertTrue(approval["candidateOnly"])
            self.assertIsNone(approval["decision"])
            with self.assertRaisesRegex(RolloutError, "refusing to overwrite"):
                scaffold_jurisdiction_workspace(
                    code="ON",
                    output=output,
                    catalog=self.inputs.catalog,
                    coverage_plan=self.inputs.coverage_plan,
                    manifests=self.inputs.manifests,
                )

    def test_cli_check_and_json_status(self) -> None:
        check = subprocess.run(
            [sys.executable, str(SCRIPT), "check"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(0, check.returncode, check.stderr)
        self.assertIn("13 jurisdictions", check.stdout)
        self.assertIn("AI tokens: 0", check.stdout)
        status = subprocess.run(
            [sys.executable, str(SCRIPT), "status", "--format", "json"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(0, status.returncode, status.stderr)
        report = json.loads(status.stdout)
        self.assertEqual(13, report["summary"]["jurisdictionsTracked"])
        self.assertEqual(0, report["summary"]["jurisdictionsPublicationReady"])


if __name__ == "__main__":
    unittest.main()
