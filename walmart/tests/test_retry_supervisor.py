"""The retry supervisor: eight retries, then an email, next run unaffected.

Every test here drives the real supervisor with the clock, the sleep and the
subprocess injected, so nine attempts and two hours of waiting are exercised in
milliseconds and nothing is skipped for being slow. The deployment tests run
the real shell script.

Each assertion is on something that changes when the behaviour is reverted. The
trap this repository has fallen into twice is a test that asserts an
identity-keyed value and passes either way, so the counts, the budgets and the
refusal reasons are all compared against figures derived independently of the
code under test.
"""

import json
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPO = ROOT.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "azure"))

import retry_supervisor as rs                                    # noqa: E402
import container_entrypoint as entry                              # noqa: E402
from walmart_collector.cron import (                             # noqa: E402
    matches, next_firings, shortest_gap_seconds)

DEPLOY = ROOT / "azure" / "deploy_jobs.sh"
ENTRYPOINT = ROOT / "azure" / "container_entrypoint.py"
DOCKERFILE = ROOT / "Dockerfile"


class Clock:
    """A monotonic clock the test advances by hand."""

    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


class Harness:
    """Drives `supervise` with nothing real but the supervisor."""

    def __init__(self, exits, window=259000, attempts=8, interval=900,
                 run_cost=5.0, captured=""):
        self.exits = list(exits)
        self.window = window
        self.run_cost = run_cost
        self.captured = captured
        self.clock = Clock()
        self.waits = []
        self.budgets = []
        self.notified = 0
        self.plan = rs.RetryPlan(attempts=attempts, interval_seconds=interval)

    def _run(self, argv):
        self.clock.t += self.run_cost
        code = self.exits.pop(0) if self.exits else 1
        return code, self.captured

    def _sleep(self, seconds):
        self.waits.append(seconds)
        self.clock.t += seconds

    def _build(self, budget):
        self.budgets.append(budget)
        return [sys.executable, "-c", "pass", "run"]

    def _notify(self, outcome, log=None):
        self.notified += 1
        return "test-notice"

    def go(self):
        return rs.supervise(self._build, self.plan, self.window,
                            run=self._run, sleep=self._sleep,
                            clock=self.clock, notify=self._notify,
                            log=lambda *a, **k: None)


class RetryCadence(unittest.TestCase):

    def test_a_run_that_keeps_failing_is_tried_nine_times_and_waits_eight(self):
        """Eight retries after the first run. One plus eight is nine."""
        h = Harness(exits=[1] * 20)
        out = h.go()
        self.assertFalse(out.succeeded)
        self.assertEqual(len(out.attempts), 9)
        self.assertEqual(len(h.waits), 8)
        self.assertEqual(out.stopped_early, "")

    def test_each_wait_is_the_configured_interval(self):
        h = Harness(exits=[1] * 20, interval=900)
        h.go()
        self.assertEqual(h.waits, [900] * 8)
        self.assertEqual(sum(h.waits), 7200, "eight retries is two hours of waiting")

    def test_a_different_interval_is_honoured(self):
        """Asserts the interval is read from the plan, not hard-coded."""
        h = Harness(exits=[1] * 20, attempts=3, interval=600)
        h.go()
        self.assertEqual(h.waits, [600, 600, 600])

    def test_it_stops_the_moment_a_run_succeeds(self):
        h = Harness(exits=[1, 1, 0])
        out = h.go()
        self.assertTrue(out.succeeded)
        self.assertEqual(len(out.attempts), 3)
        self.assertEqual(len(h.waits), 2, "no wait after the run that worked")

    def test_a_run_that_recovers_sends_no_failure_notice(self):
        """Found by mutation testing: returning early on success and merely
        breaking out of the loop give identical attempt counts, and the test
        above passes either way. Only this asserts the difference, which is
        whether the operator is emailed about a run that worked."""
        h = Harness(exits=[1, 1, 0])
        out = h.go()
        self.assertEqual(h.notified, 0)
        self.assertEqual(out.notified, "")

    def test_a_run_that_never_recovers_sends_exactly_one_notice(self):
        h = Harness(exits=[1] * 20)
        h.go()
        self.assertEqual(h.notified, 1, "one failure, one email")

    def test_exit_code_follows_the_outcome(self):
        self.assertEqual(Harness(exits=[0]).go().exit_code, 0)
        self.assertEqual(Harness(exits=[1] * 20).go().exit_code, 1)


