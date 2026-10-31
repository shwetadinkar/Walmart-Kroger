"""PART B of REVIEW_ACTIONS_2026-10-31.md. B1 and B2 sit with the probe's tests
in test_opd_bounded_probe.py; B3 is covered in the corrections suite."""
import ast
import inspect
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from walmart_collector.composition import (BINDING_KEY, CallableEnrichment,
                                           CompositeSource, unavailable_crawl)
from walmart_collector.config import Store, categories_from_csv
from walmart_collector.opd import WalmartOPDSnapshotSource
from walmart_collector.runner import Collector, ValidationFailure
from walmart_collector.schema import RecordRejected, make_record
from walmart_collector.sources import (AuthorizedProviderSource, FixtureSource, Page)
from walmart_collector.storage import LocalStorage

STORE = Store("100", "72712", "Walmart #100", "Bentonville, AR")
ARGS = ("Food", "Pantry", "2026-10-31")


def RAW(title, weight):
    return {"store_id": "100", "zipcode": "72712", "store_context_verified": True,
            "seller_type": "walmart", "fulfillment": "pickup", "product_id": "1",
            "product_title": title, "weight": weight, "regular_price": "4.99",
            "url": "https://www.walmart.com/ip/x/1", "upc": "1", "brand": "Example"}



class ApproximateServingsAreNotApproximateWeight(unittest.TestCase):
    """B4. The exclusion is about weight, not about approximation in general."""

    FIXED = ("Rice 16 oz, approximately 8 servings",
             "Rice 16 oz approx. 8 servings",
             "Pasta Sauce 24 oz, approx 6 servings per container",
             "Cereal, about 12 servings",
             "Crackers approximately 40 count",
             "Candle approx. 30 hours burn time",
             "Foil 12 in x approximately 75 sq ft",
             "Grapes about 20 grapes per pack")
    APPROXIMATE = ("Chicken approximately 1 lb", "Beef approx. 2-3 lb",
                   "Pork approx 1.5 pounds", "Ham approx: 8 oz",
                   "Roast approximately 1/2 kg", "Steak about 12 oz",
                   "Turkey Approximate Weight", "Ribs approx. net wt 3 lb",
                   "Fish 1 lb approx.", "Lamb 2 lb (approx)",
                   "Veal 16 oz, approximately", "Brisket weight approximately 4",
                   "Duck 5 lb approximately weight varies")

    def test_a_fixed_size_with_an_approximate_serving_count_passes(self):
        for title in self.FIXED:
            record = make_record(RAW(title, "16 oz"), STORE, *ARGS)
            self.assertEqual(record["product_title"], title)

    def test_approximate_weight_in_a_title_is_still_excluded(self):
        for title in self.APPROXIMATE:
            with self.assertRaisesRegex(RecordRejected, "APPROXIMATE_WEIGHT_IN_TITLE", msg=title):
                make_record(RAW(title, "1 lb"), STORE, *ARGS)

    def test_a_serving_count_in_the_weight_field_passes(self):
        for weight in ("16 oz, approximately 8 servings", "about 4 servings", "approx. 30 count"):
            record = make_record(RAW("Rice", weight), STORE, *ARGS)
            self.assertEqual(record["weight"], weight)

    def test_approximate_wording_in_the_weight_field_is_still_excluded(self):
        for weight in ("approx. 2 lb", "approximately 2", "about 3", "about 3 lb",
                       "2 lb approx", "approximate", "approx"):
            with self.assertRaisesRegex(RecordRejected, "^APPROXIMATE_WEIGHT$", msg=weight):
                make_record(RAW("Rice", weight), STORE, *ARGS)

    def test_family_packs_and_multipacks_are_untouched(self):
        for title, weight in (("Family Pack Ground Beef, 5 lb", "5 lb"),
                              ("Yogurt 12 ct, 5.3 oz each", "63.6 oz")):
            self.assertEqual(make_record(RAW(title, weight), STORE, *ARGS)["weight"], weight)



def runner_reads():
    """Every attribute the runner asks of a source, from its own source code."""
    tree = ast.parse((ROOT / "walmart_collector/runner.py").read_text(encoding="utf-8"))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            base = node.value
            if (isinstance(base, ast.Name) and base.id == "source") or (
                    isinstance(base, ast.Attribute) and base.attr == "source"):
                names.add(node.attr)
        if isinstance(node, ast.Call) and getattr(node.func, "id", "") in ("getattr", "hasattr"):
            target = node.args[0]
            if getattr(target, "attr", getattr(target, "id", "")) == "source":
                names.add(node.args[1].value)
    return names


