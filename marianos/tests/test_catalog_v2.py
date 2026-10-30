"""Kroger Catalog V2 adapter: contract mapping, store binding and honest blanks.

Every payload here is shaped exactly as Kroger's published Catalog V2 OpenAPI
1.5.5 document defines it, including the two different money spellings the
contract uses in the same response ("$4.99" on defaultDescription, "USD 18.00"
on nFor.price and unit).

These tests are what make the adapter provable without partner credentials.
They are not evidence that an entitlement exists, and none of them talk to the
network.
"""
import json
import unittest
from pathlib import Path
from urllib.error import HTTPError

from marianos_collector.catalog_v2 import (
    CatalogV2Client,
    CatalogV2Error,
    CatalogV2Source,
    Credentials,
    _money,
    _volume_deal,
)
from marianos_collector.config import Category, Store, stores_from_json
from marianos_collector.schema import RecordRejected, make_record
from marianos_collector.sources import AccessChallenge

ROOT = Path(__file__).resolve().parent.parent
STORE = Store(
    store_id="70100485",
    zipcode="60661",
    store_name="Mariano's West Loop",
    store_location="Chicago, IL",
    store_logo="",
)
CATEGORY = Category(name="Dairy", url="https://www.marianos.com/c/dairy")
LOCATION_ID = "70100485"


def product(
    upc="0001111041700",
    name="Simple Truth 2% Reduced Fat Milk",
    regular="$4.99",
    promo=None,
    n_for=None,
    unit="USD 5.00",
    location_id=LOCATION_ID,
    url="https://www.marianos.com/p/simple-truth-2-milk/0001111041700",
    categories=None,
):
    """Build one Catalog V2 product exactly as the contract shapes it."""
    regular_block = {
        "defaultDescription": regular,
        "description": "Regular price",
        "soldBy": "UNIT",
        "unit": unit,
        "effectiveDate": {"value": "2026-11-01"},
        "expiredDate": {"value": "2026-11-30"},
    }
    promo_block = {}
    if promo or n_for:
        promo_block = {
            "defaultDescription": promo,
            "promoDescription": promo,
            "description": "Offer price",
            "soldBy": "UNIT",
        }
        if n_for:
            promo_block["nFor"] = {"quantity": n_for[0], "price": n_for[1]}
    return {
        "upc": upc,
        "name": name,
        "productPageURL": url,
        "brand": {"name": "Simple Truth"},
        "categories": categories
        if categories is not None
        else [{"name": "Milk", "parent": {"name": "Dairy"}}],
        "metadata": {"size": "1 gal", "averageWeightPerUnit": "0.3 [lb_av]"},
        "images": [{"sizes": [{"url": "https://www.marianos.com/i/milk.jpg"}]}],
        "locations": [
            {
                "id": location_id,
                "inventory": [
                    {
                        "instock": True,
                        "stock": {"level": "HIGH"},
                        "prices": [
                            {
                                "regular": regular_block,
                                "promo": promo_block,
                                "discountLabel": "YellowTag",
                            }
                        ],
                    }
                ],
            }
        ],
    }


def page(products, has_more=False, offset=0):
    return {"data": products, "meta": {"page": {"offset": offset, "size": 50, "hasMore": has_more}}}


class FakeClient:
    """Stands in for CatalogV2Client, returning prepared pages in order."""

    scope = "product.compact"

    def __init__(self, pages, raises=None):
        self.pages = list(pages)
        self.raises = raises
        self.calls = []

    def get(self, path, params):
        self.calls.append((path, dict(params)))
        if self.raises:
            raise self.raises
        return self.pages.pop(0) if self.pages else page([])


def source(client, **kwargs):
    return CatalogV2Source(client, LOCATION_ID, fulfillment="curbside", **kwargs)


class MoneyTests(unittest.TestCase):
    def test_both_contract_money_spellings_reduce_to_a_bare_amount(self):
        # The contract really does use both in one response.
        self.assertEqual(_money("$4.99"), "4.99")
        self.assertEqual(_money("USD 18.00"), "18.00")
        self.assertEqual(_money("18.00"), "18.00")

    def test_unreadable_money_is_blank_never_guessed(self):
        for bad in (None, "", "call for price", "2 for $5", "USD", "$-1"):
            self.assertEqual(_money(bad), "", bad)


