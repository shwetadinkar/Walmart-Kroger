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


WEST_LOOP = {'location_id': '53100508', 'zipcode': '60661'}
VERNON_HILLS = {'location_id': '53100502', 'zipcode': '60061'}


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
                run_attempt(storage, client, budget, 'trial1', 'execution-A', 'interrupt', crash, **WEST_LOOP)
            resumed = run_attempt(storage, client, BudgetOpener(6), 'trial1', 'execution-B', 'resume', crash, **WEST_LOOP)
            fresh = run_attempt(storage, client, BudgetOpener(6), 'trial1', 'execution-C', 'fresh', crash, **WEST_LOOP)
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
                run_attempt(storage, Client(), BudgetOpener(6), 'trial1', 'execution-A', 'resume', lambda: None, **WEST_LOOP)

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
                run_attempt(storage, Client(), budget, 'trial1', 'execution-A', 'interrupt', lambda: None, **WEST_LOOP)
            self.assertEqual(json.loads(storage.read('recovery-review/53100508/trial1/budget.json'))['attempts'], 8)

    def test_thin_source_cannot_create_successful_interruption_marker(self):
        with tempfile.TemporaryDirectory() as d:
            storage = LocalStorage(Path(d))
            class Client:
                def get(self, path): return {'data': store()}
                def products(self, *args, **kwargs): return {'data': [product()]}
            def crash(): raise AssertionError('thin source must not reach approved crash point')
            with self.assertRaises(ValueError):
                run_attempt(storage, Client(), BudgetOpener(6), 'thin', 'execution-A', 'interrupt', crash, **WEST_LOOP)
            self.assertIsNone(storage.read('recovery-review/53100508/thin/durable-checkpoint.json'))


class ConfiguredStoreTests(unittest.TestCase):
    def client(self, document):
        class Client:
            def get(self, path): return {'data': document}
            def products(self, *args, **kwargs):
                return {'data': [product('000111106093' + str(i)) for i in range(5)]}
        return Client()

    def vernon_hills(self):
        document = store()
        document.update(locationId='53100502', name='Marianos - Vernon Hills')
        document['address'].update(addressLine1='1720 N Milwaukee Ave', city='Vernon Hills', zipCode='60061')
        return document

    def run_interrupt(self, storage, document, **where):
        class Crash2(BaseException):
            pass
        def crash(): raise Crash2()
        with self.assertRaises(Crash2):
            run_attempt(storage, self.client(document), BudgetOpener(6), 'trial1', 'execution-A',
                        'interrupt', crash, **where)

    def test_a_vernon_hills_run_writes_only_under_vernon_hills(self):
        with tempfile.TemporaryDirectory() as d:
            storage = LocalStorage(Path(d))
            self.run_interrupt(storage, self.vernon_hills(), **VERNON_HILLS)
            self.assertIsNotNone(storage.read('recovery-review/53100502/trial1/durable-checkpoint.json'))
            self.assertFalse((Path(d) / 'recovery-review/53100508').exists())
            page = json.loads(storage.read('recovery-review/53100502/trial1/checkpoints/53100502/trial1-resume/page_00.json'))
            self.assertEqual(page['locationId'], '53100502')

    def test_the_west_loop_trial_evidence_keeps_its_store_and_is_left_alone(self):
        with tempfile.TemporaryDirectory() as d:
            storage = LocalStorage(Path(d))
            storage.write('recovery-review/53100508/trial1/durable-checkpoint.json', b'west loop evidence')
            self.run_interrupt(storage, self.vernon_hills(), **VERNON_HILLS)
            self.assertEqual(storage.read('recovery-review/53100508/trial1/durable-checkpoint.json'),
                             b'west loop evidence')

    def test_the_store_has_no_default(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(TypeError):
                run_attempt(LocalStorage(Path(d)), self.client(store()), BudgetOpener(6),
                            'trial1', 'execution-A', 'interrupt', lambda: None)

    def test_a_configured_store_the_api_contradicts_is_refused(self):
        # West Loop's response to a request for Vernon Hills: two characters apart.
        with tempfile.TemporaryDirectory() as d:
            storage = LocalStorage(Path(d))
            with self.assertRaisesRegex(ValueError, 'STORE_MISMATCH'):
                run_attempt(storage, self.client(store()), BudgetOpener(6), 'trial1',
                            'execution-A', 'interrupt', lambda: None, **VERNON_HILLS)

    def test_a_malformed_store_is_refused_before_anything_is_written(self):
        with tempfile.TemporaryDirectory() as d:
            storage = LocalStorage(Path(d))
            for where in ({'location_id': '5310050', 'zipcode': '60061'},
                          {'location_id': '53100502', 'zipcode': '6006'}):
                with self.subTest(where), self.assertRaisesRegex(ValueError, 'INVALID_RECOVERY_STORE'):
                    run_attempt(storage, self.client(store()), BudgetOpener(6), 'trial1',
                                'execution-A', 'interrupt', lambda: None, **where)
            self.assertEqual(list(Path(d).iterdir()), [])


if __name__ == '__main__':
    unittest.main()
