"""A term whose pages did not all complete is not marked done.

It used to be marked done unconditionally. So a term that failed on page 0
collected nothing, was checkpointed as finished, and was skipped by every
later resume for ever, while a fresh run would have collected it. The working
rules recorded that as a known-false resumability claim: "a resumed sweep
serves exactly what a fresh one served" was not true, and the test written for
it compared a run's output against itself over the same raw directory, so it
asserted nothing.

The loss was silent. The only trace was an entry in `page_failures` that
nothing compared against `done_terms`.

Retrying is bounded. A term that fails the same way on every attempt would
otherwise be retried for ever across resumes and no run would finish, so after
`MAX_TERM_ATTEMPTS` it is marked done and named in `terms_abandoned`. A term we
stopped trying to collect is a coverage fact, so it is reported rather than
left in the checkpoint.
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from marianos_collector import sweep_core  # noqa: E402
from marianos_collector.config import Store  # noqa: E402
from marianos_collector.kroger import KrogerError  # noqa: E402

STORE = Store("53100502", "60061", "Marianos - Marianos Vernon Hills",
              "1720 N Milwaukee Ave, Vernon Hills, IL 60061", "")
CMAP = {"Dairy": "Dairy"}


def product(upc):
    return {"productId": upc, "upc": upc, "description": f"Item {upc}",
            "brand": "Kroger", "productPageURI": f"/p/item/{upc}",
            "categories": ["Dairy"], "images": [],
            "items": [{"soldBy": "UNIT", "size": "18 ct",
                       "fulfillment": {"curbside": True},
                       "price": {"regular": 2.98},
                       "inventory": {"stockLevel": "HIGH"}}]}


class FailingClient:
    """Fails the first `fail_times` calls for `fail_term`, then succeeds."""

    def __init__(self, fail_term, fail_times=99, fail_at_start=0,
                 full_first_page=False):
        self.fail_term = fail_term
        self.fail_times = fail_times
        self.fail_at_start = fail_at_start
        self.full_first_page = full_first_page
        self.calls = []
        self.failures_served = 0

    def products(self, location_id, term, offset=0, limit=50):
        self.calls.append((term, offset))
        if term == self.fail_term and offset == self.fail_at_start:
            if self.failures_served < self.fail_times:
                self.failures_served += 1
                raise KrogerError("Kroger API HTTP 503")
        if offset > 0:
            return {"data": [], "meta": {}}
        if self.full_first_page:
            # A short page ends the term's page loop, so a mid-sequence failure
            # is only reachable when page 0 comes back full.
            return {"data": [product(f"{n:013d}") for n in range(1, 51)],
                    "meta": {}}
        return {"data": [product("0001111060933")], "meta": {}}


def sweep(client, state=None, terms=None, work=None):
    budget = sweep_core.Budget(200, 120)
    return sweep_core.sweep(
        client, STORE.store_id, STORE,
        terms or {"Dairy": ["milk", "eggs"]}, budget, 6,
        state=state, log=lambda *_: None, category_map=CMAP,
        raw_dir=(Path(work) / "raw") if work else None)


class AFailedTermIsNotMarkedDone(unittest.TestCase):

    def test_a_term_that_failed_on_page_zero_is_not_in_done_terms(self):
        state = sweep(FailingClient("milk"))
        self.assertNotIn("Dairy||milk", state["done_terms"])
        self.assertIn("Dairy||eggs", state["done_terms"])

    def test_the_term_that_succeeded_is_marked_done(self):
        state = sweep(FailingClient("milk"))
        self.assertEqual(state["done_terms"], ["Dairy||eggs"])

    def test_the_failure_is_still_recorded(self):
        state = sweep(FailingClient("milk"))
        self.assertEqual([f["term"] for f in state["page_failures"]],
                         ["Dairy||milk"])

    def test_a_resume_retries_the_failed_term(self):
        client = FailingClient("milk", fail_times=1)
        first = sweep(client)
        self.assertNotIn("Dairy||milk", first["done_terms"])

        second = sweep(client, state=first)
        self.assertIn("Dairy||milk", second["done_terms"])
        self.assertIn(("milk", 0), client.calls[len(client.calls) - 6:])

    def test_a_resume_does_not_retry_a_term_that_completed(self):
        client = FailingClient("milk", fail_times=1)
        first = sweep(client)
        before = [c for c in client.calls if c[0] == "eggs"]
        sweep(client, state=first)
        after = [c for c in client.calls if c[0] == "eggs"]
        self.assertEqual(before, after)

    def test_a_term_that_fails_mid_sequence_is_also_retried(self):
        """Pages 0 and 50 succeeded and page 100 failed, so the term is
        incomplete even though it collected something."""
        client = FailingClient("milk", fail_times=1, fail_at_start=50,
                                full_first_page=True)
        state = sweep(client)
        self.assertNotIn("Dairy||milk", state["done_terms"])
        self.assertEqual(state["term_attempts"]["Dairy||milk"], 1)


class RetryingIsBounded(unittest.TestCase):

    def test_after_the_cap_the_term_is_marked_done_and_named(self):
        client = FailingClient("milk")          # always fails
        state = None
        for _ in range(sweep_core.MAX_TERM_ATTEMPTS):
            state = sweep(client, state=state)
        self.assertIn("Dairy||milk", state["done_terms"])
        self.assertEqual(state["terms_abandoned"], ["Dairy||milk"])

    def test_it_is_not_abandoned_before_the_cap(self):
        client = FailingClient("milk")
        state = None
        for _ in range(sweep_core.MAX_TERM_ATTEMPTS - 1):
            state = sweep(client, state=state)
        self.assertEqual(state["terms_abandoned"], [])
        self.assertNotIn("Dairy||milk", state["done_terms"])

    def test_a_later_resume_does_not_retry_an_abandoned_term(self):
        client = FailingClient("milk")
        state = None
        for _ in range(sweep_core.MAX_TERM_ATTEMPTS):
            state = sweep(client, state=state)
        calls_before = len(client.calls)
        sweep(client, state=state)
        self.assertEqual(len(client.calls), calls_before)

    def test_abandoning_is_not_recorded_twice(self):
        client = FailingClient("milk")
        state = None
        for _ in range(sweep_core.MAX_TERM_ATTEMPTS + 2):
            state = sweep(client, state=state)
        self.assertEqual(state["terms_abandoned"].count("Dairy||milk"), 1)

    def test_a_term_that_eventually_succeeds_clears_its_attempt_count(self):
        client = FailingClient("milk", fail_times=1)
        state = sweep(client)
        self.assertIn("Dairy||milk", state["term_attempts"])
        state = sweep(client, state=state)
        self.assertNotIn("Dairy||milk", state["term_attempts"])
        self.assertEqual(state["terms_abandoned"], [])


class TheStateVersionGuardsTheNewShape(unittest.TestCase):

    def test_the_version_was_bumped_for_the_new_keys(self):
        self.assertGreaterEqual(sweep_core.STATE_VERSION, 6)

    def test_a_state_without_the_new_keys_does_not_raise(self):
        """A hand-assembled state, not a checkpoint; the version gate already
        refuses an older checkpoint."""
        bare = {"state_version": sweep_core.STATE_VERSION,
                "records": {}, "done_terms": [], "term_counts": {},
                "category_disagreements": [], "errors": [],
                "page_failures": [], "terms_hit_start_cap": [],
                "unmapped": {}, "discovery": {}, "quarantine": {},
                "contexts": {}, "observations": {}}
        state = sweep(FailingClient("milk"), state=bare)
        self.assertEqual(state["terms_abandoned"], [])


class TheReportSurfacesBoth(unittest.TestCase):

    def report_after(self, attempts):
        """Each attempt is a NEW source over the same work directory.

        `sweep_once` short-circuits on `self._index`, so calling it twice on
        one source does nothing: a resume is a fresh process reading the
        checkpoint, and the fixture has to model that or it tests nothing.
        """
        from marianos_collector.kroger_sweep_source import KrogerSweepSource
        with tempfile.TemporaryDirectory() as td:
            work = Path(td) / "w"
            client = FailingClient("milk")
            report = None
            for _ in range(attempts):
                source = KrogerSweepSource(client, "53100502", work,
                                           {"Dairy": ["milk", "eggs"]},
                                           category_map=CMAP, resume=True)
                source.sweep_once(STORE)
                report = source.provenance_report()
            return report

    def test_an_incomplete_term_is_reported_as_pending_retry(self):
        report = self.report_after(1)
        self.assertEqual(report["terms_incomplete_pending_retry"],
                         ["Dairy||milk"])
        self.assertEqual(report["terms_abandoned_count"], 0)

    def test_an_abandoned_term_is_reported_and_no_longer_pending(self):
        report = self.report_after(sweep_core.MAX_TERM_ATTEMPTS)
        self.assertEqual(report["terms_abandoned_after_retries"],
                         ["Dairy||milk"])
        self.assertEqual(report["terms_abandoned_count"], 1)
        self.assertEqual(report["terms_incomplete_pending_retry"], [])

    def test_a_clean_run_reports_neither(self):
        from marianos_collector.kroger_sweep_source import KrogerSweepSource
        with tempfile.TemporaryDirectory() as td:
            source = KrogerSweepSource(FailingClient("nothing-fails"),
                                       "53100502", Path(td) / "w",
                                       {"Dairy": ["milk"]}, category_map=CMAP,
                                       resume=True)
            source.sweep_once(STORE)
            report = source.provenance_report()
        self.assertEqual(report["terms_abandoned_after_retries"], [])
        self.assertEqual(report["terms_incomplete_pending_retry"], [])


if __name__ == "__main__":
    unittest.main()
