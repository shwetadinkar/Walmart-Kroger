"""Everything the runner asks a source must reach the spine.

Forwarding names one at a time lost three in turn in this module.
`unresolved_offers` and `reset_unresolved` were fixed when they were noticed.
`coverage_attested` was not, and the consequence was worse than a missing
report section: the CLI decided scope from the **spine's** attestation while
the runner read the **composite's**, found nothing, and refused every
authorized composite release. `--source composite --spine catalog_v2` could
not publish at all. The same omission silently skipped the uncovered-roots
staleness gate, because `populated_roots` never reached the spine either and
the runner took the "a source that cannot report its roots is not asked to
guess" branch.

The Walmart module had already replaced hand-written forwarding with a generic
`__getattr__` and its comment names `coverage_attested` as one of the three it
lost. That implementation is now here too, which is what the read-before-you-
write rule asks for.

Three properties, and a test for each:

- A public attribute the composite does not define comes from the spine.
- One the spine lacks stays **absent**, rather than being forwarded as a
  neutral default. `unresolved_offers` used to forward as `[]`, so a spine
  keeping no such record read as a count of zero.
- The composite's own identity is not laundered: `source_mode` still reports
  `composite(...)` and `spine_source_mode` still reports what enumerated.
"""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from marianos_collector.composition import (  # noqa: E402
    CompositeSource, unavailable_crawl)
from marianos_collector.config import Category, Store  # noqa: E402
from marianos_collector.runner import Collector, ValidationFailure  # noqa: E402
from marianos_collector.sources import Page  # noqa: E402
from marianos_collector.storage import LocalStorage  # noqa: E402

STORE = Store("53100502", "60061", "Marianos - Vernon Hills",
              "1720 N Milwaukee Ave, Vernon Hills, IL 60061", "")
CATS = [Category("Dairy", "https://www.marianos.com/d/dairy"),
        Category("Produce", "https://www.marianos.com/d/produce")]


def product(n, category_hint="Dairy"):
    return {"store_id": STORE.store_id, "zipcode": STORE.zipcode,
            "store_context_verified": True, "seller_type": "marianos",
            "fulfillment": "pickup", "product_id": f"P{n}",
            "product_title": f"Item {n}", "weight": "12 oz",
            "regular_price": "4.99", "sale_price": "",
            "upc": f"999999{n:07d}", "brand": "T",
            "url": f"https://www.marianos.com/p/test-{n}",
            "image_url": "https://www.marianos.com/i.jpg", "ppm": "",
            "volume_deals_description": "", "volume_deals_price": "",
            "digital_deals_description": "", "digital_deals_price": ""}


class Spine:
    """A spine whose declarations are set per test."""

    source_mode = "kroger_catalog_v2_partner_api"

    def __init__(self, attested=True, roots=None, unresolved=None, count=3):
        if attested is not None:
            self.coverage_attested = attested
        if roots is not None:
            self.populated_roots = lambda: list(roots)
        if unresolved is not None:
            self.unresolved_offers = unresolved
        self.count = count
        self.reset_calls = 0

    def reset_unresolved(self):
        self.reset_calls += 1

    def fetch(self, store, category, url, cursor):
        return Page(store_id=store.store_id, zipcode=store.zipcode,
                    store_context_verified=True, source_url=url,
                    products=[product(i) for i in range(self.count)],
                    children=[], next_cursor="", subcategories_complete=True)


def composite(spine, enrichments=None):
    return CompositeSource(spine, "catalog_v2",
                           enrichments if enrichments is not None
                           else [unavailable_crawl("datacenter refused")])


class WhatTheSpineDeclaresReachesTheRunner(unittest.TestCase):
    def test_coverage_attested_true_is_forwarded(self):
        self.assertIs(composite(Spine(attested=True)).coverage_attested, True)

    def test_coverage_attested_false_is_forwarded_not_defaulted(self):
        self.assertIs(composite(Spine(attested=False)).coverage_attested, False)

    def test_populated_roots_reaches_the_spine(self):
        source = composite(Spine(roots=["Dairy", "Produce"]))
        self.assertEqual(source.populated_roots(), ["Dairy", "Produce"])

    def test_unresolved_offers_are_the_spines_own(self):
        source = composite(Spine(unresolved=[{"reason": "NO_PRICE"}]))
        self.assertEqual(source.unresolved_offers, [{"reason": "NO_PRICE"}])

    def test_a_composite_wrapping_a_composite_still_reaches_the_bottom(self):
        inner = composite(Spine(attested=True, roots=["Dairy"]))
        outer = CompositeSource(inner, "inner", [])
        self.assertIs(outer.coverage_attested, True)
        self.assertEqual(outer.populated_roots(), ["Dairy"])


