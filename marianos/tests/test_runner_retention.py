import sys as _sys, pathlib as _pathlib
_sys.path.insert(0, str(_pathlib.Path(__file__).resolve().parent.parent))
_sys.path.insert(0, str(_pathlib.Path(__file__).resolve().parent))
import copy,json,tempfile,unittest
from pathlib import Path
from marianos_collector.runner import Collector,ValidationFailure
from marianos_collector.sources import Page
from marianos_collector.storage import LocalStorage,read_json,write_json
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


class ReleaseReconciliationTests(unittest.TestCase):
    """Client finding A2: a two-category repeat published four identities, then
    three, and the second report still said validated."""

    class Source:
        source_mode='synthetic_fixture_retention_replay'
        def __init__(self):self.ids=[1,2,3,4];self.reset=0
        def reset_unresolved(self):self.reset+=1
        def fetch(self,s,c,url,cursor):
            own=[i for i in self.ids if (i<=2)==(c is self.first)]
            products=[dict(store_id=s.store_id,zipcode=s.zipcode,store_context_verified=True,seller_type='marianos',
                fulfillment='pickup',product_title='Item '+str(i),weight='1 ct',url='https://www.marianos.com/p/item/'+str(i).zfill(8),
                upc=str(i).zfill(13),regular_price='2.00',observed_at=self.at) for i in own]
            return Page(s.store_id,s.zipcode,True,url,products,[],'',True)

    def setUp(self):
        self._tmp=tempfile.TemporaryDirectory();self.addCleanup(self._tmp.cleanup)
        self.store=stores_from_json(ROOT/'config/stores_demo.json')[0]
        self.cats=categories_from_csv(ROOT/'config/categories.csv')[:2]
        self.storage=LocalStorage(Path(self._tmp.name));self.source=self.Source();self.source.first=self.cats[0]
        self.collector=Collector(self.storage,self.source,self.cats,min_products=1,previous_ratio=0.1,trial=True)

    def repeat(self):
        self.source.at='2026-10-24T10:00:00Z';first=self.collector.run(self.store)
        self.source.ids=[1,3,4];self.source.at='2026-10-25T10:00:00Z'
        return first,self.collector.run(self.store)

    def test_a_two_category_repeat_keeps_every_published_identity(self):
        first,second=self.repeat()
        self.assertEqual((first['manifest']['records'],second['manifest']['records']),(4,4))
        rows=read_json(self.storage,second['manifest']['data_key'])
        self.assertEqual(next(r for r in rows if r['upc'].endswith('2'))['crawl_date'],'2026-10-24')
        self.assertEqual(next(r for r in rows if r['upc'].endswith('1'))['crawl_date'],'2026-10-25')
        self.assertEqual((second['report']['current_records'],second['report']['carried_forward_records']),(3,1))
        meta=read_json(self.storage,second['manifest']['retention_key'])
        self.assertEqual(sorted(m['observation_status'] for m in meta.values()),['carried_forward','current','current','current'])

    def test_a_release_that_loses_an_identity_does_not_validate(self):
        from unittest import mock
        import marianos_collector.runner as runner
        self.source.at='2026-10-24T10:00:00Z';self.collector.run(self.store)
        real=runner.reconcile
        def losing(*args,**kwargs):
            result=real(*args,**kwargs);result['products']=result['products'][:-1];return result
        pointer=self.storage.read('trials/'+self.collector.namespace.split('/')[1]+'/'+self.store.store_id+'/latest.json')
        self.source.ids=[1,3,4];self.source.at='2026-10-25T10:00:00Z'
        with mock.patch.object(runner,'reconcile',losing),self.assertRaisesRegex(runner.ValidationFailure,'PUBLISHED_IDENTITY_LOST'):
            self.collector.run(self.store)
        self.assertEqual(self.storage.read('trials/'+self.collector.namespace.split('/')[1]+'/'+self.store.store_id+'/latest.json'),pointer)

    def test_a_source_is_reset_on_every_run_and_keeps_its_report(self):
        self.repeat()
        self.assertEqual(self.source.reset,2)

    def test_the_release_keeps_the_composition_reporting(self):
        # marianos-fresh-runs-category-evidence deleted both from its report.
        self.source.unresolved_offers=[{'reason':'NO_MATCH'},{'reason':'NO_MATCH'}]
        self.source.provenance_report=lambda:{'spine':'catalog_v2'}
        self.source.at='2026-10-24T10:00:00Z'
        report=self.collector.run(self.store)['report']
        self.assertEqual(report['unresolved_offers']['by_reason'],{'NO_MATCH':2})
        self.assertEqual(report['provenance'],{'spine':'catalog_v2'})

    def test_a_previous_release_from_another_store_is_refused(self):
        self.source.at='2026-10-24T10:00:00Z'
        first=self.collector.run(self.store)
        rows=read_json(self.storage,first['manifest']['data_key'])
        for row in rows:row['store_location']='1720 N Milwaukee Ave, Vernon Hills, IL 60061'
        write_json(self.storage,first['manifest']['data_key'],rows)
        self.source.at='2026-10-25T10:00:00Z'
        with self.assertRaisesRegex(ValidationFailure,'PRIOR_STORE_CONTEXT_MISMATCH'):
            self.collector.run(self.store)

    def test_a_previous_release_with_no_retention_metadata_is_refused_not_guessed(self):
        self.source.at='2026-10-24T10:00:00Z'
        first=self.collector.run(self.store)
        manifest=dict(first['manifest']);manifest.pop('retention_key')
        key=first['manifest']['data_key'].replace('data.json','manifest.json')
        write_json(self.storage,key,manifest)
        self.source.at='2026-10-25T10:00:00Z'
        with self.assertRaisesRegex(ValidationFailure,'PREVIOUS_RETENTION_METADATA_REQUIRED'):
            self.collector.run(self.store)

    def test_a_bad_coupon_is_refused_in_the_collector_without_losing_the_product(self):
        source=self.source
        original=source.fetch
        def fetch(s,c,url,cursor):
            page=original(s,c,url,cursor)
            for p in page.products:p['digital_deals_description']='$1 Cash Back. Sign In To Clip'
            return page
        source.fetch=fetch;source.at='2026-10-24T10:00:00Z'
        result=self.collector.run(self.store)
        self.assertEqual(result['manifest']['records'],4)
        self.assertEqual(result['report']['values_refused_by_reason'],{'CASHBACK_MISCLASSIFIED_AS_DIGITAL':4})


if __name__ == '__main__':
    unittest.main()