class VolumeDealTests(unittest.TestCase):
    def test_nfor_composes_a_description_and_flags_it_as_composed(self):
        description, price, origin = _volume_deal({"nFor": {"quantity": 4, "price": "USD 18.00"}})
        self.assertEqual(description, "4 for $18.00")
        self.assertEqual(price, "18.00")
        # The brief wants retailer wording preserved. This string was built by
        # us, and the adapter must say so rather than implying it was scraped.
        self.assertEqual(origin, "composed_from_nFor")

    def test_absent_or_partial_nfor_yields_nothing(self):
        self.assertEqual(_volume_deal({}), ("", "", ""))
        self.assertEqual(_volume_deal({"nFor": {"quantity": 4}}), ("", "", ""))
        self.assertEqual(_volume_deal({"nFor": {"price": "USD 18.00"}}), ("", "", ""))


class MappingTests(unittest.TestCase):
    def test_a_contract_product_maps_to_a_publishable_22_field_record(self):
        src = source(FakeClient([page([product()])]))
        result = src.fetch(STORE, CATEGORY, CATEGORY.url, "")
        self.assertEqual(len(result.products), 1)
        record = make_record(result.products[0], STORE, "Dairy", "Milk", "2026-11-06")
        self.assertEqual(record["regular_price"], "4.99")
        self.assertEqual(record["weight"], "1 gal")
        self.assertEqual(record["upc"], "0001111041700")
        self.assertEqual(record["product_title"], "Simple Truth 2% Reduced Fat Milk")
        self.assertEqual(record["store_brand"], "yes")

    def test_leading_zeros_on_upc_survive_the_mapping(self):
        src = source(FakeClient([page([product(upc="0001111041700")])]))
        raw = src.fetch(STORE, CATEGORY, CATEGORY.url, "").products[0]
        self.assertEqual(raw["upc"], "0001111041700")

    def test_volume_offer_reaches_the_record(self):
        src = source(FakeClient([page([product(promo="$18.00", n_for=(4, "USD 18.00"))])]))
        raw = src.fetch(STORE, CATEGORY, CATEGORY.url, "").products[0]
        record = make_record(raw, STORE, "Dairy", "Milk", "2026-11-06")
        self.assertEqual(record["volume_deals_description"], "4 for $18.00")
        self.assertEqual(record["volume_deals_price"], "18.00")

    def test_digital_deal_fields_stay_blank_because_no_kroger_api_exposes_them(self):
        src = source(FakeClient([page([product(promo="$18.00", n_for=(4, "USD 18.00"))])]))
        raw = src.fetch(STORE, CATEGORY, CATEGORY.url, "").products[0]
        self.assertEqual(raw["digital_deals_description"], "")
        self.assertEqual(raw["digital_deals_price"], "")


class PPMTests(unittest.TestCase):
    """The `unit` field is a candidate for PPM, not an established one."""

    def test_unit_field_is_not_written_to_ppm_by_default(self):
        src = source(FakeClient([page([product(unit="USD 5.00")])]))
        raw = src.fetch(STORE, CATEGORY, CATEGORY.url, "").products[0]
        self.assertEqual(raw["ppm"], "")

    def test_unit_field_is_written_only_when_an_operator_opts_in(self):
        import os

        os.environ["CATALOG_V2_UNIT_IS_PPM"] = "yes"
        try:
            src = source(FakeClient([page([product(unit="USD 5.00")])]))
            raw = src.fetch(STORE, CATEGORY, CATEGORY.url, "").products[0]
            self.assertEqual(raw["ppm"], "USD 5.00")
        finally:
            del os.environ["CATALOG_V2_UNIT_IS_PPM"]

    def test_the_candidate_is_always_carried_to_the_audit_record(self):
        client = FakeClient([page([product(unit="USD 5.00")])])
        src = source(client)
        src.sweep(STORE)
        entry = src._sweep.audit[0]
        self.assertEqual(entry["ppm_candidate_unit_field"], "USD 5.00")
        self.assertFalse(entry["ppm_written"])


class StoreBindingTests(unittest.TestCase):
    """The cross-banner leak this project has already seen once must not recur."""

    def test_a_product_carried_only_at_another_location_is_dropped(self):
        src = source(FakeClient([page([product(location_id="99999999")])]))
        self.assertEqual(src.fetch(STORE, CATEGORY, CATEGORY.url, "").products, [])

    def test_the_requested_store_is_selected_not_the_first_location(self):
        item = product()
        item["locations"].insert(
            0,
            {
                "id": "99999999",
                "inventory": [
                    {
                        "instock": True,
                        "prices": [{"regular": {"defaultDescription": "$1.00"}, "promo": {}}],
                    }
                ],
            },
        )
        src = source(FakeClient([page([item])]))
        raw = src.fetch(STORE, CATEGORY, CATEGORY.url, "").products[0]
        # $1.00 belongs to the other store; taking locations[0] would store it.
        self.assertEqual(raw["regular_price"], "4.99")

    def test_a_foreign_banner_product_url_is_refused_not_rewritten(self):
        src = source(
            FakeClient([page([product(url="https://www.kroger.com/p/milk/0001111041700")])])
        )
        self.assertEqual(src.fetch(STORE, CATEGORY, CATEGORY.url, "").products, [])

    def test_a_marianos_url_passes_the_schema_url_gate(self):
        src = source(FakeClient([page([product()])]))
        raw = src.fetch(STORE, CATEGORY, CATEGORY.url, "").products[0]
        make_record(raw, STORE, "Dairy", "Milk", "2026-11-06")


