"""The five corrections from the client review of 31 October 2026.

Each test reproduces the case he described and asserts the corrected
behaviour. Synthetic feeds throughout; nothing here touches the network or the
delivered 615 products.
"""
import io
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import sys as _sys, pathlib as _pathlib
_sys.path.insert(0, str(_pathlib.Path(__file__).resolve().parent.parent))

from walmart_collector.config import Category, Store
from walmart_collector.opd import WalmartOPDSnapshotSource, _to_raw
from walmart_collector.runner import Collector, ValidationFailure
from walmart_collector.schema import RecordRejected, make_record
from walmart_collector.sources import FixtureSource
from walmart_collector.storage import LocalStorage, read_json

ROOT = Path(__file__).resolve().parent.parent
TODAY = datetime.now(timezone.utc).date().isoformat()
STORE = Store("100", "72712", "Walmart #100", "Bentonville, AR")
CATEGORIES = [Category("Food", "https://www.walmart.com/cp/food/976759"),
              Category("Beauty", "https://www.walmart.com/cp/beauty/1085666")]
MAP = {"Food": {"feed_category_id": "976759", "path_segments": ["Food"]},
       "Beauty": {"feed_category_id": "1085666", "path_segments": ["Beauty"]}}
URL = "https://storage.googleapis.com/test/fixture.json.gz"


class FakeClient:
    def verify_store(self, store):
        return {"fulfillmentStoreId": store.store_id, "fulfillmentType": "INSTORE_PICKUP"}

    def get_feeds(self, kind, category_id):
        return TODAY, [URL.replace("fixture", kind + "-" + category_id)]


def catalog_offer(name, offer, item, category):
    return dict(offerId=offer, itemId=item, name=name,
                categoryPath=f"Home Page/{category}/Shelf",
                productUrlText=f"/ip/test/{item}", upc="123456789012",
                size="12 fl oz", productImage="https://i5.walmartimages.com/i.jpg",
                brandName="Example", marketplace=False, isOnlineOnly=False)


def four_product_feed(url, kind, store_id):
    """His case: four eligible source products across two categories, of which
    one is unavailable and one is available but unpriced."""
    category = "Food" if "976759" in url else "Beauty"
    # Distinct item ids per category: the fingerprint is keyed on product_id, so
    # reusing ids across categories would make dedup collapse them and mask what
    # this test is actually measuring.
    base = 100 if category == "Food" else 200
    if kind == "catalog":
        return [catalog_offer(f"{category} available", f"{category}-ok", base + 1, category),
                catalog_offer(f"{category} unavailable", f"{category}-out", base + 2, category)]
    return [
        dict(offerId=f"{category}-ok", storeCode=store_id, availability="AVAILABLE",
             currentPrice="2.99", unitPriceDisplay="(25.0 c/oz)"),
        # Carried by the store, not sellable today.
        dict(offerId=f"{category}-out", storeCode=store_id, availability="OUT_OF_STOCK",
             currentPrice="", unitPriceDisplay=""),
    ]


def result_fields():
    from walmart_collector.schema import FIELDS
    return FIELDS


