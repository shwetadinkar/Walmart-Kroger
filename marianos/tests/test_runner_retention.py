import copy,json,tempfile,unittest
from pathlib import Path
from marianos_collector.runner import Collector
from marianos_collector.sources import Page
from marianos_collector.storage import LocalStorage,read_json
from marianos_collector.config import categories_from_csv,stores_from_json
ROOT=Path(__file__).resolve().parent.parent
class RunnerRetentionTests(unittest.TestCase):
    def test_single_configured_category_retains_absent_identity_and_blank_upcs(self):
        store=stores_from_json(ROOT/'config/stores_demo.json')[0];cats=categories_from_csv(ROOT/'config/categories.csv')[:1]
        class Source:
            source_mode='synthetic_fixture_retention_replay';second=False
            def fetch(self,s,c,url,cursor):
                ids=range(1,5) if self.second else range(5)
                products=[dict(store_id=s.store_id,zipcode=s.zipcode,store_context_verified=True,seller_type='marianos',
                    fulfillment='pickup',product_title='Controlled '+str(i),weight='1 ct',url='https://www.marianos.com/p/controlled/'+str(i).zfill(8),
                    upc='',regular_price='' if self.second else '2.00',observed_at='2026-10-25T10:00:00Z' if self.second else '2026-10-24T10:00:00Z') for i in ids]
                return Page(s.store_id,s.zipcode,True,url,products,[],'',True)
        with tempfile.TemporaryDirectory() as d:
            storage=LocalStorage(Path(d));source=Source();collector=Collector(storage,source,cats,min_products=1,trial=True)
            a=collector.run(store);source.second=True;b=collector.run(store)
            rows=read_json(storage,b['manifest']['data_key'])
            self.assertEqual(len(rows),5)
            self.assertEqual(b['report']['current_records'],4)
            self.assertEqual(b['report']['carried_forward_records'],1)
            old=next(r for r in rows if r['url'].endswith('00000000'))
            self.assertEqual((old['crawl_date'],old['regular_price']),('2026-10-24','2.00'))
            meta=read_json(storage,b['manifest']['retention_key'])
            self.assertEqual(len(meta),5)