class SweepTests(unittest.TestCase):
    def test_pagination_follows_hasmore_and_stops_when_it_clears(self):
        client = FakeClient(
            [
                page([product(upc="0000000000001")], has_more=True),
                page([product(upc="0000000000002")], has_more=False),
            ]
        )
        src = source(client)
        result = src.sweep(STORE)
        self.assertEqual(result.product_count, 2)
        self.assertEqual(result.pages_fetched, 2)
        self.assertTrue(result.complete)
        self.assertEqual(client.calls[1][1]["page.offset"], 50)

    def test_hasmore_true_on_an_empty_page_does_not_loop_for_ever(self):
        client = FakeClient([page([], has_more=True), page([], has_more=True)])
        src = source(client)
        result = src.sweep(STORE)
        self.assertEqual(result.pages_fetched, 1)
        self.assertFalse(result.complete)

    def test_an_incomplete_sweep_is_reported_so_publication_can_be_refused(self):
        client = FakeClient([page([product()], has_more=True)])
        src = source(client, max_pages=1)
        result = src.fetch(STORE, CATEGORY, CATEGORY.url, "")
        self.assertFalse(result.subcategories_complete)

    def test_the_sweep_runs_once_and_is_reused_across_categories(self):
        client = FakeClient([page([product()])])
        src = source(client)
        src.fetch(STORE, CATEGORY, CATEGORY.url, "")
        src.fetch(STORE, CATEGORY, CATEGORY.url, "")
        self.assertEqual(len(client.calls), 1)

    def test_retention_option_is_requested_so_priceless_items_are_not_dropped(self):
        client = FakeClient([page([product()])])
        source(client).sweep(STORE)
        self.assertEqual(client.calls[0][1]["option.missingPrices"], "true")

    def test_required_contract_filters_are_always_sent(self):
        client = FakeClient([page([product()])])
        source(client).sweep(STORE)
        params = client.calls[0][1]
        self.assertEqual(params["filter.locations.id.eq"], LOCATION_ID)
        self.assertEqual(params["filter.locations.fulfillment.eq"], "curbside")


class GuardTests(unittest.TestCase):
    def test_a_demo_location_id_is_refused(self):
        for bad in ("DEMO-WESTLOOP-60661", "REPLACE_ME", "UNRESOLVED"):
            with self.assertRaises(CatalogV2Error):
                CatalogV2Source(FakeClient([]), bad)

    def test_page_size_outside_the_contract_range_is_refused(self):
        for bad in (0, 51, 500):
            with self.assertRaises(CatalogV2Error):
                CatalogV2Source(FakeClient([]), LOCATION_ID, page_size=bad)

    def test_missing_credentials_are_refused_before_any_request(self):
        import os

        saved = {k: os.environ.pop(k, None) for k in ("KROGER_CLIENT_ID", "KROGER_CLIENT_SECRET")}
        try:
            with self.assertRaises(CatalogV2Error):
                Credentials.from_environment()
        finally:
            for k, v in saved.items():
                if v is not None:
                    os.environ[k] = v

    def test_undocumented_paths_are_refused(self):
        client = CatalogV2Client(Credentials("id", "secret"))
        with self.assertRaises(CatalogV2Error):
            client.get("/v1/products", {})

    def test_entitlement_refusal_is_a_challenge_and_is_not_retried(self):
        src = source(FakeClient([], raises=AccessChallenge("Catalog V2 HTTP 403")))
        with self.assertRaises(AccessChallenge):
            src.sweep(STORE)


class ProvenanceTests(unittest.TestCase):
    def test_provenance_declares_every_unverified_assumption(self):
        client = FakeClient([page([product()])])
        src = source(client)
        src.sweep(STORE)
        record = src.provenance()
        self.assertFalse(record["fulfillment_filter_verified"])
        self.assertFalse(record["scope_verified"])
        self.assertEqual(
            record["volume_wording"], "composed_from_nFor_not_verbatim_retailer_text"
        )
        self.assertEqual(
            record["digital_deals"], "not_exposed_by_any_published_kroger_api"
        )
        self.assertTrue(record["sweep_complete"])
        self.assertEqual(record["products_swept"], 1)


if __name__ == "__main__":
    unittest.main()
