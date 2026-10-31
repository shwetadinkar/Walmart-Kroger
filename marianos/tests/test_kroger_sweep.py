"""The Kroger sweep and the normalizer it was ported onto.

The first sweep, stopped on 31 October 2026, fabricated product URLs, took the
first item whatever it was, skipped `make_record`, kept no raw response, and
wrote 18,351 records with a blank store_name and store_location. Its 63 page
failures were all HTTP 400 at filter.start=251. Each of those has a test here.
Everything runs against a fake client; no test touches the network.
"""
import csv
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import sys as _sys, pathlib as _pathlib
_ROOT = _pathlib.Path(__file__).resolve().parent.parent
_sys.path.insert(0, str(_ROOT))
_sys.path.insert(0, str(_ROOT / "tools"))

import kroger_full_sweep as sweep_tool
from marianos_collector.api_trial import normalize, verify_store
from marianos_collector.config import Store
from marianos_collector.kroger import KrogerError
from marianos_collector.schema import FIELDS, RecordRejected

STORE = Store("53100508", "60661", "Marianos - Marianos West Loop",
              "40 S Halsted St, Chicago, IL 60661", sweep_tool.LOGO)
CATEGORY_MAP = {"Dairy": "Dairy", "Produce": "Produce"}
LOCATION = {"locationId": "53100508", "chain": "MARIANOS",
            "name": "Marianos - Marianos West Loop",
            "address": {"addressLine1": "40 S Halsted St", "city": "Chicago",
                        "state": "IL", "zipCode": "60661"}}


def offer(**changes):
    item = {"soldBy": "UNIT", "size": "18 ct", "fulfillment": {"curbside": True},
            "price": {"regular": 2.98, "promo": 0}}
    item.update(changes)
    return item


def product(upc="0001111060933", **changes):
    p = {"productId": upc, "upc": upc, "description": "Kroger Eggs", "brand": "Kroger",
         "productPageURI": f"/p/kroger-eggs/{upc}?cid=source",
         "categories": ["Dairy"], "items": [offer()], "images": []}
    p.update(changes)
    return p


def norm(p):
    return normalize(p, STORE, "2026-10-31", CATEGORY_MAP)


class FakeClient:
    """Serves pages per start value; refuses filter.start above `cap` as Kroger did."""

    def __init__(self, pages=None, cap=250):
        self.pages = pages or {}
        self.cap = cap
        self.starts = []

    def products(self, location_id, term, offset=0, limit=50):
        self.starts.append(offset)
        if offset > self.cap:
            raise KrogerError("Kroger API HTTP 400")
        return {"data": self.pages.get(offset, []), "meta": {"term": term}}

    def get(self, path, params=None):
        return {"data": json.loads(json.dumps(LOCATION))}


def run(client, terms=None, **kwargs):
    budget = sweep_tool.Budget(100, 60)
    return sweep_tool.sweep(client, STORE.store_id, STORE,
                            terms or {"Dairy": ["eggs"]}, budget, 20,
                            log=lambda *_: None, category_map=CATEGORY_MAP, **kwargs)


def full_page(start):
    return [product(f"{start + n:013d}") for n in range(50)]


