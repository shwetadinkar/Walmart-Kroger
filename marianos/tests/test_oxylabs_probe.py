"""The probe must find the field if it is there, and must not invent a verdict.

Its whole job is one question: does `marianos_product` return a price per
measure and the retailer's deal wording. A probe that misses a field one level
deeper than expected, or that answers the question itself from a key name,
would be worse than not running it.
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import oxylabs_probe as probe  # noqa: E402


class ItFindsAFieldWhereverItSits(unittest.TestCase):
    def test_a_nested_rate_field_is_found(self):
        paths = probe.flatten({"product": {"price": {"unit_price": "0.49/oz"}}})
        self.assertIn("product.price.unit_price", paths)
        self.assertEqual(probe.candidates(paths, probe.RATE_PATTERNS)
                         ["product.price.unit_price"], "0.49/oz")

    def test_a_field_inside_a_list_is_found(self):
        paths = probe.flatten({"offers": [{"promo_text": "Buy 1 Get 1"}]})
        self.assertEqual(probe.candidates(paths, probe.DEAL_PATTERNS)
                         ["offers[0].promo_text"], "Buy 1 Get 1")

    def test_every_leaf_is_listed_even_when_no_pattern_matches(self):
        """A field whose name matches neither pattern must still be visible,
        or the probe answers no when the truth is that we did not look."""
        paths = probe.flatten({"product": {"rate_per_measure_display": "$0.49"}})
        self.assertEqual(probe.candidates(paths, probe.RATE_PATTERNS), {})
        self.assertIn("product.rate_per_measure_display", paths)

    def test_absent_fields_produce_no_candidates(self):
        paths = probe.flatten({"product": {"title": "Milk", "price": 3.49}})
        self.assertEqual(probe.candidates(paths, probe.RATE_PATTERNS), {})
        self.assertEqual(probe.candidates(paths, probe.DEAL_PATTERNS), {})


class ItPrefersCheckableSubjects(unittest.TestCase):
    """A UPC whose displayed rate we already read off the page makes the
    answer checkable. One that does not can only show a field exists."""

    def data(self, with_ppm, without_ppm):
        records = []
        for i in range(with_ppm):
            records.append({"upc": f"1{i:012d}", "ppm": "$0.49/oz",
                            "product_title": f"A{i}", "regular_price": "3.49",
                            "weight": "12 oz"})
        for i in range(without_ppm):
            records.append({"upc": f"2{i:012d}", "ppm": "",
                            "product_title": f"B{i}", "regular_price": "1.99",
                            "weight": "8 oz"})
        path = Path(tempfile.mkdtemp()) / "data.json"
        path.write_text(json.dumps(records))
        return path

    def test_it_takes_the_rated_ones_first(self):
        picked = probe.subjects(self.data(10, 10), 5)
        self.assertTrue(all(s["observed_ppm"] for s in picked))

    def test_it_still_fills_up_when_too_few_are_rated(self):
        picked = probe.subjects(self.data(2, 10), 5)
        self.assertEqual(len(picked), 5)
        self.assertEqual(sum(1 for s in picked if s["observed_ppm"]), 2)

    def test_a_record_with_no_upc_is_not_probed(self):
        path = Path(tempfile.mkdtemp()) / "data.json"
        path.write_text(json.dumps([{"upc": "", "ppm": "$1/oz"},
                                    {"upc": "0001", "ppm": ""}]))
        self.assertEqual([s["upc"] for s in probe.subjects(path, 5)], ["0001"])


class ItIsBoundedAndSendsNothingUnasked(unittest.TestCase):
    def test_the_cap_is_refused_before_any_request(self):
        with self.assertRaises(SystemExit):
            probe.main(["--count", str(probe.HARD_CAP + 1), "--dry-run"])

    def test_zero_is_refused(self):
        with self.assertRaises(SystemExit):
            probe.main(["--count", "0", "--dry-run"])

    def test_a_real_run_must_say_where_the_responses_go(self):
        """Responses that are not kept cannot be checked by anyone else."""
        with self.assertRaises(SystemExit):
            probe.main(["--count", "5"])

    def test_the_store_context_is_sent_by_default(self):
        subject = {"upc": "0001"}
        body = probe.payload(subject, "marianos_product", "query", True, "scrape")
        self.assertEqual(body["store_id"], "53100502")
        self.assertEqual(body["delivery_zip"], "60061")
        self.assertEqual(body["fulfillment_type"], "pickup")

    def test_the_store_context_can_be_omitted_to_see_if_it_matters(self):
        body = probe.payload({"upc": "0001"}, "marianos_product", "query",
                             False, "scrape")
        for key in ("store_id", "delivery_zip", "fulfillment_type"):
            self.assertNotIn(key, body)

    def test_the_target_is_in_the_path_for_scrape_and_a_field_for_classic(self):
        """Oxylabs has two shapes and the account decides which. Getting this
        wrong costs a round trip, so both are supported rather than assumed."""
        scrape = probe.payload({"upc": "1"}, "marianos_product", "query", False, "scrape")
        classic = probe.payload({"upc": "1"}, "marianos_product", "query", False, "classic")
        self.assertNotIn("source", scrape)
        self.assertEqual(classic["source"], "marianos_product")

    def test_an_api_key_is_preferred_over_a_username(self):
        import os
        from unittest import mock
        with mock.patch.dict(os.environ, {"OXYLABS_WEB_API_KEY": "k",
                                          "OXYLABS_USERNAME": "u",
                                          "OXYLABS_PASSWORD": "p"}, clear=True):
            header, which = probe.auth_header()
        self.assertEqual(header, "Bearer k")
        self.assertEqual(which, "OXYLABS_WEB_API_KEY")

    def test_basic_auth_is_used_when_there_is_no_key(self):
        import os
        from unittest import mock
        with mock.patch.dict(os.environ, {"OXYLABS_USERNAME": "u",
                                          "OXYLABS_PASSWORD": "p"}, clear=True):
            header, _ = probe.auth_header()
        self.assertTrue(header.startswith("Basic "))

    def test_no_credentials_at_all_sends_nothing(self):
        import os
        from unittest import mock
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(SystemExit) as caught:
                probe.auth_header()
        self.assertIn("Nothing was sent", str(caught.exception))

    def test_credentials_are_never_an_argument(self):
        flags = probe.main.__doc__ or ""
        source = (ROOT / "tools/oxylabs_probe.py").read_text()
        self.assertNotIn("add_argument(\"--password", source)
        self.assertNotIn("add_argument(\"--username", source)
        self.assertNotIn("add_argument(\"--api-key", source)
        self.assertIn("OXYLABS_USERNAME", source)
        self.assertIn("OXYLABS_WEB_API_KEY", source)


class ItDoesNotAnswerTheQuestionItself(unittest.TestCase):
    def test_the_report_refuses_to_compute_a_verdict(self):
        source = (ROOT / "tools/oxylabs_probe.py").read_text()
        self.assertIn("_verdict_is_not_computed_here", source)

    def test_it_says_a_candidate_is_a_key_name_match_only(self):
        source = (ROOT / "tools/oxylabs_probe.py").read_text()
        self.assertIn("KEY NAME", source)

    def test_nothing_in_it_writes_to_a_dataset(self):
        """A value from a different method on a different date must not be
        merged into an earlier run, so the probe has no way to reach the
        schema, retention or storage layers at all. Asserted structurally
        rather than by scanning the prose: the first version of this test
        searched the whole file for "publish" and tripped on the docstring
        sentence saying it publishes nothing.
        """
        import ast
        tree = ast.parse((ROOT / "tools/oxylabs_probe.py").read_text())
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        # Narrowed on 3 November. The first version forbade importing
        # marianos_collector at all, which fired the moment the probe started
        # using the shared Oxylabs transport. The property that matters is
        # that it cannot reach the layers that write a release, not that it
        # imports nothing from the package.
        source = (ROOT / "tools/oxylabs_probe.py").read_text()
        for forbidden in ("marianos_collector.schema",
                          "marianos_collector.retention",
                          "marianos_collector.storage",
                          "marianos_collector.runner",
                          "marianos_collector.composition"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)
        self.assertNotIn("schema", imported)
        self.assertNotIn("runner", imported)

    def test_every_write_targets_the_out_directory(self):
        """Its only output is under --out, so nothing it produces can land
        beside a release by accident."""
        import ast
        tree = ast.parse((ROOT / "tools/oxylabs_probe.py").read_text())
        writes = [n for n in ast.walk(tree)
                  if isinstance(n, ast.Call)
                  and isinstance(n.func, ast.Attribute)
                  and n.func.attr in ("write_text", "write_bytes", "mkdir")]
        self.assertTrue(writes, "no writes found; the test is looking at nothing")
        for call in writes:
            rendered = ast.dump(call)
            self.assertIn("'out'", rendered,
                          f"a write that does not go through --out: {ast.unparse(call)}")


class TheSummarySaysWhyItFailed(unittest.TestCase):
    """The first real run printed "responses_with_parsed_content: 0" and
    nothing else, so the reader could not tell a 404 from a 401 from a shape
    mismatch without opening a raw file. A summary that hides the reason is
    not a summary."""

    def test_the_summary_carries_the_status_counts(self):
        source = (ROOT / "tools/oxylabs_probe.py").read_text()
        self.assertIn("http_status_counts", source)

    def test_the_summary_carries_the_first_error_body(self):
        source = (ROOT / "tools/oxylabs_probe.py").read_text()
        self.assertIn("first_error_body", source)

    def test_an_error_excerpt_is_kept_per_result_when_content_is_absent(self):
        source = (ROOT / "tools/oxylabs_probe.py").read_text()
        self.assertIn("error_excerpt", source)


if __name__ == "__main__":
    unittest.main()
