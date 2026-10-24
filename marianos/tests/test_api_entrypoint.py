import importlib.util
import os
from pathlib import Path
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('container_entrypoint',Path(__file__).resolve().parents[1]/'azure/container_entrypoint.py')
entry=importlib.util.module_from_spec(spec);spec.loader.exec_module(entry)

class EntrypointTests(unittest.TestCase):
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