class NormalizeTests(unittest.TestCase):
    def test_url_comes_from_the_api_not_from_the_upc(self):
        r = norm(product())
        self.assertEqual(r["url"], "https://www.marianos.com/p/kroger-eggs/0001111060933")

    def test_query_and_fragment_are_stripped_from_the_url(self):
        clean = "https://www.marianos.com/p/kroger-eggs/0001111060933"
        for suffix in ("?cid=dmF-our-client-id", "#reviews", "?cid=x&y=z#reviews"):
            with self.subTest(suffix=suffix):
                uri = "/p/kroger-eggs/0001111060933" + suffix
                self.assertEqual(norm(product(productPageURI=uri))["url"], clean)

    def test_a_uri_with_no_query_is_unchanged(self):
        uri = "/p/kroger-eggs/0001111060933"
        self.assertEqual(norm(product(productPageURI=uri))["url"],
                         "https://www.marianos.com" + uri)

    def test_the_product_id_is_still_checked_behind_a_query(self):
        with self.assertRaisesRegex(ValueError, "INVALID_PRODUCT_URI"):
            norm(product(productPageURI="/p/x/999999999?cid=x"))

    def test_a_bad_product_uri_is_refused(self):
        for uri in ("", None, "https://evil.example/p/x/0001111060933",
                    "//evil.example/p/x/0001111060933", "/q/x/0001111060933", "/p/x/999999999"):
            with self.subTest(uri=uri), self.assertRaisesRegex(ValueError, "INVALID_PRODUCT_URI"):
                norm(product(productPageURI=uri))

    def test_a_bad_upc_is_refused(self):
        for upc in ("", None, 1234567890123, "12345", "abc45678"):
            with self.subTest(upc=upc), self.assertRaisesRegex(ValueError, "INVALID_UPC"):
                norm(product(upc=upc))

    def test_the_qualifying_offer_is_used_not_the_first_item(self):
        r = norm(product(items=[
            offer(fulfillment={"shipToHome": True}, price={"regular": 99.0}, size="1 ct"),
            offer(price={"regular": 3.49}, size="12 ct")]))
        self.assertEqual((r["regular_price"], r["weight"]), ("3.49", "12 ct"))

    def test_an_offer_that_does_not_qualify_is_refused(self):
        bad = {
            "sold by weight": offer(soldBy="WEIGHT"),
            "no curbside": offer(fulfillment={"curbside": False}),
            "in store only": offer(fulfillment={"inStore": True}),
            "no size": offer(size=""),
            "no price": offer(price=None),
            "no regular": offer(price={"promo": 1.0}),
            "zero": offer(price={"regular": 0}),
            "negative": offer(price={"regular": -1}),
            "infinite": offer(price={"regular": float("inf")}),
            "nan": offer(price={"regular": float("nan")}),
            "boolean": offer(price={"regular": True}),
            "string": offer(price={"regular": "2.98"}),
        }
        for name, item in bad.items():
            with self.subTest(name), self.assertRaisesRegex(
                    ValueError, "NO_QUALIFYING_LOCAL_PICKUP_OFFER"):
                norm(product(items=[item]))

    def test_nulls_in_the_payload_are_a_refusal_not_a_crash(self):
        for item in (offer(soldBy=None), offer(fulfillment=None), "not an object"):
            with self.subTest(item=item), self.assertRaisesRegex(
                    ValueError, "NO_QUALIFYING_LOCAL_PICKUP_OFFER"):
                norm(product(items=[item]))
        with self.assertRaisesRegex(ValueError, "NO_QUALIFYING_LOCAL_PICKUP_OFFER"):
            norm(product(items=None))

    def test_make_record_applies_its_exclusions(self):
        with self.assertRaisesRegex(RecordRejected, "APPROXIMATE_WEIGHT_IN_TITLE"):
            norm(product(description="Chicken Average Weight 1 lb"))
        with self.assertRaisesRegex(RecordRejected, "^APPROXIMATE_WEIGHT$"):
            norm(product(items=[offer(size="about 2 lb")]))

    def test_exact_schema_and_estimates_stay_blank(self):
        p = product(items=[offer(price={"regular": 2.98, "regularPerUnitEstimate": 0.17})])
        r = norm(p)
        self.assertEqual(list(r), list(FIELDS))
        self.assertTrue(all(isinstance(v, str) for v in r.values()))
        self.assertEqual((r["ppm"], r["unit_price"], r["gupc"]), ("", "", ""))

    def test_promo_is_kept_and_a_zero_promo_is_absent(self):
        r = norm(product(items=[offer(price={"regular": 2.98, "promo": 1.99})]))
        self.assertEqual(r["sale_price"], "1.99")
        self.assertEqual(norm(product())["sale_price"], "")

    def test_a_mapped_label_sets_category_and_sub_category(self):
        r = norm(product(categories=["Dairy"]))
        self.assertEqual((r["category"], r["sub_category"]), ("Dairy", "Dairy"))

    def test_an_unmapped_label_leaves_category_empty(self):
        r = norm(product(categories=["Halloween"]))
        self.assertEqual((r["category"], r["sub_category"]), ("", "Halloween"))

    def test_private_brands_read_yes_in_any_case(self):
        for brand in ("Heritage Farm", "Luvsome", "Field & Vine", "Psst", "PSST",
                      "p$$t", "Kroger", "Roundy's", "ROUNDY'S"):
            with self.subTest(brand=brand):
                self.assertEqual(norm(product(brand=brand))["store_brand"], "yes")

    def test_a_house_brand_prefix_reads_yes(self):
        # Both observed in the probe, as brand values, not guessed.
        for brand in ("Kroger Carbmaster", "Roundy's Select", "Simply Roundy's"):
            with self.subTest(brand=brand):
                self.assertEqual(norm(product(brand=brand))["store_brand"], "yes")

    def test_other_brands_read_no(self):
        # The last three share a first word with a house brand, or its letters.
        for brand in ("Tyson", "Field Day", "", "Simple Mills", "Field Roast",
                      "Krogerville"):
            with self.subTest(brand=brand):
                self.assertEqual(norm(product(brand=brand))["store_brand"], "no")

    def test_the_front_image_is_used_not_the_first(self):
        images = [{"perspective": "back", "sizes": [{"size": "xlarge", "url": "https://i/back"}]},
                  {"perspective": "front", "sizes": [{"size": "small", "url": "https://i/small"},
                                                     {"size": "xlarge", "url": "https://i/front"}]}]
        self.assertEqual(norm(product(images=images))["image_url"], "https://i/front")

    def test_verify_store_refuses_another_banner(self):
        document = dict(LOCATION, chain="KROGER")
        with self.assertRaisesRegex(ValueError, "STORE_MISMATCH"):
            verify_store(document, "53100508", "60661")