class RetentionTests(unittest.TestCase):
    """1. Unavailable and unpriced products must stay in the dataset."""

    def _run(self):
        with tempfile.TemporaryDirectory() as base:
            def files(url, kind):
                yield from four_product_feed(url, kind, STORE.store_id)
            with patch("walmart_collector.opd.signed_records", files):
                source = WalmartOPDSnapshotSource(FakeClient(), Path(base) / "cache",
                                                  MAP, page_size=10)
                storage = LocalStorage(Path(base) / "data")
                result = Collector(storage, source, CATEGORIES,
                                   min_products=2, trial=True).run(STORE)
                return result, read_json(storage, result["manifest"]["data_key"])

    def test_the_unavailable_product_is_published_not_dropped(self):
        _, data = self._run()
        titles = {r["product_title"] for r in data}
        self.assertIn("Food unavailable", titles)
        self.assertIn("Beauty unavailable", titles)

    def test_all_four_identities_survive(self):
        result, data = self._run()
        # Two categories, two offers each. Previously only the two priced ones
        # reached the output and the other two vanished entirely.
        self.assertEqual(result["manifest"]["records"], 4)
        self.assertEqual(len(data), 4)

    def test_an_unavailable_product_carries_empty_price_not_a_stale_one(self):
        _, data = self._run()
        out = next(r for r in data if r["product_title"] == "Food unavailable")
        self.assertEqual(out["regular_price"], "")
        self.assertEqual(out["sale_price"], "")
        self.assertEqual(out["ppm"], "")
        # Identity and descriptive fields are still carried.
        self.assertTrue(out["url"])
        self.assertTrue(out["upc"])

    def test_the_available_product_still_carries_its_price(self):
        _, data = self._run()
        ok = next(r for r in data if r["product_title"] == "Food available")
        self.assertEqual(ok["regular_price"], "2.99")
        self.assertEqual(ok["ppm"], "(25.0 c/oz)")

    def test_a_price_observed_on_an_unavailable_row_is_kept_with_its_context(self):
        # Client finding B3: the rule is never publish a value that was not
        # observed, not suppress one that was. Whether a shopper could pay it
        # is uncertain, and that uncertainty is a field, not an erasure.
        record = _to_raw(
            catalog_offer("Stale", "s", 7, "Food"),
            dict(availability="OUT_OF_STOCK", currentPrice="9.99",
                 unitPriceDisplay="83.25 c/oz", storeCode="100"), STORE)
        self.assertEqual(record["regular_price"], "9.99")
        self.assertEqual(record["ppm"], "83.25 c/oz")
        self.assertEqual(record["offer_availability"], "OUT_OF_STOCK")
        self.assertEqual(record["value_certainty"],
                         "observed_on_unavailable_offer_payability_unestablished")

    def test_an_available_row_is_marked_as_one(self):
        record = _to_raw(
            catalog_offer("Fresh", "f", 7, "Food"),
            dict(availability="AVAILABLE", currentPrice="1.00", storeCode="100"), STORE)
        self.assertEqual(record["value_certainty"], "observed_on_available_offer")

    def test_the_context_of_a_value_reaches_the_release_beside_the_record(self):
        import tempfile
        from pathlib import Path
        from walmart_collector.runner import Collector
        from walmart_collector.sources import Page
        from walmart_collector.storage import LocalStorage, read_json
        def row(title, number, availability, price):
            return dict(_to_raw(catalog_offer(title, title, number, "Food"),
                                dict(availability=availability, currentPrice=price,
                                     storeCode="100"), STORE),
                        upc=f"{number:012d}")
        class Source:
            source_mode = "synthetic_fixture_offer_context"
            coverage_attested = True
            def fetch(self, store, category, url, cursor):
                # Both categories carry the same two products, so they stay one
                # identity each and the counts below are of offers, not placements.
                return Page(store.store_id, store.zipcode, True, url,
                            [row("In", 1, "AVAILABLE", "1.00"),
                             row("Out", 2, "OUT_OF_STOCK", "9.99")], [], "", True)
        with tempfile.TemporaryDirectory() as tmp:
            storage = LocalStorage(Path(tmp))
            result = Collector(storage, Source(), CATEGORIES, min_products=1,
                               trial=True).run(STORE)
            rows = read_json(storage, result["manifest"]["data_key"])
            context = read_json(storage, result["manifest"]["offer_context_key"])
        self.assertEqual(next(r for r in rows if r["product_title"] == "Out")["regular_price"], "9.99")
        self.assertEqual(sorted(c["offer_availability"] for c in context.values()),
                         ["AVAILABLE", "OUT_OF_STOCK"])
        self.assertEqual(result["report"]["offer_availability_by_value"],
                         {"AVAILABLE": 1, "OUT_OF_STOCK": 1})
        self.assertEqual(sorted(rows[0]), sorted(result_fields()))

    def test_a_catalog_offer_with_no_store_price_row_is_unresolved_not_invented(self):
        """Store membership is evidenced by the store-scoped price feed. A
        catalog offer with no price row for this store has not been shown to be
        carried here, so it is neither published nor silently discarded."""
        def files(url, kind):
            category = "Food" if "976759" in url else "Beauty"
            if kind == "catalog":
                return iter([catalog_offer("Orphan", f"{category}-orphan", 300, category),
                             catalog_offer("Priced", f"{category}-ok", 301, category)])
            return iter([dict(offerId=f"{category}-ok", storeCode=STORE.store_id,
                              availability="AVAILABLE", currentPrice="1.50",
                              unitPriceDisplay="(1 c/oz)")])

        with tempfile.TemporaryDirectory() as base:
            with patch("walmart_collector.opd.signed_records", files):
                source = WalmartOPDSnapshotSource(FakeClient(), Path(base) / "cache",
                                                  MAP, page_size=10)
                storage = LocalStorage(Path(base) / "data")
                result = Collector(storage, source, CATEGORIES,
                                   min_products=1, trial=True).run(STORE)
                data = read_json(storage, result["manifest"]["data_key"])

        self.assertEqual({r["product_title"] for r in data}, {"Priced"})
        unresolved = {u["name"] for u in source.unresolved_offers}
        self.assertEqual(unresolved, {"Orphan"})
        self.assertIn("store assortment membership unestablished",
                      source.unresolved_offers[0]["reason"])


class CoverageGateTests(unittest.TestCase):
    """2. Incomplete coverage must block a full publication, not merely be disclosed."""

    def test_a_source_that_cannot_attest_coverage_cannot_publish_full(self):
        with tempfile.TemporaryDirectory() as base:
            source = WalmartOPDSnapshotSource(FakeClient(), Path(base) / "cache", MAP)
            with self.assertRaises(ValidationFailure) as caught:
                Collector(LocalStorage(Path(base) / "data"), source, CATEGORIES,
                          min_products=1)
            self.assertIn("does not attest complete coverage", str(caught.exception))

    def test_the_same_source_may_still_run_as_an_isolated_trial(self):
        with tempfile.TemporaryDirectory() as base:
            source = WalmartOPDSnapshotSource(FakeClient(), Path(base) / "cache", MAP)
            Collector(LocalStorage(Path(base) / "data"), source, CATEGORIES,
                      min_products=1, trial=True)

    def test_a_source_that_does_attest_is_unaffected(self):
        with tempfile.TemporaryDirectory() as base:
            Collector(LocalStorage(Path(base) / "data"),
                      FixtureSource(ROOT / "fixtures"), CATEGORIES, min_products=1)

    def test_a_source_that_declares_nothing_is_refused_rather_than_assumed_complete(self):
        class Undeclared:
            source_mode = "undeclared"
            def fetch(self, store, category, url, cursor):
                raise AssertionError("should never be reached")

        with tempfile.TemporaryDirectory() as base:
            with self.assertRaises(ValidationFailure):
                Collector(LocalStorage(Path(base) / "data"), Undeclared(),
                          CATEGORIES, min_products=1)