class WindowArithmetic(unittest.TestCase):
    """The plan lives inside one replica timeout, which is a SIGKILL."""

    def test_each_attempt_is_given_the_time_actually_left(self):
        """Budgets must shrink. A fixed budget would hand attempt nine the
        same figure as attempt one and overrun the replica."""
        h = Harness(exits=[1] * 20, run_cost=100.0)
        h.go()
        self.assertEqual(len(h.budgets), 9)
        for earlier, later in zip(h.budgets, h.budgets[1:]):
            self.assertLess(later, earlier)
        # Attempt one gets the whole window less the collector's publish
        # headroom, computed here rather than read from the code.
        # This collector's publish headroom is 1200s, not the Mariano's 900.
        self.assertEqual(h.budgets[0], 259000 - 1200)

    def test_a_first_attempt_that_exhausts_the_window_is_not_retried(self):
        """The one failure where retrying is pure waste.

        A run stopped by its own budget would be given *less* time next
        attempt, not more. No classification is needed: there is nothing left
        to retry it with, and the supervisor owns the clock.
        """
        window = 14400 - rs.SUPERVISOR_EXIT_HEADROOM_SECONDS
        h = Harness(exits=[1] * 20, window=window, run_cost=window - 900)
        out = h.go()
        self.assertEqual(len(out.attempts), 1)
        self.assertEqual(h.waits, [], "no fifteen-minute wait for a retry that cannot run")
        self.assertIn("no room for another attempt", out.stopped_early)

    def test_it_stops_early_rather_than_starting_an_attempt_too_short_to_work(self):
        """An attempt below the floor could not reach the retailer at all."""
        window = 900 + rs.MIN_ATTEMPT_SECONDS + 10
        h = Harness(exits=[1] * 20, window=window, run_cost=20.0)
        out = h.go()
        self.assertLess(len(out.attempts), 9)
        self.assertTrue(out.stopped_early)

    def test_the_very_first_attempt_is_checked_against_the_floor_too(self):
        """Found by mutation testing: removing the pre-attempt window check
        left every other test green, because the post-wait check catches the
        same cases *after* a failure. Nothing covered the first attempt, which
        has no wait before it. A window this small must start no attempt at
        all rather than one too short to reach the retailer and publish."""
        window = 900 + rs.MIN_ATTEMPT_SECONDS - 100
        h = Harness(exits=[1] * 20, window=window, run_cost=1.0)
        out = h.go()
        self.assertEqual(len(out.attempts), 0, "no attempt should have started")
        self.assertEqual(h.budgets, [], "and none should have been costed")
        self.assertIn("window exhausted", out.stopped_early)
        self.assertEqual(h.notified, 1, "a run that never started is still a failure")

    def test_stopping_early_still_notifies(self):
        window = 14400 - rs.SUPERVISOR_EXIT_HEADROOM_SECONDS
        h = Harness(exits=[1] * 20, window=window, run_cost=window - 900)
        out = h.go()
        self.assertEqual(h.notified, 1)
        self.assertEqual(out.notified, "test-notice")

    def test_main_refuses_a_timeout_with_no_room_for_one_attempt(self):
        with self.assertRaises(ValueError) as caught:
            rs.main(build_argv=lambda b: ["x"], replica_timeout=1000,
                    collector_headroom_seconds=900)
        self.assertIn("no room for a single attempt", str(caught.exception))