class WhatTheSpineLacksStaysAbsent(unittest.TestCase):
    """Forwarding a neutral default is how a missing record reads as zero."""

    def test_an_attribute_the_spine_lacks_is_absent(self):
        source = composite(Spine(attested=None))
        self.assertFalse(hasattr(source, "coverage_attested"))
        with self.assertRaises(AttributeError):
            source.coverage_attested

    def test_unresolved_offers_is_absent_rather_than_an_empty_list(self):
        source = composite(Spine(attested=True))
        self.assertFalse(hasattr(source, "unresolved_offers"))

    def test_populated_roots_is_absent_rather_than_an_empty_list(self):
        source = composite(Spine(attested=True))
        self.assertFalse(hasattr(source, "populated_roots"))

    def test_private_names_are_never_forwarded(self):
        """The spine is given one, so this cannot pass merely because the
        attribute is missing everywhere. It matters because the composite keeps
        its own private state: forwarding privates would let a spine answer for
        `_traces` or `_refused` and the composite would report the spine's."""
        spine = Spine(attested=True)
        spine._secret = "the spine's"
        spine._refused = ["the spine's refusals"]
        source = composite(spine)
        with self.assertRaises(AttributeError):
            source._secret
        self.assertEqual(source._refused, [])


class TheCompositeDoesNotLaunderTheSpine(unittest.TestCase):
    def test_source_mode_still_says_composite(self):
        self.assertEqual(composite(Spine()).source_mode, "composite(catalog_v2)")

    def test_spine_source_mode_still_says_what_enumerated(self):
        self.assertEqual(composite(Spine()).spine_source_mode,
                         "kroger_catalog_v2_partner_api")

    def test_provenance_report_is_the_composites_own(self):
        report = composite(Spine()).provenance_report()
        self.assertEqual(report["spine"], "catalog_v2")
        self.assertIn("enrichments_unavailable", report)

    def test_durable_evidence_is_the_composites_own(self):
        self.assertIn("field_observations", composite(Spine()).durable_evidence())

    def test_reset_unresolved_reaches_the_spine_and_clears_the_composite(self):
        spine = Spine(unresolved=[{"reason": "x"}])
        source = composite(spine)
        source.reset_unresolved()
        self.assertEqual(spine.reset_calls, 1)
        self.assertEqual(source.provenance_report()["conflict_count"], 0)


class TheCompositePublishPathRuns(unittest.TestCase):
    """The consequence of the missing forward, as an end-to-end case."""

    def collect(self, spine, trial, uncovered=None):
        with tempfile.TemporaryDirectory() as td:
            return Collector(LocalStorage(Path(td)), composite(spine), CATS,
                             min_products=1, trial=trial,
                             uncovered_roots=uncovered).run(STORE)

    def test_an_attesting_spine_can_publish_a_full_release(self):
        out = self.collect(Spine(attested=True), trial=False)
        self.assertEqual(out["report"]["scope"], "full")
        self.assertTrue(out["report"]["source_coverage_attested"])
        self.assertTrue(out["manifest"]["data_key"].startswith("published/"))

    def test_a_non_attesting_spine_still_cannot(self):
        """The gate judges the spine's own statement, and is not relaxed."""
        with self.assertRaises(ValidationFailure) as caught:
            self.collect(Spine(attested=False), trial=False)
        self.assertIn("does not attest complete coverage", str(caught.exception))

    def test_the_unavailable_enrichment_is_still_disclosed(self):
        out = self.collect(Spine(attested=True), trial=False)
        self.assertEqual(out["report"]["provenance"]["enrichments_unavailable"],
                         {"crawl": "datacenter refused"})

    def test_a_stale_uncovered_declaration_is_caught_through_a_composite(self):
        """Previously skipped in silence: populated_roots never reached the
        spine, so the runner took the cannot-report branch."""
        with self.assertRaises(ValidationFailure) as caught:
            self.collect(Spine(attested=True, roots=["Dairy", "Seafood"]),
                         trial=True, uncovered={"Seafood": "no mapping label"})
        self.assertIn("declaration is stale", str(caught.exception))

    def test_a_declaration_that_is_not_stale_passes_through_a_composite(self):
        out = self.collect(Spine(attested=True, roots=["Dairy", "Produce"]),
                           trial=True, uncovered={"Seafood": "no mapping label"})
        self.assertEqual(out["report"]["roots_not_covered_by_source"],
                         {"Seafood": "no mapping label"})


if __name__ == "__main__":
    unittest.main()
