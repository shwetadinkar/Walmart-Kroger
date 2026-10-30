"""Offline safety/regression tests; no Azure identity or Bright Data access."""
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import sys as _sys, pathlib as _pathlib
_sys.path.insert(0, str(_pathlib.Path(__file__).resolve().parent.parent))

from walmart_collector.schema import FIELDS
from walmart_collector.brightdata_automatic import AzureBlobStore, LocalStore, blob_smoke

STORE = {"store_id": "100", "zipcode": "72712", "store_name": "Walmart Supercenter #100"}


def sample_row(pid, category="Food"):
    item = {name: "" for name in FIELDS}
    item.update({"zipcode": "72712", "store_name": "Walmart Supercenter #100",
                 "category": category, "product_title": f"Test item {pid}",
                 "url": f"https://www.walmart.com/ip/Test-Item/{pid}",
                 "crawl_date": "2026-10-23"})
    return item


class BlobSmokeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.storage = LocalStore(self.tmp.name)
        self.filename = "Walmart_Store100_615_Trial_22Field.json"

    def tearDown(self):
        self.tmp.cleanup()

    def test_read_validate_write_audit_without_provider_or_release(self):
        rows = [sample_row(10001, "Food"), sample_row(10002, "Diapering")]
        self.storage.put(self.filename, json.dumps(rows).encode())
        report = blob_smoke(self.storage, STORE, expected_records=2)
        self.assertEqual(report["status"], "blob_read_write_succeeded")
        self.assertEqual(report["records_checked"], 2)
        self.assertEqual(report["categories"], {"Diapering": 1, "Food": 1})
        self.assertFalse(report["provider_api_called"])
        stored = json.loads(self.storage.get(report["report_blob"]))
        self.assertEqual(stored["records_checked"], 2)
        self.assertIsNone(self.storage.get("published/100/latest.json"))
        self.assertIsNone(self.storage.get("brightdata-trials/100/history.json"))
        self.assertIsNone(self.storage.get("brightdata-trials/100/latest-trial.json"))

    def test_rejects_duplicate_wrong_store_and_bad_schema_before_writing(self):
        rows = [sample_row(10001), sample_row(10001)]
        for bad_rows in (
            rows,
            [dict(sample_row(10002), zipcode="00000")],
            [dict(sample_row(10003), extra_field="wrong")],
        ):
            self.storage.put(self.filename, json.dumps(bad_rows).encode())
            with self.assertRaises(ValueError):
                blob_smoke(self.storage, STORE, expected_records=len(bad_rows))
        self.assertEqual(len(list(Path(self.tmp.name).rglob("*azure-verification*"))), 0)

    def test_fails_closed_when_file_missing(self):
        with self.assertRaises(FileNotFoundError):
            blob_smoke(self.storage, STORE, expected_records=615)

    def test_managed_identity_uses_blob_account_url_without_connection_string(self):
        azure = types.ModuleType("azure")
        storage = types.ModuleType("azure.storage")
        blob = types.ModuleType("azure.storage.blob")
        identity = types.ModuleType("azure.identity")
        credential = object()
        identity.ManagedIdentityCredential = Mock(return_value=credential)
        fake_service = Mock()
        blob.BlobServiceClient = Mock(return_value=fake_service)
        azure.storage = storage
        azure.identity = identity
        storage.blob = blob
        with patch.dict(sys.modules, {
            "azure": azure, "azure.storage": storage,
            "azure.storage.blob": blob, "azure.identity": identity,
        }):
            AzureBlobStore(container="retail-collection",
                           account_url="https://stwalmart63trial1024.blob.core.windows.net")
        blob.BlobServiceClient.assert_called_once_with(
            account_url="https://stwalmart63trial1024.blob.core.windows.net", credential=credential)
        fake_service.get_container_client.assert_called_once_with("retail-collection")
        self.assertFalse(fake_service.create_container.called)

    def test_reject_non_blob_domain(self):
        with self.assertRaises(ValueError):
            AzureBlobStore(account_url="http://evil.example.com", container="retail-collection")


if __name__ == "__main__":
    unittest.main()
