from __future__ import annotations

import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from jsonschema import Draft202012Validator

from national.model_handoff import (
    CANDIDATE_SCHEMA_PATH,
    JOB_SCHEMA_PATH,
    TRUSTED_JOB_MANIFEST_PATH,
    TRUSTED_JOB_MANIFEST_SCHEMA_PATH,
    ModelHandoffError,
    _load_trusted_job_manifest,
    _validate_source_authority,
    _validate_target_against_directory,
    load_strict_json,
    parse_strict_json,
    validate_candidate,
    validate_handoff_files,
    validate_job,
)
from scripts.render_model_handoff_prompt import render_prompt


ROOT = Path(__file__).resolve().parents[1]
WELLESLEY_JOB_PATH = (
    ROOT
    / "handoffs"
    / "jobs"
    / "ontario-waterloo-2026"
    / "02-wellesley"
    / "job.json"
)
WILMOT_JOB_PATH = (
    ROOT
    / "handoffs"
    / "jobs"
    / "ontario-waterloo-2026"
    / "03-wilmot"
    / "job.json"
)
WELLESLEY_CLASSIFICATION_JOB_PATH = (
    ROOT
    / "handoffs"
    / "jobs"
    / "ontario-waterloo-2026"
    / "02-wellesley"
    / "classification"
    / "job.json"
)
WELLESLEY_PACKET_PATH = (
    WELLESLEY_CLASSIFICATION_JOB_PATH.parent / "prefetched-source-packet.json"
)
EXAMPLE_CANDIDATE_PATH = (
    ROOT / "handoffs" / "examples" / "wellesley-partial-candidate.json"
)
PACKET_SCHEMA_PATH = (
    ROOT / "national" / "schemas" / "prefetched-source-packet.schema.json"
)


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


