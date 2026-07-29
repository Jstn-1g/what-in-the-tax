#!/usr/bin/env python3
"""Build deterministic, browser-safe receipt packs from the internal ledgers."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
# The root data/ tree is canonical. web/src/data is a compatibility copy and
# must never become an independent publication source.
DATA_ROOT = ROOT / "data"
OUTPUT_ROOT = ROOT / "web" / "public" / "packs"

PACK_INPUTS = {
    "north-dumfries-on": DATA_ROOT,
    "brant-county-on": DATA_ROOT / "brant",
    "kitchener-on": DATA_ROOT / "kitchener",
    "waterloo-on": DATA_ROOT / "waterloo",
    "cambridge-on": DATA_ROOT / "cambridge",
    "woolwich-on": DATA_ROOT / "woolwich",
}
PACK_FISCAL_YEARS = {pack_id: 2026 for pack_id in PACK_INPUTS}

RECEIPT_SCALAR_FIELDS = (
    "schemaVersion",
    "artifact",
    "fiscalYear",
    "currency",
    "status",
    "purpose",
)
PUBLISHER_FIELDS = ("name", "role")
LICENSE_FIELDS = ("spdx", "scope", "sourceDocuments")
CORRECTIONS_ROUTE_FIELDS = ("type", "url", "status")
PUBLICATION_APPROVAL_FIELDS = ("status", "approvedBy", "approvedAt")
COVERAGE_FIELDS = (
    "status",
    "tier",
    "fiscalYear",
    "currency",
    "geography",
    "assessmentClass",
    "included",
    "excluded",
    "findingsCount",
    "openGapsCount",
)
SOURCE_COVERAGE_FIELDS = (
    "receiptDrivingSources",
    "reviewedSourceAndExtractPairs",
    "citedFacts",
    "loadBearingFacts",
)
CITATION_EXPECTED_FIELDS = (
    "verbatim",
    "normalized",
    "hardFailures",
    "bindingIssues",
)
JURISDICTION_FIELDS = ("slug", "displayName", "level", "aliases")
PROFILE_BUCKET_FIELDS = (
    "basis",
    "amountCad",
    "assessmentCad",
    "evidenceStatus",
    "sourceFactId",
    "gapId",
    "warnings",
    "note",
    "uiLabel",
)
RECEIPT_LINE_FIELDS = (
    "id",
    "label",
    "amountCad",
    "classification",
    "evidenceStatus",
    "sourceFactId",
    "gapId",
    "note",
)
COMBINED_COMPONENT_FIELDS = ("label", "amountCad", "rate", "sourceFactId")
AYR_VARIANT_FIELDS = (
    "specialAreaRateCad",
    "totalCad",
    "totalRate",
    "note",
)
HYPOTHETICAL_SHARE_FIELDS = ("label", "share", "sourceFactId")
FINDING_FIELDS = (
    "id",
    "kind",
    "category",
    "title",
    "opportunitySeverity",
    "citedFactIds",
    "evidenceSummary",
    "billImpactCad",
    "townshipResponse",
    "belowMateriality",
    "gapIds",
)
PUBLIC_UI_HINT_FIELDS = (
    "defaultProfile",
    "showGapsAsFirstClassUi",
    "forbidFillerAllocation",
    "municipalBucketLabel",
    "regionBucketLabel",
    "heroLabel",
)
SOURCE_FIELDS = ("id", "title", "url", "asOf", "authority")
FACT_FIELDS = (
    "id",
    "sourceId",
    "page",
    "label",
    "amountCad",
    "value",
    "excerpt",
    "status",
    "kind",
    "url",
)
DERIVED_FIELDS = ("id", "label", "amountCad", "formula", "inputs", "kind")
GAP_FIELDS = (
    "id",
    "kind",
    "title",
    "detail",
    "blocks",
    "neededEvidence",
    "disposition",
)

BANNED_PUBLIC_KEYS = {
    "closedGaps",
    "extractedText",
    "localPath",
    "searchTrail",
    "suppressed",
}


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def pick_fields(value: dict[str, Any], fields: Iterable[str]) -> dict[str, Any]:
    return {field: value[field] for field in fields if field in value}


def approved_finding_ids(receipt: dict[str, Any]) -> set[str]:
    """Findings require explicit human sign-off metadata, not a UI hint alone."""
    review = receipt.get("publicationReview")
    if not isinstance(review, dict) or review.get("status") != "approved":
        return set()
    if not review.get("signedOffBy") or not review.get("signedOffAt"):
        return set()
    ids = review.get("approvedFindingIds")
    return {value for value in ids if isinstance(value, str)} if isinstance(ids, list) else set()


def as_object(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def project_line_items(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [
        pick_fields(item, RECEIPT_LINE_FIELDS)
        for item in value
        if isinstance(item, dict)
    ]


def project_profile_bucket(value: Any) -> dict[str, Any]:
    bucket = as_object(value)
    projected = pick_fields(bucket, PROFILE_BUCKET_FIELDS)
    if "lineItems" in bucket:
        projected["lineItems"] = project_line_items(bucket["lineItems"])
    return projected


def project_region_illustration(value: Any) -> dict[str, Any]:
    illustration = as_object(value)
    projected = project_profile_bucket(illustration)
    projected.update(
        pick_fields(illustration, ("description", "lineItemsSumCheckCad"))
    )
    return projected


def project_combined_assessment(value: Any) -> dict[str, Any]:
    combined = as_object(value)
    projected = pick_fields(
        combined,
        (
            "assessmentCad",
            "basis",
            "evidenceStatus",
            "totalCad",
            "totalRate",
        ),
    )
    projected["components"] = [
        pick_fields(component, COMBINED_COMPONENT_FIELDS)
        for component in combined.get("components", [])
        if isinstance(component, dict)
    ]
    if isinstance(combined.get("ayrUrbanVariant"), dict):
        projected["ayrUrbanVariant"] = pick_fields(
            combined["ayrUrbanVariant"], AYR_VARIANT_FIELDS
        )
    return projected


TAXING_BODY_FIELDS = (
    "id",
    "role",
    "label",
    "order",
    "amountCad",
    "basis",
    "evidenceStatus",
    "assessmentCad",
    "sourceFactId",
    "gapId",
    "lineItems",
    "warnings",
    "note",
    "uiLabel",
)


def project_supported_profile(value: Any) -> dict[str, Any]:
    profile = as_object(value)
    projected = pick_fields(
        profile,
        (
            "description",
            "combinedTotalCad",
            "combinedTotalNote",
            "warnings",
        ),
    )
    # The bill as declared bodies. Projected field-by-field like everything else
    # here, so a builder cannot smuggle an unreviewed key into a public artifact
    # by adding it upstream.
    bodies = profile.get("taxingBodies")
    if isinstance(bodies, list) and bodies:
        projected["taxingBodies"] = [
            pick_fields(as_object(body), TAXING_BODY_FIELDS) for body in bodies
        ]
    inapplicable = profile.get("inapplicableBodies")
    if isinstance(inapplicable, list) and inapplicable:
        projected["inapplicableBodies"] = [
            pick_fields(as_object(entry), ("role", "reason")) for entry in inapplicable
        ]
    for bucket_name in ("township", "region", "education"):
        projected[bucket_name] = project_profile_bucket(profile.get(bucket_name))
    if isinstance(profile.get("regionIllustrationAt354500"), dict):
        projected["regionIllustrationAt354500"] = project_region_illustration(
            profile["regionIllustrationAt354500"]
        )
    if isinstance(profile.get("combinedAtAssessment"), dict):
        projected["combinedAtAssessment"] = project_combined_assessment(
            profile["combinedAtAssessment"]
        )
    return projected


def project_hypothetical_profile(value: Any) -> dict[str, Any]:
    profile = as_object(value)
    projected = pick_fields(
        profile,
        (
            "amountCad",
            "evidenceStatus",
            "gapId",
            "allocatable",
            "impliedAssessmentCad",
            "message",
        ),
    )
    if "compositionShares" in profile:
        projected["compositionShares"] = [
            pick_fields(share, HYPOTHETICAL_SHARE_FIELDS)
            for share in profile.get("compositionShares", [])
            if isinstance(share, dict)
        ]
    return projected


def project_receipt(receipt: dict[str, Any]) -> dict[str, Any]:
    projected = pick_fields(receipt, RECEIPT_SCALAR_FIELDS)
    if isinstance(receipt.get("publisher"), dict):
        projected["publisher"] = pick_fields(
            receipt["publisher"], PUBLISHER_FIELDS
        )
    if isinstance(receipt.get("license"), dict):
        projected["license"] = pick_fields(receipt["license"], LICENSE_FIELDS)
    if isinstance(receipt.get("correctionsRoute"), dict):
        projected["correctionsRoute"] = pick_fields(
            receipt["correctionsRoute"], CORRECTIONS_ROUTE_FIELDS
        )
    if isinstance(receipt.get("publicationApproval"), dict):
        projected["publicationApproval"] = pick_fields(
            receipt["publicationApproval"], PUBLICATION_APPROVAL_FIELDS
        )
    if isinstance(receipt.get("coverage"), dict):
        source_coverage = as_object(receipt["coverage"].get("sourceCoverage"))
        citation_expected = as_object(
            source_coverage.get("citationAuditExpected")
        )
        projected_source_coverage = pick_fields(
            source_coverage, SOURCE_COVERAGE_FIELDS
        )
        if citation_expected:
            projected_source_coverage["citationAuditExpected"] = pick_fields(
                citation_expected, CITATION_EXPECTED_FIELDS
            )
        projected["coverage"] = {
            **pick_fields(receipt["coverage"], COVERAGE_FIELDS),
            **(
                {"sourceCoverage": projected_source_coverage}
                if projected_source_coverage
                else {}
            ),
        }
    projected["evidencePolicyRef"] = "Evidence included with this preview"
    projected["jurisdiction"] = pick_fields(
        as_object(receipt.get("jurisdiction")), JURISDICTION_FIELDS
    )
    profiles = as_object(receipt.get("profiles"))
    projected["profiles"] = {
        "supportedAverageHousehold": project_supported_profile(
            profiles.get("supportedAverageHousehold")
        ),
        "hypothetical5000": project_hypothetical_profile(
            profiles.get("hypothetical5000")
        ),
    }

    approved_ids = approved_finding_ids(receipt)
    projected["findings"] = [
        pick_fields(finding, FINDING_FIELDS)
        for finding in receipt.get("findings", [])
        if isinstance(finding, dict) and finding.get("id") in approved_ids
    ]

    source_hints = as_object(receipt.get("uiModelHints"))
    hints = pick_fields(source_hints, PUBLIC_UI_HINT_FIELDS)
    if not isinstance(hints.get("defaultProfile"), str) or not hints["defaultProfile"]:
        hints["defaultProfile"] = "supportedAverageHousehold"
    if not isinstance(hints.get("showGapsAsFirstClassUi"), bool):
        hints["showGapsAsFirstClassUi"] = True
    if not isinstance(hints.get("forbidFillerAllocation"), bool):
        hints["forbidFillerAllocation"] = True
    hints["publishedFindingIds"] = [
        value
        for value in source_hints.get("publishedFindingIds", [])
        if value in approved_ids
    ]
    hints["marqueeFindings"] = [
        value for value in source_hints.get("marqueeFindings", []) if value in approved_ids
    ]
    projected["uiModelHints"] = hints
    return projected


def collect_known_references(value: Any, known_ids: set[str]) -> set[str]:
    references: set[str] = set()
    if isinstance(value, str):
        if value in known_ids:
            references.add(value)
    elif isinstance(value, dict):
        for child in value.values():
            references.update(collect_known_references(child, known_ids))
    elif isinstance(value, list):
        for child in value:
            references.update(collect_known_references(child, known_ids))
    return references


def project_evidence(
    ledger: dict[str, Any], public_receipt: dict[str, Any]
) -> tuple[dict[str, Any], set[str]]:
    sources_by_id = {value["id"]: value for value in ledger.get("sources", [])}
    facts_by_id = {value["id"]: value for value in ledger.get("facts", [])}
    derived_by_id = {value["id"]: value for value in ledger.get("derived", [])}
    gaps_by_id = {value["id"]: value for value in ledger.get("gaps", [])}
    known_ids = (
        set(sources_by_id) | set(facts_by_id) | set(derived_by_id) | set(gaps_by_id)
    )
    pending = list(collect_known_references(public_receipt, known_ids))
    included_sources: set[str] = set()
    included_facts: set[str] = set()
    included_derived: set[str] = set()
    # Open gaps are a public transparency surface, not an implementation detail.
    # Keep the complete sanitized gap list even when an older receipt forgot to
    # reference a gap ID directly.
    included_gaps: set[str] = set(gaps_by_id)

    while pending:
        reference = pending.pop()
        if reference in facts_by_id and reference not in included_facts:
            included_facts.add(reference)
            source_id = facts_by_id[reference].get("sourceId")
            if isinstance(source_id, str):
                included_sources.add(source_id)
        elif reference in derived_by_id and reference not in included_derived:
            included_derived.add(reference)
            pending.extend(
                value
                for value in derived_by_id[reference].get("inputs", [])
                if isinstance(value, str)
            )
        elif reference in gaps_by_id:
            included_gaps.add(reference)
        elif reference in sources_by_id:
            included_sources.add(reference)

    policy = ledger.get("evidencePolicy", {})
    evidence = {
        "evidencePolicy": {"rules": policy.get("rules", [])},
        "sources": [
            pick_fields(source, SOURCE_FIELDS)
            for source in ledger.get("sources", [])
            if source.get("id") in included_sources
        ],
        "facts": [
            pick_fields(fact, FACT_FIELDS)
            for fact in ledger.get("facts", [])
            if fact.get("id") in included_facts
        ],
        "derived": [
            pick_fields(derived, DERIVED_FIELDS)
            for derived in ledger.get("derived", [])
            if derived.get("id") in included_derived
        ],
        "gaps": [
            {
                **pick_fields(gap, GAP_FIELDS),
                # Legacy internal ledgers predate public gap classification.
                # Treat them conservatively as missing evidence until a human
                # review assigns a more precise public disposition.
                "disposition": (
                    gap.get("disposition")
                    if gap.get("disposition")
                    in {"missing_evidence", "not_applicable", "resolved_context"}
                    else "missing_evidence"
                ),
            }
            for gap in ledger.get("gaps", [])
            if gap.get("id") in included_gaps
        ],
    }
    return evidence, included_facts


def project_audit(audit: dict[str, Any], included_fact_ids: set[str]) -> dict[str, Any]:
    audit_by_id: dict[str, dict[str, Any]] = {}
    for result in audit.get("results", []):
        if not isinstance(result, dict):
            continue
        fact_id = result.get("id")
        if fact_id not in included_fact_ids:
            continue
        if fact_id in audit_by_id:
            raise ValueError(f"duplicate citation audit row for {fact_id}")
        audit_by_id[fact_id] = result

    # Every public fact receives exactly one audit row. Missing or malformed
    # rows are explicitly unverifiable so the browser cannot infer safety from
    # absence and cannot create an unaudited PDF page deep link.
    results: list[dict[str, Any]] = []
    for fact_id in sorted(included_fact_ids):
        source_row = audit_by_id.get(fact_id)
        tier = source_row.get("tier") if source_row else None
        results.append(
            {
                "id": fact_id,
                "tier": tier if isinstance(tier, str) and tier else "unverifiable",
            }
        )
    return {
        "counts": dict(
            sorted(
                Counter(
                    result["tier"] for result in results if "tier" in result
                ).items()
            )
        ),
        "results": results,
    }


def find_banned_keys(value: Any, path: str = "$") -> list[str]:
    matches: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            if key in BANNED_PUBLIC_KEYS:
                matches.append(child_path)
            matches.extend(find_banned_keys(child, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            matches.extend(find_banned_keys(child, f"{path}[{index}]"))
    return matches


def build_pack(pack_id: str, input_dir: Path) -> dict[str, Any]:
    receipt = load_json(input_dir / "taxpayer-receipt.json")
    ledger = load_json(input_dir / "evidence-ledger.json")
    audit = load_json(input_dir / "citation-audit.json")

    jurisdiction = receipt.get("jurisdiction", {})
    if jurisdiction.get("slug") != pack_id:
        raise ValueError(
            f"{pack_id}: receipt jurisdiction slug is {jurisdiction.get('slug')!r}"
        )
    fiscal_year = receipt.get("fiscalYear")
    if (
        not isinstance(fiscal_year, int)
        or isinstance(fiscal_year, bool)
        or not 2000 <= fiscal_year <= 2100
    ):
        raise ValueError(f"{pack_id}: receipt fiscalYear must be explicit")
    expected_fiscal_year = PACK_FISCAL_YEARS.get(pack_id)
    if fiscal_year != expected_fiscal_year:
        raise ValueError(
            f"{pack_id}: receipt fiscalYear must equal the configured "
            f"current evidence year {expected_fiscal_year}"
        )
    if receipt.get("currency") != "CAD":
        raise ValueError(f"{pack_id}: receipt currency must be CAD")

    public_receipt = project_receipt(receipt)
    public_evidence, included_fact_ids = project_evidence(ledger, public_receipt)
    public_pack = {
        "schemaVersion": "1.2.0",
        "id": pack_id,
        "receipt": public_receipt,
        "evidence": public_evidence,
        "audit": project_audit(audit, included_fact_ids),
    }
    banned = find_banned_keys(public_pack)
    if banned:
        raise ValueError(f"{pack_id}: banned public keys: {', '.join(banned)}")
    return public_pack


def serialize(value: dict[str, Any]) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
        allow_nan=False,
    ) + "\n"


def expected_output_names() -> set[str]:
    return {f"{pack_id}.json" for pack_id in PACK_INPUTS}


def unexpected_json_artifacts(output_root: Path = OUTPUT_ROOT) -> list[Path]:
    if not output_root.exists():
        return []
    resolved_root = output_root.resolve()
    unexpected: list[Path] = []
    for path in output_root.rglob("*.json"):
        resolved_path = path.resolve()
        try:
            relative = resolved_path.relative_to(resolved_root)
        except ValueError as exc:
            raise ValueError(f"public pack artifact escapes output root: {path}") from exc
        if len(relative.parts) != 1 or relative.name not in expected_output_names():
            unexpected.append(path)
    return sorted(unexpected, key=lambda path: str(path).lower())


def remove_unexpected_json_artifacts(
    paths: Iterable[Path], output_root: Path = OUTPUT_ROOT
) -> None:
    resolved_root = output_root.resolve()
    for path in paths:
        resolved_path = path.resolve()
        try:
            resolved_path.relative_to(resolved_root)
        except ValueError as exc:
            raise ValueError(f"refusing to remove artifact outside output root: {path}") from exc
        if resolved_path.suffix.lower() != ".json" or not path.is_file():
            raise ValueError(f"refusing to remove non-JSON artifact: {path}")
        path.unlink()


def output_path_for(pack_id: str, output_root: Path = OUTPUT_ROOT) -> Path:
    path = output_root / f"{pack_id}.json"
    resolved_root = output_root.resolve()
    resolved_path = path.resolve()
    if resolved_path.parent != resolved_root:
        raise ValueError(f"public pack output escapes output root: {path}")
    return path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail if committed public artifacts differ; do not write files",
    )
    args = parser.parse_args()

    failures: list[str] = []
    if not args.check:
        OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

    unexpected = unexpected_json_artifacts()
    if args.check:
        failures.extend(
            f"unexpected: {path.relative_to(ROOT)}" for path in unexpected
        )
    else:
        remove_unexpected_json_artifacts(unexpected)

    for pack_id, input_dir in PACK_INPUTS.items():
        expected = serialize(build_pack(pack_id, input_dir))
        output_path = output_path_for(pack_id)
        if args.check:
            actual = (
                output_path.read_text(encoding="utf-8")
                if output_path.exists()
                else None
            )
            if actual != expected:
                failures.append(str(output_path.relative_to(ROOT)))
        else:
            output_path.write_text(expected, encoding="utf-8", newline="\n")

    if failures:
        print("Public pack artifacts are missing or stale:")
        for failure in failures:
            print(f"  - {failure}")
        print("Run: python scripts/build_public_packs.py")
        return 1

    action = "Verified" if args.check else "Built"
    print(f"{action} {len(PACK_INPUTS)} public pack artifacts.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