class NotRetried(unittest.TestCase):

    def test_a_usage_error_is_not_retried(self):
        """argparse exits 2 and will be wrong the same way eight more times."""
        h = Harness(exits=[rs.USAGE_EXIT_CODE])
        out = h.go()
        self.assertEqual(len(out.attempts), 1)
        self.assertEqual(h.waits, [])
        self.assertIn("usage error", out.stopped_early)

    def test_a_bot_challenge_is_not_retried(self):
        """The retailer said no. The standing position is that the route is
        unavailable and that is reported, not worked around, and retrying a
        refusal on a schedule is working around it."""
        h = Harness(exits=[1] * 20,
                    captured="ERROR: AccessChallenge: press and hold")
        out = h.go()
        self.assertEqual(len(out.attempts), 1)
        self.assertEqual(h.waits, [])
        self.assertIn("bot challenge", out.stopped_early)
        self.assertIn("worked around", out.stopped_early)

    def test_an_ordinary_failure_is_still_retried(self):
        """Guards the test above from passing by refusing everything.

        Credential expiry is the likeliest unattended failure and it IS
        retried: a classifier cannot tell an expired key from a token blip, and
        retrying one costs no retailer requests at all.
        """
        h = Harness(exits=[1] * 20,
                    captured="ERROR: KrogerError: 401 from the token endpoint")
        out = h.go()
        self.assertEqual(len(out.attempts), 9)
        self.assertEqual(len(h.waits), 8)

    def test_the_challenge_marker_is_not_matched_in_passing_prose(self):
        """A marker loose enough to match ordinary log text would close the
        retry path on a false positive, which is the failure CLAUDE.md records
        twice: a route declared closed on an unchecked match."""
        h = Harness(exits=[1] * 20,
                    captured="collected 12 products from the access aisle")
        self.assertEqual(len(h.go().attempts), 9)


class NotARun(unittest.TestCase):

    def test_list_runs_once_with_no_retries_and_no_notice(self):
        """`list` is not a run. cli.py already makes that separation for
        refusal records; a failure notice must follow it too."""
        calls = []
        original = rs._run_subprocess
        rs._run_subprocess = lambda argv: (calls.append(argv) or (1, ""))
        try:
            code = rs.main(build_argv=lambda b: ["never"], replica_timeout=14400,
                           collector_headroom_seconds=900,
                           argv_for_non_run=["python", "-m", "x", "list"])
        finally:
            rs._run_subprocess = original
        self.assertEqual(code, 1)
        self.assertEqual(len(calls), 1, "a non-run must not be retried")

    def test_the_entrypoint_treats_list_as_a_non_run(self):
        env = {k: v for k, v in os.environ.items() if not k.startswith("MARIANOS_")}
        with _environment(env, clear=("WALMART_STORE_ID",)):
            argv = entry.command()
        self.assertIn("list", argv)
        self.assertNotIn("run", argv)


class Notification(unittest.TestCase):

    def _failed_outcome(self):
        out = rs.Outcome(succeeded=False)
        out.attempts.append(rs.Attempt(number=1, budget_seconds=6300,
                                       exit_code=1, elapsed_seconds=12.0,
                                       note="failed with exit 1"))
        return out

    def test_without_smtp_it_prints_the_marker_and_says_so(self):
        lines = []
        with _environment({"WALMART_STORE_ID": "100"},
                          clear=("SMTP_HOST", "ALERT_EMAIL_TO")):
            result = rs.send_failure_notice(self._failed_outcome(), log=lines.append)
        self.assertTrue(any(rs.ALERT_MARKER in line for line in lines),
                        "an Azure Monitor log alert has nothing to match without it")
        self.assertIn("log_marker_only", result)

    def test_with_smtp_it_sends_and_the_message_carries_the_facts(self):
        sent = {}

        def transport(message, host, port, user, password):
            sent.update(message=message, host=host, port=port)

        with _environment({"SMTP_HOST": "smtp.example.com",
                           "ALERT_EMAIL_TO": "ops@example.com",
                           "SMTP_PORT": "2525",
                           "WALMART_STORE_ID": "100",
                           "WALMART_SOURCE": "opd"}):
            result = rs.send_failure_notice(self._failed_outcome(), log=lambda *a: None,
                                            smtp=transport)
        self.assertIn("email_sent", result)
        self.assertEqual(sent["host"], "smtp.example.com")
        self.assertEqual(sent["port"], 2525)
        body = sent["message"].get_content()
        self.assertIn("100", body)
        self.assertIn("opd", body)
        self.assertIn("exit 1", body)
        self.assertIn("100", sent["message"]["Subject"])

    def test_the_notice_says_the_next_run_is_unaffected(self):
        """The instruction was explicit that the next run stays on time, so the
        failure report has to answer the question it will raise."""
        with _environment({"WALMART_STORE_ID": "100"}):
            body = rs._notice_body(self._failed_outcome())
        self.assertIn("next scheduled run is unaffected", body)

    def test_the_notice_points_at_the_refusal_record_rather_than_replacing_it(self):
        body = rs._notice_body(self._failed_outcome())
        self.assertIn("failures/", body)

    def test_no_smtp_password_reaches_the_body_or_the_marker_line(self):
        """Credentials stay with their owner, including in what we emit."""
        lines = []
        with _environment({"WALMART_STORE_ID": "100",
                           "SMTP_PASSWORD": "s3cr3t-do-not-log",
                           "SMTP_USERNAME": "ops"},
                          clear=("SMTP_HOST", "ALERT_EMAIL_TO")):
            rs.send_failure_notice(self._failed_outcome(), log=lines.append)
            body = rs._notice_body(self._failed_outcome())
        for text in lines + [body]:
            self.assertNotIn("s3cr3t-do-not-log", text)

    def test_a_failed_email_never_replaces_the_failure_it_reports(self):
        """Same rule the refusal recorder follows: recording a failure must not
        become the failure."""
        def boom(message, host, port, user, password):
            raise RuntimeError("relay refused")

        with _environment({"SMTP_HOST": "smtp.example.com",
                           "ALERT_EMAIL_TO": "ops@example.com"}):
            result = rs.send_failure_notice(self._failed_outcome(), log=lambda *a: None,
                                            smtp=boom)
        self.assertIn("email_failed", result)

        h = Harness(exits=[1] * 20)
        h._notify = lambda outcome, log=None: "email_failed (RuntimeError)"
        self.assertEqual(h.go().exit_code, 1)


