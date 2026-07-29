"""Bind every printed number to the evidence node it cites.

The receipt used to be an independent authority for its own numbers. A line
could print any amount while citing a real, correct ledger node, and every gate
stayed green: the reference existed, the citation audit resolved it, and nothing
compared the two. A planted 999999 passed `validate_pack` with zero errors.

That is the whole product failing quietly. This module is the check that closes
it, and it is deliberately narrow - only relationships the artifact itself
declares are accepted:

  direct          the printed amount equals the cited node's amount
  rate x base     the object declares a rate, the cited node IS that rate, and
                  the printed amount equals rate x the assessment in scope

Anything else is unbound, and unbound is refused rather than warned about.
`GENERALIZATION-PLAN.md` section 9.5 puts `printedValue x scaleFactor !=
canonicalValue` under HARD FAIL; this applies it to the values a reader
actually sees.
"""

from __future__ import annotations

from typing import Any, Iterator, NamedTuple

# FIR and by-law figures are whole cents. A cent of rounding on a rate product
# is expected; anything above it is a real disagreement.
TOLERANCE_CAD = 0.011


class Unbound(NamedTuple):
    """One printed number that does not follow from what it cites."""

    path: str
    node_id: str
    printed: float
    node_amount: float | None
    reason: str

    def __str__(self) -> str:
        node = "missing" if self.node_amount is None else f"{self.node_amount:,.4f}"
        return (
            f"{self.path} prints {self.printed:,.2f} citing {self.node_id!r} "
            f"(node {node}): {self.reason}"
        )


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _walk(value: Any, path: str, assessment: float | None) -> Iterator[tuple[str, dict, float | None]]:
    """Yield every object carrying a citation, with the assessment in scope.

    Assessment is inherited downward: `combinedAtAssessment` sets the base its
    own components are measured against, and a component does not repeat it.
    """

    if isinstance(value, list):
        for index, child in enumerate(value):
            yield from _walk(child, f"{path}[{index}]", assessment)
        return
    if not isinstance(value, dict):
        return

    scope = assessment
    if _is_number(value.get("assessmentCad")):
        scope = float(value["assessmentCad"])

    if isinstance(value.get("sourceFactId"), str) and _is_number(value.get("amountCad")):
        yield path, value, scope

    for key, child in value.items():
        yield from _walk(child, f"{path}.{key}", scope)


def unbound_values(receipt: dict, nodes: dict[str, dict]) -> list[Unbound]:
    """Every printed number that does not follow from the node it cites.

    `nodes` maps id -> fact or derived row. Ids that do not resolve are left to
    the existing missing-reference check rather than reported twice here.
    """

    problems: list[Unbound] = []
    for path, obj, assessment in _walk(receipt, "$", None):
        node_id = obj["sourceFactId"]
        node = nodes.get(node_id)
        if node is None:
            continue
        # Rate facts carry their number under `value` in some ledgers and
        # `amountCad` in others - North Dumfries writes 0.00315303 as `value`
        # while Cambridge writes the same kind of rate as `amountCad`. Reading
        # only one of them reported seven nodes as carrying no amount when every
        # one of them does. The inconsistency is worth fixing at the source, but
        # a checker that cannot read the ledger it guards is the worse problem.
        node_amount = node.get("amountCad")
        if not _is_number(node_amount):
            node_amount = node.get("value")
        if not _is_number(node_amount):
            problems.append(
                Unbound(path, node_id, float(obj["amountCad"]), None,
                        "cited node carries no amount to bind against")
            )
            continue

        printed = float(obj["amountCad"])
        node_amount = float(node_amount)

        if abs(printed - node_amount) <= TOLERANCE_CAD:
            continue

        # A citation may support a sibling of amountCad rather than amountCad
        # itself. Brant's hypothetical5000 prints a $5,000 premise while citing
        # the derived implied assessment - and carries impliedAssessmentCad
        # equal to that node exactly. The number the node evidences is present
        # and checkable in the same object, so the citation is bound.
        #
        # The comparison scales with the node rather than using the cent
        # tolerance flat. A flat cent swallows rate-sized nodes whole: 0.0052
        # sits within a cent of a body's order: 0, so the first version of this
        # fallback quietly re-bound every doubled-rate tamper the module exists
        # to catch. The planted-defect test caught it before it shipped, which
        # is the entire argument for planted-defect tests. Structural fields
        # are excluded outright - their equality with an amount is never
        # evidence of anything.
        sibling_tolerance = min(TOLERANCE_CAD, max(abs(node_amount) * 1e-3, 1e-9))
        if any(
            _is_number(sibling)
            and key not in ("amountCad", "order", "page", "fiscalYear")
            and abs(float(sibling) - node_amount) <= sibling_tolerance
            for key, sibling in obj.items()
        ):
            continue

        # A rate is only a rate if the artifact says so and the cited node is
        # that same rate. Inferring "this looks like a rate because the numbers
        # divide nicely" would rebuild the hole this closes.
        rate = obj.get("rate")
        if _is_number(rate) and abs(float(rate) - node_amount) <= 1e-9:
            if assessment is None:
                problems.append(
                    Unbound(path, node_id, printed, node_amount,
                            "declares a rate but no assessment is in scope to apply it to")
                )
                continue
            expected = round(float(rate) * assessment, 2)
            if abs(printed - expected) <= TOLERANCE_CAD:
                continue
            problems.append(
                Unbound(path, node_id, printed, node_amount,
                        f"rate x {assessment:,.2f} is {expected:,.2f}, not the printed amount")
            )
            continue

        problems.append(
            Unbound(path, node_id, printed, node_amount,
                    "printed amount does not equal its cited node and declares no rate")
        )
    return problems
