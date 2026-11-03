"""What a store's response actually evidences about carriage.

The first version of this classifier returned a carriage verdict for **any**
product the endpoint returned, and only recorded `has_regular_price` as a
detail it never used. Its own docstring stated the correct rule - at least one
item the store prices or stocks - so the right rule was written down and the
wrong one implemented.

The run of 326 ids therefore reported 324 carried and **zero** confirmed
absences, which is not a finding about the store but a classifier that never
says no. Kroger's product-details endpoint returns the catalogue record whether
or not the location carries the product. The client caught it before the number
reached anyone, and asked for two changes: count a product as carried only on
price or stock evidence at the location, and treat a 404 as absence rather than
a lookup failure.

The test that matters most is `test_a_catalogue_record_alone_is_not_carriage`.
Under the old classifier it was impossible to write, because nothing could
produce a non-carriage verdict except an empty array.
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import resolve_sitemap_gap as gap  # noqa: E402


def response(items=None, description="Item"):
    return {"data": [{"description": description, "items": list(items or [])}]}


class PresenceInTheCatalogueIsNotCarriage(unittest.TestCase):
    def test_a_catalogue_record_alone_is_not_carriage(self):
        """The defect. 324 of 326 ids took this path and were called carried."""
        verdict, detail = gap.classify(response([{}]))
        self.assertEqual(verdict, gap.NO_STORE_EVIDENCE)
        self.assertIn("unknown", detail["_why"])

    def test_a_price_at_the_location_is_carriage_evidence(self):
        verdict, _ = gap.classify(response([{"price": {"regular": 2.99}}]))
        self.assertEqual(verdict, gap.PRICED)
        self.assertIn(verdict, gap.CARRIAGE_EVIDENCE)

    def test_a_stock_level_without_a_price_is_also_carriage_evidence(self):
        verdict, _ = gap.classify(response([{"inventory": {"stockLevel": "LOW"}}]))
        self.assertEqual(verdict, gap.STOCKED)
        self.assertIn(verdict, gap.CARRIAGE_EVIDENCE)

    def test_a_zero_price_is_not_a_price(self):
        """Read as a price it would mean free, which is the same rule the
        schema layer applies."""
        verdict, _ = gap.classify(response([{"price": {"regular": 0}}]))
        self.assertEqual(verdict, gap.NO_STORE_EVIDENCE)

    def test_no_items_at_all_is_not_carriage(self):
        self.assertEqual(gap.classify(response([]))[0], gap.NO_STORE_EVIDENCE)

    def test_an_empty_data_array_is_absence(self):
        self.assertEqual(gap.classify({"data": []})[0], gap.ABSENT)

    def test_a_single_object_rather_than_an_array_is_handled(self):
        document = {"data": {"description": "X", "items": [{"price": {"regular": 1.5}}]}}
        self.assertEqual(gap.classify(document)[0], gap.PRICED)

    def test_the_stock_levels_are_retained_for_a_later_reclassification(self):
        """The first run kept only a price boolean, so a priceless product
        could not be narrowed afterwards. That is why it is kept now."""
        _, detail = gap.classify(response([{"inventory": {"stockLevel": "HIGH"}}]))
        self.assertEqual(detail["stock_levels"], ["HIGH"])

    def test_every_verdict_says_why(self):
        for document in (response([{"price": {"regular": 1}}]),
                        response([{"inventory": {"stockLevel": "HIGH"}}]),
                        response([{}]), {"data": []}):
            with self.subTest(document=document):
                self.assertTrue(gap.classify(document)[1].get("_why"))


class AFourOhFourIsAnAnswer(unittest.TestCase):
    def test_a_404_is_absence_not_a_failure(self):
        verdict, detail = gap.classify_error("Kroger API HTTP 404")
        self.assertEqual(verdict, gap.ABSENT)
        self.assertIn("404", detail["_why"])

    def test_any_other_error_stays_unresolved(self):
        for message in ("Kroger API HTTP 500", "timeout", "connection reset"):
            with self.subTest(message=message):
                self.assertEqual(gap.classify_error(message)[0], gap.UNRESOLVED)

    def test_an_unresolved_error_keeps_its_text(self):
        self.assertEqual(gap.classify_error("boom")[1]["error"], "boom")


class TheSavedReportCanBeCorrectedWithoutSpendingCalls(unittest.TestCase):
    """Re-spending 326 calls to correct an error of mine is not the client's
    cost to bear."""

    def saved(self, priced, unpriced, not_found):
        results = {}
        for i in range(priced):
            results[f"p{i}"] = {"verdict": "carried_and_missed", "has_regular_price": True}
        for i in range(unpriced):
            results[f"q{i}"] = {"verdict": "carried_and_missed", "has_regular_price": False}
        for i in range(not_found):
            results[f"r{i}"] = {"verdict": "unresolved", "error": "Kroger API HTTP 404"}
        return {"counts": {"carried_and_missed": priced + unpriced,
                           "not_carried": 0, "unresolved": not_found},
                "results": results}

    def test_it_reproduces_the_real_runs_split(self):
        """186 priced, 138 unpriced, 2 404s, from the actual run."""
        redone = gap.reclassify(self.saved(186, 138, 2))
        self.assertEqual(redone["counts"], {gap.PRICED: 186,
                                            gap.NO_STORE_EVIDENCE: 138,
                                            gap.ABSENT: 2})

    def test_nothing_is_still_called_carried_without_evidence(self):
        redone = gap.reclassify(self.saved(0, 5, 0))
        self.assertEqual(redone["counts"].get(gap.PRICED, 0), 0)
        self.assertEqual(redone["counts"][gap.NO_STORE_EVIDENCE], 5)

    def test_it_says_stock_could_not_be_recovered(self):
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "GAP_RESOLUTION.json"
            src.write_text(json.dumps(self.saved(2, 3, 1)))
            out = Path(td) / "out"
            gap.main(["--reclassify", str(src), "--out", str(out)])
            report = json.loads((out / "GAP_RESOLUTION_RECLASSIFIED.json").read_text())
        self.assertIn("not stock levels", report["_stock_was_not_retained"])
        self.assertEqual(report["original_counts"]["carried_and_missed"], 5)

    def test_the_bounds_are_both_reported(self):
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "GAP_RESOLUTION.json"
            src.write_text(json.dumps(self.saved(186, 138, 2)))
            out = Path(td) / "out"
            gap.main(["--reclassify", str(src), "--out", str(out)])
            report = json.loads((out / "GAP_RESOLUTION_RECLASSIFIED.json").read_text())
        self.assertEqual(report["lower_bound_missed_by_the_sweep"], 186)
        self.assertEqual(report["upper_bound_missed_by_the_sweep"], 324)

    def test_reclassify_makes_no_request(self):
        """It must work with no credentials and no network at all."""
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "GAP_RESOLUTION.json"
            src.write_text(json.dumps(self.saved(1, 1, 1)))
            self.assertEqual(
                gap.main(["--reclassify", str(src), "--out", str(Path(td) / "o")]), 0)


class TheUndeterminedBucketIsNotHidden(unittest.TestCase):
    """Asserted against the written report rather than the source text, so a
    line wrap cannot break it and a reworded source cannot pass it."""

    def report(self):
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "GAP_RESOLUTION.json"
            src.write_text(json.dumps({
                "counts": {}, "results": {
                    "a": {"verdict": "carried_and_missed", "has_regular_price": True},
                    "b": {"verdict": "carried_and_missed", "has_regular_price": False}}}))
            out = Path(td) / "out"
            gap.main(["--reclassify", str(src), "--out", str(out)])
            return json.loads((out / "GAP_RESOLUTION_RECLASSIFIED.json").read_text())

    def test_the_undetermined_bucket_is_named_in_the_report(self):
        report = self.report()
        self.assertEqual(report["counts"][gap.NO_STORE_EVIDENCE], 1)
        self.assertEqual(report["lower_bound_missed_by_the_sweep"], 1)
        self.assertEqual(report["upper_bound_missed_by_the_sweep"], 2)

    def test_each_undetermined_product_says_it_is_undetermined(self):
        report = self.report()
        undetermined = [v for v in report["results"].values()
                        if v["verdict"] == gap.NO_STORE_EVIDENCE]
        self.assertEqual(len(undetermined), 1)
        self.assertIn("undetermined", undetermined[0]["_why"])

    def test_the_docstring_describes_the_verdicts_the_code_returns(self):
        """The first version's docstring stated a rule the code did not
        implement, which is how the defect survived being written down."""
        for verdict in (gap.PRICED, gap.STOCKED, gap.NO_STORE_EVIDENCE,
                        gap.ABSENT, gap.UNRESOLVED):
            with self.subTest(verdict=verdict):
                self.assertIn(verdict, gap.__doc__)
        self.assertNotIn("carried_and_missed", gap.__doc__.split("The first version")[0])


if __name__ == "__main__":
    unittest.main()
