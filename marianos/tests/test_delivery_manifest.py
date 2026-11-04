"""The revision manifest and the change-to-test map.

This tool reported itself as a changed source file no test imports, on the run
immediately after it was added, which is the behaviour it exists to provide and
also a real gap. Both are tested here.
"""

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import delivery_manifest as tool  # noqa: E402

REPO = Path(__file__).resolve().parents[2]


class ModuleNamesCoverHowATestWouldImportIt(unittest.TestCase):

    def test_a_package_module_is_matched_by_its_dotted_and_bare_names(self):
        names = tool.module_names("marianos/marianos_collector/kroger.py")
        self.assertIn("kroger", names)
        self.assertIn("marianos_collector.kroger", names)

    def test_a_tool_is_matched_by_its_bare_name(self):
        self.assertIn("merge_page_enrichment",
                      tool.module_names("marianos/tools/merge_page_enrichment.py"))


class TheTestIndexIsReadFromTheTestsThemselves(unittest.TestCase):

    def setUp(self):
        self.index = tool.test_index(REPO, ["marianos/tests"])

    def test_a_module_with_a_known_test_is_indexed_to_it(self):
        self.assertIn("marianos/tests/test_merge_page_enrichment.py",
                      self.index.get("merge_page_enrichment", set()))

    def test_a_module_nothing_imports_is_absent(self):
        self.assertEqual(self.index.get("a_module_that_does_not_exist"), None)


class Sha256IsTheRealDigest(unittest.TestCase):

    def test_it_matches_hashlib_for_a_known_file(self):
        with tempfile.NamedTemporaryFile("wb", delete=False) as fh:
            fh.write(b"the quick brown fox")
            path = fh.name
        try:
            self.assertEqual(tool.sha256(path),
                             hashlib.sha256(b"the quick brown fox").hexdigest())
        finally:
            os.unlink(path)


class TheToolRunsAgainstThisRepository(unittest.TestCase):

    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.out = Path(self._td.name) / "out"
        self.delivered = Path(self._td.name) / "d.txt"
        self.delivered.write_text("delivered bytes", encoding="utf-8")
        head = subprocess.run(
            ["git", "-C", str(REPO), "rev-parse", "HEAD~1"],
            capture_output=True, text=True, check=True).stdout.strip()
        tool.main(["--repo", str(REPO), "--since", head,
                   "--delivery", str(self.delivered),
                   "--test-dir", "marianos/tests",
                   "--out", str(self.out)])
        self.manifest = json.loads(
            (self.out / "REVISION_MANIFEST.json").read_text())
        self.mapping = json.loads(
            (self.out / "CHANGE_TO_TEST_MAP.json").read_text())

    def tearDown(self):
        self._td.cleanup()

    def test_it_writes_all_three_artefacts(self):
        for name in ("REVISION_MANIFEST.json", "CHANGE_TO_TEST_MAP.json",
                     "CHANGE_TO_TEST_MAP.md"):
            self.assertTrue((self.out / name).exists(), name)

    def test_the_revision_is_the_real_head(self):
        head = subprocess.run(["git", "-C", str(REPO), "rev-parse", "HEAD"],
                              capture_output=True, text=True,
                              check=True).stdout.strip()
        self.assertEqual(self.manifest["revision"], head)

    def test_every_delivered_file_is_hashed(self):
        entry = self.manifest["delivered_files"][0]
        self.assertEqual(entry["sha256"],
                         hashlib.sha256(b"delivered bytes").hexdigest())
        self.assertEqual(entry["bytes"], len("delivered bytes"))
        self.assertEqual(self.manifest["delivered_file_count"], 1)

    def test_it_states_what_a_hash_does_not_establish(self):
        joined = " ".join(self.manifest["_does_not_establish"])
        self.assertIn("nothing about whether the values in them are right",
                      joined)

    def test_a_commit_lists_the_source_files_it_changed(self):
        self.assertEqual(len(self.mapping["commits"]), 1)
        self.assertTrue(
            isinstance(self.mapping["commits"][0]["source_files_changed"], list))

    def test_the_markdown_has_the_uncovered_section_either_way(self):
        text = (self.out / "CHANGE_TO_TEST_MAP.md").read_text()
        self.assertIn("Changed source files no test imports", text)


if __name__ == "__main__":
    unittest.main()
