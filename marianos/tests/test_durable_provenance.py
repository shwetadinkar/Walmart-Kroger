"""Two points the client made on 3 November, as gates.

**1. A capped preview is not the evidence.** `provenance_report` returned
`self._refused[:200]`, on an object the CLI discarded after the run. His words:
"If that is the persisted evidence, later refused observations are still lost.
Keep complete durable history separately; a capped report preview is fine when
it points to that complete record." So the complete list lives in
`durable_evidence()`, the runner persists it as its own artefact keyed in the
manifest, and the report carries a preview that names it.

**2. An older observation must not be relabelled as a new one.** His words:
"The seven-day freshness rule is an explicit improvement over accepting
arbitrary text, but it must not relabel an older observed price or offer as
newly observed on a later run. Preserve each source observation time and its
context." The merged provenance recorded which source supplied each field and
no observation time at all, so a page value read days after the spine left no
trace of when it was seen. The per-field source observation time is now part
of the durable record.

The 201st refused contribution is the test that matters here. Before the fix
it existed nowhere once the run ended.
"""

import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from marianos_collector.composition import (  # noqa: E402
    BINDING_KEY, DURABLE_EVIDENCE_FILENAME, CallableEnrichment, CompositeSource)
from marianos_collector.config import Category, Store  # noqa: E402
from marianos_collector.runner import Collector  # noqa: E402
from marianos_collector.sources import Page  # noqa: E402
from marianos_collector.storage import LocalStorage  # noqa: E402

STORE = Store("53100502", "60061", "Marianos - Vernon Hills",
              "1720 N Milwaukee Ave, Vernon Hills, IL 60061", "")
CAT = Category("Dairy", "https://www.marianos.com/d/dairy")


def now_iso(**delta):
    return (datetime.now(timezone.utc) - timedelta(**delta)).isoformat()


def binding(identity, observed_at=None, fulfillment="pickup"):
    """A binding must name the product it was observed for; `binding_refusal`
    refuses one that does not, which is the rule under test elsewhere."""
    return {"identity": identity, "store_id": STORE.store_id,
            "zipcode": STORE.zipcode, "fulfillment": fulfillment,
            "observed_at": observed_at or now_iso(hours=1)}


def spine_product(n, **extra):
    base = {
        "store_id": STORE.store_id, "zipcode": STORE.zipcode,
        "store_context_verified": True, "seller_type": "marianos",
        "fulfillment": "pickup", "product_id": f"P{n:05d}",
        "product_title": f"Item {n}", "weight": "12 oz",
        "regular_price": "4.99", "sale_price": "",
        "upc": f"999999{n:07d}", "brand": "Test",
        "url": f"https://www.marianos.com/p/test-{n}",
        "image_url": f"https://www.marianos.com/images/{n}.jpg",
        "ppm": "", "volume_deals_description": "", "volume_deals_price": "",
        "digital_deals_description": "", "digital_deals_price": "",
    }
    base.update(extra)
    return base


def composite(count, lookup, policy=None):
    class Spine:
        source_mode = "test_spine"
        unresolved_offers = []

        def fetch(self, store, category, url, cursor):
            return Page(store_id=store.store_id, zipcode=store.zipcode,
                        store_context_verified=True, source_url=url,
                        products=[spine_product(i) for i in range(count)],
                        children=[], next_cursor="", subcategories_complete=True)

    source = CompositeSource(
        Spine(), "spine", [CallableEnrichment("crawl", ("ppm",), lookup)],
        policy=policy)
    source.fetch(STORE, CAT, CAT.url, "")
    return source


class ThePreviewIsNotTheEvidence(unittest.TestCase):
    def refuse_many(self, count):
        """Every contribution refused as stale, so all `count` are recorded."""
        def lookup(store, identity, product):
            return {"ppm": f"$0.{identity[-2:]}/oz",
                    BINDING_KEY: binding(identity, observed_at=now_iso(days=30))}
        return composite(count, lookup)

    def test_the_two_hundred_and_first_refusal_survives(self):
        source = self.refuse_many(250)
        report = source.provenance_report()
        durable = source.durable_evidence()
        self.assertEqual(report["refused_contribution_count"], 250)
        self.assertEqual(len(report["refused_contributions_preview"]), 200)
        self.assertEqual(len(durable["refused_contributions"]), 250)

    def test_the_preview_says_it_is_capped_and_where_the_rest_is(self):
        report = self.refuse_many(250).provenance_report()
        self.assertEqual(report["refused_contributions_preview_capped_at"], 200)
        self.assertEqual(report["complete_evidence_artifact"],
                         DURABLE_EVIDENCE_FILENAME)

    def test_the_old_uncapped_key_is_gone_so_nothing_reads_the_preview_as_complete(self):
        report = self.refuse_many(5).provenance_report()
        self.assertNotIn("refused_contributions", report)

    def test_conflicts_are_uncapped_in_the_durable_record_too(self):
        def lookup(store, identity, product):
            return {"ppm": "$9.99/oz", BINDING_KEY: binding(identity)}
        # The spine offers a ppm the enrichment disagrees with, for 250 products.
        class Spine:
            source_mode = "test_spine"
            unresolved_offers = []

            def fetch(self, store, category, url, cursor):
                return Page(store_id=store.store_id, zipcode=store.zipcode,
                            store_context_verified=True, source_url=url,
                            products=[spine_product(i, ppm="$1.11/oz")
                                      for i in range(250)],
                            children=[], next_cursor="",
                            subcategories_complete=True)

        source = CompositeSource(
            Spine(), "spine", [CallableEnrichment("crawl", ("ppm",), lookup)],
            policy={"ppm": ("crawl", "spine")})
        source.fetch(STORE, CAT, CAT.url, "")
        self.assertEqual(source.provenance_report()["conflict_count"], 250)
        self.assertEqual(len(source.durable_evidence()["conflicts"]), 250)