class ApproximateWeightTests(unittest.TestCase):
    """3. Approximate-weight wording must be excluded from titles too."""

    def raw(self, title, weight):
        return {"store_id": "100", "zipcode": "72712", "store_context_verified": True,
                "seller_type": "walmart", "fulfillment": "pickup",
                "product_id": "1", "product_title": title, "weight": weight,
                "regular_price": "4.99", "url": "https://www.walmart.com/ip/x/1",
                "upc": "1", "brand": "Example"}

    def test_approximate_wording_in_the_title_is_rejected(self):
        for title in ("Chicken approximately 1 lb",
                      "Chicken Average Weight 1 lb",
                      "Beef avg. weight 2 lb",
                      "Pork variable weight",
                      "Fish estimated weight 1 lb"):
            with self.assertRaises(RecordRejected, msg=title) as caught:
                make_record(self.raw(title, "1 lb"), STORE, "Food", "Meat", "2026-10-31")
            self.assertIn("APPROXIMATE_WEIGHT", str(caught.exception))

    def test_average_weight_in_the_weight_field_is_now_caught_too(self):
        with self.assertRaises(RecordRejected):
            make_record(self.raw("Chicken Breast", "Average Weight 1 lb"),
                        STORE, "Food", "Meat", "2026-10-31")

    def test_fixed_weight_family_packs_and_multipacks_still_pass(self):
        for title, weight in (("Family Pack Ground Beef, 5 lb", "5 lb"),
                              ("Great Value Chicken Breast, 3 lb", "3 lb"),
                              ("Soda 12 Count", "12 fl oz"),
                              ("Cheese Block", "1 lb"),
                              ("Value Pack Pork Chops", "4 lb")):
            record = make_record(self.raw(title, weight), STORE, "Food", "Meat",
                                 "2026-10-31")
            self.assertEqual(record["product_title"], title)



class ManifestStrictnessTests(unittest.TestCase):
    """4. A manifest entry this tool cannot check must fail, not be filtered out."""

    def setUp(self):
        import sys
        sys.path.insert(0, str(ROOT / "tools"))
        import verify_snapshot_manifest as vsm
        self.vsm = vsm
        self.dir = tempfile.TemporaryDirectory()
        self.base = Path(self.dir.name)
        (self.base / "snaps").mkdir()
        (self.base / "snaps" / "a.json").write_text("hello", encoding="utf-8")
        import hashlib
        self.good_hash = hashlib.sha256(b"hello").hexdigest()

    def tearDown(self):
        self.dir.cleanup()

    def write(self, name, manifest):
        path = self.base / name
        path.write_text(json.dumps(manifest), encoding="utf-8")
        return path

    def run_tool(self, manifest_path):
        return self.vsm.main(["--snapshots", str(self.base / "snaps"),
                              "--manifest", str(manifest_path), "--quiet"])

    def test_one_good_entry_plus_an_entry_with_no_file_name_fails(self):
        path = self.write("nofile.json", {"files": [
            {"file": "a.json", "redacted_sha256": self.good_hash},
            {"redacted_sha256": "deadbeef"}]})
        self.assertEqual(self.run_tool(path), 2)

    def test_one_good_entry_plus_a_non_object_entry_fails(self):
        path = self.write("nonobj.json", {"files": [
            {"file": "a.json", "redacted_sha256": self.good_hash},
            "not-an-object"]})
        self.assertEqual(self.run_tool(path), 2)

    def test_the_error_states_how_many_were_declared_and_how_many_failed(self):
        path = self.write("nofile2.json", {"files": [
            {"file": "a.json", "redacted_sha256": self.good_hash},
            {"redacted_sha256": "deadbeef"}]})
        with self.assertRaises(self.vsm.ManifestError) as caught:
            self.vsm.verify(self.base / "snaps", path)
        message = str(caught.exception)
        self.assertIn("declares 2 entries", message)
        self.assertIn("1 cannot be verified", message)
        self.assertIn("entry 1: no file name", message)

    def test_a_clean_manifest_still_passes_and_reports_the_declared_count(self):
        path = self.write("good.json", {"files": [
            {"file": "a.json", "redacted_sha256": self.good_hash}]})
        self.assertEqual(self.run_tool(path), 0)
        ok, altered, missing, key, declared = self.vsm.verify(self.base / "snaps", path)
        self.assertEqual((len(ok), len(altered), len(missing), declared), (1, 0, 0, 1))
        self.assertEqual(key, "redacted_sha256")

    def test_an_altered_file_still_fails_with_exit_1(self):
        path = self.write("good2.json", {"files": [
            {"file": "a.json", "redacted_sha256": self.good_hash}]})
        (self.base / "snaps" / "a.json").write_text("tampered", encoding="utf-8")
        self.assertEqual(self.run_tool(path), 1)

    def test_a_missing_file_still_fails_with_exit_1(self):
        path = self.write("missing.json", {"files": [
            {"file": "a.json", "redacted_sha256": self.good_hash},
            {"file": "gone.json", "redacted_sha256": self.good_hash}]})
        self.assertEqual(self.run_tool(path), 1)


