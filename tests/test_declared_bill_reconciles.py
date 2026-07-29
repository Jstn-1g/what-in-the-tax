"""The declared bill has to agree with the lines the receipt already prints.

Declaring taxingBodies[] moved the bill from three fixed slots to a list, but it
did not connect the new list to anything. A builder can emit a local body of any
amount it likes and every existing check still passes: the bodies sum to the
printed total because the builder made them, and the line items sum to the
bucket because they always did. Nothing compares the two.

That gap matters most for the people this project is trying to hand off to. The
realistic contributor is adding their own town, copying an existing builder, and
the easiest mistake to make is to declare the local body as the municipal bucket
total - which is right for five of the six packs and wrong for the sixth, because
County of Brant folds a $78.04 hospital levy into that bucket and declares it
separately as a special-area body. A contributor who copies the wrong pack
publishes a municipal portion overstated by exactly one levy.

The relationship that holds, and that this pins:

    municipal bucket line items
      - lines classified special_levy
      = the declared 'local' body amount

Verified against all six committed packs, exactly, to the cent.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACK_DIR = ROOT / "web" / "public" / "packs"

# FIR and by-law amounts are whole cents. A cent of rounding across a dozen
# lines is expected; anything larger is a real disagreement.
TOLERANCE_CAD = 0.011


def load_packs() -> list[tuple[str, dict]]:
    return [
        (path.stem, json.loads(path.read_text(encoding="utf-8")))
        for path in sorted(PACK_DIR.glob("*.json"))
    ]


def reconcile_local_body(profile: dict) -> tuple[float, float] | None:
    """Return (lines minus special levies, declared local amount), or None.

    None means this pack has not declared a bill yet, which is a state the
    migration passes through rather than an error.
    """

    bodies = profile.get("taxingBodies") or []
    local = next((b for b in bodies if b.get("role") == "local"), None)
    if local is None:
        return None
    lines = (profile.get("township") or {}).get("lineItems") or []
    if not lines:
        return None
    total = sum(line["amountCad"] for line in lines)
    special = sum(
        line["amountCad"]
        for line in lines
        if line.get("classification") == "special_levy"
    )
    return round(total - special, 2), float(local["amountCad"])


class DeclaredBillReconcilesToLines(unittest.TestCase):
    def test_every_declared_local_body_matches_its_own_lines(self) -> None:
        checked = 0
        for slug, pack in load_packs():
            profile = pack["receipt"]["profiles"]["supportedAverageHousehold"]
            result = reconcile_local_body(profile)
            if result is None:
                continue
            net, declared = result
            checked += 1
            with self.subTest(pack=slug):
                self.assertAlmostEqual(
                    net,
                    declared,
                    delta=TOLERANCE_CAD,
                    msg=(
                        f"{slug}: municipal lines minus special levies are "
                        f"{net:,.2f} but the declared local body is "
                        f"{declared:,.2f}. Either the body is wrong or a line "
                        f"belongs to a different body."
                    ),
                )
        # A test that silently checks nothing is worse than no test. If every
        # pack stopped declaring a bill, this would notice.
        self.assertGreater(checked, 0, "no committed pack declares a bill")

    def test_a_special_levy_is_declared_as_its_own_body(self) -> None:
        # The case that makes the check necessary rather than tautological.
        # Brant's $78.04 hospital levy sits inside the municipal bucket's lines
        # and is declared as a separate special-area body; if a builder ever
        # folds it into the local body instead, the test above fails.
        for slug, pack in load_packs():
            profile = pack["receipt"]["profiles"]["supportedAverageHousehold"]
            lines = (profile.get("township") or {}).get("lineItems") or []
            levies = [
                line
                for line in lines
                if line.get("classification") == "special_levy"
            ]
            if not levies:
                continue
            bodies = profile.get("taxingBodies") or []
            special_total = round(
                sum(b["amountCad"] for b in bodies if b.get("role") == "special-area"),
                2,
            )
            with self.subTest(pack=slug):
                self.assertAlmostEqual(
                    round(sum(line["amountCad"] for line in levies), 2),
                    special_total,
                    delta=TOLERANCE_CAD,
                    msg=(
                        f"{slug}: special-levy lines and declared special-area "
                        f"bodies describe different amounts."
                    ),
                )

    def test_declared_bodies_sum_to_the_printed_total(self) -> None:
        # Re-checked here as well as in the browser. The web loader refuses an
        # incoherent bill at render; this refuses it in CI, before anyone can
        # deploy the artifact that contains it.
        for slug, pack in load_packs():
            profile = pack["receipt"]["profiles"]["supportedAverageHousehold"]
            bodies = profile.get("taxingBodies") or []
            printed = profile.get("combinedTotalCad")
            if not bodies or not isinstance(printed, (int, float)):
                continue
            with self.subTest(pack=slug):
                self.assertAlmostEqual(
                    round(sum(b["amountCad"] for b in bodies), 2),
                    float(printed),
                    delta=0.05,
                    msg=f"{slug}: declared bodies do not sum to the printed total.",
                )


class TheCheckItselfCatchesADefect(unittest.TestCase):
    """Proof the reconciliation would refuse a wrong bill, not just pass one."""

    BASE = {
        "taxingBodies": [{"role": "local", "amountCad": 100.0}],
        "township": {
            "lineItems": [
                {"amountCad": 90.0, "classification": "county_levy_allocated"},
                {"amountCad": 20.0, "classification": "county_levy_allocated"},
                {"amountCad": -10.0, "classification": "county_levy_allocated"},
                {"amountCad": 5.0, "classification": "special_levy"},
            ]
        },
    }

    def test_a_correct_bill_reconciles(self) -> None:
        # 90 + 20 - 10 + 5 = 105, minus the 5 special levy = 100.
        net, declared = reconcile_local_body(json.loads(json.dumps(self.BASE)))
        self.assertAlmostEqual(net, declared, delta=TOLERANCE_CAD)

    def test_folding_the_special_levy_into_the_local_body_is_caught(self) -> None:
        # The exact contributor mistake: declaring the bucket total as the
        # local body, levy and all.
        payload = json.loads(json.dumps(self.BASE))
        payload["taxingBodies"][0]["amountCad"] = 105.0
        net, declared = reconcile_local_body(payload)
        self.assertNotAlmostEqual(net, declared, delta=TOLERANCE_CAD)

    def test_a_negative_allocation_line_still_counts(self) -> None:
        # Credits reduce the levy. Dropping them because they are negative is
        # how a municipal portion silently overstates itself.
        payload = json.loads(json.dumps(self.BASE))
        payload["township"]["lineItems"] = [
            line
            for line in payload["township"]["lineItems"]
            if line["amountCad"] > 0
        ]
        net, declared = reconcile_local_body(payload)
        self.assertNotAlmostEqual(net, declared, delta=TOLERANCE_CAD)

    def test_a_pack_without_a_declared_bill_is_skipped_not_failed(self) -> None:
        payload = json.loads(json.dumps(self.BASE))
        payload["taxingBodies"] = []
        self.assertIsNone(reconcile_local_body(payload))


if __name__ == "__main__":
    unittest.main()