class EachFieldKeepsTheTimeItsSourceObservedIt(unittest.TestCase):
    def test_the_merged_field_carries_its_own_source_observation_time(self):
        seen = now_iso(hours=6)

        def lookup(store, identity, product):
            return {"ppm": "$0.33/oz", BINDING_KEY: binding(identity, observed_at=seen)}

        source = composite(1, lookup, policy={"ppm": ("crawl", "spine")})
        observations = source.durable_evidence()["field_observations"]
        self.assertEqual(len(observations), 1)
        per_field = next(iter(observations.values()))
        self.assertEqual(per_field["ppm"]["source"], "crawl")
        self.assertEqual(per_field["ppm"]["source_observed_at"], seen)

    def test_two_sources_observed_at_different_times_stay_distinguishable(self):
        """The point of his objection: one record, two fields, two dates."""
        early, late = now_iso(days=5), now_iso(hours=1)

        def lookup(store, identity, product):
            if product["upc"].endswith("0000"):
                return {"ppm": "$0.11/oz", BINDING_KEY: binding(identity, observed_at=early)}
            return {"ppm": "$0.22/oz", BINDING_KEY: binding(identity, observed_at=late)}

        source = composite(2, lookup, policy={"ppm": ("crawl", "spine")})
        times = {v["ppm"]["source_observed_at"]
                 for v in source.durable_evidence()["field_observations"].values()}
        self.assertEqual(times, {early, late})

    def test_a_refused_contribution_keeps_its_own_date(self):
        old = now_iso(days=30)

        def lookup(store, identity, product):
            return {"ppm": "$0.33/oz", BINDING_KEY: binding(identity, observed_at=old)}

        durable = composite(1, lookup).durable_evidence()
        self.assertEqual(durable["refused_contributions"][0]["binding"]["observed_at"],
                         old)
        self.assertEqual(durable["field_observations"], {})

    def test_the_count_in_the_report_matches_the_durable_record(self):
        def lookup(store, identity, product):
            return {"ppm": "$0.33/oz", BINDING_KEY: binding(identity)}

        source = composite(7, lookup, policy={"ppm": ("crawl", "spine")})
        self.assertEqual(source.provenance_report()["field_observations_recorded"],
                         source.durable_evidence()["field_observation_count"])
        self.assertEqual(source.durable_evidence()["field_observation_count"], 7)


class TheRunnerPersistsIt(unittest.TestCase):
    """Computing it is not keeping it. The same mistake as provenance()."""

    def run_once(self, td, lookup, count=3):
        class Spine:
            source_mode = "test_spine"
            coverage_attested = True
            unresolved_offers = []

            def fetch(self, store, category, url, cursor):
                return Page(store_id=store.store_id, zipcode=store.zipcode,
                            store_context_verified=True, source_url=url,
                            products=[spine_product(i) for i in range(count)],
                            children=[], next_cursor="",
                            subcategories_complete=True)

        source = CompositeSource(
            Spine(), "spine", [CallableEnrichment("crawl", ("ppm",), lookup)],
            policy={"ppm": ("crawl", "spine")})
        storage = LocalStorage(Path(td))
        out = Collector(storage, source, [CAT], min_products=1, trial=True).run(STORE)
        return storage, out

    def test_the_manifest_names_the_evidence_artifact(self):
        def lookup(store, identity, product):
            return {"ppm": "$0.33/oz", BINDING_KEY: binding(identity)}

        with tempfile.TemporaryDirectory() as td:
            storage, out = self.run_once(td, lookup)
            key = out["manifest"]["provenance_evidence_key"]
            self.assertTrue(key.endswith("/provenance_evidence.json"))
            evidence = json.loads(storage.read(key))
            self.assertEqual(evidence["field_observation_count"], 3)

    def test_the_persisted_record_holds_every_refusal_not_two_hundred(self):
        def lookup(store, identity, product):
            return {"ppm": "$0.33/oz",
                    BINDING_KEY: binding(identity, observed_at=now_iso(days=30))}

        with tempfile.TemporaryDirectory() as td:
            storage, out = self.run_once(td, lookup, count=250)
            evidence = json.loads(storage.read(out["manifest"]["provenance_evidence_key"]))
            self.assertEqual(len(evidence["refused_contributions"]), 250)
            self.assertEqual(
                len(out["report"]["provenance"]["refused_contributions_preview"]), 200)

    def test_a_source_without_durable_evidence_still_runs(self):
        """Not every source composes. The key is empty rather than absent, so
        a reader can tell "none to keep" from "forgot to keep it"."""
        class Plain:
            source_mode = "plain"
            coverage_attested = True

            def fetch(self, store, category, url, cursor):
                return Page(store_id=store.store_id, zipcode=store.zipcode,
                            store_context_verified=True, source_url=url,
                            products=[spine_product(1)], children=[],
                            next_cursor="", subcategories_complete=True)

        with tempfile.TemporaryDirectory() as td:
            out = Collector(LocalStorage(Path(td)), Plain(), [CAT],
                            min_products=1, trial=True).run(STORE)
            self.assertEqual(out["manifest"]["provenance_evidence_key"], "")


if __name__ == "__main__":
    unittest.main()
