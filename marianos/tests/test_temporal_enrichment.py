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
        self.assertEqual(len(result['products']),1)
        self.assertEqual(result['products'][0]['regular_price'],'')
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

    def test_volume_teaser_without_verified_full_terms_stays_pending(self):
        e={**self.e,'volume_deals_description':'Save $1 each when you buy 5 or more',
           'observed_text':self.e['observed_text']+' Save $1 each when you buy 5 or more'}
        result=self.merge(e)
        self.assertEqual(result['products'][0]['volume_deals_description'],'')
        self.assertEqual(result['report']['volume_details_pending'],1)

    def test_merge_does_not_infer_live_source_status_from_arbitrary_inputs(self):
        self.assertIsNone(self.merge()['report']['source_is_synthetic'])

    def test_complete_offer_can_join_exact_displayed_passages_without_paraphrasing(self):
        parts=['Buy any 5 participating items.', 'Mix and match. No coupon needed.']
        e={**self.e,'volume_terms_complete':True,'volume_deals_description':'\n'.join(parts),
           'displayed_fragments':{'volume_deals_description':parts},
           'observed_text':self.e['observed_text']+'\n'+parts[0]+'\nNavigation\n'+parts[1]}
        result=self.merge(e)
        self.assertEqual(result['products'][0]['volume_deals_description'],'\n'.join(parts))
        self.assertEqual(result['products'][0]['volume_deals_price'],'')

    def test_offer_fragment_metadata_cannot_authorize_altered_or_absent_text(self):
        for parts in (['Buy 5', 'Invented extra saving'], ['', 'Buy 5'], 'Buy 5'):
            e={**self.e,'volume_terms_complete':True,'volume_deals_description':'Buy 5\nSave $2',
               'displayed_fragments':{'volume_deals_description':parts},
               'observed_text':self.e['observed_text']+' Buy 5 Save $2'}
            self.assertEqual(self.merge(e)['products'][0]['volume_deals_description'],'')

    def test_fragments_cannot_assemble_a_computed_ppm(self):
        e={**self.e,'ppm':'$0.17/oz','observed_text':self.e['observed_text']+' $0.17 /oz',
           'displayed_fragments':{'ppm':['$0.17','/oz']}}
        self.assertEqual(self.merge(e)['products'][0]['ppm'],'')

    def test_malformed_fragment_container_is_rejected_without_crashing_merge(self):
        for malformed in (['Buy 5'], 'Buy 5', 7):
            e={**self.e,'volume_terms_complete':True,'volume_deals_description':'Buy 5\nSave $2',
               'displayed_fragments':malformed}
            self.assertEqual(self.merge(e)['products'][0]['volume_deals_description'],'')

    def test_fragments_cannot_truncate_prices_or_reorder_offer_conditions(self):
        for text,parts in (
            ('Buy 5 participating items. Save $20 when you buy 50.', ['Save $2','Buy 5']),
            ('Buy 5 participating items.\nSave $20 when you buy 50.', ['Save $20 when you buy 50.','Buy 5 participating items.']),
            ('Buy 5 participating items.\nSave $20 when you buy 50.', ['Buy 5 participating items.','Save $2']),
        ):
            e={**self.e,'volume_terms_complete':True,'volume_deals_description':'\n'.join(parts),
               'displayed_fragments':{'volume_deals_description':parts},
               'observed_text':self.e['observed_text']+'\n'+text}
            self.assertEqual(self.merge(e)['products'][0]['volume_deals_description'],'')

    def test_unfinished_or_unavailable_variant_cannot_enrich_a_good_api_record(self):
        for change in (
            {'selection_complete':False},
            {'observed_text':self.e['observed_text']+' This selection is unavailable. Please choose another option.'},
            {'primary_text':'Option: 9-Watt (60-Watt)\nSize:\nButton Group Options\n2 pk\n4 pk'},
        ):
            result=self.merge({**self.e,**change})
            self.assertEqual(result['products'][0]['ppm'],'')
            self.assertEqual(result['rejected_evidence'][0]['reason'],'WEBSITE_VARIANT_SELECTION_UNUSABLE')

    def test_unfinished_variant_price_does_not_quarantine_the_valid_api_record(self):
        result=self.merge({**self.e,'selection_complete':False,'displayed_regular_price':'99.99'})
        self.assertEqual(result['quarantine'],[])
        self.assertEqual(result['products'],[self.row])

    def test_resolved_out_of_stock_variant_stays_in_assortment_with_unpriced_record(self):
        e={**self.e,'pickup_available':False,
           'primary_text':'UPC: '+self.row['upc']+'\nOption: Large\nSize: 18 ct\nThis selection is unavailable. Please choose another option.\nPickup\nOut of Stock'}
        result=self.merge(e)
        self.assertEqual(len(result['products']),1)
        self.assertEqual(result['products'][0]['upc'],self.row['upc'])
        self.assertEqual(result['products'][0]['regular_price'],'')
        self.assertEqual(result['quarantine'],[])
        self.assertEqual(result['availability_audit'][0]['status'],'pickup_unavailable')
        self.assertEqual(result['availability_audit'][0]['api_record'],self.row)

    def test_malformed_selection_complete_flag_cannot_authorize_enrichment(self):
        for value in ('false',0,None):
            result=self.merge({**self.e,'selection_complete':value})
            self.assertEqual(result['products'][0]['ppm'],'')

    def test_an_old_primary_upc_plus_a_matching_recommendation_cannot_quarantine_api(self):
        for notice in ('This selection is unavailable.',''):
            e={**self.e,'pickup_available':False,
               'primary_text':'UPC: 0001111060934\n'+notice+'\nRecommended UPC: '+self.row['upc']}
            result=self.merge(e)
            self.assertEqual(result['quarantine'],[])
            self.assertEqual(result['products'],[self.row])

    def test_unavailable_missing_price_and_conflicting_price_both_preserve_identity(self):
        for price in ('', '999.99'):
            e={**self.e,'pickup_available':False,'displayed_regular_price':price,
               'primary_text':'UPC: '+self.row['upc']+'\nPickup\nOut of Stock'}
            result=self.merge(e)
            self.assertEqual(len(result['products']),1)
            row=result['products'][0]
            self.assertEqual(list(row),list(self.row))
            for field in ('regular_price','sale_price','ppm','volume_deals_description','volume_deals_price','digital_deals_description','digital_deals_price'):
                self.assertEqual(row[field],'')
            self.assertEqual(result['availability_audit'][0]['website_evidence'],e)
            self.assertEqual(result['report']['unavailable_records_retained'],1)
            self.assertEqual(self.row['regular_price'],'2.98')

    def test_stale_or_wrong_store_unavailability_does_not_blank_current_record(self):
        for change in ({'store_id':'53100503'},{'observed_at':'2026-10-23T10:00:00Z'}):
            e={**self.e,'pickup_available':False,'primary_text':'UPC: '+self.row['upc'],**change}
            result=self.merge(e)
            self.assertEqual(result['products'],[self.row])
            self.assertEqual(result['availability_audit'],[])

    def test_unknown_availability_cannot_erase_api_prices(self):
        changes=[{'observed_text':''},{'primary_text':''},
                 {'primary_text':'UPC: '+self.row['upc']+'\nPickup'},
                 {'observed_text':'UPC: '+self.row['upc']+' Pickup Out of Stock'}]
        for change in changes:
            e={**self.e,'pickup_available':False,
               'primary_text':'UPC: '+self.row['upc']+'\nPickup\nOut of Stock',**change}
            result=self.merge(e)
            self.assertEqual(result['products'],[self.row])
            self.assertEqual(result['availability_audit'],[])
            self.assertTrue(result['rejected_evidence'])

    def test_verified_website_price_fills_missing_api_price_with_website_timestamp(self):
        self.row['regular_price']='';self.row['sale_price']=''
        e={**self.e,'displayed_regular_price':'2.98','displayed_sale_price':'2.49',
            'observed_text':self.e['observed_text']+' Sale $2.49'}
        result=self.merge(e);row=result['products'][0]
        self.assertEqual((row['regular_price'],row['sale_price']),('2.98','2.49'))
        identity=next(iter(result['retention']))
        self.assertEqual(result['retention'][identity]['price_observed_at']['regular_price'],e['observed_at'])
        self.assertEqual(result['retention'][identity]['price_observed_at']['sale_price'],e['observed_at'])

    def test_substring_price_is_not_a_direct_displayed_price(self):
        self.row['regular_price']=''
        e={**self.e,'displayed_regular_price':'2.98','observed_text':self.e['observed_text'].replace('$2.98','$12.98')}
        self.assertEqual(self.merge(e)['products'][0]['regular_price'],'')

if __name__=='__main__':unittest.main()
