"""The schedule, as two claims that must not be allowed to carry each other.

"Twice-weekly Azure operation" is the weakest of the five evidence claims: a
deployment template plus a manually driven three-execution pilot, with the
schedule never observed running by itself. `tools/observe_schedule.py` closes
as much of that as can be closed away from the client's subscription, and the
only way it is worth anything is if the two claims stay separate.

**Claim A** is that the deployed expression fires on Mondays and Thursdays at
06:00 UTC. Computed, from the expression read out of the deployment script.

**Claim B** is that a scheduler left alone executes the job repeatedly.
Observed in real elapsed time, at a compressed cadence.

A compressed cadence cannot evidence the real times, and computing the real
times cannot evidence unattended repetition. The tests below are mostly about
keeping that line, and about the cron matcher being right, since every firing
time in claim A rests on it.
"""

import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import observe_schedule as obs  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
MARIANOS_SCRIPT = ROOT / "azure/deploy_jobs.sh"
WALMART_SCRIPT = ROOT.parent / "walmart/azure/deploy_jobs.sh"


def utc(*args):
    return datetime(*args, tzinfo=timezone.utc)


class TheCronMatcherIsRight(unittest.TestCase):
    """Every firing time claim A reports rests on this."""

    def test_the_deployed_expression_fires_monday_and_thursday_at_six(self):
        expression = "0 6 * * 1,4"
        self.assertTrue(obs.matches(expression, utc(2026, 11, 5, 6, 0)))   # Thursday
        self.assertTrue(obs.matches(expression, utc(2026, 11, 9, 6, 0)))   # Monday
        self.assertFalse(obs.matches(expression, utc(2026, 11, 6, 6, 0)))  # Friday
        self.assertFalse(obs.matches(expression, utc(2026, 11, 5, 7, 0)))  # wrong hour
        self.assertFalse(obs.matches(expression, utc(2026, 11, 5, 6, 1)))  # wrong minute

    def test_cron_day_of_week_is_not_pythons(self):
        """cron Monday is 1; Python's weekday() makes Monday 0. Getting this
        wrong shifts every reported firing by a day."""
        self.assertTrue(obs.matches("0 0 * * 1", utc(2026, 11, 9)))    # Monday
        self.assertFalse(obs.matches("0 0 * * 0", utc(2026, 11, 9)))
        self.assertTrue(obs.matches("0 0 * * 0", utc(2026, 11, 8)))    # Sunday

    def test_seven_and_zero_both_mean_sunday(self):
        for spec in ("0", "7"):
            with self.subTest(dow=spec):
                self.assertTrue(obs.matches(f"0 0 * * {spec}", utc(2026, 11, 8)))

    def test_ranges_and_steps(self):
        self.assertTrue(obs.matches("0 0 * * 1-5", utc(2026, 11, 11)))   # Wednesday
        self.assertFalse(obs.matches("0 0 * * 1-5", utc(2026, 11, 8)))   # Sunday
        self.assertTrue(obs.matches("*/15 * * * *", utc(2026, 11, 3, 4, 30)))
        self.assertFalse(obs.matches("*/15 * * * *", utc(2026, 11, 3, 4, 31)))

    def test_next_firings_are_ordered_and_distinct(self):
        firings = obs.next_firings("0 6 * * 1,4", utc(2026, 11, 3), 6)
        self.assertEqual(len(firings), 6)
        self.assertEqual(firings, sorted(firings))
        self.assertEqual(len(set(firings)), 6)

    def test_the_gaps_are_seventy_two_and_ninety_six_hours(self):
        """Which is what twice weekly on those two days actually looks like."""
        firings = obs.next_firings("0 6 * * 1,4", utc(2026, 11, 3), 5)
        gaps = {int((b - a).total_seconds() // 3600)
                for a, b in zip(firings, firings[1:])}
        self.assertEqual(gaps, {72, 96})


class TheExpressionIsReadNotRetyped(unittest.TestCase):
    def test_it_reads_the_marianos_deployment_default(self):
        self.assertEqual(obs.deployed_cron(MARIANOS_SCRIPT), "0 6 * * 1,4")

    def test_it_reads_the_walmart_deployment_default_too(self):
        """The two scripts spell it differently; both are read."""
        self.assertEqual(obs.deployed_cron(WALMART_SCRIPT), "0 6 * * 1,4")

    def test_a_script_with_no_default_is_refused(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "deploy.sh"
            path.write_text("#!/bin/bash\necho nothing here\n")
            with self.assertRaises(SystemExit):
                obs.deployed_cron(path)

    def test_disagreeing_defaults_in_one_script_are_refused(self):
        """A script edited in one of its two places must not let this attest
        whichever default it happened to find first."""
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "deploy.sh"
            path.write_text('CRON="${CRON_EXPRESSION:-0 6 * * 1,4}"\n'
                            'echo "${CRON_EXPRESSION:-0 7 * * 2}"\n')
            with self.assertRaises(SystemExit) as caught:
                obs.deployed_cron(path)
            self.assertIn("disagreeing", str(caught.exception))


class ClaimAFailsIfTheScheduleIsNotTwiceWeekly(unittest.TestCase):
    def test_the_deployed_expression_passes(self):
        self.assertEqual(obs.check_deployed_times("0 6 * * 1,4")["verdict"], "PASS")

    def test_a_daily_schedule_fails(self):
        result = obs.check_deployed_times("0 6 * * *")
        self.assertEqual(result["verdict"], "FAIL")
        self.assertFalse(result["fires_twice_a_week"])

    def test_the_right_days_at_the_wrong_hour_fails(self):
        self.assertEqual(obs.check_deployed_times("0 7 * * 1,4")["verdict"], "FAIL")

    def test_the_right_hour_on_the_wrong_days_fails(self):
        self.assertEqual(obs.check_deployed_times("0 6 * * 2,5")["verdict"], "FAIL")

    def test_it_reports_the_days_and_times_it_found(self):
        result = obs.check_deployed_times("0 6 * * 1,4")
        self.assertEqual(result["days_it_fires"], ["Monday", "Thursday"])
        self.assertEqual(result["times_it_fires_utc"], ["06:00"])


class ClaimBObservesRealUnattendedExecutions(unittest.TestCase):
    def test_two_firings_produce_two_distinct_releases(self):
        result = obs.observe_unattended(executions=2, interval=1)
        self.assertEqual(result["verdict"], "PASS")
        self.assertEqual(result["executions_observed"], 2)
        self.assertEqual(result["executions_published"], 2)
        self.assertEqual(result["distinct_releases"], 2)
        self.assertEqual(result["operator_interventions"], 0)

    def test_each_firing_has_its_own_wall_clock_time(self):
        result = obs.observe_unattended(executions=2, interval=1)
        fired = [e["fired_at_utc"] for e in result["executions"]]
        self.assertEqual(len(set(fired)), 2)
        self.assertEqual(fired, sorted(fired))

    def test_it_says_the_cadence_is_compressed(self):
        """Without this the reader could take it for the deployed cadence."""
        result = obs.observe_unattended(executions=1, interval=1)
        self.assertIn("compressed", result["_cadence_is_compressed"])
        self.assertIn("twice weekly", result["_cadence_is_compressed"])

    def test_a_firing_that_refuses_is_not_counted_as_published(self):
        """The verdict must not pass on executions that failed."""
        original = obs.one_execution
        obs.one_execution = lambda store, work, n: {
            "execution": n, "fired_at_utc": "2026-11-03T00:00:00+00:00",
            "outcome": "refused", "refused_with": "ValidationFailure: injected",
            "finished_at_utc": "2026-11-03T00:00:01+00:00"}
        try:
            result = obs.observe_unattended(executions=2, interval=1)
        finally:
            obs.one_execution = original
        self.assertEqual(result["verdict"], "FAIL")
        self.assertEqual(result["executions_published"], 0)
        self.assertEqual(len(result["refused_executions"]), 2)


class TheTranscriptRefusesTheAzureReading(unittest.TestCase):
    def test_it_states_that_nothing_ran_on_azure(self):
        for required in ("did not run on Azure", "cadence observed is not the deployed",
                        "data is replayed", "client's environment",
                        "One week of real operation is still unobserved"):
            with self.subTest(required=required):
                self.assertIn(required, obs.DOES_NOT_ESTABLISH)

    def test_the_written_report_keeps_the_two_claims_apart(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "out"
            obs.main(["--out", str(out), "--executions", "1", "--interval", "1"])
            report = json.loads((out / "SCHEDULE.json").read_text())
        self.assertEqual(len(report["claims"]), 2)
        self.assertEqual(report["deployed_expression"], "0 6 * * 1,4")
        methods = [c["method"] for c in report["claims"]]
        self.assertIn("Computed, not simulated", methods[0])
        self.assertIn("Real elapsed time", methods[1])

    def test_the_report_names_the_script_it_read(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "out"
            obs.main(["--out", str(out), "--executions", "1", "--interval", "1"])
            report = json.loads((out / "SCHEDULE.json").read_text())
        self.assertTrue(report["deployed_expression_read_from"].endswith("deploy_jobs.sh"))


if __name__ == "__main__":
    unittest.main()
