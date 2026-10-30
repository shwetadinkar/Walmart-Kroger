from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import sys as _sys, pathlib as _pathlib
_sys.path.insert(0, str(_pathlib.Path(__file__).resolve().parent.parent))

from walmart_collector.config import categories_from_csv, stores_from_json, is_excluded_subcategory
from walmart_collector.schema import FIELDS, RecordRejected, make_record
from walmart_collector.sources import FixtureSource, SourceError
from walmart_collector.runner import Collector, ValidationFailure
from walmart_collector.storage import LocalStorage, read_json, StorageError

ROOT = Path(__file__).resolve().parent.parent
CATEGORIES = categories_from_csv(ROOT / "config/categories.csv")
STORES = stores_from_json(ROOT / "config/stores.json")

def product():
    return json.loads(next((ROOT / "fixtures" / "100" / "food").glob("*.json")).read_text())["products"][0]

class SchemaTests(unittest.TestCase):
    def test_exact_category_list(self):
        self.assertEqual(len(CATEGORIES),11)
        self.assertEqual(CATEGORIES[0].name,"Food")
        self.assertEqual(CATEGORIES[-1].name,"Office Supplies")
        self.assertTrue(is_excluded_subcategory("Recipes", CATEGORIES[0].exclusions))
        self.assertTrue(is_excluded_subcategory("Farm Animals", CATEGORIES[7].exclusions))
        self.assertFalse(is_excluded_subcategory("Canned Foods", CATEGORIES[0].exclusions))

    def test_schema_order_and_strings(self):
        p = product()
        result = make_record(p,STORES[0],"Food","", "2026-10-20")
        self.assertEqual(tuple(result),FIELDS)
        self.assertTrue(all(isinstance(v,str) for v in result.values()))
        self.assertEqual(result["gupc"],"")
        self.assertEqual(result["unit_price"],"")
        self.assertEqual(result["ppm"],"$0.29/oz")
        self.assertEqual(result["store_brand"],"yes")
        self.assertNotIn("remarks",result)
        self.assertEqual(list(result)[-1],"crawl_date")

    def test_no_recomputed_promotions(self):
        p = product()
        p["digital_deals_description"] = "Clip Coupon: Save $2"
        p["digital_deals_price"] = ""
        p["volume_deals_description"] = "Buy 1, Get 1 Free"
        p["volume_deals_price"] = ""
        result = make_record(p,STORES[0],"Food","", "2026-10-20")
        self.assertEqual(result["digital_deals_price"],"")
        self.assertEqual(result["volume_deals_price"],"")
        self.assertEqual(result["regular_price"],"3.99")

    def test_cashback_not_accepted_as_clip_deal(self):
        p = product()
        p["digital_deals_description"] = "Walmart Cash earn $5"
        with self.assertRaises(RecordRejected):
            make_record(p,STORES[0],"Food","", "2026-10-20")

    def test_shipping_or_marketplace_rejected(self):
        for field,value in (("fulfillment","shipping"),("seller_type","marketplace")):
            with self.subTest(field=field):
                p=product();p[field]=value
                with self.assertRaises(RecordRejected):
                    make_record(p,STORES[0],"Food","", "2026-10-20")

    def test_store_mismatch_rejected(self):
        p=product();p["zipcode"]="99999"
        with self.assertRaises(RecordRejected):
            make_record(p,STORES[0],"Food","", "2026-10-20")

    def test_approximate_weight_rejected(self):
        for value in ("approx. 2 lb", "approximately 2 pounds", "variable weight", "about 3 lb"):
            with self.subTest(value=value):
                p=product();p["weight"]=value
                with self.assertRaises(RecordRejected):
                    make_record(p,STORES[0],"Food","", "2026-10-20")

class CrashOnceFixture(FixtureSource):
    def __init__(self,directory):
        super().__init__(directory)
        self.fail=True
        self.attempts=[]
    def fetch(self, store, category, url, cursor):
        self.attempts.append((category.slug,url,cursor))
        if category.name == "Household Essentials" and self.fail:
            self.fail=False
            raise SourceError("Simulated process interruption")
        return super().fetch(store,category,url,cursor)

class EmptyFixture(FixtureSource):
    def fetch(self,store,category,url,cursor):
        page=super().fetch(store,category,url,cursor)
        page.products=[]
        return page

class BadLocation(FixtureSource):
    def fetch(self,store,category,url,cursor):
        page=super().fetch(store,category,url,cursor)
        page.zipcode="00000"
        return page

class DuplicatedFixture(FixtureSource):
    def fetch(self,store,category,url,cursor):
        page=super().fetch(store,category,url,cursor)
        page.products = page.products + page.products
        return page

