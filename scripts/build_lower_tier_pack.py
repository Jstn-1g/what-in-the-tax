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
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from lib.region_schedule import load_region_schedule  # noqa: E402
from lib.rt_rates import parse_rt_rates_from_extract  # noqa: E402


def fact(**kwargs):
    kwargs.setdefault("kind", "FACT")
    return kwargs


def gap(**kwargs):
    kwargs.setdefault("kind", "GAP")
    return kwargs


def derived(**kwargs):
    kwargs.setdefault("kind", "DERIVED")
    return kwargs


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


def _prefix(slug: str) -> str:
    """KIT from kitchener-on, WAT from waterloo-on, etc."""
    stem = slug.replace("-on", "").replace("-county", "")
    parts = re.split(r"[-_]", stem)
    letters = "".join(p[0] for p in parts if p).upper()
    return (letters or "MUN")[:6]


def build_pack(cfg: dict) -> tuple[dict, dict]:
    slug = cfg["slug"]
    name = cfg["name"]
    aliases = cfg.get("aliases") or [name]
    level = cfg.get("level", "lower-tier")
    upper = cfg.get("parentBodies") or ["region-of-waterloo-on"]
    area_key = cfg["regionAreaKey"]
    assessment = int(cfg["defaultAssessmentCad"])
    assessment_code = str(cfg.get("assessmentCode") or "pending")
    prefix = cfg.get("idPrefix") or _prefix(slug)
    local_label = cfg.get("localBucketLabel") or "City portion"
    data_dir = cfg.get("dataDir") or f"data/{slug.replace('-on', '').split('-')[0]}"
    # Allow explicit dataDir like data/waterloo
    if "dataDir" in cfg:
        data_dir = cfg["dataDir"]
    else:
        # waterloo-on -> waterloo; woolwich-on -> woolwich; cambridge-on -> cambridge
        data_dir = f"data/{slug.removesuffix('-on')}"

    rates_cfg = cfg["rates"]
    if rates_cfg.get("fromExtract"):
        extract = ROOT / rates_cfg["fromExtract"]
        parsed = parse_rt_rates_from_extract(
            extract,
            page=rates_cfg.get("page"),
            prefer_percent=rates_cfg.get("preferPercent"),
        )
        rate_city = float(rates_cfg.get("city", parsed["city"]))
        rate_region = float(rates_cfg.get("region", parsed["region"]))
        rate_edu = float(rates_cfg.get("education", parsed["education"]))
        rate_total = float(rates_cfg.get("total", parsed["total"]))
        rate_excerpt = rates_cfg.get("excerpt") or parsed["excerpt"]
        rate_page = int(rates_cfg.get("page") or parsed["page"] or 1)
    else:
        rate_city = float(rates_cfg["city"])
        rate_region = float(rates_cfg["region"])
        rate_edu = float(rates_cfg["education"])
        rate_total = float(rates_cfg.get("total", rate_city + rate_region + rate_edu))
        rate_excerpt = rates_cfg["excerpt"]
        rate_page = int(rates_cfg.get("page", 1))

    if abs((rate_city + rate_region + rate_edu) - rate_total) > 1e-7:
        raise SystemExit(
            f"rate sum {rate_city + rate_region + rate_edu} != total {rate_total}"
        )

    city_portion = round(assessment * rate_city, 2)
    region_portion = round(assessment * rate_region, 2)
    edu_portion = round(assessment * rate_edu, 2)
    combined = round(city_portion + region_portion + edu_portion, 2)
    expected = round(assessment * rate_total, 2)
    if abs(combined - expected) > 0.02:
        raise SystemExit(f"combined {combined} != assessment*total {expected}")

    control = cfg["controlTotal"]
    levy = float(control["levyCad"])
    if levy == int(levy):
        levy = int(levy)
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

    sources.append(
        {
            "id": "row-2026-book",
            "title": region["source"]["title"],
            "url": "https://www.regionofwaterloo.ca/",
            "localPath": "source-pdfs/2026_final_budget_book_region.pdf",
            "extractedText": region["extractPath"],
            "asOf": "2026",
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

    facts: list[dict] = [
        fact(
            id=f"{prefix}-LEVY-2026",
            sourceId=budget_source_id,
            page=int(control.get("levyPage", 1)),
            label=control.get("levyLabel")
            or f"{name} 2026 published net tax levy",
            amountCad=levy,
            excerpt=control["levyExcerpt"],
            status=control.get("status", "approved"),
        ),
        fact(
            id=f"{prefix}-AVG-ASSESSMENT-2026",
            sourceId=control.get("assessmentSourceId", budget_source_id),
            page=int(control.get("assessmentPage", control.get("levyPage", 1))),
            label="Average assessed value used for residential impact illustrations",
            amountCad=assessment,
            excerpt=control["assessmentExcerpt"],
            status=control.get("status", "approved"),
        ),
        fact(
            id=f"{prefix}-TAXRATE-RES-CITY-2026",
            sourceId=rate_source_id,
            page=rate_page,
            label="RT Residential local tax rate 2026",
            amountCad=rate_city,
            unit="rate",
            excerpt=rate_excerpt,
            status="final",
        ),
        fact(
            id=f"{prefix}-TAXRATE-RES-REGION-2026",
            sourceId=rate_source_id,
            page=rate_page,
            label="RT Residential Region tax rate 2026 (as printed locally)",
            amountCad=rate_region,
            unit="rate",
            excerpt=rate_excerpt,
            status="final",
        ),
        fact(
            id=f"{prefix}-TAXRATE-RES-EDUCATION-2026",
            sourceId=rate_source_id,
            page=rate_page,
            label="RT Residential Education tax rate 2026",
            amountCad=rate_edu,
            unit="rate",
            excerpt=rate_excerpt,
            status="final",
        ),
        fact(
            id=f"{prefix}-TAXRATE-RES-TOTAL-2026",
            sourceId=rate_source_id,
            page=rate_page,
            label="RT Residential total tax rate 2026",
            amountCad=rate_total,
            unit="rate",
            excerpt=rate_excerpt,
            status="final",
        ),
    ]

    if control.get("taxIncreasePct") is not None:
        facts.append(
            fact(
                id=f"{prefix}-TAX-INCREASE-PCT-2026",
                sourceId=budget_source_id,
                page=int(control.get("increasePage", control.get("levyPage", 1))),
                label="2026 property tax rate increase (local)",
                amountCad=float(control["taxIncreasePct"]),
                unit="percent",
                excerpt=control.get("increaseExcerpt") or control["levyExcerpt"],
                status=control.get("status", "approved"),
            )
        )
    if control.get("taxIncreaseCad") is not None:
        facts.append(
            fact(
                id=f"{prefix}-TAX-INCREASE-CAD-2026",
                sourceId=budget_source_id,
                page=int(control.get("increasePage", control.get("levyPage", 1))),
                label="2026 average-home local tax increase dollars",
                amountCad=float(control["taxIncreaseCad"]),
                excerpt=control.get("increaseExcerpt") or control["levyExcerpt"],
                status=control.get("status", "approved"),
            )
        )

    if has_dept_alloc:
        facts.append(
            fact(
                id=f"{prefix}-NET-DEPT-EXP-2026",
                sourceId=dept_source_id,
                page=int(control.get("allocPage", 1)),
                label="Net departmental expenditures 2026 (allocation base)",
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
                    label=f"{d['label']} — 2026 department total",
                    amountCad=int(d["amountCad"]),
                    excerpt=d["excerpt"],
                    status="approved",
                )
            )

    # Region schedule FACTS
    area_tag = area_key.upper()
    total_fact_id = f"ROW-{area_tag}-HH-TOTAL-2026"
    facts.append(
        fact(
            id=total_fact_id,
            sourceId="row-2026-book",
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
            id="ROW-HH-PIL-2026",
            sourceId="row-2026-book",
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
                sourceId="row-2026-book",
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
                id=f"DRV-{prefix}-ALLOCATION-BASE-2026",
                label="Department net-expenditure allocation base",
                amountCad=alloc_base,
                formula=f"sum(department totals) == {prefix}-NET-DEPT-EXP-2026",
                inputs=[d["id"] for d in depts] + [f"{prefix}-NET-DEPT-EXP-2026"],
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
                label="Local portion at average assessment",
                amountCad=city_portion,
                formula=f"{prefix}-AVG-ASSESSMENT-2026 * {prefix}-TAXRATE-RES-CITY-2026",
                inputs=[f"{prefix}-AVG-ASSESSMENT-2026", f"{prefix}-TAXRATE-RES-CITY-2026"],
            ),
            derived(
                id=drv_region,
                label="Region portion at average assessment",
                amountCad=region_portion,
                formula=f"{prefix}-AVG-ASSESSMENT-2026 * {prefix}-TAXRATE-RES-REGION-2026",
                inputs=[f"{prefix}-AVG-ASSESSMENT-2026", f"{prefix}-TAXRATE-RES-REGION-2026"],
            ),
            derived(
                id=drv_edu,
                label="Education portion at average assessment",
                amountCad=edu_portion,
                formula=f"{prefix}-AVG-ASSESSMENT-2026 * {prefix}-TAXRATE-RES-EDUCATION-2026",
                inputs=[f"{prefix}-AVG-ASSESSMENT-2026", f"{prefix}-TAXRATE-RES-EDUCATION-2026"],
            ),
            derived(
                id=drv_combined,
                label="Combined RT bill at average assessment",
                amountCad=combined,
                formula="city + region + education",
                inputs=[drv_city, drv_region, drv_edu, f"{prefix}-TAXRATE-RES-TOTAL-2026"],
            ),
        ]
    )

    if has_dept_alloc:
        for d in depts:
            share = int(d["amountCad"]) / alloc_base
            line_amt = round(city_portion * share, 2)
            derived_id = f"DRV-{d['id']}-HH"
            derived_rows.append(
                derived(
                    id=derived_id,
                    label=f"Household share — {d['label']}",
                    amountCad=line_amt,
                    formula=f"{drv_city} * ({d['id']} / DRV-{prefix}-ALLOCATION-BASE-2026)",
                    inputs=[drv_city, d["id"], f"DRV-{prefix}-ALLOCATION-BASE-2026"],
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
        lines_sum = sum(x["amountCad"] for x in city_lines)
        residual = round(city_portion - lines_sum, 2)
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
            fire_share = round(city_portion * (amount / alloc_base), 2)
            sub_drv = f"DRV-{prefix}-{sub['id']}"
            derived_rows.append(
                derived(
                    id=sub_drv,
                    label=sub["label"],
                    amountCad=fire_share,
                    formula=f"{drv_city} * ({sub['factId']} / DRV-{prefix}-ALLOCATION-BASE-2026)",
                    inputs=[drv_city, sub["factId"], f"DRV-{prefix}-ALLOCATION-BASE-2026"],
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
                "label": f"{name} (combined — rate × average assessment)",
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
            "label": "Region of Waterloo (combined — rate × local average assessment)",
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
            "sourceFactId": "ROW-HH-PIL-2026",
        }
    )

    gaps: list[dict] = []
    if has_dept_alloc and levy != alloc_base:
        gaps.append(
            gap(
                id=f"GAP-{prefix}-LEVY-VS-DEPTS",
                title="Published net tax levy differs from net departmental expenditures",
                detail=(
                    f"Published levy ${levy:,}; allocation base ${alloc_base:,} "
                    f"(delta ${levy - alloc_base:,}). Household department shares use the "
                    "department base, not the levy headline."
                ),
                blocks=[],
                neededEvidence=["One-page reconciliation from levy headline to department totals"],
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
                f"Approved formula mapping Region {area_key} HH lines onto the local average assessment bill"
            ],
        )
    )
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
        gaps.append(gap(**extra))

    closed_gaps = [
        {
            "id": f"GAP-{prefix}-REGION-SCHEDULE",
            "title": f"Region of Waterloo {area_key} household schedule imported from shared pack",
            "resolvedAt": "2026-07-25",
            "resolution": (
                f"{area_key} column imported from corpus/region-of-waterloo-on/schedules/"
                f"household-tax-supported-2026.yaml. Lines appear under regionIllustrationAt354500 "
                f"at ${hh_assessment:,}. Bill-stack Region total remains rate × ${assessment:,} "
                f"(${region_portion:,.2f}). Narrowed remainder: GAP-{prefix}-REGION-ASSESSMENT-BRIDGE."
            ),
        }
    ]
    closed_gaps.extend(cfg.get("extraClosedGaps") or [])

    share_city = rate_city / rate_total
    share_reg = rate_region / rate_total
    share_edu = rate_edu / rate_total
    implied_5000 = round(5000 / rate_total)

    ledger = {
        "schemaVersion": "2.0.0",
        "artifact": "EvidenceLedger",
        "jurisdiction": {
            "slug": slug,
            "name": name,
            "aliases": aliases,
            "level": level,
            "upperTier": upper,
            "assessmentCode": assessment_code,
            "note": f"Lower-tier in Region of Waterloo. Assessment code pending Schedule 02 lock.",
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
    if control.get("taxIncreaseCad") is not None:
        increase_note = (
            f" Published local increase ${control['taxIncreaseCad']} / "
            f"{control.get('taxIncreasePct', '?')}% is local-portion only."
        )

    township_bucket: dict = {
        "basis": (
            f"{name} local portion at average assessment"
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
        "status": "partial_evidence_based",
        "purpose": (
            f"{name} 2026 taxpayer receipt. Lower-tier: local + Region of Waterloo + education."
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
                "description": f"Published average residential assessment (${assessment:,}).",
                "township": township_bucket,
                "region": {
                    "basis": (
                        f"Printed REGION rate on local 2026 rates sheet at ${assessment:,}"
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
                        f"Region 2026 Budget Book p.{hh_page} {area_key} column "
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
                    "basis": "RT Residential rates applied to published average assessment",
                    "evidenceStatus": "DERIVED",
                    "components": [
                        {
                            "label": name,
                            "amountCad": city_portion,
                            "rate": rate_city,
                            "sourceFactId": f"{prefix}-TAXRATE-RES-CITY-2026",
                        },
                        {
                            "label": "Region of Waterloo",
                            "amountCad": region_portion,
                            "rate": rate_region,
                            "sourceFactId": f"{prefix}-TAXRATE-RES-REGION-2026",
                        },
                        {
                            "label": "Education (Province of Ontario)",
                            "amountCad": edu_portion,
                            "rate": rate_edu,
                            "sourceFactId": f"{prefix}-TAXRATE-RES-EDUCATION-2026",
                        },
                    ],
                    "totalCad": combined,
                    "totalRate": rate_total,
                },
                "combinedTotalNote": (
                    f"Local ${city_portion:,.2f} + Region ${region_portion:,.2f} + "
                    f"Education ${edu_portion:,.2f} = ${combined:,.2f} at ${assessment:,}."
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
                ],
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
                        "sourceFactId": f"{prefix}-TAXRATE-RES-CITY-2026",
                    },
                    {
                        "label": "Region of Waterloo",
                        "share": share_reg,
                        "sourceFactId": f"{prefix}-TAXRATE-RES-REGION-2026",
                    },
                    {
                        "label": "Education (Province of Ontario)",
                        "share": share_edu,
                        "sourceFactId": f"{prefix}-TAXRATE-RES-EDUCATION-2026",
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

    return ledger, receipt


def write_artifacts(cfg: dict, ledger: dict, receipt: dict) -> Path:
    slug = cfg["slug"]
    data_rel = cfg.get("dataDir") or f"data/{slug.removesuffix('-on')}"
    data = ROOT / data_rel
    web = ROOT / "web" / "src" / data_rel.replace("data/", "data/")
    # web path mirrors data/<name>
    web = ROOT / "web" / "src" / Path(data_rel).as_posix()
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
            web_audit = ROOT / "web" / "src" / Path(cfg.get("dataDir") or f"data/{cfg['slug'].removesuffix('-on')}") / "citation-audit.json"
            web_audit.parent.mkdir(parents=True, exist_ok=True)
            web_audit.write_text(audit_src.read_text(encoding="utf-8"), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
