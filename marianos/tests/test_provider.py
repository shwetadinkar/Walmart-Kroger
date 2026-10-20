"""Provider contract, pagination, checkpoints and safe-failure tests."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from io import BytesIO

from marianos_collector.config import categories_from_csv,stores_from_json
from marianos_collector.sources import AuthorizedProviderSource,SourceError,AccessChallenge,Page
from marianos_collector.runner import Collector,ValidationFailure
from marianos_collector.storage import LocalStorage,read_json
from marianos_collector.cli import main

ROOT=Path(__file__).resolve().parent.parent
CAT=categories_from_csv(ROOT/'config/categories.csv')[:2]
STORE=stores_from_json(ROOT/'config/stores_demo.json')[0]

class Response:
    status=200
    def __init__(self,document):self.body=json.dumps(document).encode()
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def read(self,n):return self.body[:n]

class Tests(unittest.TestCase):
    def page(self,url):
        from marianos_collector.sources import FixtureSource
        c=next(c for c in CAT if c.url==url)
        return FixtureSource(ROOT/'fixtures').fetch(STORE,c,c.url,'').__dict__ | {'location_evidence_url':'https://www.marianos.com/stores/grocery/il/chicago'}

    def test_reject_non_https_provider(self):
        with self.assertRaises(SourceError): AuthorizedProviderSource('http://example.com','abc')

    def test_reject_retailer_as_undocumented_endpoint(self):
        with self.assertRaises(SourceError):AuthorizedProviderSource('https://www.marianos.com/undocumented','abc')

    def test_provider_http_page_contract(self):
        source=AuthorizedProviderSource('https://licensed-provider.example/category','token',max_attempts=1)
        with patch('marianos_collector.sources.urlopen',return_value=Response(self.page(CAT[0].url))) as opener:
            p=source.fetch(STORE,CAT[0],CAT[0].url,'')
        self.assertEqual(p.store_id,STORE.store_id)
        self.assertEqual(p.products[0]['seller_type'],'marianos')
        self.assertIn('category_url=',opener.call_args.args[0].full_url)
        self.assertIn('Bearer token',opener.call_args.args[0].headers['Authorization'])

    def test_provider_blocked_http_fails(self):
        source=AuthorizedProviderSource('https://licensed-provider.example/category','token',max_attempts=1)
        err=HTTPError('https://licensed-provider.example/',403,'Forbidden',{},BytesIO())
        with patch('marianos_collector.sources.urlopen',side_effect=err):
            with self.assertRaises(AccessChallenge):source.fetch(STORE,CAT[0],CAT[0].url,'')

    def test_provider_page_no_evidence_rejects_publish(self):
        class Provider:
            source_mode='authorized_provider_data_unverified_until_review'
            def fetch(self,store,cat,url,cursor):
                p=self._page(cat,url)
                p.location_evidence_url=''
                return p
            def _page(self,cat,url):return Page.parse(Tests().page(url))
        with tempfile.TemporaryDirectory() as root:
            storage=LocalStorage(Path(root))
            with self.assertRaisesRegex(ValidationFailure,'independent location evidence'):
                Collector(storage,Provider(),CAT,min_products=1).run(STORE)
            self.assertIsNone(read_json(storage,'published/'+STORE.store_id+'/latest.json'))

    def test_pagination_resume_after_crash(self):
        class Retriable:
            source_mode='authorized_provider_data_unverified_until_review'
            times=0
            def fetch(self,store,cat,url,cursor):
                self.times+=1
                if self.times==2: raise SourceError('Synthetic connection interruption')
                p=Page.parse(Tests().page(url))
                if cat.name==CAT[0].name and cursor=='':
                    p.next_cursor='page2'
                else:
                    p.next_cursor=''
                    if cat.name==CAT[0].name:
                        p.products=[]  # after first page already has a product
                return p
        with tempfile.TemporaryDirectory() as root:
            storage=LocalStorage(Path(root)); source=Retriable()
            with self.assertRaises(SourceError): Collector(storage,source,CAT,min_products=2).run(STORE)
            prior=read_json(storage,f'checkpoints/{STORE.store_id}/{CAT[0].slug}.json')
            self.assertEqual(len(prior['pages']),1)
            # Resume cursor from checkpoint; source call #3 succeeds, category #2 succeeds.
            res=Collector(storage,source,CAT,min_products=2).run(STORE)
            self.assertEqual(res['manifest']['records'],2)
            self.assertIsNone(read_json(storage,f'checkpoints/{STORE.store_id}/{CAT[0].slug}.json'))

    def test_live_run_with_demo_id_rejected(self):
        with patch.dict('os.environ',{'MARIANOS_DATA_AUTHORIZED':'yes','PROVIDER_BASE_URL':'https://licensed-provider.example','PROVIDER_API_TOKEN':'test'}):
            with tempfile.TemporaryDirectory() as root:
                with self.assertRaises(SystemExit) as exit_info:
                    main(['run','--source','provider','--authorized-source','--output',root])
                self.assertEqual(exit_info.exception.code,2)

if __name__=='__main__':unittest.main()