class PlanArithmetic(unittest.TestCase):

    def test_minimum_timeout_is_the_waiting_plus_a_floor_for_every_attempt(self):
        plan = rs.RetryPlan(attempts=8, interval_seconds=900,
                            collector_headroom_seconds=1200)
        expected = (8 * 900                           # waiting
                    + 9 * rs.MIN_ATTEMPT_SECONDS      # a floor per attempt
                    + 1200                            # collector publishes
                    + rs.SUPERVISOR_EXIT_HEADROOM_SECONDS)
        self.assertEqual(plan.minimum_timeout_for_full_plan(), expected)
        self.assertEqual(expected, 11220,
                         "the figure the deploy refusal quotes to the operator")

    def test_the_deployed_default_can_reach_every_configured_attempt(self):
        """The default this repository deploys must satisfy its own gate."""
        plan = rs.RetryPlan()
        deployed = _deploy_default("REPLICA_TIMEOUT")
        self.assertGreaterEqual(deployed, plan.minimum_timeout_for_full_plan())

    def test_a_full_length_plan_is_reported_rather_than_enforced(self):
        plan = rs.RetryPlan()
        self.assertGreater(plan.timeout_for_full_budget_plan(6300),
                           plan.minimum_timeout_for_full_plan())

    def test_describe_reports_both_constraints(self):
        info = rs.describe(rs.RetryPlan(), 21600, 20400, 259200)
        self.assertTrue(info["all_attempts_reachable"])
        self.assertTrue(info["finishes_before_the_next_firing"])
        info = rs.describe(rs.RetryPlan(), 7200, 6000, 259200)
        self.assertFalse(info["all_attempts_reachable"])

    def test_a_negative_or_zero_interval_is_refused(self):
        with self.assertRaises(ValueError):
            rs.RetryPlan(attempts=8, interval_seconds=0)
        with self.assertRaises(ValueError):
            rs.RetryPlan(attempts=-1)

    def test_the_plan_is_read_from_the_environment_the_deploy_forwards(self):
        with _environment({"RETRY_ATTEMPTS": "3", "RETRY_INTERVAL_SECONDS": "600"}):
            plan = rs.plan_from_environment()
        self.assertEqual(plan.attempts, 3)
        self.assertEqual(plan.interval_seconds, 600)

    def test_a_non_numeric_plan_is_refused_rather_than_defaulted(self):
        """Silently falling back would deploy a plan nobody configured."""
        with _environment({"RETRY_ATTEMPTS": "eight"}):
            with self.assertRaises(ValueError):
                rs.plan_from_environment()


