"""KrogerSweepSource: the term sweep driven by the collector.

The 26,166 delivered records came from a tool outside the runner, so they
never passed the publication gate, retention reconciliation, namespace
separation or a runner-driven resume. This is the adapter that closes that,
and these are the properties it has to have for the claim to be true.

Two of them are the whole reason the adapter is shaped the way it is:

- The source serves *raw products*, and the runner makes the records through
  the same `make_retained_record` the sweep uses. So there is one definition
  of what a product is, and a rule added to one path cannot miss the other.
- The index is built by reading the persisted API responses back off disk, not
  from the sweep's return value. The sweep's checkpoint holds finished
  records, so a resumed sweep has nothing to hand the runner for the terms it
  already did. Re-reading the responses makes a fresh run and a resumed run
  serve exactly the same products.

No test here touches the network.
"""

import io
import json
import logging
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from marianos_collector import cli  # noqa: E402
from marianos_collector.api_trial import observe  # noqa: E402
from marianos_collector.catalog_v2 import CatalogV2Source  # noqa: E402
from marianos_collector.config import Category, Store  # noqa: E402
from marianos_collector.kroger import KrogerError  # noqa: E402
from marianos_collector.kroger_sweep_source import (  # noqa: E402
    PAGES_PER_TERM, KrogerSweepSource)
from marianos_collector.runner import Collector, ValidationFailure  # noqa: E402
from marianos_collector.schema import FIELDS, make_retained_record  # noqa: E402
from marianos_collector.sources import AuthorizedProviderSource, FixtureSource  # noqa: E402
from marianos_collector.storage import LocalStorage  # noqa: E402
from marianos_collector.sweep_core import STATE_VERSION, store_from_locations  # noqa: E402

STORE = Store("53100502", "60061", "Marianos - Marianos Vernon Hills",
              "1720 N Milwaukee Ave, Vernon Hills, IL 60061", "")
CATEGORY_MAP = {"Dairy": "Dairy", "Produce": "Produce"}
CATEGORIES = [Category("Dairy", "https://www.marianos.com/d/dairy"),
              Category("Produce", "https://www.marianos.com/d/produce")]
LOCATION = {"data": {"locationId": "53100502", "chain": "MARIANOS",
                     "name": "Marianos - Marianos Vernon Hills",
                     "address": {"addressLine1": "1720 N Milwaukee Ave",
                                 "city": "Vernon Hills", "state": "IL",
                                 "zipCode": "60061"}}}


def offer(**changes):
    item = {"soldBy": "UNIT", "size": "18 ct", "fulfillment": {"curbside": True},
            "price": {"regular": 2.98, "promo": 0},
            "inventory": {"stockLevel": "HIGH"}}
    item.update(changes)
    return item


def product(upc, categories=("Dairy",), **changes):
    p = {"productId": upc, "upc": upc, "description": f"Item {upc}", "brand": "Kroger",
         "productPageURI": f"/p/item/{upc}", "categories": list(categories),
         "items": [offer()], "images": []}
    p.update(changes)
    return p


class FakeClient:
    """Serves a fixed product list per term, 50 at a time, like Kroger does."""

    def __init__(self, by_term, location=None):
        self.by_term = by_term
        self.location = location if location is not None else LOCATION
        self.calls = []

    def products(self, location_id, term, offset=0, limit=50):
        self.calls.append((term, offset))
        items = self.by_term.get(term, [])
        window = items[offset:offset + limit]
        return {"data": window,
                "meta": {"pagination": {"total": len(items), "start": offset,
                                        "limit": limit}}}

    def get(self, path):
        if path.startswith("/locations/"):
            return self.location
        raise KrogerError(f"unexpected path {path}")


def source(by_term, work_dir, terms=None, **kwargs):
    return KrogerSweepSource(FakeClient(by_term), "53100502", work_dir,
                             terms or {"Dairy": ["milk"]},
                             category_map=CATEGORY_MAP, **kwargs)


