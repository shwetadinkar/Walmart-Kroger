"""Declaring the roots a route cannot reach, without hiding the gap.

Five of the client's 28 roots came back empty on the 31 October sweep:
Coupons, Seafood, Coffee, Batteries, Light Bulbs. Kroger's category label
vocabulary has no equivalent for them, which is not the same as the shelf
being empty. The runner refuses a release with an empty configured root, and
that refusal is correct, so a scheduled sweep would fail every run for a
permanent vocabulary reason.

The fix is a declaration, not a weakened gate. A declared root is removed from
the configured set, so the zero-products gate still binds every other root,
and the declaration is carried in the release report so a reader can tell a
root that was never asked for from one that returned nothing.

The risk the declaration creates is the opposite one: it goes stale, the route
starts returning products for a declared root, and nobody notices because the
root is no longer asked for. So the declaration is checked against what the
source actually found. That check is the most important thing in this file.
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from marianos_collector import cli  # noqa: E402
from marianos_collector.config import categories_from_csv, stores_from_json  # noqa: E402
from marianos_collector.runner import Collector, ValidationFailure  # noqa: E402
from marianos_collector.sources import Page  # noqa: E402
from marianos_collector.storage import LocalStorage  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DECLARATION = ROOT / "config/sweep_coverage.json"


def product(store, n=1):
    return {
        "store_id": store.store_id, "zipcode": store.zipcode,
        "store_context_verified": True, "seller_type": "marianos",
        "fulfillment": "pickup", "product_id": f"P{n:03d}",
        "product_title": f"Item {n}", "weight": "12 oz",
        "regular_price": "4.99", "sale_price": "",
        "upc": f"999999000{n:04d}", "brand": "Test",
        "url": f"https://www.marianos.com/p/test-{n}",
        "image_url": f"https://www.marianos.com/images/{n}.jpg",
        "ppm": "", "volume_deals_description": "", "volume_deals_price": "",
        "digital_deals_description": "", "digital_deals_price": "",
    }


class Source:
    source_mode = "test_source"
    coverage_attested = False

    def __init__(self, populated=None):
        self._n = 0
        self._populated = populated

    def fetch(self, store, category, url, cursor):
        self._n += 1
        return Page(store_id=store.store_id, zipcode=store.zipcode,
                    store_context_verified=True, source_url=url,
                    products=[product(store, self._n)], children=[],
                    next_cursor="", subcategories_complete=False)

    def populated_roots(self):
        if self._populated is None:
            raise AssertionError("not asked for")
        return list(self._populated)


def categories(n=2):
    return categories_from_csv(ROOT / "config/categories.csv")[:n]


def store():
    return stores_from_json(ROOT / "config/stores_demo.json")[0]


def collect(source, cats, uncovered):
    with tempfile.TemporaryDirectory() as td:
        return Collector(LocalStorage(Path(td)), source, cats, min_products=1,
                         trial=True, uncovered_roots=uncovered).run(store())


class TheShippedDeclarationIsConsistent(unittest.TestCase):
    """It is config, so nothing in the code checks it. This does."""

    def setUp(self):
        self.declared = json.loads(DECLARATION.read_text())
        self.uncovered = self.declared["uncovered"]
        self.configured = {c.name for c in
                           categories_from_csv(ROOT / "config/categories.csv")}

    def test_every_declared_root_is_a_configured_category(self):
        self.assertEqual(set(self.uncovered) - self.configured, set())

    def test_every_declared_root_carries_a_reason(self):
        for name, reason in self.uncovered.items():
            with self.subTest(root=name):
                self.assertIsInstance(reason, str)
                self.assertGreater(len(reason.strip()), 40,
                                   "a reason has to say why, not just that")

    def test_it_names_the_five_roots_the_31_october_run_left_empty(self):
        self.assertEqual(sorted(self.uncovered),
                         ["Batteries", "Coffee", "Coupons", "Light Bulbs", "Seafood"])

    def test_it_says_which_run_and_store_measured_it(self):
        self.assertEqual(self.declared["measured"], "2026-10-31")
        self.assertEqual(self.declared["measured_store"], "53100502")

    def test_it_does_not_leave_the_28_roots_entirely_uncovered(self):
        self.assertLess(len(self.uncovered), len(self.configured))

    def test_the_seafood_reason_does_not_imply_no_seafood_was_collected(self):
        """It did not. Kroger files meat and seafood under one label, the map
        sends it to Meat and keeps the label in sub_category, so seafood ships
        inside the Meat records. A reviewer reading only the root name would
        conclude the opposite, so the reason has to say so itself."""
        reason = self.uncovered["Seafood"]
        self.assertIn("ARE in the delivered dataset", reason)
        self.assertIn("sub_category", reason)
        cmap = json.loads((ROOT / "config/category_map.json").read_text())
        self.assertEqual(cmap["map"]["Meat & Seafood"], "Meat")
        self.assertNotIn("Seafood", set(cmap["map"].values()))

    def test_the_coffee_reason_does_not_blame_a_map_that_has_the_entry(self):
        cmap = json.loads((ROOT / "config/category_map.json").read_text())
        self.assertEqual(cmap["map"].get("Coffee"), "Coffee")
        self.assertIn("map is not the obstacle", self.uncovered["Coffee"])


class AStaleDeclarationStopsTheRun(unittest.TestCase):
    """The one failure mode a declaration introduces, and the gate for it."""

    def test_a_declared_root_that_returns_products_fails_the_run(self):
        cats = categories(2)
        with self.assertRaises(ValidationFailure) as caught:
            collect(Source(populated=[cats[0].name, "Seafood"]),
                    cats, {"Seafood": "no mapping label"})
        self.assertIn("declaration is stale", str(caught.exception))
        self.assertIn("Seafood", str(caught.exception))

    def test_a_declared_root_that_stays_empty_does_not(self):
        cats = categories(2)
        out = collect(Source(populated=[c.name for c in cats]),
                      cats, {"Seafood": "no mapping label"})
        self.assertEqual(out["report"]["roots_not_covered_by_source"],
                         {"Seafood": "no mapping label"})

    def test_a_root_cannot_be_declared_uncovered_and_collected_at_once(self):
        cats = categories(2)
        with self.assertRaises(ValidationFailure) as caught:
            collect(Source(populated=[]), cats, {cats[0].name: "contradiction"})
        self.assertIn("also configured for collection", str(caught.exception))

    def test_a_source_that_cannot_report_its_roots_is_not_asked_to_guess(self):
        """Not every source can say which roots it reached. The declaration
        still travels in the release; only the staleness check is skipped."""
        class Quiet(Source):
            populated_roots = None

        cats = categories(2)
        out = collect(Quiet(), cats, {"Seafood": "no mapping label"})
        self.assertEqual(out["report"]["roots_not_covered_by_source"],
                         {"Seafood": "no mapping label"})


class TheDeclarationTravelsInTheRelease(unittest.TestCase):
    def test_the_report_names_the_roots_collected_and_the_roots_not(self):
        cats = categories(3)
        out = collect(Source(populated=[c.name for c in cats]), cats,
                      {"Seafood": "no mapping label", "Coffee": "labelled Beverages"})
        report = out["report"]
        self.assertEqual(report["roots_collected"], [c.name for c in cats])
        self.assertEqual(sorted(report["roots_not_covered_by_source"]),
                         ["Coffee", "Seafood"])
        for name in report["roots_not_covered_by_source"]:
            self.assertNotIn(name, report["category_counts"])

    def test_a_run_with_nothing_declared_says_so_rather_than_omitting_the_field(self):
        cats = categories(2)
        out = collect(Source(populated=[c.name for c in cats]), cats, {})
        self.assertEqual(out["report"]["roots_not_covered_by_source"], {})


class TheCliReadsTheDeclaration(unittest.TestCase):
    def test_the_shipped_file_drops_exactly_five_roots(self):
        args = cli.parser_().parse_args(
            ["run", "--source", "sweep", "--uncovered-roots", str(DECLARATION)])
        declared = json.loads(args.uncovered_roots.read_text())["uncovered"]
        kept = [c for c in categories_from_csv(args.categories)
                if c.name not in declared]
        self.assertEqual(len(kept), 23)

    def test_a_declared_root_that_is_not_a_configured_category_is_refused(self):
        with tempfile.TemporaryDirectory() as td:
            bad = Path(td) / "bad.json"
            bad.write_text(json.dumps({"uncovered": {"Nonsense": "a reason"}}))
            with self.assertRaises(SystemExit):
                cli.main(["run", "--source", "fixture", "--uncovered-roots", str(bad)])

    def test_a_declared_root_without_a_reason_is_refused(self):
        with tempfile.TemporaryDirectory() as td:
            bad = Path(td) / "bad.json"
            bad.write_text(json.dumps({"uncovered": {"Seafood": "  "}}))
            with self.assertRaises(SystemExit):
                cli.main(["run", "--source", "fixture", "--uncovered-roots", str(bad)])

    def test_declaring_every_root_uncovered_is_refused(self):
        with tempfile.TemporaryDirectory() as td:
            everything = {c.name: "a reason long enough to be a reason"
                          for c in categories_from_csv(ROOT / "config/categories.csv")}
            bad = Path(td) / "all.json"
            bad.write_text(json.dumps({"uncovered": everything}))
            with self.assertRaises(SystemExit):
                cli.main(["run", "--source", "fixture", "--uncovered-roots", str(bad)])


class TheAzureJobCanRunTheSweep(unittest.TestCase):
    def setUp(self):
        import importlib.util
        import os
        spec = importlib.util.spec_from_file_location(
            "sweep_entrypoint", ROOT / "azure" / "container_entrypoint.py")
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)
        self.keys = ("MARIANOS_STORE_ID", "MARIANOS_SOURCE", "KROGER_LOCATION_ID",
                     "MARIANOS_EXPECT_ZIPCODE", "MARIANOS_EXPECT_STREET",
                     "MARIANOS_SWEEP_WORK_DIR", "MARIANOS_SWEEP_MAX_SECONDS",
                     "REPLICA_TIMEOUT")
        self._saved = {k: os.environ.pop(k, None) for k in self.keys}

    def tearDown(self):
        import os
        for key, value in self._saved.items():
            os.environ.pop(key, None)
            if value is not None:
                os.environ[key] = value

    def set(self, **kwargs):
        import os
        os.environ.update(kwargs)

    def complete(self, **extra):
        self.set(MARIANOS_STORE_ID="53100502", MARIANOS_SOURCE="sweep",
                 KROGER_LOCATION_ID="53100502",
                 MARIANOS_EXPECT_ZIPCODE="60061",
                 MARIANOS_EXPECT_STREET="1720 N Milwaukee Ave", **extra)
        return self.module.command()

    def test_the_job_passes_the_declaration_and_the_resolved_store(self):
        argv = self.complete()
        self.assertIn("sweep", argv)
        self.assertIn("--resolve-store", argv)
        self.assertEqual(argv[argv.index("--expect-zipcode") + 1], "60061")
        self.assertEqual(argv[argv.index("--expect-street") + 1],
                         "1720 N Milwaukee Ave")
        self.assertEqual(argv[argv.index("--uncovered-roots") + 1],
                         "/app/config/sweep_coverage.json")

    def test_the_job_does_not_assert_an_authorization_it_has_not_got(self):
        """The sweep is the public tier. --authorized-source is the flag the
        two partner routes use, and a scheduled job must not pass it here."""
        self.assertNotIn("--authorized-source", self.complete())
        self.set(MARIANOS_STORE_ID="70100485", MARIANOS_SOURCE="provider")
        self.assertIn("--authorized-source", self.module.command())

    def test_the_address_assertions_are_required(self):
        for missing in ("MARIANOS_EXPECT_ZIPCODE", "MARIANOS_EXPECT_STREET"):
            with self.subTest(missing=missing):
                import os
                self.complete()
                os.environ.pop(missing)
                with self.assertRaises(ValueError):
                    self.module.command()

    def test_a_placeholder_location_is_refused(self):
        import os
        self.complete()
        os.environ["KROGER_LOCATION_ID"] = "REPLACE_ME"
        with self.assertRaises(ValueError):
            self.module.command()

    def test_the_work_dir_is_overridable_for_a_mounted_volume(self):
        argv = self.complete(MARIANOS_SWEEP_WORK_DIR="/mnt/sweep")
        self.assertEqual(argv[argv.index("--sweep-work-dir") + 1], "/mnt/sweep")

    def test_fixtures_are_still_not_runnable_from_a_scheduled_job(self):
        self.set(MARIANOS_STORE_ID="53100502", MARIANOS_SOURCE="fixture")
        with self.assertRaises(ValueError):
            self.module.command()



class TheCollectorStopsItselfBeforeAzureKillsIt(unittest.TestCase):
    """The collector was given exactly as long as Azure allows.

    The entrypoint passed no budget, so the CLI default of 7200 seconds
    applied, and `deploy_jobs.sh` deployed `--replica-timeout 7200`. The
    graceful stop and Azure's kill landed on the same instant, and the kill is
    SIGKILL: not an exception, so `refusal_recorded` never runs. An overrunning
    unattended run would leave **no release and no refusal record** - exactly
    the trace that machinery exists to leave - defeated by a configuration
    coincidence rather than by any code.
    """

    def setUp(self):
        import importlib.util
        import os
        spec = importlib.util.spec_from_file_location(
            "sweep_entrypoint2", ROOT / "azure" / "container_entrypoint.py")
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)
        self.keys = ("MARIANOS_SWEEP_MAX_SECONDS", "REPLICA_TIMEOUT",
                     "MARIANOS_STORE_ID", "MARIANOS_SOURCE",
                     "KROGER_LOCATION_ID", "MARIANOS_EXPECT_ZIPCODE",
                     "MARIANOS_EXPECT_STREET")
        self._saved = {k: os.environ.pop(k, None) for k in self.keys}

    def tearDown(self):
        import os
        for key, value in self._saved.items():
            os.environ.pop(key, None)
            if value is not None:
                os.environ[key] = value

    def test_the_budget_is_strictly_less_than_the_replica_timeout(self):
        import os
        os.environ["REPLICA_TIMEOUT"] = "7200"
        self.assertLess(self.module.sweep_budget_seconds(), 7200)

    def test_the_headroom_is_enough_to_publish(self):
        import os
        os.environ["REPLICA_TIMEOUT"] = "7200"
        self.assertEqual(7200 - self.module.sweep_budget_seconds(),
                         self.module.BUDGET_HEADROOM_SECONDS)
        self.assertGreaterEqual(self.module.BUDGET_HEADROOM_SECONDS, 300)

    def test_it_tracks_a_timeout_the_job_is_actually_deployed_with(self):
        import os
        os.environ["REPLICA_TIMEOUT"] = "3600"
        self.assertLess(self.module.sweep_budget_seconds(), 3600)

    def test_a_timeout_with_no_room_to_publish_is_refused(self):
        import os
        os.environ["REPLICA_TIMEOUT"] = "600"
        with self.assertRaises(ValueError):
            self.module.sweep_budget_seconds()

    def test_the_argv_carries_the_budget(self):
        import os
        os.environ.update(MARIANOS_STORE_ID="53100502", MARIANOS_SOURCE="sweep",
                          KROGER_LOCATION_ID="53100502",
                          MARIANOS_EXPECT_ZIPCODE="60061",
                          MARIANOS_EXPECT_STREET="1720 N Milwaukee Ave",
                          REPLICA_TIMEOUT="7200")
        argv = self.module.command()
        self.assertIn("--sweep-max-seconds", argv)
        budget = float(argv[argv.index("--sweep-max-seconds") + 1])
        self.assertLess(budget, 7200)

    def test_the_deploy_script_passes_the_timeout_through_to_the_container(self):
        """Otherwise the entrypoint would derive its budget from a default
        while the job was deployed with something else."""
        script = (ROOT / "azure" / "deploy_jobs.sh").read_text(encoding="utf-8")

        # Asserted on the ENVVARS entry itself, not on the substring. The
        # substring `REPLICA_TIMEOUT=$REPLICA_TIMEOUT` also occurs inside this
        # script's own error message, so the first version of this assertion
        # passed with the forwarding deleted: it was satisfied by the error
        # text. Exactly the "assert on something that changes" failure.
        forwarded = [line.strip() for line in script.splitlines()
                     if line.strip() == '"REPLICA_TIMEOUT=$REPLICA_TIMEOUT"']
        self.assertEqual(len(forwarded), 1,
                         "the replica timeout is not forwarded to the container "
                         "as an ENVVARS entry")
        self.assertIn('--replica-timeout "$REPLICA_TIMEOUT"', script)

    def test_the_deploy_script_refuses_a_timeout_with_no_headroom(self):
        script = (ROOT / "azure" / "deploy_jobs.sh").read_text(encoding="utf-8")
        self.assertIn("REPLICA_TIMEOUT <= 900", script)

class TheImageRefusesToBuildWithoutAVerifiedStore(unittest.TestCase):
    """config/stores_live.json is gitignored by design and nothing checked it.

    It holds the verified location id, so azure/README.md says to copy it from
    the template before building. A build that skipped that step produced a
    perfectly good image whose first act, at 06:00 UTC with nobody watching,
    was to fail on a missing file. A misconfigured job is the failure most
    likely to recur unattended, and the build is the cheapest place to catch
    it: on the operator's screen.
    """

    def setUp(self):
        self.dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")

    def test_the_build_checks_the_store_mapping_exists(self):
        self.assertIn("stores_live.json", self.dockerfile)
        self.assertIn("BUILD REFUSED", self.dockerfile)

    def test_the_build_also_rejects_placeholder_identities(self):
        """A copied template still saying DEMO would otherwise deploy, and this
        repository has published one store's data under another store's name
        once already."""
        for marker in ("DEMO", "REPLACE", "UNRESOLVED"):
            self.assertIn(marker, self.dockerfile)

    def test_the_check_runs_before_the_entrypoint_is_declared(self):
        """A check after ENTRYPOINT would still build a broken image."""
        self.assertLess(self.dockerfile.index("BUILD REFUSED"),
                        self.dockerfile.index("ENTRYPOINT"))

    def test_the_entrypoint_asks_for_the_file_the_build_checks(self):
        """The two must name the same path, or the build would verify a file
        the job does not read."""
        entry = (ROOT / "azure" / "container_entrypoint.py").read_text(
            encoding="utf-8")
        self.assertIn("/app/config/stores_live.json", entry)
        self.assertIn("/app/config/stores_live.json", self.dockerfile)


if __name__ == "__main__":
    unittest.main()