class CronMaths(unittest.TestCase):
    """The day-of-week conversion is load-bearing: cron Monday is 1 where
    Python's weekday() makes it 0, and getting it wrong shifts every firing."""

    def test_the_deployed_expression_fires_monday_and_thursday_at_six(self):
        firings = next_firings("0 6 * * 1,4",
                               datetime(2026, 11, 3, tzinfo=timezone.utc), 4)
        self.assertEqual([f.isoformat() for f in firings],
                         ["2026-11-05T06:00:00+00:00", "2026-11-09T06:00:00+00:00",
                          "2026-11-12T06:00:00+00:00", "2026-11-16T06:00:00+00:00"])

    def test_cron_one_is_monday_not_tuesday(self):
        monday = datetime(2026, 11, 9, 6, 0, tzinfo=timezone.utc)
        self.assertEqual(monday.weekday(), 0)
        self.assertTrue(matches("0 6 * * 1", monday))
        self.assertFalse(matches("0 6 * * 2", monday))

    def test_sunday_is_both_zero_and_seven(self):
        sunday = datetime(2026, 11, 8, 6, 0, tzinfo=timezone.utc)
        self.assertTrue(matches("0 6 * * 0", sunday))
        self.assertTrue(matches("0 6 * * 7", sunday))

    def test_the_shortest_gap_is_the_tightest_one_not_the_first_or_widest(self):
        """`0 6 * * 1,4` alternates 72 and 96 hours. 72 is what binds, and a
        max() or a first-gap would both give 96 and permit an overlap."""
        self.assertEqual(shortest_gap_seconds("0 6 * * 1,4"), 72 * 3600)
        self.assertEqual(shortest_gap_seconds("0 6 * * *"), 24 * 3600)
        self.assertEqual(shortest_gap_seconds("0 */4 * * *"), 4 * 3600)

    def test_an_expression_that_never_fires_raises(self):
        with self.assertRaises(ValueError):
            next_firings("0 6 30 2 *", datetime(2026, 1, 1, tzinfo=timezone.utc), 1)

    def test_this_module_keeps_exactly_one_copy_of_the_maths(self):
        """A second copy of the day-of-week conversion is a second chance to
        get it wrong, and the two would disagree silently.

        `tools/observe_schedule.py` is on the Mariano's side only, so the
        equivalent claim here is that nothing in this module defines the
        conversion outside walmart_collector/cron.py.
        """
        owner = ROOT / "walmart_collector" / "cron.py"
        definers = [path for path in ROOT.rglob("*.py")
                    if "__pycache__" not in path.parts
                    and path.name != "test_retry_supervisor.py"
                    and "Monday 0 -> cron 1" in path.read_text()]
        self.assertEqual(definers, [owner],
                         "the cron conversion must live in exactly one file")


class EntrypointWiring(unittest.TestCase):

    RUN_ENV = {"WALMART_STORE_ID": "100", "WALMART_SOURCE": "opd"}

    def test_the_per_attempt_budget_reaches_the_collector(self):
        """A budget fixed at startup would give attempt nine attempt one's
        figure and overrun the replica."""
        with _environment(self.RUN_ENV):
            argv = entry.command(budget_seconds=4242)
        self.assertIn("--max-seconds", argv)
        self.assertEqual(argv[argv.index("--max-seconds") + 1], "4242")

    def test_without_a_budget_it_still_derives_one_from_the_replica_timeout(self):
        with _environment(dict(self.RUN_ENV, REPLICA_TIMEOUT="21600")):
            argv = entry.command()
        self.assertEqual(argv[argv.index("--max-seconds") + 1],
                         str(21600 - entry.BUDGET_HEADROOM_SECONDS))

    def test_list_takes_no_budget_at_all(self):
        """`list` is not a run. A budget landing on the list argv is a defect
        this suite already caught once."""
        with _environment({}, clear=("WALMART_STORE_ID",)):
            argv = entry.command(budget_seconds=4242)
        self.assertNotIn("--max-seconds", argv)

    def test_the_replica_timeout_is_read_from_what_the_deploy_forwards(self):
        with _environment({"REPLICA_TIMEOUT": "20000"}):
            self.assertEqual(entry.replica_timeout_seconds(), 20000)
        with _environment({}, clear=("REPLICA_TIMEOUT",)):
            self.assertEqual(entry.replica_timeout_seconds(),
                             entry.DEFAULT_REPLICA_TIMEOUT)

    def test_the_entrypoint_does_not_execv_the_collector(self):
        """`os.execv` replaces this process, so nothing is left to see the exit
        code and no retry is possible. This is the structural guard: the whole
        retry path is unreachable if it comes back."""
        text = ENTRYPOINT.read_text()
        self.assertNotIn("os.execv(", text)
        self.assertIn("retry_supervisor", text)

    def test_the_image_ships_the_supervisor_the_entrypoint_imports(self):
        """An image missing it would build fine and fail at 06:00 UTC with
        nobody watching, which is the defect class this Dockerfile already
        guards for the store mapping."""
        self.assertIn("azure/retry_supervisor.py", DOCKERFILE.read_text())