class _FakeRequest:
    """Minimal stand-in for urllib's Request in redirect tests."""
    full_url = "https://developer.api.walmart.com/start"
    def get_full_url(self): return self.full_url
    def has_header(self, name): return False
    def get_method(self): return "GET"
    headers = {}
    unredirected_hdrs = {}
    timeout = None
    data = None
    origin_req_host = "developer.api.walmart.com"
    unverifiable = False


class BoundedProbeTests(unittest.TestCase):
    """5. The bounded probe must honour one cumulative budget and never retry."""

    def setUp(self):
        import sys
        sys.path.insert(0, str(ROOT / "tools"))
        import opd_bounded_probe as probe
        self.probe = probe

    def test_the_request_ceiling_is_cumulative_and_refuses_the_next_one(self):
        budget = self.probe.Budget(max_requests=3)
        for n in range(3):
            budget.charge(f"call {n}", "https://example.com/x")
        with self.assertRaises(self.probe.BudgetExceeded) as caught:
            budget.charge("one too many", "https://example.com/x")
        self.assertIn("request ceiling reached", str(caught.exception))
        self.assertEqual(budget.requests, 3)

    def test_a_redirect_to_an_allowed_host_is_charged_as_a_request(self):
        budget = self.probe.Budget(max_requests=5)
        handler = self.probe._CountingRedirects(budget, self.probe.SIGNED_HOSTS)
        handler.redirect_request(
            _FakeRequest(), None, 302, "Found", {},
            "https://storage.googleapis.com/bucket/f.json.gz")
        self.assertEqual(budget.requests, 1)

    def test_a_redirect_off_the_allowlist_is_refused_not_merely_counted(self):
        """urllib forwards Authorization across hosts, so counting is not enough."""
        budget = self.probe.Budget()
        handler = self.probe._CountingRedirects(budget, self.probe.ALLOWED_HOSTS)
        with self.assertRaises(self.probe.ProbeFailure) as caught:
            handler.redirect_request(_FakeRequest(), None, 302, "Found", {},
                                     "https://evil.example/collect")
        self.assertIn("evil.example", str(caught.exception))
        self.assertIn("credentials", str(caught.exception).lower())
        self.assertEqual(budget.requests, 0, "a refused hop must not be charged")

    def test_the_redirect_handler_is_actually_installed_in_the_opener(self):
        """The handler being correct is useless if fetch() does not use it."""
        seen = {}

        def fake_build_opener(*handlers):
            seen["types"] = [type(h).__name__ for h in handlers]
            raise self.probe.ProbeFailure("stop here")

        with patch.object(self.probe, "build_opener", fake_build_opener):
            with self.assertRaises(self.probe.ProbeFailure):
                self.probe.fetch(self.probe.Budget(), "x", "https://example.com/a")
        self.assertIn("_CountingRedirects", seen["types"])

    def test_the_time_ceiling_stops_the_run(self):
        budget = self.probe.Budget(max_requests=99, max_seconds=600)
        budget.charge("first", "https://example.com/x")
        # Wind the clock back rather than sleeping for ten minutes.
        budget.started -= 601
        with self.assertRaises(self.probe.BudgetExceeded) as caught:
            budget.charge("second", "https://example.com/x")
        self.assertIn("time ceiling reached", str(caught.exception))
        self.assertEqual(budget.requests, 1, "the refused call must not be counted")

    def test_an_oversized_single_response_is_refused(self):
        budget = self.probe.Budget(max_response_bytes=10)
        with self.assertRaises(self.probe.BudgetExceeded) as caught:
            budget.record_body(11)
        self.assertIn("exceeds", str(caught.exception))

    def test_the_cumulative_traffic_ceiling_is_enforced(self):
        budget = self.probe.Budget(max_total_bytes=100, max_response_bytes=100)
        budget.record_body(60)
        with self.assertRaises(self.probe.BudgetExceeded) as caught:
            budget.record_body(60)
        self.assertIn("traffic ceiling reached", str(caught.exception))

    def test_a_503_spends_exactly_one_request_and_does_not_retry(self):
        """The production client retries three times on 503. This must not."""
        from urllib.error import HTTPError
        budget = self.probe.Budget()
        opened = []

        class Failing:
            def open(self, request, timeout=None):
                opened.append(request.full_url)
                raise HTTPError(request.full_url, 503, "Service Unavailable", {},
                                io.BytesIO(b"upstream down"))

        with patch.object(self.probe, "build_opener", lambda *a, **k: Failing()):
            with self.assertRaises(self.probe.ProbeFailure) as caught:
                self.probe.fetch(budget, "price feed listing", "https://example.com/x")
        self.assertEqual(len(opened), 1, "probe must not retry")
        self.assertEqual(budget.requests, 1)
        self.assertIn("does not retry", str(caught.exception))

    def test_the_budget_report_states_zero_retries(self):
        report = self.probe.Budget().report()
        self.assertEqual(report["retries_performed"], 0)
        self.assertTrue(report["redirects_counted_as_requests"])

    def test_the_request_log_records_hosts_not_signed_query_strings(self):
        budget = self.probe.Budget()
        budget.charge("signed catalog file",
                      "https://storage.googleapis.com/bucket/f.json.gz?X-Goog-Signature=secret")
        entry = budget.report()["requests"][0]
        self.assertEqual(entry["host"], "storage.googleapis.com")
        self.assertNotIn("Signature", json.dumps(entry))

    def test_a_signed_url_on_an_unexpected_host_is_refused(self):
        budget = self.probe.Budget()
        with self.assertRaises(self.probe.ProbeFailure) as caught:
            self.probe.signed_rows(budget, "signed file", "https://evil.example/f.json.gz", 5, "catalog")
        self.assertIn("unexpected host", str(caught.exception))

    def test_the_dry_run_plan_declares_the_bounds_and_makes_no_request(self):
        args = type("A", (), {"store": "100", "zipcode": "72712", "products": 5,
                              "max_requests": 10, "max_seconds": 600})()
        plan = self.probe.plan(args)
        self.assertEqual(plan["retries"], 0)
        self.assertEqual(plan["cumulative_bounds"]["requests"], 10)
        self.assertEqual(plan["cumulative_bounds"]["seconds"], 600)
        # Only stages the probe actually issues. An earlier version claimed a
        # token-refresh path and a locator call it never made, and this test
        # asserted those strings, which locked the false claim in.
        for stage in ("oauth", "locator", "feed listings",
                      "signed file downloads", "redirects"):
            self.assertIn(stage, plan["covers_what_it_issues"])
        self.assertNotIn("token refresh", plan["covers_what_it_issues"])
        self.assertIn("does not refresh", plan["token_refresh"])
        self.assertIn("isolated", plan["writes"])

    def test_price_field_observation_reports_absence_without_deriving(self):
        rows = [{"currentPrice": "2.99", "storeCode": "100"},
                {"storeCode": "100", "currentPrice": ""}]
        summary = self.probe.observe_price_fields(rows)
        self.assertEqual(summary["currentPrice"]["present_on_rows"], 2)
        self.assertEqual(summary["currentPrice"]["non_empty_on_rows"], 1)
        self.assertEqual(summary["unitPriceDisplay"]["absent_on_rows"], 2)


