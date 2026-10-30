"""Field-level composition for Walmart: precedence, provenance, conflicts and honest gaps."""
import unittest

import sys as _sys, pathlib as _pathlib
_sys.path.insert(0, str(_pathlib.Path(__file__).resolve().parent.parent))

from walmart_collector.composition import (
    COMPOSABLE_FIELDS,
    Availability,
    CallableEnrichment,
    CompositeSource,
    CompositionError,
    DERIVED_FIELDS,
    unavailable_crawl,
)
from walmart_collector.config import Category, Store
from walmart_collector.schema import FIELDS, make_record
from walmart_collector.sources import Page, SourceError

STORE = Store(
    store_id="100",
    zipcode="72712",
    store_name="Walmart Supercenter",
    store_location="Bentonville, AR",
)
CATEGORY = Category(name="Food", url="https://www.walmart.com/cp/food/976759")


def raw(**overrides):
    base = {
        "store_id": STORE.store_id,
        "zipcode": STORE.zipcode,
        "store_context_verified": True,
        "seller_type": "walmart",
        "fulfillment": "pickup",
        "product_id": "0001111041700",
        "product_title": "Great Value 2% Milk",
        "weight": "1 gal",
        "regular_price": "4.99",
        "sale_price": "",
        "volume_deals_description": "",
        "volume_deals_price": "",
        "digital_deals_description": "",
        "digital_deals_price": "",
        "upc": "0001111041700",
        "brand": "Great Value",
        "url": "https://www.walmart.com/ip/milk/938273658",
        "image_url": "https://i5.walmartimages.com/milk.jpg",
        "ppm": "",
    }
    base.update(overrides)
    return base


class Spine:
    source_mode = "spine"

    def __init__(self, products, pages=None):
        self.products = products
        self.calls = 0

    def fetch(self, store, category, url, cursor):
        self.calls += 1
        return Page(
            store_id=store.store_id,
            zipcode=store.zipcode,
            store_context_verified=True,
            source_url=url,
            products=[dict(p) for p in self.products],
            children=[],
            next_cursor="",
            subcategories_complete=True,
        )


def composite(products, enrichments=None, policy=None):
    return CompositeSource(Spine(products), "opd", enrichments, policy)


class FieldSetTests(unittest.TestCase):
    def test_composable_and_derived_fields_partition_the_schema(self):
        self.assertEqual(COMPOSABLE_FIELDS | DERIVED_FIELDS, set(FIELDS))
        self.assertFalse(COMPOSABLE_FIELDS & DERIVED_FIELDS)

    def test_collector_set_fields_are_never_composable(self):
        for name in ("zipcode", "store_name", "category", "crawl_date", "gupc", "unit_price"):
            self.assertIn(name, DERIVED_FIELDS)


class PrecedenceTests(unittest.TestCase):
    def test_an_enrichment_fills_a_field_the_spine_left_blank(self):
        crawl = CallableEnrichment(
            "crawl", ["ppm"], lambda s, i, p: {"ppm": "($0.42/oz)"}
        )
        src = composite([raw()], [crawl])
        product = src.fetch(STORE, CATEGORY, CATEGORY.url, "").products[0]
        self.assertEqual(product["ppm"], "($0.42/oz)")

    def test_opd_outranks_the_crawl_for_ppm(self):
        crawl = CallableEnrichment("crawl", ["ppm"], lambda s, i, p: {"ppm": "crawled"})
        src = composite([raw(ppm="from_api")], [crawl])
        product = src.fetch(STORE, CATEGORY, CATEGORY.url, "").products[0]
        # Walmart differs from Kroger here. OPD's unitPriceDisplay is a
        # DISPLAYED unit price string rather than a rate the collector
        # computes, which is exactly what the brief asks for, so it outranks a
        # parsed page. On the Kroger side the precedence is the other way round,
        # because no Kroger API confirms a displayed per-measure price.
        self.assertEqual(product["ppm"], "from_api")

    def test_crawl_outranks_opd_for_offer_terms(self):
        crawl = CallableEnrichment(
            "crawl", ["sale_price"], lambda s, i, p: {"sale_price": "3.49"}
        )
        src = composite([raw(sale_price="9.99")], [crawl])
        product = src.fetch(STORE, CATEGORY, CATEGORY.url, "").products[0]
        # OPD documents no offer fields at all, and a snapshot current price is
        # not evidence of a displayed sale against a regular price.
        self.assertEqual(product["sale_price"], "3.49")

    def test_the_api_outranks_the_crawl_for_price(self):
        crawl = CallableEnrichment(
            "crawl", ["regular_price"], lambda s, i, p: {"regular_price": "9.99"}
        )
        src = composite([raw(regular_price="4.99")], [crawl])
        product = src.fetch(STORE, CATEGORY, CATEGORY.url, "").products[0]
        # A store-bound API price is stronger evidence than a parsed page.
        self.assertEqual(product["regular_price"], "4.99")

    def test_an_empty_enrichment_value_never_blanks_a_populated_field(self):
        crawl = CallableEnrichment("crawl", ["ppm"], lambda s, i, p: {"ppm": ""})
        src = composite([raw(ppm="kept")], [crawl])
        product = src.fetch(STORE, CATEGORY, CATEGORY.url, "").products[0]
        self.assertEqual(product["ppm"], "kept")

    def test_a_source_outside_a_fields_policy_can_fill_a_blank_but_not_displace(self):
        other = CallableEnrichment(
            "provider", ["regular_price"], lambda s, i, p: {"regular_price": "7.77"}
        )
        policy = {"regular_price": ("opd",)}
        filled = composite([raw(regular_price="4.99")], [other], policy)
        self.assertEqual(
            filled.fetch(STORE, CATEGORY, CATEGORY.url, "").products[0]["regular_price"],
            "4.99",
        )
        blank = composite([raw(regular_price="")], [other], policy)
        self.assertEqual(
            blank.fetch(STORE, CATEGORY, CATEGORY.url, "").products[0]["regular_price"],
            "7.77",
        )


