"""Validate and inspect AuditBack's province-by-province rollout plan.

The command is offline and deterministic. It neither downloads government
data nor invokes AI, and its scaffolds are candidate-only.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from national.rollout import (  # noqa: E402
    RolloutError,
    build_rollout_report,
    load_rollout_inputs,
    render_rollout_table,
    scaffold_jurisdiction_workspace,
    validate_rollout_contract,
)


DEFAULT_CATALOG = ROOT / "national" / "source_catalog.json"
DEFAULT_COVERAGE = ROOT / "national" / "coverage_plan.json"
DEFAULT_JURISDICTIONS = ROOT / "national" / "jurisdictions"


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Validate and manage the offline AuditBack provincial rollout "
            "(0 AI tokens)"
        )
    )
    parser.add_argument("--catalog", default=str(DEFAULT_CATALOG))
    parser.add_argument("--coverage-plan", default=str(DEFAULT_COVERAGE))
    parser.add_argument("--jurisdictions", default=str(DEFAULT_JURISDICTIONS))
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser(
        "check",
        help="Validate all 13 rollout packets and their cross-file invariants",
    )
    status = subparsers.add_parser(
        "status",
        help="Render deterministic rollout readiness without claiming publication",
    )
    status.add_argument("--format", choices=("table", "json"), default="table")

    scaffold = subparsers.add_parser(
        "scaffold",
        help="Create a non-overwriting candidate workspace for one jurisdiction",
    )
    scaffold.add_argument("code", help="Two-letter province or territory code")
    scaffold.add_argument("--output", required=True)
    return parser


def run(args: argparse.Namespace) -> int:
    inputs = load_rollout_inputs(
        catalog_path=Path(args.catalog),
        coverage_plan_path=Path(args.coverage_plan),
        jurisdictions_root=Path(args.jurisdictions),
    )
    if args.command == "check":
        validate_rollout_contract(
            catalog=inputs.catalog,
            coverage_plan=inputs.coverage_plan,
            manifests=inputs.manifests,
        )
        print(
            "National rollout contract valid: 13 jurisdictions, "
            "8 ordered gates each. Runtime network: 0. AI calls: 0. AI tokens: 0."
        )
        return 0
    if args.command == "status":
        report = build_rollout_report(
            catalog=inputs.catalog,
            coverage_plan=inputs.coverage_plan,
            manifests=inputs.manifests,
        )
        if args.format == "json":
            print(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2))
        else:
            print(render_rollout_table(report))
        return 0
    if args.command == "scaffold":
        paths = scaffold_jurisdiction_workspace(
            code=args.code,
            output=Path(args.output),
            catalog=inputs.catalog,
            coverage_plan=inputs.coverage_plan,
            manifests=inputs.manifests,
        )
        print("Created candidate-only onboarding workspace:")
        for path in paths:
            print(f"- {path}")
        print("Runtime network: 0. AI calls: 0. AI tokens: 0.")
        return 0
    raise RolloutError(f"unsupported command {args.command!r}")


def main() -> int:
    parser = make_parser()
    args = parser.parse_args()
    try:
        return run(args)
    except (OSError, RolloutError, ValueError) as exc:
        parser.exit(1, f"ERROR: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
