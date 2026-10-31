import sys as _sys, pathlib as _pathlib
_sys.path.insert(0, str(_pathlib.Path(__file__).resolve().parent.parent))
_sys.path.insert(0, str(_pathlib.Path(__file__).resolve().parent))
import json
from pathlib import Path
import tempfile
import unittest
from marianos_collector.cloud_recovery import run_attempt
from marianos_collector.storage import LocalStorage
from marianos_collector.api_collection import BudgetOpener
from test_api_trial import product, store


class Crash(BaseException):
    pass


class CloudRecoveryTests(unittest.TestCase):
    def test_stable_logical_identity_separate_platform_attempts_and_isolated_storage(self):
        with tempfile.TemporaryDirectory() as d:
            storage = LocalStorage(Path(d))
            storage.write('trials/53100508/latest.json', b'protected')
            budget = BudgetOpener(6)
            class Client:
                calls = 0
                def get(self, path): return {'data': store()}
                def products(self, *args, **kwargs):
                    self.calls += 1
                    return {'data': [product('000111106093' + str(i)) for i in range(5)]}
            client = Client()
            def crash(): raise Crash()
            with self.assertRaises(Crash):
                run_attempt(storage, client, budget, 'trial1', 'execution-A', 'interrupt', crash)
            resumed = run_attempt(storage, client, BudgetOpener(6), 'trial1', 'execution-B', 'resume', crash)
            fresh = run_attempt(storage, client, BudgetOpener(6), 'trial1', 'execution-C', 'fresh', crash)
            self.assertTrue(resumed['checkpoint_unchanged'])
            self.assertEqual(resumed['new_queries'], 0)
            self.assertEqual(fresh['new_queries'], 1)
            self.assertEqual(client.calls, 2)
            self.assertEqual(resumed['platform_execution'], 'execution-B')
            self.assertNotEqual(resumed['logical_run_id'], fresh['logical_run_id'])
            self.assertEqual(storage.read('trials/53100508/latest.json'), b'protected')
            self.assertFalse(any(p.is_file() for p in (Path(d)/'checkpoints').rglob('*')))

    def test_resume_without_checkpoint_and_repeated_attempt_fail_before_source(self):
        with tempfile.TemporaryDirectory() as d:
            storage = LocalStorage(Path(d))
            class Client:
                def get(self, path): raise AssertionError('source must not be called')
            with self.assertRaises(ValueError):
                run_attempt(storage, Client(), BudgetOpener(6), 'trial1', 'execution-A', 'resume', lambda: None)

    def test_shared_budget_refuses_ninth_attempt(self):
        with tempfile.TemporaryDirectory() as d:
            storage = LocalStorage(Path(d))
            storage.write('recovery-review/53100508/trial1/budget.json', b'{"attempts":8}')
            budget = BudgetOpener(6)
            class Client:
                def get(self, path):
                    budget('https://example.invalid')
                    raise AssertionError('network should not be reached')
            with self.assertRaises(ValueError):
                run_attempt(storage, Client(), budget, 'trial1', 'execution-A', 'interrupt', lambda: None)
            self.assertEqual(json.loads(storage.read('recovery-review/53100508/trial1/budget.json'))['attempts'], 8)

    def test_thin_source_cannot_create_successful_interruption_marker(self):
        with tempfile.TemporaryDirectory() as d:
            storage = LocalStorage(Path(d))
            class Client:
                def get(self, path): return {'data': store()}
                def products(self, *args, **kwargs): return {'data': [product()]}
            def crash(): raise AssertionError('thin source must not reach approved crash point')
            with self.assertRaises(ValueError):
                run_attempt(storage, Client(), BudgetOpener(6), 'thin', 'execution-A', 'interrupt', crash)
            self.assertIsNone(storage.read('recovery-review/53100508/thin/durable-checkpoint.json'))


if __name__ == '__main__':
    unittest.main()