def served(src, category_name, store=STORE):
    """Every product the source serves for one root, walking its own cursors."""
    category = next(c for c in CATEGORIES if c.name == category_name)
    out, cursor, guard = [], "", 0
    while True:
        page = src.fetch(store, category, category.url, cursor)
        out.extend(page.products)
        cursor = page.next_cursor
        guard += 1
        if not cursor or guard > 500:
            break
    return out


class TheProductsOwnLabelDecidesTheRoot(unittest.TestCase):
    """The search term is how a product was found, not what it is."""

    def test_a_product_is_served_under_its_own_mapped_root(self):
        with tempfile.TemporaryDirectory() as td:
            src = source({"milk": [product("0001111060933", ("Produce",))]}, Path(td))
            self.assertEqual(served(src, "Produce")[0]["upc"], "0001111060933")
            self.assertEqual(served(src, "Dairy"), [])

    def test_an_unmapped_label_is_not_placed_under_the_terms_root(self):
        with tempfile.TemporaryDirectory() as td:
            src = source({"milk": [product("0001111060933", ("Nothing Mapped",))]},
                         Path(td))
            self.assertEqual(served(src, "Dairy"), [])
            self.assertEqual(served(src, "Produce"), [])
            prov = src.provenance_report()
            self.assertEqual(prov["unplaceable_unmapped_products"], 1)
            self.assertEqual(prov["unmapped_labels"], {"Nothing Mapped": 1})

    def test_an_unmapped_product_is_counted_as_seen_not_silently_lost(self):
        with tempfile.TemporaryDirectory() as td:
            src = source({"milk": [product("0001111060933", ("Nothing Mapped",))]},
                         Path(td))
            src.sweep_once(STORE)
            prov = src.provenance_report()
            self.assertEqual(prov["products_seen"], 1)
            self.assertEqual(prov["products_served"], 0)


