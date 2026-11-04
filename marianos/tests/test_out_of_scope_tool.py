"""The out-of-scope reconciliation tool, end to end.

Flagged by `tools/delivery_manifest.py`: the tool was added with no test module
importing it, while the retention it depends on was tested. A tool the client
will run to produce a deliverable needs its own coverage, not coverage of the
thing underneath it.
"""

import csv
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import out_of_scope_reconciliation as tool  # noqa: E402
from marianos_collector.config import Category, Store  # noqa: E402
from marianos_collector.kroger_sweep_source import KrogerSweepSource  # noqa: E402

VERNON = Store("53100502", "60061", "Marianos - Marianos Vernon Hills",
               "1720 N Milwaukee Ave, Vernon Hills, IL 60061", "")
CMAP = {"Dairy": "Dairy"}
DAIRY = Category("Dairy", "https://www.marianos.com/d/dairy")


def offer():
    return {"soldBy": "UNIT", "size": "18 ct", "fulfillment": {"curbside": True},
            "price": {"regular": 2.98}, "inventory": {"stockLevel": "HIGH"}}


def product(upc, categories=("Dairy",)):
    return {"productId": upc, "upc": upc, "description": f"Item {upc}",
            "brand": "Kroger", "productPageURI": f"/p/item/{upc}",
            "categories": list(categories), "items": [offer()], "images": []}


class Fake:
    def __init__(self, by_term):
        self.by_term = by_term

    def products(self, location_id, term, offset=0, limit=50):
        items = self.by_term.get(term, [])
        return {"data": items[offset:offset + limit],
                "meta": {"pagination": {"total": len(items)}}}


class TheToolWritesTheReconciliation(unittest.TestCase):

    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.work = Path(self._td.name) / "w"
        self.out = Path(self._td.name) / "out"
        KrogerSweepSource(
            Fake({"milk": [product("0001111060933"),
                           product("0002222060001", categories=("Halloween",)),
                           product("0003333060002", categories=("Party",))]}),
            "53100502", self.work, {"Dairy": ["milk"]},
            category_map=CMAP).sweep_once(VERNON)
        self.args = [
            "--work-dir", str(self.work),
            "--location-id", "53100502", "--store-id", "53100502",
            "--zipcode", "60061",
            "--store-name", "Marianos - Marianos Vernon Hills",
            "--store-location", "1720 N Milwaukee Ave",
            "--release", "20261103T175940Z_426c12e8",
            "--out", str(self.out),
        ]

    def tearDown(self):
        self._td.cleanup()

    def run_tool(self, extra=()):
        # The real category map would place Halloween and Party nowhere either,
        # but this pins the fixture's map rather than depending on the config.
        real = tool.load_category_map
        tool.load_category_map = lambda: CMAP
        try:
            return tool.main(self.args + list(extra))
        finally:
            tool.load_category_map = real

    def test_it_writes_both_artefacts_and_the_counts_reconcile(self):
        self.assertEqual(self.run_tool(), 0)
        payload = json.loads(
            (self.out / "OUT_OF_SCOPE_RECONCILIATION.json").read_text())
        self.assertEqual(payload["out_of_scope_count"], 2)
        self.assertEqual(payload["unplaceable_counter"], 2)
        self.assertEqual(payload["products_served_under_a_root"], 1)
        self.assertTrue((self.out / "README.md").exists())

    def test_the_csv_carries_the_label_and_the_source_path_per_product(self):
        self.run_tool()
        with open(self.out / "out_of_scope_products.csv", encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        self.assertEqual(sorted(r["retailer_label"] for r in rows),
                         ["Halloween", "Party"])
        self.assertTrue(all(r["source_response_file"].endswith(".json")
                            for r in rows))
        self.assertTrue(all(r["upc"] for r in rows))

    def test_no_root_is_assigned_to_any_of_them(self):
        self.run_tool()
        with open(self.out / "out_of_scope_products.csv", encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        self.assertEqual({r["configured_root"] for r in rows}, {""})

    def test_the_readme_states_what_it_does_not_establish(self):
        self.run_tool()
        text = (self.out / "README.md").read_text()
        self.assertIn("does not establish", text.lower())
        self.assertIn("Completion of any required root", text)

    def test_it_refuses_a_store_id_that_differs_from_the_location_id(self):
        """Otherwise the labels would describe a store that was not queried."""
        args = list(self.args)
        args[args.index("--store-id") + 1] = "53100508"
        self.assertEqual(args[args.index("--location-id") + 1], "53100502")
        with self.assertRaises(SystemExit):
            tool.main(args)

    def test_it_collects_nothing_and_needs_no_client(self):
        """It re-indexes the persisted responses. If it ever starts needing a
        Kroger client, that is a collection and does not belong here."""
        self.run_tool()
        payload = json.loads(
            (self.out / "OUT_OF_SCOPE_RECONCILIATION.json").read_text())
        self.assertGreater(payload["responses_indexed"], 0)

    def test_a_mismatch_between_the_counter_and_the_rows_is_refused(self):
        real = tool.KrogerSweepSource

        class Skewed(real):
            def _index_raw(self, store):
                index = super()._index_raw(store)
                index.unplaceable += 1   # a counter that does not match
                return index

        tool.KrogerSweepSource = Skewed
        try:
            with self.assertRaises(SystemExit) as caught:
                self.run_tool()
            self.assertIn("not a reconciliation", str(caught.exception))
        finally:
            tool.KrogerSweepSource = real


if __name__ == "__main__":
    unittest.main()