class ProbeEndToEndTests(unittest.TestCase):
    """`run()` had no test at all, which is why three defects reached the branch."""

    def setUp(self):
        import sys
        sys.path.insert(0, str(ROOT / "tools"))
        import opd_bounded_probe as probe
        self.probe = probe

    def _fake_opener(self, *, gzip_bodies=True, signed_query=True):
        """Serves the shapes walmart_collector/opd.py documents."""
        import gzip as gziplib
        probe = self.probe
        suffix = "?X-Goog-Signature=abc" if signed_query else ""
        cat_url = f"https://storage.googleapis.com/b/catalog.json.gz{suffix}"
        price_url = f"https://storage.googleapis.com/b/price.json.gz{suffix}"

        def body_for(url):
            if "/token" in url:
                return json.dumps({"access_token": "T"}).encode()
            if url.startswith(probe.BASE + probe.LOCATOR.split("?")[0]):
                return json.dumps({"status": "OK", "payload": {"accessPointList": [
                    {"fulfillmentStoreId": "100", "fulfillmentType": "INSTORE_PICKUP"}]}}).encode()
            if probe.CATALOG_FEEDS in url and "price" not in url:
                return json.dumps({"product_snapshot_data": [cat_url]}).encode()
            if probe.PRICE_FEEDS in url:
                return json.dumps({"price_avail_snapshot_data": [price_url]}).encode()
            if "catalog.json.gz" in url:
                rows = b"\n".join(json.dumps({
                    "offerId": f"o{i}", "itemId": i, "name": f"P{i}",
                    "size": "12 oz", "upc": "0001"}).encode() for i in range(5))
                return gziplib.compress(rows) if gzip_bodies else rows
            if "price.json.gz" in url:
                # Caret-delimited CSV: the shape walmart_collector/opd.py
                # actually reads for the price feed. Serving NDJSON here was
                # the test asserting its own mock rather than the client.
                header = b"offerId^storeCode^availability^currentPrice^unitPriceDisplay\n"
                rows = header + b"\n".join(
                    f"o{i}^100^AVAILABLE^1.99^(16 c/oz)".encode() for i in range(5))
                return gziplib.compress(rows) if gzip_bodies else rows
            raise AssertionError("unexpected url " + url)

        class Response:
            def __init__(self, b): self.body, self.status = b, 200
            def read(self, n=None): return self.body
            def __enter__(self): return self
            def __exit__(self, *a): pass

        class Opener:
            def open(self, request, timeout=None):
                return Response(body_for(request.full_url))

        return lambda *a, **k: Opener()

    def args(self, **over):
        base = dict(store="100", zipcode="72712", category_id="976759", products=5,
                    max_requests=10, max_seconds=600)
        base.update(over)
        return type("A", (), base)()

    def test_a_complete_run_produces_five_records_within_budget(self):
        budget = self.probe.Budget()
        with patch.dict("os.environ", {"WALMART_OPD_CLIENT_ID": "id",
                                       "WALMART_OPD_CLIENT_SECRET": "secret"}):
            with patch.object(self.probe, "build_opener", self._fake_opener()):
                result = self.probe.run(self.args(), budget)
        self.assertEqual(len(result["records"]), 5)
        self.assertTrue(result["store_confirmed_as_pickup_store"])
        self.assertTrue(all(r["price_row_found_for_this_store"] for r in result["records"]))
        self.assertEqual(result["records"][0]["currentPrice"], "1.99")
        self.assertLessEqual(budget.requests, 10)

    def test_a_signed_url_with_a_query_string_is_still_decompressed(self):
        """url.endswith('.gz') is false for every real signed URL. That bug made
        the probe return zero rows and then report a vacuous pass."""
        budget = self.probe.Budget()
        with patch.dict("os.environ", {"WALMART_OPD_CLIENT_ID": "id",
                                       "WALMART_OPD_CLIENT_SECRET": "secret"}):
            with patch.object(self.probe, "build_opener",
                              self._fake_opener(signed_query=True)):
                result = self.probe.run(self.args(), budget)
        self.assertEqual(result["store_rows_seen"], 5)
        self.assertNotEqual(result["store_rows_seen"], 0)

    def test_zero_parseable_rows_fails_rather_than_reporting_a_vacuous_pass(self):
        """Must reach the empty-parse branch, not merely raise something.

        An earlier version of this test did not patch the opener, so it issued a
        real request, passed on the resulting HTTP 400, and never exercised the
        branch it is named after. Its only assertion was that some exception
        existed, which is true of any failure.
        """
        class Empty:
            def open(self, request, timeout=None):
                class R:
                    status = 200
                    def read(self, n=None): return b"   \n  \n"
                    def __enter__(self): return self
                    def __exit__(self, *a): pass
                return R()

        budget = self.probe.Budget()
        with patch.object(self.probe, "build_opener", lambda *a, **k: Empty()):
            with self.assertRaises(self.probe.ProbeFailure) as caught:
                self.probe.signed_rows(budget, "signed catalog file",
                                       "https://storage.googleapis.com/b/f.json",
                                       5, "catalog")
        self.assertIn("no parseable catalog rows", str(caught.exception))
        self.assertIn("vacuous", str(caught.exception))

    def test_the_price_feed_is_read_as_caret_delimited_csv(self):
        """The two feeds are different formats. Asserting against the shape the
        production client documents, not against this test's own mock."""
        rows = self.probe.parse_feed_body(
            b"offerId^storeCode^availability^currentPrice\n"
            b"o1^100^AVAILABLE^1.99\n", "price")
        self.assertEqual(rows, [{"offerId": "o1", "storeCode": "100",
                                 "availability": "AVAILABLE", "currentPrice": "1.99"}])

    def test_the_catalog_feed_accepts_ndjson_and_a_json_array(self):
        nd = b'{"offerId":"o1"}\n{"offerId":"o2"}'
        arr = b'[{"offerId":"o1"},{"offerId":"o2"}]'
        self.assertEqual(len(self.probe.parse_feed_body(nd, "catalog")), 2)
        self.assertEqual(len(self.probe.parse_feed_body(arr, "catalog")), 2)

    def test_an_api_call_may_not_redirect_to_the_signed_download_host(self):
        """The allowlist is per request. A global one let a 302 on the OAuth
        call reach the multi-tenant object store carrying Basic credentials."""
        budget = self.probe.Budget()
        handler = self.probe._CountingRedirects(budget, (self.probe.API_HOST,))
        with self.assertRaises(self.probe.ProbeFailure) as caught:
            handler.redirect_request(_FakeRequest(), None, 302, "Found", {},
                                     "https://storage.googleapis.com/evil")
        self.assertIn("storage.googleapis.com", str(caught.exception))
        self.assertEqual(budget.requests, 0)

    def test_the_feed_listing_shape_matches_the_production_client(self):
        self.assertEqual(
            self.probe.feed_urls({"product_snapshot_data": ["https://x/a.gz"]},
                                 "product_snapshot_data", "catalog"),
            ["https://x/a.gz"])
        with self.assertRaises(self.probe.ProbeFailure) as caught:
            self.probe.feed_urls({"product_snapshot_data": [{"url": "https://x/a.gz"}]},
                                 "product_snapshot_data", "catalog")
        self.assertIn("no URL strings", str(caught.exception))
        with self.assertRaises(self.probe.ProbeFailure):
            self.probe.feed_urls({"wrong_key": ["x"]}, "price_avail_snapshot_data", "price")

    def test_a_receipt_is_written_even_on_an_unexpected_exception(self):
        with tempfile.TemporaryDirectory() as out:
            def boom(*a, **k):
                raise ValueError("gateway returned HTML, not JSON")
            with patch.dict("os.environ", {"WALMART_OPD_CLIENT_ID": "id",
                                           "WALMART_OPD_CLIENT_SECRET": "secret"}):
                with patch.object(self.probe, "run", boom):
                    code = self.probe.main(["--output", out, "--i-have-entitlement"])
            self.assertEqual(code, 1)
            receipt = json.loads((Path(out) / "RECEIPT.json").read_text())
            self.assertTrue(receipt["stopped_on_failure"])
            self.assertIn("ValueError", receipt["failure"])
            self.assertIn("budget", receipt)

    def test_an_http_error_body_is_not_echoed_into_the_receipt(self):
        from urllib.error import HTTPError
        budget = self.probe.Budget()
        secret_xml = b"<Error><StringToSign>SECRETSIG</StringToSign></Error>"

        class Failing:
            def open(self, request, timeout=None):
                raise HTTPError(request.full_url, 403, "Forbidden", {},
                                io.BytesIO(secret_xml))

        with patch.object(self.probe, "build_opener", lambda *a, **k: Failing()):
            with self.assertRaises(self.probe.ProbeFailure) as caught:
                self.probe.fetch(budget, "signed price file", "https://x/f.gz")
        self.assertNotIn("SECRETSIG", str(caught.exception))
        self.assertIn("withheld", str(caught.exception))