def class_surface(cls):
    return {n for n in vars(cls) if not n.startswith("_")}


class Sentinel:
    def __init__(self, names):
        self.source_mode = "sentinel"
        self.fetch = lambda *a: None
        for name in names:
            setattr(self, name, object())


class DelegationSurfaceTests(unittest.TestCase):
    """B5. Three attributes were missed one at a time, so the surface is derived
    from the code rather than listed, and adding to it needs no change here."""

    OWNED = {"fetch", "source_mode", "reset_unresolved", "provenance_report",
             "spine_source_mode"}

    def surface(self):
        names = runner_reads()
        for cls in (FixtureSource, AuthorizedProviderSource, WalmartOPDSnapshotSource):
            names |= class_surface(cls)
        return names - self.OWNED

    def test_the_derivation_actually_finds_the_interface(self):
        reads = runner_reads()
        self.assertTrue({"fetch", "source_mode", "coverage_attested", "unresolved_offers",
                         "reset_unresolved", "provenance_report"} <= reads, reads)

    def test_every_attribute_of_the_spine_interface_reaches_the_spine(self):
        names = self.surface()
        spine = Sentinel(names)
        composite = CompositeSource(spine, "opd", [])
        for name in sorted(names):
            self.assertIs(getattr(composite, name), getattr(spine, name), name)

    def test_an_attribute_the_spine_lacks_stays_absent(self):
        composite = CompositeSource(Sentinel(()), "opd", [])
        self.assertFalse(hasattr(composite, "unresolved_offers"))
        self.assertFalse(hasattr(composite, "coverage_attested"))
        with self.assertRaises(AttributeError):
            composite._private_thing

    def test_private_attributes_of_the_spine_do_not_leak(self):
        spine = Sentinel(())
        spine._secret = 1
        self.assertFalse(hasattr(CompositeSource(spine, "opd", []), "_secret"))


class CoverageGateTests(unittest.TestCase):
    def categories(self):
        return categories_from_csv(ROOT / "config/categories.csv")[:2]

    def test_an_attested_spine_passes_the_gate_through_the_composite(self):
        class Attested(FixtureSource):
            source_mode = "authorized_provider_x"
        source = CompositeSource(Attested(ROOT / "fixtures"), "provider",
                                 [unavailable_crawl("blocked")])
        with tempfile.TemporaryDirectory() as base:
            Collector(LocalStorage(Path(base)), source, self.categories())
        self.assertTrue(source.coverage_attested)

    def test_an_unattested_spine_is_still_refused_through_the_composite(self):
        class Unattested(FixtureSource):
            coverage_attested = False
        source = CompositeSource(Unattested(ROOT / "fixtures"), "opd", [])
        with tempfile.TemporaryDirectory() as base:
            with self.assertRaisesRegex(ValidationFailure, "does not attest"):
                Collector(LocalStorage(Path(base)), source, self.categories())

    def test_a_spine_silent_on_coverage_is_refused_through_the_composite(self):
        class Silent:
            source_mode = "silent"
            def fetch(self, *a):
                raise AssertionError("never reached")
        with tempfile.TemporaryDirectory() as base:
            with self.assertRaises(ValidationFailure):
                Collector(LocalStorage(Path(base)), CompositeSource(Silent(), "opd", []),
                          self.categories())

    def test_a_spine_that_stops_attesting_mid_run_is_seen_live(self):
        class Fades(FixtureSource):
            pass
        spine = Fades(ROOT / "fixtures")
        composite = CompositeSource(spine, "opd", [])
        self.assertTrue(composite.coverage_attested)
        spine.coverage_attested = False
        self.assertFalse(composite.coverage_attested)

    def test_a_synthetic_spine_stays_synthetic_through_the_composite(self):
        """`composite(...)` does not start with synthetic_fixture, so a fixture
        run wrapped in a composite reported source_is_synthetic=false, and that
        is the flag submission_gate refuses on."""
        categories = self.categories()
        with tempfile.TemporaryDirectory() as base:
            source = CompositeSource(FixtureSource(ROOT / "fixtures"), "fixture",
                                     [unavailable_crawl("blocked")])
            result = Collector(LocalStorage(Path(base)), source, categories,
                               min_products=1).run(STORE)
        self.assertTrue(result["report"]["source_is_synthetic"])
        self.assertTrue(result["report"]["source_mode"].startswith("composite("))

    def test_a_provider_spine_keeps_its_location_evidence_check(self):
        class Provider:
            source_mode = "authorized_provider_x"
            coverage_attested = True
            def fetch(self, store, category, url, cursor):
                return Page(store_id=store.store_id, zipcode=store.zipcode,
                            store_context_verified=True, source_url=url, products=[],
                            children=[], next_cursor="", subcategories_complete=True)
        with tempfile.TemporaryDirectory() as base:
            collector = Collector(LocalStorage(Path(base)),
                                  CompositeSource(Provider(), "provider", []),
                                  self.categories(), min_products=1)
            with self.assertRaisesRegex(ValidationFailure, "independent location evidence"):
                collector.run(STORE)