class DeploymentGate(unittest.TestCase):
    """The real shell script, run."""

    def _deploy(self, **overrides):
        env = dict(os.environ,
                   RESOURCE_GROUP="rg", CONTAINERAPPS_ENVIRONMENT="env",
                   IMAGE="img",
                   AZURE_STORAGE_CONNECTION_STRING="UseDevelopmentStorage=true",
                   WALMART_SOURCE="opd",
                   WALMART_OPD_CLIENT_ID="id-not-a-secret",
                   WALMART_OPD_CLIENT_SECRET="placeholder-for-dry-run")
        for key in ("ALERT_EMAIL_TO", "SMTP_HOST", "SMTP_USERNAME",
                    "SMTP_PASSWORD", "RETRY_ATTEMPTS",
                    "RETRY_INTERVAL_SECONDS", "REPLICA_TIMEOUT"):
            env.pop(key, None)
        env.update({k: str(v) for k, v in overrides.items()})
        return subprocess.run(["bash", str(DEPLOY), "--dry-run"],
                              capture_output=True, text=True, env=env)

    def test_the_default_deployment_is_accepted(self):
        done = self._deploy()
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("Retry plan:", done.stderr)

    def test_it_refuses_a_timeout_that_cannot_reach_every_attempt(self):
        """7200 was the deployed figure, and 8 retries at 900s is 7200s of
        waiting alone. Refused rather than quietly shortened: a plan that stops
        at attempt three is not the plan that was configured."""
        done = self._deploy(REPLICA_TIMEOUT=7200)
        self.assertEqual(done.returncode, 1)
        self.assertIn("cannot reach all 9 attempts", done.stderr)
        self.assertIn("11220", done.stderr, "the operator needs the figure")

    def test_it_refuses_a_timeout_that_could_overrun_the_next_firing(self):
        """The instruction was that the next run stays on time. Azure's cron
        fires independently, so an overrun runs beside the next execution and
        meets the Blob lease, which refuses it."""
        done = self._deploy(REPLICA_TIMEOUT=300000)
        self.assertEqual(done.returncode, 1)
        self.assertIn("259200s gap", done.stderr)

    def test_a_smaller_plan_fits_the_smaller_timeout(self):
        """Guards the refusal tests from passing by refusing everything."""
        done = self._deploy(REPLICA_TIMEOUT=7200, RETRY_ATTEMPTS=2,
                            RETRY_INTERVAL_SECONDS=600)
        self.assertEqual(done.returncode, 0, done.stderr)

    def test_it_forwards_the_retry_figures_it_validated(self):
        """Validating one plan and deploying another is the drift this whole
        arrangement exists to prevent."""
        text = DEPLOY.read_text()
        self.assertIn('"RETRY_ATTEMPTS=$RETRY_ATTEMPTS"', text)
        self.assertIn('"RETRY_INTERVAL_SECONDS=$RETRY_INTERVAL_SECONDS"', text)
        self.assertIn('"REPLICA_TIMEOUT=$REPLICA_TIMEOUT"', text)

    def test_it_checks_the_plan_with_the_code_the_container_runs(self):
        """Retyping the arithmetic here would let a deployment promise a plan
        the supervisor does not deliver."""
        text = DEPLOY.read_text()
        self.assertIn("import retry_supervisor", text)
        self.assertIn("from walmart_collector.cron import shortest_gap_seconds", text)

    def test_email_asked_for_without_a_host_is_refused_at_deploy_time(self):
        done = self._deploy(ALERT_EMAIL_TO="ops@example.com")
        self.assertEqual(done.returncode, 1)
        self.assertIn("SMTP_HOST", done.stderr)

    def test_the_dry_run_says_which_failure_route_is_configured(self):
        quiet = self._deploy()
        self.assertIn("WALMART_RUN_FAILED_AFTER_RETRIES", quiet.stdout + quiet.stderr)
        loud = self._deploy(ALERT_EMAIL_TO="ops@example.com",
                            SMTP_HOST="smtp.example.com")
        self.assertIn("ops@example.com", loud.stdout + loud.stderr)

    def test_no_secret_value_is_echoed_by_a_dry_run(self):
        done = self._deploy(ALERT_EMAIL_TO="ops@example.com",
                            SMTP_HOST="smtp.example.com",
                            SMTP_USERNAME="ops", SMTP_PASSWORD="s3cr3t-do-not-log")
        self.assertNotIn("s3cr3t-do-not-log", done.stdout + done.stderr)