class OPDRetentionRegressionTests(unittest.TestCase):
    """Defects the independent review found in the retention correction itself."""

    def test_a_null_availability_raises_rather_than_crashing_or_blanking(self):
        from walmart_collector.opd import _to_raw, SourceError
        with self.assertRaises(SourceError) as caught:
            _to_raw(catalog_offer("X", "o", 1, "Food"),
                    {"storeCode": "100", "currentPrice": "1.99", "availability": None},
                    STORE)
        self.assertIn("no availability value", str(caught.exception))

    def test_a_missing_availability_key_raises_rather_than_silently_blanking(self):
        from walmart_collector.opd import _to_raw, SourceError
        with self.assertRaises(SourceError):
            _to_raw(catalog_offer("X", "o", 1, "Food"),
                    {"storeCode": "100", "currentPrice": "1.99"}, STORE)

    def test_unresolved_offers_do_not_accumulate_across_runs(self):
        def files(url, kind):
            category = "Food" if "976759" in url else "Beauty"
            if kind == "catalog":
                return iter([catalog_offer("Orphan", f"{category}-orphan", 300, category),
                             catalog_offer("Priced", f"{category}-ok", 301, category)])
            return iter([dict(offerId=f"{category}-ok", storeCode=STORE.store_id,
                              availability="AVAILABLE", currentPrice="1.50")])

        with tempfile.TemporaryDirectory() as base:
            with patch("walmart_collector.opd.signed_records", files):
                source = WalmartOPDSnapshotSource(FakeClient(), Path(base) / "cache",
                                                  MAP, page_size=10)
                storage = LocalStorage(Path(base) / "data")
                counts = []
                for _ in range(3):
                    Collector(storage, source, CATEGORIES, min_products=1,
                              trial=True).run(STORE)
                    counts.append(len(source.unresolved_offers))
        self.assertEqual(counts, [2, 2, 2], "a reused source must not accumulate")

    def test_unresolved_offers_reach_the_run_report(self):
        def files(url, kind):
            category = "Food" if "976759" in url else "Beauty"
            if kind == "catalog":
                return iter([catalog_offer("Orphan", f"{category}-orphan", 300, category),
                             catalog_offer("Priced", f"{category}-ok", 301, category)])
            return iter([dict(offerId=f"{category}-ok", storeCode=STORE.store_id,
                              availability="AVAILABLE", currentPrice="1.50")])

        with tempfile.TemporaryDirectory() as base:
            with patch("walmart_collector.opd.signed_records", files):
                source = WalmartOPDSnapshotSource(FakeClient(), Path(base) / "cache",
                                                  MAP, page_size=10)
                result = Collector(LocalStorage(Path(base) / "data"), source,
                                   CATEGORIES, min_products=1, trial=True).run(STORE)
        unresolved = result["report"]["unresolved_offers"]
        self.assertEqual(unresolved["count"], 2)
        self.assertIn("store assortment membership unestablished",
                      " ".join(unresolved["by_reason"]))

    def test_an_offer_with_no_usable_url_is_recorded_not_silently_dropped(self):
        def files(url, kind):
            category = "Food" if "976759" in url else "Beauty"
            if kind == "catalog":
                bad = catalog_offer("NoUrl", f"{category}-bad", 400, category)
                bad["productUrlText"] = ""
                return iter([bad, catalog_offer("Good", f"{category}-ok", 401, category)])
            return iter([dict(offerId=f"{category}-bad", storeCode=STORE.store_id,
                              availability="AVAILABLE", currentPrice="1.00"),
                         dict(offerId=f"{category}-ok", storeCode=STORE.store_id,
                              availability="AVAILABLE", currentPrice="1.50")])

        with tempfile.TemporaryDirectory() as base:
            with patch("walmart_collector.opd.signed_records", files):
                source = WalmartOPDSnapshotSource(FakeClient(), Path(base) / "cache",
                                                  MAP, page_size=10)
                result = Collector(LocalStorage(Path(base) / "data"), source,
                                   CATEGORIES, min_products=1, trial=True).run(STORE)
        reasons = " ".join(result["report"]["unresolved_offers"]["by_reason"])
        self.assertIn("no usable product URL", reasons)


