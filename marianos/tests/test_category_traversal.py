"""Synthetic driver tests; these do not establish live retailer coverage."""
import tempfile
import unittest
from pathlib import Path
from marianos_collector.category_traversal import CategoryTraversal, CategoryAccessBlocked
from marianos_collector.storage import LocalStorage


ROOT='https://www.marianos.com/pl/batteries/26003'
CHILD='https://www.marianos.com/pl/aa-batteries/2600300002'

class Driver:
    source_kind='synthetic-fixture'
    def __init__(self):self.calls=[];self.fail=False
    def visit(self,url,maximum_pages):
        self.calls.append(url)
        if self.fail:raise RuntimeError('interrupted')
        return {'url':url,'store_id':'53100508','zipcode':'60661','store_context_verified':True,
                'observed_at':'2026-10-24T11:00:00Z','status':'ok','listing_present':True,
                'terminal':True,'expected_products':1,'observed_listing_cards':1,
                'unique_product_urls':['https://www.marianos.com/p/item/0001'],
                'children':[CHILD] if url==ROOT else [],'discovery_complete':True,
                'snapshot_text':'synthetic snapshot','discovery_text':'synthetic discovery','pages':1}

class TraversalTests(unittest.TestCase):
    def setup_run(self,path,driver,max_categories=10):
        return CategoryTraversal(LocalStorage(Path(path)),driver,[{'name':'Batteries','url':ROOT}],
                                 '53100508','60661','test',max_categories=max_categories,maximum_pages=2)
    def test_resumes_queue_without_replaying_completed_nodes(self):
        with tempfile.TemporaryDirectory() as p:
            d=Driver();r=self.setup_run(p,d,max_categories=1).run()
            self.assertEqual(r['pending_nodes'],1)
            r=self.setup_run(p,d,max_categories=2).run()
            self.assertEqual(d.calls,[ROOT,CHILD]);self.assertEqual(r['pending_nodes'],0)
            self.assertFalse(r['all_roots_complete'])
    def test_interruption_does_not_lose_pending_node(self):
        with tempfile.TemporaryDirectory() as p:
            d=Driver();d.fail=True
            with self.assertRaises(RuntimeError):self.setup_run(p,d).run()
            d.fail=False;r=self.setup_run(p,d).run()
            self.assertEqual(r['visited_nodes'],2)
    def test_changed_store_or_roots_cannot_reuse_checkpoint(self):
        with tempfile.TemporaryDirectory() as p:
            d=Driver();self.setup_run(p,d).run()
            with self.assertRaises(ValueError):
                CategoryTraversal(LocalStorage(Path(p)),d,[{'name':'Other','url':CHILD}],
                                  '53100508','60661','test').run()
    def test_evidence_tampering_fails_closed(self):
        with tempfile.TemporaryDirectory() as p:
            d=Driver();self.setup_run(p,d).run()
            snapshot=next(Path(p).glob('category-runs/53100508/test/evidence/*.txt'))
            snapshot.write_text('changed')
            with self.assertRaises(ValueError):self.setup_run(p,d).run()
    def test_aggregate_page_budget_persists_across_resume(self):
        with tempfile.TemporaryDirectory() as p:
            d=Driver();r=self.setup_run(p,d,max_categories=1).run()
            self.assertEqual(r['pages_observed'],1)
            r=self.setup_run(p,d,max_categories=2).run()
            self.assertEqual(r['pages_observed'],2)

    def test_access_block_is_durable_and_resume_makes_no_browser_call(self):
        with tempfile.TemporaryDirectory() as p:
            d=Driver()
            def blocked(*args):d.calls.append(ROOT);raise CategoryAccessBlocked()
            d.visit=blocked
            with self.assertRaises(CategoryAccessBlocked):self.setup_run(p,d).run()
            with self.assertRaises(CategoryAccessBlocked):self.setup_run(p,d).run()
            self.assertEqual(d.calls,[ROOT])

if __name__=='__main__':unittest.main()
