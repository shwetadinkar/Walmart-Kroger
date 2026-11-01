"""Tests for the page-harvest parser.

The parser exists to read what the retailer displayed. These tests are written
against the rule it has to obey: it may recognise a shape, and it may not
produce a value the page did not show.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))

from parse_page_harvest import parse  # noqa: E402


def card(lines, ppm=""):
    return parse("milk", "0001115015950", "/p/x/0001115015950", ppm, lines)


class FixedPriceCards(unittest.TestCase):
    def test_single_price_is_regular_and_no_sale(self):
        rec, reason = card(["$3.29", "$3.29", "Roundy's Milk", "1 Gallon"], "$0.03/fl oz")
        self.assertEqual(reason, "")
        self.assertEqual(rec["regular_price"], "$3.29")
        self.assertEqual(rec["sale_price"], "")
        self.assertEqual(rec["product_title"], "Roundy's Milk")
        self.assertEqual(rec["size"], "1 Gallon")

    def test_two_prices_mean_the_first_is_the_sale(self):
        rec, reason = card(
            ["$2.00", "$2.29", "Sale: $2.00 discounted from $2.29", "Egg Noodles", "16 oz"],
            "$0.13/oz")
        self.assertEqual(reason, "")
        self.assertEqual(rec["sale_price"], "$2.00")
        self.assertEqual(rec["regular_price"], "$2.29")
        self.assertEqual(rec["product_title"], "Egg Noodles")

    def test_leading_label_is_kept_not_mistaken_for_a_title(self):
        rec, reason = card(["Everyday Low Price", "$4.49", "$4.49", "Simple Truth", "1/2 gal"])
        self.assertEqual(reason, "")
        self.assertEqual(rec["price_label"], "Everyday Low Price")
        self.assertEqual(rec["product_title"], "Simple Truth")

    def test_price_cut_is_a_label_not_a_title(self):
        rec, reason = card(
            ["Price Cut", "$5.00", "$5.49", "Sale: $5.00 discounted from $5.49",
             "Kroger Pizza", "12 oz"])
        self.assertEqual(reason, "")
        self.assertEqual(rec["price_label"], "Price Cut")
        self.assertEqual(rec["product_title"], "Kroger Pizza")
        self.assertEqual(rec["sale_price"], "$5.00")


class SoldByWeightCards(unittest.TestCase):
    def test_about_each_is_not_written_into_regular_price(self):
        rec, reason = card(
            ["about", "$1.45", "each", "about $1.45 each", "Fresh Bananas"], "$0.69/lb")
        self.assertEqual(reason, "")
        self.assertEqual(rec["approximate_each_price"], "$1.45")
        self.assertEqual(rec["price_basis"], "about each, sold by weight")
        self.assertEqual(rec["regular_price"], "")
        self.assertEqual(rec["sale_price"], "")

    def test_a_weight_item_keeps_the_displayed_per_pound_rate(self):
        rec, _ = card(
            ["about", "$1.45", "each", "about $1.45 each", "Fresh Bananas"], "$0.69/lb")
        self.assertEqual(rec["ppm"], "$0.69/lb")

    def test_discounted_weight_item_carries_both_approximate_prices(self):
        rec, reason = card(
            ["about", "$3.38", "$7.18", "each",
             "Sale: about $3.38 each discounted from $7.18", "Green Grapes"], "$1.69/lb")
        self.assertEqual(reason, "")
        self.assertEqual(rec["approximate_each_price"], "$3.38")
        self.assertEqual(rec["approximate_each_regular_price"], "$7.18")
        self.assertEqual(rec["price_basis"], "about each on sale, sold by weight")
        self.assertEqual(rec["regular_price"], "")

    def test_prices_may_vary_leaves_both_prices_empty(self):
        rec, reason = card(["Prices May Vary", "Jumbo Avocado", "1 each"])
        self.assertEqual(reason, "")
        self.assertEqual(rec["price_basis"], "prices may vary")
        self.assertEqual(rec["regular_price"], "")
        self.assertEqual(rec["approximate_each_price"], "")
        self.assertEqual(rec["product_title"], "Jumbo Avocado")


class ValuesAreReadNeverMade(unittest.TestCase):
    def test_a_card_with_no_displayed_rate_gets_no_rate(self):
        """Price and size are both present and a rate is computable. It is still
        not computed, because the retailer did not display one."""
        rec, reason = card(["$3.20", "$3.20", "Something", "16 oz"], "")
        self.assertEqual(reason, "")
        self.assertEqual(rec["ppm"], "")

    def test_the_displayed_rate_is_passed_through_character_for_character(self):
        for shown in ("$0.057/fl oz", "86.8 ¢/lb", "$1.69/lb", "$0.13/oz"):
            rec, _ = card(["$3.29", "$3.29", "T", "1 ct"], shown)
            self.assertEqual(rec["ppm"], shown)

    def test_deal_wording_is_kept_verbatim_and_not_composed(self):
        rec, _ = card(
            ["$2.39", "$2.39", "Milk", "1/2 Gallon", "Buy 1, Get 1 Free"])
        self.assertEqual(rec["deal_lines"], ["Buy 1, Get 1 Free"])

    def test_several_deal_lines_are_all_kept_in_order(self):
        rec, _ = card(
            ["$1.25", "$1.25", "Apple", "1 ct", "Coupon: $1.79 lb Honeycrisp",
             "3/$12 When you buy 3 or more"])
        self.assertEqual(
            rec["deal_lines"],
            ["Coupon: $1.79 lb Honeycrisp", "3/$12 When you buy 3 or more"])

    def test_an_unrecognised_card_reports_a_reason_and_invents_nothing(self):
        rec, reason = card(["Something Unexpected"])
        self.assertNotEqual(reason, "")
        self.assertEqual(rec["regular_price"], "")
        self.assertEqual(rec["sale_price"], "")
        self.assertEqual(rec["product_title"], "")

    def test_the_upc_and_term_are_carried_through_untouched(self):
        rec, _ = card(["$1.00", "$1.00", "T", "1 ct"])
        self.assertEqual(rec["upc"], "0001115015950")
        self.assertEqual(rec["term"], "milk")


if __name__ == "__main__":
    unittest.main()