class ModelHandoffTests(unittest.TestCase):
    def setUp(self) -> None:
        self.job = load(WELLESLEY_JOB_PATH)
        self.candidate = load(EXAMPLE_CANDIDATE_PATH)

    def assertRefused(self, job: dict, candidate: dict, text: str) -> None:
        with self.assertRaisesRegex(ModelHandoffError, text):
            validate_candidate(job, candidate)

    def complete_candidate(self) -> dict:
        candidate = copy.deepcopy(self.candidate)
        candidate["outcome"] = "complete"
        candidate["gaps"] = []
        candidate["sources"] = []
        authorities = {
            authority["authorityId"]: authority
            for authority in self.job["officialAuthorities"]
        }
        required = [
            document
            for document in self.job["requestedDocuments"]
            if document["required"]
        ]
        for index, document in enumerate(required, start=1):
            authority = authorities[document["authorityId"]]
            adoption_status = (
                "final"
                if document["documentType"] == "final-tax-rate-instrument"
                else "approved"
            )
            candidate["sources"].append(
                {
                    "sourceKey": f"S{index}",
                    "url": (
                        f"https://www.{authority['domains'][0]}/"
                        f"evidence-{index}.pdf"
                    ),
                    "publisher": authority["publisher"],
                    "title": f"Official evidence {index}",
                    "documentType": document["documentType"],
                    "authorityId": document["authorityId"],
                    "adoptionStatus": adoption_status,
                    "fiscalYear": document["fiscalYear"],
                    "governmentLevel": document["governmentLevel"],
                    "publicationDate": "2026-02-01",
                    "retrievedAt": "2026-07-26T18:00:00Z",
                    "contentType": "application/pdf",
                    "locator": "p. 1",
                    "exactExcerpt": "Final or approved evidence.",
                    "sourceContentSha256": "a" * 64,
                    "exactExcerptUtf8Sha256": hashlib.sha256(
                        b"Final or approved evidence."
                    ).hexdigest(),
                    "issueCodes": [],
                    "secondCheckRequired": True,
                }
            )
        return candidate

    def classification_candidate(self) -> dict:
        job = load(WELLESLEY_CLASSIFICATION_JOB_PATH)
        packet = load(WELLESLEY_PACKET_PATH)
        candidate = {
            "schemaVersion": (
                "whatinthetax-municipal-evidence-candidate-1.0.0"
            ),
            "jobId": job["jobId"],
            "jobCanonicalSha256": job["jobCanonicalSha256"],
            "packetCanonicalSha256": packet["packetCanonicalSha256"],
            "target": copy.deepcopy(job["target"]),
            "producer": {
                "provider": "anthropic",
                "model": "claude-sonnet-4-6",
                "accessMode": "subscription-cli",
                "runBindingAt": "2026-07-27T12:00:00Z",
            },
            "status": "pending-human-review",
            "outcome": "partial",
            "humanReviewRequired": True,
            "mayAutoPublish": False,
            "sources": [],
            "gaps": [],
        }
        copied_fields = (
            "sourceKey",
            "url",
            "publisher",
            "title",
            "documentType",
            "authorityId",
            "governmentLevel",
            "fiscalYear",
            "publicationDate",
            "retrievedAt",
            "contentType",
            "locator",
            "exactExcerpt",
            "sourceContentSha256",
            "exactExcerptUtf8Sha256",
        )
        covered = set()
        for packet_source in packet["sources"]:
            source = {
                field: copy.deepcopy(packet_source[field])
                for field in copied_fields
            }
            source["adoptionStatus"] = (
                "approved"
                if source["documentType"] == "approved-budget"
                else "final"
            )
            source["issueCodes"] = []
            source["secondCheckRequired"] = True
            candidate["sources"].append(source)
            covered.add(
                (
                    source["documentType"],
                    source["authorityId"],
                    source["governmentLevel"],
                    source["fiscalYear"],
                )
            )
        for document in job["requestedDocuments"]:
            key = (
                document["documentType"],
                document["authorityId"],
                document["governmentLevel"],
                document["fiscalYear"],
            )
            if document["required"] and key not in covered:
                candidate["gaps"].append(
                    {
                        "documentType": document["documentType"],
                        "authorityId": document["authorityId"],
                        "governmentLevel": document["governmentLevel"],
                        "fiscalYear": document["fiscalYear"],
                        "reasonCode": "not-yet-researched",
                        "searchTrail": [],
                        "note": "No packet excerpt covers this document.",
                    }
                )
        return candidate

    def test_checked_in_schemas_are_valid_draft_2020_12(self) -> None:
        for path in (
            JOB_SCHEMA_PATH,
            CANDIDATE_SCHEMA_PATH,
            TRUSTED_JOB_MANIFEST_SCHEMA_PATH,
            PACKET_SCHEMA_PATH,
        ):
            with self.subTest(schema=path.name):
                Draft202012Validator.check_schema(load(path))

    def test_seed_jobs_are_hash_bound_and_keep_original_order(self) -> None:
        wellesley = validate_job(self.job)
        wilmot = validate_job(load(WILMOT_JOB_PATH))
        self.assertEqual(
            [
                (wellesley["sequence"], wellesley["target"]["displayName"]),
                (wilmot["sequence"], wilmot["target"]["displayName"]),
            ],
            [(2, "Wellesley"), (3, "Wilmot")],
        )

    def test_example_candidate_passes_candidate_only_gate(self) -> None:
        result = validate_handoff_files(
            WELLESLEY_JOB_PATH,
            EXAMPLE_CANDIDATE_PATH,
        )
        self.assertTrue(result["valid"])
        self.assertEqual(result["status"], "pending-human-review")
        self.assertEqual(result["outcome"], "partial")
        self.assertEqual(result["sourceCount"], 1)
        self.assertEqual(result["gapCount"], 7)
        self.assertEqual(result["networkRequestsMade"], 0)
        self.assertFalse(result["canonicalDataWritten"])
        self.assertFalse(result["mayPublish"])
        self.assertRegex(result["candidateCanonicalSha256"], r"^[0-9a-f]{64}$")

    def test_rendered_prompt_is_self_contained_and_hash_bound(self) -> None:
        prompt = render_prompt(WELLESLEY_JOB_PATH)
        self.assertIn("evidence-mapping assistant, not a verifier", prompt)
        self.assertIn(self.job["jobId"], prompt)
        self.assertIn(self.job["jobCanonicalSha256"], prompt)
        self.assertIn(
            "whatinthetax-municipal-evidence-candidate-1.0.0",
            prompt,
        )
        self.assertNotIn("wellesley-partial-candidate", prompt)

    def test_classification_render_and_offline_gate_require_trusted_packet(
        self,
    ) -> None:
        with self.assertRaisesRegex(ModelHandoffError, "requires --packet"):
            render_prompt(WELLESLEY_CLASSIFICATION_JOB_PATH)
        rendered = render_prompt(
            WELLESLEY_CLASSIFICATION_JOB_PATH,
            WELLESLEY_PACKET_PATH,
        )
        packet = load(WELLESLEY_PACKET_PATH)
        self.assertIn("## PREFETCHED_PACKET_JSON", rendered)
        self.assertIn(packet["packetCanonicalSha256"], rendered)

        with tempfile.TemporaryDirectory() as temporary:
            candidate_path = Path(temporary) / "candidate.json"
            candidate_path.write_text(
                json.dumps(self.classification_candidate()),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                ModelHandoffError,
                "validation requires the trusted packet",
            ):
                validate_handoff_files(
                    WELLESLEY_CLASSIFICATION_JOB_PATH,
                    candidate_path,
                )
            result = validate_handoff_files(
                WELLESLEY_CLASSIFICATION_JOB_PATH,
                candidate_path,
                WELLESLEY_PACKET_PATH,
            )
            self.assertTrue(result["valid"])
            self.assertFalse(result["mayPublish"])

    def test_strict_parser_rejects_duplicate_keys(self) -> None:
        with self.assertRaisesRegex(ModelHandoffError, "duplicate JSON key"):
            parse_strict_json('{"status":"candidate","status":"published"}')

    def test_strict_parser_rejects_floats_and_non_finite_numbers(self) -> None:
        for payload in ('{"amount":1.25}', '{"amount":NaN}'):
            with self.subTest(payload=payload):
                with self.assertRaises(ModelHandoffError):
                    parse_strict_json(payload)

    def test_strict_parser_normalizes_recursion_failures(self) -> None:
        payload = "[" * 2000 + "0" + "]" * 2000
        with self.assertRaisesRegex(ModelHandoffError, "nesting limit"):
            parse_strict_json(payload)

    def test_tampered_job_hash_is_rejected(self) -> None:
        tampered = copy.deepcopy(self.job)
        tampered["target"]["officialName"] = "Different Township"
        with self.assertRaisesRegex(ModelHandoffError, "does not match job content"):
            validate_job(tampered)

    def test_recomputed_external_job_is_not_trusted(self) -> None:
        external = copy.deepcopy(self.job)
        external["target"]["displayName"] = "Invented Place"
        external["target"]["officialName"] = "Invented Place"
        from national.models import canonical_sha256

        external["jobCanonicalSha256"] = canonical_sha256(
            {
                key: value
                for key, value in external.items()
                if key != "jobCanonicalSha256"
            }
        )
        with self.assertRaisesRegex(
            ModelHandoffError,
            "not present in the checked-in trusted job manifest",
        ):
            validate_job(external)

    def test_manifest_binds_prompt_and_candidate_schema_digests(self) -> None:
        manifest = load(TRUSTED_JOB_MANIFEST_PATH)
        cases = (
            ("prompt", "utf8Sha256", "trusted handoff prompt digest"),
            (
                "candidateSchema",
                "canonicalSha256",
                "trusted candidate schema digest",
            ),
        )
        with tempfile.TemporaryDirectory() as temporary:
            manifest_path = Path(temporary) / "manifest.json"
            for section, field, message in cases:
                with self.subTest(section=section):
                    changed = copy.deepcopy(manifest)
                    changed[section][field] = "0" * 64
                    manifest_path.write_text(
                        json.dumps(changed),
                        encoding="utf-8",
                    )
                    with patch(
                        "national.model_handoff.TRUSTED_JOB_MANIFEST_PATH",
                        manifest_path,
                    ):
                        with self.assertRaisesRegex(ModelHandoffError, message):
                            validate_job(self.job)

    def test_target_identity_matches_canonical_directory(self) -> None:
        manifest = load(TRUSTED_JOB_MANIFEST_PATH)
        directory = load(ROOT / manifest["targetDirectories"][0]["path"])
        _validate_target_against_directory(self.job["target"], directory)

        changed = copy.deepcopy(self.job["target"])
        changed["assessmentCode"] = "9999"
        with self.assertRaisesRegex(ModelHandoffError, "trusted directory fields"):
            _validate_target_against_directory(changed, directory)

    def test_manifest_binds_jobs_to_directory_paths_and_record_ids(self) -> None:
        manifest = load(TRUSTED_JOB_MANIFEST_PATH)
        self.assertIsInstance(manifest["targetDirectories"], list)
        self.assertEqual(
            manifest["targetDirectories"][0]["jurisdiction"],
            "CA-ON",
        )
        for entry in manifest["jobs"]:
            self.assertIn("targetDirectoryPath", entry)
            self.assertIn("targetRecordId", entry)
            self.assertNotIn("targetDirectoryId", entry)

    def test_manifest_rejects_cross_job_authority_identity_drift(self) -> None:
        manifest = load(TRUSTED_JOB_MANIFEST_PATH)
        changed_job = load(WILMOT_JOB_PATH)
        changed_job["officialAuthorities"][1]["publisher"] = (
            "Different regional publisher"
        )
        from national.models import canonical_sha256

        changed_job["jobCanonicalSha256"] = canonical_sha256(
            {
                key: value
                for key, value in changed_job.items()
                if key != "jobCanonicalSha256"
            }
        )
        for entry in manifest["jobs"]:
            if entry["jobId"] == changed_job["jobId"]:
                entry["jobCanonicalSha256"] = changed_job[
                    "jobCanonicalSha256"
                ]

        original_loader = load_strict_json

        def altered_loader(path: str | Path) -> object:
            if Path(path).resolve() == WILMOT_JOB_PATH.resolve():
                return copy.deepcopy(changed_job)
            return original_loader(path)

        with tempfile.TemporaryDirectory() as temporary:
            manifest_path = Path(temporary) / "manifest.json"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            with (
                patch(
                    "national.model_handoff.TRUSTED_JOB_MANIFEST_PATH",
                    manifest_path,
                ),
                patch(
                    "national.model_handoff.load_strict_json",
                    side_effect=altered_loader,
                ),
            ):
                with self.assertRaisesRegex(
                    ModelHandoffError,
                    "reuse an authorityId with a different identity",
                ):
                    _load_trusted_job_manifest()

    def test_alphanumeric_non_ontario_target_identity_is_supported(self) -> None:
        target = copy.deepcopy(self.job["target"])
        target.update(
            {
                "directoryId": "ca:nb:csd:abc12",
                "assessmentCode": "ABC-12",
                "externalIdNamespace": "statcan-csd",
                "displayName": "Example",
                "officialName": "City of Example",
                "provinceTerritory": "NB",
                "governmentTier": "single-tier",
                "geographicArea": "Example County",
                "governsGeographyIds": ["ca:nb:csd:abc12"],
                "parentBody": None,
            }
        )
        directory = {
            "schemaVersion": "auditback-canonical-government-directory-3.0.0",
            "jurisdiction": "CA-NB",
            "records": [
                {
                    "id": "ca:nb:csd:abc12",
                    "bodyType": "municipal-government",
                    "status": "active",
                    "officialNames": {"en": "City of Example"},
                    "provinceTerritory": "NB",
                    "officialUrl": "https://example.ca/",
                    "externalIds": {"statcan-csd": "ABC-12"},
                    "governsGeographyIds": ["ca:nb:csd:abc12"],
                    "officialLegalType": "City",
                    "governmentTier": "single-tier",
                    "parentBodyIds": [],
                    "effectiveFrom": "2026-01-01",
                    "effectiveTo": None,
                }
            ],
        }
        _validate_target_against_directory(
            target,
            directory,
            target_record_id="ca:nb:csd:abc12",
        )

        mutations = {
            "officialName": ("officialNames", {"en": "Wrong city"}),
            "assessmentCode": ("externalIds", {"statcan-csd": "WRONG"}),
            "governmentTier": ("governmentTier", "lower-tier"),
            "provinceTerritory": ("provinceTerritory", "NS"),
            "status": ("status", "inactive"),
            "governsGeographyIds": (
                "governsGeographyIds",
                ["ca:nb:csd:different"],
            ),
            "parentBodyIds": (
                "parentBodyIds",
                ["ca:nb:region:different"],
            ),
        }
        for label, (field, value) in mutations.items():
            with self.subTest(binding=label):
                changed_directory = copy.deepcopy(directory)
                changed_directory["records"][0][field] = value
                with self.assertRaisesRegex(
                    ModelHandoffError,
                    "trusted directory fields",
                ):
                    _validate_target_against_directory(
                        target,
                        changed_directory,
                        target_record_id="ca:nb:csd:abc12",
                    )

        changed_job = copy.deepcopy(self.job)
        changed_job["jobId"] = "NB-ABC-12-FY2026-source-map"
        changed_job["target"] = target
        schema = load(JOB_SCHEMA_PATH)
        errors = list(Draft202012Validator(schema).iter_errors(changed_job))
        self.assertEqual(errors, [])

    def test_candidate_cannot_switch_jobs_or_municipalities(self) -> None:
        wrong_job = copy.deepcopy(self.candidate)
        wrong_job["jobId"] = "ON-3018-FY2026-source-map"
        self.assertRefused(self.job, wrong_job, "jobId does not match")

        wrong_target = copy.deepcopy(self.candidate)
        wrong_target["target"]["assessmentCode"] = "3018"
        self.assertRefused(self.job, wrong_target, "target does not exactly match")

    def test_official_authority_domain_allowlist_is_enforced(self) -> None:
        changed = copy.deepcopy(self.candidate)
        changed["sources"][0]["url"] = "https://example.com/budget.pdf"
        self.assertRefused(self.job, changed, "outside.*official authority lane")

    def test_government_level_cannot_cross_satisfy_authority_lane(self) -> None:
        changed = copy.deepcopy(self.candidate)
        changed["sources"][0][
            "url"
        ] = "https://www.regionofwaterloo.ca/budget.pdf"
        changed["sources"][0][
            "publisher"
        ] = "Regional Municipality of Waterloo"
        self.assertRefused(self.job, changed, "official authority lane")

        changed = copy.deepcopy(self.candidate)
        changed["sources"][0]["publisher"] = "Regional Municipality of Waterloo"
        self.assertRefused(
            self.job,
            changed,
            "authorityId, publisher, host, and governmentLevel",
        )

    def test_authority_id_is_exact_even_when_domains_are_shared(self) -> None:
        job = {
            "officialAuthorities": [
                {
                    "authorityId": "ca-nb-first",
                    "governmentLevel": "special-purpose",
                    "publisher": "First Authority",
                    "domains": ["shared.example.ca"],
                },
                {
                    "authorityId": "ca-nb-second",
                    "governmentLevel": "special-purpose",
                    "publisher": "Second Authority",
                    "domains": ["shared.example.ca"],
                },
            ]
        }
        source = {
            "authorityId": "ca-nb-second",
            "governmentLevel": "special-purpose",
            "publisher": "Second Authority",
            "url": "https://shared.example.ca/evidence.pdf",
        }
        _validate_source_authority(job, source, label="source")

        source["publisher"] = "First Authority"
        with self.assertRaisesRegex(ModelHandoffError, "same official authority"):
            _validate_source_authority(job, source, label="source")

    def test_candidate_packet_binding_depends_on_task_type(self) -> None:
        changed = copy.deepcopy(self.candidate)
        changed["packetCanonicalSha256"] = "a" * 64
        self.assertRefused(
            self.job,
            changed,
            "source-discovery candidate packetCanonicalSha256 must be null",
        )

        classification_job = load(WELLESLEY_CLASSIFICATION_JOB_PATH)
        packet = load(WELLESLEY_PACKET_PATH)
        classification_candidate = copy.deepcopy(self.candidate)
        classification_candidate["jobId"] = classification_job["jobId"]
        classification_candidate["jobCanonicalSha256"] = classification_job[
            "jobCanonicalSha256"
        ]
        classification_candidate["packetCanonicalSha256"] = packet[
            "packetCanonicalSha256"
        ]
        classification_candidate["target"] = classification_job["target"]
        classification_candidate["sources"] = []
        classification_candidate["gaps"] = [
            {
                "documentType": document["documentType"],
                "authorityId": document["authorityId"],
                "governmentLevel": document["governmentLevel"],
                "fiscalYear": document["fiscalYear"],
                "reasonCode": "not-yet-researched",
                "searchTrail": [],
                "note": "No model research was performed.",
            }
            for document in classification_job["requestedDocuments"]
            if document["required"]
        ]
        classification_candidate["outcome"] = "no-official-source-found"
        validate_candidate(classification_job, classification_candidate)

        classification_candidate["packetCanonicalSha256"] = None
        self.assertRefused(
            classification_job,
            classification_candidate,
            "extract-candidates candidate requires packetCanonicalSha256",
        )

    def test_prefetched_packet_is_hash_bound_and_authority_bound(self) -> None:
        from national.models import canonical_sha256

        packet = load(WELLESLEY_PACKET_PATH)
        schema = load(PACKET_SCHEMA_PATH)
        self.assertEqual(
            list(Draft202012Validator(schema).iter_errors(packet)),
            [],
        )
        observed = canonical_sha256(
            {
                key: value
                for key, value in packet.items()
                if key != "packetCanonicalSha256"
            }
        )
        self.assertEqual(packet["packetCanonicalSha256"], observed)
        requested = {
            (
                document["documentType"],
                document["authorityId"],
                document["governmentLevel"],
                document["fiscalYear"],
            )
            for document in load(WELLESLEY_CLASSIFICATION_JOB_PATH)[
                "requestedDocuments"
            ]
        }
        for source in packet["sources"]:
            self.assertIn(
                (
                    source["documentType"],
                    source["authorityId"],
                    source["governmentLevel"],
                    source["fiscalYear"],
                ),
                requested,
            )

    def test_source_provenance_hash_and_binding_timestamp_are_checked(self) -> None:
        changed = copy.deepcopy(self.candidate)
        changed["producer"]["completedAt"] = changed["producer"].pop("runBindingAt")
        self.assertRefused(self.job, changed, "candidate schema rejected")

        changed = self.complete_candidate()
        changed["sources"][0]["exactExcerptUtf8Sha256"] = "0" * 64
        self.assertRefused(self.job, changed, "does not match exactExcerpt")

        changed = self.complete_candidate()
        changed["sources"][0]["contentType"] = None
        self.assertRefused(self.job, changed, "wholly captured or wholly null")

    def test_gap_search_trail_stays_in_government_level_lane(self) -> None:
        changed = copy.deepcopy(self.candidate)
        changed["gaps"][0]["searchTrail"] = [
            {
                "authorityId": "ca-on-wellesley",
                "url": "https://www.regionofwaterloo.ca/budget.pdf",
            }
        ]
        self.assertRefused(self.job, changed, "outside.*official authority lane")

        shared_domain = copy.deepcopy(self.candidate)
        shared_domain["gaps"][0]["searchTrail"] = [
            {
                "authorityId": "ca-on-waterloo-region",
                "url": "https://www.wellesley.ca/budget.pdf",
            }
        ]
        self.assertRefused(
            self.job,
            shared_domain,
            "searchTrail authorityId does not match the gap authority",
        )

    def test_unrequested_year_is_rejected(self) -> None:
        changed = copy.deepcopy(self.candidate)
        changed["sources"][0]["fiscalYear"] = 2023
        self.assertRefused(self.job, changed, "does not answer a requested document")

    def test_api_access_and_publication_claims_are_schema_rejected(self) -> None:
        api = copy.deepcopy(self.candidate)
        api["producer"]["accessMode"] = "api"
        self.assertRefused(self.job, api, "candidate schema rejected")

        publish = copy.deepcopy(self.candidate)
        publish["mayAutoPublish"] = True
        self.assertRefused(self.job, publish, "candidate schema rejected")

        verified = copy.deepcopy(self.candidate)
        verified["verificationStatus"] = "verified"
        self.assertRefused(self.job, verified, "candidate schema rejected")

    def test_unknown_fields_are_rejected_at_nested_boundaries(self) -> None:
        changed = copy.deepcopy(self.candidate)
        changed["sources"][0]["confidence"] = 0.99
        self.assertRefused(self.job, changed, "candidate schema rejected")

    def test_missing_excerpt_must_be_flagged(self) -> None:
        changed = copy.deepcopy(self.candidate)
        changed["sources"][0]["issueCodes"] = [
            "date-unclear",
            "status-unclear",
        ]
        self.assertRefused(self.job, changed, "excerpt-not-captured")

    def test_issue_date_status_and_adoption_invariants(self) -> None:
        cases: list[tuple[str, dict, str]] = []

        missing_date_issue = copy.deepcopy(self.candidate)
        missing_date_issue["sources"][0]["issueCodes"].remove("date-unclear")
        cases.append(("missing-date-issue", missing_date_issue, "date-unclear"))

        stale_date_issue = copy.deepcopy(self.candidate)
        stale_date_issue["sources"][0]["publicationDate"] = "2026-01-01"
        cases.append(("stale-date-issue", stale_date_issue, "date-unclear"))

        missing_status_issue = copy.deepcopy(self.candidate)
        missing_status_issue["sources"][0]["issueCodes"].remove("status-unclear")
        cases.append(
            ("missing-status-issue", missing_status_issue, "status-unclear")
        )

        incompatible_adoption = self.complete_candidate()
        incompatible_adoption["sources"][0]["adoptionStatus"] = "final"
        cases.append(
            (
                "incompatible-adoption",
                incompatible_adoption,
                "adoptionStatus is incompatible",
            )
        )

        for label, changed, message in cases:
            with self.subTest(case=label):
                self.assertRefused(self.job, changed, message)

    def test_non_closing_sources_require_matching_gaps(self) -> None:
        cases = (
            ("draft", [], "only-draft-found"),
            ("unknown", ["status-unclear"], "status-unclear"),
        )
        for adoption_status, issues, _gap_reason in cases:
            with self.subTest(adoption_status=adoption_status):
                changed = self.complete_candidate()
                changed["sources"][0]["adoptionStatus"] = adoption_status
                changed["sources"][0]["issueCodes"] = issues
                self.assertRefused(
                    self.job,
                    changed,
                    "non-closing source requires a matching gap",
                )

        changed = self.complete_candidate()
        changed["sources"][0]["exactExcerpt"] = None
        changed["sources"][0]["exactExcerptUtf8Sha256"] = None
        changed["sources"][0]["locator"] = None
        changed["sources"][0]["issueCodes"] = ["excerpt-not-captured"]
        self.assertRefused(
            self.job,
            changed,
            "non-closing source requires a matching gap",
        )

    def test_source_gap_overlap_requires_explicit_non_closing_semantics(self) -> None:
        changed = self.complete_candidate()
        source = changed["sources"][0]
        changed["outcome"] = "partial"
        changed["gaps"] = [
            {
                "documentType": source["documentType"],
                "authorityId": source["authorityId"],
                "governmentLevel": source["governmentLevel"],
                "fiscalYear": source["fiscalYear"],
                "reasonCode": "not-found",
                "searchTrail": [
                    {
                        "authorityId": source["authorityId"],
                        "url": source["url"],
                    }
                ],
                "note": "Contradicts the closing source.",
            }
        ]
        self.assertRefused(
            self.job,
            changed,
            "source and gap overlap.*explicit non-closing",
        )

        result = validate_candidate(self.job, self.candidate)
        self.assertEqual(result["outcome"], "partial")

    def test_gap_search_trail_invariants(self) -> None:
        changed = copy.deepcopy(self.candidate)
        changed["gaps"][1]["reasonCode"] = "not-found"
        self.assertRefused(self.job, changed, "requires an official searchTrail")

        changed = copy.deepcopy(self.candidate)
        changed["gaps"][1]["searchTrail"] = [
            {
                "authorityId": "ca-on-wellesley",
                "url": "https://www.wellesley.ca/taxes/",
            }
        ]
        self.assertRefused(
            self.job,
            changed,
            "not-yet-researched must have an empty searchTrail",
        )

    def test_extract_candidate_jobs_cannot_enable_browsing(self) -> None:
        changed = copy.deepcopy(self.job)
        changed["taskType"] = "extract-candidates"
        from national.models import canonical_sha256

        changed["jobCanonicalSha256"] = canonical_sha256(
            {
                key: value
                for key, value in changed.items()
                if key != "jobCanonicalSha256"
            }
        )
        with self.assertRaisesRegex(ModelHandoffError, "must disable web search"):
            validate_job(changed)

    def test_unsupported_review_conflict_task_is_schema_rejected(self) -> None:
        changed = copy.deepcopy(self.job)
        changed["taskType"] = "review-conflict"
        from national.models import canonical_sha256

        changed["jobCanonicalSha256"] = canonical_sha256(
            {
                key: value
                for key, value in changed.items()
                if key != "jobCanonicalSha256"
            }
        )
        with self.assertRaisesRegex(ModelHandoffError, "job schema rejected"):
            validate_job(changed)

    def test_secret_like_text_and_local_paths_are_rejected(self) -> None:
        secret = copy.deepcopy(self.candidate)
        secret["gaps"][0]["note"] = "token sk-" + "A" * 30
        self.assertRefused(self.job, secret, "credential-like")

        local_path = copy.deepcopy(self.candidate)
        local_path["gaps"][0]["note"] = r"read C:\Users\Operator\secret.txt"
        self.assertRefused(self.job, local_path, "local filesystem path")

        private_contact = copy.deepcopy(self.candidate)
        private_contact["gaps"][0]["note"] = "Resident SIN 046 454 286"
        self.assertRefused(self.job, private_contact, "valid SIN-like")

        cases = (
            ("email address", "Contact resident@example.ca"),
            ("phone number", "Call 519-555-1234"),
            (
                "credential-like",
                "Bearer eyJabcdefgh.ijklmnop.qrstuvwx",
            ),
        )
        for message, note in cases:
            with self.subTest(message=message):
                changed = copy.deepcopy(self.candidate)
                changed["gaps"][0]["note"] = note
                self.assertRefused(self.job, changed, message)

    def test_outcome_must_agree_with_sources_and_gaps(self) -> None:
        changed = copy.deepcopy(self.candidate)
        changed["outcome"] = "complete"
        self.assertRefused(self.job, changed, "outcome complete")

        changed = copy.deepcopy(self.candidate)
        changed["outcome"] = "no-official-source-found"
        self.assertRefused(self.job, changed, "zero sources")


if __name__ == "__main__":
    unittest.main()
