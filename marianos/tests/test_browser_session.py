import unittest
from marianos_collector.browser_session import assert_accessible,verify_rendered_store
from marianos_collector.category_traversal import CategoryAccessBlocked

class Response:
    def __init__(self,status):self.status=status

class BrowserSetupTests(unittest.TestCase):
    def test_http_and_rendered_restrictions_stop_without_retry(self):
        for status,text in [(403,'Forbidden'),(429,'Busy'),(200,'Please verify you are human'),(200,'Access Denied')]:
            with self.assertRaises(CategoryAccessBlocked):assert_accessible(Response(status),text)
        assert_accessible(Response(200),'Normal store products')
    def test_wrong_store_or_unproved_grid_is_not_accepted(self):
        store={'id':'53100508','name':'Marianos West Loop','street':'40 S Halsted St','zipcode':'60661'}
        verify_rendered_store(store,'Pickup at Marianos West Loop | 40 S Halsted St','00508')
        for text,grid in [('Pickup at Marianos West Loop | 40 S Halsted St','00531'),('Pickup at Other | 40 S Halsted St','00508'),('Pickup at Marianos West Loop | Other Street','00508')]:
            with self.assertRaises(ValueError):verify_rendered_store(store,text,grid)

if __name__=='__main__':unittest.main()
