"""The retailer's own published taxonomy, as a denominator for coverage.

Every coverage statement in this project has been bounded by the same
admission: term-filtered search cannot attest complete category discovery, so
we could say what we collected but not what we collected it out of. The
retailer publishes a product-listing sitemap that robots.txt advertises, and
it enumerates its own category structure. That is the first denominator this
project has had for categories.

It is not a denominator for products, and the tests that matter most here are
the ones that stop it being read as one.
"""

import csv
import json
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import sitemap_reconciliation as recon  # noqa: E402
from marianos_collector.kroger import Credentials, KrogerClient, KrogerError  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
TAXONOMY = ROOT / "evidence/2026-11-02-marianos-sitemap-taxonomy.json"


def configured_roots():
    with (ROOT / "config/categories.csv").open(newline="", encoding="utf-8-sig") as s:
        return [r["Category (Auto)"].strip() for r in csv.DictReader(s)
                if r.get("Category (Auto)", "").strip()]


def row(url="", upc="", category="Dairy"):
    return {"url": url, "upc": upc, "category": category}


class TheCapturedTaxonomyIsWhatItClaims(unittest.TestCase):
    def setUp(self):
        self.tax = json.loads(TAXONOMY.read_text())

    def test_every_listing_id_encodes_its_own_depth(self):
        for entry in self.tax["listing_pages"]["entries"]:
            with self.subTest(id=entry["id"]):
                self.assertEqual(recon.DEPTH_LABEL[len(entry["id"])], entry["depth"])

    def test_every_subcategory_and_leaf_sits_under_a_published_department(self):
        departments = {e["id"] for e in self.tax["listing_pages"]["entries"]
                       if e["depth"] == "department"}
        for entry in self.tax["listing_pages"]["entries"]:
            if entry["depth"] != "department":
                with self.subTest(id=entry["id"]):
                    self.assertIn(entry["id"][:2], departments)

    def test_the_counts_match_the_entries(self):
        pages = self.tax["listing_pages"]
        self.assertEqual(pages["total"], len(pages["entries"]))
        self.assertEqual(pages["departments"] + pages["subcategories"] + pages["leaves"],
                         pages["total"])

    def test_every_url_is_a_marianos_listing_url(self):
        for entry in self.tax["listing_pages"]["entries"]:
            with self.subTest(id=entry["id"]):
                self.assertEqual(
                    entry["url"],
                    f"https://www.marianos.com/pl/{entry['slug']}/{entry['id']}")

    def test_the_seo_product_list_is_labelled_as_a_subset_not_a_catalogue(self):
        caution = self.tax["seo_product_pages"]["_caution"]
        self.assertIn("NOT a route to complete product enumeration", caution)
        self.assertEqual(self.tax["seo_product_pages"]["total"],
                         len(self.tax["seo_product_pages"]["entries"]))

    def test_it_records_that_a_datacenter_fetch_was_refused(self):
        self.assertIn("refused", self.tax["captured_how"])
        self.assertIn("none was bypassed", self.tax["captured_how"])


class TheRootMapIsCheckedNotAsserted(unittest.TestCase):
    """The map duplicates ids that live in the evidence file, so the tool
    verifies every one of them and refuses to report if any is wrong."""

    def setUp(self):
        self.tax = json.loads(TAXONOMY.read_text())

    def test_every_mapped_id_exists_in_the_captured_taxonomy(self):
        """A root may map to more than one department: the client's single
        Kitchen Dining root spans the retailer's 28 kitchen and 40 dining."""
        ids = {e["id"] for e in self.tax["listing_pages"]["entries"]}
        for name, value in recon.ROOT_TO_SITE.items():
            if value is None:
                continue
            mapped = (value,) if isinstance(value, str) else tuple(value)
            for site_id in mapped:
                with self.subTest(root=name, id=site_id):
                    self.assertIn(site_id, ids)

    def test_a_wrong_id_in_the_map_stops_the_report(self):
        with unittest.mock.patch.dict(recon.ROOT_TO_SITE, {"Dairy": "99"}):
            with self.assertRaises(SystemExit) as caught:
                recon.reconcile(self.tax, [row()], configured_roots())
        self.assertIn("absent from the captured taxonomy", str(caught.exception))

    def test_the_map_covers_exactly_the_configured_roots(self):
        report = recon.reconcile(self.tax, [row()], configured_roots())
        self.assertEqual(report["roots_unmapped_and_therefore_unreported"], [])
        self.assertEqual(report["mapped_roots_not_in_the_configured_set"], [])

    def test_a_root_added_to_the_csv_without_the_map_is_reported_not_ignored(self):
        report = recon.reconcile(self.tax, [row()], configured_roots() + ["Brand New"])
        self.assertEqual(report["roots_unmapped_and_therefore_unreported"], ["Brand New"])

    def test_the_five_roots_published_only_as_subcategories(self):
        report = recon.reconcile(self.tax, [row()], configured_roots())
        subs = sorted(r["root"] for r in report["roots"]
                      if r["published_depth"] == "subcategory")
        self.assertEqual(subs, ["Batteries", "Candles Home Fragrances", "Coffee",
                                "Light Bulbs", "Seafood"])

    def test_the_roots_with_no_published_listing_page(self):
        report = recon.reconcile(self.tax, [row()], configured_roots())
        none = sorted(r["root"] for r in report["roots"]
                      if r["published_depth"] == "none")
        self.assertEqual(none, ["Bakery", "Beer Wine Liquor", "Coupons", "Floral"])

    def test_a_root_the_api_evidences_but_the_sitemap_does_not_says_so(self):
        """Bakery has no listing page and 604 delivered records. Neither
        vocabulary is treated as authoritative."""
        report = recon.reconcile(self.tax, [row(category="Bakery")], configured_roots())
        bakery = next(r for r in report["roots"] if r["root"] == "Bakery")
        self.assertEqual(bakery["evidenced_by"],
                         "Kroger API labels only, no published listing page")

    def test_a_root_neither_source_evidences_says_neither(self):
        report = recon.reconcile(self.tax, [row(category="Dairy")], configured_roots())
        coupons = next(r for r in report["roots"] if r["root"] == "Coupons")
        self.assertEqual(coupons["evidenced_by"], "neither")


