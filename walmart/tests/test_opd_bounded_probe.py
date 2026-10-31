"""B1 and B2 of REVIEW_ACTIONS_2026-10-31.md, driven through the real probe code
with a fake opener and, for the abandoned stage, a really blocked thread."""
import gzip
import io
import json
import os
import sys
import tempfile
import threading
import time
import unittest
from email.message import Message
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import opd_bounded_probe as probe

CAT_URL = "https://storage.googleapis.com/b/2026-10-31/catalog.json.gz?X-Goog-Signature=SIGNEDSECRET"
PRICE_URL = "https://storage.googleapis.com/b/2026-10-31/price.csv.gz?X-Goog-Signature=SIGNEDSECRET"
ENV = {"WALMART_OPD_CLIENT_ID": "id", "WALMART_OPD_CLIENT_SECRET": "secret"}


def catalog(n=5, start=0):
    return gzip.compress(b"\n".join(json.dumps(
        {"offerId": f"o{i}", "itemId": i, "name": f"P{i}", "size": "12 oz",
         "upc": "0001"}).encode() for i in range(start, start + n)))


def prices(rows):
    return gzip.compress(("offerId^storeCode^availability^currentPrice^unitPriceDisplay\n"
                          + "\n".join(rows)).encode())


def five_for(store="100", start=0):
    return prices([f"o{i}^{store}^AVAILABLE^1.99^(16 c/oz)" for i in range(start, start + 5)])


class Response:
    status = 200

    def __init__(self, body, on_read=None, headers=None):
        self.stream, self.on_read = io.BytesIO(body), on_read
        self.headers = headers or {}

    def read(self, n=None):
        if self.on_read:
            self.on_read()
        return self.stream.read(n)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass


def opener(catalog_body=None, price_body=None, on_read=None, locator_store="100"):
    catalog_body = catalog() if catalog_body is None else catalog_body
    price_body = five_for() if price_body is None else price_body

    def body_for(url):
        if "/token" in url:
            return json.dumps({"access_token": "BEARERSECRET"}).encode()
        if probe.LOCATOR.split("?")[0] in url:
            return json.dumps({"payload": {"accessPointList": [
                {"fulfillmentStoreId": locator_store, "fulfillmentType": "INSTORE_PICKUP"}]}}).encode()
        if probe.PRICE_FEEDS in url:
            return json.dumps({"price_avail_snapshot_data": [PRICE_URL],
                               "snapshot_time": "2026-10-31T02:00:00Z"}).encode()
        if probe.CATALOG_FEEDS in url:
            return json.dumps({"product_snapshot_data": [CAT_URL]}).encode()
        if "catalog.json.gz" in url:
            return catalog_body
        if "price.csv.gz" in url:
            return price_body
        raise AssertionError(url)

    class Opener:
        def open(self, request, timeout=None):
            return Response(body_for(request.full_url), on_read,
                            {"ETag": '"abc"', "Last-Modified": "Sat, 31 Oct 2026 02:00:00 GMT"})

    return lambda *a, **k: Opener()


