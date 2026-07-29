"""Every printed number follows from the node it cites, and stays that way.

The defect this guards against passed every gate the project had: a line item
changed from $298.54 to $999,999 with its sourceFactId intact validated with
zero errors, because the reference was checked to exist and never compared to
anything. validate_pack now refuses an unbound printed value unconditionally -
a draft is allowed weak provenance; it is not allowed to print a number
inconsistent with its own citation.

The committed-packs sweep is the part that bites: if a builder change ever
reintroduces an unbound value into web/public/packs, this fails in CI before
the artifact can deploy.
"""

from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from scripts.lib.value_binding import unbound_values

ROOT = Path(__file__).resolve().parents[1]
PACK_DIR = ROOT / "web" / "public" / "packs"


def load_packs() -> list[tuple[str, dict]]:
    return [
        (path.stem, json.loads(path.read_text(encoding="utf-8")))
        for path in sorted(PACK_DIR.glob("*.json"))
    ]


def nodes_of(pack: dict) -> dict[str, dict]:
    return {
        n["id"]: n
        for n in pack["evidence"]["facts"] + pack["evidence"]["derived"]
    }


class CommittedPacksAreFullyBound(unittest.TestCase):
    def test_no_committed_pack_prints_an_unbound_value(self) -> None:
        checked = 0
        for slug, pack in load_packs():
            problems = unbound_values(pack["receipt"], nodes_of(pack))
            checked += 1
            with self.subTest(pack=slug):
                self.assertEqual(
                    [],
                    [str(p) for p in problems],
                    msg=f"{slug} prints values that do not follow from their citations",
                )
        self.assertGreater(checked, 0, "no committed packs found to check")


class TheGateCatchesPlantedDefects(unittest.TestCase):
    """Proof the check would refuse, not just that today's data passes."""

    def setUp(self) -> None:
        slug, pack = load_packs()[0]
        self.slug = slug
        self.pack = pack
        self.nodes = nodes_of(pack)
        self.assertEqual([], unbound_values(pack["receipt"], self.nodes))

    def _first_cited(self, receipt: dict) -> dict:
        profile = receipt["profiles"]["supportedAverageHousehold"]
        for body in profile.get("taxingBodies") or []:
            if body.get("sourceFactId"):
                return body
        for line in (profile.get("township") or {}).get("lineItems") or []:
            if line.get("sourceFactId"):
                return line
        raise AssertionError("fixture pack has no cited amounts")

    def test_the_exact_original_defect_is_refused(self) -> None:
        # The $999,999 with an intact citation - the one that started all this.
        receipt = copy.deepcopy(self.pack["receipt"])
        self._first_cited(receipt)["amountCad"] = 999_999.0
        problems = unbound_values(receipt, self.nodes)
        self.assertTrue(
            any(p.printed == 999_999.0 for p in problems),
            "a tampered amount with an intact citation must be reported",
        )

    def test_a_subtle_tamper_is_refused_too(self) -> None:
        # Off by a dollar, not by six orders of magnitude. The tolerance is a
        # cent; a quiet $1 edit is exactly as refused as a loud one.
        receipt = copy.deepcopy(self.pack["receipt"])
        target = self._first_cited(receipt)
        target["amountCad"] = float(target["amountCad"]) + 1.0
        self.assertNotEqual([], unbound_values(receipt, self.nodes))

    def test_a_rate_body_cannot_swap_in_a_different_rate(self) -> None:
        # Declaring a rate only binds when the cited node IS that rate.
        # Changing the declared rate away from the node must not create a
        # second way to justify an arbitrary amount. Brant binds by direct
        # equality and declares no rates, so search every pack for one that
        # does rather than skipping - a permanently-skipped tamper test is a
        # tamper test that does not exist.
        for slug, pack in load_packs():
            receipt = copy.deepcopy(pack["receipt"])
            profile = receipt["profiles"]["supportedAverageHousehold"]
            rated = [
                b
                for b in profile.get("taxingBodies") or []
                if b.get("rate") is not None and b.get("assessmentCad")
            ]
            if not rated:
                continue
            rated[0]["rate"] = float(rated[0]["rate"]) * 2
            rated[0]["amountCad"] = round(
                rated[0]["rate"] * rated[0]["assessmentCad"], 2
            )
            self.assertNotEqual(
                [],
                unbound_values(receipt, nodes_of(pack)),
                f"{slug}: amount consistent with a rate the cited node does not hold must fail",
            )
            return
        self.fail("no committed pack declares a rate-bearing body to test against")

    def test_missing_amount_on_the_cited_node_is_reported(self) -> None:
        receipt = copy.deepcopy(self.pack["receipt"])
        target = self._first_cited(receipt)
        node = copy.deepcopy(self.nodes)
        cited = node[target["sourceFactId"]]
        cited.pop("amountCad", None)
        cited.pop("value", None)
        cited.pop("rate", None)
        problems = unbound_values(receipt, node)
        self.assertTrue(
            any("no amount to bind against" in p.reason for p in problems)
        )


if __name__ == "__main__":
    unittest.main()