class ProductsAreMatchedOnUrlAndUpc(unittest.TestCase):
    def setUp(self):
        self.tax = json.loads(TAXONOMY.read_text())
        self.first = self.tax["seo_product_pages"]["product_ids"][0]

    def test_a_product_matched_by_its_url_tail_counts_as_present(self):
        rows = [row(url=f"https://www.marianos.com/p/thing/{self.first}")]
        report = recon.reconcile(self.tax, rows, configured_roots())
        self.assertEqual(report["seo_product_sitemap"]["in_delivered_dataset"], 1)

    def test_a_product_matched_by_upc_alone_counts_as_present(self):
        """A record with no observed URL still has an identity through its
        UPC, and the retention rule keeps it. It must not be counted missing."""
        report = recon.reconcile(self.tax, [row(upc=self.first)], configured_roots())
        self.assertEqual(report["seo_product_sitemap"]["in_delivered_dataset"], 1)

    def test_present_and_absent_always_sum_to_the_published_total(self):
        for rows in ([], [row(upc=self.first)], [row(upc="0000000000000")]):
            with self.subTest(rows=len(rows)):
                seo = recon.reconcile(self.tax, rows, configured_roots())["seo_product_sitemap"]
                self.assertEqual(seo["in_delivered_dataset"] + seo["absent_from_delivered_dataset"],
                                 seo["published"])

    def test_the_absent_ids_are_listed_so_they_can_be_resolved(self):
        seo = recon.reconcile(self.tax, [], configured_roots())["seo_product_sitemap"]
        self.assertEqual(len(seo["absent_ids"]), seo["absent_from_delivered_dataset"])


class TheReportRefusesToBeReadAsACoveragePercentage(unittest.TestCase):
    def test_the_disclaimer_names_the_three_reasons_it_is_not_one(self):
        text = recon.DOES_NOT_ESTABLISH
        self.assertIn("not a coverage percentage", text)
        self.assertIn("not a random sample", text)
        self.assertIn("not the whole taxonomy", text)
        self.assertIn("capture, not a feed", text)

    def test_it_states_that_an_absent_product_may_simply_not_be_carried(self):
        self.assertIn("may not be carried", recon.DOES_NOT_ESTABLISH)

    def test_the_written_report_carries_the_real_figures(self):
        tax = json.loads(TAXONOMY.read_text())
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "out"
            data = Path(td) / "data.json"
            data.write_text(json.dumps([row(upc=tax["seo_product_pages"]["product_ids"][0])]))
            recon.main(["--taxonomy", str(TAXONOMY), "--data", str(data),
                        "--out", str(out)])
            disclaimer = (out / "DOES_NOT_ESTABLISH.md").read_text()
            self.assertIn("890", disclaimer)
            self.assertIn("889 of those 890", disclaimer)
            self.assertEqual(len(json.loads((out / "absent_from_delivered.json").read_text())), 889)


class TheEndpointAllowlistStaysAnAllowlist(unittest.TestCase):
    """Resolving the gap needs product-details-by-id, so the Kroger client's
    allowlist was widened. It must have been widened by exactly that much."""

    def client(self):
        return KrogerClient(Credentials("id", "secret"))

    def test_a_thirteen_digit_product_id_is_allowed(self):
        self.assertTrue(KrogerClient._PRODUCT_BY_ID.match("/products/0001111078407"))

    def test_nothing_else_under_products_is_allowed(self):
        for path in ("/products/", "/products/123", "/products/abcdefghijklm",
                     "/products/0001111078407/extra", "/products/0001111078407?x=1",
                     "/products/00011110784071", "/products/../locations"):
            with self.subTest(path=path):
                self.assertIsNone(KrogerClient._PRODUCT_BY_ID.match(path))

    def test_an_undocumented_endpoint_is_still_refused(self):
        for path in ("/coupons", "/cart", "/identity/profile", "/products/0001111078407/x"):
            with self.subTest(path=path), self.assertRaises(KrogerError) as caught:
                self.client().get(path)
            self.assertIn("Only approved documented", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