class CategoryMapTests(unittest.TestCase):
    def setUp(self):
        self.map = json.loads((_ROOT / "config/category_map.json").read_text())["map"]

    def test_api_trial_category_map_is_merged_without_conflict(self):
        merged = {"Natural & Organic": "Natural Organic", "Dairy": "Dairy",
                  "Bakery": "Bakery", "Breakfast": "Breakfast", "Frozen": "Frozen",
                  "Deli": "Deli", "Beverages": "Beverages", "Produce": "Produce",
                  "Grocery": "Grocery", "Candy": "Candy", "Coffee": "Coffee",
                  "Baby": "Baby", "Beauty": "Beauty", "Health": "Health",
                  "Pet Care": "Pet Supplies"}
        for label, root in merged.items():
            self.assertEqual(self.map.get(label), root, label)

    def test_kroger_bare_hardware_label_is_mapped(self):
        self.assertEqual(self.map["Hardware"], "Hardware Home Improvement")
        self.assertEqual(self.map["Hardware & Automotive"], "Hardware Home Improvement")

    def test_labels_with_no_client_root_stay_unmapped(self):
        for label in ("Halloween", "Party", "Entertainment"):
            self.assertNotIn(label, self.map)

    def test_every_root_is_one_of_the_clients_roots(self):
        with (_ROOT / "config/categories.csv").open(newline="", encoding="utf-8-sig") as f:
            roots = {row["Category (Auto)"] for row in csv.DictReader(f)}
        self.assertEqual(set(self.map.values()) - roots, set())


