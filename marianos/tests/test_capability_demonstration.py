"""The capability demonstration must not be able to pass vacuously.

The client asked for evidence that the sweep-through-collector path exercises
retention, resume, trial separation and failed-run publication protection.
`tools/capability_demonstration.py` runs those four scenarios and writes a
transcript. A transcript is worth nothing if a scenario can report PASS
without the behaviour happening, and the first version of the fourth scenario
did exactly that: a failed run left a resumable checkpoint, the next bad run
inherited its staged pages, and it was refused by the yield gate rather than
the gate it was meant to exercise. The refusal looked correct and evidenced
nothing.

So these tests check the scenarios discriminate: each one must fail when the
protection it names is removed.
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import capability_demonstration as demo  # noqa: E402


def run_all():
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "out"
        demo.main(["--out", str(out)])
        return json.loads((out / "CAPABILITIES.json").read_text())


class AllFourScenariosPass(unittest.TestCase):
    def setUp(self):
        self.report = run_all()
        self.by_name = {c["capability"]: c for c in self.report["capabilities"]}

    def test_all_four_are_reported(self):
        self.assertEqual(len(self.report["capabilities"]), 4)
        self.assertTrue(self.report["all_pass"])

    def test_retention_keeps_a_product_the_api_stopped_returning(self):
        c = next(v for k, v in self.by_name.items() if "retention" in k.lower())
        self.assertTrue(c["it_is_still_in_the_second_release"])
        self.assertTrue(c["its_crawl_date_is_unchanged"])
        self.assertEqual(c["carried_forward_count"], 1)

    def test_retention_keeps_an_unpriced_product_with_a_blank_price(self):
        c = next(v for k, v in self.by_name.items() if "retention" in k.lower())
        self.assertTrue(c["unpriced_out_of_stock_product_retained"])
        self.assertTrue(c["its_regular_price_is_blank_not_invented"])

    def test_resume_refetches_nothing(self):
        c = next(v for k, v in self.by_name.items() if "Resume" in k)
        self.assertTrue(c["checkpoint_survived"])
        self.assertEqual(c["api_calls_made_by_the_resumed_sweep"], 0)
        self.assertTrue(c["resumed_run_published"])

    def test_the_sweep_cannot_publish_a_full_release(self):
        c = next(v for k, v in self.by_name.items() if "namespace" in k)
        self.assertIn("does not attest complete coverage", c["full_release_refused_with"])
        self.assertTrue(c["wrote_under_trials"])
        self.assertEqual(c["published_namespace_contents"], [])
        self.assertFalse(c["report_declares_coverage_attested"])

    def test_each_failure_gate_refuses_for_its_own_reason(self):
        """The defect that made the first version worthless."""
        c = next(v for k, v in self.by_name.items() if "Failed-run" in k)
        gates = c["gates_that_refused"]
        self.assertEqual(len(gates), 3)
        self.assertTrue(all(gates.values()), gates)
        self.assertEqual(len(set(gates.values())), 3, gates)
        self.assertIn("yield collapse", gates["yield_collapse"])
        self.assertIn("minimum", gates["minimum_product_floor"])
        self.assertIn("STORE_CONTEXT", gates["wrong_store_context"])

    def test_a_failed_run_never_moves_the_latest_pointer(self):
        c = next(v for k, v in self.by_name.items() if "Failed-run" in k)
        self.assertTrue(c["latest_pointer_unchanged"])
        self.assertEqual(c["latest_pointer_still_names"], c["good_release"])


class TheTranscriptSaysWhatItIsNot(unittest.TestCase):
    def test_the_gaps_are_stated_rather_than_left_to_inference(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "out"
            demo.main(["--out", str(out)])
            gaps = (out / "GAPS.md").read_text()
        for required in ("Category coverage is not established",
                        "not unattended", "Nothing here ran on Azure",
                        "data above is invented"):
            with self.subTest(required=required):
                self.assertIn(required, gaps)

    def test_the_module_docstring_refuses_the_live_data_reading(self):
        self.assertIn("not** evidence about live data", demo.__doc__)

    def test_the_report_names_the_commit_and_whether_the_tree_was_clean(self):
        report = run_all()
        self.assertEqual(len(report["commit"]), 40)
        self.assertIn("working_tree_clean", report)

    def test_the_replay_client_makes_no_request(self):
        """It stands in for KrogerClient; anything else would be a live call."""
        client = demo.ReplayClient({})
        with self.assertRaises(RuntimeError):
            client.get("/locations/53100502")


class TheScenariosDiscriminate(unittest.TestCase):
    """Each scenario must stop reporting PASS when its protection is removed.

    "Does not report PASS" rather than "reports FAIL" on purpose: with a
    protection removed, the run usually raises instead, and a raise is the
    collector refusing. Either outcome discriminates; a clean PASS would not.
    """

    def assert_does_not_pass(self, scenario):
        with tempfile.TemporaryDirectory() as td:
            try:
                result = scenario(Path(td) / "w", Path(td) / "s")
            except Exception:
                return  # refused outright, which is discrimination enough
        self.assertNotEqual(result["verdict"], "PASS", result)

    def test_retention_does_not_pass_without_carry_forward(self):
        import marianos_collector.runner as runner
        original = runner.reconcile

        def no_carry(rows, observations, store_id, collection_at,
                     previous_rows=None, previous_retention=None, **kw):
            return original(rows, observations, store_id, collection_at,
                            previous_rows=[], previous_retention={}, **kw)

        runner.reconcile = no_carry
        try:
            self.assert_does_not_pass(demo.retention)
        finally:
            runner.reconcile = original

    def test_trial_separation_does_not_pass_if_the_source_claims_coverage(self):
        original = demo.KrogerSweepSource.coverage_attested
        demo.KrogerSweepSource.coverage_attested = True
        try:
            self.assert_does_not_pass(demo.trial_separation)
        finally:
            demo.KrogerSweepSource.coverage_attested = original

    def test_failed_run_protection_does_not_pass_without_the_yield_check(self):
        import marianos_collector.runner as runner
        original = runner.Collector.__init__

        def lenient(self, *a, **kw):
            original(self, *a, **kw)
            self.previous_ratio = 0.0          # accept any collapse
            self.min_products = 1              # and any volume

        runner.Collector.__init__ = lenient
        try:
            self.assert_does_not_pass(demo.failed_run_protection)
        finally:
            runner.Collector.__init__ = original

    def test_resume_does_not_pass_if_the_sweep_refetches_everything(self):
        original = demo.KrogerSweepSource._resume_state
        demo.KrogerSweepSource._resume_state = lambda self: None
        try:
            self.assert_does_not_pass(demo.resume)
        finally:
            demo.KrogerSweepSource._resume_state = original


if __name__ == "__main__":
    unittest.main()
