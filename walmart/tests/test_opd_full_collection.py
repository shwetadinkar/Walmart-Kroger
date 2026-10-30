"""A genuine integration test of OPD adapter -> Collector -> publication; synthetic feeds only."""
import json
from contextlib import closing
import tempfile
import unittest
from datetime import datetime,timezone
from pathlib import Path
from unittest.mock import patch

from walmart_collector.config import Category,Store
from walmart_collector.opd import (
    WalmartOPDSnapshotSource, OPDClient, SourceError,
    _category_match, _to_raw, validate_signed_url
)
from walmart_collector.runner import Collector, ValidationFailure
from walmart_collector.storage import LocalStorage, read_json

URL = "https://storage.googleapis.com/test/fixture.json.gz"
TODAY = datetime.now(timezone.utc).date().isoformat()
STORES = [Store("100","72712","Walmart #100","Bentonville, AR"),
          Store("5959","77007","Walmart #5959","Houston, TX")]
CATEGORIES = [Category("Food","https://www.walmart.com/cp/food/976759",("recipes","shop all foods")),
              Category("Beauty","https://www.walmart.com/cp/beauty/1085666")]
MAP = {"Food":{"feed_category_id":"976759","path_segments":["Food"]},
       "Beauty":{"feed_category_id":"1085666","path_segments":["Beauty"]}}

class FakeClient:
    def __init__(self):
        self.verified = []
    def verify_store(self, store):
        self.verified.append(store.store_id)
        return {"fulfillmentStoreId":store.store_id,"fulfillmentType":"INSTORE_PICKUP"}
    def get_feeds(self, kind, category_id):
        return TODAY,[URL.replace("fixture",kind+"-"+category_id)]


def records_for(url, kind, store_id):
    cat_name = "Food" if "976759" in url else "Beauty"
    if kind == "catalog":
        return [dict(offerId=f"{cat_name}-1",itemId=101 if cat_name=="Food" else 201,
                     categoryPath="Home Page/"+cat_name+"/Shampoo", name="Sample "+cat_name,
                     productUrlText="/ip/test/123",upc="123456789012", size="12 fl oz",
                     productImage="https://i5.walmartimages.com/image.jpg",brandName="Example",
                     marketplace=False,isOnlineOnly=False),
                dict(offerId="MKT",itemId=999,categoryPath="Home Page/"+cat_name,
                     name="Marketplace",marketplace=True)]
    return [dict(offerId=cat_name+"-1",storeCode=store_id,availability="AVAILABLE",
                 currentPrice="2.99",unitPriceDisplay="(25.0 ¢/oz)"),
            dict(offerId=cat_name+"-1",storeCode="9999",availability="AVAILABLE",
                 currentPrice="0.99",unitPriceDisplay="(8 ¢/oz)")]

