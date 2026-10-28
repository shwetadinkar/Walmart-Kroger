import unittest
from marianos_collector.schema import make_record, RecordRejected
from marianos_collector.config import Store

class CouponCashbackTermsTests(unittest.TestCase):
    def record(self, description):
        raw = dict(store_id='53100508', zipcode='60661', seller_type='marianos',
                   fulfillment='pickup', store_context_verified=True,
                   product_title='Battery', weight='1 Count',
                   url='https://www.marianos.com/p/battery/0003980000675',
                   digital_deals_description=description)
        return make_record(raw, Store('53100508','60661','West Loop','40 S Halsted St'),
                           'Cleaning and Household','Batteries','2026-10-28')

    def test_coupon_prohibition_is_preserved_without_becoming_cashback(self):
        text = 'Save $1 on one pack. No cash back. No cash back if coupon value exceeds retail price. Sign In To Clip'
        self.assertEqual(self.record(text)['digital_deals_description'], text)

    def test_actual_cashback_still_rejected_even_with_prohibition(self):
        for text in ('$1 Cash Back. Sign In To Clip',
                     '$1 cashback. Sign In To Clip',
                     'No cash back if coupon exceeds price. $1 Cash Back. Sign In To Clip'):
            with self.subTest(text=text), self.assertRaisesRegex(RecordRejected,'CASHBACK_MISCLASSIFIED'):
                self.record(text)
