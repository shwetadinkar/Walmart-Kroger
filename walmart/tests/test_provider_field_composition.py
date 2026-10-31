"""ppm and regular_price on the 615: exact source text, stated as composed."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import compose_provider_fields as tool
from walmart_collector.schema import FIELDS


def row(identity):
    base = dict.fromkeys(FIELDS, "")
    base.update(url=f"https://www.walmart.com/ip/x/{identity}", product_title="T", upc="1",
                zipcode="72712", crawl_date="2026-10-22", weight="100.8 Fluid Ounces")
    return base


RAW = """[
 {"product_id": "1", "url": "https://www.walmart.com/ip/x/1", "unit_price": 0.340, "unit": "fl oz",
  "final_price": 5.78},
 {"product_id": "2", "url": "https://www.walmart.com/ip/x/2", "unit_price": null, "unit": null,
  "final_price": 20},
 {"product_id": "3", "url": "https://www.walmart.com/ip/x/3", "unit_price": 2, "unit": "ct",
  "final_price": null},
 {"product_id": "4", "url": "https://www.walmart.com/ip/x/4", "unit_price": 0.5, "unit": "",
  "final_price": 3.5}
]"""
RAW_LATER = """[{"product_id": "1", "url": "https://www.walmart.com/ip/x/1", "unit_price": 0.340,
  "unit": "fl oz", "final_price": 6.01}]"""


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        self.snapshots = self.dir / "snapshots"
        self.snapshots.mkdir()
        (self.snapshots / "a.json").write_text(RAW)
        (self.snapshots / "b.json").write_text(RAW_LATER)
        patch = mock.patch.object(tool, "_validate", return_value="")
        patch.start()
        self.addCleanup(patch.stop)
        self.rows = [row(str(n)) for n in (1, 2, 3, 4)]
        stated = {"1": 0.34, "2": None, "3": 2, "4": 0.5}
        self.evidence = {f"100:{k}": {
            "file": "a.json", "row_index_zero_based": int(k) - 1, "source_row_sha256": "h" + k,
            "source_observed_at": "2026-10-22T00:00:00Z", "available_for_pickup": k != "2",
            "provider_unit_price_candidate_not_proven_displayed": v} for k, v in stated.items()}
        self.evidence["100:1"]["provider_unit_price_candidate_not_proven_displayed"] = "0.340"

    def composed(self):
        return tool.compose(self.rows, self.evidence, self.snapshots, "s" * 64)


class Values(Base):
    def test_raw_number_text_is_kept_and_nothing_is_rounded(self):
        self.assertEqual(self.composed()[0][0]["ppm"], "$0.340/fl oz")
        self.assertEqual(tool.compose_ppm("0.1579123", "oz"), "$0.1579123/oz")

    def test_either_part_absent_leaves_ppm_blank(self):
        rows = self.composed()[0]
        self.assertEqual((rows[1]["ppm"], rows[3]["ppm"]), ("", ""))
        self.assertEqual(rows[2]["ppm"], "$2/ct")

    def test_a_non_number_is_refused(self):
        with self.assertRaises(tool.CompositionRefused):
            tool.compose_ppm("15.8 c", "oz")

    def test_regular_price_comes_from_final_price(self):
        rows = self.composed()[0]
        self.assertEqual([r["regular_price"] for r in rows], ["5.78", "20.00", "", "3.50"])

    def test_a_price_needing_rounding_is_refused_not_rounded(self):
        with self.assertRaises(tool.CompositionRefused):
            tool.format_regular("5.785")

    def test_no_other_field_changes(self):
        rows = self.composed()[0]
        tool.check(self.rows, rows)
        self.assertEqual(rows[0]["unit_price"], "")
        for field in FIELDS:
            if field not in tool.COMPOSED_FIELDS:
                self.assertEqual(rows[0][field], self.rows[0][field])


class Refusals(Base):
    def test_changing_any_other_field(self):
        changed = [dict(r) for r in self.rows]
        changed[0]["weight"] = "x"
        with self.assertRaisesRegex(tool.CompositionRefused, "weight"):
            tool.check(self.rows, changed)

    def test_filling_the_briefs_unit_price(self):
        changed = [dict(r) for r in self.rows]
        changed[0]["unit_price"] = "1"
        with self.assertRaises(tool.CompositionRefused):
            tool.check(self.rows, changed)

    def test_row_count_or_order(self):
        with self.assertRaises(tool.CompositionRefused):
            tool.check(self.rows, self.rows[:1])
        reordered = [dict(reversed(list(r.items()))) for r in self.rows]
        with self.assertRaises(tool.CompositionRefused):
            tool.check(self.rows, reordered)

    def test_input_with_a_value_in_gupc(self):
        self.rows[0]["gupc"] = "x"
        with self.assertRaisesRegex(tool.CompositionRefused, "gupc"):
            self.composed()

    def test_a_product_with_no_evidence(self):
        del self.evidence["100:2"]
        with self.assertRaisesRegex(tool.CompositionRefused, "No evidence"):
            self.composed()

    def test_evidence_pointing_at_another_products_row(self):
        self.evidence["100:1"]["row_index_zero_based"] = 2
        with self.assertRaisesRegex(tool.CompositionRefused, "is not 1"):
            self.composed()

    def test_a_row_disagreeing_with_the_sidecar(self):
        self.evidence["100:3"]["provider_unit_price_candidate_not_proven_displayed"] = 9
        with self.assertRaisesRegex(tool.CompositionRefused, "sidecar"):
            self.composed()


class Provenance(Base):
    def test_each_value_names_its_source_and_the_statement(self):
        entry = self.composed()[1]["1"]
        self.assertEqual(entry["ppm"]["source_fields"], ["unit_price", "unit"])
        self.assertEqual(entry["ppm"]["raw_unit_price"], "0.340")
        self.assertEqual(entry["ppm"]["provider_statement"], tool.STATEMENT)
        self.assertEqual(entry["ppm"]["provider_statement_sha256"], "s" * 64)
        self.assertEqual(entry["ppm"]["source_row_sha256"], "h1")
        self.assertEqual(entry["regular_price"]["source_fields"], ["final_price"])
        self.assertEqual(entry["regular_price"]["raw_final_price"], "5.78")

    def test_composed_ppm_says_dollars_against_rendered_cents(self):
        entry = self.composed()[1]["1"]["ppm"]
        self.assertEqual(entry["status"], "composed_not_captured_as_displayed")
        self.assertIn("in dollars", entry["basis"])
        self.assertIn("render cents", entry["basis"])
        self.assertIn("no capture", entry["basis"])

    def test_a_blank_says_why(self):
        entries = self.composed()[1]
        self.assertEqual(entries["2"]["ppm"]["status"], "blank_field_absent")
        self.assertEqual(entries["3"]["regular_price"]["status"], "blank_field_absent")

    def test_a_price_differing_across_snapshots_is_recorded(self):
        disagreements = self.composed()[2]
        self.assertEqual(disagreements, [{"identity": "1", "field": "final_price", "kept": "5.78",
                                          "observed_across_snapshots": ["5.78", "6.01"]}])

    def test_the_note_is_computed_and_keeps_the_gaps(self):
        rows, provenance, disagreements = self.composed()
        facts = tool.summary(rows, provenance, disagreements)
        self.assertEqual((facts["ppm_populated"], facts["ppm_blank"]), (2, 2))
        self.assertEqual((facts["regular_price_populated"], facts["regular_price_blank"]), (3, 1))
        self.assertEqual(facts["populated_where_pickup_not_available"], 1)
        text = tool.note(facts)
        self.assertIn("| `ppm` | 2 | 2 |", text)
        self.assertIn("composed, not captured", text)
        self.assertIn("no acceptance is recorded", text)

    def test_output_folder_must_be_new_and_input_stays(self):
        submission = self.dir / "in.json"
        submission.write_text(json.dumps(self.rows))
        evidence = self.dir / "e.json"
        evidence.write_text(json.dumps(self.evidence))
        statement = self.dir / "s.md"
        statement.write_text("x")
        args = ["--submission", str(submission), "--evidence", str(evidence), "--snapshots",
                str(self.snapshots), "--statement", str(statement)]
        before = submission.read_bytes()
        self.assertEqual(tool.main([*args, "--output", str(self.dir / "new")]), 0)
        self.assertEqual(submission.read_bytes(), before)
        self.assertEqual(tool.main([*args, "--output", str(self.dir / "new")]), 1)


class Gate(Base):
    def test_main_refuses_a_composition_that_touched_another_field(self):
        submission = self.dir / "in.json"
        submission.write_text(json.dumps(self.rows))
        evidence = self.dir / "e.json"
        evidence.write_text(json.dumps(self.evidence))
        statement = self.dir / "s.md"
        statement.write_text("x")
        spoiled = [{**self.rows[0], "weight": "x"}] + self.rows[1:]
        with mock.patch.object(tool, "compose", return_value=(spoiled, {}, [])):
            code = tool.main(["--submission", str(submission), "--evidence", str(evidence),
                              "--snapshots", str(self.snapshots), "--statement", str(statement),
                              "--output", str(self.dir / "out")])
        self.assertEqual(code, 1)
        self.assertFalse((self.dir / "out").exists())


if __name__ == "__main__":
    unittest.main()