class ProvenanceTests(unittest.TestCase):
    def test_every_merged_value_names_the_source_that_produced_it(self):
        crawl = CallableEnrichment(
            "crawl",
            ["ppm", "digital_deals_description"],
            lambda s, i, p: {"ppm": "($0.42/oz)", "digital_deals_description": "Clip to save"},
        )
        src = composite([raw()], [crawl])
        src.fetch(STORE, CATEGORY, CATEGORY.url, "")
        trace = src.provenance_for("0001111041700")
        self.assertEqual(trace["ppm"], "crawl")
        self.assertEqual(trace["digital_deals_description"], "crawl")
        self.assertEqual(trace["regular_price"], "opd")

    def test_the_report_counts_values_by_field_and_source(self):
        crawl = CallableEnrichment("crawl", ["ppm"], lambda s, i, p: {"ppm": "x"})
        src = composite([raw(product_id="a"), raw(product_id="b")], [crawl])
        src.fetch(STORE, CATEGORY, CATEGORY.url, "")
        report = src.provenance_report()
        self.assertEqual(report["values_by_field_and_source"]["ppm"]["crawl"], 2)
        self.assertEqual(report["products_traced"], 2)

    def test_source_mode_names_only_the_sources_that_actually_ran(self):
        live = CallableEnrichment("provider", ["ppm"], lambda s, i, p: {})
        blocked = unavailable_crawl("Azure egress refused by the retailer")
        src = composite([raw()], [live, blocked])
        self.assertEqual(src.source_mode, "composite(opd+provider)")


class ConflictTests(unittest.TestCase):
    def test_disagreement_is_recorded_rather_than_silently_resolved(self):
        crawl = CallableEnrichment(
            "crawl", ["regular_price"], lambda s, i, p: {"regular_price": "9.99"}
        )
        src = composite([raw(regular_price="4.99")], [crawl])
        src.fetch(STORE, CATEGORY, CATEGORY.url, "")
        report = src.provenance_report()
        self.assertEqual(report["conflict_count"], 1)
        conflict = report["conflicts"][0]
        self.assertEqual(conflict["field"], "regular_price")
        self.assertEqual(conflict["kept"]["value"], "4.99")
        self.assertEqual(conflict["discarded"]["value"], "9.99")

    def test_agreement_is_not_a_conflict(self):
        crawl = CallableEnrichment(
            "crawl", ["regular_price"], lambda s, i, p: {"regular_price": "4.99"}
        )
        src = composite([raw(regular_price="4.99")], [crawl])
        src.fetch(STORE, CATEGORY, CATEGORY.url, "")
        self.assertEqual(src.provenance_report()["conflict_count"], 0)


class AvailabilityTests(unittest.TestCase):
    def test_a_blocked_crawl_leaves_its_fields_blank_and_states_why(self):
        blocked = unavailable_crawl("Azure datacenter egress served a bot challenge")
        src = composite([raw()], [blocked])
        product = src.fetch(STORE, CATEGORY, CATEGORY.url, "").products[0]
        self.assertEqual(product["ppm"], "")
        self.assertEqual(product["digital_deals_description"], "")
        report = src.provenance_report()
        self.assertIn("crawl", report["enrichments_unavailable"])
        self.assertIn("bot challenge", report["enrichments_unavailable"]["crawl"])

    def test_a_blocked_source_is_still_registered_so_the_gap_is_visible(self):
        blocked = unavailable_crawl("refused")
        src = composite([raw()], [blocked])
        self.assertIn("crawl", src.provenance_report()["enrichments"])

    def test_an_unavailable_source_must_give_a_reason(self):
        with self.assertRaises(CompositionError):
            Availability.blocked("")

    def test_one_enrichment_failing_on_one_product_does_not_lose_the_product(self):
        def flaky(store, identity, product):
            raise SourceError("upstream timed out")

        crawl = CallableEnrichment("crawl", ["ppm"], flaky)
        src = composite([raw()], [crawl])
        page = src.fetch(STORE, CATEGORY, CATEGORY.url, "")
        self.assertEqual(len(page.products), 1)
        self.assertEqual(page.products[0]["regular_price"], "4.99")
        self.assertIn("crawl", src.provenance_report()["enrichments_unavailable"])


