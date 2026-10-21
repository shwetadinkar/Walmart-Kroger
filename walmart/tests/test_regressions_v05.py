"""Regression checks for integrity and restricted publication changes."""
from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from walmart_collector.config import Category, Store
from walmart_collector.runner import Collector, ValidationFailure
from walmart_collector.sources import Page, FixtureSource
from walmart_collector.storage import LocalStorage, read_json
from tools.submission_gate import inspect, FIELDS, CHECKS

ROOT = Path(__file__).resolve().parents[1]
STORE = Store("100", "72712", "Walmart #100", "Bentonville, AR")


class TestSafetyRegression(unittest.TestCase):
    def test_taxonomy_diagnostic_never_claims_full_coverage(self):
        from tools.opd_category_audit import audit, category_id
        hierarchy = {"categories":[{"id":"976759","name":"Food",
                     "children":[{"id":"976759_999","name":"Cereal"}]}]}
        rows = [{"Category (Auto)":"Food", "URL":"https://www.walmart.com/cp/food/976759"},
                {"Category (Auto)":"Beauty", "URL":"https://www.walmart.com/cp/beauty/1085666"}]
        result = audit(hierarchy,rows)
        self.assertEqual(result["categories"][0]["status"], "MATCH_CANDIDATE_VERIFY_PATH")
        self.assertEqual(result["categories"][1]["status"], "MANUAL_MAPPING_REQUIRED")
        self.assertFalse(result["approved_for_contest"])
        self.assertEqual(category_id("https://www.walmart.com/browse/a/b/2637_1042319_1212898_3956207"),"2637_1042319_1212898_3956207")

    def test_opd_cli_always_isolates_trial(self):
        from walmart_collector.cli import build_parser
        parser = build_parser()
        self.assertEqual(parser.parse_args(["run", "--source", "opd"]).source, "opd")
        # A dedicated OPD trial namespace is selected in cli.main, so an OPD
        # invocation cannot accidentally update the full-release pointer.
        from unittest.mock import patch
        from walmart_collector import cli
        with tempfile.TemporaryDirectory() as root:
            # OPD auth must still be checked and cannot be supplied in tests.
            with patch.dict("os.environ", {}, clear=True):
                status = cli.main(["status", "--source", "opd", "--output", root])
            self.assertEqual(status, 0)

    def test_trial_never_replaces_full_release(self):
        from walmart_collector.config import categories_from_csv
        cats = categories_from_csv(ROOT/"config/categories.csv")
        with tempfile.TemporaryDirectory() as folder:
            storage = LocalStorage(Path(folder))
            source = FixtureSource(ROOT/"fixtures")
            full = Collector(storage,source,cats,min_products=11).run(STORE)
            original = read_json(storage,"published/100/latest.json")
            trial = Collector(storage,source,cats[:2],min_products=2,trial=True).run(STORE)
            self.assertEqual(read_json(storage,"published/100/latest.json"), original)
            self.assertEqual(trial["manifest"]["scope"], "trial")
            self.assertEqual(full["manifest"]["scope"], "full")
            self.assertIsNone(read_json(storage,"checkpoints/100/full/food.json"))

    def test_revision_switch_rejected_without_publishing(self):
        class ChangingSource:
            source_mode = "synthetic_fixture_revision_change"
            def fetch(self, store, category, url, cursor):
                fixture = FixtureSource(ROOT/"fixtures")
                page = fixture.fetch(store,category,url,cursor)
                page.source_revision = "snapshot-A" if not cursor else "snapshot-B"
                return page
        from walmart_collector.config import categories_from_csv
        cats = [x for x in categories_from_csv(ROOT/"config/categories.csv")
                if x.name == "Household Essentials"]
        with tempfile.TemporaryDirectory() as folder:
            storage = LocalStorage(Path(folder))
            with self.assertRaisesRegex(ValidationFailure,"snapshot changed"):
                Collector(storage,ChangingSource(),cats,min_products=1).run(STORE)
            self.assertIsNone(read_json(storage,"published/100/latest.json"))

    def test_submission_gate_rejects_synthetic_and_unreviewed(self):
        rows = [{k: "" for k in FIELDS} for _ in range(500)]
        for i,r in enumerate(rows):
            r["zipcode"]="72712";r["url"]=f"https://www.walmart.com/ip/{i}"
        raw = json.dumps(rows).encode()
        sample = {"scope":"full", "source_is_synthetic":True,
                  "source_coverage_attested":False, "status":"validated",
                  "unique_records":500, "category_counts":{"Food":500}}
        result = inspect(rows,sample,{},["Food"],raw)
        self.assertEqual(result["status"],"BLOCKED")
        self.assertTrue(any("Synthetic" in e for e in result["errors"]))

    def test_submission_gate_requires_every_external_signoff(self):
        rows = [{k: "" for k in FIELDS} for _ in range(500)]
        for i,r in enumerate(rows):
            r["zipcode"]="72712";r["url"]=f"https://www.walmart.com/ip/{i}"
        raw=json.dumps(rows).encode()
        report={"scope":"full","source_is_synthetic":False,"source_coverage_attested":True,
                "status":"validated","unique_records":500,"category_counts":{"Food":500}}
        review={"data_sha256":hashlib.sha256(raw).hexdigest(), "assigned_store_id":"100",
                "reviewer":"Independent test engineer","reviewed_at_utc":"2026-10-21T12:00:00Z",
                "attestations":{k:True for k in CHECKS},
                "evidence":{k:f"review/{k}.md" for k in CHECKS}}
        self.assertEqual(inspect(rows,report,review,["Food"],raw)["status"],"PASS_REQUIRES_BUYER_CONFIRMATION")
        review["attestations"]["pickup_and_in_store_eligibility_audit"] = False
        self.assertEqual(inspect(rows,report,review,["Food"],raw)["status"],"BLOCKED")

if __name__ == "__main__": unittest.main()
