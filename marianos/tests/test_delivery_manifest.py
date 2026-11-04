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

    def test_a_dirty_tree_says_what_is_dirty_not_merely_that_it_is(self):
        """A bare working_tree_clean: false tells a reviewer that something was
        uncommitted and not what, which invites the question the manifest
        exists to answer. Untracked run outputs are the normal case and say
        nothing about the revision; a modified tracked file means the revision
        does not describe the source that produced the delivery."""
        for key in ("modified_tracked_files", "untracked_paths",
                    "modified_tracked_file_count", "untracked_path_count"):
            self.assertIn(key, self.manifest)
        self.assertIsInstance(self.manifest["modified_tracked_files"], list)
        self.assertEqual(self.manifest["modified_tracked_file_count"],
                         len(self.manifest["modified_tracked_files"]))
        self.assertEqual(self.manifest["untracked_path_count"],
                         len(self.manifest["untracked_paths"]))
        self.assertIn("does not", self.manifest["_working_tree_note"])

    def test_the_two_kinds_of_dirt_are_not_conflated(self):
        """An untracked path must never be counted as a modified tracked file."""
        paths = {x["path"] for x in self.manifest["modified_tracked_files"]}
        self.assertEqual(paths & set(self.manifest["untracked_paths"]), set())
        statuses = {x["status"] for x in self.manifest["modified_tracked_files"]}
        self.assertNotIn("??", statuses)

    def test_the_markdown_explains_a_dirty_tree_in_words(self):
        """The text is wrapped, so the assertion collapses whitespace first.
        Checking a literal phrase against wrapped prose fails on a line break
        and says nothing about the behaviour."""
        text = " ".join((self.out / "CHANGE_TO_TEST_MAP.md").read_text().split())
        if not self.manifest["working_tree_clean"]:
            self.assertTrue(
                ("MODIFIED and not committed" in text)
                or ("untracked path" in text), text[:400])


class TheTwoKindsOfDirtInARepoThatHasBoth(unittest.TestCase):
    """Built as its own repository on purpose.

    The assertions in the class above ran against whatever this checkout
    happened to contain. With no untracked path present they could not detect
    untracked being counted as modified: reverting the split passed every test.
    A fixture that holds one modified tracked file and one untracked file
    exercises the classification instead of depending on ambient state.
    """

    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.repo = Path(self._td.name) / "r"
        (self.repo / "pkg").mkdir(parents=True)
        (self.repo / "tests").mkdir()
        (self.repo / "pkg" / "thing.py").write_text("X = 1\n", encoding="utf-8")
        (self.repo / "tests" / "test_thing.py").write_text(
            "import thing\n", encoding="utf-8")

        def g(*args):
            subprocess.run(["git", "-C", str(self.repo), *args],
                           check=True, capture_output=True)
        g("init", "-q")
        g("config", "user.email", "t@example.invalid")
        g("config", "user.name", "T")
        g("add", "-A")
        g("commit", "-qm", "base")
        self.base = subprocess.run(
            ["git", "-C", str(self.repo), "rev-parse", "HEAD"],
            capture_output=True, text=True, check=True).stdout.strip()
        (self.repo / "pkg" / "thing.py").write_text("X = 2\n", encoding="utf-8")
        g("add", "-A")
        g("commit", "-qm", "change thing")

        # Now make the tree dirty in both ways, deliberately.
        (self.repo / "pkg" / "thing.py").write_text("X = 3\n", encoding="utf-8")
        (self.repo / "untracked_output.json").write_text("{}", encoding="utf-8")

        self.out = Path(self._td.name) / "out"
        tool.main(["--repo", str(self.repo), "--since", self.base,
                   "--test-dir", "tests", "--out", str(self.out)])
        self.manifest = json.loads(
            (self.out / "REVISION_MANIFEST.json").read_text())

    def tearDown(self):
        self._td.cleanup()

    def test_the_modified_tracked_file_is_reported_as_modified(self):
        self.assertEqual([x["path"] for x in self.manifest["modified_tracked_files"]],
                         ["pkg/thing.py"])
        self.assertEqual(self.manifest["modified_tracked_file_count"], 1)

    def test_the_untracked_file_is_reported_as_untracked(self):
        self.assertEqual(self.manifest["untracked_paths"],
                         ["untracked_output.json"])
        self.assertEqual(self.manifest["untracked_path_count"], 1)

    def test_the_untracked_file_is_not_counted_as_a_modified_tracked_file(self):
        """This is the assertion the ambient-state version could not make."""
        self.assertNotIn("untracked_output.json",
                         [x["path"] for x in self.manifest["modified_tracked_files"]])
        self.assertNotIn("??",
                         {x["status"] for x in self.manifest["modified_tracked_files"]})

    def test_a_changed_module_its_test_imports_is_not_reported_uncovered(self):
        text = " ".join((self.out / "CHANGE_TO_TEST_MAP.md").read_text().split())
        self.assertIn("Every source file changed since the reviewed revision",
                      text)

    def test_a_changed_module_no_test_imports_is_reported(self):
        (self.repo / "pkg" / "lonely.py").write_text("Y = 1\n", encoding="utf-8")
        for args in (["add", "-A"], ["commit", "-qm", "add lonely"]):
            subprocess.run(["git", "-C", str(self.repo), *args],
                           check=True, capture_output=True)
        out2 = self.out.parent / "out2"
        tool.main(["--repo", str(self.repo), "--since", self.base,
                   "--test-dir", "tests", "--out", str(out2)])
        raw = (out2 / "CHANGE_TO_TEST_MAP.md").read_text()
        text = " ".join(raw.split())
        self.assertIn("NO TEST IMPORTS THIS", text)

        # The per-commit listing marks it, and so must the summary section at
        # the end. Asserting only on the whole document passed when the summary
        # was emptied, because the per-commit line is produced separately: the
        # summary is what a reader skips to, so it is what must be asserted.
        head, _, summary = raw.partition(
            "## Changed source files no test imports")
        summary = " ".join(summary.split())
        self.assertIn("pkg/lonely.py", summary)
        self.assertNotIn("None. Every source file changed", summary)


if __name__ == "__main__":
    unittest.main()