class PortedBetweenCollectors(unittest.TestCase):
    """The supervisor is one implementation kept in two places, and checked.

    The two collectors build their container images from separate contexts, so
    neither Dockerfile can COPY a module that lives above its own directory.
    There is therefore no shared importable home for the supervisor without
    restructuring both builds, and this repository already ports between the
    two modules for exactly that reason - the generic attribute forwarding in
    CompositeSource was ported this way.

    A copy that nobody checks is how two implementations of one rule drift
    apart and start disagreeing silently, which is the failure CLAUDE.md
    records for the deal columns and for the source report methods. So the copy
    is derived here by substitution and compared: a change to one side that is
    not made to the other fails this test by name, and the fix is to port it
    rather than to edit this list.
    """

    SUBSTITUTIONS = [
        ("marianos_collector", "walmart_collector"),
        ("MARIANOS_RUN_FAILED_AFTER_RETRIES", "WALMART_RUN_FAILED_AFTER_RETRIES"),
        ("MARIANOS_STORE_ID", "WALMART_STORE_ID"),
        ("MARIANOS_SOURCE", "WALMART_SOURCE"),
        ("Mariano's", "Walmart"),
        ("Marianos", "Walmart"),
        ("marianos", "walmart"),
        # The only intended behavioural difference: this collector publishes
        # per category and needs longer to finish the one in hand.
        ("collector_headroom_seconds: int = 900", "collector_headroom_seconds: int = 1200"),
    ]

    PAIRS = [
        ("azure/retry_supervisor.py", "azure/retry_supervisor.py"),
        ("marianos_collector/cron.py", "walmart_collector/cron.py"),
    ]

    def test_the_two_copies_are_the_same_file_with_the_names_changed(self):
        marianos_root = REPO / "marianos"
        walmart_root = REPO / "walmart"
        self.assertTrue(marianos_root.is_dir(), "both modules must be present")
        for left, right in self.PAIRS:
            with self.subTest(file=right):
                expected = (marianos_root / left).read_text()
                for before, after in self.SUBSTITUTIONS:
                    expected = expected.replace(before, after)
                actual = (walmart_root / right).read_text()
                self.assertEqual(
                    actual.splitlines(), expected.splitlines(),
                    f"{right} has drifted from marianos/{left}. Port the change "
                    f"to both rather than editing the substitution list.")

    def test_the_substitution_list_actually_changes_something(self):
        """Guards the test above from passing vacuously, which is how two of
        this repository's tests passed while asserting nothing.

        Checked across every ported file rather than one of them: a
        substitution can legitimately apply to only one of the pair, and
        looking in too narrow a place reported a live entry as dead.
        """
        text = "".join((REPO / "marianos" / left).read_text()
                       for left, _ in self.PAIRS)
        for before, after in self.SUBSTITUTIONS:
            with self.subTest(substitution=before):
                self.assertIn(before, text,
                              "a substitution that matches nothing is dead and "
                              "hides a real difference")


class _environment:
    """Set and restore environment variables around a block."""

    def __init__(self, values, clear=()):
        self.values = values
        self.clear = clear
        self.saved = {}

    def __enter__(self):
        for key in list(self.values) + list(self.clear):
            self.saved[key] = os.environ.get(key)
        for key, value in self.values.items():
            os.environ[key] = value
        for key in self.clear:
            os.environ.pop(key, None)
        return self

    def __exit__(self, *exc):
        for key, value in self.saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        return False


def _deploy_default(name: str) -> int:
    """The deployment default, read from the script rather than retyped."""
    import re
    text = DEPLOY.read_text()
    found = re.findall(rf'{name}="\$\{{{name}:-(\d+)\}}"', text)
    if not found:
        raise AssertionError(f"no {name} default found in {DEPLOY}")
    unique = set(found)
    assert len(unique) == 1, f"{name} has disagreeing defaults {sorted(unique)}"
    return int(unique.pop())


if __name__ == "__main__":
    unittest.main()
