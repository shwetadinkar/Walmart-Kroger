import sys as _sys, pathlib as _pathlib
_sys.path.insert(0, str(_pathlib.Path(__file__).resolve().parent.parent))
_sys.path.insert(0, str(_pathlib.Path(__file__).resolve().parent))
import json
import tempfile
import unittest
from pathlib import Path
from marianos_collector import api_collection as collect
from marianos_collector.storage import LocalStorage
from test_api_trial import store, product

class Client:
    def __init__(self):self.queries=[];self.location_checks=0
    def get(self,path):self.location_checks+=1;return {'data':store()}
    def products(self,location_id,term,offset,limit):
        self.queries.append(term)
        if term=='broken':raise ValueError('source failure')
        return {'data':[product('00011110609'+str(len(self.queries)).zfill(2))]}

class CollectionTests(unittest.TestCase):
    def test_query_bound_and_real_resume_without_new_product_calls(self):
        with tempfile.TemporaryDirectory() as tmp:
            storage=LocalStorage(Path(tmp));client=Client()
            a=collect.collect(client,storage,'53100508','60661','run1',['milk','bread','cheese'],2,2)
            self.assertEqual(a['unique_records'],2)
            self.assertEqual(client.queries,['milk','bread'])
            again=Client()
            b=collect.collect(again,storage,'53100508','60661','run1',['milk','bread','cheese'],2,2)
            self.assertEqual(again.queries,[])
            self.assertEqual(b['unique_records'],2)
            self.assertEqual(again.location_checks,1)

    def test_crash_keeps_successful_page_and_retry_resumes(self):
        with tempfile.TemporaryDirectory() as tmp:
            storage=LocalStorage(Path(tmp));client=Client()
            with self.assertRaises(ValueError):collect.collect(client,storage,'53100508','60661','run1',['milk','broken'],2,3)
            self.assertIsNotNone(storage.read('checkpoints/53100508/run1/page_00.json'))
            self.assertIsNone(storage.read('checkpoints/53100508/run1/page_01.json'))

    def test_checkpoint_configuration_change_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            storage=LocalStorage(Path(tmp))
            collect.collect(Client(),storage,'53100508','60661','run1',['milk'],1,1)
            with self.assertRaises(ValueError):collect.collect(Client(),storage,'53100508','60661','run1',['bread'],1,1)

    def test_network_budget_is_a_hard_ceiling(self):
        calls=[]
        def opener(*args,**kwargs):calls.append(1);return 'ok'
        limited=collect.BudgetOpener(2,opener)
        self.assertEqual(limited(None),'ok');self.assertEqual(limited(None),'ok')
        with self.assertRaises(ValueError):limited(None)
        self.assertEqual(len(calls),2)

    def test_missing_configured_canary_stops_before_page_checkpoint(self):
        with tempfile.TemporaryDirectory() as tmp:
            storage=LocalStorage(Path(tmp))
            with self.assertRaises(ValueError):
                collect.collect(Client(),storage,'53100508','60661','run1',['milk'],1,1,canary_upc='9999999999999')
            self.assertIsNone(storage.read('checkpoints/53100508/run1/page_00.json'))

if __name__=='__main__':unittest.main()
