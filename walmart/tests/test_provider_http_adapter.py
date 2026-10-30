"""Mock HTTP regression tests of the *actual* authorized-feed adapter.
No Walmart or third-party network access is made. No claim of authorization or real data.
"""
from __future__ import annotations
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlparse

import sys as _sys, pathlib as _pathlib
_sys.path.insert(0, str(_pathlib.Path(__file__).resolve().parent.parent))

from walmart_collector.config import categories_from_csv, stores_from_json
from walmart_collector.runner import Collector
from walmart_collector.sources import AuthorizedProviderSource, AccessChallenge, Page, SourceError
from walmart_collector.storage import LocalStorage, read_json

ROOT = Path(__file__).resolve().parent.parent
CATS = categories_from_csv(ROOT / 'config/categories.csv')
STORES = {s.store_id: s for s in stores_from_json(ROOT / 'config/stores.json')}

class FakeResponse(io.BytesIO):
    status = 200
    def __enter__(self):
        return self
    def __exit__(self, *_):
        self.close()

class ProviderHttpAdapterTests(unittest.TestCase):
    def setUp(self):
        self.source = AuthorizedProviderSource('https://approved-feed.example/api/catalog','TEST-ONLY-NOT-SECRET')

    def make_http_response(self, request, timeout=None):
        url = urlparse(request.full_url)
        params = parse_qs(url.query)
        sid = params['store_id'][0]
        category = next(x for x in CATS if x.name == params['category'][0])
        category_url = params['category_url'][0]
        cursor = params.get('cursor',[''])[0]
        import hashlib
        node = hashlib.sha256(category_url.encode()).hexdigest()[:14]
        path = ROOT / 'fixtures' / sid / category.slug / f'{node}_{cursor or "start"}.json'
        doc = json.loads(path.read_text())
        # Mock only: evidence URI is not proof; store_id/ZIP remain fixture identifiers.
        doc['location_evidence_url'] = 'https://approved-feed.example/SYNTHETIC-ONLY/location-proof'
        self.assertEqual(request.get_header('Authorization'), 'Bearer TEST-ONLY-NOT-SECRET')
        self.assertEqual(params['zipcode'][0], STORES[sid].zipcode)
        return FakeResponse(json.dumps(doc).encode())

    def test_http_adapter_single_page(self):
        with patch('walmart_collector.sources.urlopen', side_effect=self.make_http_response):
            page = self.source.fetch(STORES['100'],CATS[0],CATS[0].url,'')
        self.assertIsInstance(page, Page)
        self.assertTrue(page.store_context_verified)
        self.assertTrue(page.products)

    def test_full_collector_runs_via_mocked_http_both_stores(self):
        with tempfile.TemporaryDirectory() as tmp, patch('walmart_collector.sources.urlopen', side_effect=self.make_http_response):
            storage = LocalStorage(Path(tmp))
            for store in STORES.values():
                result = Collector(storage,self.source,CATS,min_products=11).run(store)
                data = read_json(storage, result['manifest']['data_key'])
                self.assertEqual(len(data),13)
                self.assertEqual(len(result['report']['category_counts']),11)
                self.assertTrue(all(r['zipcode']==store.zipcode for r in data))

    def test_http_adapter_fails_closed_for_403(self):
        def forbidden(request, timeout=None):
            raise HTTPError(request.full_url,403,'Forbidden',{},None)
        with patch('walmart_collector.sources.urlopen', side_effect=forbidden):
            with self.assertRaises(AccessChallenge):
                self.source.fetch(STORES['100'],CATS[0],CATS[0].url,'')

    def test_http_adapter_fails_closed_for_bad_payload(self):
        with patch('walmart_collector.sources.urlopen', return_value=FakeResponse(b'{}')):
            with self.assertRaises(SourceError):
                self.source.fetch(STORES['100'],CATS[0],CATS[0].url,'')

if __name__ == '__main__':
    unittest.main()
