"""Every Source must expose the report method the runner actually looks for.

This defect has now occurred three times in this repository, in three
different sources, and cost a release each time it was not caught:

- `KrogerSweepSource.provenance()` was never called, because the runner looks
  for `provenance_report()`. The unmapped labels, the unplaceable products,
  `page_failures` and `stopped_reason` reached no release, while the working
  rules claimed they did.
- `CatalogV2Source.provenance()` had the identical gap and was recorded as
  still unfixed.
- `AuthorizedProviderSource` had no report method under either name. The
  runner reads it through `hasattr`, so a release produced through that source
  carried no provenance block at all and nothing failed. That source has
  `coverage_attested = True`, so unlike the sweep it may publish outside the
  trial namespace: the source permitted the strongest claim disclosed the
  least.

A rename fixes one occurrence. This test is what makes the fourth occurrence
fail at the suite rather than at a release, by deriving the requirement from
the runner instead of restating it.
"""

import ast
import importlib
import inspect
import pkgutil
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import marianos_collector as package  # noqa: E402

RUNNER = Path(package.__file__).parent / "runner.py"

# Sources that exist only to serve test fixtures, and never produce a release.
FIXTURE_ONLY = {"FixtureSource"}


def source_classes():
    found = {}
    for module_info in pkgutil.iter_modules(package.__path__):
        module = importlib.import_module(f"{package.__name__}.{module_info.name}")
        for name, obj in vars(module).items():
            if (inspect.isclass(obj) and name.endswith("Source")
                    and obj.__module__ == module.__name__):
                found[name] = obj
    return found


def names_the_runner_reads_off_a_source():
    """Parse runner.py for the attribute names it reads off `self.source`.

    Derived rather than listed, because a list here would drift from the
    runner exactly as the working rules drifted from the code.
    """
    tree = ast.parse(RUNNER.read_text(encoding="utf-8"))
    names = set()
    for node in ast.walk(tree):
        # getattr(self.source, "name", ...) and hasattr(self.source, "name")
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id in ("getattr", "hasattr")
                and len(node.args) >= 2
                and isinstance(node.args[1], ast.Constant)
                and isinstance(node.args[1].value, str)):
            target = node.args[0]
            if (isinstance(target, ast.Attribute) and target.attr == "source"):
                names.add(node.args[1].value)
        # self.source.name
        if (isinstance(node, ast.Attribute)
                and isinstance(node.value, ast.Attribute)
                and node.value.attr == "source"):
            names.add(node.attr)
    return names


class TheRunnerLooksForProvenanceReport(unittest.TestCase):

    def test_the_runner_reads_provenance_report_and_not_provenance(self):
        names = names_the_runner_reads_off_a_source()
        self.assertIn("provenance_report", names)
        self.assertNotIn("provenance", names)

    def test_the_parse_found_a_plausible_surface(self):
        """If the parse silently found nothing, every assertion below would
        pass vacuously. The derivation is only useful if it works."""
        names = names_the_runner_reads_off_a_source()
        self.assertGreater(len(names), 3, names)


class EverySourceExposesTheReport(unittest.TestCase):

    def setUp(self):
        self.sources = source_classes()

    def test_the_sources_were_actually_discovered(self):
        """Guards against the discovery returning an empty mapping, which
        would make the real assertions below assert nothing."""
        self.assertGreaterEqual(len(self.sources), 4, sorted(self.sources))
        for expected in ("KrogerSweepSource", "CatalogV2Source",
                         "CompositeSource", "AuthorizedProviderSource"):
            self.assertIn(expected, self.sources)

    def test_every_non_fixture_source_has_provenance_report(self):
        missing = sorted(name for name, cls in self.sources.items()
                         if name not in FIXTURE_ONLY
                         and not hasattr(cls, "provenance_report"))
        self.assertEqual(missing, [], f"no provenance_report on: {missing}")

    def test_no_source_keeps_the_stale_name(self):
        """`provenance` is the name that reached no release three times. A
        source carrying it again, even beside the right one, is the start of
        the same divergence."""
        stale = sorted(name for name, cls in self.sources.items()
                       if hasattr(cls, "provenance"))
        self.assertEqual(stale, [], f"stale `provenance` on: {stale}")

    def test_a_source_that_attests_coverage_must_report_provenance(self):
        """The sharp case. A source with coverage_attested True may publish
        outside the trial namespace, so it is the one that must disclose
        most."""
        for name, cls in self.sources.items():
            if name in FIXTURE_ONLY:
                continue
            if getattr(cls, "coverage_attested", False):
                self.assertTrue(hasattr(cls, "provenance_report"),
                                f"{name} attests coverage and reports nothing")


class TheProviderReportSaysWhatItIsAndHidesTheToken(unittest.TestCase):

    def build(self):
        from marianos_collector.sources import AuthorizedProviderSource
        return AuthorizedProviderSource("https://provider.example/v1/feed",
                                        "s3cret-token-value")

    def test_it_reports_the_host_and_path(self):
        report = self.build().provenance_report()
        self.assertEqual(report["provider_host"], "provider.example")
        self.assertEqual(report["provider_path"], "/v1/feed")

    def test_the_token_appears_nowhere_in_the_report(self):
        import json
        report = self.build().provenance_report()
        self.assertNotIn("s3cret-token-value", json.dumps(report))

    def test_it_does_not_present_the_attestation_as_our_verification(self):
        report = self.build().provenance_report()
        self.assertTrue(report["coverage_attested"])
        self.assertIn("not an independent", report["coverage_attested_means"])

    def test_it_states_what_it_does_not_establish(self):
        report = self.build().provenance_report()
        self.assertTrue(report["_does_not_establish"])

    def test_counters_start_at_zero_and_are_reported(self):
        report = self.build().provenance_report()
        self.assertEqual(report["pages_fetched"], 0)
        self.assertEqual(report["transient_retries"], 0)


if __name__ == "__main__":
    unittest.main()
