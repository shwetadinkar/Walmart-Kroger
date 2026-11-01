"""Tests for merging the page read into the API record set.

The merge has to obey three things that have gone wrong before in this
repository: a page value must not reach a product it was not observed for, a
page value must never reach another store's rows, and a product must not be
dropped because it has no page value.
"""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from merge_page_enrichment import main, split_deals  # noqa: E402

STORE = "Marianos - Marianos Vernon Hills"


def api_row(upc, title, **over):
    row = {
        "zipcode": "60061", "store_name": STORE,
        "store_location": "1720 N Milwaukee Ave, Vernon Hills, IL 60061",
        "store_logo": "", "store_brand": "Marianos", "category": "Dairy",
        "sub_category": "", "product_title": title, "weight": "1 Gallon",
        "regular_price": "3.29", "sale_price": "", "volume_deals_description": "",
        "volume_deals_price": "", "digital_deals_description": "",
        "digital_deals_price": "", "image_url": "", "url": "https://x/p/1",
        "upc": upc, "gupc": "", "ppm": "", "unit_price": "",
        "crawl_date": "2026-10-31",
    }
    row.update(over)
    return row


def page_row(upc, ppm="", deals=()):
    return {"term": "milk", "upc": upc, "url_path": "/p/x/" + upc, "ppm": ppm,
            "price_label": "", "regular_price": "$3.29", "sale_price": "",
            "product_title": "T", "size": "1 Gallon", "deal_lines": list(deals),
            "approximate_each_price": "", "approximate_each_regular_price": "",
            "price_basis": "fixed", "parse_reason": ""}


def run(api, page, extra=()):
    d = tempfile.mkdtemp()
    ap, pp = os.path.join(d, "a.json"), os.path.join(d, "p.json")
    json.dump(api, open(ap, "w"))
    json.dump(page, open(pp, "w"))
    out = os.path.join(d, "out")
    main(["--api", ap, "--page", pp, "--out", out, *extra])
    return (json.load(open(os.path.join(out, "data_22_fields_enriched.json"))),
            json.load(open(os.path.join(out, "merge_report.json"))),
            json.load(open(os.path.join(out, "provenance.json"))))


class DealSplitting(unittest.TestCase):
    def test_a_coupon_line_is_a_digital_deal(self):
        vol, dig = split_deals(["Coupon: $1.79 lb Bartlett Pears"])
        self.assertEqual(vol, "")
        self.assertEqual(dig, "Coupon: $1.79 lb Bartlett Pears")

    def test_anything_else_is_a_volume_deal(self):
        vol, dig = split_deals(["Buy 1, Get 1 Free"])
        self.assertEqual(vol, "Buy 1, Get 1 Free")
        self.assertEqual(dig, "")

    def test_both_kinds_separate_and_stay_verbatim(self):
        vol, dig = split_deals(
            ["3/$12 When you buy 3 or more", "Coupon: $1.00 off"])
        self.assertEqual(vol, "3/$12 When you buy 3 or more")
        self.assertEqual(dig, "Coupon: $1.00 off")


class ValuesLandOnTheRightProduct(unittest.TestCase):
    def test_a_matched_upc_receives_the_page_rate(self):
        recs, _, _ = run([api_row("0001", "A")], [page_row("0001", "$0.03/fl oz")])
        self.assertEqual(recs[0]["ppm"], "$0.03/fl oz")

    def test_an_unmatched_product_keeps_an_empty_rate(self):
        recs, _, _ = run([api_row("0001", "A"), api_row("0002", "B")],
                         [page_row("0001", "$0.03/fl oz")])
        self.assertEqual(recs[1]["ppm"], "")

    def test_a_page_upc_absent_from_the_api_reaches_no_product(self):
        recs, report, _ = run([api_row("0001", "A")],
                              [page_row("0009", "$9.99/oz")])
        self.assertEqual(report["page_upcs_not_in_api"], 1)
        self.assertEqual([r["ppm"] for r in recs], [""])
        self.assertNotIn("$9.99/oz", json.dumps(recs))

    def test_the_rate_is_attributed_to_the_page_not_the_api(self):
        _, _, prov = run([api_row("0001", "A")], [page_row("0001", "$0.03/fl oz")])
        self.assertEqual(prov["values_by_field_and_source"]["ppm"], {"crawl": 1})


class RowsAreNeverDropped(unittest.TestCase):
    def test_every_api_record_survives_the_merge(self):
        api = [api_row(f"000{i}", f"P{i}") for i in range(5)]
        recs, report, _ = run(api, [page_row("0002", "$1.00/oz")])
        self.assertEqual(len(recs), 5)
        self.assertEqual(report["api_records"], 5)

    def test_a_product_with_no_price_is_kept_not_removed(self):
        recs, _, _ = run([api_row("0001", "A", regular_price="")], [])
        self.assertEqual(len(recs), 1)
        self.assertEqual(recs[0]["regular_price"], "")


class StoreSafety(unittest.TestCase):
    def test_a_foreign_store_in_the_api_set_refuses_the_whole_merge(self):
        api = [api_row("0001", "A"),
               api_row("0002", "B", store_name="Marianos - Marianos West Loop")]
        with self.assertRaises(SystemExit) as caught:
            run(api, [page_row("0001", "$0.03/fl oz")])
        self.assertIn("West Loop", str(caught.exception))


class TheCrawlCannotOverreach(unittest.TestCase):
    def test_the_api_price_is_not_replaced_by_the_page(self):
        recs, _, _ = run([api_row("0001", "A", regular_price="3.29")],
                         [page_row("0001", "$0.03/fl oz")])
        self.assertEqual(recs[0]["regular_price"], "3.29")

    def test_deal_wording_is_written_as_rendered(self):
        recs, _, _ = run([api_row("0001", "A")],
                         [page_row("0001", deals=["Buy 1, Get 1 Free"])])
        self.assertEqual(recs[0]["volume_deals_description"], "Buy 1, Get 1 Free")

    def test_no_promotional_price_is_invented_from_deal_wording(self):
        recs, _, _ = run([api_row("0001", "A")],
                         [page_row("0001", deals=["3/$12 When you buy 3 or more"])])
        self.assertEqual(recs[0]["volume_deals_price"], "")

    def test_gupc_and_unit_price_stay_empty_through_the_merge(self):
        recs, _, _ = run([api_row("0001", "A")], [page_row("0001", "$0.03/fl oz")])
        self.assertEqual(recs[0]["gupc"], "")
        self.assertEqual(recs[0]["unit_price"], "")


if __name__ == "__main__":
    unittest.main()
