"""One verdict per sold-by-weight product, on the client's terms.

His instruction of 3 November: "Do not remove all 34 products merely because
they are sold by weight or have an approximate total price. Supply their exact
title, size/weight wording and page evidence; exclude those with
approximate-weight wording and keep eligible genuine fixed-size/bulk/multipack
identities. Do not infer that API '1 lb' proves the page has no excluded
wording."

Three things in that are easy to get wrong and each has a test here.

The exclusion pattern matches `sold by weight`, and 31 of the 34 pages carry
that phrase in their **pricing basis**. Feeding the pricing basis to the rule
would exclude them on precisely the ground he ruled out, so the pricing basis
must decide nothing.

`Buy 1, Get 1 Free` in the size slot carries no approximate-weight wording. A
promotional badge would not. Reading that as evidence of a fixed size kept
four products on no evidence at all in the first run of this tool.

An absent page size is not a clean bill of health. The API size is not
evidence about the page, so the verdict is UNDETERMINED and the product stays.
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import weight_exclusion_verdicts as wev  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
AUDIT = ROOT / "reports/2026-11-02-sold-by-weight/data/sold_by_weight_audit.json"


def record(title="Chicken Breasts", api_weight="1 lb", page_size="",
           price_basis="about each, sold by weight", upc="0001"):
    return {"upc": upc, "category": "Meat",
            "api_observation": {"product_title": title, "weight": api_weight,
                                "regular_price": "4.99", "url": ""},
            "page_observation": {"size_as_rendered": page_size,
                                 "price_basis": price_basis,
                                 "approximate_each_price": "$1.45",
                                 "displayed_rate": "$0.69/lb", "path": "/p/x/0001"}}


class ThePricingBasisDecidesNothing(unittest.TestCase):
    def test_sold_by_weight_pricing_alone_does_not_exclude(self):
        """The exact failure mode he named."""
        v = wev.verdict_for(record(price_basis="about each, sold by weight"))
        self.assertNotEqual(v["verdict"], wev.EXCLUDE)

    def test_the_pattern_really_would_have_matched_that_phrase(self):
        """Proves the test above is load-bearing and not vacuous."""
        from marianos_collector.schema import _APPROX_WEIGHT
        self.assertTrue(_APPROX_WEIGHT.search("about each, sold by weight"))

    def test_an_approximate_each_price_alone_does_not_exclude(self):
        v = wev.verdict_for(record(price_basis="prices may vary"))
        self.assertNotEqual(v["verdict"], wev.EXCLUDE)

    def test_the_pricing_evidence_is_still_recorded_on_the_row(self):
        v = wev.verdict_for(record())
        shown = v["page_pricing_evidence_not_used_for_the_verdict"]
        self.assertEqual(shown["price_basis"], "about each, sold by weight")
        self.assertEqual(shown["approximate_each_price"], "$1.45")


class ApproximateWordingInTheRightFieldDoesExclude(unittest.TestCase):
    def test_an_approximate_title_excludes(self):
        v = wev.verdict_for(record(title="Beef Brisket, approx 3 lb"))
        self.assertEqual(v["verdict"], wev.EXCLUDE)
        self.assertIn("api_title", v["matched_exclusion_wording"])

    def test_an_approximate_weight_field_excludes(self):
        v = wev.verdict_for(record(api_weight="about 2 lb"))
        self.assertEqual(v["verdict"], wev.EXCLUDE)
        self.assertIn("api_weight_field", v["matched_exclusion_wording"])

    def test_an_approximate_page_size_excludes(self):
        v = wev.verdict_for(record(page_size="average weight 1.5 lb"))
        self.assertEqual(v["verdict"], wev.EXCLUDE)
        self.assertIn("page_size_wording", v["matched_exclusion_wording"])

    def test_the_verdict_quotes_the_wording_that_excluded_it(self):
        v = wev.verdict_for(record(title="Pork Loin, approximately 4 lb"))
        self.assertTrue(v["matched_exclusion_wording"]["api_title"])
        self.assertIn(v["matched_exclusion_wording"]["api_title"], v["reason"])


class PromotionalTextIsNotASize(unittest.TestCase):
    def test_an_offer_badge_in_the_size_slot_does_not_support_keeping(self):
        for badge in ("Buy 1, Get 1 Free", "Coupon: $1.79 lb Honeycrisp Apples",
                      "Save $2.00", "20% off"):
            with self.subTest(badge=badge):
                v = wev.verdict_for(record(page_size=badge))
                self.assertEqual(v["verdict"], wev.UNDETERMINED)
                self.assertIn("promotional", v["reason"])

    def test_a_genuine_quantity_and_unit_supports_keeping(self):
        for size in ("12 ounces", "1 each", "500 g", "6 ct", "2 L", "16 fl oz"):
            with self.subTest(size=size):
                self.assertEqual(wev.verdict_for(record(page_size=size))["verdict"],
                                 wev.KEEP)

    def test_text_that_is_neither_is_undetermined(self):
        self.assertEqual(wev.verdict_for(record(page_size="Fresh"))["verdict"],
                         wev.UNDETERMINED)


class AnAbsentPageSizeIsNotACleanBillOfHealth(unittest.TestCase):
    def test_no_page_size_is_undetermined_not_keep(self):
        v = wev.verdict_for(record(page_size=""))
        self.assertEqual(v["verdict"], wev.UNDETERMINED)

    def test_the_api_size_is_named_as_not_being_evidence(self):
        v = wev.verdict_for(record(api_weight="1 lb", page_size=""))
        self.assertIn("not evidence about the page", v["reason"])
        self.assertIn("1 lb", v["reason"])

    def test_an_undetermined_product_is_retained(self):
        self.assertIn("Retained", wev.verdict_for(record(page_size=""))["reason"])


class TheShippedVerdictsAreWhatTheToolProduces(unittest.TestCase):
    """Recomputed from the audit, not written from notes."""

    def setUp(self):
        if not AUDIT.is_file():
            self.skipTest(f"{AUDIT} absent")
        self.audit = json.loads(AUDIT.read_text())

    def test_the_34_split_into_0_exclude_3_keep_31_undetermined(self):
        verdicts = [wev.verdict_for(r) for r in self.audit["findings"]]
        counts = {v: sum(1 for x in verdicts if x["verdict"] == v)
                  for v in (wev.EXCLUDE, wev.KEEP, wev.UNDETERMINED)}
        self.assertEqual(counts, {wev.EXCLUDE: 0, wev.KEEP: 3, wev.UNDETERMINED: 31})

    def test_nothing_is_excluded_on_the_evidence_held(self):
        """Which answers his question: do not remove all 34. Remove none."""
        verdicts = [wev.verdict_for(r) for r in self.audit["findings"]]
        self.assertEqual([x for x in verdicts if x["verdict"] == wev.EXCLUDE], [])

    def test_every_product_carries_its_exact_wording(self):
        for r in self.audit["findings"]:
            v = wev.verdict_for(r)
            with self.subTest(upc=v["upc"]):
                self.assertIn("api_product_title", v["exact_wording_observed"])
                self.assertTrue(v["exact_wording_observed"]["api_product_title"])
                self.assertIn("api_weight_field", v["exact_wording_observed"])

    def test_the_written_report_matches_the_recomputed_counts(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "out"
            wev.main(["--audit", str(AUDIT), "--out", str(out)])
            written = json.loads((out / "verdicts.json").read_text())
            self.assertEqual(written["counts"],
                             {wev.EXCLUDE: 0, wev.KEEP: 3, wev.UNDETERMINED: 31})
            summary = (out / "VERDICTS.md").read_text()
            self.assertIn("| 0 |", summary)
            self.assertIn("Nothing has been removed", summary)
            self.assertEqual(len(written["undetermined_page_paths"]), 31)


if __name__ == "__main__":
    unittest.main()
