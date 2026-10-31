"""The client's three worked examples, each run through the real importer.

Run twice against one output folder, as two dated collections of one store.
Every assertion on the second run is against something the second run changed,
and retained rows are told apart through retention.json, never by the record.
"""
import copy
import json
import tempfile
import unittest
from pathlib import Path

import sys as _sys, pathlib as _pathlib
_sys.path.insert(0, str(_pathlib.Path(__file__).resolve().parent.parent))
_sys.path.insert(0, str(_pathlib.Path(__file__).resolve().parent))

from marianos_collector.api_trial import import_snapshot
from test_api_trial import product, store

FIRST, SECOND = "2026-10-24T10:00:00Z", "2026-10-25T10:00:00Z"


def stocked(p, level):
    p = copy.deepcopy(p)
    p["items"][0]["inventory"] = {"stockLevel": level}
    return p


class WorkedExamples(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.out = self.root / "out"
        self.eggs = stocked(product("0001111060933"), "HIGH")
        self.other = stocked(product("0001111060934"), "HIGH")
        # Enough that one absence is not the material yield drop the brief gates.
        self.rest = [stocked(product(f"000111106094{n}"), "HIGH") for n in range(4)]

    def collect(self, products, at):
        src = self.root / "src"
        src.mkdir(exist_ok=True)
        (src / "verified_store.json").write_text(json.dumps({"data": store()}))
        (src / "page_00.json").write_text(json.dumps(
            {"locationId": "53100508", "observed_at": at, "response": {"data": products}}))
        report = import_snapshot(src, self.out, "53100508", "60661", 1)
        pointer = json.loads((self.out / "latest.json").read_text())
        rows = {r["upc"]: r for r in json.loads((self.out / pointer["data_key"]).read_text())}
        meta = json.loads((self.out / pointer["retention_key"]).read_text())
        return report, rows, {k.rsplit(":", 1)[1]: v for k, v in meta.items()}

    def test_available_becoming_unavailable(self):
        self.collect([self.eggs, self.other], FIRST)
        gone = stocked(self.eggs, "TEMPORARILY_OUT_OF_STOCK")
        gone["items"][0]["price"]["regular"] = 3.49
        _, rows, meta = self.collect([gone, self.other], SECOND)
        row, m = rows[self.eggs["upc"]], meta[self.eggs["upc"]]
        self.assertEqual(len(rows), 2)
        self.assertEqual((row["regular_price"], row["crawl_date"]), ("3.49", "2026-10-25"))
        self.assertEqual((m["availability_state"], m["observation_status"]),
                         ("unavailable", "current"))
        self.assertEqual(m["historical_prices"]["regular_price"]["value"], "2.98")
        self.assertEqual(meta[self.other["upc"]]["availability_state"], "available")

    def test_a_missing_price(self):
        self.collect([self.eggs, self.other], FIRST)
        unpriced = copy.deepcopy(self.eggs)
        unpriced["items"][0].pop("price")
        report, rows, meta = self.collect([unpriced, self.other], SECOND)
        row, m = rows[self.eggs["upc"]], meta[self.eggs["upc"]]
        self.assertEqual(len(rows), 2)
        self.assertEqual((row["regular_price"], row["crawl_date"]), ("", "2026-10-25"))
        self.assertEqual(m["price_observed_at"]["regular_price"], "")
        self.assertEqual(m["historical_prices"]["regular_price"]["value"], "2.98")
        self.assertEqual(m["pickup_context"]["offer_gaps"], ["NO_POSITIVE_REGULAR_PRICE"])
        self.assertEqual(report["current_records"], 2)

    def test_a_product_absent_on_the_next_run(self):
        self.collect([self.eggs, self.other, *self.rest], FIRST)
        report, rows, meta = self.collect([self.other, *self.rest], SECOND)
        row, m = rows[self.eggs["upc"]], meta[self.eggs["upc"]]
        self.assertEqual(len(rows), 6)
        self.assertEqual((row["regular_price"], row["crawl_date"]), ("2.98", "2026-10-24"))
        self.assertEqual(m["observation_status"], "carried_forward")
        self.assertEqual(m["carry_forward_reason"], "NOT_RETURNED_IN_CURRENT_COLLECTION")
        self.assertEqual(m["last_observed_at"], FIRST)
        self.assertEqual(rows[self.other["upc"]]["crawl_date"], "2026-10-25")
        self.assertEqual(meta[self.other["upc"]]["observation_status"], "current")
        self.assertEqual((report["current_records"], report["carried_forward_records"]), (5, 1))


if __name__ == "__main__":
    unittest.main()
