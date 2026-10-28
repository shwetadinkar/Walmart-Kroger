import copy
import unittest
from marianos_collector.api_trial import normalize
from marianos_collector.retention import stable_identity,reconcile
from test_api_trial import product,store

class RetentionPolicyTests(unittest.TestCase):
    def setUp(self):
        self.sid='53100508';self.row=normalize(product(),store(),'2026-10-24')
    def obs(self,row,stamp):
        return {stable_identity(row,self.sid):{'observed_at':stamp,'source_refs':[{'sha256':'a'*64,'url':row['url']}],'availability_state':'available'}}
    def test_missing_price_and_unavailable_are_not_identity_filters(self):
        p=product();p['items'][0]['fulfillment']['curbside']=False;p['items'][0].pop('price')
        r=normalize(p,store(),'2026-10-24',assortment_verified=True)
        self.assertEqual(r['regular_price'],'');self.assertEqual(r['upc'],p['upc'])
    def test_missing_upcs_do_not_collapse_distinct_verified_ids(self):
        rows=[]
        for pid in ('0001111060933','0001111060934'):
            p=product(pid);p.pop('upc');rows.append(normalize(p,store(),'2026-10-24',assortment_verified=True))
        self.assertEqual([r['upc'] for r in rows],['',''])
        self.assertEqual(len({stable_identity(r,self.sid) for r in rows}),2)
    def test_absence_carries_original_dates_and_price_not_fresh(self):
        a=reconcile([self.row],self.obs(self.row,'2026-10-24T10:00:00Z'),self.sid,'2026-10-24T10:01:00Z')
        b=reconcile([],{},self.sid,'2026-10-25T10:01:00Z',a['products'],a['retention'])
        self.assertEqual(b['products'],[self.row])
        m=b['retention'][stable_identity(self.row,self.sid)]
        self.assertEqual(m['observation_status'],'carried_forward')
        self.assertEqual(m['last_observed_at'],'2026-10-24T10:00:00Z')
        self.assertEqual(m['price_observed_at']['regular_price'],'2026-10-24T10:00:00Z')
        self.assertEqual(m['last_successful_collection_at'],'2026-10-25T10:01:00Z')
    def test_current_missing_price_is_blank_and_historical_quote_stays_only_in_audit(self):
        a=reconcile([self.row],self.obs(self.row,'2026-10-24T10:00:00Z'),self.sid,'2026-10-24T10:01:00Z')
        row=copy.deepcopy(self.row);row['regular_price']='';row['crawl_date']='2026-10-25'
        b=reconcile([row],self.obs(row,'2026-10-25T10:00:00Z'),self.sid,'2026-10-25T10:01:00Z',a['products'],a['retention'])
        self.assertEqual(b['products'][0]['regular_price'],'')
        m=b['retention'][stable_identity(row,self.sid)]
        self.assertEqual(m['price_observed_at']['regular_price'],'')
        self.assertEqual(m['historical_prices']['regular_price']['value'],'2.98')
    def test_stale_input_and_duplicate_identity_do_not_refresh_prices(self):
        a=reconcile([self.row],self.obs(self.row,'2026-10-24T10:00:00Z'),self.sid,'2026-10-24T10:01:00Z')
        old=copy.deepcopy(self.row);old['regular_price']='99.99';old['crawl_date']='2026-10-23'
        b=reconcile([old,old],self.obs(old,'2026-10-23T10:00:00Z'),self.sid,'2026-10-25T10:01:00Z',a['products'],a['retention'])
        self.assertEqual(b['products'],[self.row])
        self.assertEqual(b['retention'][stable_identity(self.row,self.sid)]['carry_forward_reason'],'STALE_OBSERVATION_IGNORED')
    def test_wrong_store_prior_row_cannot_be_carried(self):
        row=copy.deepcopy(self.row);row['zipcode']='60601'
        with self.assertRaises(ValueError):reconcile([self.row],self.obs(self.row,'2026-10-24T10:00:00Z'),self.sid,'2026-10-24T10:01:00Z',[row],{})

    def test_invalid_price_and_boolean_assortment_claim_do_not_remove_or_authorize_identity(self):
        p=product();p['items'][0]['price']['regular']=float('nan')
        self.assertEqual(normalize(p,store(),'2026-10-24')['regular_price'],'')
        p['items'][0]['fulfillment']['curbside']=False
        with self.assertRaises(ValueError):normalize(p,store(),'2026-10-24',assortment_verified='false')

    def test_duplicate_nonempty_upc_with_different_retailer_id_fails_closed(self):
        a=self.row;b=copy.deepcopy(a);b['url']='https://www.marianos.com/p/different/0001111060934'
        observations={**self.obs(a,'2026-10-24T10:00:00Z'),**self.obs(b,'2026-10-24T10:00:00Z')}
        with self.assertRaisesRegex(ValueError,'UPC_IDENTITY_COLLISION'):
            reconcile([a,b],observations,self.sid,'2026-10-24T10:01:00Z')

    def test_verified_url_identity_survives_missing_product_id_or_invalid_upc(self):
        p=product();p.pop('productId');p['upc']='invalid-source-barcode'
        row=normalize(p,store(),'2026-10-24',assortment_verified=True)
        self.assertEqual(row['upc'],'')
        self.assertTrue(stable_identity(row,self.sid).endswith('0001111060933'))
