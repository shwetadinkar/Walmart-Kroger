"""Approximate-weight exclusion must apply to titles, not only the weight field.

The client found this on the Walmart side on 31 October 2026. The Mariano's
normalizer carried the identical defect: only `weight` was ever searched, and
the pattern had no "average weight" wording in it at all, so a product titled
"Chicken Average Weight 1 lb" with size "1 lb" passed every check.
"""
import unittest

import sys as _sys, pathlib as _pathlib
_sys.path.insert(0, str(_pathlib.Path(__file__).resolve().parent.parent))

from marianos_collector.config import Store
from marianos_collector.schema import RecordRejected, make_record

STORE = Store("70100485", "60661", "Mariano's West Loop", "Chicago, IL")


def raw(title, weight):
    return {"store_id": STORE.store_id, "zipcode": STORE.zipcode,
            "store_context_verified": True, "seller_type": "marianos",
            "fulfillment": "pickup", "product_id": "1",
            "product_title": title, "weight": weight, "regular_price": "4.99",
            "url": "https://www.marianos.com/p/x/1", "upc": "1", "brand": "Example"}


class ApproximateWeightTitleTests(unittest.TestCase):
    def test_approximate_wording_in_the_title_is_rejected(self):
        for title in ("Chicken approximately 1 lb",
                      "Chicken Average Weight 1 lb",
                      "Beef avg. weight 2 lb",
                      "Pork variable weight",
                      "Salmon sold by weight",
                      "Fish estimated weight 1 lb"):
            with self.assertRaises(RecordRejected, msg=title) as caught:
                make_record(raw(title, "1 lb"), STORE, "Meat", "Poultry", "2026-10-31")
            self.assertIn("APPROXIMATE_WEIGHT", str(caught.exception))

    def test_average_weight_in_the_weight_field_is_now_caught_too(self):
        with self.assertRaises(RecordRejected):
            make_record(raw("Chicken Breast", "Average Weight 1 lb"),
                        STORE, "Meat", "Poultry", "2026-10-31")

    def test_fixed_weight_family_packs_and_multipacks_still_pass(self):
        for title, weight in (("Family Pack Ground Beef, 5 lb", "5 lb"),
                              ("Private Selection Chicken Breast, 3 lb", "3 lb"),
                              ("Sparkling Water 12 Count", "12 fl oz"),
                              ("Cheese Block", "1 lb"),
                              ("Value Pack Pork Chops", "4 lb")):
            record = make_record(raw(title, weight), STORE, "Meat", "Poultry",
                                 "2026-10-31")
            self.assertEqual(record["product_title"], title)

    def test_an_ordinary_product_is_untouched(self):
        record = make_record(raw("Simple Truth 2% Milk", "1 gal"), STORE,
                             "Dairy", "Milk", "2026-10-31")
        self.assertEqual(record["weight"], "1 gal")


class ApproximateServingsAreNotApproximateWeight(unittest.TestCase):
    """B4. The exclusion is about weight, not about approximation in general."""

    FIXED = ("Rice 16 oz, approximately 8 servings",
             "Rice 16 oz approx. 8 servings",
             "Pasta Sauce 24 oz, approx 6 servings per container",
             "Cereal, about 12 servings",
             "Crackers approximately 40 count",
             "Candle approx. 30 hours burn time",
             "Foil 12 in x approximately 75 sq ft",
             "Grapes about 20 grapes per pack")
    APPROXIMATE = ("Chicken approximately 1 lb", "Beef approx. 2-3 lb",
                   "Pork approx 1.5 pounds", "Ham approx: 8 oz",
                   "Roast approximately 1/2 kg", "Steak about 12 oz",
                   "Turkey Approximate Weight", "Ribs approx. net wt 3 lb",
                   "Fish 1 lb approx.", "Lamb 2 lb (approx)",
                   "Veal 16 oz, approximately", "Brisket weight approximately 4",
                   "Duck 5 lb approximately weight varies")

    def test_a_fixed_size_with_an_approximate_serving_count_passes(self):
        for title in self.FIXED:
            record = make_record(raw(title, "16 oz"), STORE, "Meat", "Poultry", "2026-10-31")
            self.assertEqual(record["product_title"], title)

    def test_approximate_weight_in_a_title_is_still_excluded(self):
        for title in self.APPROXIMATE:
            with self.assertRaisesRegex(RecordRejected, "APPROXIMATE_WEIGHT_IN_TITLE", msg=title):
                make_record(raw(title, "1 lb"), STORE, "Meat", "Poultry", "2026-10-31")

    def test_a_serving_count_in_the_weight_field_passes(self):
        for weight in ("16 oz, approximately 8 servings", "about 4 servings", "approx. 30 count"):
            record = make_record(raw("Rice", weight), STORE, "Meat", "Poultry", "2026-10-31")
            self.assertEqual(record["weight"], weight)

    def test_approximate_wording_in_the_weight_field_is_still_excluded(self):
        for weight in ("approx. 2 lb", "approximately 2", "about 3", "about 3 lb",
                       "2 lb approx", "approximate", "approx"):
            with self.assertRaisesRegex(RecordRejected, "^APPROXIMATE_WEIGHT$", msg=weight):
                make_record(raw("Rice", weight), STORE, "Meat", "Poultry", "2026-10-31")

    def test_family_packs_and_multipacks_are_untouched(self):
        for title, weight in (("Family Pack Ground Beef, 5 lb", "5 lb"),
                              ("Yogurt 12 ct, 5.3 oz each", "63.6 oz")):
            self.assertEqual(make_record(raw(title, weight), STORE, "Meat", "Poultry", "2026-10-31")["weight"], weight)


if __name__ == "__main__":
    unittest.main()
