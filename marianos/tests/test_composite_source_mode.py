"""A composite must not launder the identity of the source that enumerated.

`CompositeSource.source_mode` reports `composite(...)`. The runner's
mode-dependent gates test `startswith("synthetic_fixture")` and
`startswith("authorized_provider")`, and `composite(...)` starts with neither.
So wrapping a fixture cleared `source_is_synthetic` and the run stopped
declaring itself synthetic, and wrapping an authorized provider skipped the
location-evidence requirement that mode exists to enforce.

Both gates now read `_base_mode`, which follows `spine_source_mode` down to
whatever actually enumerated. These tests cover both cases and must fail if
either gate is weakened again.
"""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from marianos_collector.composition import CompositeSource, unavailable_crawl  # noqa: E402
from marianos_collector.config import categories_from_csv, stores_from_json  # noqa: E402
from marianos_collector.runner import Collector, ValidationFailure  # noqa: E402
from marianos_collector.sources import FixtureSource, Page  # noqa: E402
from marianos_collector.storage import LocalStorage  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


class ProviderSpine:
    """Stands in for an authorized provider that returns no location evidence.

    The real `AuthorizedProviderSource` carries this mode, and the runner is
    required to refuse its pages when `location_evidence_url` is empty.
    """

    source_mode = "authorized_provider_data_unverified_until_review"

    def __init__(self, location_evidence_url=""):
        self.location_evidence_url = location_evidence_url
        self.unresolved_offers = []
        self._n = 0

    def _product(self, store):
        """A product that passes schema validation, so the only thing that can
        fail the run is the location-evidence gate. Without this the run failed
        the minimum-record check instead and the test passed for the wrong
        reason, surviving a mutation that removed the gate."""
        self._n += 1
        return {
            "store_id": store.store_id, "zipcode": store.zipcode,
            "store_context_verified": True, "seller_type": "marianos",
            "fulfillment": "pickup", "product_id": f"TEST-{self._n:03d}",
            "product_title": f"Test item {self._n}", "weight": "12 oz",
            "regular_price": "4.99", "sale_price": "",
            "upc": f"999999000{self._n:04d}", "brand": "Test Brand",
            "url": f"https://www.marianos.com/p/test-{self._n}",
            "image_url": f"https://www.marianos.com/images/test-{self._n}.jpg",
            "ppm": "", "volume_deals_description": "", "volume_deals_price": "",
            "digital_deals_description": "", "digital_deals_price": "",
        }

    def fetch(self, store, category, url, cursor):
        return Page(
            store_id=store.store_id, zipcode=store.zipcode,
            store_context_verified=True, source_url=url,
            products=[self._product(store)], children=[], next_cursor="",
            subcategories_complete=True,
            location_evidence_url=self.location_evidence_url,
        )


def categories():
    return categories_from_csv(ROOT / "config/categories.csv")[:2]


def store():
    return stores_from_json(ROOT / "config/stores_demo.json")[0]


class TheSpineModeIsVisibleThroughAComposite(unittest.TestCase):
    def test_a_bare_fixture_reports_itself_synthetic(self):
        src = FixtureSource(ROOT / "fixtures")
        self.assertTrue(src.source_mode.startswith("synthetic_fixture"))

    def test_a_composite_over_a_fixture_still_reports_the_fixture(self):
        src = CompositeSource(FixtureSource(ROOT / "fixtures"), "fixture",
                              [unavailable_crawl("blocked for this test")])
        self.assertEqual(src.source_mode[:10], "composite(")
        self.assertTrue(
            src.spine_source_mode.startswith("synthetic_fixture"),
            "the composite hid a synthetic spine")

    def test_a_composite_over_a_provider_still_reports_the_provider(self):
        src = CompositeSource(ProviderSpine(), "provider",
                              [unavailable_crawl("blocked for this test")])
        self.assertTrue(
            src.spine_source_mode.startswith("authorized_provider"),
            "the composite hid a provider spine")

    def test_nesting_a_composite_still_reaches_the_real_source(self):
        inner = CompositeSource(FixtureSource(ROOT / "fixtures"), "fixture",
                                [unavailable_crawl("blocked")])
        outer = CompositeSource(inner, "inner", [unavailable_crawl("blocked")])
        self.assertTrue(outer.spine_source_mode.startswith("synthetic_fixture"))


class TheSyntheticLabelSurvivesWrapping(unittest.TestCase):
    """Case one of the two the client asked for."""

    def _run_and_report(self, source):
        with tempfile.TemporaryDirectory() as td:
            out = Collector(LocalStorage(Path(td)), source, categories(),
                            min_products=1, trial=True).run(store())
        return out["report"]

    def test_a_bare_fixture_run_is_marked_synthetic(self):
        report = self._run_and_report(FixtureSource(ROOT / "fixtures"))
        self.assertTrue(report["source_is_synthetic"])

    def test_a_fixture_wrapped_in_a_composite_is_still_marked_synthetic(self):
        wrapped = CompositeSource(FixtureSource(ROOT / "fixtures"), "fixture",
                                  [unavailable_crawl("blocked for this test")])
        report = self._run_and_report(wrapped)
        self.assertTrue(
            report["source_is_synthetic"],
            "wrapping a fixture in a composite cleared the synthetic label")


class TheProviderEvidenceGateSurvivesWrapping(unittest.TestCase):
    """Case two. An authorized provider must supply location evidence."""

    def _run(self, source):
        with tempfile.TemporaryDirectory() as td:
            return Collector(LocalStorage(Path(td)), source, categories(),
                             min_products=1, trial=True).run(store())

    def test_a_provider_WITH_location_evidence_runs(self):
        """The control. Without this, a run that fails for some other reason
        would make the two refusal tests below pass for the wrong reason."""
        report = self._run(ProviderSpine(
            location_evidence_url="https://www.marianos.com/stores/evidence"))
        self.assertEqual(report["report"]["status"], "validated")

    def test_a_bare_provider_without_location_evidence_is_refused(self):
        with self.assertRaises(ValidationFailure):
            self._run(ProviderSpine(location_evidence_url=""))

    def test_a_wrapped_provider_without_location_evidence_is_still_refused(self):
        wrapped = CompositeSource(ProviderSpine(location_evidence_url=""),
                                  "provider",
                                  [unavailable_crawl("blocked for this test")])
        with self.assertRaises(ValidationFailure):
            self._run(wrapped)

    def test_a_wrapped_provider_WITH_evidence_runs(self):
        wrapped = CompositeSource(
            ProviderSpine(location_evidence_url="https://www.marianos.com/stores/evidence"),
            "provider", [unavailable_crawl("blocked for this test")])
        report = self._run(wrapped)
        self.assertEqual(report["report"]["status"], "validated")


if __name__ == "__main__":
    unittest.main()
