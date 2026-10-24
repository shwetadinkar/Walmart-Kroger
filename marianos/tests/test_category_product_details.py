import unittest
from unittest.mock import Mock
from marianos_collector.kroger import KrogerClient,Credentials,KrogerError


class ProductDetailsTests(unittest.TestCase):
    def test_details_always_pin_the_verified_location(self):
        client=KrogerClient(Credentials('test','test'))
        client.get=Mock(return_value={'data':{'productId':'0003980014519'}})
        data=client.product_details('53100508','0003980014519')
        client.get.assert_called_once_with('/products/0003980014519',{'filter.locationId':'53100508'})
        self.assertEqual(data['data']['productId'],'0003980014519')

    def test_bad_identifiers_and_wrong_product_fail_closed(self):
        for sid,pid in [('bad','0003980014519'),('53100508','../locations')]:
            with self.assertRaises(KrogerError):KrogerClient(Credentials('test','test')).product_details(sid,pid)
        client=KrogerClient(Credentials('test','test'))
        client.get=Mock(return_value={'data':{'productId':'0003980014520'}})
        with self.assertRaises(KrogerError):client.product_details('53100508','0003980014519')

if __name__=='__main__':unittest.main()
