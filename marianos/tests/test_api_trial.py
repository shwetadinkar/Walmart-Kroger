import copy
import json
import tempfile
import unittest
from pathlib import Path
from marianos_collector import api_trial as api
from marianos_collector.schema import FIELDS

def store():
    return {'locationId':'53100508','chain':'MARIANOS','name':'Marianos West Loop',
            'address':{'addressLine1':'40 S Halsted St','city':'Chicago','state':'IL','zipCode':'60661'}}

def product(upc='0001111060933'):
    return {'productId':upc,'upc':upc,'description':'Kroger Eggs','brand':'Kroger',
            'productPageURI':'/p/kroger-eggs/'+upc+'?cid=source', 'categories':['Dairy'],
            'items':[{'soldBy':'UNIT','size':'18 ct','fulfillment':{'curbside':True},
                      'price':{'regular':2.98}}], 'images':[]}

class ApiTrialTests(unittest.TestCase):
    def test_verified_store_rejects_wrong_banner_zip_or_id(self):
        for field,value in [('chain','KROGER'),('locationId','01400943')]:
            s=store();s[field]=value
            with self.assertRaises(ValueError): api.verify_store(s,'53100508','60661')
        s=store();s['address']['zipCode']='60601'
        with self.assertRaises(ValueError): api.verify_store(s,'53100508','60661')

    def test_exact_schema_no_calculated_ppm_and_local_price_only(self):
        p=product();p['items'][0]['nationalPrice']={'regular':99}
        r=api.normalize(p,store(),'2026-10-24')
        self.assertEqual(list(r),list(FIELDS))
        self.assertTrue(all(isinstance(v,str) for v in r.values()))
        self.assertEqual(r['regular_price'],'2.98')
        self.assertEqual((r['ppm'],r['unit_price'],r['gupc']),('','',''))
        self.assertEqual(r['upc'],'0001111060933')
        self.assertEqual(r['category'],'Dairy')
        self.assertEqual(r['sub_category'],'')

    def test_reject_variable_weight_and_shipping_only(self):
        for field,value in [('soldBy','WEIGHT'),('size','approximately 2 lb')]:
            p=product();p['items'][0][field]=value
            with self.assertRaises(ValueError):api.normalize(p,store(),'2026-10-24')
        p=product();p['items'][0]['fulfillment']={'shipToHome':True}
        with self.assertRaises(ValueError):api.normalize(p,store(),'2026-10-24')

    def test_reject_missing_price_and_fragment_product_uri(self):
        p=product();p['items'][0].pop('price')
        with self.assertRaises(ValueError):api.normalize(p,store(),'2026-10-24')
        p=product();p['productPageURI']='/p/fake-#1/0001111060933'
        with self.assertRaises(ValueError):api.normalize(p,store(),'2026-10-24')

    def test_export_deduplicates_and_failed_import_preserves_latest(self):
        with tempfile.TemporaryDirectory() as tmp:
            src=Path(tmp)/'source';src.mkdir();out=Path(tmp)/'out'
            (src/'verified_store.json').write_text(json.dumps({'data':store()}))
            (src/'page_00.json').write_text(json.dumps({'locationId':'53100508','term':'eggs',
                'observed_at':'2026-10-24T06:00:00+00:00','response':{'data':[product(),product()]}}))
            report=api.import_snapshot(src,out,'53100508','60661',minimum=1)
            self.assertEqual(report['records'],1)
            self.assertEqual(report['duplicate_placements'],1)
            pointer=(out/'latest.json').read_bytes()
            with self.assertRaises(ValueError):api.import_snapshot(src,out,'53100508','60661',minimum=500)
            self.assertEqual((out/'latest.json').read_bytes(),pointer)
            self.assertFalse(report['submission_ready'])

    def test_mismatched_page_location_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            src=Path(tmp);(src/'verified_store.json').write_text(json.dumps({'data':store()}))
            (src/'page_00.json').write_text(json.dumps({'locationId':'53100503','term':'eggs',
                'observed_at':'2026-10-24T06:00:00+00:00','response':{'data':[product()]}}))
            with self.assertRaises(ValueError):api.import_snapshot(src,src/'out','53100508','60661',1)

    def test_website_enrichment_rejects_wrong_store_and_requires_display_evidence(self):
        r=api.normalize(product(),store(),'2026-10-24')
        e={'store_id':'53100503','upc':r['upc'],'observed_text':'$0.17/each','ppm':'$0.17/each'}
        with self.assertRaises(ValueError):api.enrich(r,e,'53100508')
        e['store_id']='53100508';e['observed_text']='other text'
        with self.assertRaises(ValueError):api.enrich(r,e,'53100508')
        e['observed_text']='UPC: '+r['upc']+' Pickup at Marianos West Loop 40 S Halsted St $0.17/each'
        self.assertEqual(api.enrich(r,e,'53100508')['ppm'],'$0.17/each')

    def test_promo_does_not_become_digital_coupon(self):
        p=product();p['items'][0]['price']['promo']=2.49
        r=api.normalize(p,store(),'2026-10-24')
        self.assertEqual(r['sale_price'],'2.49')
        self.assertEqual(r['digital_deals_description'],'')

    def test_unknown_api_category_preserved_without_inventing_csv_membership(self):
        p=product();p['categories']=['Canned & Packaged']
        self.assertEqual(api.normalize(p,store(),'2026-10-24')['category'],'Canned & Packaged')

    def test_enrichment_revalidates_price_and_paired_conditions(self):
        r=api.normalize(product(),store(),'2026-10-24')
        e={'store_id':'53100508','upc':r['upc'],
           'observed_text':'UPC: '+r['upc']+' Pickup at Marianos West Loop 40 S Halsted St Save $1 $5.00',
           'volume_deals_price':'Save $1'}
        with self.assertRaises(ValueError):api.enrich(r,e,'53100508')
        e['volume_deals_price']='5.00'
        with self.assertRaises(ValueError):api.enrich(r,e,'53100508')

    def test_changed_website_metadata_gets_distinct_immutable_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            src=Path(tmp)/'source';src.mkdir();out=Path(tmp)/'out'
            (src/'verified_store.json').write_text(json.dumps({'data':store()}))
            (src/'page_00.json').write_text(json.dumps({'locationId':'53100508','term':'eggs',
                'observed_at':'2026-10-24T06:00:00+00:00','response':{'data':[product()]}}))
            text='UPC: 0001111060933 Pickup at Marianos West Loop 40 S Halsted St'
            e={'store_id':'53100508','upc':'0001111060933','observed_text':text,'digital_details_required':False}
            api.import_snapshot(src,out,'53100508','60661',1,1,[e])
            first=json.loads((out/'latest.json').read_text())
            original=(out/first['report_key']).read_bytes()
            e['digital_details_required']=True
            api.import_snapshot(src,out,'53100508','60661',1,1,[e])
            second=json.loads((out/'latest.json').read_text())
            self.assertNotEqual(first['run'],second['run'])
            self.assertEqual((out/first['report_key']).read_bytes(),original)

    def test_material_yield_drop_cannot_replace_previous_trial(self):
        with tempfile.TemporaryDirectory() as tmp:
            src=Path(tmp)/'source';src.mkdir();out=Path(tmp)/'out'
            (src/'verified_store.json').write_text(json.dumps({'data':store()}))
            page={'locationId':'53100508','term':'eggs','observed_at':'2026-10-24T06:00:00+00:00',
                  'response':{'data':[product(),product('0001111060934')]}}
            (src/'page_00.json').write_text(json.dumps(page))
            api.import_snapshot(src,out,'53100508','60661',1,2)
            pointer=(out/'latest.json').read_bytes()
            page['response']['data']=[product()]
            (src/'page_00.json').write_text(json.dumps(page))
            with self.assertRaises(ValueError):api.import_snapshot(src,out,'53100508','60661',1,2)
            self.assertEqual((out/'latest.json').read_bytes(),pointer)

    def test_website_price_conflict_is_quarantined_not_silently_exported(self):
        with tempfile.TemporaryDirectory() as tmp:
            src=Path(tmp)/'source';src.mkdir();out=Path(tmp)/'out'
            (src/'verified_store.json').write_text(json.dumps({'data':store()}))
            (src/'page_00.json').write_text(json.dumps({'locationId':'53100508','term':'eggs',
                'observed_at':'2026-10-24T06:00:00+00:00','response':{'data':[product(),product('0001111060934')]}}))
            e={'store_id':'53100508','upc':'0001111060933',
               'observed_text':'UPC: 0001111060933 Pickup at Marianos West Loop 40 S Halsted St',
               'displayed_regular_price':'9.99'}
            r=api.import_snapshot(src,out,'53100508','60661',1,2,[e])
            self.assertEqual(r['records'],1)
            self.assertEqual(r['quarantined_records'],1)
            pointer=json.loads((out/'latest.json').read_text())
            rows=json.loads((out/pointer['data_key']).read_text())
            self.assertEqual(rows[0]['upc'],'0001111060934')

    def test_website_sale_conflict_is_quarantined_even_when_regular_matches(self):
        with tempfile.TemporaryDirectory() as tmp:
            src=Path(tmp)/'source';src.mkdir();out=Path(tmp)/'out'
            p=product();p['items'][0]['price']['promo']=2.49
            (src/'verified_store.json').write_text(json.dumps({'data':store()}))
            (src/'page_00.json').write_text(json.dumps({'locationId':'53100508','term':'eggs',
                'observed_at':'2026-10-24T06:00:00+00:00','response':{'data':[p,product('0001111060934')]}}))
            e={'store_id':'53100508','upc':'0001111060933',
               'observed_text':'UPC: 0001111060933 Pickup at Marianos West Loop 40 S Halsted St $2.98 $2.19',
               'displayed_regular_price':'2.98','displayed_sale_price':'2.19'}
            r=api.import_snapshot(src,out,'53100508','60661',1,2,[e])
            self.assertEqual(r['records'],1)
            self.assertEqual(r['quarantined_records'],1)

if __name__=='__main__': unittest.main()
