import unittest
from marianos_collector.api_trial import normalize
from marianos_collector.temporal_enrichment import merge_export
from test_api_trial import product,store


class TemporalEnrichmentTests(unittest.TestCase):
    def setUp(self):
        self.row=normalize(product(),store(),'2026-10-24')
        self.provenance={self.row['upc']:{'observed_at':'2026-10-24T10:00:00Z'}}
        self.e={'upc':self.row['upc'],'store_id':'53100508','url':self.row['url'],
                'observed_at':'2026-10-24T10:05:00Z','ppm':'$0.17/each',
                'displayed_regular_price':'2.98','displayed_sale_price':'','pickup_available':True,
                'observed_text':'Pickup at Marianos West Loop 40 S Halsted St UPC: '+self.row['upc']+' $2.98 $0.17/each'}

    def merge(self,e=None):return merge_export([self.row],self.provenance,[e or self.e],store())

    def test_matching_source_and_time_copy_literal_ppm_with_field_provenance(self):
        result=self.merge()
        self.assertEqual(result['products'][0]['ppm'],'$0.17/each')
        self.assertEqual(self.row['ppm'],'')
        field=result['provenance'][self.row['upc']]['website_fields']['ppm']
        self.assertEqual(field['observed_at'],self.e['observed_at'])

    def test_old_evidence_is_not_applied_or_used_to_quarantine_current_prices(self):
        e={**self.e,'observed_at':'2026-10-24T06:00:00Z','displayed_regular_price':'9.99'}
        result=self.merge(e)
        self.assertEqual(result['products'],[self.row]);self.assertEqual(result['quarantine'],[])
        self.assertEqual(result['rejected_evidence'][0]['reason'],'OBSERVATION_TIME_GAP')

    def test_current_price_conflict_preserves_both_values_in_quarantine(self):
        result=self.merge({**self.e,'displayed_regular_price':'3.99'})
        self.assertEqual(result['products'],[])
        self.assertEqual(result['quarantine'][0]['api_record']['regular_price'],'2.98')
        self.assertEqual(result['quarantine'][0]['website_evidence']['displayed_regular_price'],'3.99')

    def test_wrong_store_or_product_url_cannot_enrich(self):
        for change in ({'store_id':'53100503'},{'url':'https://www.marianos.com/p/other/0001111060934'}):
            result=self.merge({**self.e,**change})
            self.assertEqual(result['products'],[self.row]);self.assertTrue(result['rejected_evidence'])

    def test_unzoned_timestamp_is_rejected(self):
        result=self.merge({**self.e,'observed_at':'2026-10-24T10:05:00'})
        self.assertEqual(result['products'],[self.row]);self.assertEqual(result['products'][0]['ppm'],'')

    def test_unobserved_and_incomplete_digital_conditions_are_not_populated(self):
        e={**self.e,'digital_deals_description':'Clip Coupon: Save $1',
           'observed_text':self.e['observed_text']+' Clip Coupon: Save $1'}
        result=self.merge(e)
        self.assertEqual(result['products'][0]['digital_deals_description'],'')
        self.assertEqual(result['report']['digital_details_pending'],1)

    def test_missing_website_regular_price_is_unverified_not_a_price_conflict(self):
        result=self.merge({**self.e,'displayed_regular_price':''})
        self.assertEqual(result['products'],[self.row])
        self.assertEqual(result['quarantine'],[])
        self.assertTrue(result['rejected_evidence'])

if __name__=='__main__':unittest.main()
