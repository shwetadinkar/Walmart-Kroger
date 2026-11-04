"""The two parses of the 1 November read are NOT interchangeable.

`CLAUDE.md` used to claim that "a `parsed.json` produced before the distinction
existed re-merges to the same result as one produced after", on the reasoning
that the merge imports `classify_card_line` and re-classifies every
`deal_lines` entry rather than trusting the parse.

Half of that is true. Re-classification *removes* a badge the old parser
wrongly admitted as a deal, so false positives are fixed whichever file is
passed. It cannot *recover* an offer the old parser put into `size`, because
such a line never reaches `deal_lines` at all and there is nothing to
re-classify.

So passing the pre-fix file silently loses real offers, and the claim would
have led a reader to pass it. These tests pin the difference with the measured
figures, so the claim cannot be re-asserted without a named failure.
"""

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from parse_page_harvest import classify_card_line  # noqa: E402

HARVEST = ROOT / "reports" / "2026-11-01-vernon-hills-page-harvest" / "data"
PRE_FIX = HARVEST / "parsed_full.json"
CORRECTED = HARVEST / "parsed_full_corrected.json"
FOUR_NOV = (ROOT / "reports" / "2026-11-04-vernon-hills-page-harvest"
            / "page_reads.json")


def by_upc(path):
    return {r["upc"]: r for r in json.loads(path.read_text())}


def deal_values(records):
    """What the merge would admit as a deal from these parsed records."""
    return [line for record in records.values()
            for line in (record.get("deal_lines") or [])
            if classify_card_line(line) == "deal"]


class BothFilesExist(unittest.TestCase):
    """Guards every test below from passing because a path moved."""

    def test_the_three_merge_inputs_are_present_and_tracked(self):
        for path in (PRE_FIX, CORRECTED, FOUR_NOV):
            with self.subTest(path=path.name):
                self.assertTrue(path.is_file(), f"{path} is missing")
                self.assertGreater(len(json.loads(path.read_text())), 0)


class NotInterchangeable(unittest.TestCase):

    def setUp(self):
        self.pre = by_upc(PRE_FIX)
        self.fixed = by_upc(CORRECTED)

    def test_the_corrected_parse_admits_more_deals_than_the_pre_fix_one(self):
        """169 against 174, measured. If these ever become equal, either the
        files changed or someone has re-run the old parser over the harvest."""
        self.assertEqual(len(deal_values(self.pre)), 169)
        self.assertEqual(len(deal_values(self.fixed)), 174)
        self.assertLess(len(deal_values(self.pre)), len(deal_values(self.fixed)))

    def test_the_offers_the_old_parser_lost_are_in_size_not_in_deal_lines(self):
        """The mechanism, not just the count. A sold-by-weight card carries no
        size, so the line after the title was taken as one whatever it said."""
        lost = []
        for upc, record in self.fixed.items():
            was = self.pre.get(upc)
            if not was:
                continue
            for line in record.get("deal_lines") or []:
                if (classify_card_line(line) == "deal"
                        and line not in (was.get("deal_lines") or [])):
                    lost.append((upc, line, was.get("size", "")))

        self.assertTrue(lost, "nothing was lost, so this test proves nothing")
        # Every lost offer must be sitting in the old file's size field: that is
        # the defect. If one is simply absent, the mechanism is different and
        # this test should be rewritten rather than relaxed.
        for upc, line, old_size in lost:
            with self.subTest(upc=upc):
                self.assertEqual(old_size, line,
                                 "a lost offer not found in the old size field")

        texts = {line for _, line, _ in lost}
        self.assertTrue(any(t.startswith("Coupon:") for t in texts),
                        "the two produce coupons should be among the lost")
        self.assertTrue(any("Buy 1, Get 1 Free" in t for t in texts),
                        "the BOGO offers should be among the lost")

    def test_the_pre_fix_file_is_recognisable_without_reading_its_values(self):
        """How a reader tells them apart. The old parser wrote neither key."""
        pre = next(iter(self.pre.values()))
        fixed = next(iter(self.fixed.values()))
        for key in ("stock_label", "non_deal_labels"):
            with self.subTest(key=key):
                self.assertNotIn(key, pre)
                self.assertIn(key, fixed)

    def test_re_classification_still_fixes_the_false_positives(self):
        """The half of the original claim that IS true, kept so the correction
        above is not read as the re-classification being useless."""
        raw = sum(len(r.get("deal_lines") or []) for r in self.pre.values())
        admitted = len(deal_values(self.pre))
        self.assertGreater(raw, admitted,
                           "re-classification should reject badges the old "
                           "parser admitted")
        self.assertEqual(raw, 257)


class TheRuleIsWrittenDown(unittest.TestCase):

    def test_claude_md_does_not_claim_the_parses_are_interchangeable(self):
        """The claim is what sent a reader to the wrong file, so its absence is
        worth asserting rather than trusting."""
        text = (ROOT.parent / "CLAUDE.md").read_text()
        self.assertNotIn(
            "re-merges to the same result as one\nproduced after", text)
        self.assertIn("never `parsed_full.json`", text)

    def test_claude_md_names_the_four_november_input_correctly(self):
        """There is no parsed_full.json for that read; its records are in
        page_reads.json, and a command naming the wrong file fails late."""
        text = (ROOT.parent / "CLAUDE.md").read_text()
        self.assertIn("page_reads.json", text)
        self.assertFalse(
            (ROOT / "reports" / "2026-11-04-vernon-hills-page-harvest"
             / "data" / "parsed_full.json").exists(),
            "if this file now exists, the guidance above needs revisiting")


if __name__ == "__main__":
    unittest.main()
