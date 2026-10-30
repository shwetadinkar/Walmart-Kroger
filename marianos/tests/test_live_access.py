"""Live preflight never reports complete collection or includes secrets."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import sys as _sys, pathlib as _pathlib
_sys.path.insert(0, str(_pathlib.Path(__file__).resolve().parent.parent))

from tools.live_access_preflight import diagnose_kroger, diagnose_provider, main

ROOT = Path(__file__).resolve().parent.parent

class FakeKroger:
    def __init__(self, creds): pass

class LiveAccessTests(unittest.TestCase):
    def test_kroger_reports_ambiguous_store_without_querying_products(self):
        cands = [{'locationId':'X123','zipcode':'60601','city':'Chicago','name':"Mariano's",
                  'address':'Example Rd'}]
        with patch('tools.live_access_preflight.Credentials.from_environment',return_value=object()), \
             patch('tools.live_access_preflight.KrogerClient',FakeKroger), \
             patch('tools.live_access_preflight.location_candidates',return_value=cands), \
             patch('tools.live_access_preflight.trial') as tr:
            r = diagnose_kroger('60601','','','milk')
        self.assertEqual(r['result'],'NEEDS_VERIFIED_LOCATION_ID')
        self.assertFalse(r['verified_500_real_products'])
        tr.assert_not_called()

    def test_kroger_valid_diagnostic_redacts_sample_records(self):
        cands = [{'locationId':'X123','zipcode':'60601','city':'Chicago','name':"Mariano's",
                  'address':'Example Rd'}]
        sample = {'matches_by_term':{'milk':1},'unique_preview_records':1,
                  'samples':[{'productId':'PRIVATE','title':'Some product','upc':'ABC123'}]}
        with patch('tools.live_access_preflight.Credentials.from_environment',return_value=object()), \
             patch('tools.live_access_preflight.KrogerClient',FakeKroger), \
             patch('tools.live_access_preflight.location_candidates',return_value=cands), \
             patch('tools.live_access_preflight.trial',return_value=sample):
            r = diagnose_kroger('60601','X123','','milk')
        self.assertEqual(r['result'],'DIAGNOSTIC_OK')
        self.assertNotIn('PRIVATE',str(r))
        self.assertNotIn('ABC123',str(r))
        self.assertFalse(r['full_category_coverage_verified'])

    def test_provider_without_authorization_fails_closed(self):
        with patch.dict(os.environ, {'MARIANOS_DATA_AUTHORIZED':'no'}):
            r = diagnose_provider(ROOT/'config/stores_demo.json','DEMO-LAKESHORE-60601',ROOT/'config/categories.csv',2)
        self.assertEqual(r['result'],'AUTHORIZATION_CONFIRMATION_MISSING')

    def test_provider_demo_store_fails_closed(self):
        with patch.dict(os.environ, {'MARIANOS_DATA_AUTHORIZED':'yes'}):
            r = diagnose_provider(ROOT/'config/stores_demo.json','DEMO-LAKESHORE-60601',ROOT/'config/categories.csv',2)
        self.assertEqual(r['result'],'VERIFIED_STORE_CONFIGURATION_REQUIRED')

    def test_main_without_api_credentials_writes_sanitized_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(os.environ, {'KROGER_CLIENT_ID':'', 'KROGER_CLIENT_SECRET':''}):
                exit_code=main(['--mode','kroger','--report',str(Path(tmp)/'safe.json')])
            self.assertEqual(exit_code,1)
            written=(Path(tmp)/'safe.json').read_text()
            self.assertIn('CONNECTION_FAILED', written)
            self.assertIn('api_secret_included', written)
            self.assertNotIn('Bearer ', written)


if __name__ == "__main__":
    unittest.main()