class Base(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.out = Path(self.dir.name) / "out"
        env = patch.dict(os.environ, ENV)
        env.start()
        self.addCleanup(env.stop)

    def main(self, built_opener, *extra):
        with patch.object(probe, "build_opener", built_opener):
            with patch("sys.stdout", io.StringIO()):
                code = probe.main(["--output", str(self.out), "--i-have-entitlement", *extra])
        return code, json.loads((self.out / "RECEIPT.json").read_text())


class ByteAccountingTests(Base):
    def test_a_refused_response_is_counted_as_received(self):
        budget = probe.Budget(max_response_bytes=10)
        with self.assertRaises(probe.BudgetExceeded):
            probe.read_counted(budget, "x", io.BytesIO(b"x" * 11))
        self.assertEqual(budget.bytes, 11)

    def test_bytes_stop_at_the_chunk_that_crossed_the_line(self):
        budget = probe.Budget(max_response_bytes=probe.READ_CHUNK)
        with self.assertRaises(probe.BudgetExceeded):
            probe.read_counted(budget, "x", io.BytesIO(b"x" * probe.READ_CHUNK * 10))
        self.assertEqual(budget.bytes, probe.READ_CHUNK * 2)

    def test_the_traffic_ceiling_counts_the_refused_body_too(self):
        budget = probe.Budget(max_total_bytes=100, max_response_bytes=100)
        budget.record_body(60)
        with self.assertRaises(probe.BudgetExceeded):
            budget.record_body(60)
        self.assertEqual(budget.bytes, 120)

    def test_an_error_body_is_counted_and_recorded_in_the_captures(self):
        budget = probe.Budget()

        class Failing:
            def open(self, request, timeout=None):
                raise HTTPError(request.full_url, 503, "Down", {}, io.BytesIO(b"e" * 100))

        with patch.object(probe, "build_opener", lambda *a, **k: Failing()):
            with self.assertRaises(probe.ProbeFailure):
                probe.fetch(budget, "x", "https://example.com/a")
        self.assertEqual(budget.bytes, 100)
        self.assertEqual(budget.captures[0]["status"], 503)
        self.assertEqual(budget.captures[0]["bytes"], 100)

    def test_a_huge_error_body_is_not_read_in_full(self):
        budget = probe.Budget()
        body = b"e" * (probe.MAX_ERROR_BODY_BYTES * 3)

        class Failing:
            def open(self, request, timeout=None):
                raise HTTPError(request.full_url, 503, "Down", {}, io.BytesIO(body))

        with patch.object(probe, "build_opener", lambda *a, **k: Failing()):
            with self.assertRaises(probe.ProbeFailure):
                probe.fetch(budget, "x", "https://example.com/a")
        self.assertEqual(budget.bytes, probe.MAX_ERROR_BODY_BYTES)

    def test_a_redirect_body_is_counted_before_urllib_reads_it(self):
        budget = probe.Budget(max_requests=5)
        handler = probe._CountingRedirects(budget, ("example.com",))

        class Parent:
            def open(self, request, timeout=None):
                return "followed"

        handler.parent = Parent()
        headers = Message()
        headers["Location"] = "https://example.com/next"
        request = Request("https://example.com/first")
        request.timeout = 5
        result = handler.http_error_302(request, io.BytesIO(b"r" * 500), 302, "Found", headers)
        self.assertEqual(result, "followed")
        self.assertEqual(budget.bytes, 500)
        self.assertEqual(budget.requests, 1)

    def test_every_redirect_status_goes_through_the_counted_path(self):
        handler = probe._CountingRedirects
        for name in ("http_error_301", "http_error_303", "http_error_307", "http_error_308"):
            self.assertIs(getattr(handler, name), handler.http_error_302, name)


class DecompressionTests(unittest.TestCase):
    def test_a_compression_bomb_stops_near_the_ceiling(self):
        budget = probe.Budget(max_decompressed_bytes=probe.READ_CHUNK * 3)
        bomb = gzip.compress(b"\0" * (64 * 1024 * 1024))
        self.assertLess(len(bomb), 200_000)
        with self.assertRaisesRegex(probe.BudgetExceeded, "decompression ceiling"):
            probe.gunzip_bounded(budget, "x", bomb)
        self.assertLessEqual(budget.decompressed_bytes, probe.READ_CHUNK * 4)

    def test_the_ceiling_is_cumulative_across_files(self):
        budget = probe.Budget(max_decompressed_bytes=1500)
        probe.gunzip_bounded(budget, "x", gzip.compress(b"a" * 1000))
        with self.assertRaises(probe.BudgetExceeded):
            probe.gunzip_bounded(budget, "y", gzip.compress(b"a" * 1000))

    def test_the_clock_is_checked_while_expanding(self):
        budget = probe.Budget(max_seconds=600)
        budget.start()
        budget.started -= 601
        with self.assertRaisesRegex(probe.BudgetExceeded, "time ceiling"):
            probe.gunzip_bounded(budget, "x", gzip.compress(b"a"))

    def test_multi_member_and_exact_content_survive(self):
        body = gzip.compress(b"one\n") + gzip.compress(b"two\n")
        self.assertEqual(probe.gunzip_bounded(probe.Budget(), "x", body), b"one\ntwo\n")
        large = os.urandom(probe.READ_CHUNK * 3)
        self.assertEqual(probe.gunzip_bounded(probe.Budget(), "x", gzip.compress(large)), large)

    def test_a_truncated_stream_is_a_failure_not_a_short_result(self):
        body = gzip.compress(os.urandom(5000))[:-100]
        with self.assertRaisesRegex(probe.ProbeFailure, "truncated"):
            probe.gunzip_bounded(probe.Budget(), "x", body)

    def test_garbage_is_a_failure(self):
        with self.assertRaisesRegex(probe.ProbeFailure, "not readable as gzip"):
            probe.gunzip_bounded(probe.Budget(), "x", b"\x1f\x8bnot really")


class DeadlineTests(Base):
    def test_the_clock_is_checked_between_chunks_of_a_response(self):
        budget = probe.Budget(max_seconds=600)
        budget.start()
        budget.started -= 601
        stream = io.BytesIO(b"x" * 10)
        with self.assertRaisesRegex(probe.BudgetExceeded, "time ceiling"):
            probe.read_counted(budget, "x", stream)
        self.assertEqual(stream.tell(), 0)

    def test_a_run_finishing_past_the_ceiling_fails(self):
        """The reviewer's case: six requests, 601 seconds, exit 0."""
        budget = probe.Budget(max_seconds=600)
        calls = []

        def slow_last_read():
            calls.append(1)
            if len(calls) == 12:  # the final download's closing read
                budget.started -= 601

        args = type("A", (), dict(store="100", zipcode="72712", category_id="1",
                                  products=5))()
        with patch.object(probe, "build_opener", opener(on_read=slow_last_read)):
            outcome, failure = probe.supervise(args, budget, {})
        self.assertIn("time ceiling reached", failure)

    def test_the_request_timeout_shrinks_with_the_time_left(self):
        budget = probe.Budget(max_seconds=30)
        budget.start()
        seen = {}

        class Capture:
            def open(self, request, timeout=None):
                seen["timeout"] = timeout
                return Response(b"{}")

        with patch.object(probe, "build_opener", lambda *a, **k: Capture()):
            probe.fetch(budget, "x", "https://example.com/a")
        self.assertLessEqual(seen["timeout"], 30)
        self.assertGreater(seen["timeout"], 25)

    def test_the_timeout_never_exceeds_the_per_request_cap(self):
        budget = probe.Budget()
        seen = {}

        class Capture:
            def open(self, request, timeout=None):
                seen["timeout"] = timeout
                return Response(b"{}")

        with patch.object(probe, "build_opener", lambda *a, **k: Capture()):
            probe.fetch(budget, "x", "https://example.com/a")
        self.assertEqual(seen["timeout"], probe.REQUEST_TIMEOUT)

    def test_a_blocked_stage_is_abandoned_and_the_receipt_is_still_written(self):
        release = threading.Event()
        self.addCleanup(release.set)

        def blocks(args, budget, evidence):
            evidence["locator_response"] = {"seen": True}
            release.wait(30)
            budget.charge("after the deadline", "https://example.com/x")

        started = time.monotonic()
        with patch.object(probe, "run", blocks):
            budget = probe.Budget(max_seconds=0.2, finalize_seconds=15)
            outcome, failure = probe.supervise(self.args(), budget, {})
        self.assertLess(time.monotonic() - started, 5)
        self.assertIsNone(outcome)
        self.assertIn("abandoned", failure)
        self.assertTrue(budget.stopped)
        release.set()

    def args(self):
        return type("A", (), dict(store="100", zipcode="72712", category_id="1", products=5))()

    def test_an_abandoned_worker_cannot_spend_after_the_stop(self):
        budget = probe.Budget()
        budget.stop()
        with self.assertRaises(probe.BudgetExceeded):
            budget.charge("late", "https://example.com/x")
        self.assertEqual(budget.requests, 0)

    def test_the_finalization_reserve_comes_out_of_the_ceiling(self):
        budget = probe.Budget(max_seconds=600, finalize_seconds=probe.FINALIZE_SECONDS)
        self.assertEqual(budget.work_seconds, 585)
        short = probe.Budget(max_seconds=10, finalize_seconds=probe.FINALIZE_SECONDS)
        self.assertEqual(short.work_seconds, 9)

    def test_finalization_past_the_hard_limit_keeps_the_receipt_and_says_what_it_skipped(self):
        budget = probe.Budget(max_seconds=600)
        budget.start()
        budget.started -= 601
        probe.finalize(self.out, {"probe": "x"}, {"locator_response": {"a": 1}}, budget)
        receipt = json.loads((self.out / "RECEIPT.json").read_text())
        self.assertEqual(receipt["evidence"]["skipped_at_deadline"], ["locator_response"])
        self.assertFalse((self.out / "evidence" / "locator_response.json").exists())

    def test_the_end_to_end_past_ceiling_run_exits_one_and_keeps_what_it_found(self):
        real = probe.run

        def finishes_late(args, budget, evidence):
            outcome = real(args, budget, evidence)
            budget.started -= 601
            return outcome

        with patch.object(probe, "run", finishes_late):
            code, receipt = self.main(opener())
        self.assertEqual(code, probe.EXIT_FAILURE)
        self.assertTrue(receipt["stopped_on_failure"])
        self.assertEqual(receipt["result_status"], "INCOMPLETE")
        self.assertFalse(receipt["result"]["complete"])
        self.assertEqual(receipt["result"]["matched_records"], 5)


class TransportIsNotAResultTests(Base):
    def test_a_full_matched_sample_exits_zero(self):
        code, receipt = self.main(opener())
        self.assertEqual(code, probe.EXIT_OK)
        self.assertEqual(receipt["result_status"], "COMPLETE")
        self.assertEqual(receipt["result"]["matched_records"], 5)
        self.assertTrue(receipt["result"]["checks"]["every_price_row_matches_requested_store"])

    def test_every_price_row_at_another_store_is_incomplete_and_no_flag_is_true(self):
        """The reviewer's case: exit 0, zero records, flag true."""
        code, receipt = self.main(opener(price_body=five_for("999")))
        result = receipt["result"]
        self.assertEqual(code, probe.EXIT_INCOMPLETE)
        self.assertEqual(receipt["result_status"], "INCOMPLETE")
        self.assertEqual(result["status"], "INCOMPLETE")
        self.assertEqual(result["matched_records"], 0)
        self.assertEqual(result["checks"], {
            "every_price_row_matches_requested_store": False,
            "unit_price_display_present_on_any_row": False,
            "upc_leading_zeros_preserved": False,
            "any_offer_terms_field_observed": False})
        self.assertIn("no price row for store 100 among 5 rows read",
                      result["incomplete_reasons"])

    def test_a_partial_match_is_incomplete_and_says_how_many(self):
        code, receipt = self.main(opener(price_body=prices(["o1^100^AVAILABLE^1.99^"])))
        self.assertEqual(code, probe.EXIT_INCOMPLETE)
        self.assertEqual(receipt["result"]["matched_records"], 1)
        self.assertIn("1 of 5 requested", receipt["result"]["incomplete_reasons"][0])
        self.assertIn("1 of 1", receipt["result"]["incomplete_reasons"][0])

    def test_a_mixed_store_file_is_honestly_not_all_matching(self):
        rows = [f"o{i}^100^AVAILABLE^1.99^" for i in range(5)] + ["o9^999^AVAILABLE^1.99^"]
        code, receipt = self.main(opener(price_body=prices(rows)))
        self.assertEqual(code, probe.EXIT_OK)
        checks = receipt["result"]["checks"]
        self.assertFalse(checks["every_price_row_matches_requested_store"])

    def test_matches_deep_in_the_feed_are_found(self):
        """Offers past the first five catalog rows and the first hundred price
        rows were reported as missing."""
        far = 1000
        noise = [f"x{i}^999^AVAILABLE^1.00^" for i in range(400)]
        price_body = prices(noise + [f"o{i}^100^AVAILABLE^1.99^" for i in range(far, far + 5)])
        catalog_body = gzip.compress(b"\n".join(json.dumps(
            {"offerId": f"o{i}", "upc": "1"}).encode() for i in range(far + 5)))
        code, receipt = self.main(opener(catalog_body, price_body))
        self.assertEqual(code, probe.EXIT_OK)
        self.assertEqual(receipt["result"]["matched_records"], 5)
        self.assertEqual(receipt["result"]["feed_coverage"]["price_rows_read"], 405)
        self.assertEqual(receipt["result"]["feed_coverage"]["catalog_rows_read"], far + 5)

    def test_the_price_file_is_scanned_past_any_prefix_of_store_rows(self):
        """Hundreds of this store's rows for other offers must not hide the match."""
        rows = [f"y{i}^100^AVAILABLE^1.00^" for i in range(300)]
        rows += [f"o{i}^100^AVAILABLE^1.99^" for i in range(5)]
        code, receipt = self.main(opener(price_body=prices(rows)))
        self.assertEqual(code, probe.EXIT_OK)
        self.assertEqual(receipt["result"]["store_rows_seen"], 305)

    def test_a_numeric_upc_fails_the_leading_zero_check(self):
        catalog_body = gzip.compress(b"\n".join(json.dumps(
            {"offerId": f"o{i}", "upc": 1234}).encode() for i in range(5)))
        _, receipt = self.main(opener(catalog_body))
        self.assertFalse(receipt["result"]["checks"]["upc_leading_zeros_preserved"])

    def test_offer_terms_are_looked_for_rather_than_stated(self):
        rows = ["offerId^storeCode^promoDescription"] + [f"o{i}^100^Save" for i in range(5)]
        _, receipt = self.main(opener(price_body=gzip.compress("\n".join(rows).encode())))
        self.assertTrue(receipt["result"]["checks"]["any_offer_terms_field_observed"])

    def test_not_established_states_the_limits_of_the_evidence(self):
        _, receipt = self.main(opener())
        text = " ".join(receipt["result"]["not_established"])
        for phrase in ("missing from the feed", "fulfilment of every price row",
                       "regular or a sale price"):
            self.assertIn(phrase, text)


class EvidenceTests(Base):
    def test_listings_rows_and_snapshot_identity_are_preserved(self):
        code, receipt = self.main(opener())
        evidence = self.out / "evidence"
        self.assertEqual(sorted(p.stem for p in evidence.iterdir()),
                         ["catalog_listing", "catalog_rows", "locator_response",
                          "price_listing", "price_rows"])
        listing = json.loads((evidence / "price_listing.json").read_text())
        self.assertEqual(listing["snapshot_time"], "2026-10-31T02:00:00Z")
        self.assertEqual(listing["price_avail_snapshot_data"],
                         ["https://storage.googleapis.com/b/2026-10-31/price.csv.gz"])
        rows = json.loads((evidence / "price_rows.json").read_text())
        self.assertEqual(len(rows["rows_for_this_store"]), 5)
        captures = {c["label"]: c for c in receipt["budget"]["captures"]}
        signed = captures["signed price file"]
        self.assertEqual(signed["path"], "/b/2026-10-31/price.csv.gz")
        self.assertEqual(signed["response_headers"]["ETag"], '"abc"')
        self.assertRegex(signed["captured_utc"], r"^2\d{3}-\d\d-\d\dT")
        self.assertEqual(len(signed["sha256"]), 64)

    def test_the_written_hashes_match_the_files(self):
        import hashlib
        _, receipt = self.main(opener())
        for name, entry in receipt["evidence"]["written"].items():
            payload = (self.out / "evidence" / f"{name}.json").read_bytes()
            self.assertEqual(hashlib.sha256(payload).hexdigest(), entry["sha256"])
            self.assertEqual(len(payload), entry["bytes"])

    def test_no_credential_survives_anywhere_in_the_output(self):
        self.main(opener())
        for path in self.out.rglob("*"):
            if path.is_file():
                text = path.read_text()
                for secret in ("SIGNEDSECRET", "X-Goog-Signature", "BEARERSECRET"):
                    self.assertNotIn(secret, text, str(path))

    def test_partial_evidence_survives_a_failed_run(self):
        code, receipt = self.main(opener(locator_store="555"))
        self.assertEqual(code, probe.EXIT_FAILURE)
        self.assertIn("locator_response", receipt["evidence"]["written"])

    def test_sanitize_drops_token_fields_and_query_strings(self):
        clean = probe.sanitize({"access_token": "t", "a": ["https://x/y.gz?sig=1"],
                                "Authorization": "b", "n": 3})
        self.assertEqual(clean, {"a": ["https://x/y.gz"], "n": 3})


class ScanTests(unittest.TestCase):
    def test_keep_and_limit_compose(self):
        stats = {}
        body = b"\n".join(json.dumps({"offerId": f"o{i}"}).encode() for i in range(10))
        rows = probe.parse_feed_body(body, "catalog", 2, stats=stats,
                                     keep=lambda r: r["offerId"] in ("o3", "o5", "o7"))
        self.assertEqual([r["offerId"] for r in rows], ["o3", "o5"])
        self.assertEqual(stats["rows_read"], 6)
        self.assertTrue(stats["stopped_at_limit"])

    def test_rows_read_but_none_kept_is_not_an_empty_parse(self):
        budget = probe.Budget()

        class One:
            def open(self, request, timeout=None):
                return Response(b'{"offerId":"o1"}')

        with patch.object(probe, "build_opener", lambda *a, **k: One()):
            rows = probe.signed_rows(budget, "x", "https://storage.googleapis.com/b/f.json",
                                     None, "catalog", keep=lambda r: False)
        self.assertEqual(rows, [])

    def test_the_clock_is_checked_while_parsing(self):
        ticks = []
        body = b"\n".join(b'{"a":1}' for _ in range(5000))
        probe.parse_feed_body(body, "catalog", check=lambda: ticks.append(1))
        self.assertEqual(len(ticks), 2)


if __name__ == "__main__":
    unittest.main()
