import copy,json,tempfile,unittest
from pathlib import Path
from marianos_collector.api_trial import import_snapshot,normalize,enrich
from test_api_trial import product,store

class RetentionIntegrationTests(unittest.TestCase):
    def snapshot(self,src,products,at):
        src.mkdir(exist_ok=True)
        (src/'verified_store.json').write_text(json.dumps({'data':store()}))
        (src/'page_00.json').write_text(json.dumps({'locationId':'53100508','observed_at':at,'response':{'data':products}}))
    def output(self,out):
        p=json.loads((out/'latest.json').read_text());return p,json.loads((out/p['data_key']).read_text())
    def test_unavailable_and_missing_price_import_and_enrich_do_not_drop_identity(self):
        with tempfile.TemporaryDirectory() as d:
            src=Path(d)/'src';out=Path(d)/'out';p=product();p['items'][0]['fulfillment']['curbside']=False;p['items'][0].pop('price')
            self.snapshot(src,[p],'2026-10-24T10:00:00Z')
            r=import_snapshot(src,out,'53100508','60661',1,10)
            pointer,rows=self.output(out)
            self.assertEqual(len(rows),1);self.assertEqual(rows[0]['regular_price'],'')
            self.assertTrue((out/pointer['retention_key']).is_file())
            e={'upc':rows[0]['upc'],'store_id':'53100508','pickup_available':False,
               'primary_text':'UPC: '+rows[0]['upc']+'\nPickup\nOut of Stock',
               'observed_text':'UPC: '+rows[0]['upc']+' Pickup at Marianos West Loop 40 S Halsted St'}
            self.assertEqual(enrich(rows[0],e,'53100508')['upc'],rows[0]['upc'])
    def test_absent_product_is_accumulated_and_old_date_preserved(self):
        with tempfile.TemporaryDirectory() as d:
            src=Path(d)/'src';out=Path(d)/'out';ps=[product('000111106093'+str(i)) for i in range(5)]
            self.snapshot(src,ps,'2026-10-24T10:00:00Z');import_snapshot(src,out,'53100508','60661',1,10)
            self.snapshot(src,ps[1:],'2026-10-25T10:00:00Z');r=import_snapshot(src,out,'53100508','60661',1,10)
            pointer,rows=self.output(out);self.assertEqual(len(rows),5);self.assertEqual(r['carried_forward_records'],1)
            absent=next(x for x in rows if x['upc']==ps[0]['upc']);self.assertEqual(absent['crawl_date'],'2026-10-24')
    def test_blank_upcs_remain_distinct_through_import(self):
        with tempfile.TemporaryDirectory() as d:
            src=Path(d)/'src';out=Path(d)/'out';ps=[product('0001111060933'),product('0001111060934')]
            for p in ps:p.pop('upc')
            self.snapshot(src,ps,'2026-10-24T10:00:00Z');import_snapshot(src,out,'53100508','60661',1,10)
            _,rows=self.output(out);self.assertEqual(len(rows),2);self.assertEqual([r['upc'] for r in rows],['',''])

    def test_inventory_not_pickup_capability_sets_availability_state(self):
        with tempfile.TemporaryDirectory() as d:
            src=Path(d)/'src';out=Path(d)/'out';p=product()
            p['items'][0]['inventory']={'stockLevel':'TEMPORARILY_OUT_OF_STOCK'}
            self.snapshot(src,[p],'2026-10-24T10:00:00Z');import_snapshot(src,out,'53100508','60661',1,10)
            pointer,_=self.output(out)
            metadata=json.loads((out/pointer['retention_key']).read_text())
            self.assertEqual(next(iter(metadata.values()))['availability_state'],'unavailable')
