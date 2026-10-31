import sys as _sys, pathlib as _pathlib
_sys.path.insert(0, str(_pathlib.Path(__file__).resolve().parent.parent))
_sys.path.insert(0, str(_pathlib.Path(__file__).resolve().parent))
import unittest
from marianos_collector.schema import make_record, make_retained_record, RecordRejected
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

    def test_the_regression_pins_both_directions(self):
        # Client finding A1: replaying 34 records rejected all 17 coupons, because
        # the whole description was searched for "cash back".
        kept = 'Save $1 on one pack. No cash back. Sign In To Clip'
        self.assertEqual(self.record(kept)['digital_deals_description'], kept)
        with self.assertRaisesRegex(RecordRejected, 'CASHBACK_MISCLASSIFIED'):
            self.record('Earn $1 cash back. Sign In To Clip')

    def test_a_real_cashback_offer_costs_the_field_not_the_product(self):
        raw = dict(store_id='53100508', zipcode='60661', seller_type='marianos',
                   fulfillment='pickup', store_context_verified=True, product_title='Battery',
                   weight='1 Count', url='https://www.marianos.com/p/battery/0003980000675',
                   digital_deals_description='$1 Cash Back. Sign In To Clip')
        store = Store('53100508', '60661', 'West Loop', '40 S Halsted St')
        record, refused = make_retained_record(raw, store, 'Batteries', '', '2026-10-28')
        self.assertEqual(record['product_title'], 'Battery')
        self.assertEqual(record['digital_deals_description'], '')
        self.assertEqual(refused[0]['reason'], 'CASHBACK_MISCLASSIFIED_AS_DIGITAL')

    def test_actual_cashback_still_rejected_even_with_prohibition(self):
        for text in ('$1 Cash Back. Sign In To Clip',
                     '$1 cashback. Sign In To Clip',
                     'No cash back if coupon exceeds price. $1 Cash Back. Sign In To Clip'):
            with self.subTest(text=text), self.assertRaisesRegex(RecordRejected,'CASHBACK_MISCLASSIFIED'):
                self.record(text)


if __name__ == '__main__':
    unittest.main()
