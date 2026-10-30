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


if __name__ == "__main__":
    unittest.main()