class SweepTests(unittest.TestCase):
    def test_refused_products_are_quarantined_with_reasons(self):
        good = product("0000000000001")
        weighed = product("0000000000002", items=[offer(soldBy="WEIGHT")])
        weighed_too = product("0000000000003", items=[offer(soldBy="WEIGHT")])
        titled = product("0000000000004", description="Beef Average Weight 2 lb")
        state = run(FakeClient({1: [good, weighed, weighed_too, titled]}))
        self.assertEqual(list(state["records"]), ["0000000000001"])
        self.assertEqual(state["term_counts"]["Dairy||eggs"], 1)
        self.assertEqual(
            {k: v["reason"] for k, v in state["quarantine"].items()},
            {"0000000000002": "NO_QUALIFYING_LOCAL_PICKUP_OFFER",
             "0000000000003": "NO_QUALIFYING_LOCAL_PICKUP_OFFER",
             "0000000000004": "APPROXIMATE_WEIGHT_IN_TITLE"})
        self.assertEqual(state["quarantine"]["0000000000004"]["found_by"], ["Dairy||eggs"])

    def test_a_malformed_product_is_quarantined_and_the_term_continues(self):
        state = run(FakeClient({1: ["junk", product(images=["junk"])]}))
        self.assertEqual(state["records"], {})
        self.assertEqual(
            sorted(v["reason"] for v in state["quarantine"].values()),
            ["MALFORMED_PRODUCT", "MALFORMED_PRODUCT:AttributeError"])

    def test_every_raw_response_is_kept_per_term_including_refused_products(self):
        refused = product("0000000000002", items=[offer(soldBy="WEIGHT")])
        pages = {1: full_page(1)[:49] + [refused], 51: [product("0000000000009")]}
        with tempfile.TemporaryDirectory() as tmp:
            run(FakeClient(pages), raw_dir=Path(tmp))
            folders = list(Path(tmp).iterdir())
            self.assertEqual(len(folders), 1)
            self.assertEqual(sorted(f.name for f in folders[0].iterdir()),
                             ["start_0001.json", "start_0051.json"])
            page = json.loads((folders[0] / "start_0001.json").read_text())
        self.assertEqual(page["response"]["data"], pages[1])
        self.assertEqual((page["locationId"], page["term"], page["term_root"], page["start"]),
                         ("53100508", "eggs", "Dairy", 1))
        self.assertTrue(page["observed_at"])

    def test_two_terms_never_share_a_raw_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            run(FakeClient({1: [product()]}), {"Dairy": ["a b", "a-b"]}, raw_dir=Path(tmp))
            self.assertEqual(len(list(Path(tmp).iterdir())), 2)

    def test_the_default_start_cap_stops_before_kroger_refuses(self):
        client = FakeClient({s: full_page(s) for s in (1, 51, 101, 151, 201)})
        state = run(client)
        self.assertEqual(client.starts, [1, 51, 101, 151, 201])
        self.assertEqual(state["page_failures"], [])
        self.assertEqual(state["terms_hit_start_cap"], ["Dairy||eggs"])

    def test_the_cap_constant_and_the_command_line_default_agree(self):
        self.assertEqual(sweep_tool.MAX_START, 201)
        with tempfile.TemporaryDirectory() as tmp:
            report = _main_run(Path(tmp) / "out")["report"]
        self.assertEqual(report["max_start"], 201)

    def test_unmapped_labels_are_reported_and_the_record_stays_blank(self):
        state = run(FakeClient({1: [product(categories=["Halloween"])]}))
        self.assertEqual(state["unmapped"], {"Halloween": ["0001111060933"]})
        self.assertEqual(state["records"]["0001111060933"]["category"], "")

    def test_the_term_root_never_becomes_the_category(self):
        state = run(FakeClient({1: [product(categories=["Produce"])]}))
        self.assertEqual(state["records"]["0001111060933"]["category"], "Produce")
        self.assertEqual(len(state["category_disagreements"]), 1)


