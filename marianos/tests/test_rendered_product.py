import copy
import unittest
from marianos_collector.rendered_product import parse_product, parse_collection
from marianos_collector.schema import FIELDS


class RenderedProductTests(unittest.TestCase):
    def setUp(self):
        self.store = {'id': '53100508', 'name': 'Marianos West Loop',
                      'street': '40 S Halsted St', 'zipcode': '60661'}
        self.proof = {'observed_at': '2026-10-28T04:35:00Z', 'dialogs': [{
            'text': 'Marianos West Loop\n40 S Halsted St, Chicago, IL 60661',
            'radios': [{'checked': True, 'value': '53100508'}]}]}
        self.evidence = {'observed_at': '2026-10-28T04:34:00Z',
            'url': 'https://www.marianos.com/p/test-battery/0000000000001?fulfillment=PICKUP',
            'text': 'Pickup at Marianos West Loop\n40 S Halsted St\nBreadcrumbs\nHome\nCleaning and Household\nBatteries\nTest Battery\nSkip Carousel\nTest Battery\nUPC: 0000000000001\n$16.99\n$16.99\n$16.99/each\nOption: AA\nAA\nAAA\nSize: 4 Count\n4 Count\n8 Count\nItem Availability\nPickup\nAvailable\nKroger Delivery\nUnavailable\nSavings\nCoupon\nSave $1\nShop Items\nCash Back\n$1 Cash Back\nShop Items\nDiscover More Options\n$0.01/oz'}

    def test_literal_ppm_selected_variant_and_incomplete_terms(self):
        row, audit = parse_product(self.evidence, self.store, self.proof)
        self.assertEqual(list(row), list(FIELDS))
        self.assertEqual(row['ppm'], '$16.99/each')
        self.assertEqual(row['regular_price'], '16.99')
        self.assertEqual(row['weight'], '4 Count')
        self.assertEqual(row['crawl_date'], '2026-10-28')
        self.assertEqual(row['digital_deals_description'], '')
        self.assertEqual(audit['selected_option'], 'AA')
        self.assertEqual(audit['availability_state'], 'available')
        self.assertTrue(audit['offers_pending'])

    def test_unavailable_missing_price_and_missing_upc_retain_identity(self):
        e = copy.deepcopy(self.evidence)
        e['text'] = e['text'].replace('UPC: 0000000000001\n', '').replace('$16.99\n', '').replace('$16.99/each\n', '').replace('Pickup\nAvailable', 'Pickup\nUnavailable')
        row, audit = parse_product(e, self.store, self.proof)
        self.assertEqual(row['upc'], '')
        self.assertEqual(row['regular_price'], '')
        self.assertEqual(row['ppm'], '')
        self.assertEqual(audit['availability_state'], 'unavailable')
        self.assertEqual(audit['stable_identity'], '53100508:product:0000000000001')

    def test_wrong_store_stale_proof_and_product_mismatch_fail(self):
        for mutate in ('store', 'time', 'upc'):
            e, proof = copy.deepcopy(self.evidence), copy.deepcopy(self.proof)
            if mutate == 'store': proof['dialogs'][0]['radios'][0]['value'] = '53100531'
            if mutate == 'time': proof['observed_at'] = '2026-10-24T00:00:00Z'
            if mutate == 'upc': e['text'] = e['text'].replace('UPC: 0000000000001', 'UPC: 0000000000002')
            with self.subTest(mutate=mutate), self.assertRaises(ValueError):
                parse_product(e, self.store, proof)

    def test_contradictory_price_does_not_choose_arbitrarily(self):
        e = copy.deepcopy(self.evidence)
        e['text'] = e['text'].replace('$16.99\n$16.99\n', '$16.99\n$18.99\n')
        row, audit = parse_product(e, self.store, self.proof)
        self.assertEqual(row['regular_price'], '')
        self.assertIn('AMBIGUOUS_DISPLAYED_PRICE', audit['discrepancies'])

    def test_dialog_chrome_is_not_mistaken_for_store_address(self):
        self.proof['dialogs'][0]['text'] = 'Start Your Shopping Trip\nPickup\nDelivery\n' + self.proof['dialogs'][0]['text']
        row, _ = parse_product(self.evidence, self.store, self.proof)
        self.assertEqual(row['store_location'], '40 S Halsted St, Chicago, IL 60661')

    def test_batch_emits_retention_and_rejects_mixed_windows(self):
        result = parse_collection([self.evidence], self.store, self.proof)
        identity = '53100508:product:0000000000001'
        self.assertEqual(result['retention'][identity]['last_observed_at'], self.evidence['observed_at'])
        self.assertFalse(result['acceptance']['submission_ready'])
        e = copy.deepcopy(self.evidence)
        e['observed_at'] = '2026-10-28T06:34:00Z'
        with self.assertRaises(ValueError):
            parse_collection([self.evidence, e], self.store, self.proof)
