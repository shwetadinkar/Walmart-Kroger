import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from io import BytesIO

from marianos_collector.config import categories_from_csv,stores_from_json,check_retailer_url,ConfigError
from marianos_collector.sources import FixtureSource,Page,SourceError
from marianos_collector.runner import Collector,ValidationFailure
from marianos_collector.storage import LocalStorage,read_json
from marianos_collector.schema import FIELDS,make_record,RecordRejected
from marianos_collector.kroger import Credentials,KrogerClient,KrogerError,location_candidates,diagnostic_product,trial

ROOT=Path(__file__).resolve().parent.parent
CATS=categories_from_csv(ROOT/'config/categories.csv')
STORES=stores_from_json(ROOT/'config/stores_demo.json')

class DummyResponse:
    status=200
    def __init__(self,payload):self.content=json.dumps(payload).encode()
    def __enter__(self):return self
    def __exit__(self,*a):pass
    def read(self,n):return self.content[:n]

class Tests(unittest.TestCase):
    def test_categories(self):
        self.assertEqual(len(CATS),28)
        self.assertEqual(CATS[0].name,'Coupons')
        self.assertEqual(CATS[-1].name,'Hardware Home Improvement')
        self.assertTrue(all(c.url.startswith('https://www.marianos.com/') for c in CATS))
    def test_reject_wrong_retailer_url(self):
        with self.assertRaises(ConfigError):check_retailer_url('https://www.walmart.com')
    def test_store_config(self):
        self.assertEqual({x.zipcode for x in STORES},{'60601','60661'})
    def test_schema_fields(self):
        self.assertEqual(len(FIELDS),22)
        self.assertEqual(FIELDS[-1],'crawl_date')
        self.assertEqual(FIELDS[18:21],('gupc','ppm','unit_price'))
    def product(self):
        source=FixtureSource(ROOT/'fixtures')
        return source.fetch(STORES[0],CATS[0],CATS[0].url,'').products[0]
    def test_schema_output(self):
        row=make_record(self.product(),STORES[0],'Coupons','','2026-10-20')
        self.assertEqual(list(row),list(FIELDS))
        self.assertEqual(row['gupc'],row['unit_price'])
        self.assertEqual(row['gupc'],'')
        self.assertEqual(row['store_brand'],'yes')
        self.assertEqual(row['volume_deals_description'],'2 for $5; must purchase 2')
    def test_approximate_weight_rejected(self):
        x=self.product();x['weight']='approximately 3 lb'
        with self.assertRaisesRegex(RecordRejected,'APPROXIMATE_WEIGHT'):
            make_record(x,STORES[0],'Coupons','','2026-10-20')
    def test_store_mismatch_rejected(self):
        x=self.product();x['zipcode']='99999'
        with self.assertRaisesRegex(RecordRejected,'STORE_MISMATCH'):
            make_record(x,STORES[0],'Coupons','','2026-10-20')
    def test_digital_requires_clip(self):
        x=self.product();x['digital_deals_description']='Cash back'
        with self.assertRaises(RecordRejected):
            make_record(x,STORES[0],'Coupons','','2026-10-20')
    def test_offline_publish_both_stores(self):
        with tempfile.TemporaryDirectory() as root:
            storage=LocalStorage(Path(root))
            for store in STORES:
                res=Collector(storage,FixtureSource(ROOT/'fixtures'),CATS,min_products=1).run(store)
                self.assertEqual(res['manifest']['records'],28)
                self.assertTrue(res['report']['source_is_synthetic'])
                self.assertEqual(len(res['report']['category_counts']),28)
    def test_publish_failed_threshold(self):
        with tempfile.TemporaryDirectory() as root:
            storage=LocalStorage(Path(root))
            with self.assertRaisesRegex(ValidationFailure,'Only 28'):
                Collector(storage,FixtureSource(ROOT/'fixtures'),CATS,min_products=500).run(STORES[0])
            self.assertIsNone(read_json(storage,'published/'+STORES[0].store_id+'/latest.json'))
    def test_previous_good_pointer_unchanged_on_failed_rerun(self):
        with tempfile.TemporaryDirectory() as root:
            storage=LocalStorage(Path(root))
            Collector(storage,FixtureSource(ROOT/'fixtures'),CATS,min_products=1).run(STORES[0])
            key='published/'+STORES[0].store_id+'/latest.json'; prior=read_json(storage,key)
            with self.assertRaises(ValidationFailure):
                Collector(storage,FixtureSource(ROOT/'fixtures'),CATS,min_products=500).run(STORES[0])
            self.assertEqual(prior,read_json(storage,key))
    def test_page_rejects_claim_incomplete(self):
        src=FixtureSource(ROOT/'fixtures')
        page=src.fetch(STORES[0],CATS[0],CATS[0].url,'').__dict__
        page['subcategories_complete']=False
        with tempfile.TemporaryDirectory() as root:
            class Stub:
                source_mode='authorized_provider_unverified'
                def fetch(self,*args):return Page.parse(page)
            with self.assertRaises(ValidationFailure):
                Collector(LocalStorage(Path(root)),Stub(),CATS[:2],min_products=1).run(STORES[0])
    def test_kroger_missing_credentials(self):
        with patch.dict('os.environ',{'KROGER_CLIENT_ID':'','KROGER_CLIENT_SECRET':''}):
            with self.assertRaises(KrogerError):Credentials.from_environment()
    def test_kroger_oauth_and_location(self):
        requests=[]
        def opener(req,timeout=0):
            requests.append(req)
            if req.full_url.endswith('/token'):
                return DummyResponse({'access_token':'testing','expires_in':3600})
            return DummyResponse({'data':[
               {'locationId':'12345678','name':'Marianos Lakeshore East','chain':{'name':'Mariano\'s'},
                'address':{'addressLine1':'333 E Benton Pl','zipCode':'60601','city':'Chicago'}},
               {'locationId':'87654321','name':'Other Store','chain':{'name':'Other'},
                'address':{'addressLine1':'333 E Benton Pl','zipCode':'60601','city':'Chicago'}}]})
        cli=KrogerClient(Credentials('a','b'),opener=opener,pause=0)
        result=location_candidates(cli,'60601','Benton')
        self.assertEqual([x['locationId'] for x in result],['12345678'])
        self.assertIn('filter.zipCode.near=60601',requests[1].full_url)
    def test_kroger_trial_never_contest_proof(self):
        product={'productId':'001','upc':'001','description':'Demo Milk','brand':'Private Selection',
                 'items':[{'size':'12 oz','price':{'regular':4.19,'promo':3.50}}]}
        class Fake:
            def products(self,loc,term,offset=0,limit=50):return {'data':[product]}
        r=trial(Fake(),'1234',['milk','organic'],limit_per_term=10)
        self.assertEqual(r['unique_preview_records'],1)
        self.assertFalse(r['suitable_as_contest_proof'])
        self.assertFalse(r['category_coverage_verified'])
        self.assertEqual(r['samples'][0]['regular_price'],'4.19')
        self.assertEqual(r['samples'][0]['sale_price'],'3.50')
        self.assertEqual(r['samples'][0]['ppm'],'')
    def test_kroger_path_allowlist(self):
        with self.assertRaises(KrogerError):KrogerClient(Credentials('a','b')).get('/some-undocumented-endpoint')
    def test_kroger_source_no_inferred_coupon(self):
        raw=diagnostic_product({'productId':'1','description':'milk','upc':'111','items':[{'size':'1 gal','price':{'regular':4.20,'promo':3.99}}]})
        self.assertNotIn('digital_deals_price',raw)
        self.assertEqual(raw['ppm'],'')
    def test_duplicate_per_category(self):
        with tempfile.TemporaryDirectory() as root:
            sample=FixtureSource(ROOT/'fixtures').fetch(STORES[0],CATS[0],CATS[0].url,'')
            class Repeater:
                source_mode='synthetic_fixture_duplicate'
                def fetch(self,*args):
                    from copy import deepcopy
                    x=deepcopy(sample)
                    x.products=x.products*2
                    return x
            # category URL mismatch on second category would cause fail, so use one category and expect validation failure
            with self.assertRaises(ValidationFailure):
                Collector(LocalStorage(Path(root)),Repeater(),CATS[:1],min_products=1).run(STORES[0])

if __name__=='__main__':unittest.main()
