"""Three defects an independent review found in the sweep adapter, and the gates for them.

The adapter was written, mutation-tested and committed, and then reviewed by
an agent given the code and the requirements but not the author's reasoning
and told to assume the author was wrong. It found these. Each one was
reproduced before being fixed and each has a test here that fails when the fix
is reverted. They are kept in their own file because they are not variations
on the happy path: they are the three ways this source could publish something
the working rules forbid.

1. **Cross-store relabelling.** `to_raw_product` stamps the store columns and
   `store_context_verified: True` from whatever Store it is handed, and
   `_index_raw` globbed every response in the work directory without checking
   which location it was collected at. A work directory shared between two
   stores served three West Loop products as verified Vernon Hills
   observations, silently. `CLAUDE.md` forbids exactly this by name.

2. **Cross-process cursor loss.** The cursor was an integer offset into a list
   rebuilt from disk per process. Across two processes: 14 products observed,
   10 published, 4 served by neither, `status: validated`, no gate fired.
   That breaks "a product is never removed from the delivered dataset".

3. **Disclosure that reached no release.** The method was called
   `provenance()`; the runner looks for `provenance_report()`. So the unmapped
   labels, the 187 unplaceable products, the page failures, the stop reason
   and the coverage limit were computed onto an object the CLI discarded,
   while `CLAUDE.md` claimed they were "counted and named in provenance()".
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from marianos_collector.config import Category, Store  # noqa: E402
from marianos_collector.kroger_sweep_source import (  # noqa: E402
    KrogerSweepSource, SweepCursorInvalid)
from marianos_collector.runner import Collector, ValidationFailure  # noqa: E402
from marianos_collector.storage import LocalStorage  # noqa: E402

WEST_LOOP = Store("53100508", "60661", "Marianos - Marianos West Loop",
                  "40 S Halsted St, Chicago, IL 60661", "")
VERNON = Store("53100502", "60061", "Marianos - Marianos Vernon Hills",
               "1720 N Milwaukee Ave, Vernon Hills, IL 60061", "")
CMAP = {"Dairy": "Dairy", "Produce": "Produce"}
CATS = [Category("Dairy", "https://www.marianos.com/d/dairy"),
        Category("Produce", "https://www.marianos.com/d/produce")]


def offer(**changes):
    item = {"soldBy": "UNIT", "size": "18 ct", "fulfillment": {"curbside": True},
            "price": {"regular": 2.98}, "inventory": {"stockLevel": "HIGH"}}
    item.update(changes)
    return item


def product(upc, categories=("Dairy",)):
    return {"productId": upc, "upc": upc, "description": f"Item {upc}",
            "brand": "Kroger", "productPageURI": f"/p/item/{upc}",
            "categories": list(categories), "items": [offer()], "images": []}


class Fake:
    def __init__(self, by_term):
        self.by_term = by_term
        self.calls = []

    def products(self, location_id, term, offset=0, limit=50):
        self.calls.append((term, offset))
        items = self.by_term.get(term, [])
        return {"data": items[offset:offset + limit],
                "meta": {"pagination": {"total": len(items)}}}

    def get(self, path):
        raise RuntimeError(path)


def src(by_term, location_id, work, terms, **kw):
    return KrogerSweepSource(Fake(by_term), location_id, work, terms,
                             category_map=CMAP, **kw)


def walk(source, store, category, first_cursor=""):
    out, cursor = [], first_cursor
    while True:
        page = source.fetch(store, category, category.url, cursor)
        out.extend(page.products)
        cursor = page.next_cursor
        if not cursor:
            return out


class AnotherStoresObservationsAreNeverRelabelled(unittest.TestCase):
    """Defect 1. The reproduction, as a test."""

    def two_stores_one_work_dir(self, td):
        work = Path(td) / "shared"
        wl = [product(f"000111106{i:04d}") for i in range(3)]
        src({"milk": wl}, "53100508", work, {"Dairy": ["milk"]}).fetch(
            WEST_LOOP, CATS[0], CATS[0].url, "")
        vh = [product("0002222060001")]
        second = src({"eggs": vh}, "53100502", work, {"Dairy": ["eggs"]})
        return second, walk(second, VERNON, CATS[0]), {p["upc"] for p in wl}

    def test_a_shared_work_dir_does_not_leak_the_other_store(self):
        with tempfile.TemporaryDirectory() as td:
            source, served, west_loop_upcs = self.two_stores_one_work_dir(td)
            self.assertEqual([p["upc"] for p in served], ["0002222060001"])
            self.assertEqual({p["upc"] for p in served} & west_loop_upcs, set())

    def test_the_refusal_is_counted_not_silent(self):
        with tempfile.TemporaryDirectory() as td:
            source, _, _ = self.two_stores_one_work_dir(td)
            refused = source.provenance_report()["responses_refused_as_foreign_location"]
            self.assertEqual(refused, {"53100508": 1})

    def test_a_response_with_no_location_is_refused_too(self):
        """Not knowing which store a response came from is not a reason to
        assume it is this one."""
        with tempfile.TemporaryDirectory() as td:
            work = Path(td) / "w"
            source = src({"milk": [product("0001111060933")]}, "53100502", work,
                         {"Dairy": ["milk"]})
            source.sweep_once(VERNON)
            path = next((work / "raw").rglob("start_*.json"))
            document = json.loads(path.read_text())
            del document["locationId"]
            path.write_text(json.dumps(document))

            again = src({}, "53100502", work, {"Dairy": ["milk"]})
            again.sweep_once(VERNON)
            self.assertEqual(walk(again, VERNON, CATS[0]), [])
            self.assertEqual(
                again.provenance_report()["responses_refused_as_foreign_location"],
                {"(absent)": 1})

    def test_the_store_that_does_own_the_responses_still_serves_them(self):
        """The guard must not be a blanket refusal."""
        with tempfile.TemporaryDirectory() as td:
            work = Path(td) / "w"
            items = [product(f"000111106{i:04d}") for i in range(3)]
            src({"milk": items}, "53100502", work, {"Dairy": ["milk"]}).sweep_once(VERNON)
            again = src({}, "53100502", work, {"Dairy": ["milk"]})
            self.assertEqual(len(walk(again, VERNON, CATS[0])), 3)
            self.assertEqual(
                again.provenance_report()["responses_refused_as_foreign_location"], {})


class AStaleCursorRefusesRatherThanLosingProducts(unittest.TestCase):
    """Defect 2. A bare offset into a rebuilt list is not a cursor."""

    def test_a_cursor_issued_against_other_contents_is_refused(self):
        with tempfile.TemporaryDirectory() as td:
            work = Path(td) / "w"
            late = [product(f"000111106{i:04d}") for i in range(8)]
            first = src({"milk": late}, "53100502", work, {"Dairy": ["milk"]},
                        serve_page_size=4)
            page = first.fetch(VERNON, CATS[0], CATS[0].url, "")
            self.assertTrue(page.next_cursor)

            early = [product(f"000222206{i:04d}") for i in range(6)]
            grown = src({"milk": late, "apples": early}, "53100502", work,
                        {"Dairy": ["milk", "apples"]}, serve_page_size=4)
            with self.assertRaises(SweepCursorInvalid) as caught:
                grown.fetch(VERNON, CATS[0], CATS[0].url, page.next_cursor)
            self.assertIn("changed since this cursor was issued",
                          str(caught.exception))

    def test_the_runner_stops_instead_of_publishing_a_short_release(self):
        """The end-to-end case. Before the fix this published 10 of 14 with
        status validated and no gate fired."""
        with tempfile.TemporaryDirectory() as td:
            work, store = Path(td) / "w", LocalStorage(Path(td) / "s")
            late = [product(f"000111106{i:04d}") for i in range(8)]
            one = src({"milk": late}, "53100502", work, {"Dairy": ["milk"]},
                      serve_page_size=4)
            with self.assertRaises(ValidationFailure):
                Collector(store, one, CATS[:1], min_products=1, trial=True,
                          max_pages=1).run(VERNON)

            early = [product(f"000222206{i:04d}") for i in range(6)]
            two = src({"milk": late, "apples": early}, "53100502", work,
                      {"Dairy": ["milk", "apples"]}, serve_page_size=4)
            with self.assertRaises(SweepCursorInvalid):
                Collector(store, two, CATS[:1], min_products=1,
                          trial=True).run(VERNON)

    def test_an_unchanged_index_resumes_normally(self):
        """The refusal must not break the ordinary resume it exists to protect."""
        with tempfile.TemporaryDirectory() as td:
            work = Path(td) / "w"
            items = [product(f"000111106{i:04d}") for i in range(8)]
            first = src({"milk": items}, "53100502", work, {"Dairy": ["milk"]},
                        serve_page_size=4)
            page = first.fetch(VERNON, CATS[0], CATS[0].url, "")
            second = src({"milk": items}, "53100502", work, {"Dairy": ["milk"]},
                         serve_page_size=4)
            resumed = second.fetch(VERNON, CATS[0], CATS[0].url, page.next_cursor)
            self.assertEqual([p["upc"] for p in resumed.products],
                             [p["upc"] for p in items[4:8]])

    def test_a_malformed_cursor_is_refused_not_treated_as_zero(self):
        with tempfile.TemporaryDirectory() as td:
            source = src({"milk": [product("0001111060933")]}, "53100502",
                         Path(td), {"Dairy": ["milk"]})
            source.sweep_once(VERNON)
            for bad in ("4", "garbage", "abc:xyz", ":"):
                with self.subTest(cursor=bad), self.assertRaises(SweepCursorInvalid):
                    source.fetch(VERNON, CATS[0], CATS[0].url, bad)

    def test_every_product_is_still_served_exactly_once_in_one_process(self):
        with tempfile.TemporaryDirectory() as td:
            items = [product(f"000111106{i:04d}") for i in range(120)]
            source = src({"milk": items}, "53100502", Path(td),
                         {"Dairy": ["milk"]}, serve_page_size=25)
            upcs = [p["upc"] for p in walk(source, VERNON, CATS[0])]
            self.assertEqual(len(upcs), 120)
            self.assertEqual(len(set(upcs)), 120)


class TheDisclosureReachesTheRelease(unittest.TestCase):
    """Defect 3. It was computed onto an object the CLI threw away."""

    def run_one(self, td, by_term, terms):
        work, store = Path(td) / "w", LocalStorage(Path(td) / "s")
        source = src(by_term, "53100502", work, terms)
        out = Collector(store, source, CATS, min_products=1, trial=True).run(VERNON)
        return out["report"]

    def test_the_runner_emits_the_sources_provenance(self):
        with tempfile.TemporaryDirectory() as td:
            report = self.run_one(td, {"milk": [product("0001111060933")],
                                       "apples": [product("0002222060001", ("Produce",))]},
                                  {"Dairy": ["milk"], "Produce": ["apples"]})
            self.assertIn("provenance", report)
            prov = report["provenance"]
            self.assertEqual(prov["source_mode"],
                             "kroger_public_products_api_term_sweep")
            self.assertEqual(prov["products_served"], 2)
            self.assertFalse(prov["coverage_attested"])

    def test_the_unmapped_products_are_named_in_the_release(self):
        """The claim CLAUDE.md made about the 187, tested where it matters."""
        with tempfile.TemporaryDirectory() as td:
            report = self.run_one(
                td, {"milk": [product("0001111060933"),
                              product("0001111069999", ("Nothing Mapped",))],
                     "apples": [product("0002222060001", ("Produce",))]},
                {"Dairy": ["milk"], "Produce": ["apples"]})
            prov = report["provenance"]
            self.assertEqual(prov["unplaceable_unmapped_products"], 1)
            self.assertEqual(prov["unmapped_labels"], {"Nothing Mapped": 1})

    def test_the_coverage_limit_travels_with_the_release(self):
        with tempfile.TemporaryDirectory() as td:
            report = self.run_one(td, {"milk": [product("0001111060933")],
                                       "apples": [product("0002222060001", ("Produce",))]},
                                  {"Dairy": ["milk"], "Produce": ["apples"]})
            self.assertIn("skip count", report["provenance"]["coverage_limit"])


class AnEmptyRootSaysWhatTheRouteDidReach(unittest.TestCase):
    """CLAUDE.md claimed missing_roots() spared the reviewer a bare validation
    failure. Nothing called it. The failure now carries the information."""

    def test_the_zero_products_failure_names_the_populated_roots(self):
        with tempfile.TemporaryDirectory() as td:
            work, store = Path(td) / "w", LocalStorage(Path(td) / "s")
            source = src({"milk": [product("0001111060933")]}, "53100502", work,
                         {"Dairy": ["milk"]})
            with self.assertRaises(ValidationFailure) as caught:
                Collector(store, source, CATS, min_products=1, trial=True).run(VERNON)
            message = str(caught.exception)
            self.assertIn("Zero eligible products: Produce", message)
            self.assertIn("'Dairy'", message)
            self.assertIn("--uncovered-roots", message)

    def test_a_source_that_cannot_report_its_roots_still_fails_cleanly(self):
        class Quiet:
            source_mode = "quiet"
            coverage_attested = False

            def fetch(self, store, category, url, cursor):
                from marianos_collector.sources import Page
                return Page(store_id=store.store_id, zipcode=store.zipcode,
                            store_context_verified=True, source_url=url,
                            products=[], children=[], next_cursor="",
                            subcategories_complete=False)

        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(ValidationFailure) as caught:
                Collector(LocalStorage(Path(td)), Quiet(), CATS,
                          min_products=1, trial=True).run(VERNON)
            self.assertIn("Zero eligible products", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
