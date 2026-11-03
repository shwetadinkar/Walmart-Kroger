"""A refused run must leave something to read.

Unattended twice weekly, the only trace of a failure was the exception and a
log line. The schedule moved on, no artefact existed, and a budget-stopped or
partially collected sweep looked identical to a run that never started. For a
job nobody is watching, that is the difference between a diagnosable failure
and a silent one.

The release is still refused — that protection is the entire point and none of
it is relaxed here. What changes is that the attempt is recorded beside the
namespace it would have published into, carrying how far the source actually
got, and the latest pointer is untouched.

Two things this must not do, and both have tests: it must not publish, and it
must not swallow or replace the error.
"""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from marianos_collector import cli  # noqa: E402
from marianos_collector.config import Category, Store  # noqa: E402
from marianos_collector.runner import Collector, ValidationFailure  # noqa: E402
from marianos_collector.sources import Page  # noqa: E402
from marianos_collector.storage import LocalStorage  # noqa: E402

STORE = Store("53100502", "60061", "Marianos - Vernon Hills",
              "1720 N Milwaukee Ave, Vernon Hills, IL 60061", "")
CATS = [Category("Dairy", "https://www.marianos.com/d/dairy"),
        Category("Produce", "https://www.marianos.com/d/produce")]


def product(n):
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


class Source:
    source_mode = "test_source"
    coverage_attested = True

    def __init__(self, per_category=None, provenance=None, raises=None):
        self.per_category = per_category or {}
        self._provenance = provenance
        self.raises = raises
        if provenance is not None:
            self.provenance_report = lambda: provenance

    def fetch(self, store, category, url, cursor):
        if self.raises:
            raise self.raises
        count = self.per_category.get(category.name, 1)
        return Page(store_id=store.store_id, zipcode=store.zipcode,
                    store_context_verified=True, source_url=url,
                    products=[product(i) for i in range(count)], children=[],
                    next_cursor="", subcategories_complete=True)


def attempt(td, source, **kw):
    storage = LocalStorage(Path(td))
    collector = Collector(storage, source, CATS, min_products=1, trial=True, **kw)
    try:
        collector.run(STORE)
        return storage, None
    except (ValidationFailure, ValueError) as exc:
        return storage, exc


def failures(storage_root):
    """Failure records live outside the publishing namespace, under failures/,
    so the namespace tree stays provably release-only."""
    root = Path(storage_root) / "failures"
    return sorted(root.rglob("*.json")) if root.is_dir() else []


