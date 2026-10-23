"""No HTTP/network tests; representative Bright Data-shaped synthetic objects only."""
import json
from pathlib import Path
import tempfile
import unittest
from walmart_collector.brightdata_import import import_snapshots, _validate, _convert
from walmart_collector.schema import FIELDS

STORE = {"store_id": "100", "zipcode":"72712", "store_name":"Walmart Supercenter #100",
         "store_location":"406 S Walton Blvd, Bentonville, AR 72712", "store_logo":""}


def raw(id="1234", pickup=True, ts="2026-10-22T23:00:00Z"):
    return {"url": f"https://www.walmart.com/ip/a-test-product/{id}", "product_id":id,
            "product_name":"Equate Sample Protein, 12 x 11 fl oz", "zip_code":"72712",
            "pickup_zipcode":"72712", "store_id":"100", "pickup_store_id":"100",
            "retailer_store_id":"100", "seller":"Walmart.com", "retailer":"Walmart.com",
            "root_category_url":"https://www.walmart.com/cp/health/976760",
            "category_name":"Protein Shakes", "available_for_pickup": pickup,
            "pickup_extras": {"location":"Bentonville S Walton Blvd Supercenter",
                              "availability_status":"IN_STOCK" if pickup else "OUT_OF_STOCK",
                              "fulfillment_price":None},
            "final_price":20.84, "unit_price":0.158, "unit":"fl oz",
            "promotion_fulltext":"Price when purchased online", "upc":"000000000000",
            "specifications":[{"name":"Net content statement","value":"12 - 11 fl oz"},
                              {"name":"Brand","value":"Equate"}], "timestamp":ts}


