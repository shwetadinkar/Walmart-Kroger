"""Tests for the page-harvest parser.

The parser exists to read what the retailer displayed. These tests are written
against the rule it has to obey: it may recognise a shape, and it may not
produce a value the page did not show.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))

from parse_page_harvest import classify_card_line, parse  # noqa: E402


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


class ABadgeIsNotADeal(unittest.TestCase):
    """The 1 November read published "Low Stock" as a volume deal on 47 rows.

    Deal lines used to be whatever remained after the title and size were
    taken, so a stock status, a payment eligibility and a "View 2 Offers" link
    all became deal text. Each assertion here is on a line the retailer
    actually rendered at Vernon Hills.
    """

    def test_a_stock_status_is_not_a_deal_line(self):
        rec, reason = card(["$4.99", "$4.99", "Yogurt", "32 oz", "Low Stock"])
        self.assertEqual(reason, "")
        self.assertEqual(rec["deal_lines"], [])
        self.assertEqual(rec["stock_label"], "Low Stock")

    def test_a_payment_eligibility_is_not_a_deal_line(self):
        rec, _ = card(["$4.99", "$4.99", "Yogurt", "32 oz", "SNAP EBT"])
        self.assertEqual(rec["deal_lines"], [])
        self.assertIn("SNAP EBT", rec["non_deal_labels"])

    def test_an_offer_link_is_not_a_deal_line(self):
        rec, _ = card(["$4.99", "$4.99", "Yogurt", "32 oz", "View 2 Offers"])
        self.assertEqual(rec["deal_lines"], [])
        self.assertIn("View 2 Offers", rec["non_deal_labels"])

    def test_a_variant_link_is_not_a_deal_line(self):
        rec, _ = card(["$4.99", "$4.99", "Yogurt", "32 oz", "11 more options"])
        self.assertEqual(rec["deal_lines"], [])
        self.assertIn("11 more options", rec["non_deal_labels"])

    def test_a_real_offer_beside_a_badge_keeps_the_offer_and_drops_the_badge(self):
        rec, _ = card(["$4.99", "$4.99", "Yogurt", "32 oz",
                       "Low Stock", "Save $15 when you spend $60"])
        self.assertEqual(rec["deal_lines"], ["Save $15 when you spend $60"])
        self.assertEqual(rec["stock_label"], "Low Stock")

    def test_every_card_line_seen_at_the_store_classifies_as_the_right_kind(self):
        for line in ("Low Stock", "Out of Stock"):
            self.assertEqual(classify_card_line(line), "stock", line)
        for line in ("SNAP EBT", "FSA/HSA"):
            self.assertEqual(classify_card_line(line), "eligibility", line)
        for line in ("View 1 Offer", "View 2 Offers", "View 4 Offers"):
            self.assertEqual(classify_card_line(line), "offer_link", line)
        for line in ("11 more options", "5 more sizes", "1 more size"):
            self.assertEqual(classify_card_line(line), "variant_link", line)
        for line in ("Buy 1, Get 1 Free", "Buy 2 Get 1 FREE.", "Buy 2 Save $4",
                     "Save $15 when you spend $60", "Save $1.00 on Energizer",
                     "Save $2 each when you buy 3 or more", "2 For $4.00",
                     "3/$12 When you buy 3 or more", "Buy 3 For $10.00",
                     "99¢ each when you buy 5 or more",
                     "Coupon: Save $1.00 on Energizer",
                     "Cash Back: $5.00 Cash Back on Pabst Blue Ribbon"):
            self.assertEqual(classify_card_line(line), "deal", line)


class TheSizeSlotDoesNotSwallowADeal(unittest.TestCase):
    """Two digital coupons were lost into the size field on 1 November.

    A sold-by-weight card carries no size, so the line after the title was
    taken as one whatever it said. At Vernon Hills that line was
    "Coupon: $1.79 lb Honeycrisp Apples" on 1 November and "SNAP EBT" on 4
    November, and the coupon never reached digital_deals_description.
    """

    def test_a_coupon_after_a_weight_sold_title_is_a_deal_not_a_size(self):
        rec, reason = card(["about", "$2.49", "each", "about $2.49 each",
                            "Large Honeycrisp Apple",
                            "Coupon: $1.79 lb Honeycrisp Apples"])
        self.assertEqual(reason, "")
        self.assertEqual(rec["size"], "")
        self.assertEqual(rec["deal_lines"],
                         ["Coupon: $1.79 lb Honeycrisp Apples"])

    def test_a_badge_after_a_weight_sold_title_is_not_a_size(self):
        rec, _ = card(["about", "$2.49", "each", "about $2.49 each",
                       "Large Honeycrisp Apple", "SNAP EBT"])
        self.assertEqual(rec["size"], "")
        self.assertIn("SNAP EBT", rec["non_deal_labels"])

    def test_a_volume_offer_after_a_weight_sold_title_is_not_a_size(self):
        rec, _ = card(["about", "$2.49", "each", "about $2.49 each",
                       "Pears", "Buy 1, Get 1 Free"])
        self.assertEqual(rec["size"], "")
        self.assertEqual(rec["deal_lines"], ["Buy 1, Get 1 Free"])

    def test_a_real_size_is_still_read_as_the_size(self):
        rec, _ = card(["$7.79", "$7.79", "Salmon Burgers", "4 ct / 11.2 oz",
                       "SNAP EBT"])
        self.assertEqual(rec["size"], "4 ct / 11.2 oz")
        self.assertEqual(rec["deal_lines"], [])

    def test_an_unrecognised_line_falls_to_size_not_to_the_deal_column(self):
        """The safe direction. A size published as an offer would be a value
        the retailer never displayed; a deal line kept as a size is published
        nowhere, because the 22 fields take size from the API."""
        rec, _ = card(["$7.79", "$7.79", "Cheese", "wedge"])
        self.assertEqual(rec["size"], "wedge")
        self.assertEqual(rec["deal_lines"], [])


if __name__ == "__main__":
    unittest.main()
