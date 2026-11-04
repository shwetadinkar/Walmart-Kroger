"""The Walmart run stops itself before the platform kills it.

**There was no budget at all.** The only bound on a Walmart run was Azure's
`--replica-timeout 14400`, and `azure/AZURE_DEPLOYMENT.md` says plainly that
"the jobs are not guaranteed to finish in four hours". A replica timeout is a
SIGKILL rather than an exception, so a run that overran left **no release and
no refusal record** - the exact failure the refusal machinery exists for, on
the runs where nobody is watching.

The Mariano's side had the same defect in a different shape: its budget was set
equal to the timeout rather than absent. "Tested in both collectors" is two
claims, so this is the Walmart half, tested here.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from walmart_collector.config import categories_from_csv, stores_from_json  # noqa: E402
from walmart_collector.runner import Collector, ValidationFailure  # noqa: E402
from walmart_collector.sources import FixtureSource  # noqa: E402
from walmart_collector.storage import LocalStorage  # noqa: E402

CATEGORIES = categories_from_csv(ROOT / "config/categories.csv")
STORE = stores_from_json(ROOT / "config/stores.json")[0]


def failures(root):
    base = Path(root) / "failures"
    return sorted(p for p in base.rglob("*.json")) if base.exists() else []


class ABudgetedRunRefusesAndLeavesARecord(unittest.TestCase):

    def run_with_budget(self, seconds, categories=None):
        td = tempfile.mkdtemp()
        storage = LocalStorage(Path(td))
        collector = Collector(storage, FixtureSource(ROOT / "fixtures"),
                              categories or CATEGORIES[:2],
                              canaries={}, trial=True, max_seconds=seconds)
        return collector, storage, td

    def test_a_budget_of_zero_is_treated_as_no_budget(self):
        """So an unset flag does not accidentally refuse every run."""
        collector, _, _ = self.run_with_budget(0)
        self.assertIsNone(collector.max_seconds)

    def test_an_exhausted_budget_refuses_the_release(self):
        collector, _, td = self.run_with_budget(0.0001)
        time.sleep(0.01)
        with self.assertRaises(ValidationFailure) as caught:
            collector.run(STORE)
        self.assertIn("TIME_BUDGET_EXCEEDED", str(caught.exception))

    def test_the_refusal_leaves_a_record_naming_the_budget(self):
        """This is the whole point. A SIGKILL leaves nothing; this leaves a
        file saying what happened and why."""
        collector, _, td = self.run_with_budget(0.0001)
        time.sleep(0.01)
        with self.assertRaises(ValidationFailure):
            collector.run(STORE)
        records = failures(td)
        self.assertEqual(len(records), 1, "a budget stop left no record")
        body = json.loads(records[0].read_text())
        self.assertIn("TIME_BUDGET_EXCEEDED", json.dumps(body))

    def test_the_publishing_tree_is_untouched_by_a_budget_stop(self):
        collector, _, td = self.run_with_budget(0.0001)
        time.sleep(0.01)
        with self.assertRaises(ValidationFailure):
            collector.run(STORE)
        published = list((Path(td)).rglob("latest.json"))
        self.assertEqual(published, [])

    def test_a_generous_budget_does_not_interfere(self):
        collector, _, td = self.run_with_budget(3600)
        try:
            collector.run(STORE)
        except ValidationFailure as exc:
            self.assertNotIn("TIME_BUDGET_EXCEEDED", str(exc))

    def test_the_message_says_how_to_fix_it(self):
        collector, _, _ = self.run_with_budget(0.0001)
        time.sleep(0.01)
        with self.assertRaises(ValidationFailure) as caught:
            collector.run(STORE)
        self.assertIn("replica timeout", str(caught.exception).lower())


class TheEntrypointBudgetStaysUnderTheReplicaTimeout(unittest.TestCase):

    def setUp(self):
        spec = importlib.util.spec_from_file_location(
            "walmart_entrypoint", ROOT / "azure" / "container_entrypoint.py")
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)
        self.keys = ("REPLICA_TIMEOUT", "WALMART_MAX_SECONDS")
        self._saved = {k: os.environ.pop(k, None) for k in self.keys}

    def tearDown(self):
        for key, value in self._saved.items():
            os.environ.pop(key, None)
            if value is not None:
                os.environ[key] = value

    def test_it_is_strictly_less_than_the_deployed_timeout(self):
        os.environ["REPLICA_TIMEOUT"] = "14400"
        self.assertLess(self.module.budget_seconds(), 14400)

    def test_the_headroom_is_enough_to_publish(self):
        os.environ["REPLICA_TIMEOUT"] = "14400"
        self.assertEqual(14400 - self.module.budget_seconds(),
                         self.module.BUDGET_HEADROOM_SECONDS)
        self.assertGreaterEqual(self.module.BUDGET_HEADROOM_SECONDS, 300)

    def test_it_tracks_the_timeout_actually_deployed(self):
        os.environ["REPLICA_TIMEOUT"] = "7200"
        self.assertLess(self.module.budget_seconds(), 7200)

    def test_a_timeout_with_no_room_to_publish_is_refused(self):
        os.environ["REPLICA_TIMEOUT"] = "1200"
        with self.assertRaises(ValueError):
            self.module.budget_seconds()

    def test_the_argv_carries_the_budget(self):
        os.environ["REPLICA_TIMEOUT"] = "14400"
        os.environ["WALMART_STORE_ID"] = "100"
        os.environ["WALMART_SOURCE"] = "provider"
        try:
            argv = self.module.command()
        finally:
            os.environ.pop("WALMART_STORE_ID", None)
            os.environ.pop("WALMART_SOURCE", None)
        self.assertIn("run", argv)
        self.assertIn("--max-seconds", argv)
        self.assertLess(float(argv[argv.index("--max-seconds") + 1]), 14400)

    def test_a_non_run_command_takes_no_budget(self):
        """`list` is not a run. The first version of this patch put the budget
        on the shared return and so appended it to `list` as well."""
        os.environ.pop("WALMART_STORE_ID", None)
        argv = self.module.command()
        self.assertIn("list", argv)
        self.assertNotIn("--max-seconds", argv)

    def test_the_deploy_script_forwards_the_timeout_it_deploys(self):
        """Asserted on the ENVVARS entry, not on the substring: the same text
        occurs in the script's own error message, and asserting the substring
        would pass with the forwarding deleted."""
        script = (ROOT / "azure" / "deploy_jobs.sh").read_text(encoding="utf-8")
        forwarded = [line.strip() for line in script.splitlines()
                     if line.strip() == '"REPLICA_TIMEOUT=$REPLICA_TIMEOUT"']
        self.assertEqual(len(forwarded), 1)
        self.assertIn('--replica-timeout "$REPLICA_TIMEOUT"', script)

    def test_the_deploy_script_refuses_a_timeout_with_no_headroom(self):
        script = (ROOT / "azure" / "deploy_jobs.sh").read_text(encoding="utf-8")
        self.assertIn("REPLICA_TIMEOUT <= 1200", script)


if __name__ == "__main__":
    unittest.main()
