from __future__ import annotations

import copy
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "validate_regional_registry.py"
SPEC = importlib.util.spec_from_file_location("validate_regional_registry", SCRIPT)
assert SPEC and SPEC.loader
regional = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = regional
SPEC.loader.exec_module(regional)

PACK_SCRIPT = ROOT / "scripts" / "validate_pack.py"
PACK_SPEC = importlib.util.spec_from_file_location(
    "regional_test_validate_pack", PACK_SCRIPT
)
assert PACK_SPEC and PACK_SPEC.loader
pack_validator = importlib.util.module_from_spec(PACK_SPEC)
sys.modules[PACK_SPEC.name] = pack_validator
PACK_SPEC.loader.exec_module(pack_validator)

REGISTRY_PATH = ROOT / "geography" / "ontario-waterloo-test-ring.json"
LOCK_PATH = ROOT / "geography" / "ontario-waterloo-test-ring.sources.lock.json"


class RegionalRegistryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
        cls.source_lock = json.loads(LOCK_PATH.read_text(encoding="utf-8"))

    def test_checked_in_registry_and_corpus_are_valid(self) -> None:
        self.assertEqual(
            [],
            regional.validate_registry(copy.deepcopy(self.registry), root=ROOT),
        )

    def test_source_lock_binds_canonical_registry(self) -> None:
        self.assertEqual(
            [],
            regional.validate_source_lock(REGISTRY_PATH, self.source_lock),
        )

    def test_official_waterloo_codes_are_locked(self) -> None:
        by_slug = {
            row["slug"]: row["assessmentCode"]
            for row in self.registry["jurisdictions"]
        }
        self.assertEqual(regional.OFFICIAL_WATERLOO_CODES, {
            slug: by_slug[slug] for slug in regional.OFFICIAL_WATERLOO_CODES
        })

    def test_first_ring_is_derived_from_touch_endpoints(self) -> None:
        anchor = set(self.registry["anchor"]["memberSlugs"])
        derived = {
            neighbour
            for neighbours in self.registry["touchesBySlug"].values()
            for neighbour in neighbours
            if neighbour not in anchor
        }
        self.assertEqual(regional.EXPECTED_FIRST_RING, derived)

    def test_duplicate_assessment_code_fails_closed(self) -> None:
        changed = copy.deepcopy(self.registry)
        rows = {row["slug"]: row for row in changed["jurisdictions"]}
        rows["woolwich-on"]["assessmentCode"] = rows["wellesley-on"][
            "assessmentCode"
        ]
        errors = regional.validate_registry(changed, check_corpus=False)
        self.assertTrue(
            any("duplicate assessmentCode" in error for error in errors),
            errors,
        )

    def test_duplicate_municipal_or_mah_code_fails_closed(self) -> None:
        for field in ("municipalId", "mahCode"):
            with self.subTest(field=field):
                changed = copy.deepcopy(self.registry)
                rows = {row["slug"]: row for row in changed["jurisdictions"]}
                rows["wellington-county-on"][field] = rows["north-dumfries-on"][
                    field
                ]
                errors = regional.validate_registry(changed, check_corpus=False)
                self.assertTrue(
                    any(f"duplicate {field}" in error for error in errors),
                    errors,
                )

    def test_wrong_cambridge_or_woolwich_code_fails_closed(self) -> None:
        for slug, wrong_code in (
            ("cambridge-on", "3010"),
            ("woolwich-on", "3024"),
        ):
            with self.subTest(slug=slug):
                changed = copy.deepcopy(self.registry)
                next(
                    row for row in changed["jurisdictions"] if row["slug"] == slug
                )["assessmentCode"] = wrong_code
                errors = regional.validate_registry(changed, check_corpus=False)
                self.assertTrue(
                    any(
                        slug in error and "official assessmentCode" in error
                        for error in errors
                    ),
                    errors,
                )

    def test_missing_or_invalid_parent_fails_closed(self) -> None:
        changed = copy.deepcopy(self.registry)
        next(
            row
            for row in changed["jurisdictions"]
            if row["slug"] == "perth-east-on"
        )["parentSlug"] = "hamilton-on"
        errors = regional.validate_registry(changed, check_corpus=False)
        self.assertTrue(any("is not upper-tier" in error for error in errors), errors)

    def test_asymmetric_anchor_touch_fails_closed(self) -> None:
        changed = copy.deepcopy(self.registry)
        changed["touchesBySlug"]["cambridge-on"].remove("kitchener-on")
        errors = regional.validate_registry(changed, check_corpus=False)
        self.assertTrue(
            any("asymmetric anchor adjacency" in error for error in errors),
            errors,
        )

    def test_unknown_touch_endpoint_fails_closed(self) -> None:
        changed = copy.deepcopy(self.registry)
        changed["touchesBySlug"]["waterloo-on"].append("imaginary-on")
        changed["touchesBySlug"]["waterloo-on"].sort()
        errors = regional.validate_registry(changed, check_corpus=False)
        self.assertTrue(
            any("unknown touching slug" in error for error in errors),
            errors,
        )

    def test_external_edge_omission_fails_exact_topology_lock(self) -> None:
        changed_registry = copy.deepcopy(self.registry)
        changed_registry["touchesBySlug"]["cambridge-on"].remove("puslinch-on")
        changed_lock = copy.deepcopy(self.source_lock)
        # Simulate a maintainer updating only the broad registry hash. The
        # independent official touch snapshot must still catch the lost edge.
        changed_lock["registryCanonicalSha256"] = regional._canonical_sha256(
            changed_registry
        )
        errors = regional.validate_source_lock(
            REGISTRY_PATH,
            changed_lock,
            registry=changed_registry,
        )
        self.assertTrue(
            any("exact source-locked topology" in error for error in errors),
            errors,
        )

    def test_source_lock_metadata_and_counts_fail_closed(self) -> None:
        mutations = (
            (
                "service URL",
                lambda lock: lock["sources"][0].__setitem__(
                    "serviceUrl", "https://example.invalid/not-ontario"
                ),
                "serviceUrl",
            ),
            (
                "effective timestamp",
                lambda lock: lock["sources"][0].__setitem__(
                    "effectiveDatetime", "not-a-date"
                ),
                "effectiveDatetime",
            ),
            (
                "edge count",
                lambda lock: lock["derivation"].__setitem__(
                    "normalizedTouchEdgeCount", 999
                ),
                "normalizedTouchEdgeCount",
            ),
            (
                "anchor codes",
                lambda lock: lock["derivation"].__setitem__(
                    "anchorAssessmentCodes", ["3001"]
                ),
                "anchorAssessmentCodes",
            ),
        )
        for label, mutate, expected_error in mutations:
            with self.subTest(label=label):
                changed = copy.deepcopy(self.source_lock)
                mutate(changed)
                errors = regional.validate_source_lock(
                    REGISTRY_PATH,
                    changed,
                    registry=self.registry,
                )
                self.assertTrue(
                    any(expected_error in error for error in errors),
                    errors,
                )

    def test_existing_pack_requires_code_or_blocking_unsupported_status(self) -> None:
        base = """\
slug: cambridge-on
level: lower-tier
parentBodies:
  - region-of-waterloo-on
publication:
  status: draft
"""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            pack_dir = root / "corpus" / "cambridge-on"
            pack_dir.mkdir(parents=True)
            (pack_dir / "pack.yaml").write_text(base, encoding="utf-8")
            errors = regional.validate_registry(self.registry, root=root)
            self.assertTrue(
                any("missing assessmentCode" in error for error in errors),
                errors,
            )

            unsupported = base.replace(
                "level: lower-tier\n",
                "level: lower-tier\nidentityStatus: unsupported\n",
            )
            (pack_dir / "pack.yaml").write_text(unsupported, encoding="utf-8")
            (pack_dir / "build-inputs.yaml").write_text(
                """\
slug: cambridge-on
level: lower-tier
parentBodies:
  - region-of-waterloo-on
identityStatus: unsupported
""",
                encoding="utf-8",
            )
            self.assertEqual(
                [],
                regional.validate_registry(self.registry, root=root),
            )

            sealed = unsupported.replace("status: draft", "status: sealed")
            (pack_dir / "pack.yaml").write_text(sealed, encoding="utf-8")
            errors = regional.validate_registry(self.registry, root=root)
            self.assertTrue(
                any(
                    "requires publication.status draft or withdrawn" in error
                    for error in errors
                ),
                errors,
            )

    def test_existing_build_inputs_cannot_silently_omit_code(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            pack_dir = root / "corpus" / "cambridge-on"
            pack_dir.mkdir(parents=True)
            (pack_dir / "pack.yaml").write_text(
                """\
slug: cambridge-on
level: lower-tier
parentBodies:
  - region-of-waterloo-on
assessmentCode: "3006"
publication:
  status: draft
""",
                encoding="utf-8",
            )
            (pack_dir / "build-inputs.yaml").write_text(
                """\
slug: cambridge-on
level: lower-tier
parentBodies:
  - region-of-waterloo-on
""",
                encoding="utf-8",
            )
            errors = regional.validate_registry(self.registry, root=root)
            self.assertTrue(
                any(
                    "build-inputs.yaml" in error
                    and "missing assessmentCode" in error
                    for error in errors
                ),
                errors,
            )

    def test_unsupported_identity_blocks_strict_pack_validation(self) -> None:
        pack = {"identityStatus": "unsupported"}
        errors, warnings = pack_validator.check_identity_status(pack, strict=False)
        self.assertEqual([], errors)
        self.assertTrue(any("sealing is blocked" in warning for warning in warnings))

        errors, warnings = pack_validator.check_identity_status(pack, strict=True)
        self.assertEqual([], warnings)
        self.assertTrue(any("sealing is blocked" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
