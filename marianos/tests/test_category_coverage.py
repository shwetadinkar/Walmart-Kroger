import unittest
from marianos_collector.category_coverage import CoverageLedger


class CoverageTests(unittest.TestCase):
    def ledger(self):return CoverageLedger([{'name':'Dairy','url':'https://www.marianos.com/d/dairy'}],'53100508','60661')
    def observation(self,**changes):
        value={'url':'https://www.marianos.com/d/dairy','store_id':'53100508','zipcode':'60661',
               'store_context_verified':True,'source_kind':'rendered-retailer','observed_at':'2026-10-24T11:00:00Z',
               'snapshot_sha256':'a'*64,'status':'ok','listing_present':True,'terminal':True,
               'expected_products':2,'observed_organic_cards':2,'unique_product_urls':['/p/a/1','/p/b/2'],
               'discovery_complete':True,'children':[],'discovery_evidence_sha256':'b'*64}
        return {**value,**changes}

    def test_discovery_does_not_count_as_collection(self):
        l=self.ledger();l.discover('https://www.marianos.com/d/dairy',['https://www.marianos.com/pl/eggs/02003'])
        self.assertFalse(l.report()['all_roots_complete'])
        self.assertEqual(l.report()['roots'][0]['status'],'incomplete')

    def test_missing_root_is_not_a_legitimate_empty_category(self):
        l=self.ledger();l.observe(self.observation(status='not_found',expected_products=0,observed_organic_cards=0))
        self.assertFalse(l.report()['all_roots_complete'])
        self.assertEqual(l.report()['roots'][0]['status'],'not_found')

    def test_terminal_with_unreconciled_count_remains_incomplete(self):
        l=self.ledger();l.observe(self.observation(expected_products=3))
        self.assertFalse(l.report()['all_roots_complete'])

    def test_complete_parent_requires_every_discovered_descendant(self):
        l=self.ledger();child='https://www.marianos.com/pl/eggs/02003'
        l.observe(self.observation(children=[child]))
        self.assertFalse(l.report()['all_roots_complete'])
        l.observe(self.observation(url=child,expected_products=1,observed_organic_cards=1,unique_product_urls=['/p/a/1']))
        self.assertTrue(l.report()['all_roots_complete'])

    def test_keyword_or_synthetic_source_cannot_establish_live_completion(self):
        for source in ('keyword-api','synthetic-fixture'):
            l=self.ledger();l.observe(self.observation(source_kind=source))
            self.assertFalse(l.report()['all_roots_complete'])

    def test_wrong_store_is_rejected(self):
        with self.assertRaises(ValueError):self.ledger().observe(self.observation(store_id='53100531'))

    def test_unproven_descendant_discovery_cannot_establish_completion(self):
        l=self.ledger();l.observe(self.observation(discovery_complete=False))
        self.assertFalse(l.report()['all_roots_complete'])

    def test_no_evidence_hash_or_unzoned_time_is_rejected(self):
        for changes in ({'snapshot_sha256':''},{'observed_at':'2026-10-24T11:00:00'}):
            with self.assertRaises(ValueError):self.ledger().observe(self.observation(**changes))

    def test_budget_stop_and_blocking_cannot_be_terminal(self):
        for status in ('budget_exhausted','blocked','error'):
            l=self.ledger();l.observe(self.observation(status=status))
            self.assertFalse(l.report()['all_roots_complete'])

    def test_duplicate_card_placements_can_reconcile_to_exact_distinct_results(self):
        l=self.ledger();l.observe(self.observation(observed_listing_cards=3))
        self.assertTrue(l.report()['all_roots_complete'])

    def test_exhaustive_children_can_reconcile_an_incomplete_broad_listing(self):
        l=self.ledger();a='https://www.marianos.com/pl/eggs/02003';b='https://www.marianos.com/pl/milk/02001'
        l.observe(self.observation(expected_products=3,children=[a,b]))
        l.observe(self.observation(url=a,unique_product_urls=['/p/a/1','/p/b/2']))
        l.observe(self.observation(url=b,expected_products=1,observed_listing_cards=1,unique_product_urls=['/p/c/3']))
        self.assertTrue(l.report()['all_roots_complete'])
        self.assertEqual(l.report()['roots'][0]['completion_basis'],'exhaustive-descendant-union')

    def test_child_union_cannot_hide_an_unassigned_parent_product(self):
        l=self.ledger();a='https://www.marianos.com/pl/eggs/02003'
        l.observe(self.observation(children=[a],unique_product_urls=['/p/a/1','/p/outside/9']))
        l.observe(self.observation(url=a,unique_product_urls=['/p/a/1','/p/b/2']))
        self.assertFalse(l.report()['all_roots_complete'])
        # Neither a matching parent count nor descendant count can hide this identity conflict.
        l.observe(self.observation(children=[a],expected_products=3,unique_product_urls=['/p/a/1','/p/outside/9']))
        self.assertFalse(l.report()['all_roots_complete'])

    def test_child_cannot_introduce_a_product_missing_from_a_directly_complete_parent(self):
        l=self.ledger();child='https://www.marianos.com/pl/eggs/02003'
        l.observe(self.observation(children=[child]))
        l.observe(self.observation(url=child,expected_products=1,observed_listing_cards=1,unique_product_urls=['/p/c/3']))
        self.assertFalse(l.report()['all_roots_complete'])

    def test_equal_count_terminal_observations_with_changed_membership_are_not_stable(self):
        l=self.ledger();l.observe(self.observation())
        l.observe(self.observation(observed_at='2026-10-24T11:02:00Z',unique_product_urls=['/p/a/1','/p/c/3']))
        self.assertFalse(l.report()['all_roots_complete'])

    def test_same_set_reordered_in_repeat_observation_is_stable(self):
        l=self.ledger();l.observe(self.observation())
        l.observe(self.observation(observed_at='2026-10-24T11:02:00Z',unique_product_urls=['/p/b/2','/p/a/1']))
        self.assertTrue(l.report()['all_roots_complete'])

    def test_hierarchy_count_disagreement_blocks_an_exact_listing_count(self):
        l=self.ledger();l.observe(self.observation(hierarchy_expected_products=3))
        self.assertFalse(l.report()['all_roots_complete'])

if __name__=='__main__':unittest.main()