class ARefusedRunIsRecorded(unittest.TestCase):
    def test_a_zero_product_root_leaves_an_artifact(self):
        with tempfile.TemporaryDirectory() as td:
            storage, exc = attempt(td, Source({"Dairy": 1, "Produce": 0}))
            self.assertIsInstance(exc, ValidationFailure)
            self.assertEqual(len(failures(td)), 1)

    def test_the_artifact_carries_the_reason_verbatim(self):
        with tempfile.TemporaryDirectory() as td:
            storage, exc = attempt(td, Source({"Dairy": 1, "Produce": 0}))
            record = json.loads(failures(td)[0].read_text())
            self.assertIn("Zero eligible products: Produce", record["refused_with"])
            self.assertIn("ValidationFailure", record["refused_with"])

    def test_it_records_the_scope_and_the_configured_roots(self):
        with tempfile.TemporaryDirectory() as td:
            attempt(td, Source({"Dairy": 1, "Produce": 0}))
            record = json.loads(failures(td)[0].read_text())
            self.assertEqual(record["scope"], "trial")
            self.assertEqual(record["roots_configured"], ["Dairy", "Produce"])
            self.assertEqual(record["store_id"], STORE.store_id)

    def test_it_records_how_far_the_source_got(self):
        """The point of it: a partial collection must be distinguishable from
        a run that never started."""
        with tempfile.TemporaryDirectory() as td:
            attempt(td, Source({"Dairy": 1, "Produce": 0},
                               provenance={"products_served": 1,
                                           "populated_roots": ["Dairy"],
                                           "stopped_reason": "request ceiling reached"}))
            record = json.loads(failures(td)[0].read_text())
            self.assertEqual(record["provenance_report"]["populated_roots"], ["Dairy"])
            self.assertEqual(record["provenance_report"]["stopped_reason"],
                             "request ceiling reached")

    def test_a_source_that_reports_nothing_still_leaves_a_record(self):
        with tempfile.TemporaryDirectory() as td:
            attempt(td, Source({"Dairy": 1, "Produce": 0}))
            record = json.loads(failures(td)[0].read_text())
            self.assertNotIn("provenance_report", record)
            self.assertIn("refused_with", record)

    def test_a_source_whose_provenance_raises_does_not_lose_the_record(self):
        source = Source({"Dairy": 1, "Produce": 0})
        source.provenance_report = lambda: (_ for _ in ()).throw(RuntimeError("boom"))
        with tempfile.TemporaryDirectory() as td:
            attempt(td, source)
            record = json.loads(failures(td)[0].read_text())
            self.assertIn("RuntimeError", record["provenance_report_unavailable"])

    def test_each_refused_attempt_gets_its_own_artifact(self):
        with tempfile.TemporaryDirectory() as td:
            for _ in range(3):
                attempt(td, Source({"Dairy": 1, "Produce": 0}))
            self.assertEqual(len(failures(td)), 3)

    def test_a_store_refused_before_collection_is_recorded_too(self):
        with tempfile.TemporaryDirectory() as td:
            storage = LocalStorage(Path(td))
            blank = Store("53100502", "60061", "", "", "")
            with self.assertRaises(ValidationFailure):
                Collector(storage, Source(), CATS, min_products=1,
                          trial=True).run(blank)
            self.assertEqual(len(failures(td)), 1)
            self.assertIn("missing required columns",
                          json.loads(failures(td)[0].read_text())["refused_with"])


class ItNeitherPublishesNorSwallows(unittest.TestCase):
    def test_nothing_is_published_by_a_refused_run(self):
        with tempfile.TemporaryDirectory() as td:
            attempt(td, Source({"Dairy": 1, "Produce": 0}))
            self.assertEqual(list(Path(td).rglob("latest.json")), [])
            self.assertEqual(list(Path(td).rglob("runs/*/data.json")), [])

    def test_the_error_still_reaches_the_caller(self):
        with tempfile.TemporaryDirectory() as td:
            _, exc = attempt(td, Source({"Dairy": 1, "Produce": 0}))
            self.assertIsInstance(exc, ValidationFailure)

    def test_a_good_release_is_not_replaced_and_leaves_no_failure(self):
        with tempfile.TemporaryDirectory() as td:
            storage, exc = attempt(td, Source({"Dairy": 2, "Produce": 2}))
            self.assertIsNone(exc)
            self.assertEqual(failures(td), [])
            pointer = next(iter(Path(td).rglob("latest.json")))
            good = json.loads(pointer.read_text())["release"]

            attempt(td, Source({"Dairy": 1, "Produce": 0}))
            self.assertEqual(len(failures(td)), 1)
            record = json.loads(failures(td)[0].read_text())
            self.assertEqual(record["published_release_untouched"], good)
            self.assertEqual(json.loads(pointer.read_text())["release"], good)

    def test_a_failure_that_cannot_be_written_does_not_replace_the_error(self):
        class Unwritable(LocalStorage):
            def write(self, key, body):
                if "failures/" in key:
                    raise OSError("disk full")
                return super().write(key, body)

        with tempfile.TemporaryDirectory() as td:
            collector = Collector(Unwritable(Path(td)), Source({"Dairy": 1, "Produce": 0}),
                                  CATS, min_products=1, trial=True)
            with self.assertRaises(ValidationFailure) as caught:
                collector.run(STORE)
            self.assertIn("Zero eligible products", str(caught.exception))


