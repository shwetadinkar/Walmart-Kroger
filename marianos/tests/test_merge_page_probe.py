"""The page probe merge: values, conflicts and provenance, per product."""
import importlib.util
import json
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from marianos_collector.config import Store
from marianos_collector.schema import FIELDS

spec = importlib.util.spec_from_file_location('merge_page_probe', ROOT / 'tools' / 'merge_page_probe.py')
tool = importlib.util.module_from_spec(spec)
sys.modules['merge_page_probe'] = tool
spec.loader.exec_module(tool)

STORE = Store(store_id='53100502', zipcode='60061', store_name='Marianos - Marianos Vernon Hills',
              store_location='1720 N Milwaukee Ave, Vernon Hills, IL 60061')
PAGE_STORE = {'id': '53100502', 'name': 'Marianos Vernon Hills',
              'street': '1720 N Milwaukee Ave', 'zipcode': '60061'}
OBSERVED = '2026-10-31T15:00:00Z'


def row(upc, price='3.99'):
    return {**dict.fromkeys(FIELDS, ''), 'upc': upc, 'regular_price': price,
            'url': f'https://www.marianos.com/p/x/{upc}', 'product_title': 'API title'}


def pdp(upc, price, ppm='$0.33/oz'):
    text = ('Pickup at Marianos Vernon Hills\n1720 N Milwaukee Ave\nBreadcrumbs\nHome\nDairy\nMilk\n'
            f'Page title\nSkip Carousel\nPage title\nUPC: {upc}\n${price}\n${price}\n{ppm}\n'
            'Size: 12 oz\nItem Availability\nPickup\nAvailable\nSavings\nSome coupon wording')
    return {'observed_at': OBSERVED, 'url': f'https://www.marianos.com/p/x/{upc}?fulfillment=PICKUP',
            'text': text}


PROOF = {'observed_at': OBSERVED, 'dialogs': [{
    'text': 'Marianos Vernon Hills\n1720 N Milwaukee Ave, Vernon Hills, IL 60061',
    'radios': [{'checked': True, 'value': '53100502'}]}]}


class Merge(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.probe = pathlib.Path(self.dir.name)
        (self.probe / 'store.json').write_text(json.dumps(PAGE_STORE))

    def pages(self, *evidence, proof=PROOF):
        if proof:
            (self.probe / 'CURRENT_STORE.json').write_text(json.dumps(proof))
        for item in evidence:
            upc = item['url'].split('/')[-1].split('?')[0]
            (self.probe / f'PDP_{upc}.json').write_text(json.dumps(item))
        return tool.read_pages(self.probe)

    def test_page_supplies_ppm_with_its_observation(self):
        pages, unparsed = self.pages(pdp('0001', '3.99'))
        products, evidence, report = tool.merge([row('0001'), row('0002')], pages, STORE, 'r')
        self.assertEqual(unparsed, [])
        self.assertEqual([p['ppm'] for p in products], ['$0.33/oz', ''])
        ppm = evidence['0001']['fields']['ppm']
        self.assertEqual(ppm['source'], 'crawl')
        self.assertEqual((ppm['binding']['observed_at'], ppm['binding']['store_id']),
                         (OBSERVED, '53100502'))
        self.assertEqual(len(ppm['binding']['evidence_sha256']), 64)
        self.assertNotIn('ppm', evidence['0002']['fields'])
        self.assertEqual(report['conflict_count'], 0)

    def test_api_price_kept_and_conflict_recorded(self):
        pages, _ = self.pages(pdp('0001', '4.49'))
        products, evidence, report = tool.merge([row('0001')], pages, STORE, 'r')
        self.assertEqual(products[0]['regular_price'], '3.99')
        self.assertEqual(evidence['0001']['fields']['regular_price']['source'], tool.API)
        conflict = evidence['0001']['conflicts'][0]
        self.assertEqual((conflict['kept']['value'], conflict['discarded']['value']), ('3.99', '4.49'))
        self.assertEqual(report['conflict_count'], 1)

    def test_page_never_supplies_title_or_offer_wording(self):
        pages, _ = self.pages(pdp('0001', '3.99'))
        products, _, _ = tool.merge([row('0001')], pages, STORE, 'r')
        self.assertEqual(products[0]['product_title'], 'API title')
        self.assertEqual(products[0]['digital_deals_description'], '')
        self.assertEqual(products[0]['volume_deals_description'], '')

    def test_no_pages_changes_nothing_and_states_why(self):
        pages, _ = self.pages(proof=None)
        rows = [row('0001')]
        products, evidence, report = tool.merge(rows, pages, STORE, 'homepage transport failure')
        self.assertEqual(products, rows)
        self.assertEqual(report['enrichments_unavailable'], {'crawl': 'homepage transport failure'})
        self.assertEqual(evidence['0001']['fields']['regular_price']['source'], tool.API)

    def test_page_from_another_store_context_is_not_read(self):
        wrong = dict(PROOF, dialogs=[{'text': 'Marianos West Loop\n40 S Halsted St, Chicago, IL 60661',
                                      'radios': [{'checked': True, 'value': '53100508'}]}])
        pages, unparsed = self.pages(pdp('0001', '3.99'), proof=wrong)
        self.assertEqual(pages, {})
        self.assertEqual(unparsed[0]['reason'], 'EXACT_SELECTED_STORE_REQUIRED')

    def test_stop_reason_names_the_stop(self):
        reason = tool.stop_reason({'pages_served': 0, 'stopped': {
            'stage': 'store_selection', 'sign': 'net::ERR_X', 'at': 'T'}})
        self.assertIn('net::ERR_X', reason)
        self.assertIn('0 pages served', reason)


if __name__ == '__main__':
    unittest.main()