class TestOPD(unittest.TestCase):
    def test_category_exact_segments_and_exclusions(self):
        self.assertTrue(_category_match("Home Page/Food/Cereal",["Food"],("Recipes",)))
        self.assertFalse(_category_match("Home Page/Food/Recipes",["Food"],("Recipes",)))
        self.assertFalse(_category_match("Home Page/Foodie",["Food"],()))

    def test_signed_url_allowlist(self):
        validate_signed_url(URL)
        for bad in ["http://storage.googleapis.com/x.json.gz","https://evil.example/x.json.gz", "file:///etc/passwd"]:
            with self.assertRaises(SourceError): validate_signed_url(bad)

    def test_price_not_invented(self):
        record = _to_raw(dict(itemId=3,name="Test",size="1 lb",productUrlText="/ip/test/3",
                              categoryPath="Home Page/Food"),
                          dict(availability="AVAILABLE",currentPrice="3.15",storeCode="100",
                               unitPriceDisplay="(3.15 $/lb)"),STORES[0])
        self.assertEqual(record["regular_price"], "3.15")
        self.assertEqual(record["ppm"], "(3.15 $/lb)")
        self.assertEqual(record["sale_price"], "")
        self.assertEqual(record["digital_deals_price"], "")
        with self.assertRaises(SourceError):
            _to_raw(dict(itemId=3,name="Test",productUrlText="/ip/test/3"),
                    dict(availability="AVAILABLE",currentPrice="3.15",storeCode="5959"),STORES[0])

    def test_two_store_end_to_end(self):
        with tempfile.TemporaryDirectory() as base:
            for store in STORES:
                fake=FakeClient()
                def files(url,kind):
                    yield from records_for(url,kind,store.store_id)
                with patch("walmart_collector.opd.signed_records",files):
                    source=WalmartOPDSnapshotSource(fake,Path(base)/"cache",MAP,page_size=1)
                    result=Collector(LocalStorage(Path(base)/"data"),source,CATEGORIES,min_products=2,trial=True).run(store)
                self.assertEqual(result["manifest"]["records"],2)
                self.assertEqual(result["report"]["category_counts"],{"Food":1,"Beauty":1})
                self.assertEqual(result["report"]["field_completeness"]["ppm"]["nonempty"],2)
                storage = LocalStorage(Path(base)/"data")
                # OPD cannot attest full category coverage, so its output must
                # stay isolated in the trial namespace and must never appear as
                # a published release.
                self.assertIsNone(
                    read_json(storage, f"published/{store.store_id}/latest.json"),
                    "OPD output must not reach the published namespace")
                data = read_json(storage, result["manifest"]["data_key"])
                self.assertIn("trials/", result["manifest"]["data_key"])
                self.assertEqual(result["report"]["scope"], "trial")
                self.assertFalse(result["report"]["source_coverage_attested"])
                self.assertEqual(data[0]["sub_category"], "Shampoo")
                self.assertEqual(data[0]["unit_price"], "")
                self.assertEqual(data[0]["gupc"], "")
                self.assertEqual(fake.verified,[store.store_id])

    def test_failed_feed_does_not_publish_and_can_resume(self):
        with tempfile.TemporaryDirectory() as base:
            store = STORES[0]
            storage = LocalStorage(Path(base)/"data")
            def files(url,kind): yield from records_for(url,kind,store.store_id)
            fake=FakeClient()
            source=WalmartOPDSnapshotSource(fake,Path(base)/"cache",MAP)
            with patch("walmart_collector.opd.signed_records",files):
                Collector(storage,source,CATEGORIES,min_products=2,trial=True).run(store)
            previous=read_json(storage,"published/100/latest.json")
            # Force the next run to use fresh snapshot cache.
            for db in (Path(base)/"cache/100").glob("*.sqlite3"):
                import sqlite3
                # A sqlite3 connection context commits/rolls back but does NOT
                # close the connection. Explicit closing avoids ResourceWarning
                # under Python 3.13 during garbage collection of test mocks.
                with closing(sqlite3.connect(db)) as con:
                    with con:
                        con.execute("DELETE FROM meta WHERE key='built_on'")
                        con.execute("DELETE FROM done")
            def interrupted(url,kind):
                if "1085666" in url and kind=="catalog":
                    raise SourceError("Synthetic network disconnection")
                yield from records_for(url,kind,store.store_id)
            with patch("walmart_collector.opd.signed_records",interrupted):
                with self.assertRaises(SourceError):
                    Collector(storage,source,CATEGORIES,min_products=2,trial=True).run(store)
            self.assertEqual(read_json(storage,"published/100/latest.json"),previous)
            with patch("walmart_collector.opd.signed_records",files):
                result=Collector(storage,source,CATEGORIES,min_products=2,trial=True).run(store)
            self.assertEqual(result["manifest"]["records"],2)

    def test_credentials_required(self):
        with self.assertRaises(SourceError): OPDClient("","")

if __name__ == "__main__":unittest.main()

class TestStreaming(unittest.TestCase):
    def test_array_and_ndjson(self):
        import io
        from walmart_collector.opd import _stream_json_values
        for raw in [b'[{"offerId":"A"},{"offerId":"B"}]',b'{"offerId":"A"}\n{"offerId":"B"}\n', b'[\n {"offerId":"A"},\n {"offerId":"B"}\n]']:
            self.assertEqual([x["offerId"] for x in _stream_json_values(io.BytesIO(raw))], ["A","B"])
    def test_broken_array_fails_closed(self):
        import io
        from walmart_collector.opd import _stream_json_values
        with self.assertRaises(SourceError):
            list(_stream_json_values(io.BytesIO(b'[{"offerId":"A"}')))