class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.storage=LocalStorage(Path(self.tmp.name))
        self.source=FixtureSource(ROOT / "fixtures")
    def tearDown(self):
        self.tmp.cleanup()
    def runner(self,source=None,canaries=None):
        return Collector(self.storage,source or self.source,CATEGORIES,min_products=11,canaries=canaries)
    def test_both_stores_end_to_end(self):
        for s in STORES:
            value=self.runner().run(s)
            self.assertEqual(value["report"]["unique_records"],13)
            self.assertEqual(len(value["report"]["category_counts"]),11)
            self.assertEqual(value["report"]["excluded_records_by_reason"]["APPROXIMATE_WEIGHT"],1)
            self.assertEqual(value["report"]["excluded_records_by_reason"]["INELIGIBLE_FULFILLMENT"],1)
            rows=read_json(self.storage,value["manifest"]["data_key"])
            self.assertTrue(all(r["zipcode"] == s.zipcode for r in rows))
            self.assertFalse(any("Recipes" in r["sub_category"] for r in rows))
            self.assertTrue(any(r["sub_category"] == "Canned Foods" for r in rows))

    def test_resume_does_not_redo_finished_page(self):
        flaky=CrashOnceFixture(ROOT / "fixtures")
        with self.assertRaises(SourceError):
            self.runner(flaky).run(STORES[0])
        self.assertIsNone(read_json(self.storage,"published/100/latest.json"))
        cp=read_json(self.storage,"checkpoints/100/full/food.json")
        self.assertTrue(cp["finished"])
        seen_before=sum(1 for x in flaky.attempts if x[0]=="food")
        result=self.runner(flaky).run(STORES[0])
        self.assertEqual(seen_before,sum(1 for x in flaky.attempts if x[0]=="food"))
        self.assertEqual(result["manifest"]["records"],13)

    def test_previous_success_survives_zero_products(self):
        initial=self.runner().run(STORES[0])
        pointer=read_json(self.storage,"published/100/latest.json")
        with self.assertRaises(ValidationFailure):
            self.runner(EmptyFixture(ROOT / "fixtures")).run(STORES[0])
        self.assertEqual(read_json(self.storage,"published/100/latest.json"),pointer)
        self.assertEqual(read_json(self.storage,initial["manifest"]["data_key"])[0]["zipcode"],"72712")

    def test_invalid_location_fails_without_publication(self):
        with self.assertRaises(ValidationFailure):
            self.runner(BadLocation(ROOT / "fixtures")).run(STORES[0])
        self.assertIsNone(read_json(self.storage,"published/100/latest.json"))

    def test_dedup_placements(self):
        report=self.runner(DuplicatedFixture(ROOT / "fixtures")).run(STORES[0])["report"]
        self.assertEqual(report["unique_records"],13)
        self.assertGreater(report["duplicate_placements"],0)

    def test_missing_canary_fails(self):
        with self.assertRaises(ValidationFailure):
            self.runner(canaries={"Food":["UNKNOWN_ITEM"]}).run(STORES[0])
        self.assertIsNone(read_json(self.storage,"published/100/latest.json"))

    def test_locked_store_cannot_overlap(self):
        with self.storage.locked("100"):
            with self.assertRaises(StorageError):
                with self.storage.locked("100"):
                    pass

class AdditionalSafetyTests(unittest.TestCase):
    def test_provider_url_must_not_be_retailer(self):
        from walmart_collector.sources import AuthorizedProviderSource, SourceError
        with self.assertRaises(SourceError):
            AuthorizedProviderSource("https://www.walmart.com/api/undocumented", "test-token")
        with self.assertRaises(SourceError):
            AuthorizedProviderSource("http://approved.example/feed", "test-token")

    def test_provider_requires_location_evidence(self):
        from walmart_collector.sources import FixtureSource
        class FakeLiveSource(FixtureSource):
            source_mode = "authorized_provider_data_unverified_until_review"
        with tempfile.TemporaryDirectory() as root:
            store = LocalStorage(Path(root))
            with self.assertRaises(ValidationFailure):
                Collector(store, FakeLiveSource(ROOT / "fixtures"), CATEGORIES, min_products=11).run(STORES[0])
            self.assertIsNone(read_json(store,"published/100/latest.json"))

    def test_category_yield_drop_is_blocked(self):
        class LowerYield(FixtureSource):
            def fetch(self,store,category,url,cursor):
                page=super().fetch(store,category,url,cursor)
                # Remove the second page from Household Essentials without declaring a failure.
                if category.name == "Household Essentials" and not cursor:
                    page.next_cursor = ""
                return page
        with tempfile.TemporaryDirectory() as root:
            store=LocalStorage(Path(root))
            Collector(store,FixtureSource(ROOT / "fixtures"),CATEGORIES,min_products=11).run(STORES[0])
            before=read_json(store,"published/100/latest.json")
            with self.assertRaises(ValidationFailure):
                Collector(store,LowerYield(ROOT / "fixtures"),CATEGORIES,min_products=11,previous_ratio=.75).run(STORES[0])
            self.assertEqual(read_json(store,"published/100/latest.json"),before)

if __name__ == "__main__": unittest.main()
