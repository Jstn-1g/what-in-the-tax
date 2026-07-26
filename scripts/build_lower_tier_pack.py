"""Build a dual-tier lower-tier pack from corpus/<slug>/build-inputs.yaml.

Deterministic — no LLM. Imports Region HH schedule by regionAreaKey.
Bill stack is always rate × local assessment; Region schedule dollars are
informational at the Region-published assessment ($354,500).

Usage:
  python scripts/build_lower_tier_pack.py waterloo-on
  python scripts/build_lower_tier_pack.py corpus/waterloo-on/build-inputs.yaml
"""

from __future__ import annotations

import json
import re
import sys
from decimal import (
    ROUND_HALF_EVEN,
    ROUND_HALF_UP,
    Decimal,
    InvalidOperation,
)
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from lib.region_schedule import load_region_schedule  # noqa: E402
from lib.path_safety import (  # noqa: E402
    PathSafetyError,
    resolve_under_root,
    validate_fiscal_year,
    validate_slug,
)
from lib.rt_rates import (  # noqa: E402
    RATE_SUM_TOLERANCE,
    normalize_rate_unit,
    parse_rt_rates_from_extract,
    rate_to_decimal,
)

ROUNDING_METHODS = {
    "half-up": ROUND_HALF_UP,
    "half-even": ROUND_HALF_EVEN,
}
ROUNDING_STRATEGIES = {
    "component": "component",
    "components": "component",
    "round-components": "component",
    "per-component": "component",
    "total": "total",
    "round-total": "total",
    "final-total": "total",
}
DEFAULT_CAD_QUANTUM = Decimal("0.01")


def fact(**kwargs):
    kwargs.setdefault("kind", "FACT")
    return kwargs


def gap(**kwargs):
    kwargs.setdefault("kind", "GAP")
    return kwargs


def derived(**kwargs):
    kwargs.setdefault("kind", "DERIVED")
    return kwargs