class DeclarationTests(unittest.TestCase):
    def test_a_source_cannot_supply_a_field_it_did_not_declare(self):
        sneaky = CallableEnrichment(
            "crawl", ["ppm"], lambda s, i, p: {"regular_price": "0.01"}
        )
        src = composite([raw()], [sneaky])
        with self.assertRaises(CompositionError):
            src.fetch(STORE, CATEGORY, CATEGORY.url, "")

    def test_declaring_a_collector_set_field_is_refused(self):
        with self.assertRaises(CompositionError):
            CallableEnrichment("crawl", ["crawl_date"], lambda s, i, p: {})

    def test_duplicate_source_names_are_refused(self):
        dupe = CallableEnrichment("opd", ["ppm"], lambda s, i, p: {})
        with self.assertRaises(CompositionError):
            composite([raw()], [dupe])

    def test_a_policy_naming_a_collector_set_field_is_refused(self):
        with self.assertRaises(CompositionError):
            composite([raw()], [], {"crawl_date": ("opd",)})


class OutputShapeTests(unittest.TestCase):
    """The delivered 22-field output must not change shape. A package has
    already been verified by hash."""

    def test_composition_does_not_add_keys_to_the_published_record(self):
        crawl = CallableEnrichment(
            "crawl",
            ["ppm", "digital_deals_description"],
            lambda s, i, p: {"ppm": "($0.42/oz)", "digital_deals_description": "Clip this offer"},
        )
        src = composite([raw()], [crawl])
        product = src.fetch(STORE, CATEGORY, CATEGORY.url, "").products[0]
        record = make_record(product, STORE, "Food", "Dairy", "2026-11-06")
        self.assertEqual(list(record.keys()), list(FIELDS))
        self.assertTrue(all(isinstance(v, str) for v in record.values()))

    def test_a_composed_digital_deal_still_passes_the_schema_wording_gate(self):
        crawl = CallableEnrichment(
            "crawl",
            ["digital_deals_description", "digital_deals_price"],
            lambda s, i, p: {
                "digital_deals_description": "Clip this digital coupon, limit 2",
                "digital_deals_price": "3.49",
            },
        )
        src = composite([raw()], [crawl])
        product = src.fetch(STORE, CATEGORY, CATEGORY.url, "").products[0]
        record = make_record(product, STORE, "Food", "Dairy", "2026-11-06")
        self.assertEqual(record["digital_deals_price"], "3.49")




class EntrypointTests(unittest.TestCase):
    """The Azure job must be able to select OPD and composite, and refuse fixtures."""

    def setUp(self):
        import importlib.util
        from pathlib import Path
        root = Path(__file__).resolve().parent.parent
        spec = importlib.util.spec_from_file_location(
            "walmart_container_entrypoint", root / "azure" / "container_entrypoint.py"
        )
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)
        import os
        self._saved = {
            k: os.environ.pop(k, None)
            for k in ("WALMART_STORE_ID", "WALMART_SOURCE", "WALMART_SPINE")
        }

    def tearDown(self):
        import os
        for key, value in self._saved.items():
            os.environ.pop(key, None)
            if value is not None:
                os.environ[key] = value

    def set(self, **kwargs):
        import os
        for key, value in kwargs.items():
            os.environ[key] = value

    def test_default_source_is_still_the_provider(self):
        self.set(WALMART_STORE_ID="100")
        self.assertIn("provider", self.module.command())

    def test_opd_is_selectable(self):
        self.set(WALMART_STORE_ID="100", WALMART_SOURCE="opd")
        self.assertIn("opd", self.module.command())

    def test_composite_passes_its_spine(self):
        self.set(WALMART_STORE_ID="100", WALMART_SOURCE="composite", WALMART_SPINE="opd")
        argv = self.module.command()
        self.assertIn("composite", argv)
        self.assertEqual(argv[argv.index("--spine") + 1], "opd")

    def test_an_unknown_spine_is_refused(self):
        self.set(WALMART_STORE_ID="100", WALMART_SOURCE="composite", WALMART_SPINE="fixture")
        with self.assertRaises(ValueError):
            self.module.command()

    def test_a_scheduled_job_cannot_run_synthetic_fixtures(self):
        self.set(WALMART_STORE_ID="100", WALMART_SOURCE="fixture")
        with self.assertRaises(ValueError):
            self.module.command()


if __name__ == "__main__":
    unittest.main()