def _main_run(out, argv=(), client=None, category_map=None):
    """main() with a fake client and fake credentials, one term, nothing fetched."""
    terms = out.parent / "terms.json"
    terms.write_text(json.dumps({"terms": {"Dairy": ["eggs"]}}))
    if category_map:
        mapping = out.parent / "map.json"
        mapping.write_text(json.dumps({"map": category_map}))
        argv = [*argv, "--category-map", str(mapping)]
    client = client or FakeClient({1: [
        product(), product("0000000000002", items=[offer(soldBy="WEIGHT")])]})
    env = {"KROGER_CLIENT_ID": "fake", "KROGER_CLIENT_SECRET": "fake"}
    with mock.patch.dict(os.environ, env), \
            mock.patch.object(sweep_tool, "KrogerClient", lambda creds: client), \
            mock.patch("sys.stderr", new=_Sink()), mock.patch("sys.stdout", new=_Sink()):
        code = sweep_tool.main(["--location-id", "53100508", "--zipcode", "60661",
                                "--terms", str(terms), "--output", str(out), *argv])
    report = out / "run_report.json"
    return {"code": code, "client": client,
            "report": json.loads(report.read_text()) if report.exists() else None}


class _Sink:
    def write(self, *_):
        pass

    def flush(self):
        pass


class MainTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.out = Path(self._tmp.name) / "out"

    def rows(self):
        return json.loads((self.out / "data_22_fields.json").read_text())

    def test_records_carry_the_store_kroger_resolved(self):
        self.assertEqual(_main_run(self.out)["code"], 0)
        row = self.rows()[0]
        self.assertEqual(
            (row["zipcode"], row["store_name"], row["store_location"], row["store_logo"]),
            ("60661", "Marianos - Marianos West Loop",
             "40 S Halsted St, Chicago, IL 60661", sweep_tool.LOGO))

    def test_a_store_of_another_banner_stops_the_run(self):
        class OtherBanner(FakeClient):
            def get(self, path, params=None):
                return {"data": dict(LOCATION, chain="KROGER")}
        client = OtherBanner()
        with self.assertRaisesRegex(ValueError, "STORE_MISMATCH"):
            _main_run(self.out, client=client)
        self.assertEqual(client.starts, [])

    def test_no_published_record_carries_the_query(self):
        _main_run(self.out)
        self.assertEqual(self.rows()[0]["url"],
                         "https://www.marianos.com/p/kroger-eggs/0001111060933")
        self.assertNotIn("cid=", (self.out / "data_22_fields.json").read_text())

    def test_quarantine_and_raw_are_written_and_reported(self):
        report = _main_run(self.out)["report"]
        self.assertEqual(report["quarantined_products"], 1)
        self.assertEqual(report["quarantine_reasons"],
                         {"NO_QUALIFYING_LOCAL_PICKUP_OFFER": 1})
        quarantine = json.loads((self.out / "quarantine.json").read_text())
        self.assertEqual(list(quarantine), ["0000000000002"])
        self.assertEqual(len(list((self.out / "raw").rglob("start_0001.json"))), 1)

    def test_the_report_says_search_cannot_attest_discovery(self):
        section = _main_run(self.out)["report"]["does_not_establish"]
        self.assertIn("cannot attest complete category discovery",
                      section["complete_category_discovery"])

    def test_terms_reaching_the_cap_are_listed_by_name(self):
        client = FakeClient({s: full_page(s) for s in (1, 51, 101, 151, 201)})
        section = _main_run(self.out, client=client)["report"]["does_not_establish"]
        results = section["complete_results_per_term"]
        self.assertEqual(results["truncated_terms"], ["Dairy||eggs"])
        self.assertEqual(results["limit_per_term"], 250)

    def test_a_term_that_stopped_on_a_failed_page_is_listed_too(self):
        client = FakeClient({s: full_page(s) for s in (1, 51, 101, 151, 201)})
        report = _main_run(self.out, ["--max-start", "251"], client)["report"]
        self.assertEqual(report["terms_that_hit_the_start_cap"], [])
        self.assertEqual(report["does_not_establish"]["complete_results_per_term"]
                         ["truncated_terms"], ["Dairy||eggs"])

    def test_a_term_that_ended_naturally_is_not_called_truncated(self):
        section = _main_run(self.out)["report"]["does_not_establish"]
        self.assertEqual(section["complete_results_per_term"]["truncated_terms"], [])

    def test_empty_seafood_and_coffee_roots_are_explained_from_the_data(self):
        meat = product("0000000000005", categories=["Meat & Seafood"])
        client = FakeClient({1: [meat]})
        roots = _main_run(self.out, client=client, category_map={
            "Meat & Seafood": "Meat"})["report"]["does_not_establish"]["populated_roots"]
        self.assertIn("from the 1 records", roots["Seafood"])
        self.assertTrue(roots["Coffee"].startswith("0 products"))

    def test_a_populated_coffee_root_is_not_reported_as_empty(self):
        coffee = product("0000000000006", categories=["Coffee"])
        roots = _main_run(self.out, client=FakeClient({1: [coffee]}), category_map={
            "Coffee": "Coffee"})["report"]["does_not_establish"]["populated_roots"]
        self.assertNotIn("Coffee", roots)
        self.assertIn("Seafood", roots)

    def test_a_coffee_label_behind_another_label_is_counted(self):
        both = product("0000000000007", categories=["Dairy", "Coffee"])
        roots = _main_run(self.out, client=FakeClient({1: [both]}), category_map={
            "Dairy": "Dairy", "Coffee": "Coffee"})["report"]["does_not_establish"]["populated_roots"]
        self.assertTrue(roots["Coffee"].startswith("1 products"))

    def test_blank_fields_are_explained_without_denying_the_estimate(self):
        section = _main_run(self.out)["report"]["does_not_establish"]
        blanks = section["displayed_prices_and_deals"]
        self.assertEqual(set(blanks), {
            "ppm", "volume_deals_description", "volume_deals_price",
            "digital_deals_description", "digital_deals_price"})
        self.assertIn("regularPerUnitEstimate", blanks["ppm"])

    def test_an_earlier_run_is_not_overwritten_by_a_fresh_start(self):
        self.out.mkdir()
        checkpoint = self.out / "checkpoint.json"
        # A current version, so only the fresh-start guard can refuse this one.
        body = json.dumps({"state_version": sweep_tool.STATE_VERSION,
                           "records": {}, "done_terms": []})
        checkpoint.write_text(body)
        client = FakeClient()
        self.assertEqual(_main_run(self.out, client=client)["code"], 2)
        self.assertEqual(checkpoint.read_text(), body)
        self.assertEqual(sorted(p.name for p in self.out.iterdir()), ["checkpoint.json"])
        self.assertEqual(client.starts, [])

    def test_a_checkpoint_from_the_old_rules_cannot_be_resumed(self):
        self.out.mkdir()
        checkpoint = self.out / "checkpoint.json"
        body = json.dumps({"records": {"old": {}}, "done_terms": []})
        checkpoint.write_text(body)
        client = FakeClient()
        self.assertEqual(_main_run(self.out, ["--resume"], client)["code"], 2)
        self.assertEqual(checkpoint.read_text(), body)
        self.assertEqual(sorted(p.name for p in self.out.iterdir()), ["checkpoint.json"])
        self.assertEqual(client.starts, [])

    def test_a_checkpoint_from_before_the_url_fix_cannot_be_resumed(self):
        # Version 2 records carry ?cid= in their URLs and an older store_brand.
        self.out.mkdir()
        checkpoint = self.out / "checkpoint.json"
        body = json.dumps({"state_version": 2, "records": {}, "done_terms": []})
        checkpoint.write_text(body)
        client = FakeClient()
        self.assertEqual(_main_run(self.out, ["--resume"], client)["code"], 2)
        self.assertEqual(checkpoint.read_text(), body)
        self.assertEqual(client.starts, [])

    def test_a_current_checkpoint_resumes_without_refetching(self):
        self.assertEqual(_main_run(self.out)["code"], 0)
        client = FakeClient()
        result = _main_run(self.out, ["--resume"], client)
        self.assertEqual(result["code"], 0)
        self.assertEqual(client.starts, [])
        self.assertEqual(result["report"]["unique_products"], 1)
        self.assertEqual(result["report"]["quarantined_products"], 1)


if __name__ == "__main__":
    unittest.main()
