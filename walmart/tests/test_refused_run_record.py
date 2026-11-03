"""A refused Walmart run must leave something to read.

This file exists because it did not. `CLAUDE.md` said the refused-run record
was in "both runners" and that three of its properties were "deliberate and
tested". The record was in both; the tests were only in the marianos suite, so
on this side the claim rested on nothing a command could check. Searching the
whole walmart suite for the failures tree returned no match at all.

Two separate things are covered here, and the second was a real gap rather
than only a missing test:

- `Collector.run` records its own refusals. Now asserted on this side too.
- A run can be refused **before** a Collector exists. The CLI builds the
  source, reads the OPD mapping and reads the canaries first, so a missing
  mapping, a malformed one or absent OPD credentials produced an exception, a
  log line and no artefact at all. That is the ordinary misconfigured job,
  which is the failure most likely to recur unattended, going unrecorded by
  the machinery built for exactly it.

Both must hold the two properties that make the record safe: it must not
publish, and it must not swallow or replace the error.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from walmart_collector import cli  # noqa: E402
from walmart_collector.config import categories_from_csv, stores_from_json  # noqa: E402
from walmart_collector.runner import Collector, ValidationFailure  # noqa: E402
from walmart_collector.sources import FixtureSource  # noqa: E402
from walmart_collector import runner as runner_module  # noqa: E402
from walmart_collector.storage import LocalStorage  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CATEGORIES = categories_from_csv(ROOT / "config/categories.csv")
STORE = stores_from_json(ROOT / "config/stores.json")[0]


def published_tree(root):
    """Every file written into a publishing root, which must be empty after a
    refusal. Checkpoints are NOT in here: a refused run is allowed to leave
    them, that is what makes it resumable. The property is that the publishing
    tree is untouched, not that nothing at all was written."""
    root = Path(root)
    return sorted(p for p in root.rglob("*.json")
                  if not p.relative_to(root).as_posix().startswith(
                      ("failures/", "checkpoints/"))
                  and p.relative_to(root).as_posix().startswith(
                      ("published/", "trials/")))


def failures(root):
    """Failure records live outside the publishing tree, under failures/, so
    the assertion that nothing may be written to the publishing tree stays
    strong. A record found anywhere else is the defect, not the evidence."""
    tree = Path(root) / "failures"
    return sorted(tree.rglob("*.json")) if tree.is_dir() else []


class TheRunnerRecordsItsOwnRefusals(unittest.TestCase):
    def refused(self, td):
        storage = LocalStorage(Path(td))
        # The real fixture source with an unreachable product floor, so the
        # refusal is the runner's own yield gate rather than a stub's.
        collector = Collector(storage, FixtureSource(ROOT / "fixtures"),
                              CATEGORIES[:1], min_products=100000,
                              canaries={}, trial=True)
        with self.assertRaises((ValidationFailure, ValueError)) as caught:
            collector.run(STORE)
        return caught.exception, failures(td)

    def test_a_refused_run_leaves_an_artifact(self):
        with tempfile.TemporaryDirectory() as td:
            _, records = self.refused(td)
            self.assertEqual(len(records), 1)

    def test_the_artifact_carries_the_reason_verbatim(self):
        with tempfile.TemporaryDirectory() as td:
            exc, records = self.refused(td)
            body = json.loads(records[0].read_text())
        self.assertIn(str(exc), body["refused_with"])
        self.assertEqual(body["store_id"], STORE.store_id)

    def test_the_error_still_reaches_the_caller(self):
        """Recording a failure must never replace the failure."""
        with tempfile.TemporaryDirectory() as td:
            exc, _ = self.refused(td)
        self.assertTrue(str(exc))

    def test_nothing_is_published_by_a_refused_run(self):
        with tempfile.TemporaryDirectory() as td:
            _, records = self.refused(td)
            leaked = published_tree(td)
        self.assertEqual(len(records), 1)
        self.assertEqual(leaked, [],
                         "a refused run wrote into the publishing tree")

    def test_a_failure_that_cannot_be_written_does_not_replace_the_error(self):
        with tempfile.TemporaryDirectory() as td:
            storage = LocalStorage(Path(td))
            collector = Collector(storage, FixtureSource(ROOT / "fixtures"),
                                  CATEGORIES[:1], min_products=100000,
                                  canaries={}, trial=True)
            # Only the record write fails. Patching write_json wholesale
            # breaks the checkpoint write first and the run never reaches a
            # refusal, so the test would pass without testing anything.
            real = runner_module.write_json

            def only_the_record(storage, key, payload):
                if str(key).startswith("failures/"):
                    raise OSError("disk full")
                return real(storage, key, payload)

            with mock.patch("walmart_collector.runner.write_json",
                            side_effect=only_the_record):
                with self.assertRaises((ValidationFailure, ValueError)) as caught:
                    collector.run(STORE)
        self.assertNotIn("disk full", str(caught.exception),
                         "the recorder's own failure replaced the one it was recording")


class ARefusalBeforeTheRunnerIsRecordedToo(unittest.TestCase):
    """The gap. Ported from the marianos module, which was fixed first."""

    def argv(self, td, command="run", *extra):
        return [command, "--source", "opd", "--authorized-source",
                "--store", STORE.store_id, "--output", str(td), *extra]

    def run_cli(self, td, command="run", *extra):
        env = {k: v for k, v in os.environ.items()
               if k not in ("WALMART_OPD_CLIENT_ID", "WALMART_OPD_CLIENT_SECRET")}
        env["WALMART_DATA_AUTHORIZED"] = "yes"
        with mock.patch.dict(os.environ, env, clear=True):
            return cli.main(self.argv(td, command, *extra))

    def test_a_startup_failure_now_leaves_a_record(self):
        with tempfile.TemporaryDirectory() as td:
            code = self.run_cli(td)
            records = failures(td)
            bodies = [json.loads(r.read_text()) for r in records]
        self.assertEqual(code, 1)
        self.assertEqual(len(records), 1,
                         "a refusal before the runner left nothing to read")
        self.assertEqual(bodies[0]["stage"], "startup")

    def test_it_records_the_store_the_scope_and_the_roots(self):
        with tempfile.TemporaryDirectory() as td:
            self.run_cli(td)
            body = json.loads(failures(td)[0].read_text())
        self.assertEqual(body["store_id"], STORE.store_id)
        self.assertEqual(body["zipcode"], STORE.zipcode)
        self.assertEqual(body["source_requested"], "opd")
        self.assertIn(body["scope"], ("trial", "full"))
        self.assertEqual(body["roots_configured"], [c.name for c in CATEGORIES])

    def test_a_missing_opd_mapping_is_recorded(self):
        """The mapping is read before the runner, so a missing file was one of
        the failures that left nothing at all."""
        env = dict(os.environ, WALMART_DATA_AUTHORIZED="yes",
                   WALMART_OPD_CLIENT_ID="test-id",
                   WALMART_OPD_CLIENT_SECRET="test-secret")
        with tempfile.TemporaryDirectory() as td:
            with mock.patch.dict(os.environ, env, clear=True):
                code = cli.main(self.argv(td, "run", "--opd-mapping",
                                          str(Path(td) / "absent.json")))
            records = failures(td)
            bodies = [json.loads(r.read_text()) for r in records]
        self.assertEqual(code, 1)
        self.assertEqual(len(records), 1)
        self.assertEqual(bodies[0]["stage"], "startup")

    def test_the_record_is_outside_the_publishing_tree(self):
        with tempfile.TemporaryDirectory() as td:
            self.run_cli(td)
            records = failures(td)
            leaked = published_tree(td)
            # A startup refusal collects nothing, so its record really is the
            # only file the run has any business writing.
            everything = sorted(Path(td).rglob("*.json"))
        self.assertEqual(leaked, [])
        self.assertEqual(everything, records)

    def test_status_is_not_a_run_and_leaves_no_record(self):
        with tempfile.TemporaryDirectory() as td:
            self.run_cli(td, "status")
            self.assertEqual(failures(td), [])

    def test_one_failure_writes_one_record(self):
        """The guard stops before the Collector on purpose. Wrapping the
        Collector too would write a second record for one failure."""
        with tempfile.TemporaryDirectory() as td:
            code = cli.main(["run", "--source", "fixture", "--store", STORE.store_id,
                             "--output", str(td), "--minimum-products", "100000"])
            records = failures(td)
        self.assertEqual(code, 1)
        self.assertEqual(len(records), 1, f"expected one record, got {len(records)}")


if __name__ == "__main__":
    unittest.main()