class ItDoesNotClaimCoverage(unittest.TestCase):
    def test_the_source_declares_that_it_cannot_attest_coverage(self):
        self.assertFalse(KrogerSweepSource.coverage_attested)

    def test_every_page_reports_subcategory_discovery_as_incomplete(self):
        with tempfile.TemporaryDirectory() as td:
            src = source({"milk": [product("0001111060933")]}, Path(td))
            page = src.fetch(STORE, CATEGORIES[0], CATEGORIES[0].url, "")
            self.assertFalse(page.subcategories_complete)

    def test_it_cannot_publish_a_full_release(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(ValidationFailure) as caught:
                Collector(LocalStorage(Path(td) / "s"),
                          source({"milk": [product("0001111060933")]}, Path(td) / "w"),
                          CATEGORIES, min_products=1, trial=False)
            self.assertIn("does not attest complete coverage", str(caught.exception))

    def test_the_provenance_states_the_paging_ceiling(self):
        with tempfile.TemporaryDirectory() as td:
            prov = source({}, Path(td)).provenance_report()
            self.assertIn("skip count", prov["coverage_limit"])
            self.assertIn("300", prov["coverage_limit"])

    def test_it_asks_for_no_page_kroger_refuses(self):
        self.assertEqual(PAGES_PER_TERM, 6)
        with tempfile.TemporaryDirectory() as td:
            client = FakeClient({"milk": [product(f"000111106{i:04d}") for i in range(400)]})
            src = KrogerSweepSource(client, "53100502", Path(td), {"Dairy": ["milk"]},
                                    category_map=CATEGORY_MAP)
            src.sweep_once(STORE)
            self.assertEqual(max(offset for _, offset in client.calls), 250)


class PagingServesEveryProductExactlyOnce(unittest.TestCase):
    def test_the_cursor_walks_the_whole_root(self):
        with tempfile.TemporaryDirectory() as td:
            items = [product(f"000111106{i:04d}") for i in range(120)]
            src = source({"milk": items}, Path(td), serve_page_size=25)
            upcs = [p["upc"] for p in served(src, "Dairy")]
            self.assertEqual(len(upcs), 120)
            self.assertEqual(len(set(upcs)), 120)

    def test_the_last_page_ends_the_cursor(self):
        with tempfile.TemporaryDirectory() as td:
            items = [product(f"000111106{i:04d}") for i in range(10)]
            src = source({"milk": items}, Path(td), serve_page_size=25)
            page = src.fetch(STORE, CATEGORIES[0], CATEGORIES[0].url, "")
            self.assertEqual(page.next_cursor, "")
            self.assertEqual(len(page.products), 10)

    def test_an_exact_multiple_does_not_serve_an_empty_last_page(self):
        with tempfile.TemporaryDirectory() as td:
            items = [product(f"000111106{i:04d}") for i in range(50)]
            src = source({"milk": items}, Path(td), serve_page_size=25)
            first = src.fetch(STORE, CATEGORIES[0], CATEGORIES[0].url, "")
            self.assertTrue(first.next_cursor)
            second = src.fetch(STORE, CATEGORIES[0], CATEGORIES[0].url,
                               first.next_cursor)
            self.assertEqual(second.next_cursor, "")

    def test_a_product_found_by_two_terms_is_served_once(self):
        with tempfile.TemporaryDirectory() as td:
            shared = product("0001111060933")
            src = source({"milk": [shared], "eggs": [shared]}, Path(td),
                         terms={"Dairy": ["milk", "eggs"]})
            self.assertEqual(len(served(src, "Dairy")), 1)
            self.assertEqual(src.provenance_report()["duplicate_identities"], 1)


class TheIndexComesFromThePersistedResponses(unittest.TestCase):
    """Why: the checkpoint holds finished records, so a resumed sweep would
    otherwise serve fewer products than a fresh one for the same store."""

    def test_a_resumed_sweep_serves_what_a_fresh_one_served(self):
        with tempfile.TemporaryDirectory() as td:
            work = Path(td) / "work"
            items = [product(f"000111106{i:04d}") for i in range(30)]
            first = source({"milk": items}, work)
            fresh = [p["upc"] for p in served(first, "Dairy")]

            resumed_client = FakeClient({"milk": items})
            second = KrogerSweepSource(resumed_client, "53100502", work,
                                       {"Dairy": ["milk"]}, category_map=CATEGORY_MAP)
            again = [p["upc"] for p in served(second, "Dairy")]

            self.assertEqual(fresh, again)
            self.assertEqual(len(again), 30)
            # And it resumed rather than re-fetching: the term was already done.
            self.assertEqual(resumed_client.calls, [])

    def test_indexing_is_deterministic(self):
        with tempfile.TemporaryDirectory() as td:
            work = Path(td) / "work"
            items = [product(f"000111106{i:04d}") for i in range(40)]
            first = [p["upc"] for p in served(source({"milk": items}, work), "Dairy")]
            second = KrogerSweepSource(FakeClient({"milk": items}), "53100502", work,
                                       {"Dairy": ["milk"]}, category_map=CATEGORY_MAP)
            self.assertEqual(first, [p["upc"] for p in served(second, "Dairy")])

    def test_a_checkpoint_from_other_record_rules_is_refused_not_resumed(self):
        with tempfile.TemporaryDirectory() as td:
            work = Path(td) / "work"
            items = [product("0001111060933")]
            source({"milk": items}, work).sweep_once(STORE)
            state = json.loads((work / "checkpoint.json").read_text())
            state["state_version"] = STATE_VERSION + 1
            (work / "checkpoint.json").write_text(json.dumps(state))

            client = FakeClient({"milk": items})
            again = KrogerSweepSource(client, "53100502", work, {"Dairy": ["milk"]},
                                      category_map=CATEGORY_MAP)
            again.sweep_once(STORE)
            self.assertTrue(client.calls, "a refused checkpoint must be re-swept")

    def test_no_resume_re_fetches(self):
        with tempfile.TemporaryDirectory() as td:
            work = Path(td) / "work"
            items = [product("0001111060933")]
            source({"milk": items}, work).sweep_once(STORE)
            client = FakeClient({"milk": items})
            KrogerSweepSource(client, "53100502", work, {"Dairy": ["milk"]},
                              category_map=CATEGORY_MAP, resume=False).sweep_once(STORE)
            self.assertTrue(client.calls)

    def test_an_unreadable_response_file_is_reported_not_skipped_in_silence(self):
        with tempfile.TemporaryDirectory() as td:
            work = Path(td) / "work"
            src = source({"milk": [product("0001111060933")]}, work)
            src.sweep_once(STORE)
            path = next((work / "raw").rglob("start_*.json"))
            path.write_text("{ not json")
            again = KrogerSweepSource(FakeClient({}), "53100502", work,
                                      {"Dairy": ["milk"]}, category_map=CATEGORY_MAP)
            again.sweep_once(STORE)
            self.assertTrue(any(k.startswith("UNREADABLE_RESPONSE")
                                for k in again.provenance_report()["malformed_by_reason"]))


class OneDefinitionOfAProduct(unittest.TestCase):
    """The source hands raw products to the runner, which makes the record
    through the same function the sweep uses. The two must agree."""

    def test_the_runner_builds_the_same_record_the_sweep_would(self):
        with tempfile.TemporaryDirectory() as td:
            item = product("0001111060933")
            src = source({"milk": [item]}, Path(td))
            raw = served(src, "Dairy")[0]
            through_runner, _ = make_retained_record(
                raw, STORE, "Dairy", raw["sub_category"], "2026-11-02")
            through_sweep, _ = observe(item, STORE, "2026-11-02", CATEGORY_MAP)
            self.assertEqual(through_runner, through_sweep)

    def test_the_raw_product_satisfies_the_runners_store_context_check(self):
        with tempfile.TemporaryDirectory() as td:
            src = source({"milk": [product("0001111060933")]}, Path(td))
            raw = served(src, "Dairy")[0]
            self.assertEqual(raw["store_id"], STORE.store_id)
            self.assertEqual(raw["zipcode"], STORE.zipcode)
            self.assertIs(raw["store_context_verified"], True)

    def test_the_raw_product_carries_its_own_observation_time(self):
        with tempfile.TemporaryDirectory() as td:
            src = source({"milk": [product("0001111060933")]}, Path(td))
            self.assertTrue(served(src, "Dairy")[0]["observed_at"])

    def test_availability_is_carried_from_explicit_inventory(self):
        cases = {"HIGH": True, "OUT_OF_STOCK": False, "": None}
        for level, expected in cases.items():
            with self.subTest(level=level), tempfile.TemporaryDirectory() as td:
                item = product("0001111060933",
                               items=[offer(inventory={"stockLevel": level})])
                src = source({"milk": [item]}, Path(td))
                self.assertIs(served(src, "Dairy")[0]["pickup_available"], expected)


class ARunThroughTheCollector(unittest.TestCase):
    def test_the_collector_publishes_the_swept_products_as_a_trial(self):
        with tempfile.TemporaryDirectory() as td:
            by_term = {"milk": [product(f"000111106{i:04d}") for i in range(5)],
                       "apples": [product(f"000222206{i:04d}", ("Produce",))
                                  for i in range(4)]}
            src = source(by_term, Path(td) / "w",
                         terms={"Dairy": ["milk"], "Produce": ["apples"]})
            out = Collector(LocalStorage(Path(td) / "s"), src, CATEGORIES,
                            min_products=1, trial=True).run(STORE)
            report = out["report"]
            self.assertEqual(report["scope"], "trial")
            self.assertFalse(report["source_coverage_attested"])
            self.assertEqual(report["unique_records"], 9)
            self.assertEqual(report["category_counts"],
                             {"Dairy": 5, "Produce": 4})

    def test_an_empty_configured_root_still_fails_the_run(self):
        """Five of the client's 28 roots came back empty in the 31 October
        sweep, because Kroger's label vocabulary has no equivalent. The runner
        refusing that is correct, and is why a sweep run names its roots."""
        with tempfile.TemporaryDirectory() as td:
            src = source({"milk": [product("0001111060933")]}, Path(td) / "w")
            with self.assertRaises(ValidationFailure) as caught:
                Collector(LocalStorage(Path(td) / "s"), src, CATEGORIES,
                          min_products=1, trial=True).run(STORE)
            self.assertIn("Zero eligible products", str(caught.exception))

    def test_missing_roots_names_them_before_a_reviewer_has_to_guess(self):
        with tempfile.TemporaryDirectory() as td:
            src = source({"milk": [product("0001111060933")]}, Path(td))
            src.sweep_once(STORE)
            self.assertEqual(src.missing_roots(CATEGORIES), ["Produce"])

    def test_the_exclusions_the_brief_makes_are_still_applied_by_the_runner(self):
        """The source does not make records, so the approximate-weight
        exclusion has to come from the runner's own make_retained_record."""
        with tempfile.TemporaryDirectory() as td:
            good = [product(f"000111106{i:04d}") for i in range(3)]
            weighed = product("0001111069999",
                              items=[offer(size="about 1 lb")])
            src = source({"milk": good + [weighed], "apples": [
                product("0002222060001", ("Produce",))]}, Path(td) / "w",
                terms={"Dairy": ["milk"], "Produce": ["apples"]})
            out = Collector(LocalStorage(Path(td) / "s"), src, CATEGORIES,
                            min_products=1, trial=True).run(STORE)
            self.assertEqual(out["report"]["excluded_records_by_reason"],
                             {"APPROXIMATE_WEIGHT": 1})
            self.assertEqual(out["report"]["unique_records"], 4)

    def test_published_records_hold_the_resolved_store_columns(self):
        """The first sweep run wrote 18,351 records with a blank store_name
        and store_location. Nothing may serve a record without them."""
        with tempfile.TemporaryDirectory() as td:
            by_term = {"milk": [product("0001111060933")],
                       "apples": [product("0002222060001", ("Produce",))]}
            src = source(by_term, Path(td) / "w",
                         terms={"Dairy": ["milk"], "Produce": ["apples"]})
            out = Collector(LocalStorage(Path(td) / "s"), src, CATEGORIES,
                            min_products=1, trial=True).run(STORE)
            rows = json.loads(LocalStorage(Path(td) / "s").read(
                out["manifest"]["data_key"]))
            self.assertTrue(rows)
            for row in rows:
                self.assertEqual(list(row), list(FIELDS))
                self.assertEqual(row["store_name"], STORE.store_name)
                self.assertEqual(row["store_location"], STORE.store_location)


class TheStoreColumnsAreObservedNotTyped(unittest.TestCase):
    def test_the_store_is_built_from_krogers_own_locations_response(self):
        store, resolved = store_from_locations(
            FakeClient({}), "53100502", "60061", "1720 N Milwaukee Ave")
        self.assertEqual(store.store_id, "53100502")
        self.assertEqual(store.zipcode, "60061")
        self.assertEqual(store.store_name, "Marianos - Marianos Vernon Hills")
        self.assertEqual(resolved["store_location"],
                         "1720 N Milwaukee Ave, Vernon Hills, IL 60061")

    def test_a_different_street_is_refused(self):
        """West Loop's id differs from Vernon Hills' by two characters."""
        with self.assertRaises(KrogerError):
            store_from_locations(FakeClient({}), "53100502", "60061",
                                 "40 S Halsted St")

    def test_a_different_zip_is_refused(self):
        with self.assertRaises(KrogerError):
            store_from_locations(FakeClient({}), "53100502", "60661",
                                 "1720 N Milwaukee Ave")

    def test_another_banner_is_refused(self):
        other = {"data": dict(LOCATION["data"], chain="KROGER",
                              name="Kroger - Somewhere")}
        with self.assertRaises(ValueError):
            store_from_locations(FakeClient({}, other), "53100502", "60061",
                                 "1720 N Milwaukee Ave")


class TheCliTableMatchesTheClasses(unittest.TestCase):
    """cli.ATTESTS_COVERAGE is read before any source is constructed, so it
    duplicates a fact the classes already carry. This is the guard."""

    def test_every_kind_matches_its_class(self):
        classes = {"fixture": FixtureSource, "provider": AuthorizedProviderSource,
                   "catalog_v2": CatalogV2Source, "sweep": KrogerSweepSource}
        self.assertEqual(set(classes) | {"composite"}, set(cli.ATTESTS_COVERAGE))
        for kind, cls in classes.items():
            with self.subTest(kind=kind):
                self.assertEqual(cli.ATTESTS_COVERAGE[kind], cls.coverage_attested)

    def test_a_sweep_run_is_scoped_as_a_trial_without_a_category_subset(self):
        args = cli.parser_().parse_args(["run", "--source", "sweep"])
        self.assertFalse(cli.attests_coverage(args))

    def test_a_composite_takes_its_attestation_from_the_spine(self):
        sweep_spine = cli.parser_().parse_args(
            ["run", "--source", "composite", "--spine", "sweep"])
        v2_spine = cli.parser_().parse_args(
            ["run", "--source", "composite", "--spine", "catalog_v2"])
        self.assertFalse(cli.attests_coverage(sweep_spine))
        self.assertTrue(cli.attests_coverage(v2_spine))


class ItLogsThroughTheCollectorsOwnFormatter(unittest.TestCase):
    """`message` is a reserved LogRecord attribute. Passing one in `extra`
    raises inside logging, so the first version of this source crashed every
    sweep as soon as the CLI's handler was attached. The file's own tests
    passed, because nothing had attached a handler; only the whole suite
    caught it. This is the regression test, and it attaches the real one."""

    def test_a_sweep_logs_without_raising(self):
        logger = logging.getLogger("collector")
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(cli.Formatter())
        logger.addHandler(handler)
        previous = logger.level
        logger.setLevel(logging.INFO)
        logging.raiseExceptions = True
        try:
            with tempfile.TemporaryDirectory() as td:
                work = Path(td) / "work"
                src = source({"milk": [product("0001111060933")]}, work)
                src.sweep_once(STORE)
                # And the unreadable-checkpoint path, which logs an exception.
                (work / "checkpoint.json").write_text("{ not json")
                KrogerSweepSource(FakeClient({"milk": [product("0001111060933")]}),
                                  "53100502", work, {"Dairy": ["milk"]},
                                  category_map=CATEGORY_MAP).sweep_once(STORE)
        finally:
            logger.removeHandler(handler)
            logger.setLevel(previous)
        events = [json.loads(line)["event"] for line in
                  stream.getvalue().splitlines() if line.strip()]
        self.assertIn("sweep_indexed", events)
        self.assertIn("sweep_term_done", events)
        self.assertIn("sweep_checkpoint_unreadable", events)


class TheRealCliDrivesIt(unittest.TestCase):
    """The claim being made to the client is that the *collector* produces the
    data now, so the regression drives the actual CLI, not the Source. Only
    the Kroger client is replaced; everything else is the shipped code path."""

    def run_cli(self, work, out, store_file, categories_file, terms_file, extra=()):
        return cli.main([
            "run",
            "--stores", str(store_file),
            "--categories", str(categories_file),
            "--source", "sweep",
            "--location-id", "53100502",
            "--resolve-store",
            "--expect-zipcode", "60061",
            "--expect-street", "1720 N Milwaukee Ave",
            "--sweep-terms", str(terms_file),
            "--sweep-work-dir", str(work),
            "--output", str(out),
            "--minimum-products", "1",
            *extra,
        ])

    def test_a_run_publishes_to_the_trial_namespace_without_a_subset(self):
        by_term = {"milk": [product(f"000111106{i:04d}") for i in range(3)],
                   "apples": [product(f"000222206{i:04d}", ("Produce",))
                              for i in range(2)]}
        client = FakeClient(by_term)
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "categories.csv").write_text(
                "Retailer,Category (Auto),URL,Scope,Notes\n"
                "Mariano's,Dairy,https://www.marianos.com/d/dairy,Category,\n"
                "Mariano's,Produce,https://www.marianos.com/d/produce,Category,\n")
            (root / "stores.json").write_text(json.dumps({"stores": [{
                "store_id": "UNUSED", "zipcode": "00000", "store_name": "x",
                "store_location": "y", "store_logo": "", "enabled": True}]}))
            (root / "terms.json").write_text(json.dumps(
                {"terms": {"Dairy": ["milk"], "Produce": ["apples"]}}))
            # Only the Kroger client is replaced. The category map is the real
            # config/category_map.json, so the run also proves the shipped map
            # places these labels where the shipped categories.csv expects.
            with mock.patch.object(cli, "KrogerClient", return_value=client), \
                    mock.patch.object(cli.Credentials, "from_environment",
                                      return_value=None):
                code = self.run_cli(root / "work", root / "out",
                                    root / "stores.json", root / "categories.csv",
                                    root / "terms.json")
            self.assertEqual(code, 0)
            # The store columns were resolved from Kroger, not read from the
            # stores file, whose single entry is deliberately wrong.
            trials = sorted((root / "out").glob("trials/*/53100502/latest.json"))
            self.assertEqual(len(trials), 1, "a sweep run must land in a trial namespace")
            self.assertFalse((root / "out" / "published").exists())
            manifest = json.loads(
                (root / "out" / json.loads(trials[0].read_text())["manifest_key"]).read_text())
            rows = json.loads((root / "out" / manifest["data_key"]).read_text())
            self.assertEqual(len(rows), 5)
            self.assertEqual({r["store_location"] for r in rows},
                             {"1720 N Milwaukee Ave, Vernon Hills, IL 60061"})
            self.assertEqual(manifest["coverage_scope"], "subset_trial")
            self.assertEqual(manifest["source_mode"],
                             "kroger_public_products_api_term_sweep")
            report = json.loads(
                (root / "out" / manifest["report_key"]).read_text())
            self.assertFalse(report["source_coverage_attested"])
            self.assertEqual(report["scope"], "trial")
            self.assertEqual(report["category_counts"], {"Dairy": 3, "Produce": 2})

    def test_resolve_store_without_the_address_assertions_is_refused(self):
        """The assigned id differs from West Loop's by two characters, so the
        address is asserted rather than assumed. Without that, a typo in the
        id silently relabels every record as the wrong store."""
        for extra in (["--expect-zipcode", "60061"],
                      ["--expect-street", "1720 N Milwaukee Ave"],
                      []):
            with self.subTest(given=extra), self.assertRaises(SystemExit):
                cli.main(["run", "--source", "sweep", "--location-id", "53100502",
                          "--resolve-store", *extra])


class ItRefusesAPlaceholderStore(unittest.TestCase):
    def test_a_demo_location_id_is_refused(self):
        with tempfile.TemporaryDirectory() as td:
            for bad in ("", "DEMO-123", "REPLACE_ME", "UNRESOLVED"):
                with self.subTest(location_id=bad), self.assertRaises(ValueError):
                    KrogerSweepSource(FakeClient({}), bad, Path(td), {"Dairy": ["milk"]})

    def test_a_sweep_with_no_terms_refuses_rather_than_reporting_nothing_found(self):
        with tempfile.TemporaryDirectory() as td:
            src = KrogerSweepSource(FakeClient({}), "53100502", Path(td), {},
                                    category_map=CATEGORY_MAP)
            with self.assertRaises(ValueError):
                src.sweep_once(STORE)


if __name__ == "__main__":
    unittest.main()
