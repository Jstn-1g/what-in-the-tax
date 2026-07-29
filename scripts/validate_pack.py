"""
Publication gate for jurisdiction packs.

The validator cross-checks the pack, ledger, receipt, source lock, derived
calculations, and citation audit.  Draft packs retain incomplete provenance as
warnings; sealed and published packs fail closed when receipt-driving evidence
is weak or is not bound to source and extract SHA-256 hashes.

There is no override flag.  ``--no-write`` is provided for read-only CI.
"""

from __future__ import annotations

import argparse
import ast
import copy
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from decimal import Decimal, DivisionByZero, InvalidOperation
from pathlib import Path, PurePosixPath
from typing import Any

try:
    import yaml  # type: ignore
except ImportError:  # pragma: no cover
    yaml = None

try:  # Works both as ``python scripts/validate_pack.py`` and as an import.
    from scripts.audit_citations import (
        HARD_CITATION_TIERS,
        STRONG_TIERS,
        audit_ledger,
        write_audit,
    )
    from scripts.lib.value_binding import unbound_values
except ModuleNotFoundError:  # pragma: no cover - exercised by direct CLI
    from audit_citations import (  # type: ignore
        HARD_CITATION_TIERS,
        STRONG_TIERS,
        audit_ledger,
        write_audit,
    )
    from lib.value_binding import unbound_values  # type: ignore

ROOT = Path(__file__).resolve().parents[1]
STRICT_PUBLICATION_STATUSES = frozenset({"sealed", "published"})
HASH_MISMATCH_ISSUES = frozenset(
    {
        "source-sha256-invalid",
        "source-sha256-mismatch",
        "source-bytes-invalid",
        "source-bytes-mismatch",
        "extract-sha256-invalid",
        "extract-sha256-mismatch",
    }
)
ID_TOKEN = re.compile(r"[A-Za-z][A-Za-z0-9_-]*")


class UnsupportedFormula(ValueError):
    """The bridge formula is human-readable rather than machine-evaluable."""


