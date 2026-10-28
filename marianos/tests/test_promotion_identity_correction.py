import hashlib
import json
import re
import unittest
from pathlib import Path

REPORT = Path(__file__).resolve().parents[1] / 'reports' / '2026-10-28-promotion-correction'

PRIVATE = Path(__file__).resolve().parents[4] / 'outputs/Marianos_Client_Corrections_2026-10-28/B_PROMOTION_CORRECTION'

class PromotionIdentityCorrectionTests(unittest.TestCase):
    def test_compact_public_identity_consistency(self):
        fixture = json.loads((REPORT / 'IDENTITY_FIXTURE.json').read_text())
        index = json.loads((REPORT / 'PRODUCT_INDEX.json').read_text())
        readme = (REPORT / 'README.md').read_text()
        retained = {r['upc'] for r in index if r['accepted']}
        self.assertEqual(retained, set(fixture['retained_output_upcs']))
        self.assertEqual(retained, set(fixture['retained_terms_upcs']))
        self.assertEqual(retained, set(re.search(r'Retained UPCs: ([0-9, ]+)', readme)[1].split(', ')))
        self.assertIn('0007457001310', retained)
        self.assertNotIn('0007457001400', retained)
        self.assertEqual(fixture['coupon_source_upc'], '0007457001400')
        self.assertEqual(fixture['coupon_applicable_retained_upc'], '0007457001310')
        self.assertFalse(fixture['expiry_discrepancy_resolved'])
        self.assertEqual(fixture['redemption_terms_end_literal'], 'November 3')
        self.assertEqual(fixture['expiry_badge_literal'], 'Nov. 04')

    @unittest.skipUnless(PRIVATE.is_dir(), 'Private source package unavailable')
    def test_readme_output_index_and_terms_have_consistent_identities(self):
        fixture = json.loads((REPORT / 'IDENTITY_FIXTURE.json').read_text())
        self.assertEqual(hashlib.sha256((PRIVATE / 'products.json').read_bytes()).hexdigest(), fixture['private_products_sha256'])
        products = json.loads((PRIVATE / 'products.json').read_text(encoding='utf-8'))
        self.assertEqual({r['upc'] for r in products}, set(fixture['retained_output_upcs']))
        index = json.loads((PRIVATE / 'PRODUCT_INDEX.json').read_text(encoding='utf-8'))
        readme = (PRIVATE / 'README.md').read_text(encoding='utf-8')
        retained = {p['upc'] for p in products}
        self.assertEqual(retained, {r['upc'] for r in index if r['accepted']})
        self.assertEqual(retained, set(re.search(r'Retained UPCs: ([0-9, ]+)', readme)[1].split(', ')))
        self.assertIn('0007457001310', retained)
        self.assertNotIn('0007457001400', retained)
        self.assertTrue(all(len(p) == 22 for p in products))
        terms = json.loads((PRIVATE / 'PROMOTION_TERMS_AND_EXPIRY_BOUNDARY.json').read_text(encoding='utf-8'))
        self.assertEqual({r['upc'] for r in terms['retained_product_terms']}, retained)
        self.assertIn('/0007457001400?', terms['expanded_coupon_source']['source_url'])
        self.assertFalse(terms['expiry_discrepancy_resolved'])
        self.assertIn('October 21 - November 3', terms['expanded_coupon_source']['terms'])
        self.assertIn('Exp. Nov. 04', terms['expanded_coupon_source']['terms'])

    @unittest.skipUnless(PRIVATE.is_dir(), 'Private source package unavailable')
    def test_frozen_evidence_hashes_prices_and_variant_selection(self):
        audit = json.loads((PRIVATE / 'DISCREPANCY_AUDIT.json').read_text(encoding='utf-8'))
        for name, expected in audit['source_sha256'].items():
            self.assertEqual(hashlib.sha256((PRIVATE / 'source' / name).read_bytes()).hexdigest(), expected)
        parsed = json.loads((PRIVATE / 'source/website_evidence_parsed.json').read_text(encoding='utf-8'))
        web = {r['upc']: r for r in parsed}
        for row in json.loads((PRIVATE / 'PRODUCT_INDEX.json').read_text(encoding='utf-8')):
            raw = json.loads((PRIVATE / 'source' / row['api_file']).read_text(encoding='utf-8'))['data']
            self.assertEqual(raw['upc'], row['upc'])
            self.assertEqual(web[row['upc']]['observed_at'], row['website_observed_at'])
            self.assertEqual(web[row['upc']]['displayed_regular_price'], row['website_regular_price'])
            self.assertEqual(web[row['upc']]['displayed_sale_price'], row['website_sale_price'])
            primary = web[row['upc']]['observed_text'].split('  - heading "Item Availability"')[0]
            self.assertIn('UPC: ' + row['upc'], primary)
            self.assertIn('Marianos West Loop', primary)
            self.assertEqual(row['api_regular_price'], str(raw['items'][0]['price']['regular']))
        chocolate = next(r for r in audit['identity_findings'] if r['upc'] == '0007457001400')
        self.assertEqual(chocolate['historical_disposition'], 'withheld_price_conflict')
        self.assertEqual(chocolate['api_regular_price'], '6.49')
        self.assertEqual(chocolate['website_regular_price'], '6.99')

if __name__ == '__main__':
    unittest.main()