class CoverageGateAtPublicationTests(unittest.TestCase):
    """The gate must not be defeatable by mutating the collector after construction."""

    def test_flipping_trial_off_after_construction_still_cannot_publish_full(self):
        with tempfile.TemporaryDirectory() as base:
            source = WalmartOPDSnapshotSource(FakeClient(), Path(base) / "cache", MAP)
            collector = Collector(LocalStorage(Path(base) / "data"), source,
                                  CATEGORIES, min_products=1, trial=True)
            collector.trial = False
            with self.assertRaises(ValidationFailure):
                collector.run(STORE)

    def test_swapping_in_an_unattested_source_after_construction_is_caught(self):
        with tempfile.TemporaryDirectory() as base:
            collector = Collector(LocalStorage(Path(base) / "data"),
                                  FixtureSource(ROOT / "fixtures"),
                                  CATEGORIES, min_products=1)
            collector.source = WalmartOPDSnapshotSource(
                FakeClient(), Path(base) / "cache", MAP)
            with self.assertRaises(ValidationFailure):
                collector.run(STORE)


class CompositeDelegationTests(unittest.TestCase):
    """A composite must not swallow what the runner asks of its spine.

    `--source composite --spine opd` is the CLI's default composite, and on that
    path the spine's unresolved record was absent from every run report and the
    spine accumulated across runs, because CompositeSource exposed neither
    attribute. The same defect that was fixed inside the spine, reintroduced by
    wrapping it.
    """

    def _feed(self, url, kind):
        category = "Food" if "976759" in url else "Beauty"
        if kind == "catalog":
            return iter([catalog_offer("Orphan", f"{category}-orphan", 500, category),
                         catalog_offer("Priced", f"{category}-ok", 501, category)])
        return iter([dict(offerId=f"{category}-ok", storeCode=STORE.store_id,
                          availability="AVAILABLE", currentPrice="1.50")])

    def _composite(self, base):
        from walmart_collector.composition import CompositeSource, unavailable_crawl
        spine = WalmartOPDSnapshotSource(FakeClient(), Path(base) / "cache",
                                         MAP, page_size=10)
        return CompositeSource(spine, "opd", [unavailable_crawl("blocked")])

    def test_the_composite_exposes_the_spines_unresolved_offers(self):
        with tempfile.TemporaryDirectory() as base:
            with patch("walmart_collector.opd.signed_records", self._feed):
                source = self._composite(base)
                result = Collector(LocalStorage(Path(base) / "data"), source,
                                   CATEGORIES, min_products=1, trial=True).run(STORE)
        self.assertEqual(result["report"]["unresolved_offers"]["count"], 2)

    def test_the_composite_does_not_accumulate_across_runs(self):
        with tempfile.TemporaryDirectory() as base:
            with patch("walmart_collector.opd.signed_records", self._feed):
                source = self._composite(base)
                storage = LocalStorage(Path(base) / "data")
                counts = []
                for _ in range(3):
                    Collector(storage, source, CATEGORIES, min_products=1,
                              trial=True).run(STORE)
                    counts.append(len(source.unresolved_offers))
        self.assertEqual(counts, [2, 2, 2])

    def test_composite_provenance_is_per_run_not_cumulative(self):
        with tempfile.TemporaryDirectory() as base:
            with patch("walmart_collector.opd.signed_records", self._feed):
                source = self._composite(base)
                storage = LocalStorage(Path(base) / "data")
                traced = []
                for _ in range(3):
                    Collector(storage, source, CATEGORIES, min_products=1,
                              trial=True).run(STORE)
                    values = source.provenance_report()["values_by_field_and_source"]
                    traced.append(sum(sum(d.values()) for d in values.values()))
        # products_traced is identity-keyed and constant either way, so it
        # cannot detect the defect. The per-source value counter does: without
        # the reset it rises run on run.
        self.assertEqual(len(set(traced)), 1,
                         f"provenance must not accumulate across runs: {traced}")
        self.assertGreater(traced[0], 0, "the counter must actually be counting")