def load_pack(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    if path.suffix.casefold() in {".yaml", ".yml"}:
        if yaml is None:
            raise RuntimeError(
                "PyYAML is required to read pack.yaml. Install project requirements."
            )
        loaded = yaml.safe_load(text)
    else:
        loaded = json.loads(text)
    if not isinstance(loaded, dict):
        raise ValueError(f"{path} must contain an object")
    return loaded


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _normalized_path(value: str) -> str:
    return str(PurePosixPath(value.replace("\\", "/")))


def _normalized_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip().casefold()


def _resolve_repo_path(declared: str) -> Path:
    if not isinstance(declared, str) or not declared.strip():
        raise ValueError(f"artifact path must be a non-empty relative string: {declared!r}")
    path = Path(declared)
    if path.is_absolute():
        raise ValueError(f"absolute artifact path is not allowed: {declared!r}")
    resolved_root = ROOT.resolve()
    resolved = (resolved_root / path).resolve()
    try:
        resolved.relative_to(resolved_root)
    except ValueError as exc:
        raise ValueError(f"artifact path escapes repository: {declared!r}") from exc
    return resolved


def _strict_issue(
    message: str,
    *,
    strict: bool,
    errors: list[str],
    warnings: list[str],
) -> None:
    (errors if strict else warnings).append(message)


def check_identity_status(
    pack: dict[str, Any], *, strict: bool
) -> tuple[list[str], list[str]]:
    """Keep explicitly unsupported identities out of sealing/publication."""

    errors: list[str] = []
    warnings: list[str] = []
    if pack.get("identityStatus") == "unsupported":
        _strict_issue(
            "pack identityStatus is unsupported; exact receipt sealing is blocked",
            strict=strict,
            errors=errors,
            warnings=warnings,
        )
    return errors, warnings


def check_judgments(receipt: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    findings = receipt.get("findings", []) or []
    if not isinstance(findings, list):
        return ["receipt.findings must be an array"]
    for finding in findings:
        if not isinstance(finding, dict):
            errors.append("receipt.findings entries must be objects")
            continue
        impact = finding.get("billImpactCad")
        if impact is not None:
            errors.append(
                f"{finding.get('id')}: JUDGMENT billImpactCad must be null, got {impact!r}"
            )
    return errors


def _indexed_nodes(
    nodes: Any, label: str
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    indexed: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    if not isinstance(nodes, list):
        return indexed, [f"{label} collection must be an array"]
    for index, node in enumerate(nodes):
        if not isinstance(node, dict):
            errors.append(f"{label}[{index}] must be an object")
            continue
        node_id = node.get("id")
        if not isinstance(node_id, str) or not node_id:
            errors.append(f"{label}[{index}] is missing a non-empty id")
            continue
        if node_id in indexed:
            errors.append(f"duplicate {label} id {node_id!r}")
        indexed[node_id] = node
    return indexed, errors


def collect_receipt_references(
    receipt: dict[str, Any],
) -> tuple[set[str], dict[str, list[str]]]:
    references: set[str] = set()
    locations: dict[str, list[str]] = {}

    def visit(value: Any, path: str) -> None:
        if isinstance(value, list):
            for index, child in enumerate(value):
                visit(child, f"{path}[{index}]")
            return
        if not isinstance(value, dict):
            return
        source_fact_id = value.get("sourceFactId")
        if isinstance(source_fact_id, str) and source_fact_id:
            references.add(source_fact_id)
            locations.setdefault(source_fact_id, []).append(f"{path}.sourceFactId")
        for index, cited_id in enumerate(value.get("citedFactIds", []) or []):
            if isinstance(cited_id, str) and cited_id:
                references.add(cited_id)
                locations.setdefault(cited_id, []).append(
                    f"{path}.citedFactIds[{index}]"
                )
        for key, child in value.items():
            if key != "citedFactIds":
                visit(child, f"{path}.{key}")

    visit(receipt, "$")
    return references, locations


def check_ids_resolve(
    ledger: dict[str, Any], receipt: dict[str, Any]
) -> tuple[list[str], set[str], set[str]]:
    facts, errors = _indexed_nodes(ledger.get("facts", []) or [], "fact")
    derived, derived_errors = _indexed_nodes(ledger.get("derived", []) or [], "derived")
    sources, source_errors = _indexed_nodes(ledger.get("sources", []) or [], "source")
    gaps_raw = ledger.get("gaps", []) or []
    closed_gaps_raw = ledger.get("closedGaps", []) or []
    if not isinstance(gaps_raw, list):
        errors.append("gap collection must be an array")
        gaps_raw = []
    if not isinstance(closed_gaps_raw, list):
        errors.append("closedGap collection must be an array")
        closed_gaps_raw = []
    gaps, gap_errors = _indexed_nodes(gaps_raw + closed_gaps_raw, "gap")
    errors.extend(derived_errors + source_errors + gap_errors)

    overlap = set(facts) & set(derived)
    for node_id in sorted(overlap):
        errors.append(f"id {node_id!r} is used by both a fact and a derived node")

    known = set(facts) | set(derived)
    for fact_id, fact in facts.items():
        source_id = fact.get("sourceId")
        if not isinstance(source_id, str) or source_id not in sources:
            errors.append(f"fact {fact_id} references missing sourceId {source_id!r}")

    for derived_id, node in derived.items():
        inputs = node.get("inputs")
        if not isinstance(inputs, list) or not inputs:
            errors.append(f"derived {derived_id} must declare a non-empty inputs list")
            continue
        if len(inputs) != len(set(inputs)):
            errors.append(f"derived {derived_id} declares duplicate inputs")
        for input_id in inputs:
            if input_id not in known:
                errors.append(
                    f"derived {derived_id} references missing input {input_id!r}"
                )

    direct_references, locations = collect_receipt_references(receipt)
    for reference in sorted(direct_references):
        if reference not in known:
            errors.append(
                f"receipt references missing id {reference!r} at "
                f"{', '.join(locations[reference])}"
            )

    findings = receipt.get("findings", []) or []
    if not isinstance(findings, list):
        findings = []
    for finding in findings:
        if not isinstance(finding, dict):
            continue
        for gap_id in finding.get("gapIds", []) or []:
            if gap_id not in gaps:
                errors.append(
                    f"finding {finding.get('id')} references missing gap {gap_id!r}"
                )

    # Receipt-driving facts include the transitive inputs of every cited DERIVED.
    load_bearing = set(direct_references)
    pending = list(direct_references)
    while pending:
        node_id = pending.pop()
        node = derived.get(node_id)
        if not node:
            continue
        for input_id in node.get("inputs", []) or []:
            if input_id not in load_bearing:
                load_bearing.add(input_id)
                pending.append(input_id)

    return errors, load_bearing, set(facts)


def check_identity_and_context(
    pack: dict[str, Any],
    ledger: dict[str, Any],
    receipt: dict[str, Any],
    *,
    directory_slug: str,
    ledger_rel: str,
    strict: bool,
) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    ledger_jurisdiction = ledger.get("jurisdiction") or {}
    receipt_jurisdiction = receipt.get("jurisdiction") or {}

    for artifact, expected in (
        (ledger.get("artifact"), "EvidenceLedger"),
        (receipt.get("artifact"), "TaxpayerReceipt"),
    ):
        if artifact != expected:
            errors.append(f"artifact type must be {expected!r}, got {artifact!r}")

    ledger_version = ledger.get("schemaVersion")
    receipt_version = receipt.get("schemaVersion")
    if ledger_version != receipt_version:
        errors.append(
            f"schemaVersion mismatch: ledger {ledger_version!r}, receipt {receipt_version!r}"
        )

    slugs = {
        "pack": pack.get("slug"),
        "ledger": ledger_jurisdiction.get("slug"),
        "receipt": receipt_jurisdiction.get("slug"),
        "directory": directory_slug,
    }
    present_slugs = {value for value in slugs.values() if value is not None}
    if len(present_slugs) > 1:
        errors.append(
            "jurisdiction slug mismatch: "
            + ", ".join(f"{key}={value!r}" for key, value in slugs.items())
        )
    for location, value in slugs.items():
        if value is None:
            _strict_issue(
                f"{location} is missing jurisdiction slug",
                strict=strict,
                errors=errors,
                warnings=warnings,
            )

    names = {
        "pack": pack.get("name"),
        "ledger": ledger_jurisdiction.get("name"),
        "receipt": receipt_jurisdiction.get("displayName"),
    }
    if names["pack"] and names["ledger"]:
        if _normalized_text(names["pack"]) != _normalized_text(names["ledger"]):
            errors.append(
                f"jurisdiction name mismatch: pack={names['pack']!r}, "
                f"ledger={names['ledger']!r}"
            )
    elif not names["ledger"]:
        _strict_issue(
            "ledger is missing jurisdiction name",
            strict=strict,
            errors=errors,
            warnings=warnings,
        )
    if names["pack"] and names["receipt"]:
        # Receipt display names may append a community qualifier, e.g. "(Paris)".
        if not _normalized_text(names["receipt"]).startswith(
            _normalized_text(names["pack"])
        ):
            errors.append(
                f"jurisdiction displayName mismatch: pack={names['pack']!r}, "
                f"receipt={names['receipt']!r}"
            )

    levels = {
        "pack": pack.get("level"),
        "ledger": ledger_jurisdiction.get("level"),
        "receipt": receipt_jurisdiction.get("level"),
    }
    present_levels = {value for value in levels.values() if value is not None}
    if len(present_levels) > 1:
        errors.append(
            "jurisdiction level mismatch: "
            + ", ".join(f"{key}={value!r}" for key, value in levels.items())
        )

    pack_code = pack.get("assessmentCode")
    ledger_code = ledger_jurisdiction.get("assessmentCode")
    if pack_code is not None and ledger_code is not None:
        if str(pack_code) != str(ledger_code):
            errors.append(
                f"assessmentCode mismatch: pack={pack_code!r}, ledger={ledger_code!r}"
            )
    elif (pack_code is None) != (ledger_code is None):
        _strict_issue(
            f"assessmentCode is not carried consistently: pack={pack_code!r}, "
            f"ledger={ledger_code!r}",
            strict=strict,
            errors=errors,
            warnings=warnings,
        )

    evidence_ref = receipt.get("evidencePolicyRef")
    if not isinstance(evidence_ref, str):
        errors.append("receipt.evidencePolicyRef must identify its ledger")
    elif _normalized_path(evidence_ref) != _normalized_path(ledger_rel):
        errors.append(
            f"receipt.evidencePolicyRef {evidence_ref!r} does not match "
            f"pack artifact ledger {ledger_rel!r}"
        )

    expected_year = pack.get("fiscalYear")
    expected_currency = pack.get("currency")
    for artifact_name, artifact in (("ledger", ledger), ("receipt", receipt)):
        artifact_year = artifact.get("fiscalYear", artifact.get("taxYear"))
        if artifact_year is None:
            _strict_issue(
                f"{artifact_name} is missing fiscalYear/taxYear",
                strict=strict,
                errors=errors,
                warnings=warnings,
            )
        elif str(artifact_year) != str(expected_year):
            errors.append(
                f"fiscal year mismatch: pack={expected_year!r}, "
                f"{artifact_name}={artifact_year!r}"
            )

        artifact_currency = artifact.get("currency")
        if artifact_currency is None:
            _strict_issue(
                f"{artifact_name} is missing currency",
                strict=strict,
                errors=errors,
                warnings=warnings,
            )
        elif str(artifact_currency).upper() != str(expected_currency).upper():
            errors.append(
                f"currency mismatch: pack={expected_currency!r}, "
                f"{artifact_name}={artifact_currency!r}"
            )

    return errors, warnings


def _numeric_value(node: dict[str, Any]) -> Decimal:
    for field in ("amountCad", "value"):
        value = node.get(field)
        if isinstance(value, bool):
            continue
        if isinstance(value, (int, float, str)):
            try:
                return Decimal(str(value))
            except InvalidOperation:
                continue
    raise UnsupportedFormula("input has no numeric amountCad/value")


def _stored_value(node: dict[str, Any]) -> tuple[Decimal, Any, str]:
    for field in ("amountCad", "value"):
        value = node.get(field)
        if isinstance(value, bool):
            continue
        if isinstance(value, (int, float, str)):
            try:
                return Decimal(str(value)), value, field
            except InvalidOperation:
                continue
    raise UnsupportedFormula("derived node has no numeric amountCad/value")


def _display_tolerance(raw_value: Any) -> Decimal:
    """Half a displayed unit: cents for 2dp money, half-dollar for integers."""

    text = str(raw_value)
    decimal_places = len(text.partition(".")[2]) if "." in text else 0
    return Decimal("0.5") * (Decimal(10) ** -decimal_places)


def _node_tolerance(node: dict[str, Any], raw_value: Any, field: str) -> Decimal:
    if field == "amountCad":
        # Integers are used for explicitly whole-dollar controls/scenarios.
        return Decimal("0.5") if isinstance(raw_value, int) else Decimal("0.005")
    return _display_tolerance(raw_value)


def _eval_ast(node: ast.AST, values: dict[str, Decimal]) -> Decimal:
    if isinstance(node, ast.Expression):
        return _eval_ast(node.body, values)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return Decimal(str(node.value))
    if isinstance(node, ast.Name):
        if node.id not in values:
            raise UnsupportedFormula(f"unknown formula token {node.id!r}")
        return values[node.id]
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        value = _eval_ast(node.operand, values)
        return value if isinstance(node.op, ast.UAdd) else -value
    if isinstance(node, ast.BinOp):
        left = _eval_ast(node.left, values)
        right = _eval_ast(node.right, values)
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
        if isinstance(node.op, ast.Div):
            return left / right
        raise UnsupportedFormula(f"operator {type(node.op).__name__} is not allowed")
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in {"sum", "mean"}
        and not node.keywords
    ):
        values_list = [_eval_ast(argument, values) for argument in node.args]
        if not values_list:
            raise UnsupportedFormula(f"{node.func.id}() requires at least one input")
        total = sum(values_list, Decimal(0))
        return total if node.func.id == "sum" else total / Decimal(len(values_list))
    raise UnsupportedFormula(f"formula syntax {type(node).__name__} is not allowed")


def _evaluate_formula(
    derived: dict[str, Any], known_nodes: dict[str, dict[str, Any]]
) -> Decimal:
    formula = derived.get("formula")
    inputs = derived.get("inputs") or []
    if not isinstance(formula, str) or not formula.strip():
        raise UnsupportedFormula("missing formula")

    # Current bridge ledgers use this human-readable identity shape.
    identity = re.fullmatch(
        r"\s*sum\(.+\)\s*==\s*([A-Za-z][A-Za-z0-9_-]*)\s*",
        formula,
        flags=re.IGNORECASE,
    )
    if identity:
        control_id = identity.group(1)
        if control_id not in inputs or control_id not in known_nodes:
            raise UnsupportedFormula("sum identity control is not a declared input")
        return sum(
            (
                _numeric_value(known_nodes[input_id])
                for input_id in inputs
                if input_id != control_id
            ),
            Decimal(0),
        )

    transformed = formula
    values: dict[str, Decimal] = {}
    referenced_ids: set[str] = set()
    for index, node_id in enumerate(
        sorted(known_nodes, key=len, reverse=True)
    ):
        pattern = re.compile(
            rf"(?<![A-Za-z0-9_-]){re.escape(node_id)}(?![A-Za-z0-9_-])"
        )
        if not pattern.search(transformed):
            continue
        if node_id not in inputs:
            raise ValueError(
                f"formula references {node_id!r} but inputs does not declare it"
            )
        variable = f"v{index}"
        transformed = pattern.sub(variable, transformed)
        values[variable] = _numeric_value(known_nodes[node_id])
        referenced_ids.add(node_id)

    # A residual identifier is human prose/alias, not a safe expression.
    residual = [
        token
        for token in ID_TOKEN.findall(transformed)
        if token not in values and token not in {"sum", "mean"}
    ]
    if residual:
        raise UnsupportedFormula(
            "human-readable formula tokens remain: " + ", ".join(sorted(set(residual)))
        )

    try:
        tree = ast.parse(transformed, mode="eval")
        return _eval_ast(tree, values)
    except (SyntaxError, DivisionByZero, ZeroDivisionError) as exc:
        raise UnsupportedFormula(str(exc)) from exc


def check_derived_calculations(
    ledger: dict[str, Any],
    *,
    strict: bool = False,
) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    facts, _ = _indexed_nodes(ledger.get("facts", []) or [], "fact")
    derived, _ = _indexed_nodes(ledger.get("derived", []) or [], "derived")
    known = {**facts, **derived}

    # Cycle detection protects transitive receipt traversal and calculation order.
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node_id: str, trail: list[str]) -> None:
        if node_id in visiting:
            start = trail.index(node_id) if node_id in trail else 0
            errors.append(
                "derived dependency cycle: " + " -> ".join(trail[start:] + [node_id])
            )
            return
        if node_id in visited or node_id not in derived:
            return
        visiting.add(node_id)
        for input_id in derived[node_id].get("inputs", []) or []:
            visit(input_id, trail + [node_id])
        visiting.remove(node_id)
        visited.add(node_id)

    for node_id in derived:
        visit(node_id, [])

    for node_id, node in derived.items():
        try:
            computed = _evaluate_formula(node, known)
            stored, raw_stored, stored_field = _stored_value(node)
        except UnsupportedFormula as exc:
            # An unparseable formula was the one case that never failed, in
            # strict mode too, because this gate was the only one never handed
            # `strict` - every sibling gets it. So the way to bypass arithmetic
            # verification entirely was to write prose in `formula`: a node that
            # cannot be recomputed was treated as a node that had been.
            # GENERALIZATION-PLAN section 9.5 lists a formula leaf that is a bare
            # literal or an undeclared id under HARD FAIL.
            _strict_issue(
                f"derived {node_id} was not recomputed: {exc}",
                strict=strict,
                errors=errors,
                warnings=warnings,
            )
            continue
        except (InvalidOperation, ValueError) as exc:
            errors.append(f"derived {node_id} formula is invalid: {exc}")
            continue

        # A sum(...) == CONTROL formula verifies both the identity and stored value.
        identity = re.fullmatch(
            r"\s*sum\(.+\)\s*==\s*([A-Za-z][A-Za-z0-9_-]*)\s*",
            str(node.get("formula") or ""),
            flags=re.IGNORECASE,
        )
        if identity:
            control = _numeric_value(known[identity.group(1)])
            control_node = known[identity.group(1)]
            control_raw = control_node.get(
                "amountCad", control_node.get("value", control)
            )
            control_field = (
                "amountCad" if "amountCad" in control_node else "value"
            )
            tolerance = max(
                _node_tolerance(node, raw_stored, stored_field),
                _node_tolerance(control_node, control_raw, control_field),
            )
            if abs(computed - control) > tolerance:
                errors.append(
                    f"derived {node_id} identity fails: component sum {computed} "
                    f"!= control {control}"
                )

        tolerance = _node_tolerance(node, raw_stored, stored_field)
        if abs(computed - stored) > tolerance:
            errors.append(
                f"derived {node_id} does not recompute: stored {stored}, "
                f"computed {computed}, tolerance {tolerance}"
            )

    return errors, warnings


def apply_sources_lock(
    ledger: dict[str, Any],
    source_lock: dict[str, Any] | None,
    *,
    load_bearing_fact_ids: set[str],
    strict: bool,
) -> tuple[dict[str, Any], list[str], list[str]]:
    """Overlay canonical lock hashes after checking ledger/lock metadata agreement."""

    errors: list[str] = []
    warnings: list[str] = []
    result = copy.deepcopy(ledger)
    ledger_sources, source_id_errors = _indexed_nodes(
        result.get("sources", []) or [], "source"
    )
    errors.extend(source_id_errors)
    facts, _ = _indexed_nodes(result.get("facts", []) or [], "fact")
    load_bearing_source_ids = {
        facts[fact_id].get("sourceId")
        for fact_id in load_bearing_fact_ids
        if fact_id in facts
    }
    load_bearing_source_ids.discard(None)

    if source_lock is None:
        _strict_issue(
            "pack has no artifacts.sourcesLock; source bytes are not independently locked",
            strict=strict and bool(load_bearing_source_ids),
            errors=errors,
            warnings=warnings,
        )
        return result, errors, warnings

    lock_entries, lock_errors = _indexed_nodes(
        source_lock.get("sources", []) or [], "source lock entry"
    )
    errors.extend(lock_errors)

    for source_id, lock_entry in lock_entries.items():
        ledger_source = ledger_sources.get(source_id)
        if ledger_source is None:
            warnings.append(f"sourcesLock contains unused source {source_id!r}")
            continue
        for field in ("localPath", "extractedText"):
            ledger_value = ledger_source.get(field)
            lock_value = lock_entry.get(field)
            if ledger_value != lock_value:
                errors.append(
                    f"source {source_id} {field} mismatch: ledger={ledger_value!r}, "
                    f"lock={lock_value!r}"
                )
        for field in ("sha256", "extractedTextSha256"):
            embedded = ledger_source.get(field)
            locked = lock_entry.get(field)
            if embedded is not None and embedded != locked:
                errors.append(
                    f"source {source_id} {field} mismatch between ledger and sourcesLock"
                )
            if locked is not None:
                ledger_source[field] = locked
        if "bytes" in lock_entry:
            ledger_source["bytes"] = lock_entry["bytes"]

    for source_id in sorted(load_bearing_source_ids):
        if source_id not in lock_entries:
            _strict_issue(
                f"load-bearing source {source_id!r} is missing from sourcesLock",
                strict=strict,
                errors=errors,
                warnings=warnings,
            )

    return result, errors, warnings


def check_citation_gate(
    audit: dict[str, Any],
    *,
    load_bearing_fact_ids: set[str],
    strict: bool,
) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    by_id = {
        result.get("id"): result
        for result in audit.get("results", [])
        if result.get("id")
    }

    for result in audit.get("results", []):
        if result.get("tier") in HARD_CITATION_TIERS:
            errors.append(
                f"citation {result.get('id')} is {result.get('tier')}: "
                f"{result.get('note')}"
            )
        mismatch_issues = set(result.get("bindingIssues", [])) & HASH_MISMATCH_ISSUES
        if mismatch_issues:
            errors.append(
                f"citation {result.get('id')} has invalid declared binding: "
                + ", ".join(sorted(mismatch_issues))
            )

    for fact_id in sorted(load_bearing_fact_ids):
        result = by_id.get(fact_id)
        if result is None:
            _strict_issue(
                f"load-bearing fact {fact_id!r} has no citation audit result",
                strict=strict,
                errors=errors,
                warnings=warnings,
            )
            continue
        tier = result.get("tier")
        binding_issues = sorted(set(result.get("bindingIssues", [])))
        if tier not in STRONG_TIERS:
            _strict_issue(
                f"load-bearing fact {fact_id!r} has weak citation tier {tier!r}",
                strict=strict,
                errors=errors,
                warnings=warnings,
            )
        if binding_issues:
            _strict_issue(
                f"load-bearing fact {fact_id!r} is not fully bound: "
                + ", ".join(binding_issues),
                strict=strict,
                errors=errors,
                warnings=warnings,
            )

    return errors, warnings


def _load_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot load {label} {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} {path} must contain an object")
    return value


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("slug", nargs="?", default="north-dumfries-on")
    parser.add_argument(
        "--no-write",
        action="store_true",
        help="run read-only; do not update validation or citation reports",
    )
    parser.add_argument(
        "--report-dir",
        help="write reports outside the corpus/data directories",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help=(
            "enforce sealed/publication-grade gates regardless of the pack's "
            "declared draft status"
        ),
    )
    return parser.parse_args(argv[1:])


def main(argv: list[str]) -> int:
    args = _parse_args(argv)
    slug = args.slug
    pack_dir = ROOT / "corpus" / slug
    pack_path = pack_dir / "pack.yaml"
    if not pack_path.exists():
        alternate = pack_dir / "pack.json"
        if alternate.exists():
            pack_path = alternate
        else:
            print(f"ERROR: missing {pack_path}", file=sys.stderr)
            return 1

    try:
        pack = load_pack(pack_path)
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    errors: list[str] = []
    warnings: list[str] = []
    for field in ("slug", "name", "fiscalYear", "currency", "publication"):
        if field not in pack:
            errors.append(f"pack is missing required field {field!r}")
    if pack.get("slug") != slug:
        errors.append(
            f"pack.slug {pack.get('slug')!r} does not match directory {slug!r}"
        )

    publication = pack.get("publication") or {}
    if not isinstance(publication, dict):
        errors.append("pack.publication must be an object")
        publication = {}
    status = publication.get("status", "draft")
    strict = args.strict or status in STRICT_PUBLICATION_STATUSES
    identity_errors, identity_warnings = check_identity_status(pack, strict=strict)
    errors.extend(identity_errors)
    warnings.extend(identity_warnings)
    artifacts = pack.get("artifacts") or {}
    if not isinstance(artifacts, dict):
        errors.append("pack.artifacts must be an object")
        artifacts = {}
    ledger_rel = artifacts.get("ledger", "data/evidence-ledger.json")
    receipt_rel = artifacts.get("receipt", "data/taxpayer-receipt.json")

    try:
        ledger_path = _resolve_repo_path(ledger_rel)
        receipt_path = _resolve_repo_path(receipt_rel)
    except ValueError as exc:
        errors.append(str(exc))
        ledger_path = receipt_path = ROOT / "__invalid_artifact__"

    ledger: dict[str, Any] = {}
    receipt: dict[str, Any] = {}
    if not ledger_path.is_file():
        errors.append(f"ledger missing: {ledger_path}")
    if not receipt_path.is_file():
        errors.append(f"receipt missing: {receipt_path}")
    if ledger_path.is_file():
        try:
            ledger = _load_json(ledger_path, "ledger")
        except ValueError as exc:
            errors.append(str(exc))
    if receipt_path.is_file():
        try:
            receipt = _load_json(receipt_path, "receipt")
        except ValueError as exc:
            errors.append(str(exc))

    load_bearing: set[str] = set()
    fact_ids: set[str] = set()
    if ledger and receipt:
        id_errors, load_bearing, fact_ids = check_ids_resolve(ledger, receipt)
        errors.extend(id_errors)
        errors.extend(check_judgments(receipt))
        identity_errors, identity_warnings = check_identity_and_context(
            pack,
            ledger,
            receipt,
            directory_slug=slug,
            ledger_rel=ledger_rel,
            strict=strict,
        )
        errors.extend(identity_errors)
        warnings.extend(identity_warnings)
        derived_errors, derived_warnings = check_derived_calculations(ledger, strict=strict)
        errors.extend(derived_errors)
        warnings.extend(derived_warnings)

        # Every printed number must follow from the node it cites - equal to it,
        # or rate x the assessment in scope where the artifact declares that
        # relationship. Unconditional, not strict-only: a draft is allowed weak
        # provenance, but it is not allowed to print a number inconsistent with
        # its own citation. Before this check a line item changed to $999,999
        # with its sourceFactId intact passed here with zero errors, because the
        # reference was verified to exist and never compared to anything.
        binding_nodes = {
            node["id"]: node
            for node in (ledger.get("facts", []) or []) + (ledger.get("derived", []) or [])
            if isinstance(node, dict) and isinstance(node.get("id"), str)
        }
        for issue in unbound_values(receipt, binding_nodes):
            errors.append(f"unbound printed value: {issue}")

    source_lock: dict[str, Any] | None = None
    source_lock_path: Path | None = None
    source_lock_rel = artifacts.get("sourcesLock")
    if source_lock_rel:
        try:
            source_lock_path = _resolve_repo_path(source_lock_rel)
            source_lock = _load_json(source_lock_path, "sourcesLock")
            locked_ledger_path = source_lock.get("ledgerPath")
            normalized_locked_ledger = (
                _normalized_path(locked_ledger_path)
                if isinstance(locked_ledger_path, str)
                else None
            )
            if normalized_locked_ledger != _normalized_path(ledger_rel):
                errors.append(
                    f"sourcesLock.ledgerPath {locked_ledger_path!r} does not match "
                    f"pack artifact ledger {_normalized_path(ledger_rel)!r}"
                )
            locked_ledger_hash = source_lock.get("ledgerSha256")
            actual_ledger_hash = sha256_file(ledger_path) if ledger_path.is_file() else None
            if locked_ledger_hash != actual_ledger_hash:
                errors.append(
                    "sourcesLock.ledgerSha256 does not match the current ledger bytes"
                )
        except ValueError as exc:
            errors.append(str(exc))

    audited_ledger, lock_errors, lock_warnings = apply_sources_lock(
        ledger,
        source_lock,
        load_bearing_fact_ids=load_bearing & fact_ids,
        strict=strict,
    )
    errors.extend(lock_errors)
    warnings.extend(lock_warnings)
    audit = audit_ledger(audited_ledger, root=ROOT) if ledger else {
        "ok": False,
        "counts": {},
        "bindingIssueCounts": {},
        "results": [],
        "sourceBindings": [],
    }
    citation_errors, citation_warnings = check_citation_gate(
        audit,
        load_bearing_fact_ids=load_bearing & fact_ids,
        strict=strict,
    )
    errors.extend(citation_errors)
    warnings.extend(citation_warnings)

    if strict and errors:
        errors.append(
            f"publication.status is {status!r} but validation failed; "
            "the pack cannot be promoted or deployed"
        )
    if status == "published":
        errors.append(
            "publication.status must not be set to published in pack.yaml by hand; "
            "publishing is a logged human act after sealing"
        )

    content_hashes: dict[str, dict[str, str]] = {}
    for label, path in (
        ("ledger", ledger_path),
        ("receipt", receipt_path),
        ("pack", pack_path),
        ("sourcesLock", source_lock_path),
    ):
        if path is not None and path.is_file():
            content_hashes[label] = {
                "path": str(path.relative_to(ROOT)).replace("\\", "/"),
                "sha256": sha256_file(path),
            }

    report = {
        "slug": slug,
        "validatedAt": datetime.now(timezone.utc).isoformat(),
        "ok": not errors,
        "publicationStatusDeclared": status,
        "strictPublicationGate": strict,
        "loadBearingFactIds": sorted(load_bearing & fact_ids),
        "errors": errors,
        "warnings": warnings,
        "citationAudit": {
            "ok": audit.get("ok", False),
            "counts": audit.get("counts", {}),
            "bindingIssueCounts": audit.get("bindingIssueCounts", {}),
        },
        "contentHashes": content_hashes,
        "engineNote": (
            "Bridge schema validator with cross-artifact identity, source-lock, "
            "citation, and machine-evaluable derived-expression gates."
        ),
    }

    wrote: list[str] = []
    if not args.no_write:
        if args.report_dir:
            report_dir = Path(args.report_dir)
            if not report_dir.is_absolute():
                report_dir = (Path.cwd() / report_dir).resolve()
            report_dir.mkdir(parents=True, exist_ok=True)
            report_path = report_dir / f"{slug}-validation-report.json"
            audit_path = report_dir / f"{slug}-citation-audit.json"
        else:
            report_path = pack_dir / "validation-report.json"
            audit_path = ledger_path.parent / "citation-audit.json"
        report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        write_audit(audit, audit_path)
        wrote.extend([str(report_path), str(audit_path)])

    print(
        json.dumps(
            {
                "ok": report["ok"],
                "errors": len(errors),
                "warnings": len(warnings),
                "wrote": wrote,
            },
            indent=2,
        )
    )
    for warning in warnings:
        print(f"  WARNING: {warning}", file=sys.stderr)
    for error in errors:
        print(f"  ERROR: {error}", file=sys.stderr)
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
