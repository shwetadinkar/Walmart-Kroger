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

from merge_page_enrichment import (  # noqa: E402
    build_lookup, main, split_deals)
from marianos_collector.composition import BINDING_KEY  # noqa: E402

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


class TheDealColumnsTakeOnlyOffers(unittest.TestCase):
    """The split used to be "anything not prefixed Coupon: is a volume deal".

    That published a stock status into volume_deals_description on 47 rows of
    the 1 November read and an offer link on 12 more. The split now asks the
    parser what each line is, so re-merging a page read parsed before that
    distinction existed gives the same answer as one parsed after it.
    """

    def test_a_stock_status_reaches_neither_deal_column(self):
        vol, dig = split_deals(["Low Stock"])
        self.assertEqual((vol, dig), ("", ""))

    def test_a_payment_eligibility_reaches_neither_deal_column(self):
        vol, dig = split_deals(["SNAP EBT"])
        self.assertEqual((vol, dig), ("", ""))

    def test_an_offer_link_reaches_neither_deal_column(self):
        vol, dig = split_deals(["View 2 Offers"])
        self.assertEqual((vol, dig), ("", ""))

    def test_a_badge_beside_an_offer_leaves_only_the_offer(self):
        vol, dig = split_deals(["Low Stock", "Save $15 when you spend $60"])
        self.assertEqual(vol, "Save $15 when you spend $60")
        self.assertEqual(dig, "")

    def test_cash_back_is_a_digital_offer_not_a_volume_one(self):
        vol, dig = split_deals(
            ["Cash Back: $5.00 Cash Back on Pabst Blue Ribbon or Pabst Light"])
        self.assertEqual(vol, "")
        self.assertEqual(
            dig, "Cash Back: $5.00 Cash Back on Pabst Blue Ribbon or Pabst Light")

    def test_the_wording_is_passed_through_unchanged(self):
        line = "Save $2 each when you buy 3 or more"
        vol, _ = split_deals(["Low Stock", line, "View 1 Offer"])
        self.assertEqual(vol, line)


class SeveralReadsAreAppliedInOnePass(unittest.TestCase):
    """Chaining a second merge onto the first one's output falsifies provenance.

    Run that way on 4 November against the real 28,549 release, 526 page-derived
    `ppm` values and all 53 digital deal descriptions came back attributed to
    `kroger_public` - the Kroger public Products API, which carries neither
    field at any tier. Every count was right, no conflict was reported and
    nothing failed; only the source labels were wrong, because the second pass
    cannot tell the first pass's contributions from the spine's own values.
    """

    @staticmethod
    def rec(upc, ppm="", deals=()):
        return {"upc": upc, "ppm": ppm, "deal_lines": list(deals)}

    def lookup_for(self, reads):
        lookup, _ = build_lookup(reads, "53100502")
        return lookup

    def test_a_value_from_either_read_is_attributed_to_the_page_not_the_spine(self):
        lookup = self.lookup_for([
            ([self.rec("0001", ppm="$1.00/oz")], "2026-11-01T00:00:00+00:00"),
            ([self.rec("0002", ppm="$2.00/oz")], "2026-11-03T00:00:00+00:00"),
        ])
        for upc in ("0001", "0002"):
            self.assertEqual(lookup(None, upc, None)["ppm"],
                             {"0001": "$1.00/oz", "0002": "$2.00/oz"}[upc])

    def test_each_product_carries_the_time_of_the_read_that_supplied_it(self):
        lookup = self.lookup_for([
            ([self.rec("0001", ppm="$1.00/oz")], "2026-11-01T00:00:00+00:00"),
            ([self.rec("0002", ppm="$2.00/oz")], "2026-11-03T00:00:00+00:00"),
        ])
        self.assertEqual(lookup(None, "0001", None)[BINDING_KEY]["observed_at"],
                         "2026-11-01T00:00:00+00:00")
        self.assertEqual(lookup(None, "0002", None)[BINDING_KEY]["observed_at"],
                         "2026-11-03T00:00:00+00:00")

    def test_the_freshest_read_wins_for_a_product_in_both(self):
        lookup = self.lookup_for([
            ([self.rec("0001", ppm="$1.00/oz")], "2026-11-01T00:00:00+00:00"),
            ([self.rec("0001", ppm="$1.50/oz")], "2026-11-03T00:00:00+00:00"),
        ])
        got = lookup(None, "0001", None)
        self.assertEqual(got["ppm"], "$1.50/oz")
        self.assertEqual(got[BINDING_KEY]["observed_at"], "2026-11-03T00:00:00+00:00")

    def test_read_order_on_the_command_line_does_not_decide_which_wins(self):
        """The observation time decides, not the argument order."""
        lookup = self.lookup_for([
            ([self.rec("0001", ppm="$1.50/oz")], "2026-11-03T00:00:00+00:00"),
            ([self.rec("0001", ppm="$1.00/oz")], "2026-11-01T00:00:00+00:00"),
        ])
        self.assertEqual(lookup(None, "0001", None)["ppm"], "$1.50/oz")

    def test_an_offer_the_later_read_did_not_see_is_not_carried_forward(self):
        """Offers expire. Four published digital deals dropped this way between
        the 1 and 4 November reads, which is correct: a coupon absent from the
        later observation is not evidence of a coupon now."""
        lookup = self.lookup_for([
            ([self.rec("0001", ppm="$1.00/oz", deals=["Coupon: Save $1.00"])],
             "2026-11-01T00:00:00+00:00"),
            ([self.rec("0001", ppm="$1.00/oz")], "2026-11-03T00:00:00+00:00"),
        ])
        self.assertNotIn("digital_deals_description", lookup(None, "0001", None))

    def test_fields_are_never_mixed_across_reads_for_one_product(self):
        """All three come from the one read that won, so a single observation
        time on the contribution is true of every value in it."""
        lookup = self.lookup_for([
            ([self.rec("0001", ppm="$1.00/oz", deals=["Buy 1, Get 1 Free"])],
             "2026-11-01T00:00:00+00:00"),
            ([self.rec("0001", ppm="$1.50/oz")], "2026-11-03T00:00:00+00:00"),
        ])
        got = lookup(None, "0001", None)
        self.assertEqual(got["ppm"], "$1.50/oz")
        self.assertNotIn("volume_deals_description", got)

    def test_a_disagreement_between_reads_is_recorded(self):
        lookup = self.lookup_for([
            ([self.rec("0001", ppm="$1.00/oz")], "2026-11-01T00:00:00+00:00"),
            ([self.rec("0001", ppm="$1.50/oz")], "2026-11-03T00:00:00+00:00"),
        ])
        self.assertEqual(len(lookup.disagreements["0001"]), 1)
        entry = lookup.disagreements["0001"][0]
        self.assertEqual((entry["field"], entry["earlier_value"], entry["later_value"]),
                         ("ppm", "$1.00/oz", "$1.50/oz"))

    def test_agreement_between_reads_is_not_recorded_as_a_disagreement(self):
        lookup = self.lookup_for([
            ([self.rec("0001", ppm="$1.00/oz")], "2026-11-01T00:00:00+00:00"),
            ([self.rec("0001", ppm="$1.00/oz")], "2026-11-03T00:00:00+00:00"),
        ])
        self.assertEqual(lookup.disagreements, {})

    def test_one_read_still_works_the_old_way(self):
        lookup, _ = build_lookup([self.rec("0001", ppm="$1.00/oz")],
                                 "53100502", "2026-11-01T00:00:00+00:00")
        self.assertEqual(lookup(None, "0001", None)["ppm"], "$1.00/oz")


if __name__ == "__main__":
    unittest.main()
