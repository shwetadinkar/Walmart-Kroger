"""Hardening tests for offline acceptance and live submission gates."""
import json
import tempfile
import unittest
from pathlib import Path
import sys as _sys, pathlib as _pathlib
_sys.path.insert(0, str(_pathlib.Path(__file__).resolve().parent.parent))

from tools.acceptance_simulation import execute
from tools.submission_gate import run
from marianos_collector.config import categories_from_csv, stores_from_json
from marianos_collector.sources import FixtureSource
from marianos_collector.runner import Collector
from marianos_collector.storage import LocalStorage, read_json

ROOT=Path(__file__).resolve().parent.parent

class AcceptanceTests(unittest.TestCase):
    def test_complete_560_record_synthetic_recovery(self):
        r=execute()
        self.assertTrue(r['passed'],r)
        self.assertEqual(r['simulated_unique_records'],560)
        self.assertEqual(r['categories_count'],28)
        self.assertFalse(r['contest_submission_evidence'])

    def test_secondary_store_synthetic_recovery(self):
        r=execute('DEMO-WESTLOOP-60661')
        self.assertTrue(r['passed'],r)

    def test_fixture_cannot_pass_submission_gate(self):
        with tempfile.TemporaryDirectory() as td:
            storage=LocalStorage(Path(td))
            c=categories_from_csv(ROOT/'config/categories.csv')
            s=stores_from_json(ROOT/'config/stores_demo.json')[0]
            Collector(storage,FixtureSource(ROOT/'fixtures'),c,min_products=1).run(s)
            result=run(s.store_id,Path(td),ROOT/'config/stores_demo.json',ROOT/'config/categories.csv',Path(td)/'missing.json')
            self.assertEqual(result['result'],'BLOCKED_PENDING_REAL_DATA_OR_VERIFICATION')
            self.assertFalse(result['checks']['not_marked_synthetic'])
            self.assertFalse(result['checks']['at_least_500_unique_records'])
            self.assertFalse(result['checks']['human_reviewer_identified'])

if __name__=='__main__':unittest.main()


if __name__ == "__main__":
    unittest.main()