class BrightDataImporterTests(unittest.TestCase):
    def test_exact_22_fields_no_inferred_price_ppm_promos(self):
        rec, e = _convert(raw(), STORE, None)
        self.assertEqual(list(rec), list(FIELDS))
        self.assertTrue(all(isinstance(v,str) for v in rec.values()))
        self.assertEqual(rec['weight'], '12 - 11 fl oz')
        self.assertEqual(rec['crawl_date'], '2026-10-22')
        self.assertEqual(rec['regular_price'], '')
        self.assertEqual(rec['sale_price'], '')
        self.assertEqual(rec['ppm'], '')
        self.assertEqual(rec['unit_price'], '')
        self.assertEqual(rec['gupc'], '')
        self.assertEqual(rec['digital_deals_description'], '')
        self.assertEqual(rec['store_brand'],'yes')
        self.assertEqual(e['online_price_candidate_unverified'],'20.84')

    def test_wrong_location_or_seller_rejected(self):
        obj=raw();obj['pickup_store_id']='5959'
        self.assertEqual(_validate(obj,'100','72712'),'STORE_ID_MISSING_OR_MISMATCHED')
        obj=raw();obj['seller']='third party'
        self.assertEqual(_validate(obj,'100','72712'),'UNVERIFIED_WALMART_SELLER')
        obj=raw();obj['root_category_url']='https://www.walmart.com/cp/toys/4171'
        self.assertEqual(_validate(obj,'100','72712'),'OUTSIDE_REQUIRED_CATEGORY_ROOTS')
        obj=raw();obj['product_id']='9999'
        self.assertEqual(_validate(obj,'100','72712'),'BAD_OR_MISMATCHED_PRODUCT_ID_URL')

    def test_approximate_size_rejected(self):
        obj=raw();obj['product_name']='Chicken approximately 1.5 lb'
        self.assertEqual(_validate(obj,'100','72712'),'APPROXIMATE_WEIGHT')

    def test_out_of_stock_kept_even_without_price(self):
        obj=raw(pickup=False)
        self.assertEqual(_validate(obj,'100','72712'),'')
        rec,e=_convert(obj,STORE,None)
        self.assertEqual(rec['regular_price'],'')
        self.assertEqual(e['pickup_status'],'OUT_OF_STOCK')

    def test_unverified_online_price_never_carried_as_verified(self):
        rec,e=_convert(raw(pickup=False),STORE,{"record":{"regular_price":"12.34"},
                                              "field_observed_at":{"regular_price":"2026-10-18T01:00:00Z"}})
        self.assertEqual(rec['regular_price'],'12.34')
        self.assertEqual(e['price_status'],'carried_prior_verified')
        self.assertEqual(e['carried_field_observed_at']['regular_price'],'2026-10-18T01:00:00Z')

    def test_run_immutable_history_and_error_audit(self):
        with tempfile.TemporaryDirectory() as tmp:
            home=Path(tmp);p=home/'snap.json'
            p.write_text(json.dumps([raw(),raw(pickup=False,id='1235'),
                                     {"error":"blocked","error_code":"detect_block"},
                                     {**raw(),"store_id":"9000"}]))
            out=home/'private'
            first,info=import_snapshots([p],STORE,out)
            self.assertEqual(info['raw_rows'],4)
            self.assertEqual(info['source_error_rows'],1)
            self.assertEqual(info['rejected_product_rows'],1)
            self.assertEqual(info['current_candidate_store_products'],2)
            self.assertEqual(info['pickup_unavailable_candidates'],1)
            self.assertFalse(info['coverage_complete'])
            exported=json.loads((first/'data_22_fields.json').read_text())
            self.assertEqual(len(exported),2)
            self.assertTrue(all(list(x)==list(FIELDS) for x in exported))
            self.assertEqual(len(json.loads((first/'rejected.json').read_text())),2)
            # Subsequent *partial* run must not silently delete missing products.
            p.write_text(json.dumps([raw(id='1234',ts='2026-10-23T02:00:00Z')]))
            second,info2=import_snapshots([p],STORE,out,first/'history.json')
            self.assertEqual(info2['current_candidate_store_products'],1)
            self.assertEqual(info2['historical_products_in_trial_export'],2)
            ev=json.loads((second/'evidence.json').read_text())
            self.assertFalse(ev['100:1235']['fresh_in_this_import'])
            self.assertEqual(json.loads((first/'data_22_fields.json').read_text()),exported)

    def test_nested_approved_category_hierarchy_and_exclusions(self):
        obj = raw()
        from walmart_collector.brightdata_import import _root_category
        cases = [
            ("0:5427:133283:1001448", "Feeding"),
            ("0:5427:486190:1101406", "Diapering"),
            ("0:1334134:5899871:9862357", "Art Supplies"),
            ("0:2637:1042319:1212898:3956207:2726275", "Balloons"),
            ("0:1229749:4796182", "Office Supplies"),
        ]
        for ids, category in cases:
            item = dict(obj, category_ids=ids,
                        root_category_url="https://www.walmart.com/cp/baby/5427")
            self.assertEqual(_validate(item, '100', '72712'), '', ids)
            self.assertEqual(_root_category(item), category)
        sentinel = dict(obj, category_ids="-1",
                        root_category_url="https://www.walmart.com/cp/household-essentials/1115193")
        self.assertEqual(_validate(sentinel, '100', '72712'), '')
        self.assertEqual(_root_category(sentinel), "Household Essentials")
        wrong = dict(obj, category_ids="0:3944:133251:1230476",
                     related_pages=["/browse/baby/food/5427_133283"])
        self.assertEqual(_validate(wrong, '100', '72712'), "OUTSIDE_REQUIRED_CATEGORY_ROOTS")
        farm = dict(obj, category_ids="0:5440:202072", category_name="Farm Animals")
        self.assertEqual(_validate(farm, '100', '72712'), "OUTSIDE_REQUIRED_CATEGORY_ROOTS")
        recipes = dict(obj, category_ids="0:976759:12345", category_name="Recipes")
        self.assertEqual(_validate(recipes, '100', '72712'), "OUTSIDE_REQUIRED_CATEGORY_ROOTS")

    def test_missing_descriptive_fields_preserve_prior_evidence(self):
        item = raw()
        item["category_name"] = ""
        prev = {"record": {"sub_category": "Protein Shakes"},
                "field_observed_at": {"sub_category": "2026-10-20T01:00:00Z"}}
        record, provenance = _convert(item, STORE, prev)
        self.assertEqual(record["sub_category"], "Protein Shakes")
        self.assertIn("sub_category", provenance["carried_fields"])
        self.assertEqual(provenance["carried_field_observed_at"]["sub_category"],
                         "2026-10-20T01:00:00Z")

    def test_repeat_seen_latest_timestamp(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'input.json'
            p.write_text(json.dumps([raw(ts='2026-10-22T10:00:00Z'),
                                     raw(ts='2026-10-22T23:00:00Z')]))
            _,m=import_snapshots([p],STORE,Path(tmp)/'out')
            self.assertEqual(m['duplicate_product_rows'],1)
            self.assertEqual(m['current_candidate_store_products'],1)

if __name__=='__main__':unittest.main()