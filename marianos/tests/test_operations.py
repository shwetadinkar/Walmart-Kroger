import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class OperationsTests(unittest.TestCase):
    def config(self):
        return json.loads((ROOT/'config/discovery.westloop.example.json').read_text())

    def test_check_validates_locality_and_rejects_bad_cron_before_network(self):
        from marianos_collector.operations import check_configuration
        result = check_configuration(self.config(), '53100508', '60661')
        self.assertEqual(result['configured_roots'], 1)
        self.assertFalse(result['live_store_verified'])
        self.assertFalse(result['submission_ready'])
        for sid, zipcode in [('53100531','60661'),('53100508','60601')]:
            with self.assertRaises(ValueError):check_configuration(self.config(),sid,zipcode)
        for cron in ['99 6 * * 1,4', '0 24 * * 1', '0 6 * 13 1', '0 6 * * 8', '*/0 6 * * 1', '0 6 5-2 * 1']:
            bad=self.config();bad['schedule']['cron_utc']=cron
            with self.assertRaises(ValueError):check_configuration(bad)

    def test_failed_discovery_report_retains_unknown_counts_and_strips_untrusted_fields(self):
        from marianos_collector.operations import build_report
        receipt={'execution_id':'azure-test','store_id':'53100508','status':'failed',
                 'browser_actions_consumed':1,'page_navigation_actions_consumed':1,
                 'error_code':'net::ERR_HTTP2_PROTOCOL_ERROR','body_text':'SECRET',
                 'error_type':'Error','token':'SECRET','url':'https://example.invalid/?token=SECRET'}
        result=build_report('discovery',receipt,configuration=self.config())
        self.assertEqual(result['status'],'failed')
        self.assertEqual(result['counts']['browser_actions'],1)
        self.assertIsNone(result['counts']['accepted_records'])
        self.assertIsNone(result['counts']['network_requests'])
        self.assertNotIn('SECRET',json.dumps(result))
        self.assertEqual(result['failure']['code'],'net::ERR_HTTP2_PROTOCOL_ERROR')
        self.assertFalse(result['submission_ready'])

    def test_complete_synthetic_listing_is_not_live_product_acceptance(self):
        from marianos_collector.operations import build_report
        receipt={'execution_id':'fixture','store_id':'53100508','status':'completed','source_kind':'synthetic-fixture'}
        coverage={'store_id':'53100508','run_id':'fixture','all_roots_complete':True,
                  'complete_roots':1,'configured_roots':1,'pages_observed':2,'source_is_synthetic':True}
        result=build_report('discovery',receipt,configuration=self.config(),coverage=coverage)
        self.assertTrue(result['source_is_synthetic'])
        self.assertTrue(result['coverage']['listing_scope_complete'])
        self.assertFalse(result['coverage']['live_category_acceptance'])
        self.assertFalse(result['coverage']['product_extraction_complete'])
        self.assertFalse(result['submission_ready'])

    def test_api_report_does_not_treat_request_count_or_product_count_as_category_proof(self):
        from marianos_collector.operations import build_report
        receipt={'run_id':'api-one','store_id':'53100508','state':'completed','attempted_requests':3,
                 'metrics':{'records':5},'pointer':{'data_key':'runs/abc/products.json','records':5}}
        result=build_report('api-trial',receipt,configuration={'zipcode':'60661'})
        self.assertEqual(result['counts']['accepted_records'],5)
        self.assertEqual(result['counts']['network_requests'],3)
        self.assertIsNone(result['counts']['quarantined_records'])
        self.assertFalse(result['coverage']['live_category_acceptance'])
        self.assertFalse(result['submission_ready'])

    def test_mixed_store_or_execution_evidence_is_rejected(self):
        from marianos_collector.operations import build_report
        receipt={'execution_id':'one','store_id':'53100508','status':'completed'}
        for coverage in [{'store_id':'53100531'}, {'run_id':'two'}]:
            with self.assertRaises(ValueError):build_report('discovery',receipt,coverage=coverage)
        bad=self.config();bad['store']['id']='53100531'
        with self.assertRaises(ValueError):build_report('discovery',receipt,configuration=bad)

    def test_untrusted_counts_status_and_failure_strings_fail_closed(self):
        from marianos_collector.operations import build_report
        for value in [True,-1,'5']:
            with self.assertRaises(ValueError):build_report('api-trial',{'run_id':'one','store_id':'53100508','state':'completed','metrics':{'records':value}})
        with self.assertRaises(ValueError):build_report('discovery',{'status':'SECRET'})
        result=build_report('discovery',{'execution_id':'one','store_id':'53100508','status':'failed','error_code':'SECRET','error_type':'SECRET'})
        self.assertNotIn('SECRET',json.dumps(result))

    def test_automatic_discovery_failure_report_is_saved_without_masking_source_failure(self):
        from marianos_collector.discovery_job import run_discovery
        from marianos_collector.storage import LocalStorage
        with tempfile.TemporaryDirectory() as td:
            storage=LocalStorage(Path(td))
            def unavailable(c,g,t):g('page');raise TimeoutError('SECRET')
            with self.assertRaises(TimeoutError):run_discovery(self.config(),storage,'failure',unavailable)
            report=json.loads(storage.read('discovery-review/53100508/failure/operational-report.json'))
            self.assertEqual(report['status'],'failed')
            self.assertEqual(report['counts']['navigation_actions'],1)
            self.assertNotIn('SECRET',json.dumps(report))

    def test_automatic_api_reports_follow_failure_resume_and_separate_execution(self):
        from marianos_collector.execution_state import execute_once
        from marianos_collector.api_collection import BudgetOpener
        from marianos_collector.storage import LocalStorage
        with tempfile.TemporaryDirectory() as td:
            storage=LocalStorage(Path(td));calls=[]
            def work():
                calls.append('source')
                pointer={'data_key':'runs/a/products.json','report_key':'runs/a/validation.json','provenance_key':'runs/a/provenance.json'}
                for key in pointer.values():storage.write('freshness-checks/53100508/'+key,b'{}')
                return pointer,{'records':5}
            def failed():raise TimeoutError('SECRET')
            config={'zipcode':'60661','output_prefix':'freshness-checks'}
            with self.assertRaises(TimeoutError):execute_once(storage,'53100508','one',config,BudgetOpener(6),failed)
            key='executions/53100508/one.operations.json'
            self.assertEqual(json.loads(storage.read(key))['status'],'failed')
            execute_once(storage,'53100508','one',config,BudgetOpener(6),work)
            report=json.loads(storage.read(key));self.assertEqual(report['status'],'completed')
            self.assertEqual(report['counts']['accepted_records'],5)
            self.assertIsNone(report['failure']['type'])
            execute_once(storage,'53100508','one',config,BudgetOpener(6),work)
            execute_once(storage,'53100508','two',config,BudgetOpener(6),work)
            self.assertEqual(calls,['source','source'])
            self.assertEqual(json.loads(storage.read('executions/53100508/two.operations.json'))['execution_id'],'two')

    def test_cli_refuses_to_overwrite_input_evidence(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'operational-report.json'
            path.write_text(json.dumps({'execution_id':'one','store_id':'53100508','status':'completed'}))
            original=path.read_bytes()
            result=subprocess.run([sys.executable,'-m','marianos_collector.operations','report','--mode','discovery','--receipt',str(path),'--output',td],cwd=ROOT,capture_output=True,text=True)
            self.assertEqual(result.returncode,2)
            self.assertEqual(original,path.read_bytes())

    def test_supplementary_reporting_failure_preserves_original_failure(self):
        from marianos_collector.discovery_job import run_discovery
        from marianos_collector.storage import LocalStorage
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as td:
            storage=LocalStorage(Path(td));write=storage.write
            def fail_report(key,body):
                if key.endswith('operational-report.json'):raise OSError('SECRET')
                write(key,body)
            def source(c,g,t):raise TimeoutError('SOURCE_SECRET')
            with patch.object(storage,'write',side_effect=fail_report):
                with self.assertLogs('collector',level='WARNING') as logs:
                    with self.assertRaises(TimeoutError):run_discovery(self.config(),storage,'one',source)
            self.assertIn('operational_report_unavailable',str(logs.output))
            self.assertNotIn('SECRET',str(logs.output))

    def test_failed_run_cannot_advertise_listing_completion_from_other_evidence(self):
        from marianos_collector.operations import build_report
        with self.assertRaises(ValueError):
            build_report('discovery',{'execution_id':'one','store_id':'53100508','status':'failed'},coverage={'all_roots_complete':True})

    def test_conflicting_or_malformed_synthetic_flags_cannot_hide_fixture_evidence(self):
        from marianos_collector.operations import build_report
        receipt={'execution_id':'one','store_id':'53100508','status':'completed','source_is_synthetic':True}
        for cov in [{'source_is_synthetic':False},{'source_is_synthetic':'false'}]:
            with self.assertRaises(ValueError):build_report('discovery',receipt,coverage=cov)
        with self.assertRaises(ValueError):build_report('discovery',{**receipt,'source_is_synthetic':'bad'},coverage={'source_is_synthetic':True})

    def test_coverage_counts_must_agree_with_configuration_and_completion(self):
        from marianos_collector.operations import build_report
        receipt={'execution_id':'one','store_id':'53100508','status':'completed'}
        for cov in [{'configured_roots':28,'complete_roots':29,'all_roots_complete':True},
                    {'configured_roots':1,'complete_roots':2},
                    {'configured_roots':1,'complete_roots':0,'all_roots_complete':True},
                    {'all_roots_complete':True}]:
            with self.assertRaises(ValueError):build_report('discovery',receipt,configuration=self.config(),coverage=cov)

    def test_api_candidate_waiting_for_publication_is_not_a_completed_run(self):
        from marianos_collector.operations import build_report
        result=build_report('api-trial',{'run_id':'one','store_id':'53100508','state':'validated','last_error_type':'OSError','metrics':{'records':5}})
        self.assertEqual(result['status'],'publication_pending')
        self.assertEqual(result['failure']['type'],'OSError')
        self.assertFalse(result['submission_ready'])

    def test_check_cli_exits_with_safe_error_and_report_cli_keeps_input_unchanged(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td);config=p/'config.json';config.write_text(json.dumps(self.config()))
            cmd=[sys.executable,'-m','marianos_collector.operations']
            checked=subprocess.run(cmd+['check','--config',str(config),'--output',str(p/'check')],cwd=ROOT,capture_output=True,text=True)
            self.assertEqual(checked.returncode,0,checked.stderr)
            self.assertTrue((p/'check/operational-report.md').is_file())
            config.write_text('{"secret":"SECRET"}')
            bad=subprocess.run(cmd+['check','--config',str(config)],cwd=ROOT,capture_output=True,text=True)
            self.assertEqual(bad.returncode,2)
            self.assertNotIn('SECRET',bad.stdout+bad.stderr)
            receipt=p/'receipt.json';receipt.write_text(json.dumps({'execution_id':'one','store_id':'53100508','status':'failed','error_type':'Error'}))
            before=receipt.read_bytes()
            reported=subprocess.run(cmd+['report','--mode','discovery','--receipt',str(receipt),'--output',str(p/'report')],cwd=ROOT,capture_output=True,text=True)
            self.assertEqual(reported.returncode,2)
            self.assertEqual(receipt.read_bytes(),before)
            self.assertFalse(json.loads((p/'report/operational-report.json').read_text())['submission_ready'])


if __name__=='__main__':unittest.main()
