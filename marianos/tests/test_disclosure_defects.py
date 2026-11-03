"""Two defects where a release asserted something untrue.

Both came out of the independent review of 3 November and both are the same
class the client has twice caught: not a missing feature, but a report stating
a fact it had no basis for.

**1. The truncation flag could not fire through the collector.**
`terms_hit_start_cap` is the only per-term record that a search term had more
products behind it than the skip-count cap allows, and the 300-product ceiling
is the sweep's main quantitative coverage limit. It was only ever appended
inside the `start > max_start` branch, which the collector never reaches:
`PAGES_PER_TERM` stops at start 250 exactly. So the flag was structurally
always empty on that path and a release reported zero terms truncated when the
truth was that we could not know. The tool escaped it only because it passes
`--pages-per-term 20` and so requests a page Kroger refuses.

Truncation is now decided after the term's pages, from the term itself. A
reported total settles it: more than the ceiling is truncated, exactly the
ceiling is complete. Without a total, reaching the ceiling is all that is
known, and not knowing what sits behind it is itself the disclosure.

**2. `pickup_context` was empty in every runner-route release.**
`RETENTION_POLICY.md` requires `retention.json` to repeat, per identity, the
fulfillment flags, `soldBy`, stock level, offer classification and observation
time. The sweep tool supplied it. The runner did not, and
`retention.observation` had no parameter for it, so every release produced
through the collector carried `pickup_context: {}` and the policy was
unsatisfiable on that path. The policy also says to read `sold_by` before
`regular_price`, which that release gave a reader no way to do.
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from marianos_collector.config import Category, Store  # noqa: E402
from marianos_collector.kroger_sweep_source import (  # noqa: E402
    PAGES_PER_TERM, KrogerSweepSource)
from marianos_collector.retention import observation  # noqa: E402
from marianos_collector.runner import Collector  # noqa: E402
from marianos_collector.storage import LocalStorage  # noqa: E402
from marianos_collector.sweep_core import MAX_START  # noqa: E402

STORE = Store("53100502", "60061", "Marianos - Vernon Hills",
              "1720 N Milwaukee Ave, Vernon Hills, IL 60061", "")
CATS = [Category("Dairy", "https://www.marianos.com/d/dairy")]
CMAP = {"Dairy": "Dairy"}
CEILING = MAX_START + 50


def offer(**changes):
    item = {"soldBy": "UNIT", "size": "18 ct", "fulfillment": {"curbside": True},
            "price": {"regular": 2.98}, "inventory": {"stockLevel": "HIGH"}}
    item.update(changes)
    return item


def product(upc, **offer_changes):
    return {"productId": upc, "upc": upc, "description": f"Item {upc}",
            "brand": "Kroger", "productPageURI": f"/p/item/{upc}",
            "categories": ["Dairy"], "items": [offer(**offer_changes)], "images": []}


class Paged:
    """Serves `available` products, reporting `total` as Kroger would."""

    def __init__(self, available, total=None, report_total=True):
        self.available = available
        self.total = available if total is None else total
        self.report_total = report_total

    def products(self, location_id, term, offset=0, limit=50):
        items = [product(f"00011110{i:05d}")
                 for i in range(offset, min(offset + limit, self.available))]
        meta = {"pagination": {"total": self.total}} if self.report_total else {}
        return {"data": items, "meta": meta}

    def get(self, path):
        raise RuntimeError(path)


def swept(client, td):
    src = KrogerSweepSource(client, "53100502", Path(td), {"Dairy": ["milk"]},
                            category_map=CMAP)
    src.sweep_once(STORE)
    return src


class TruncationIsDisclosedThroughTheCollector(unittest.TestCase):
    def test_the_collector_never_requests_a_page_kroger_refuses(self):
        """Which is why the old flag could not fire, so this is the premise."""
        self.assertEqual((PAGES_PER_TERM - 1) * 50, MAX_START)

    def test_a_term_with_more_behind_it_is_flagged(self):
        with tempfile.TemporaryDirectory() as td:
            src = swept(Paged(available=CEILING, total=2000), td)
            self.assertEqual(src.provenance_report()["terms_hit_start_cap"], 1)

    def test_a_term_exactly_filling_the_ceiling_is_not_flagged(self):
        """A reported total of exactly the ceiling means nothing was missed."""
        with tempfile.TemporaryDirectory() as td:
            src = swept(Paged(available=CEILING, total=CEILING), td)
            self.assertEqual(src.provenance_report()["terms_hit_start_cap"], 0)

    def test_a_short_term_is_not_flagged(self):
        with tempfile.TemporaryDirectory() as td:
            src = swept(Paged(available=49, total=49), td)
            self.assertEqual(src.provenance_report()["terms_hit_start_cap"], 0)

    def test_reaching_the_ceiling_with_no_total_reported_is_flagged(self):
        """Not knowing what sits behind it is the disclosure, not a reason
        to report nothing."""
        with tempfile.TemporaryDirectory() as td:
            src = swept(Paged(available=CEILING, report_total=False), td)
            self.assertEqual(src.provenance_report()["terms_hit_start_cap"], 1)

    def test_a_term_is_flagged_once_not_once_per_page(self):
        with tempfile.TemporaryDirectory() as td:
            src = swept(Paged(available=CEILING, total=5000), td)
            self.assertEqual(
                len(src._state["terms_hit_start_cap"]),
                len(set(src._state["terms_hit_start_cap"])))

    def test_the_flag_travels_in_the_release(self):
        with tempfile.TemporaryDirectory() as td:
            storage = LocalStorage(Path(td) / "s")
            src = KrogerSweepSource(Paged(available=CEILING, total=2000),
                                    "53100502", Path(td) / "w",
                                    {"Dairy": ["milk"]}, category_map=CMAP)
            out = Collector(storage, src, CATS, min_products=1, trial=True).run(STORE)
            self.assertEqual(out["report"]["provenance"]["terms_hit_start_cap"], 1)


class ThePickupContextReachesRetention(unittest.TestCase):
    def run_one(self, td, **offer_changes):
        storage = LocalStorage(Path(td) / "s")

        class One:
            def products(self, location_id, term, offset=0, limit=50):
                items = [product("0001111060933", **offer_changes)] if not offset else []
                return {"data": items, "meta": {"pagination": {"total": 1}}}

            def get(self, path):
                raise RuntimeError(path)

        src = KrogerSweepSource(One(), "53100502", Path(td) / "w",
                                {"Dairy": ["milk"]}, category_map=CMAP)
        out = Collector(storage, src, CATS, min_products=1, trial=True).run(STORE)
        retention = json.loads(storage.read(out["manifest"]["retention_key"]))
        return next(iter(retention.values()))

    def test_retention_carries_everything_the_policy_names(self):
        with tempfile.TemporaryDirectory() as td:
            meta = self.run_one(td)
            context = meta["pickup_context"]
            for required in ("sold_by", "stock_level", "offer_status",
                            "offer_gaps", "fulfillment", "observed_at"):
                with self.subTest(required=required):
                    self.assertIn(required, context)

    def test_sold_by_weight_is_readable_before_the_price(self):
        """RETENTION_POLICY.md: read sold_by before reading regular_price.
        Through the collector that was unsatisfiable."""
        with tempfile.TemporaryDirectory() as td:
            meta = self.run_one(td, soldBy="WEIGHT", size="1 lb")
            self.assertEqual(meta["pickup_context"]["sold_by"], "WEIGHT")

    def test_a_product_with_no_qualifying_offer_says_why(self):
        with tempfile.TemporaryDirectory() as td:
            meta = self.run_one(td, soldBy="WEIGHT",
                                fulfillment={"curbside": False},
                                inventory={"stockLevel": "OUT_OF_STOCK"})
            context = meta["pickup_context"]
            self.assertEqual(context["offer_status"], "no_qualifying_pickup_offer")
            self.assertEqual(sorted(context["offer_gaps"]),
                             ["NOT_SOLD_BY_UNIT", "NO_CURBSIDE_PICKUP"])
            self.assertEqual(meta["availability_state"], "unavailable")

    def test_the_context_names_the_response_it_came_from(self):
        with tempfile.TemporaryDirectory() as td:
            meta = self.run_one(td)
            self.assertTrue(meta["pickup_context"]["response_file"].endswith(".json"))

    def test_a_source_supplying_no_context_records_an_empty_one(self):
        """Absent rather than invented, and visibly absent."""
        self.assertEqual(
            observation({}, "53100502", "2026-11-03T00:00:00+00:00")["pickup_context"],
            {})

    def test_the_context_is_not_shared_between_identities(self):
        obs = observation({}, "53100502", "2026-11-03T00:00:00+00:00",
                          pickup_context={"sold_by": "UNIT"})
        obs["pickup_context"]["sold_by"] = "MUTATED"
        again = observation({}, "53100502", "2026-11-03T00:00:00+00:00",
                            pickup_context={"sold_by": "UNIT"})
        self.assertEqual(again["pickup_context"]["sold_by"], "UNIT")


if __name__ == "__main__":
    unittest.main()
