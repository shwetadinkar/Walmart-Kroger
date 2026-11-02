"""Tests for the two reporting tools the client asked for.

Neither tool changes data. The thing worth testing is that they report what is
there rather than what would be convenient: that every required root appears
even when it is empty, that a root is never credited to a product whose label
is unmapped, and that the sold-by-weight audit reports the exclusion failing to
see these products rather than quietly agreeing with it.
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

from coverage_reconciliation import build, required_roots  # noqa: E402
from sold_by_weight_audit import audit  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def record(upc, category="Dairy", sub="Dairy", **over):
    r = {"upc": upc, "category": category, "sub_category": sub,
         "product_title": f"Item {upc}", "weight": "1 lb",
         "regular_price": "3.99", "ppm": "", "volume_deals_description": "",
         "digital_deals_description": "", "url": f"https://x/p/{upc}"}
    r.update(over)
    return r


def card(upc, basis="about each, sold by weight", **over):
    c = {"upc": upc, "term": "banana", "url_path": f"/p/x/{upc}",
         "ppm": "$0.69/lb", "price_basis": basis,
         "approximate_each_price": "$1.45", "approximate_each_regular_price": "",
         "size": "1 lb", "product_title": f"Item {upc}"}
    c.update(over)
    return c


REPORT = {"terms_completed": 10, "requests_spent": 40, "pages_per_term": 20,
          "max_start": 250, "page_failures": [], "unmapped_labels": ["Party"],
          "records_with_unmapped_category": 9, "category_disagreements": 100,
          "terms_that_hit_the_start_cap": ["Grocery||sugar", "Produce||apple"],
          "store": {}, "locationId": "53100502", "generated_utc": "x"}


class TheRootListComesFromTheClientsCsv(unittest.TestCase):
    def test_all_twenty_eight_required_roots_are_read(self):
        self.assertEqual(len(required_roots(ROOT / "config/categories.csv")), 28)

    def test_every_required_root_appears_even_with_no_products(self):
        roots = required_roots(ROOT / "config/categories.csv")
        out = build([record("1")], REPORT, roots, set())
        self.assertEqual(len(out["roots"]), 28)
        self.assertEqual(out["required_roots"], 28)

    def test_an_empty_root_is_named_not_omitted(self):
        out = build([record("1", category="Dairy")], REPORT,
                    ["Dairy", "Seafood"], set())
        self.assertIn("Seafood", out["roots_with_no_products"])
        self.assertEqual(out["roots_with_products"], 1)


class ARootIsNeverGuessed(unittest.TestCase):
    def test_an_unmapped_label_with_no_root_is_reported_as_zero_guessed(self):
        records = [record("1", category="", sub="Party")]
        out = build(records, REPORT, ["Dairy"], set())
        self.assertEqual(
            out["unmapped_labels"]["products_given_a_root_despite_an_unmapped_label"], 0)
        self.assertEqual(out["unmapped_labels"]["distinct_products_left_without_a_root"], 1)

    def test_a_guessed_root_is_counted_and_therefore_visible(self):
        """If a product with an unmapped label ever gets a root, the report has
        to show it. This is the check that would catch the rule being broken."""
        records = [record("1", category="Grocery", sub="Party")]
        out = build(records, REPORT, ["Grocery"], set())
        self.assertEqual(
            out["unmapped_labels"]["products_given_a_root_despite_an_unmapped_label"], 1)

    def test_the_two_unmapped_counts_are_both_reported(self):
        out = build([record("1", category="", sub="Party")], REPORT, ["Dairy"], set())
        self.assertEqual(out["unmapped_labels"]["distinct_products_left_without_a_root"], 1)
        self.assertEqual(out["unmapped_labels"]["encounters_during_the_sweep"], 9)


class PageLimitsAreCarriedThrough(unittest.TestCase):
    def test_terms_that_hit_the_ceiling_are_named_and_counted(self):
        out = build([record("1")], REPORT, ["Dairy"], set())
        self.assertEqual(out["pages"]["terms_that_hit_the_ceiling"], 2)
        self.assertEqual(out["pages"]["terms_that_hit_the_ceiling_by_root"],
                         {"Grocery": 1, "Produce": 1})

    def test_the_report_says_what_it_does_not_establish(self):
        out = build([record("1")], REPORT, ["Dairy"], set())
        self.assertTrue(any("Complete category discovery" in s
                            for s in out["does_not_establish"]))


class SoldByWeightAudit(unittest.TestCase):
    def test_a_sold_by_weight_card_is_found(self):
        out = audit([record("1")], [card("1")])
        self.assertEqual(out["products_the_page_prices_by_weight_or_variably"], 1)

    def test_a_normal_card_is_not_reported(self):
        out = audit([record("1")], [card("1", basis="fixed")])
        self.assertEqual(out["products_the_page_prices_by_weight_or_variably"], 0)

    def test_prices_may_vary_is_also_reported(self):
        out = audit([record("1")], [card("1", basis="prices may vary")])
        self.assertEqual(out["products_the_page_prices_by_weight_or_variably"], 1)

    def test_a_clean_api_weight_is_reported_as_unseen_by_the_exclusion(self):
        out = audit([record("1", weight="1 lb")], [card("1")])
        self.assertEqual(out["of_those_caught_by_the_existing_exclusion"], 0)
        self.assertEqual(out["of_those_the_exclusion_cannot_see"], 1)

    def test_an_api_weight_that_does_say_approximate_is_reported_as_caught(self):
        out = audit([record("1", weight="approx 2 lb")], [card("1")])
        self.assertEqual(out["of_those_caught_by_the_existing_exclusion"], 1)

    def test_both_source_observations_are_included_for_review(self):
        out = audit([record("1", weight="1 lb")], [card("1")])
        f = out["findings"][0]
        self.assertEqual(f["api_observation"]["weight"], "1 lb")
        self.assertEqual(f["page_observation"]["approximate_each_price"], "$1.45")
        self.assertEqual(f["page_observation"]["displayed_rate"], "$0.69/lb")

    def test_a_card_with_no_delivered_record_is_counted_not_dropped(self):
        out = audit([record("1")], [card("9999")])
        self.assertEqual(out["page_cards_with_no_delivered_record"], 1)

    def test_the_audit_does_not_modify_the_records(self):
        records = [record("1")]
        before = json.dumps(records, sort_keys=True)
        audit(records, [card("1")])
        self.assertEqual(json.dumps(records, sort_keys=True), before)


if __name__ == "__main__":
    unittest.main()
