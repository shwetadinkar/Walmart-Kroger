"""The out-of-scope products are retained as identities, not only counted.

The client's instruction of 4 November: retain their original retailer labels
and identities in a separate unmapped/out-of-scope reconciliation, with source
paths and counts; do not invent a root assignment and do not discard historical
observations.

Before this, `SweepIndex` kept `unplaceable` as an integer and `unmapped` as
label -> count, and dropped the product. So the identities could not be
produced for a published release without re-indexing, and the source path each
was read from was discarded at the point it was in hand.
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from marianos_collector.config import Category, Store  # noqa: E402
from marianos_collector.kroger_sweep_source import KrogerSweepSource  # noqa: E402

VERNON = Store("53100502", "60061", "Marianos - Marianos Vernon Hills",
               "1720 N Milwaukee Ave, Vernon Hills, IL 60061", "")
CMAP = {"Dairy": "Dairy"}
DAIRY = Category("Dairy", "https://www.marianos.com/d/dairy")


def offer(**changes):
    item = {"soldBy": "UNIT", "size": "18 ct", "fulfillment": {"curbside": True},
            "price": {"regular": 2.98}, "inventory": {"stockLevel": "HIGH"}}
    item.update(changes)
    return item


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


def indexed(by_term, terms, work):
    source = KrogerSweepSource(Fake(by_term), "53100502", work, terms,
                              category_map=CMAP)
    source.sweep_once(VERNON)
    source.fetch(VERNON, DAIRY, DAIRY.url, "")
    return source


class TheOutOfScopeProductsAreRetained(unittest.TestCase):

    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        work = Path(self._td.name) / "w"
        # One mapped product and three whose retailer label is not in the map.
        self.source = indexed(
            {"milk": [product("0001111060933"),
                      product("0002222060001", categories=("Halloween",)),
                      product("0003333060002", categories=("Party",)),
                      product("0004444060003", categories=("Party",))]},
            {"Dairy": ["milk"]}, work)
        self.report = self.source.provenance_report()
        self.rows = self.report["out_of_scope_products"]

    def tearDown(self):
        self._td.cleanup()

    def test_every_counted_product_is_also_retained_as_an_identity(self):
        self.assertEqual(self.report["unplaceable_unmapped_products"], 3)
        self.assertEqual(len(self.rows), 3)

    def test_the_retailer_label_is_kept_exactly_as_returned(self):
        self.assertEqual(sorted(r["retailer_label"] for r in self.rows),
                         ["Halloween", "Party", "Party"])

    def test_the_identity_and_upc_are_retained(self):
        self.assertEqual(sorted(r["upc"] for r in self.rows),
                         ["0002222060001", "0003333060002", "0004444060003"])
        self.assertTrue(all(r["identity"] for r in self.rows))

    def test_the_source_response_file_is_retained_for_every_one(self):
        self.assertTrue(all(r["source_response_file"] for r in self.rows))
        self.assertTrue(all(r["source_response_file"].endswith(".json")
                            for r in self.rows))

    def test_no_root_is_assigned_and_the_search_term_is_not_used_as_one(self):
        for row in self.rows:
            self.assertEqual(row["configured_root"], "")
            self.assertNotEqual(row["retailer_label"], row["search_term"])

    def test_the_mapped_product_is_not_in_the_reconciliation(self):
        self.assertNotIn("0001111060933", [r["upc"] for r in self.rows])

    def test_the_out_of_scope_products_are_served_under_no_root(self):
        """They are recorded beside the release, never in it."""
        served = self.source.fetch(VERNON, DAIRY, DAIRY.url, "").products
        self.assertEqual([p["upc"] for p in served], ["0001111060933"])

    def test_no_bucket_is_created_for_the_empty_root(self):
        """Asserting only on what `fetch` serves for a configured category was
        decorative: a product bucketed under "" is served to nobody, so that
        assertion held even when the product was placed. The bucket itself is
        the thing that must not exist, because `product_count` sums every
        bucket and a release would then report these products as served."""
        self.assertNotIn("", self.source._index.by_root)
        self.assertEqual(sorted(self.source._index.by_root), ["Dairy"])

    def test_the_served_count_counts_only_products_under_a_configured_root(self):
        self.assertEqual(self.report["products_served"], 1)
        self.assertEqual(self.report["products_seen"], 4)

    def test_the_counter_and_the_retained_rows_cannot_disagree(self):
        """The reconciliation tool refuses on a mismatch, so this is the
        property that makes that check meaningful rather than decorative."""
        self.assertEqual(self.report["unplaceable_unmapped_products"],
                         len(self.rows))

    def test_the_report_survives_a_round_trip_as_json(self):
        again = json.loads(json.dumps(self.report["out_of_scope_products"]))
        self.assertEqual(again, self.rows)


if __name__ == "__main__":
    unittest.main()
