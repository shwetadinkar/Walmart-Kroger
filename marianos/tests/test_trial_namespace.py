"""The trial storage namespace must be derived in exactly one place.

It was derived twice, and the two disagreed: `runner` hashed the category
tuples with `sort_keys=True` and compact separators, `cli` used `json.dumps`
defaults. So `run` wrote to one `trials/<signature>` and `status`, `export` and
`clear-checkpoints` addressed another. A trial looked like it had produced
nothing, and resetting its checkpoints cleared a path nothing had written.

These tests drive the whole sequence the client asked for, run then status then
export then reset, over one subset, through the real CLI.
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from marianos_collector import cli  # noqa: E402
from marianos_collector.config import categories_from_csv  # noqa: E402
from marianos_collector.runner import storage_namespaces  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
STORE = "DEMO-LAKESHORE-60601"
SUBSET = "Dairy,Produce"


def run_cli(command, out, extra=()):
    return cli.main([
        command,
        "--stores", str(ROOT / "config/stores_demo.json"),
        "--categories", str(ROOT / "config/categories.csv"),
        "--store", STORE,
        "--source", "fixture",
        "--fixtures", str(ROOT / "fixtures"),
        "--output", str(out),
        "--minimum-products", "1",
        "--only-categories", SUBSET,
        *extra,
    ])


def subset_categories():
    wanted = set(SUBSET.split(","))
    return [c for c in categories_from_csv(ROOT / "config/categories.csv")
            if c.name in wanted]


class OneCanonicalNamespace(unittest.TestCase):
    def test_the_helper_is_the_only_definition_and_is_stable(self):
        cats = subset_categories()
        first = storage_namespaces(cats, True)
        self.assertEqual(first, storage_namespaces(cats, True))
        self.assertTrue(first[0].startswith("trials/"))
        self.assertTrue(first[1].startswith("checkpoints-trials/"))

    def test_a_full_run_is_published_not_a_trial(self):
        cats = subset_categories()
        self.assertEqual(storage_namespaces(cats, False), ("published", "checkpoints"))

    def test_different_subsets_get_different_namespaces(self):
        all_cats = categories_from_csv(ROOT / "config/categories.csv")
        a = storage_namespaces(all_cats[:2], True)
        b = storage_namespaces(all_cats[2:4], True)
        self.assertNotEqual(a, b)


class RunStatusExportReset(unittest.TestCase):
    """The sequence the client asked for, over one subset."""

    def test_status_and_export_see_what_run_wrote(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td)
            self.assertEqual(run_cli("run", out), 0)

            namespace, checkpoint_root = storage_namespaces(subset_categories(), True)

            pointer = out / namespace / STORE / "latest.json"
            self.assertTrue(
                pointer.exists(),
                f"run wrote nothing that status would read at {namespace}")

            self.assertEqual(run_cli("status", out), 0)

            export = out / "exported.json"
            self.assertEqual(
                run_cli("export", out, ["--export-file", str(export)]), 0)
            self.assertTrue(export.exists(), "export produced no file")
            records = json.loads(export.read_text(encoding="utf-8"))
            self.assertGreater(len(records), 0, "export produced an empty file")

    def test_reset_clears_the_checkpoints_a_trial_run_would_leave(self):
        """A completed run tidies its own checkpoints away, so asserting on an
        empty directory afterwards asserts nothing. This plants a checkpoint at
        the namespace the Collector derives, which is where an interrupted run
        leaves one, and then requires `clear-checkpoints` to remove it."""
        with tempfile.TemporaryDirectory() as td:
            out = Path(td)
            cats = subset_categories()
            _, checkpoint_root = storage_namespaces(cats, True)

            planted = []
            for category in cats:
                path = out / checkpoint_root / STORE / f"{category.slug}.json"
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('{"pages": [], "cursor": "part-way"}', encoding="utf-8")
                planted.append(path)
            self.assertTrue(all(p.exists() for p in planted))

            self.assertEqual(run_cli("clear-checkpoints", out, ["--confirm-reset"]), 0)

            left = [p for p in planted if p.exists()]
            self.assertEqual(
                left, [],
                f"clear-checkpoints left {len(left)} of {len(planted)} checkpoints "
                f"in {checkpoint_root}; it addressed a different namespace")

    def test_a_trial_does_not_write_into_published(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td)
            run_cli("run", out)
            self.assertFalse(
                (out / "published" / STORE / "latest.json").exists(),
                "a category subset overwrote the complete published dataset")


if __name__ == "__main__":
    unittest.main()
