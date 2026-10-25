"""Offline configuration/orchestration acceptance; fixture source is never live proof."""
import copy,json,tempfile,unittest
from pathlib import Path
from marianos_collector.production_config import validate_discovery_config
from marianos_collector.discovery_job import run_discovery
from marianos_collector.category_traversal import CategoryAccessBlocked
from marianos_collector.storage import LocalStorage

ROOT='https://www.marianos.com/pl/batteries/26003'
CHILD='https://www.marianos.com/pl/aa-batteries/2600300002'
CONFIG={'version':1,'store':{'id':'53100508','zipcode':'60661','name':'Marianos West Loop','street':'40 S Halsted St'},'roots':[{'name':'Batteries','url':ROOT}], 'limits':{'categories':10,'pages_per_category':4,'total_pages':8,'browser_actions':50,'wall_seconds':120},'output_prefix':'discovery-review','schedule':{'enabled':False,'cron_utc':'0 6 * * 1,4'}}
class Driver:
    source_kind='synthetic-fixture'
    def __init__(self,guard,calls,fail=None):self.guard,self.calls,self.fail=guard,calls,fail
    def visit(self,url,maximum_pages):
        self.guard();self.calls.append(url)
        if self.fail==url:raise RuntimeError('sensitive text must not enter receipt')
        return {'url':url,'store_id':'53100508','zipcode':'60661','store_context_verified':True,'observed_at':'2026-10-25T12:00:00Z','status':'ok','listing_present':True,'terminal':True,'expected_products':1,'observed_listing_cards':1,'unique_product_urls':['https://www.marianos.com/p/item/0001111060933'],'children':[CHILD] if url==ROOT else [],'discovery_complete':True,'snapshot_text':'fixture listing','discovery_text':'fixture hierarchy','pages':1}
    def close(self):pass
    def capture_failure(self):return {'url':CHILD,'body_text':'fixture failed listing','source_is_synthetic':True}

class ConfiguredDiscoveryTests(unittest.TestCase):
    def test_configuration_is_strict_and_does_not_impose_500_on_subset(self):
        c=validate_discovery_config(CONFIG)
        self.assertEqual(len(c['roots']),1)
        for path,value in [('output_prefix','trials'),('output_prefix','../escape')]:
            bad=copy.deepcopy(CONFIG);bad[path]=value
            with self.assertRaises(ValueError):validate_discovery_config(bad)
        for field,value in [('total_pages',True),('wall_seconds',0),('browser_actions',1.5)]:
            bad=copy.deepcopy(CONFIG);bad['limits'][field]=value
            with self.assertRaises(ValueError):validate_discovery_config(bad)
        bad=copy.deepcopy(CONFIG);bad['secret']='never allowed'
        with self.assertRaises(ValueError):validate_discovery_config(bad)
        bad=copy.deepcopy(CONFIG);bad['schedule']['enabled']=True
        with self.assertRaises(ValueError):validate_discovery_config(bad)
    def test_resume_and_fresh_execution_are_distinct(self):
        with tempfile.TemporaryDirectory() as p:
            s=LocalStorage(Path(p));calls=[]
            with self.assertRaises(RuntimeError):run_discovery(CONFIG,s,'one',lambda c,g,t:Driver(g,calls,CHILD))
            receipt=json.loads(s.read('discovery-review/53100508/one/receipt.json'))
            self.assertEqual(receipt['status'],'failed');self.assertNotIn('sensitive',json.dumps(receipt))
            self.assertEqual(json.loads(s.read('discovery-review/53100508/one/failure-source.json'))['body_text'],'fixture failed listing')
            result=run_discovery(CONFIG,s,'one',lambda c,g,t:Driver(g,calls))
            self.assertEqual(calls,[ROOT,CHILD,CHILD]);self.assertEqual(result['pages_observed'],2)
            self.assertFalse(result['submission_ready'])
            run_discovery(CONFIG,s,'two',lambda c,g,t:Driver(g,calls))
            self.assertEqual(calls[-2:],[ROOT,CHILD])
    def test_changed_configuration_cannot_resume(self):
        with tempfile.TemporaryDirectory() as p:
            s=LocalStorage(Path(p));run_discovery(CONFIG,s,'one',lambda c,g,t:Driver(g,[]))
            bad=copy.deepcopy(CONFIG);bad['limits']['browser_actions']=51
            with self.assertRaises(ValueError):run_discovery(bad,s,'one',lambda *x:self.fail('must not launch'))
    def test_access_block_is_durable_including_store_bootstrap(self):
        with tempfile.TemporaryDirectory() as p:
            s=LocalStorage(Path(p));calls=[]
            def blocked(c,g,t):g();calls.append('bootstrap');raise CategoryAccessBlocked('blocked')
            with self.assertRaises(CategoryAccessBlocked):run_discovery(CONFIG,s,'one',blocked)
            with self.assertRaises(CategoryAccessBlocked):run_discovery(CONFIG,s,'one',blocked)
            self.assertEqual(calls,['bootstrap'])
            self.assertEqual(json.loads(s.read('discovery-review/53100508/one/receipt.json'))['status'],'access_blocked')
    def test_aggregate_page_ceiling_and_last_good_preservation(self):
        with tempfile.TemporaryDirectory() as p:
            s=LocalStorage(Path(p));s.write('trials/53100508/latest.json',b'protected')
            c=copy.deepcopy(CONFIG);c['limits']['total_pages']=1;calls=[]
            result=run_discovery(c,s,'one',lambda c,g,t:Driver(g,calls))
            self.assertEqual(calls,[ROOT]);self.assertEqual(result['pending_nodes'],1)
            self.assertEqual(s.read('trials/53100508/latest.json'),b'protected')
            run_discovery(c,s,'one',lambda c,g,t:Driver(g,calls))
            self.assertEqual(calls,[ROOT])
    def test_action_ceiling_is_persisted_across_resume(self):
        with tempfile.TemporaryDirectory() as p:
            s=LocalStorage(Path(p));c=copy.deepcopy(CONFIG);c['limits']['browser_actions']=1;calls=[]
            with self.assertRaises(RuntimeError):run_discovery(c,s,'one',lambda c,g,t:Driver(g,calls))
            with self.assertRaises(RuntimeError):run_discovery(c,s,'one',lambda c,g,t:Driver(g,calls))
            self.assertEqual(calls,[ROOT])
    def test_navigation_budget_charges_failed_bootstrap_and_prevents_resume_calls(self):
        with tempfile.TemporaryDirectory() as p:
            s=LocalStorage(Path(p));c=copy.deepcopy(CONFIG);c['limits']['total_pages']=1;calls=[]
            def failed_navigation(config,guard,remaining):
                guard('page');calls.append('navigation');raise RuntimeError('transport failure')
            with self.assertRaises(RuntimeError):run_discovery(c,s,'one',failed_navigation)
            with self.assertRaises(RuntimeError):run_discovery(c,s,'one',failed_navigation)
            self.assertEqual(calls,['navigation'])
            state=json.loads(s.read('discovery-review/53100508/one/budget.json'))
            self.assertEqual(state['page_actions'],1)

if __name__=='__main__':unittest.main()