def _decimal(value, *, label: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise SystemExit(f"{label} must be a decimal number, got {value!r}") from exc
    if not result.is_finite():
        raise SystemExit(f"{label} must be finite, got {value!r}")
    return result


def _json_safe(value):
    """Convert exact Decimal working values only at the JSON boundary."""

    if isinstance(value, Decimal):
        if value == value.to_integral_value():
            return int(value)
        return float(value)
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    return value


def _round_to_quantum(
    value: Decimal,
    *,
    quantum: Decimal = DEFAULT_CAD_QUANTUM,
    method=ROUND_HALF_UP,
) -> Decimal:
    if not quantum.is_finite() or quantum <= 0:
        raise SystemExit(f"rounding quantum must be positive and finite, got {quantum}")
    return (value / quantum).quantize(Decimal("1"), rounding=method) * quantum


def _rounding_policy(raw: dict | None) -> dict:
    if raw is None:
        return {
            "strategy": "component",
            "method": "half-up",
            "quantumCad": DEFAULT_CAD_QUANTUM,
            "source": "builder-default (preview only)",
            "sourceDeclared": False,
            "sealedEligible": False,
        }
    if not isinstance(raw, dict):
        raise SystemExit("rates.rounding must be a mapping with strategy, method, and source")

    strategy_key = str(raw.get("strategy", "")).strip().lower()
    try:
        strategy = ROUNDING_STRATEGIES[strategy_key]
    except KeyError as exc:
        raise SystemExit(
            "rates.rounding.strategy must be 'component' or 'total'"
        ) from exc

    method_key = str(raw.get("method", "")).strip().lower().replace("_", "-")
    try:
        method = ROUNDING_METHODS[method_key]
    except KeyError as exc:
        raise SystemExit(
            "rates.rounding.method must be 'half-up' or 'half-even'"
        ) from exc

    quantum = _decimal(
        raw.get("quantumCad", raw.get("precisionCad", "0.01")),
        label="rates.rounding.quantumCad",
    )
    if quantum <= 0:
        raise SystemExit("rates.rounding.quantumCad must be positive")
    source = str(raw.get("source", "")).strip()
    if not source:
        raise SystemExit(
            "rates.rounding.source is required for a source-declared rounding policy"
        )
    return {
        "strategy": strategy,
        "method": method_key,
        "quantumCad": quantum,
        "source": source,
        "sourceDeclared": True,
        "sealedEligible": True,
    }


def calculate_bill_stack(
    *,
    assessment,
    city_rate,
    region_rate,
    education_rate,
    total_rate,
    rounding: dict | None = None,
) -> dict:
    """Calculate a three-authority bill with exact Decimal arithmetic."""

    assessment_decimal = _decimal(assessment, label="assessment")
    rates = {
        "city": _decimal(city_rate, label="city rate"),
        "region": _decimal(region_rate, label="region rate"),
        "education": _decimal(education_rate, label="education rate"),
        "total": _decimal(total_rate, label="total rate"),
    }
    if assessment_decimal < 0 or any(value < 0 for value in rates.values()):
        raise SystemExit("assessment and rates must be non-negative")
    component_rate_sum = rates["city"] + rates["region"] + rates["education"]
    if abs(component_rate_sum - rates["total"]) > RATE_SUM_TOLERANCE:
        raise SystemExit(
            f"rate sum {component_rate_sum} != total {rates['total']}"
        )

    policy = _rounding_policy(rounding)
    method = ROUNDING_METHODS[policy["method"]]
    quantum = policy["quantumCad"]
    amounts = {
        key: _round_to_quantum(
            assessment_decimal * rates[key],
            quantum=quantum,
            method=method,
        )
        for key in ("city", "region", "education")
    }
    component_sum = sum(amounts.values(), Decimal("0"))
    total_rate_amount = _round_to_quantum(
        assessment_decimal * rates["total"],
        quantum=quantum,
        method=method,
    )
    combined = (
        component_sum
        if policy["strategy"] == "component"
        else total_rate_amount
    )
    return {
        **amounts,
        "combined": combined,
        "componentSum": component_sum,
        "totalRateAmount": total_rate_amount,
        "roundingAdjustment": combined - component_sum,
        "componentVsTotalRateDelta": component_sum - total_rate_amount,
        "policy": policy,
    }


def load_inputs(path: Path) -> dict:
    if yaml is None:
        raise SystemExit("PyYAML required (pip install pyyaml)")
    if not path.exists():
        raise SystemExit(f"missing {path}")
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def resolve_inputs_path(arg: str) -> Path:
    p = Path(arg)
    if p.suffix in {".yaml", ".yml"}:
        return p if p.is_absolute() else ROOT / p
    slug = arg.rstrip("/")
    return ROOT / "corpus" / slug / "build-inputs.yaml"


def _data_relative_path(cfg: dict) -> str:
    if cfg.get("dataDir") is not None:
        return str(cfg["dataDir"])
    slug = validate_slug(cfg["slug"])
    return f"data/{slug.removesuffix('-on')}"


def resolve_artifact_directories(cfg: dict) -> tuple[Path, Path]:
    """Resolve pack-controlled output paths under the two approved data roots."""

    data_rel = _data_relative_path(cfg)
    try:
        data = resolve_under_root(
            data_rel,
            project_root=ROOT,
            approved_root=ROOT / "data",
            base=ROOT,
            label="dataDir",
        )
        web = resolve_under_root(
            data_rel,
            project_root=ROOT,
            approved_root=ROOT / "web" / "src" / "data",
            base=ROOT / "web" / "src",
            label="web dataDir",
        )
    except PathSafetyError as exc:
        raise SystemExit(str(exc)) from exc
    return data, web


def resolve_assessment_code_evidence(
    cfg: dict, *, slug: str, assessment_code: str
) -> dict | None:
    """Bind an assessment code to the locked regional identity registry."""

    registry_ref = cfg.get("assessmentCodeRegistry")
    if registry_ref is None:
        return None

    try:
        registry_path = resolve_under_root(
            registry_ref,
            project_root=ROOT,
            approved_root=ROOT / "geography",
            base=ROOT,
            label="assessmentCodeRegistry",
        )
    except PathSafetyError as exc:
        raise SystemExit(str(exc)) from exc
    if not registry_path.is_file():
        raise SystemExit(f"missing assessment-code registry {registry_path}")

    try:
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(
            f"invalid assessment-code registry {registry_path}: {exc}"
        ) from exc

    rows = registry.get("jurisdictions")
    if not isinstance(rows, list):
        raise SystemExit(
            f"assessment-code registry {registry_path} has no jurisdictions list"
        )
    matches = [
        row
        for row in rows
        if isinstance(row, dict) and row.get("slug") == slug
    ]
    if len(matches) != 1:
        raise SystemExit(
            f"assessment-code registry must contain exactly one {slug} row"
        )
    locked_code = str(matches[0].get("assessmentCode") or "")
    if locked_code != assessment_code:
        raise SystemExit(
            f"assessment code {assessment_code} for {slug} does not match "
            f"locked registry code {locked_code}"
        )

    source_lock_ref = registry.get("sourceLock")
    if not isinstance(source_lock_ref, str) or not source_lock_ref:
        raise SystemExit(
            f"assessment-code registry {registry_path} has no sourceLock"
        )
    try:
        source_lock_path = resolve_under_root(
            source_lock_ref,
            project_root=ROOT,
            approved_root=ROOT / "geography",
            base=ROOT,
            label="assessment-code registry sourceLock",
        )
    except PathSafetyError as exc:
        raise SystemExit(str(exc)) from exc
    if not source_lock_path.is_file():
        raise SystemExit(
            f"missing assessment-code registry source lock {source_lock_path}"
        )

    return {
        "registryId": registry.get("registryId"),
        "effectiveDate": registry.get("effectiveDate"),
        "registryPath": registry_path.relative_to(ROOT.resolve()).as_posix(),
        "sourceLockPath": source_lock_path.relative_to(ROOT.resolve()).as_posix(),
    }


def _prefix(slug: str) -> str:
    """KIT from kitchener-on, WAT from waterloo-on, etc."""
    stem = slug.replace("-on", "").replace("-county", "")
    parts = re.split(r"[-_]", stem)
    letters = "".join(p[0] for p in parts if p).upper()
    return (letters or "MUN")[:6]


def build_pack(cfg: dict) -> tuple[dict, dict]:
    try:
        slug = validate_slug(cfg["slug"])
        fiscal_year = validate_fiscal_year(cfg.get("fiscalYear", 2026))
    except PathSafetyError as exc:
        raise SystemExit(str(exc)) from exc
    currency = str(cfg.get("currency", "")).strip().upper()
    if not re.fullmatch(r"[A-Z]{3}", currency):
        raise SystemExit(
            "currency is required and must be an explicit three-letter ISO code "
            "(for example, CAD)"
        )
    fiscal_year_policy = {
        "value": fiscal_year,
        "declaration": (
            "config.fiscalYear"
            if "fiscalYear" in cfg
            else "builder-default (preview only)"
        ),
        "sealedEligible": "fiscalYear" in cfg,
    }
    if fiscal_year != "2026":
        raise SystemExit(
            "lower-tier builder currently has only a locked 2026 Region schedule; "
            f"cannot build fiscalYear {fiscal_year}"
        )
    name = cfg["name"]
    aliases = cfg.get("aliases") or [name]
    level = cfg.get("level", "lower-tier")
    upper = cfg.get("parentBodies") or ["region-of-waterloo-on"]
    area_key = cfg["regionAreaKey"]
    assessment = int(cfg["defaultAssessmentCad"])
    assessment_code = str(cfg.get("assessmentCode") or "pending")
    assessment_code_evidence = resolve_assessment_code_evidence(
        cfg, slug=slug, assessment_code=assessment_code
    )
    prefix = cfg.get("idPrefix") or _prefix(slug)
    local_label = cfg.get("localBucketLabel") or "City portion"
    data_dir = _data_relative_path(cfg)
    # Validate output containment before parsing or doing any other pack work.
    resolve_artifact_directories(cfg)

    rates_cfg = cfg["rates"]
    configured_rate_unit = rates_cfg.get("rateUnit", rates_cfg.get("unit"))
    if rates_cfg.get("fromExtract"):
        extract = ROOT / rates_cfg["fromExtract"]
        parsed = parse_rt_rates_from_extract(
            extract,
            page=rates_cfg.get("page"),
            rate_unit=configured_rate_unit,
            prefer_percent=rates_cfg.get("preferPercent"),
        )
        resolved_rate_unit = parsed["sourceUnit"]
        rate_unit_declaration = parsed["unitDeclaration"]

        def selected_rate(field: str, parsed_field: str) -> Decimal:
            if field not in rates_cfg:
                return parsed[parsed_field]
            return rate_to_decimal(rates_cfg[field], unit=resolved_rate_unit)

        rate_city = selected_rate("city", "city")
        rate_region = selected_rate("region", "region")
        rate_edu = selected_rate("education", "education")
        rate_total = selected_rate("total", "total")
        rate_excerpt = rates_cfg.get("excerpt") or parsed["excerpt"]
        rate_page = int(rates_cfg.get("page") or parsed["page"] or 1)
    else:
        if configured_rate_unit is not None:
            resolved_rate_unit = normalize_rate_unit(configured_rate_unit)
            rate_unit_declaration = "config.rateUnit"
        elif rates_cfg.get("preferPercent") is not None:
            resolved_rate_unit = (
                "percent" if rates_cfg["preferPercent"] else "decimal"
            )
            rate_unit_declaration = "legacy.preferPercent"
        else:
            raise SystemExit(
                "rates without an extract require rateUnit "
                "('decimal', 'percent', or 'mill')"
            )
        rate_city = rate_to_decimal(rates_cfg["city"], unit=resolved_rate_unit)
        rate_region = rate_to_decimal(rates_cfg["region"], unit=resolved_rate_unit)
        rate_edu = rate_to_decimal(rates_cfg["education"], unit=resolved_rate_unit)
        rate_total = (
            rate_to_decimal(rates_cfg["total"], unit=resolved_rate_unit)
            if rates_cfg.get("total") is not None
            else rate_city + rate_region + rate_edu
        )
        rate_excerpt = rates_cfg["excerpt"]
        rate_page = int(rates_cfg.get("page", 1))

    bill = calculate_bill_stack(
        assessment=assessment,
        city_rate=rate_city,
        region_rate=rate_region,
        education_rate=rate_edu,
        total_rate=rate_total,
        rounding=rates_cfg.get("rounding"),
    )
    city_portion = bill["city"]
    region_portion = bill["region"]
    edu_portion = bill["education"]
    combined = bill["combined"]
    rounding_adjustment = bill["roundingAdjustment"]
    rate_policy = {
        "sourceUnit": resolved_rate_unit,
        "canonicalUnit": "decimal",
        "declaration": rate_unit_declaration,
        "sealedEligible": (
            "printed_suffix" in rate_unit_declaration
            or "config.rateUnit" in rate_unit_declaration
        ),
    }

    control = cfg["controlTotal"]
    control_measure_type = str(control.get("measureType", "")).strip()
    absolute_levy: Decimal | None = None
    if control_measure_type == "absolute_levy":
        if control.get("levyCad") is None:
            raise SystemExit(
                "controlTotal.measureType is absolute_levy but levyCad is missing"
            )
        absolute_levy = _decimal(
            control["levyCad"],
            label="controlTotal.levyCad",
        )
    elif control_measure_type:
        raise SystemExit(
            "controlTotal.measureType must be 'absolute_levy' when levyCad is a "
            "published absolute levy; use levyIncreaseCad or "
            "averageHouseholdIncreaseCad for non-control measures"
        )
    depts = cfg.get("departments") or []
    alloc_base = int(control.get("allocationBaseCad") or 0)
    if depts:
        dept_sum = sum(int(d["amountCad"]) for d in depts)
        if alloc_base and dept_sum != alloc_base:
            raise SystemExit(f"department sum {dept_sum} != allocationBase {alloc_base}")
        if not alloc_base:
            alloc_base = dept_sum
    has_dept_alloc = bool(depts) and alloc_base > 0

    sources = list(cfg.get("sources") or [])
    region = load_region_schedule(area_key)
    area = region["area"]
    hh_assessment = region["assessmentCad"]
    hh_page = region["page"]
    hh_total = area["taxSupportedTotalCad"]
    area_label = region["areaLabel"]

    region_source_id = f"row-{fiscal_year}-book"
    sources.append(
        {
            "id": region_source_id,
            "title": region["source"]["title"],
            "url": "https://www.regionofwaterloo.ca/",
            "localPath": f"source-pdfs/{fiscal_year}_final_budget_book_region.pdf",
            "extractedText": region["extractPath"],
            "asOf": fiscal_year,
            "authority": "Region of Waterloo",
            "note": (
                f"Shared pack schedule area={area_key}. "
                f"Dollars at Region average ${hh_assessment:,} — not local ${assessment:,}."
            ),
        }
    )

    rate_source_id = rates_cfg.get("sourceId") or next(
        (s["id"] for s in sources if "tax" in s["id"].lower() or "rate" in s["id"].lower()),
        sources[0]["id"] if sources else "rates",
    )
    budget_source_id = control.get("sourceId") or next(
        (s["id"] for s in sources if "budget" in s["id"].lower() or "summary" in s["id"].lower()),
        sources[0]["id"] if sources else "budget",
    )
    dept_source_id = control.get("deptSourceId") or budget_source_id

    assessment_measure_declared = "assessmentMeasureType" in control
    assessment_measure_type = str(
        control.get("assessmentMeasureType", "reference_scenario")
    ).strip()
    if assessment_measure_type not in {"published_average", "reference_scenario"}:
        raise SystemExit(
            "controlTotal.assessmentMeasureType must be 'published_average' "
            "or 'reference_scenario'"
        )
    assessment_source_id = control.get("assessmentSourceId", budget_source_id)
    assessment_source = next(
        (source for source in sources if source.get("id") == assessment_source_id),
        None,
    )
    if assessment_source is None:
        raise SystemExit(
            f"assessment source {assessment_source_id!r} is not declared in sources"
        )
    assessment_excerpt = str(control.get("assessmentExcerpt", "")).strip()
    if not assessment_excerpt:
        raise SystemExit(
            "controlTotal.assessmentExcerpt is required for the assessment scenario"
        )

    if assessment_measure_type == "published_average":
        authority = str(assessment_source.get("authority", "")).strip()
        if authority.casefold() != name.casefold():
            raise SystemExit(
                "published_average assessment requires a source issued by the "
                f"local jurisdiction {name!r}; got authority {authority!r}"
            )
        assessment_fact_id = f"{prefix}-AVG-ASSESSMENT-{fiscal_year}"
        assessment_fact_label = (
            f"{name} published average residential assessment"
        )
        assessment_fact_status = control.get("status", "approved")
        assessment_context = "published average assessment"
        profile_description = (
            f"Published average residential assessment (${assessment:,})."
        )
    else:
        assessment_fact_id = f"{prefix}-REFERENCE-ASSESSMENT-{fiscal_year}"
        assessment_fact_label = (
            f"Reference assessment scenario — not a published {name} average"
        )
        assessment_fact_status = "reference_scenario"
        assessment_context = "reference assessment scenario"
        profile_description = (
            f"Reference residential assessment scenario (${assessment:,}); "
            f"not a published {name} average."
        )
    assessment_policy = {
        "measureType": assessment_measure_type,
        "declaration": (
            "controlTotal.assessmentMeasureType"
            if assessment_measure_declared
            else "builder-default reference scenario (preview only)"
        ),
        "sourceId": assessment_source_id,
        "sourceAuthority": assessment_source.get("authority"),
        "sealedEligible": assessment_measure_declared,
    }

    facts: list[dict] = []
    if absolute_levy is not None:
        if not control.get("levyExcerpt"):
            raise SystemExit(
                "controlTotal.levyExcerpt is required for an absolute levy FACT"
            )
        facts.append(
            fact(
                id=f"{prefix}-LEVY-{fiscal_year}",
                sourceId=budget_source_id,
                page=int(control.get("levyPage", 1)),
                label=control.get("levyLabel")
                or f"{name} {fiscal_year} published net tax levy",
                amountCad=absolute_levy,
                unit="cad",
                measureType="absolute_levy",
                excerpt=control["levyExcerpt"],
                status=control.get("status", "approved"),
            )
        )
    facts.extend(
        [
        fact(
            id=assessment_fact_id,
            sourceId=assessment_source_id,
            page=int(control.get("assessmentPage", control.get("levyPage", 1))),
            label=assessment_fact_label,
            amountCad=assessment,
            unit="cad",
            measureType=assessment_measure_type,
            excerpt=assessment_excerpt,
            status=assessment_fact_status,
        ),
        fact(
            id=f"{prefix}-TAXRATE-RES-CITY-{fiscal_year}",
            sourceId=rate_source_id,
            page=rate_page,
            label=f"RT Residential local tax rate {fiscal_year}",
            amountCad=rate_city,
            unit="rate",
            sourceRateUnit=resolved_rate_unit,
            canonicalRateUnit="decimal",
            rateUnitDeclaration=rate_unit_declaration,
            excerpt=rate_excerpt,
            status="final",
        ),
        fact(
            id=f"{prefix}-TAXRATE-RES-REGION-{fiscal_year}",
            sourceId=rate_source_id,
            page=rate_page,
            label=f"RT Residential Region tax rate {fiscal_year} (as printed locally)",
            amountCad=rate_region,
            unit="rate",
            sourceRateUnit=resolved_rate_unit,
            canonicalRateUnit="decimal",
            rateUnitDeclaration=rate_unit_declaration,
            excerpt=rate_excerpt,
            status="final",
        ),
        fact(
            id=f"{prefix}-TAXRATE-RES-EDUCATION-{fiscal_year}",
            sourceId=rate_source_id,
            page=rate_page,
            label=f"RT Residential Education tax rate {fiscal_year}",
            amountCad=rate_edu,
            unit="rate",
            sourceRateUnit=resolved_rate_unit,
            canonicalRateUnit="decimal",
            rateUnitDeclaration=rate_unit_declaration,
            excerpt=rate_excerpt,
            status="final",
        ),
        fact(
            id=f"{prefix}-TAXRATE-RES-TOTAL-{fiscal_year}",
            sourceId=rate_source_id,
            page=rate_page,
            label=f"RT Residential total tax rate {fiscal_year}",
            amountCad=rate_total,
            unit="rate",
            sourceRateUnit=resolved_rate_unit,
            canonicalRateUnit="decimal",
            rateUnitDeclaration=rate_unit_declaration,
            excerpt=rate_excerpt,
            status="final",
        ),
        ]
    )

    if control.get("taxIncreasePct") is not None:
        excerpt = (
            control.get("taxIncreaseExcerpt")
            or control.get("increaseExcerpt")
            or control.get("levyExcerpt")
        )
        if not excerpt:
            raise SystemExit("controlTotal.taxIncreasePct requires a source excerpt")
        facts.append(
            fact(
                id=f"{prefix}-TAX-INCREASE-PCT-{fiscal_year}",
                sourceId=budget_source_id,
                page=int(control.get("increasePage", control.get("levyPage", 1))),
                label=f"{fiscal_year} property tax rate increase (local)",
                amountCad=_decimal(
                    control["taxIncreasePct"],
                    label="controlTotal.taxIncreasePct",
                ),
                unit="percent",
                measureType="rate_increase",
                excerpt=excerpt,
                status=control.get("status", "approved"),
            )
        )
    if control.get("levyIncreaseCad") is not None:
        excerpt = (
            control.get("levyIncreaseExcerpt")
            or control.get("levyExcerpt")
            or control.get("increaseExcerpt")
        )
        if not excerpt:
            raise SystemExit("controlTotal.levyIncreaseCad requires a source excerpt")
        facts.append(
            fact(
                id=f"{prefix}-LEVY-INCREASE-CAD-{fiscal_year}",
                sourceId=budget_source_id,
                page=int(
                    control.get(
                        "levyIncreasePage",
                        control.get("increasePage", control.get("levyPage", 1)),
                    )
                ),
                label=control.get("levyIncreaseLabel")
                or f"{fiscal_year} published tax levy increase dollars",
                amountCad=_decimal(
                    control["levyIncreaseCad"],
                    label="controlTotal.levyIncreaseCad",
                ),
                unit="cad",
                measureType="levy_increase",
                excerpt=excerpt,
                status=control.get("status", "approved"),
            )
        )
    if control.get("averageHouseholdIncreaseCad") is not None:
        excerpt = (
            control.get("averageHouseholdIncreaseExcerpt")
            or control.get("increaseExcerpt")
            or control.get("levyExcerpt")
        )
        if not excerpt:
            raise SystemExit(
                "controlTotal.averageHouseholdIncreaseCad requires a source excerpt"
            )
        facts.append(
            fact(
                id=f"{prefix}-AVG-HOUSEHOLD-INCREASE-CAD-{fiscal_year}",
                sourceId=budget_source_id,
                page=int(
                    control.get(
                        "averageHouseholdIncreasePage",
                        control.get("increasePage", control.get("levyPage", 1)),
                    )
                ),
                label=control.get("averageHouseholdIncreaseLabel")
                or f"{fiscal_year} average-household local tax increase dollars",
                amountCad=_decimal(
                    control["averageHouseholdIncreaseCad"],
                    label="controlTotal.averageHouseholdIncreaseCad",
                ),
                unit="cad",
                measureType="average_household_increase",
                excerpt=excerpt,
                status=control.get("status", "approved"),
            )
        )

    if has_dept_alloc:
        facts.append(
            fact(
                id=f"{prefix}-NET-DEPT-EXP-{fiscal_year}",
                sourceId=dept_source_id,
                page=int(control.get("allocPage", 1)),
                label=f"Net departmental expenditures {fiscal_year} (allocation base)",
                amountCad=alloc_base,
                excerpt=control.get("allocExcerpt") or f"allocation base {alloc_base:,}",
                status="approved",
            )
        )
        for d in depts:
            facts.append(
                fact(
                    id=d["id"],
                    sourceId=d.get("sourceId", dept_source_id),
                    page=int(d.get("page", 1)),
                    label=f"{d['label']} — {fiscal_year} department total",
                    amountCad=int(d["amountCad"]),
                    excerpt=d["excerpt"],
                    status="approved",
                )
            )

    # Region schedule FACTS
    area_tag = area_key.upper()
    total_fact_id = f"ROW-{area_tag}-HH-TOTAL-{fiscal_year}"
    facts.append(
        fact(
            id=total_fact_id,
            sourceId=region_source_id,
            page=hh_page,
            label=f"Tax-supported regional services cost per average {area_key} household",
            amountCad=hh_total,
            excerpt=(
                f"{area_label} ... Regional Tax Levy ... ${hh_total:,} ... "
                f"Based on an average residential property valued at ${hh_assessment:,}"
            ),
            status="approved",
            assessmentBasisCad=hh_assessment,
            note=(
                f"Imported from shared region-of-waterloo-on schedule ({area_key}). "
                f"Do not add to local rate×${assessment:,} Region portion."
            ),
        )
    )
    facts.append(
        fact(
            id=f"ROW-HH-PIL-{fiscal_year}",
            sourceId=region_source_id,
            page=hh_page,
            label="Payments in Lieu & Supplementary Taxes (household share)",
            amountCad=area["pilAndSupplementaryCad"],
            excerpt="Less: Payments in Lieu & Supplementary Taxes(3) ($78)",
            status="approved",
        )
    )
    for line in area["lines"]:
        facts.append(
            fact(
                id=line["id"],
                sourceId=region_source_id,
                page=hh_page,
                label=f"{area_key.capitalize()} household — {line['label']}",
                amountCad=line["amountCad"],
                regionalNetExpenditure000s=line["netExpenditure000Cad"],
                regionalPropertyTaxLevy000s=line["propertyTaxLevy000Cad"],
                excerpt=f"{line['label']} ... {area_key.capitalize()} ${line['amountCad']}",
                status="approved",
                assessmentBasisCad=hh_assessment,
            )
        )

    derived_rows: list[dict] = []
    city_lines: list[dict] = []

    if has_dept_alloc:
        derived_rows.append(
            derived(
                id=f"DRV-{prefix}-ALLOCATION-BASE-{fiscal_year}",
                label="Department net-expenditure allocation base",
                amountCad=alloc_base,
                formula=f"sum(department totals) == {prefix}-NET-DEPT-EXP-{fiscal_year}",
                inputs=[d["id"] for d in depts] + [f"{prefix}-NET-DEPT-EXP-{fiscal_year}"],
            )
        )

    drv_city = f"DRV-{prefix}-BILL-CITY"
    drv_region = f"DRV-{prefix}-BILL-REGION"
    drv_edu = f"DRV-{prefix}-BILL-EDUCATION"
    drv_combined = f"DRV-{prefix}-BILL-COMBINED"
    derived_rows.extend(
        [
            derived(
                id=drv_city,
                label=f"Local portion at {assessment_context}",
                amountCad=city_portion,
                formula=f"{assessment_fact_id} * {prefix}-TAXRATE-RES-CITY-{fiscal_year}",
                inputs=[assessment_fact_id, f"{prefix}-TAXRATE-RES-CITY-{fiscal_year}"],
            ),
            derived(
                id=drv_region,
                label=f"Region portion at {assessment_context}",
                amountCad=region_portion,
                formula=f"{assessment_fact_id} * {prefix}-TAXRATE-RES-REGION-{fiscal_year}",
                inputs=[assessment_fact_id, f"{prefix}-TAXRATE-RES-REGION-{fiscal_year}"],
            ),
            derived(
                id=drv_edu,
                label=f"Education portion at {assessment_context}",
                amountCad=edu_portion,
                formula=f"{assessment_fact_id} * {prefix}-TAXRATE-RES-EDUCATION-{fiscal_year}",
                inputs=[assessment_fact_id, f"{prefix}-TAXRATE-RES-EDUCATION-{fiscal_year}"],
            ),
        ]
    )
    combined_inputs = [
        drv_city,
        drv_region,
        drv_edu,
        f"{prefix}-TAXRATE-RES-TOTAL-{fiscal_year}",
    ]
    combined_formula = "city + region + education"
    if rounding_adjustment:
        drv_rounding = f"DRV-{prefix}-BILL-ROUNDING"
        derived_rows.append(
            derived(
                id=drv_rounding,
                label="Source-declared bill rounding adjustment",
                amountCad=rounding_adjustment,
                formula=(
                    "rounded(assessment * total rate) - "
                    "sum(rounded component amounts)"
                ),
                inputs=[
                    drv_city,
                    drv_region,
                    drv_edu,
                    assessment_fact_id,
                    f"{prefix}-TAXRATE-RES-TOTAL-{fiscal_year}",
                ],
                roundingPolicy=bill["policy"],
            )
        )
        combined_inputs.append(drv_rounding)
        combined_formula = "city + region + education + rounding adjustment"
    elif bill["policy"]["strategy"] == "total":
        combined_formula = "rounded(assessment * total rate)"
        combined_inputs = [
            assessment_fact_id,
            f"{prefix}-TAXRATE-RES-TOTAL-{fiscal_year}",
        ]
    derived_rows.append(
        derived(
            id=drv_combined,
            label=f"Combined RT bill at {assessment_context}",
            amountCad=combined,
            formula=combined_formula,
            inputs=combined_inputs,
            roundingPolicy=bill["policy"],
        )
    )

    if has_dept_alloc:
        for d in depts:
            share = Decimal(int(d["amountCad"])) / Decimal(alloc_base)
            line_amt = _round_to_quantum(city_portion * share)
            derived_id = f"DRV-{d['id']}-HH"
            derived_rows.append(
                derived(
                    id=derived_id,
                    label=f"Household share — {d['label']}",
                    amountCad=line_amt,
                    formula=f"{drv_city} * ({d['id']} / DRV-{prefix}-ALLOCATION-BASE-{fiscal_year})",
                    inputs=[drv_city, d["id"], f"DRV-{prefix}-ALLOCATION-BASE-{fiscal_year}"],
                )
            )
            city_lines.append(
                {
                    "id": d["id"],
                    "label": d["label"],
                    "amountCad": line_amt,
                    "classification": "city_levy_allocated",
                    "evidenceStatus": "DERIVED",
                    "sourceFactId": derived_id,
                    "note": (
                        f"Pro-rata of department allocation base (${alloc_base:,}) "
                        f"against local tax ${city_portion:,.2f}"
                    ),
                }
            )
        lines_sum = sum(
            (x["amountCad"] for x in city_lines),
            Decimal("0"),
        )
        residual = _round_to_quantum(city_portion - lines_sum)
        if residual != 0:
            city_lines.append(
                {
                    "id": f"{prefix}-ALLOC-ROUNDING",
                    "label": "Allocation rounding",
                    "amountCad": residual,
                    "classification": "reconciling_item",
                    "evidenceStatus": "RECONCILING",
                    "note": "Cent rounding so department shares sum to the local portion.",
                }
            )
        for sub in cfg.get("disclosureSublines") or []:
            parent_id = sub["parentDeptId"]
            amount = int(sub["amountCad"])
            fire_share = _round_to_quantum(
                city_portion * (Decimal(amount) / Decimal(alloc_base))
            )
            sub_drv = f"DRV-{prefix}-{sub['id']}"
            derived_rows.append(
                derived(
                    id=sub_drv,
                    label=sub["label"],
                    amountCad=fire_share,
                    formula=f"{drv_city} * ({sub['factId']} / DRV-{prefix}-ALLOCATION-BASE-{fiscal_year})",
                    inputs=[drv_city, sub["factId"], f"DRV-{prefix}-ALLOCATION-BASE-{fiscal_year}"],
                )
            )
            for line in city_lines:
                if line["id"] == parent_id:
                    line["subLines"] = [
                        {
                            "id": sub["id"],
                            "label": sub.get("uiLabel") or sub["label"],
                            "amountCad": fire_share,
                            "classification": "disclosure_subline",
                            "evidenceStatus": "DERIVED",
                            "sourceFactId": sub_drv,
                            "note": "Already included in parent line; not added to any total.",
                        }
                    ]
            facts.append(
                fact(
                    id=sub["factId"],
                    sourceId=sub.get("sourceId", dept_source_id),
                    page=int(sub.get("page", 1)),
                    label=sub["factLabel"],
                    amountCad=amount,
                    excerpt=sub["excerpt"],
                    status="approved",
                )
            )
    else:
        city_lines.append(
            {
                "id": f"{prefix}-LOCAL-RATE-PORTION",
                "label": f"{name} (combined — rate × {assessment_context})",
                "amountCad": city_portion,
                "classification": "city_levy_unallocated",
                "evidenceStatus": "DERIVED",
                "sourceFactId": drv_city,
                "note": (
                    "Department allocation base not transcribed for this Tier 0 pack "
                    f"(see GAP-{prefix}-DEPT-SCHEDULE)."
                ),
                "gapId": f"GAP-{prefix}-DEPT-SCHEDULE",
            }
        )

    region_lines = [
        {
            "id": f"{prefix}-REGION-RATE-PORTION",
            "label": f"Region of Waterloo (combined — rate × {assessment_context})",
            "amountCad": region_portion,
            "classification": "region_tax_supported",
            "evidenceStatus": "DERIVED",
            "sourceFactId": drv_region,
            "note": (
                f"Printed REGION rate × ${assessment:,}. Region-published {area_key} service "
                f"lines at ${hh_assessment:,} are under regionIllustrationAt354500."
            ),
        }
    ]

    region_illustration_lines = [
        {
            "id": line["id"],
            "label": line["label"],
            "amountCad": line["amountCad"],
            "classification": "region_schedule_illustration",
            "evidenceStatus": "FACT",
            "sourceFactId": line["id"],
            "note": f"Region-published at ${hh_assessment:,}; not part of the ${assessment:,} bill.",
        }
        for line in area["lines"]
    ]
    if area["roundingAdjustmentCad"]:
        region_illustration_lines.append(
            {
                "id": f"ROW-HH-{area_tag}-ROUNDING",
                "label": "Unallocated table-rounding difference (source total vs summed lines)",
                "amountCad": area["roundingAdjustmentCad"],
                "classification": "reconciling_item",
                "evidenceStatus": "RECONCILING",
                "note": (
                    f"Printed lines sum ${area['servicesSubtotalCad']:,}; "
                    f"printed subtotal ${area['publishedServicesSubtotalCad']:,}."
                ),
            }
        )
    region_illustration_lines.append(
        {
            "id": "ROW-HH-PIL-OFFSET",
            "label": "Less: Payments in Lieu & Supplementary Taxes (household share)",
            "amountCad": area["pilAndSupplementaryCad"],
            "classification": "region_schedule_illustration",
            "evidenceStatus": "FACT",
            "sourceFactId": f"ROW-HH-PIL-{fiscal_year}",
        }
    )

    gaps: list[dict] = []
    if absolute_levy is None:
        legacy_detail = (
            " A legacy levyCad value is present but is not classified as "
            "measureType: absolute_levy, so it was not promoted to FACT."
            if control.get("levyCad") is not None
            else ""
        )
        gaps.append(
            gap(
                id=f"GAP-{prefix}-LEVY-ABSOLUTE",
                title="Absolute net tax levy is not bound as a typed control total",
                detail=(
                    "No source-bound controlTotal with measureType "
                    f"absolute_levy is available for {fiscal_year}.{legacy_detail}"
                ),
                blocks=["absolute_levy_control"],
                neededEvidence=[
                    "Published absolute net tax levy with source page and excerpt"
                ],
            )
        )
    elif has_dept_alloc and absolute_levy != alloc_base:
        gaps.append(
            gap(
                id=f"GAP-{prefix}-LEVY-VS-DEPTS",
                title="Published net tax levy differs from net departmental expenditures",
                detail=(
                    f"Published levy ${absolute_levy:,}; allocation base ${alloc_base:,} "
                    f"(delta ${absolute_levy - alloc_base:,}). Household department shares use the "
                    "department base, not the levy headline."
                ),
                blocks=[],
                neededEvidence=["One-page reconciliation from levy headline to department totals"],
            )
        )
    if (
        control.get("taxIncreaseCad") is not None
        and control.get("levyIncreaseCad") is None
        and control.get("averageHouseholdIncreaseCad") is None
    ):
        gaps.append(
            gap(
                id=f"GAP-{prefix}-INCREASE-MEASURE-TYPE",
                title="Legacy tax increase dollars lack a typed measure",
                detail=(
                    "taxIncreaseCad is ambiguous and was not promoted to FACT. "
                    "Classify the source value as levyIncreaseCad or "
                    "averageHouseholdIncreaseCad."
                ),
                blocks=[],
                neededEvidence=["Typed dollar-increase measure and matching source excerpt"],
            )
        )
    if not has_dept_alloc:
        gaps.append(
            gap(
                id=f"GAP-{prefix}-DEPT-SCHEDULE",
                title="Local department household allocation not transcribed",
                detail=(
                    f"This Tier 0 pack cites the local rate × ${assessment:,} as a single line. "
                    "A published department / service split for household illustration has not "
                    "been bound into the allocation base yet."
                ),
                blocks=["township_department_lines"],
                neededEvidence=["Department net expenditure table suitable for pro-rata"],
            )
        )

    gaps.append(
        gap(
            id=f"GAP-{prefix}-REGION-ASSESSMENT-BRIDGE",
            title=(
                f"No DERIVED bridge from Region ${hh_assessment:,} {area_key} schedule "
                f"to local ${assessment:,} rate bill"
            ),
            detail=(
                f"Local bill uses REGION rate × ${assessment:,} = ${region_portion:,.2f}. "
                f"Region {area_key} household schedule totals ${hh_total:,} at ${hh_assessment:,}. "
                "Informational only until an explicit rate×assessment DERIVED path is approved."
            ),
            blocks=[],
            neededEvidence=[
                f"Approved formula mapping Region {area_key} HH lines onto the local {assessment_context} bill"
            ],
        )
    )
    if assessment_code_evidence is None:
        gaps.append(
            gap(
                id=f"GAP-{prefix}-FIR-CODE-VERIFY",
                title="FIR / MAH assessment code not yet locked from Schedule 02",
                detail=(
                    f"Pack uses working code {assessment_code} pending a hand-checked FIR Schedule 02 row."
                ),
                blocks=[],
                neededEvidence=[f"FIR Schedule 02 MAH code for {name}"],
            )
        )
    gaps.append(
        gap(
            id=f"GAP-{prefix}-PEER-FIR-FAIRNESS",
            title=f"Peer per-capita fairness check not yet run for {name}",
            detail="Tier 0 draft: no peer FIR findings published.",
            blocks=["findings_peer_fairness"],
            neededEvidence=["Hand-checked FIR Schedule 40 peer cohort"],
        )
    )
    for extra in cfg.get("extraGaps") or []:
        extra_gap = gap(**extra)
        duplicate_index = next(
            (
                index
                for index, existing in enumerate(gaps)
                if existing["id"] == extra_gap["id"]
            ),
            None,
        )
        if duplicate_index is None:
            gaps.append(extra_gap)
        else:
            gaps[duplicate_index] = extra_gap

    closed_gaps = [
        {
            "id": f"GAP-{prefix}-REGION-SCHEDULE",
            "title": f"Region of Waterloo {area_key} household schedule imported from shared pack",
            "resolvedAt": "2026-07-25",
            "resolution": (
                f"{area_key} column imported from corpus/region-of-waterloo-on/schedules/"
                f"household-tax-supported-{fiscal_year}.yaml. Lines appear under regionIllustrationAt354500 "
                f"at ${hh_assessment:,}. Bill-stack Region total remains rate × ${assessment:,} "
                f"(${region_portion:,.2f}). Narrowed remainder: GAP-{prefix}-REGION-ASSESSMENT-BRIDGE."
            ),
        }
    ]
    closed_gaps.extend(cfg.get("extraClosedGaps") or [])

    share_city = rate_city / rate_total
    share_reg = rate_region / rate_total
    share_edu = rate_edu / rate_total
    implied_5000 = _round_to_quantum(
        Decimal("5000") / rate_total,
        quantum=Decimal("1"),
    )

    ledger = {
        "schemaVersion": "2.0.0",
        "artifact": "EvidenceLedger",
        "fiscalYear": int(fiscal_year),
        "currency": currency,
        "buildPolicies": {
            "fiscalYear": fiscal_year_policy,
            "rateUnit": rate_policy,
            "rounding": bill["policy"],
            "assessment": assessment_policy,
        },
        "jurisdiction": {
            "slug": slug,
            "name": name,
            "aliases": aliases,
            "level": level,
            "upperTier": upper,
            "assessmentCode": assessment_code,
            "note": (
                "Lower-tier in Region of Waterloo. "
                + (
                    f"Assessment code matched locked registry "
                    f"{assessment_code_evidence['registryPath']}."
                    if assessment_code_evidence
                    else "Assessment code pending Schedule 02 lock."
                )
            ),
            **(
                {"assessmentCodeEvidence": assessment_code_evidence}
                if assessment_code_evidence
                else {}
            ),
        },
        "evidencePolicy": {
            "rules": [
                "FACT requires a published source, page, and excerpt or numeric binding.",
                "DERIVED requires an explicit formula over FACT/DERIVED ids only.",
                "Never invent bill dollars to fill a GAP.",
                "JUDGMENT billImpactCad is always null until a formula is approved.",
                "Do not copy another municipality's Region household table into this pack.",
            ]
        },
        "sources": sources,
        "facts": facts,
        "derived": derived_rows,
        "gaps": gaps,
        "closedGaps": closed_gaps,
    }

    increase_note = ""
    if control.get("averageHouseholdIncreaseCad") is not None:
        increase_note = (
            f" Published local increase ${control['averageHouseholdIncreaseCad']} / "
            f"{control.get('taxIncreasePct', '?')}% is local-portion only."
        )

    township_bucket: dict = {
        "basis": (
            f"{name} local portion at {assessment_context}"
            + (" — department pro-rata" if has_dept_alloc else " — unallocated pending department schedule")
        ),
        "amountCad": city_portion,
        "assessmentCad": assessment,
        "evidenceStatus": "DERIVED",
        "sourceFactId": drv_city,
        "lineItems": city_lines,
        "uiLabel": local_label,
        "note": f"Local rate × ${assessment:,} = ${city_portion:,.2f}.{increase_note}",
    }
    if not has_dept_alloc:
        township_bucket["gapId"] = f"GAP-{prefix}-DEPT-SCHEDULE"

    receipt = {
        "schemaVersion": "2.0.0",
        "artifact": "TaxpayerReceipt",
        "fiscalYear": int(fiscal_year),
        "currency": currency,
        "status": "partial_evidence_based",
        "purpose": (
            f"{name} {fiscal_year} taxpayer receipt. "
            "Lower-tier: local + Region of Waterloo + education."
        ),
        "evidencePolicyRef": f"{data_dir}/evidence-ledger.json",
        "jurisdiction": {
            "slug": slug,
            "displayName": name,
            "level": level,
            "aliases": aliases,
        },
        "profiles": {
            "supportedAverageHousehold": {
                "description": profile_description,
                "township": township_bucket,
                "region": {
                    "basis": (
                        f"Printed REGION rate on local {fiscal_year} rates sheet at ${assessment:,}"
                    ),
                    "amountCad": region_portion,
                    "assessmentCad": assessment,
                    "evidenceStatus": "DERIVED",
                    "sourceFactId": drv_region,
                    "lineItems": region_lines,
                    "uiLabel": "Region portion",
                    "note": (
                        f"Bill total is rate × ${assessment:,} = ${region_portion:,.2f}. "
                        f"Region-published {area_key} breakdown at ${hh_assessment:,} "
                        f"(${hh_total:,} after PIL) is under regionIllustrationAt354500."
                    ),
                },
                "regionIllustrationAt354500": {
                    "description": (
                        f"Region-published {area_label} tax-supported services at "
                        f"${hh_assessment:,} — INFORMATIONAL only."
                    ),
                    "basis": (
                        f"Region {fiscal_year} Budget Book p.{hh_page} {area_key} column "
                        f"(shared pack schedule) at ${hh_assessment:,}"
                    ),
                    "amountCad": hh_total,
                    "assessmentCad": hh_assessment,
                    "evidenceStatus": "FACT",
                    "sourceFactId": total_fact_id,
                    "uiLabel": f"Region illustration @ ${hh_assessment:,}",
                    "lineItems": region_illustration_lines,
                    "lineItemsSumCheckCad": sum(x["amountCad"] for x in region_illustration_lines),
                    "note": (
                        f"Do not add these dollars to the local ${assessment:,} bill. "
                        f"See GAP-{prefix}-REGION-ASSESSMENT-BRIDGE."
                    ),
                    "gapId": f"GAP-{prefix}-REGION-ASSESSMENT-BRIDGE",
                },
                "education": {
                    "basis": f"RT Residential Education rate at ${assessment:,}",
                    "amountCad": edu_portion,
                    "assessmentCad": assessment,
                    "evidenceStatus": "DERIVED",
                    "sourceFactId": drv_edu,
                    "note": "Province sets this rate; the local municipality collects it.",
                    "uiLabel": "Education",
                },
                "combinedTotalCad": combined,
                "combinedAtAssessment": {
                    "assessmentCad": assessment,
                    "basis": (
                        f"RT Residential rates applied to {assessment_context}; "
                        f"assessment evidence: {assessment_fact_id}"
                    ),
                    "evidenceStatus": "DERIVED",
                    "components": [
                        {
                            "label": name,
                            "amountCad": city_portion,
                            "rate": rate_city,
                            "sourceFactId": f"{prefix}-TAXRATE-RES-CITY-{fiscal_year}",
                        },
                        {
                            "label": "Region of Waterloo",
                            "amountCad": region_portion,
                            "rate": rate_region,
                            "sourceFactId": f"{prefix}-TAXRATE-RES-REGION-{fiscal_year}",
                        },
                        {
                            "label": "Education (Province of Ontario)",
                            "amountCad": edu_portion,
                            "rate": rate_edu,
                            "sourceFactId": f"{prefix}-TAXRATE-RES-EDUCATION-{fiscal_year}",
                        },
                    ],
                    "totalCad": combined,
                    "totalRate": rate_total,
                    "calculationPolicy": {
                        "fiscalYear": fiscal_year_policy,
                        "rateUnit": rate_policy,
                        "rounding": bill["policy"],
                        "assessment": assessment_policy,
                        "componentSumCad": bill["componentSum"],
                        "totalRateAmountCad": bill["totalRateAmount"],
                        "roundingAdjustmentCad": rounding_adjustment,
                        "componentVsTotalRateDeltaCad": bill[
                            "componentVsTotalRateDelta"
                        ],
                    },
                },
                "combinedTotalNote": (
                    f"Local ${city_portion:,.2f} + Region ${region_portion:,.2f} + "
                    f"Education ${edu_portion:,.2f}"
                    + (
                        f" + source rounding {rounding_adjustment:+,.2f}"
                        if rounding_adjustment
                        else ""
                    )
                    + f" = ${combined:,.2f} at ${assessment:,}."
                ),
                "warnings": [
                    (
                        "Local published increase (if shown) is local portion only — "
                        "not the full combined bill change."
                    ),
                    (
                        "Department shares are a pro-rata model when an allocation base is present — "
                        "not a published per-household split."
                        if has_dept_alloc
                        else "Local department split is GAP until a suitable table is transcribed."
                    ),
                    (
                        f"Region bill line is rate × ${assessment:,}; Region {area_key} schedule at "
                        f"${hh_assessment:,} is informational only "
                        f"(GAP-{prefix}-REGION-ASSESSMENT-BRIDGE)."
                    ),
                    "Utilities (water / sanitary / storm) are billed separately and are not part of this property-tax receipt.",
                ]
                + (
                    [
                        "Rate unit uses legacy preferPercent metadata. "
                        "Set rates.rateUnit before sealing this pack."
                    ]
                    if not rate_policy["sealedEligible"]
                    else []
                )
                + (
                    [
                        "Bill rounding uses the preview-only builder default. "
                        "Bind rates.rounding to a named source before sealing this pack."
                    ]
                    if not bill["policy"]["sealedEligible"]
                    else []
                )
                + (
                    [
                        "Fiscal year uses a preview-only builder default. "
                        "Set fiscalYear before sealing this pack."
                    ]
                    if not fiscal_year_policy["sealedEligible"]
                    else []
                )
                + (
                    [
                        "Assessment is treated as a reference scenario, not a "
                        "published local average. Declare assessmentMeasureType "
                        "and bind its source before sealing this pack."
                    ]
                    if not assessment_policy["sealedEligible"]
                    else []
                ),
            },
            "hypothetical5000": {
                "amountCad": 5000,
                "evidenceStatus": "DERIVED",
                "allocatable": True,
                "impliedAssessmentCad": implied_5000,
                "compositionShares": [
                    {
                        "label": name,
                        "share": share_city,
                        "sourceFactId": f"{prefix}-TAXRATE-RES-CITY-{fiscal_year}",
                    },
                    {
                        "label": "Region of Waterloo",
                        "share": share_reg,
                        "sourceFactId": f"{prefix}-TAXRATE-RES-REGION-{fiscal_year}",
                    },
                    {
                        "label": "Education (Province of Ontario)",
                        "share": share_edu,
                        "sourceFactId": f"{prefix}-TAXRATE-RES-EDUCATION-{fiscal_year}",
                    },
                ],
                "message": (
                    f"A $5,000 total bill implies an assessment of about ${implied_5000:,}. "
                    "Shown as rate shares rather than invented department dollars."
                ),
            },
        },
        "findings": [],
        "uiModelHints": {
            "municipalBucketLabel": local_label,
            "regionBucketLabel": "Region portion",
            "defaultProfile": "supportedAverageHousehold",
            "showGapsAsFirstClassUi": True,
            "forbidFillerAllocation": True,
            "marqueeFindings": [],
            "publishedFindingIds": [],
        },
    }

    return _json_safe(ledger), _json_safe(receipt)


def write_artifacts(cfg: dict, ledger: dict, receipt: dict) -> Path:
    data, web = resolve_artifact_directories(cfg)
    data.mkdir(parents=True, exist_ok=True)
    web.mkdir(parents=True, exist_ok=True)
    for folder in (data, web):
        (folder / "evidence-ledger.json").write_text(
            json.dumps(ledger, indent=2) + "\n", encoding="utf-8"
        )
        (folder / "taxpayer-receipt.json").write_text(
            json.dumps(receipt, indent=2) + "\n", encoding="utf-8"
        )
    print(f"wrote {data}/evidence-ledger.json")
    print(f"wrote {data}/taxpayer-receipt.json")
    print(f"copied to {web}/")
    return data


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if not args:
        print("Usage: python scripts/build_lower_tier_pack.py <slug>", file=sys.stderr)
        return 1
    path = resolve_inputs_path(args[0])
    cfg = load_inputs(path)
    ledger, receipt = build_pack(cfg)
    data = write_artifacts(cfg, ledger, receipt)
    # Run citation audit into data dir
    audit_script = ROOT / "scripts" / "audit_citations.py"
    if audit_script.exists():
        import subprocess

        subprocess.run(
            [sys.executable, str(audit_script), str(data / "evidence-ledger.json")],
            cwd=str(ROOT),
            check=False,
        )
        audit_src = data / "citation-audit.json"
        if audit_src.exists():
            _, web_data = resolve_artifact_directories(cfg)
            web_audit = web_data / "citation-audit.json"
            web_audit.parent.mkdir(parents=True, exist_ok=True)
            web_audit.write_text(audit_src.read_text(encoding="utf-8"), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
