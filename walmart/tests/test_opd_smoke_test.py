import io
import unittest
from unittest.mock import patch
from contextlib import redirect_stdout, redirect_stderr

import sys as _sys, pathlib as _pathlib
_sys.path.insert(0, str(_pathlib.Path(__file__).resolve().parent.parent))

from tools import walmart_opd_smoke_test as probe


class OfficialOpdProbeTests(unittest.TestCase):
    def test_dry_run_makes_no_api_calls(self):
        out = io.StringIO()
        with patch.object(probe, 'api_json', side_effect=AssertionError('network call')), redirect_stdout(out):
            code = probe.main(['--store', 'both', '--dry-run'])
        self.assertEqual(code, 0)
        self.assertIn('72712', out.getvalue())
        self.assertIn('77007', out.getvalue())
        self.assertIn('NO Walmart API data', out.getvalue())

    def test_requires_credentials_without_network(self):
        err = io.StringIO()
        with patch.dict('os.environ', {'WALMART_OPD_CLIENT_ID': '', 'WALMART_OPD_CLIENT_SECRET': ''}), patch.object(probe, 'api_json', side_effect=AssertionError('network call')), redirect_stderr(err):
            code = probe.main(['--store', '100'])
        self.assertEqual(code, 2)
        self.assertIn('Missing', err.getvalue())

    def test_store_id_requires_matching_fulfillment_store(self):
        fake_response = {'payload': {'accessPointList': [
            {'fulfillmentStoreId': '100', 'accessPointName': 'Walmart Supercenter Bentonville', 'fulfillmentType': 'INSTORE_PICKUP'},
            {'fulfillmentStoreId': '99', 'accessPointName': 'Another store', 'fulfillmentType': 'INSTORE_PICKUP'}]}}
        with patch.object(probe, 'api_json', return_value=fake_response) as fn:
            result = probe.query_store('id', 'token', '100')
        self.assertTrue(result['store_found'])
        self.assertEqual(result['status'], 'STORE_CONFIRMED')
        self.assertEqual(fn.call_args.args[0], 'POST')

    def test_not_found_is_not_confirmed(self):
        with patch.object(probe, 'api_json', return_value={'payload': {'accessPointList': [{'fulfillmentStoreId': '123'}]}}):
            result = probe.query_store('id', 'token', '5959')
        self.assertFalse(result['store_found'])

    def test_no_secret_in_output(self):
        stdout = io.StringIO()
        with patch.dict('os.environ', {'WALMART_OPD_CLIENT_ID': 'test-public-id', 'WALMART_OPD_CLIENT_SECRET': 'DO-NOT-PRINT'}), patch.object(probe, 'get_token', return_value='DO-NOT-PRINT-TOKEN'), patch.object(probe, 'query_store', return_value={'store_found': True}), redirect_stdout(stdout):
            code = probe.main(['--store', '100'])
        self.assertEqual(code, 0)
        self.assertNotIn('DO-NOT-PRINT', stdout.getvalue())

    def test_catalog_feed_urls_are_not_printed(self):
        with patch.object(probe, 'api_json', return_value={'snapshot_date': '2026-10-20', 'product_snapshot_data': ['https://signed-private.example/a?token=secret']}):
            result = probe.query_catalog_metadata('id', 'token')
        self.assertEqual(result['feed_files'], 1)
        self.assertNotIn('secret', str(result))


if __name__ == "__main__":
    unittest.main()
