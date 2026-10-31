import sys as _sys, pathlib as _pathlib
_sys.path.insert(0, str(_pathlib.Path(__file__).resolve().parent.parent))
_sys.path.insert(0, str(_pathlib.Path(__file__).resolve().parent))
import json
from pathlib import Path
import tempfile
import unittest
from marianos_collector.execution_state import execute_once
from marianos_collector.api_collection import BudgetOpener
from marianos_collector.storage import LocalStorage
from unittest.mock import patch


class ExecutionStateTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.storage=LocalStorage(Path(self.temp.name));self.calls=[]
        self.config={'target':5,'zipcode':'60661'}

    def work(self,run):
        def perform():
            self.calls.append(run)
            pointer={'run':run,'records':5,'data_key':f'runs/{run}/products.json',
                     'report_key':f'runs/{run}/validation.json','provenance_key':f'runs/{run}/provenance.json',
                     'submission_ready':False}
            for key in ('data_key','report_key','provenance_key'):
                self.storage.write('trials/53100508/'+pointer[key],b'{}')
            return pointer,{'records':5,'product_queries':1}
        return perform

    def execute(self,run,work=None,budget=None):
        return execute_once(self.storage,'53100508',run,self.config,budget or BudgetOpener(6),work or self.work(run))

    def test_completed_execution_is_idempotent_without_work_or_publication_rollback(self):
        self.execute('one');self.execute('two')
        latest=self.storage.read('trials/53100508/latest.json')
        again=self.execute('one')
        self.assertTrue(again['duplicate_skipped']);self.assertEqual(self.calls,['one','two'])
        self.assertEqual(latest,self.storage.read('trials/53100508/latest.json'))

    def test_distinct_executions_both_perform_work(self):
        self.execute('one');self.execute('two')
        self.assertEqual(self.calls,['one','two'])

    def test_freshness_namespace_preserves_baseline_pointer_and_objects(self):
        self.execute('baseline');before=self.storage.read('trials/53100508/latest.json')
        self.config['output_prefix']='freshness-checks'
        def isolated():
            pointer={'records':5,'data_key':'runs/check/products.json','report_key':'runs/check/validation.json',
                     'provenance_key':'runs/check/provenance.json'}
            for field in ('data_key','report_key','provenance_key'):
                self.storage.write('freshness-checks/53100508/'+pointer[field],b'{}')
            return pointer,{'records':5,'product_queries':1}
        self.execute('check',isolated)
        self.assertEqual(before,self.storage.read('trials/53100508/latest.json'))
        self.assertIsNotNone(self.storage.read('freshness-checks/53100508/latest.json'))

    def test_unsafe_output_namespace_is_rejected_before_work(self):
        self.config['output_prefix']='../trials'
        with self.assertRaises(ValueError):self.execute('bad')
        self.assertEqual(self.calls,[])

    def test_failed_work_preserves_success_and_retry_can_resume_same_execution(self):
        self.execute('good');before=self.storage.read('trials/53100508/latest.json')
        def failure():raise ValueError('do not expose source secrets')
        with self.assertRaises(ValueError):self.execute('retry',failure)
        self.assertEqual(before,self.storage.read('trials/53100508/latest.json'))
        result=self.execute('retry')
        self.assertFalse(result['duplicate_skipped'])
        receipt=json.loads(self.storage.read('executions/53100508/retry.json'))
        self.assertEqual(receipt['state'],'completed')
        self.assertNotIn('do not expose',json.dumps(receipt))

    def test_changed_configuration_for_same_execution_fails_before_work(self):
        self.execute('one');self.config['target']=6
        with self.assertRaises(ValueError):self.execute('one')
        self.assertEqual(self.calls,['one'])

    def test_request_budget_survives_failure_and_restart(self):
        budget=BudgetOpener(2,opener=lambda *a,**k:None)
        def fail_after_request():budget(None);raise TimeoutError()
        with self.assertRaises(TimeoutError):self.execute('retry',fail_after_request,budget)
        second=BudgetOpener(2,opener=lambda *a,**k:None)
        def retry_over_budget():second(None);second(None)
        with self.assertRaises(ValueError):self.execute('retry',retry_over_budget,second)
        self.assertEqual(second.used,2)

    def test_completed_receipt_with_corrupt_immutable_data_is_rejected(self):
        self.execute('one');self.storage.write('trials/53100508/runs/one/products.json',b'corrupt')
        with self.assertRaises(ValueError):self.execute('one')

    def test_retry_after_pointer_write_failure_reuses_validated_output_without_source_calls(self):
        original=self.storage.write
        def broken_write(key,body):
            if key.endswith('/latest.json'):raise OSError('publication interrupted')
            return original(key,body)
        with patch.object(self.storage,'write',side_effect=broken_write):
            with self.assertRaises(OSError):self.execute('one')
        self.execute('one')
        self.assertEqual(self.calls,['one'])

    def test_older_validated_candidate_cannot_overwrite_a_later_success(self):
        original=self.storage.write
        def broken_write(key,body):
            if key.endswith('/latest.json'):raise OSError()
            return original(key,body)
        with patch.object(self.storage,'write',side_effect=broken_write):
            with self.assertRaises(OSError):self.execute('one')
        self.execute('two');latest=self.storage.read('trials/53100508/latest.json')
        result=self.execute('one')
        self.assertTrue(result['superseded_by_later_success'])
        self.assertEqual(latest,self.storage.read('trials/53100508/latest.json'))

if __name__=='__main__':unittest.main()
