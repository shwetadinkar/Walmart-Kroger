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

    def test_a_price_on_an_unavailable_row_is_not_reported_as_current(self):
        # A price carried on a non-AVAILABLE row is not one a shopper can pay.
        record = _to_raw(
            catalog_offer("Stale", "s", 7, "Food"),
            dict(availability="OUT_OF_STOCK", currentPrice="9.99",
                 unitPriceDisplay="(1 c/oz)", storeCode="100"), STORE)
        self.assertEqual(record["regular_price"], "")
        self.assertEqual(record["ppm"], "")
        self.assertEqual(record["product_title"], "Stale")

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


if __name__ == "__main__":
    unittest.main()


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

    def test_a_redirect_hop_is_charged_as_a_request(self):
        budget = self.probe.Budget(max_requests=2)
        handler = self.probe._CountingRedirects(budget)
        budget.charge("initial", "https://example.com/a")
        # The redirect itself must consume the remaining allowance.
        try:
            handler.redirect_request(None, None, 302, "Found", {}, "https://example.com/b")
        except Exception:
            pass
        self.assertEqual(budget.requests, 2)
        with self.assertRaises(self.probe.BudgetExceeded):
            budget.charge("after redirect", "https://example.com/c")

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
            self.probe.signed_rows(budget, "signed file", "https://evil.example/f.json.gz", 5)
        self.assertIn("unexpected host", str(caught.exception))

    def test_the_dry_run_plan_declares_the_bounds_and_makes_no_request(self):
        args = type("A", (), {"store": "100", "zipcode": "72712", "products": 5,
                              "max_requests": 10, "max_seconds": 600})()
        plan = self.probe.plan(args)
        self.assertEqual(plan["retries"], 0)
        self.assertEqual(plan["cumulative_bounds"]["requests"], 10)
        self.assertEqual(plan["cumulative_bounds"]["seconds"], 600)
        for stage in ("oauth", "token refresh", "locator", "metadata",
                      "signed file downloads", "redirects"):
            self.assertIn(stage, plan["covers"])
        self.assertIn("isolated", plan["writes"])

    def test_price_field_observation_reports_absence_without_deriving(self):
        rows = [{"currentPrice": "2.99", "storeCode": "100"},
                {"storeCode": "100", "currentPrice": ""}]
        summary = self.probe.observe_price_fields(rows)
        self.assertEqual(summary["currentPrice"]["present_on_rows"], 2)
        self.assertEqual(summary["currentPrice"]["non_empty_on_rows"], 1)
        self.assertEqual(summary["unitPriceDisplay"]["absent_on_rows"], 2)
