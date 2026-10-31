"""The package builder must refuse what it cannot establish."""
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import build_evidence_package as tool


def product(pid, when="2026-10-28T08:00:43.368Z"):
    return {"productId": pid, "productPageURI": f"/p/x/{pid}?cid=TRACK",
            "items": [{"price": {"regular": 1.5, "effectiveDate": {"value": when}}}]}


def page(observed, ids, total=943, when="2026-10-28T08:00:43.368Z"):
    return json.dumps({"locationId": "53100508", "observed_at": observed, "response": {
        "data": [product(i, when) for i in ids],
        "meta": {"pagination": {"total": total}}}})


def write_folder(folder, files):
    folder.mkdir(parents=True)
    for name, text in files.items():
        target = folder / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    declared = {n: hashlib.sha256((folder / n).read_bytes()).hexdigest() for n in files}
    (folder / "MANIFEST_SHA256.json").write_text(json.dumps(declared), encoding="utf-8")


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.azure_files = {
            tool.CHECKPOINT: page("2026-10-28T09:20:49.774598+00:00", ["a", "b"]),
            tool.FRESH_PAGE: page("2026-10-28T12:07:39.195016+00:00", ["b", "a"], 940,
                                  "2026-10-28T10:26:40.289Z"),
            "EARLIER_SELECTED_5.json": "[1]", "FRESH_SELECTED_5.json": "[1]",
            "RESTORED_OVERVIEW.png": "image", "RESULTS.md": "see STATUS.json"}
        self.azure_files["STATUS.json"] = json.dumps({"checkpoint_sha256": hashlib.sha256(
            self.azure_files[tool.CHECKPOINT].encode()).hexdigest()})
        self.blocked = {"url": "https://www.marianos.com/p/x/0003?fulfillment=PICKUP",
                        "last_successful_product_count": 1, "remaining_discovered_urls": 2}
        self.battery_files = {
            "BLOCKED_SOURCE.json": json.dumps(self.blocked), "LISTING_03.txt": "listing",
            "PENDING_61_URLS.json": json.dumps(["/p/x/0003"]),
            "products/0001.json": "{}", "products/0002.json": "{}",
            "PROVENANCE_34_V2.json": json.dumps([{"weight_reference": "LISTING_03.txt"}])}
        self.fixture = {"retained_output_upcs": ["1"], "coupon_source_upc": "2",
                        "expiry_discrepancy_resolved": False}
        self.notes = {name: "# note" for name in tool.NOTES}

    def build(self):
        azure, batteries = self.base / "a", self.base / "b"
        notes = self.base / "n"
        write_folder(azure, self.azure_files)
        write_folder(batteries, self.battery_files)
        notes.mkdir()
        for name, text in self.notes.items():
            (notes / name).write_text(text, encoding="utf-8")
        fixture = self.base / "IDENTITY_FIXTURE.json"
        fixture.write_text(json.dumps(self.fixture), encoding="utf-8")
        self.output = self.base / "out"
        self.sources = (azure, batteries)
        return tool.build(azure, batteries, fixture, notes, self.output)


class BuildTests(Base):
    def test_every_file_is_listed_with_a_hash_that_matches(self):
        manifest = self.build()
        on_disk = {p.relative_to(self.output).as_posix() for p in self.output.rglob("*")
                   if p.is_file()} - {"MANIFEST_SHA256.json"}
        self.assertEqual({e["path"] for e in manifest["entries"]}, on_disk)
        self.assertEqual(manifest["files"], len(on_disk))
        for entry in manifest["entries"]:
            self.assertEqual(tool.sha256(self.output / entry["path"]), entry["sha256"])

    def test_originals_are_copied_byte_for_byte_and_their_manifests_still_hold(self):
        self.build()
        for name in ("azure_recovery", "batteries_reference"):
            self.assertEqual(len(tool.verify_folder(self.output / name)) > 0, True)
        self.assertEqual((self.output / "azure_recovery" / tool.CHECKPOINT).read_text(),
                         self.azure_files[tool.CHECKPOINT])

    def test_the_equal_size_is_explained_not_called_a_coincidence(self):
        pages = self.build()["statements_recomputed_from_the_bytes"]["page_files"]
        self.assertEqual(pages["same_size_bytes"], len(self.azure_files[tool.CHECKPOINT]))
        self.assertFalse(pages["bytes_identical"])
        self.assertTrue(pages["same_product_set"])
        self.assertFalse(pages["same_product_order"])
        self.assertTrue(pages["every_changed_value_keeps_its_width"])
        self.assertEqual(pages["changed_values_by_field"],
                         {"/items[]/price/effectiveDate/value": 2, "/pagination/total": 1})

    def test_handling_flags_are_recorded_beside_the_file(self):
        entries = {e["path"]: e for e in self.build()["entries"]}
        self.assertEqual(entries[f"azure_recovery/{tool.CHECKPOINT}"]["cid_parameters"], 2)
        self.assertTrue(entries["azure_recovery/RESTORED_OVERVIEW.png"]["shows_account_identity"])
        self.assertNotIn("cid_parameters", entries["azure_recovery/STATUS.json"])
        self.assertNotIn("shows_account_identity", entries["azure_recovery/STATUS.json"])

    def test_superseded_and_derived_files_are_labelled(self):
        entries = {e["path"]: e for e in self.build()["entries"]}
        self.assertIn("superseded", entries["azure_recovery/RESULTS.md"]["status"])
        self.assertIn("derived", entries["azure_recovery/FRESH_SELECTED_5.json"]["status"])
        self.assertEqual(entries["RESULTS.md"]["status"], "current")
        self.assertEqual(entries["RESULTS.md"]["origin"], "written 2026-10-31")
        self.assertEqual(entries["azure_recovery/STATUS.json"]["origin"], "original, unchanged")

    def test_the_batteries_counts_are_reconciled(self):
        facts = self.build()["statements_recomputed_from_the_bytes"]["batteries"]
        self.assertEqual((facts["products_captured"], facts["urls_pending"]), (2, 1))
        self.assertEqual((facts["refusal_record_products"], facts["refusal_record_remaining"]),
                         (1, 2))
        self.assertEqual(facts["sizes_recovered_from_listing_03"], 1)

    def test_a_non_empty_output_is_refused(self):
        self.base.joinpath("out").mkdir()
        self.base.joinpath("out", "old").write_text("x")
        with self.assertRaisesRegex(tool.PackageRefused, "not empty"):
            self.build()


