import os
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from marianos_collector.storage import AzureBlobStorage, StorageError


class ManagedIdentityStorageTests(unittest.TestCase):
    def test_existing_container_uses_identity_without_storage_key_or_container_creation(self):
        service = Mock()
        blob = Mock(return_value=service)
        identity = Mock(return_value=object())
        modules = {
            'azure.storage.blob': SimpleNamespace(BlobServiceClient=blob),
            'azure.core.exceptions': SimpleNamespace(ResourceExistsError=Exception),
            'azure.identity': SimpleNamespace(ManagedIdentityCredential=identity),
        }
        with patch.dict('sys.modules', modules), patch.dict(os.environ, {
            'AZURE_STORAGE_ACCOUNT_URL': 'https://stwalmart63trial1024.blob.core.windows.net',
        }, clear=True):
            result = AzureBlobStorage.from_environment('retail-collection')
        identity.assert_called_once_with()
        blob.assert_called_once_with(account_url='https://stwalmart63trial1024.blob.core.windows.net', credential=identity.return_value)
        service.get_container_client.assert_called_once_with('retail-collection')
        result.container.create_container.assert_not_called()

    def test_ambiguous_identity_and_account_key_configuration_fails_closed(self):
        with patch.dict(os.environ, {
            'AZURE_STORAGE_ACCOUNT_URL': 'https://example.blob.core.windows.net',
            'AZURE_STORAGE_CONNECTION_STRING': 'private-value-never-log',
        }, clear=True):
            with self.assertRaises(StorageError): AzureBlobStorage.from_environment('retail-collection')

    def test_non_azure_account_url_is_rejected_before_credentials_are_requested(self):
        with patch.dict(os.environ, {'AZURE_STORAGE_ACCOUNT_URL':'https://example.com'}, clear=True):
            with self.assertRaises(StorageError): AzureBlobStorage.from_environment('retail-collection')

if __name__ == '__main__': unittest.main()