class UnguardedFixTests(unittest.TestCase):
    """Fixes that mutation testing showed no test would have caught.

    Reverting the pre-artifact gate, and reverting the manifest hash type
    check, both left the whole suite green. A fix no test defends is a fix that
    silently regresses.
    """

    def test_a_refused_full_publication_writes_no_artifacts_at_all(self):
        """Gating only the pointer still left data.json, report.json and
        manifest.json under published/, including a report reading scope=full
        with source_coverage_attested=false."""
        with tempfile.TemporaryDirectory() as base:
            root = Path(base) / "data"
            storage = LocalStorage(root)
            # The source must stop attesting DURING the run. Swapping it before
            # run() only trips the entry gate, which leaves the pre-artifact
            # check unexercised: reverting that line still left this test green
            # until it was written this way.
            class StopsAttesting:
                source_mode = "synthetic_fixture_stops_attesting"
                coverage_attested = True

                def __init__(self):
                    self._inner = FixtureSource(ROOT / "fixtures")

                def fetch(self, store, category, url, cursor):
                    page = self._inner.fetch(store, category, url, cursor)
                    self.coverage_attested = False
                    return page

            # Real configured categories, so the fixture lookup resolves.
            from walmart_collector.config import categories_from_csv
            real_categories = categories_from_csv(ROOT / "config/categories.csv")[:2]
            collector = Collector(storage, StopsAttesting(), real_categories,
                                  min_products=1)
            with self.assertRaises(ValidationFailure):
                collector.run(STORE)
            published = root / "published"
            leaked = sorted(str(q.relative_to(root)) for q in published.rglob("*")
                            if q.is_file()) if published.exists() else []
            self.assertEqual(leaked, [], f"nothing may be written: found {leaked}")

    def test_a_non_string_hash_value_is_refused_not_reported_as_altered(self):
        import sys
        sys.path.insert(0, str(ROOT / "tools"))
        import verify_snapshot_manifest as vsm
        import hashlib
        with tempfile.TemporaryDirectory() as base:
            snaps = Path(base) / "snaps"; snaps.mkdir()
            (snaps / "a.json").write_text("hello", encoding="utf-8")
            good = hashlib.sha256(b"hello").hexdigest()
            for label, value in (("int", 12345), ("list", ["x"]), ("bool", True),
                                 ("dict", {"a": 1}), ("float", 1.5), ("none", None)):
                manifest = Path(base) / f"m_{label}.json"
                manifest.write_text(json.dumps({"files": [
                    {"file": "a.json", "redacted_sha256": good},
                    {"file": "b.json", "redacted_sha256": value}]}), encoding="utf-8")
                code = vsm.main(["--snapshots", str(snaps), "--manifest",
                                 str(manifest), "--quiet"])
                self.assertEqual(code, 2, f"{label} hash must be unverifiable, not altered")


if __name__ == "__main__":
    unittest.main()