def spine_with(product):
    class Spine:
        source_mode = "spine"
        def fetch(self, store, category, url, cursor):
            return Page(store_id=store.store_id, zipcode=store.zipcode,
                        store_context_verified=True, source_url=url,
                        products=[dict(product)], children=[], next_cursor="",
                        subcategories_complete=True)
    return Spine()


class BindingTests(unittest.TestCase):
    """B5. A contributed value counts only if tied to product, store, fulfilment
    and time."""

    GOOD = {"identity": "1", "store_id": "100", "fulfillment": "pickup",
            "observed_at": "2026-10-31T12:00:00Z"}

    def compose(self, binding):
        def lookup(store, identity, product):
            value = {"digital_deals_description": "Clip this digital coupon"}
            if binding is not None:
                value[BINDING_KEY] = binding
            return value
        crawl = CallableEnrichment("crawl", ["digital_deals_description"], lookup)
        source = CompositeSource(spine_with({**RAW("Rice", "16 oz")}), "opd", [crawl])
        category = categories_from_csv(ROOT / "config/categories.csv")[0]
        return source, source.fetch(STORE, category, category.url, "").products[0]

    def test_a_fully_bound_value_is_merged(self):
        source, product = self.compose(self.GOOD)
        self.assertEqual(product["digital_deals_description"], "Clip this digital coupon")
        self.assertEqual(source.provenance_report()["contributions_refused_as_unbound"], {})

    def test_a_value_that_cannot_be_tied_is_refused_and_counted(self):
        cases = (("UNBOUND_NO_BINDING", None),
                 ("UNBOUND_PRODUCT", {**self.GOOD, "identity": "2"}),
                 ("UNBOUND_STORE", {**self.GOOD, "store_id": "999"}),
                 ("UNBOUND_FULFILLMENT", {**self.GOOD, "fulfillment": "delivery"}),
                 ("UNBOUND_TIME", {**self.GOOD, "observed_at": " "}))
        for reason, binding in cases:
            source, product = self.compose(binding)
            self.assertNotIn("digital_deals_description", product, reason)
            self.assertEqual(source.provenance_report()["contributions_refused_as_unbound"],
                             {f"crawl:{reason}": 1})

    def test_the_binding_key_never_reaches_the_record(self):
        _, product = self.compose(self.GOOD)
        self.assertNotIn(BINDING_KEY, product)
        self.assertEqual(make_record(product, STORE, *ARGS)["digital_deals_description"],
                         "Clip this digital coupon")

    def test_the_refusal_count_is_per_run(self):
        source, _ = self.compose(None)
        source.reset_unresolved()
        self.assertEqual(source.provenance_report()["contributions_refused_as_unbound"], {})


class ExecutableSourceTests(unittest.TestCase):
    def test_the_placeholder_is_reported_as_not_executable(self):
        source = CompositeSource(spine_with(RAW("Rice", "16 oz")), "opd",
                                 [unavailable_crawl("blocked")])
        report = source.provenance_report()
        crawl = next(s for s in report["sources"] if s["name"] == "crawl")
        self.assertFalse(crawl["executable"])
        self.assertFalse(crawl["available"])
        self.assertEqual(report["sources"][0]["role"], "spine")
        self.assertEqual(report["fields_without_executable_source"],
                         sorted(("sale_price", "volume_deals_description", "volume_deals_price",
                                 "digital_deals_description", "digital_deals_price")))

    def test_a_working_source_closes_the_gap_for_its_fields_only(self):
        working = CallableEnrichment("provider", ["sale_price"], lambda *a: {})
        source = CompositeSource(spine_with(RAW("Rice", "16 oz")), "opd",
                                 [working, unavailable_crawl("blocked")])
        unservable = source.provenance_report()["fields_without_executable_source"]
        self.assertNotIn("sale_price", unservable)
        self.assertIn("digital_deals_price", unservable)


if __name__ == "__main__":
    unittest.main()
