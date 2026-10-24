import importlib.util
import os
from pathlib import Path
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('container_entrypoint',Path(__file__).resolve().parents[1]/'azure/container_entrypoint.py')
entry=importlib.util.module_from_spec(spec);spec.loader.exec_module(entry)

class EntrypointTests(unittest.TestCase):
    def test_azure_first_run_can_be_limited_to_five_records(self):
        with patch.dict(os.environ,{'MARIANOS_MODE':'api-trial','MARIANOS_STORE_ID':'53100508',
                                   'MARIANOS_ZIPCODE':'60661','MARIANOS_TARGET':'5',
                                   'MARIANOS_MINIMUM':'5','MARIANOS_MAX_QUERIES':'1',
                                   'MARIANOS_MAX_REQUESTS':'6'},clear=True):
            args=entry.command()
        self.assertEqual(args[args.index('--target')+1],'5')
        self.assertEqual(args[args.index('--minimum')+1],'5')
        self.assertEqual(args[args.index('--maximum-queries')+1],'1')
        self.assertEqual(args[args.index('--maximum-requests')+1],'6')

    def test_azure_budget_cannot_exceed_the_trial_ceiling(self):
        with patch.dict(os.environ,{'MARIANOS_MODE':'api-trial','MARIANOS_STORE_ID':'53100508',
                                   'MARIANOS_ZIPCODE':'60661','MARIANOS_MAX_REQUESTS':'999'},clear=True):
            with self.assertRaises(ValueError):entry.command()

    def test_api_mode_uses_trial_module_and_durable_azure_storage(self):
        with patch.dict(os.environ,{'MARIANOS_MODE':'api-trial','MARIANOS_STORE_ID':'53100508',
                                   'MARIANOS_ZIPCODE':'60661','MARIANOS_RUN_ID':'run1'},clear=True):
            args=entry.command()
        self.assertIn('marianos_collector.api_collection',args)
        self.assertIn('azure',args)
        self.assertNotIn('provider',args)

    def test_api_mode_requires_zip(self):
        with patch.dict(os.environ,{'MARIANOS_MODE':'api-trial','MARIANOS_STORE_ID':'53100508'},clear=True):
            with self.assertRaises(ValueError):entry.command()

    def test_existing_safe_default_remains_list(self):
        with patch.dict(os.environ,{},clear=True):self.assertEqual(entry.command()[-1],'list')

if __name__=='__main__':unittest.main()
