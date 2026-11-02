"""A source that cannot reconcile against the full category set may collect,
but may not publish a full release.

Before this, the runner refused such a source outright, at the per-page
`subcategories_complete` check. That conflated two different things: whether a
page enumerated its own children, and whether the route can reconcile against
the client's 28 configured roots. A route that is honest about the second,
like a term-filtered search sweep, could not run at all, which is why the
26,166 records were produced by a tool outside the collector.

Walmart's runner already separated the two. This is the same gate, with the
cases that prove it was not loosened on the way across.
"""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from marianos_collector.config import categories_from_csv, stores_from_json  # noqa: E402
from marianos_collector.runner import Collector, ValidationFailure  # noqa: E402
from marianos_collector.sources import Page  # noqa: E402
from marianos_collector.storage import LocalStorage  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def product(store, n=1):
    return {
        "store_id": store.store_id, "zipcode": store.zipcode,
        "store_context_verified": True, "seller_type": "marianos",
        "fulfillment": "pickup", "product_id": f"P{n:03d}",
        "product_title": f"Item {n}", "weight": "12 oz",
        "regular_price": "4.99", "sale_price": "",
        "upc": f"999999000{n:04d}", "brand": "Test",
        "url": f"https://www.marianos.com/p/test-{n}",
        "image_url": f"https://www.marianos.com/images/{n}.jpg",
        "ppm": "", "volume_deals_description": "", "volume_deals_price": "",
        "digital_deals_description": "", "digital_deals_price": "",
    }


class Source:
    """A source whose two declarations can be set independently."""

    source_mode = "test_source"

    def __init__(self, attests, pages_complete=True):
        self.coverage_attested = attests
        self.pages_complete = pages_complete
        self.unresolved_offers = []
        self._n = 0

    def fetch(self, store, category, url, cursor):
        self._n += 1
        return Page(store_id=store.store_id, zipcode=store.zipcode,
                    store_context_verified=True, source_url=url,
                    products=[product(store, self._n)], children=[],
                    next_cursor="", subcategories_complete=self.pages_complete)


def categories():
    return categories_from_csv(ROOT / "config/categories.csv")[:2]


def store():
    return stores_from_json(ROOT / "config/stores_demo.json")[0]


def collect(source, trial):
    with tempfile.TemporaryDirectory() as td:
        return Collector(LocalStorage(Path(td)), source, categories(),
                         min_products=1, trial=trial).run(store())


class AFullReleaseNeedsAttestation(unittest.TestCase):
    def test_a_non_attesting_source_cannot_publish_a_full_release(self):
        with self.assertRaises(ValidationFailure) as caught:
            collect(Source(attests=False), trial=False)
        self.assertIn("does not attest complete coverage", str(caught.exception))

    def test_an_attesting_source_can_publish_a_full_release(self):
        out = collect(Source(attests=True), trial=False)
        self.assertEqual(out["report"]["scope"], "full")
        self.assertTrue(out["report"]["source_coverage_attested"])


class ANonAttestingSourceMayStillCollect(unittest.TestCase):
    """The point of the change. Honesty about coverage must not mean the
    source cannot run; it means its output is a trial."""

    def test_a_non_attesting_source_runs_as_a_trial(self):
        out = collect(Source(attests=False), trial=True)
        self.assertEqual(out["report"]["scope"], "trial")
        self.assertFalse(out["report"]["source_coverage_attested"])

    def test_a_non_attesting_source_may_report_incomplete_pages(self):
        out = collect(Source(attests=False, pages_complete=False), trial=True)
        self.assertEqual(out["report"]["scope"], "trial")

    def test_its_output_says_coverage_was_not_attested(self):
        out = collect(Source(attests=False), trial=True)
        self.assertIn("source_coverage_attested", out["report"])
        self.assertFalse(out["report"]["source_coverage_attested"])


class TheGateIsNotWeakened(unittest.TestCase):
    def test_an_attesting_source_with_incomplete_pages_is_still_refused(self):
        """The per-page check still binds anything that claims to attest. This
        is the case that would show the gate had been loosened."""
        with self.assertRaises(ValidationFailure) as caught:
            collect(Source(attests=True, pages_complete=False), trial=False)
        self.assertIn("subcategory discovery", str(caught.exception))

    def test_flipping_trial_off_after_construction_is_caught_at_run_time(self):
        with tempfile.TemporaryDirectory() as td:
            collector = Collector(LocalStorage(Path(td)), Source(attests=False),
                                  categories(), min_products=1, trial=True)
            collector.trial = False
            with self.assertRaises(ValidationFailure):
                collector.run(store())

    def test_swapping_in_a_non_attesting_source_afterwards_is_caught(self):
        with tempfile.TemporaryDirectory() as td:
            collector = Collector(LocalStorage(Path(td)), Source(attests=True),
                                  categories(), min_products=1, trial=False)
            collector.source = Source(attests=False)
            with self.assertRaises(ValidationFailure):
                collector.run(store())

    def test_a_source_that_says_nothing_about_coverage_is_treated_as_not_attesting(self):
        class Silent(Source):
            def __init__(self):
                super().__init__(attests=True)
                del self.coverage_attested

        with self.assertRaises(ValidationFailure):
            collect(Silent(), trial=False)


if __name__ == "__main__":
    unittest.main()
