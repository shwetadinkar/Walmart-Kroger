import unittest
from marianos_collector import website_evidence as web

TEXT = '''- region "Currently Shopping":
  - button "Pickup at Marianos West Loop, open modal to change how you are shopping":
  - generic: 40 S Halsted St
- main:
  - navigation "Breadcrumbs":
    - list:
      - link "Home":
        - /url: /
      - link "Dairy & Eggs":
        - /url: /pl/dairy-eggs/02
      - link "Milk & Dairy Free Milk":
        - /url: /pl/milk-dairy-free-milk/02001
  - heading "Test Milk" [level=1]
  - generic: "UPC: 0001111042852"
  - generic: $3.99
  - generic: $4.49
  - generic: "Sale: $3.99 discounted from $4.49"
  - generic: $0.06/fl oz
  - heading "Item Availability" [level=3]
  - generic: Pickup
  - generic: Available
  - heading "Savings" [level=2]
  - list:
    - note:
      - generic: Sale
    - generic: Save $1 each when you buy 5 or more
'''

class WebsiteEvidenceTests(unittest.TestCase):
    def test_extracts_literal_price_ppm_and_volume_conditions(self):
        e=web.parse({'store_id':'53100508','upc':'0001111042852','observed_text':TEXT})
        self.assertEqual(e['ppm'],'$0.06/fl oz')
        self.assertEqual(e['displayed_regular_price'],'4.49')
        self.assertEqual(e['displayed_sale_price'],'3.99')
        self.assertEqual(e['volume_deals_description'],'Save $1 each when you buy 5 or more')
        self.assertEqual(e['volume_deals_price'],'')
        self.assertEqual(e['breadcrumbs'],['Dairy & Eggs','Milk & Dairy Free Milk'])

    def test_coupon_teaser_stays_unverified_without_full_terms(self):
        t=TEXT.replace('generic: Sale\n    - generic: Save $1 each when you buy 5 or more',
                       'generic: Weekly Digital Deal\n    - generic: $2.49 Milk')
        e=web.parse({'store_id':'53100508','upc':'0001111042852','observed_text':t})
        self.assertTrue(e['digital_details_required'])
        self.assertEqual(e['digital_deals_description'],'')

    def test_missing_ppm_never_calculated(self):
        e=web.parse({'store_id':'53100508','upc':'0001111042852','observed_text':TEXT.replace('  - generic: $0.06/fl oz\n','')})
        self.assertEqual(e['ppm'],'')

    def test_unavailable_offer_cannot_be_called_pickup_available(self):
        e=web.parse({'store_id':'53100508','upc':'0001111042852','observed_text':TEXT.replace('generic: Available','generic: Unavailable')})
        self.assertFalse(e['pickup_available'])

if __name__=='__main__':unittest.main()