class ARefusalBeforeTheRunnerIsRecordedToo(unittest.TestCase):
    """The hole the class above did not cover.

    `Collector.run` records its own refusals, but the CLI loads the retailer
    credentials twice before `run` is ever reached: once resolving the store
    from /locations, once building the source. So a missing or expired key
    produced an exception, a log line and no artefact at all - the precise
    unattended failure this record was built for, going unrecorded by the
    machinery built to record it. Reproduced by running the real CLI with the
    credentials removed from the environment.

    Credential expiry is the likeliest unattended failure a twice-weekly job
    has, because keys are rotated and nobody is watching when they are.
    """

    def argv(self, td, command="run", *extra):
        return [command, "--source", "sweep",
                "--store", "53100502", "--location-id", "53100502",
                "--resolve-store", "--expect-zipcode", "60061",
                "--expect-street", "1720 N Milwaukee Ave",
                "--output", str(td), "--sweep-work-dir", str(Path(td) / "work"),
                *extra]

    def without_credentials(self):
        kept = {k: v for k, v in os.environ.items()
                if k not in ("KROGER_CLIENT_ID", "KROGER_CLIENT_SECRET")}
        return mock.patch.dict(os.environ, kept, clear=True)

    def refused(self, td, command="run", *extra):
        with self.without_credentials():
            code = cli.main(self.argv(td, command, *extra))
        return code, failures(td)

    def test_a_credential_failure_now_leaves_a_record(self):
        with tempfile.TemporaryDirectory() as td:
            code, records = self.refused(td)
        self.assertEqual(code, 1)
        self.assertEqual(len(records), 1, "a refusal before the runner left nothing")

    def test_the_record_carries_the_reason_verbatim(self):
        with tempfile.TemporaryDirectory() as td:
            _, records = self.refused(td)
            body = json.loads(records[0].read_text())
        self.assertIn("KROGER_CLIENT_ID", body["refused_with"])
        self.assertEqual(body["stage"], "startup")

    def test_it_does_not_claim_a_store_it_never_resolved(self):
        """Store resolution is what failed, so the ids are arguments. This
        repository has already published one store's data under another
        store's name once; a failure record reading like a store observation
        is the same mistake somewhere quieter."""
        with tempfile.TemporaryDirectory() as td:
            _, records = self.refused(td)
            body = json.loads(records[0].read_text())
        self.assertFalse(body["store_resolved"])
        self.assertEqual(body["requested_location_id"], "53100502")
        self.assertNotIn("store_name", body)
        self.assertNotIn("store_location", body)
        self.assertIn("not an observation of any store", body["_store_not_resolved"])

    def test_the_record_is_outside_the_publishing_namespace(self):
        with tempfile.TemporaryDirectory() as td:
            _, records = self.refused(td)
            published = sorted(Path(td).glob("published/**/*.json"))
            everything = sorted(p for p in Path(td).rglob("*.json"))
        self.assertEqual(published, [])
        self.assertEqual(everything, records,
                         "a refused startup wrote something besides its own record")

    def test_the_declared_uncovered_roots_travel_into_it(self):
        with tempfile.TemporaryDirectory() as td:
            _, records = self.refused(
                td, "run", "--uncovered-roots", str(ROOT / "config/sweep_coverage.json"))
            body = json.loads(records[0].read_text())
        self.assertIn("Seafood", body["roots_not_covered_by_source"])
        self.assertNotIn("Seafood", body["roots_configured"])

    def test_status_is_not_a_run_and_leaves_no_record(self):
        """status and export must not litter the failure tree, and must not
        need credentials in the first place."""
        with tempfile.TemporaryDirectory() as td:
            code, records = self.refused(td, "status")
        self.assertEqual(code, 1)
        self.assertEqual(records, [])

    def test_one_failure_writes_one_record(self):
        """The startup guard stops before the Collector on purpose. Wrapping
        the Collector too would write a second record for one failure."""
        with tempfile.TemporaryDirectory() as td:
            code = cli.main(["run", "--source", "fixture",
                             "--store", "DEMO-WESTLOOP-60661",
                             "--location-id", "DEMO-WESTLOOP-60661",
                             "--output", str(td), "--minimum-products", "100000"])
            records = failures(td)
            bodies = [json.loads(r.read_text()) for r in records]
        self.assertEqual(code, 1)
        self.assertEqual(len(records), 1, f"expected one record, got {len(records)}")
        self.assertEqual(bodies[0].get("stage", "runner"), "runner",
                         "a runner refusal was recorded as a startup one")


if __name__ == "__main__":
    unittest.main()
