import csv
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from walmart_collector.brightdata_automatic import (
    HTTPBrightData, BrightDataError, LocalStore,
    approved_input_categories, execute, main,
)

STORE = {"store_id": "100", "zipcode": "72712", "store_name": "Walmart Supercenter #100",
         "store_location": "406 S Walton Blvd, Bentonville, AR 72712", "store_logo": ""}


def product(pid, pickup=True):
    return {
        "product_id": str(pid), "url": f"https://www.walmart.com/ip/Synthetic-Product/{pid}",
        "product_name": f"Synthetic product {pid} 12 oz", "store_id": "100",
        "pickup_store_id": "100", "retailer_store_id": "100",
        "zip_code": "72712", "pickup_zipcode": "72712", "seller": "Walmart.com",
        "retailer": "Walmart.com", "root_category_url": "https://www.walmart.com/cp/food/976759",
        "category_name": "Pantry", "specifications": [{"name": "Net content statement", "value": "12 oz"}],
        "pickup_extras": {"location": "Bentonville S Walton Blvd", "availability_status": "IN_STOCK" if pickup else "OUT_OF_STOCK"},
        "available_for_pickup": pickup, "final_price": 2.19, "timestamp": "2026-10-23T00:00:00Z",
        "upc": "012345678905", "main_image": "https://example.com/test.png",
    }


class API:
    def __init__(self, records=None, states=None):
        self.records = [product(1234)] if records is None else records
        self.states = list(states or ["ready"])
        self.trigger_calls = 0
        self.snapshot_calls = 0

    def trigger(self, dataset, inputs, max_records):
        self.trigger_calls += 1
        self.last_args = (dataset, inputs, max_records)
        return "s_test123456"

    def progress(self, snapshot_id):
        if len(self.states) > 1:
            return self.states.pop(0)
        return self.states[0]

    def snapshot(self, snapshot_id):
        self.snapshot_calls += 1
        return self.records


class AutomaticTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = LocalStore(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_snapshot_no_trigger_writes_private_22_fields(self):
        api = API(records=[product(1234), product(4567, pickup=False)])
        report = execute(STORE, api, self.store, snapshot_id="s_test123456", poll_seconds=0)
        self.assertEqual(report["record_count"], 2)
        self.assertEqual(report["confirmed_local_prices"], 0)
        self.assertEqual(api.trigger_calls, 0)
        self.assertIsNone(self.store.get("published/100/latest.json"))
        rows = json.loads(self.store.get(report["run"] + "/data_22_fields.json"))
        self.assertEqual(len(rows), 2)
        self.assertEqual(len(rows[0]), 22)
        self.assertEqual(rows[0]["regular_price"], "")
        self.assertEqual(rows[1]["unit_price"], "")
        self.assertEqual(rows[1]["ppm"], "")
        self.assertEqual(len(json.loads(self.store.get("brightdata-trials/100/history.json"))["products"]), 2)

    def test_progress_pending_resumes_without_triggering_another_job(self):
        first = API(states=["running"])
        pending = execute(STORE, first, self.store, trigger_inputs=[{"url": "https://www.walmart.com/cp/food/976759"}],
                          max_records=10, poll_seconds=0, max_polls=1)
        self.assertEqual(pending["status"], "pending")
        second = API()
        complete = execute(STORE, second, self.store, trigger_inputs=[{"url": "https://www.walmart.com/cp/food/976759"}],
                           max_records=10, poll_seconds=0)
        self.assertEqual(second.trigger_calls, 0)
        self.assertEqual(complete["record_count"], 1)

    def test_carried_history_survives_second_sample(self):
        a = execute(STORE, API(records=[product(1234, pickup=False)]), self.store, snapshot_id="s_first12345", poll_seconds=0)
        b = execute(STORE, API(records=[product(5678)]), self.store, snapshot_id="s_second1234", poll_seconds=0)
        self.assertEqual(a["record_count"], 1)
        self.assertEqual(b["record_count"], 2)
        evid = json.loads(self.store.get(b["run"] + "/evidence.json"))
        self.assertEqual(evid["100:1234"]["classification"], "carried_not_observed_partial_crawl")

    def test_source_failure_preserves_existing_history(self):
        execute(STORE, API(), self.store, snapshot_id="s_first12345", poll_seconds=0)
        history = self.store.get("brightdata-trials/100/history.json")
        with self.assertRaises(BrightDataError):
            execute(STORE, API(states=["failed"]), self.store, snapshot_id="s_second1234", poll_seconds=0)
        self.assertEqual(history, self.store.get("brightdata-trials/100/history.json"))

    def test_empty_snapshot_does_not_publish(self):
        with self.assertRaises(BrightDataError):
            execute(STORE, API(records=[]), self.store, snapshot_id="s_first12345", poll_seconds=0)
        self.assertIsNone(self.store.get("brightdata-trials/100/latest-trial.json"))

    def test_bad_store_is_rejected_not_normalized(self):
        wrong = product(9999)
        wrong["store_id"] = "472"
        report = execute(STORE, API(records=[wrong, product(1234)]), self.store, snapshot_id="s_first12345", poll_seconds=0)
        rej = json.loads(self.store.get(report["run"] + "/rejected.json"))
        self.assertEqual(len(rej), 1)
        self.assertIn("STORE_ID", rej[0]["reason"])

    def test_new_trigger_is_opt_in(self):
        with patch.dict("os.environ", {"WALMART_DATA_AUTHORIZED": "", "BRIGHTDATA_COLLECTION_APPROVED": ""}):
            with self.assertRaises(SystemExit) as ex:
                main(["--trigger", "--inputs-csv", str(Path(__file__).parent.parent/"config"/"brightdata_category_inputs.csv"), "--max-records", "10", "--local-root", self.tmp.name])
            self.assertEqual(ex.exception.code, 2)

    def test_input_allowlist_blocks_other_categories(self):
        path = Path(self.tmp.name)/"cats.csv"
        path.write_text("url,zip_code,store_id\nhttps://www.walmart.com/cp/food/976759,72712,100\n")
        self.assertEqual(len(approved_input_categories(path, "100", "72712")), 1)
        path.write_text("url,zip_code,store_id\nhttps://www.walmart.com/cp/electronics/3944,72712,100\n")
        with self.assertRaises(ValueError):
            approved_input_categories(path, "100", "72712")

    def test_dry_run_is_not_billed(self):
        path = Path(__file__).parent.parent/"config"/"brightdata_category_inputs.csv"
        with patch.dict("os.environ", {"WALMART_DATA_AUTHORIZED": "", "BRIGHTDATA_COLLECTION_APPROVED": ""}):
            self.assertEqual(main(["--trigger", "--dry-run", "--inputs-csv", str(path), "--max-records", "10"]), 0)


if __name__ == "__main__":
    unittest.main()

class SeedHistoryTests(unittest.TestCase):
    def test_seed_is_fail_closed_and_one_time(self):
        from walmart_collector.brightdata_automatic import execute, LocalStore
        from tools.seed_azure_history import seed
        with tempfile.TemporaryDirectory() as td:
            store = LocalStore(Path(td) / 'src')
            execute(STORE, API(), store, snapshot_id='s_seed123456', poll_seconds=0)
            body=store.get('brightdata-trials/100/history.json')
            path=Path(td)/'history.json'; path.write_bytes(body)
            target=LocalStore(Path(td)/'dest')
            self.assertFalse(seed(path,target,confirm=False)['uploaded'])
            self.assertIsNone(target.get('brightdata-trials/100/history.json'))
            self.assertEqual(seed(path,target,confirm=True)['products'],1)
            with self.assertRaises(RuntimeError):
                seed(path,target,confirm=True)
