import unittest
from unittest.mock import Mock
from marianos_collector.rendered_categories import RenderedCategoryDriver
from marianos_collector.category_traversal import CategoryAccessBlocked

class RenderedDriverTests(unittest.TestCase):
    def test_redirect_to_another_category_cannot_be_stamped_as_requested(self):
        page=Mock();page.goto.return_value.status=200
        driver=RenderedCategoryDriver(page,'53100508','60661','Marianos West Loop','40 S Halsted St')
        driver._settled=Mock(return_value={'url':'https://www.marianos.com/pl/eggs/02003'})
        with self.assertRaisesRegex(ValueError,'REDIRECT'):
            driver._goto('https://www.marianos.com/pl/batteries/26003')

    def test_lost_store_context_fails_before_collection(self):
        page=Mock();page.evaluate.return_value={'main_text':'19 results','shopping':'Another Store'}
        driver=RenderedCategoryDriver(page,'53100508','60661','Marianos West Loop','40 S Halsted St')
        with self.assertRaisesRegex(ValueError,'STORE_CONTEXT'):
            driver._read()

    def test_200_access_denied_without_cards_is_typed_block_even_after_wait_timeout(self):
        page=Mock();page.wait_for_function.side_effect=TimeoutError()
        page.evaluate.return_value={'missing_main':True,'body':'Access Denied'}
        driver=RenderedCategoryDriver(page,'53100508','60661','Marianos West Loop','40 S Halsted St')
        with self.assertRaises(CategoryAccessBlocked):driver._settled()

if __name__=='__main__':unittest.main()
