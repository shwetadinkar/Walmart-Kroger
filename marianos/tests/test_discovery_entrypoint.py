import importlib.util,os,unittest
from pathlib import Path
from unittest.mock import patch
spec=importlib.util.spec_from_file_location('discovery_entrypoint',Path(__file__).resolve().parents[1]/'azure/container_entrypoint.py')
entry=importlib.util.module_from_spec(spec);spec.loader.exec_module(entry)
ENV={'MARIANOS_MODE':'discovery','MARIANOS_STORE_ID':'53100508','MARIANOS_ZIPCODE':'60661','AZURE_BLOB_CONTAINER':'retail-collection','CONTAINER_APP_JOB_NAME':'marianos-westloop-api-pilot','CONTAINER_APP_JOB_EXECUTION_NAME':'probe-a'}
class DiscoveryEntrypointTests(unittest.TestCase):
    def test_explicit_mode_uses_verified_config_and_stable_execution_identity(self):
        with patch.dict(os.environ,ENV,clear=True):first=entry.command();second=entry.command()
        self.assertEqual(first,second)
        self.assertEqual(first[2],'marianos_collector.discovery_job')
        self.assertEqual(first[first.index('--container')+1],'retail-collection')
        self.assertTrue(first[first.index('--run-id')+1].startswith('azure-'))
        with patch.dict(os.environ,{**ENV,'CONTAINER_APP_JOB_EXECUTION_NAME':'probe-b'},clear=True):other=entry.command()
        self.assertNotEqual(first[first.index('--run-id')+1],other[other.index('--run-id')+1])
    def test_store_and_zip_must_match_shipped_configuration(self):
        for change in ({'MARIANOS_STORE_ID':'53100531'},{'MARIANOS_ZIPCODE':'60601'}):
            with patch.dict(os.environ,{**ENV,**change},clear=True):
                with self.assertRaises(ValueError):entry.command()
    def test_missing_identity_or_store_fails_before_launch(self):
        for key in ('CONTAINER_APP_JOB_EXECUTION_NAME','MARIANOS_STORE_ID'):
            env={k:v for k,v in ENV.items() if k!=key}
            with patch.dict(os.environ,env,clear=True):
                with self.assertRaises(ValueError):entry.command()
    def test_discovery_config_cannot_read_outside_shipped_config_directory(self):
        for name in ('../../private/credentials.json','/tmp/config.json','..json'):
            with patch.dict(os.environ,{**ENV,'MARIANOS_DISCOVERY_CONFIG':name},clear=True):
                with self.assertRaises(ValueError):entry.command()

if __name__=='__main__':unittest.main()