class RefusalTests(Base):
    def refused(self, pattern):
        with self.assertRaisesRegex(tool.PackageRefused, pattern):
            self.build()

    def test_a_changed_original_is_refused(self):
        original = tool.verify_folder

        def tamper(folder):
            (folder / "RESULTS.md").write_text("edited") if folder.name == "a" else None
            return original(folder)

        tool.verify_folder = tamper
        self.addCleanup(setattr, tool, "verify_folder", original)
        self.refused("does not match its manifest hash")

    def test_a_file_the_manifest_does_not_list_is_refused(self):
        original = tool.verify_folder

        def add(folder):
            (folder / "EXTRA.txt").write_text("x")
            return original(folder)

        tool.verify_folder = add
        self.addCleanup(setattr, tool, "verify_folder", original)
        self.refused("manifest and files disagree")

    def test_a_checkpoint_that_does_not_match_status_is_refused(self):
        self.azure_files["STATUS.json"] = json.dumps({"checkpoint_sha256": "0" * 64})
        self.refused("does not match the hash in STATUS")

    def test_identical_pages_are_not_two_observations(self):
        self.azure_files[tool.FRESH_PAGE] = self.azure_files[tool.CHECKPOINT]
        self.refused("not independent")

    def test_the_same_observed_at_is_not_two_observations(self):
        self.azure_files[tool.FRESH_PAGE] = page("2026-10-28T09:20:49.774598+00:00",
                                                 ["b", "a"])
        self.refused("not independent")

    def test_equal_size_with_different_products_is_refused(self):
        self.azure_files[tool.FRESH_PAGE] = page("2026-10-28T12:07:39.195016+00:00",
                                                 ["c", "a"], 940)
        self.refused("not explained")

    def test_selected_files_that_differ_are_refused(self):
        self.azure_files["FRESH_SELECTED_5.json"] = "[2]"
        self.refused("no longer byte-identical")

    def test_counts_covering_different_urls_are_refused(self):
        self.battery_files["BLOCKED_SOURCE.json"] = json.dumps(
            {**self.blocked, "remaining_discovered_urls": 3})
        self.refused("different URLs")

    def test_a_blocked_product_missing_from_pending_is_refused(self):
        self.battery_files["PENDING_61_URLS.json"] = json.dumps(["/p/x/0009"])
        self.refused("not among the pending")

    def test_a_resolved_expiry_is_refused(self):
        self.fixture["expiry_discrepancy_resolved"] = True
        self.refused("must stay unresolved")

    def test_an_absent_expiry_flag_is_refused(self):
        del self.fixture["expiry_discrepancy_resolved"]
        self.refused("must stay unresolved")

    def test_a_coupon_source_relabelled_as_retained_is_refused(self):
        self.fixture["retained_output_upcs"] = ["2"]
        self.refused("must not be a retained")

    def test_a_reference_to_an_absent_file_is_refused(self):
        self.notes["RESULTS.md"] = "see LISTING_09.txt"
        self.refused("LISTING_09.txt")

    def test_a_reference_in_an_original_is_refused_too(self):
        self.azure_files["RESULTS.md"] = "see FRESH_PAGE_MISSING.json"
        self.refused("FRESH_PAGE_MISSING.json")

    def test_a_present_file_and_a_web_address_are_not_absences(self):
        self.notes["RESULTS.md"] = "see LISTING_03.txt at www.marianos.com/logo.png"
        self.build()


if __name__ == "__main__":
    unittest.main()
