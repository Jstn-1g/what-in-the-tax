"""Build a receipt's taxingBodies[] from the components the bill already prints.

Two rules shape this module.

**Roles are declared, never inferred.** The caller supplies a role for each
component, keyed by its sourceFactId. A label is not evidence of a role: the
receipt's own disclaimer says display names are never used to guess one, and
"Region of Waterloo" being an upper tier is a fact about Ontario's structure, not
about the string. An undeclared component is an error, so adding a fourth line to
a bill forces someone to say what it is rather than silently inheriting a
neighbour's role.

**Bodies are derived from the components, not written alongside them.** The
amounts a reader sees and the amounts in taxingBodies[] are then the same
numbers by construction. Maintaining two hand-written copies of a bill is how
they end up disagreeing, and a receipt whose breakdown contradicts its own total
is the worst thing this project could publish.

The invariants below are deliberately the same ones web/src/lib/taxingBodies.ts
re-checks in the browser. A reader should not have to trust bytes that travelled
over a network, and the builder should not be the only thing standing between a
malformed bill and a page.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Iterable, Mapping, Sequence

ROLES = ("local", "special-area", "upper-tier", "education")

# Roles a single bill may name at most once. Two local governments is a defect,
# not an unusual municipality.
SINGULAR_ROLES = ("local", "upper-tier", "education")


class TaxingBodyError(RuntimeError):
    """A bill could not be expressed as a coherent list of taxing bodies."""


def build_taxing_bodies(
    components: Sequence[Mapping[str, Any]],
    roles_by_fact_id: Mapping[str, str],
    *,
    total_cad: float,
    assessment_cad: int | None = None,
    basis: str,
    evidence_status: str = "DERIVED",
    ids_by_fact_id: Mapping[str, str] | None = None,
    notes_by_fact_id: Mapping[str, str] | None = None,
) -> list[dict[str, Any]]:
    """One body per component, in the order the bill prints them."""

    bodies: list[dict[str, Any]] = []
    for order, component in enumerate(components):
        fact_id = component.get("sourceFactId")
        if not fact_id:
            raise TaxingBodyError(
                f"component {order} ({component.get('label')!r}) has no sourceFactId, "
                "so its role cannot be declared against anything stable"
            )
        role = roles_by_fact_id.get(fact_id)
        if role is None:
            raise TaxingBodyError(
                f"no role declared for {fact_id!r} ({component.get('label')!r}). "
                "Add it to the role map; do not let it inherit a neighbour's role "
                "or be guessed from its label."
            )
        if role not in ROLES:
            raise TaxingBodyError(f"{fact_id!r} declares unknown role {role!r}; expected one of {ROLES}")

        body: dict[str, Any] = {
            "id": (ids_by_fact_id or {}).get(fact_id, fact_id.lower()),
            "role": role,
            "label": component["label"],
            "order": order,
            "amountCad": component["amountCad"],
            "basis": basis,
            "evidenceStatus": evidence_status,
            "sourceFactId": fact_id,
        }
        if assessment_cad is not None:
            body["assessmentCad"] = assessment_cad
        # Carry the rate across when the component declares one. A body's
        # amountCad is rate x assessment, but the body cited the rate fact while
        # printing the product and said nothing about the relationship - so the
        # printed number could not be checked against what it cited, and 12 of
        # these were unbound. With rate and assessmentCad both present the
        # arithmetic is stated by the artifact rather than inferred by a reader.
        rate = component.get("rate")
        # Decimal as well as float: these builders carry rates as Decimal so the
        # eight-place by-law rate is not rounded on the way in, and a plain
        # isinstance(int, float) check silently dropped every one of them.
        if isinstance(rate, Decimal):
            rate = float(rate)
        if isinstance(rate, (int, float)) and not isinstance(rate, bool):
            body["rate"] = rate
        note = (notes_by_fact_id or {}).get(fact_id)
        if note:
            body["note"] = note
        bodies.append(body)

    assert_bill_is_coherent(bodies, total_cad)
    return bodies


def assert_bill_is_coherent(
    bodies: Iterable[Mapping[str, Any]],
    total_cad: float | None,
    inapplicable: Iterable[Mapping[str, Any]] = (),
) -> None:
    """Refuse a bill that cannot be true, rather than warning about it."""

    bodies = list(bodies)
    counts: dict[str, int] = {}
    for body in bodies:
        counts[body["role"]] = counts.get(body["role"], 0) + 1

    for role in SINGULAR_ROLES:
        if counts.get(role, 0) > 1:
            raise TaxingBodyError(
                f"a bill may name at most one {role} body; this one names {counts[role]}"
            )
    if counts.get("local", 0) == 0:
        raise TaxingBodyError("a bill must name the local municipality that issues it")

    charged = {body["role"] for body in bodies}
    for entry in inapplicable:
        if entry["role"] in charged:
            raise TaxingBodyError(
                f"{entry['role']} is listed both as a taxing body and as not applicable"
            )

    if total_cad is not None:
        summed = round(sum(body["amountCad"] for body in bodies), 2)
        # A cent of rounding across four bodies is expected; a dollar is not.
        if abs(summed - total_cad) > 0.05:
            raise TaxingBodyError(
                f"taxing bodies sum to {summed:.2f} but the receipt prints {total_cad:.2f}"
            )
