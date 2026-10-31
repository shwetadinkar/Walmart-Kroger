"""The package builder must refuse what it cannot establish."""
import hashlib
import json
import shutil
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
        self.sample = [{"upc": "0009", "store_name": "Marianos West Loop", "weight": "1 ct",
                        "digital_deals_description": "a\n\nb", "digital_deals_price": ""},
                       {"upc": "0008", "store_name": "Marianos West Loop", "weight": "2 ct",
                        "digital_deals_description": "", "digital_deals_price": ""}]
        self.batteries_v2 = [{"upc": "0009", "store_name": "Marianos West Loop", "weight": "1 ct",
                              "digital_deals_description": "a\nb", "digital_deals_price": ""}]
        self.coupon_files = {"COUPON.png": "drawer"}
        self.complete_notes = True
        self.withhold = ["RESTORED_OVERVIEW.png"]
        self.denied = "# synthetic\nowner@example.test\nacme utilities\n0000aaaa-1111\n"

    def build(self):
        azure, batteries, coupon = self.base / "a", self.base / "b", self.base / "c"
        notes = self.base / "n"
        write_folder(azure, self.azure_files)
        write_folder(batteries, {**self.battery_files, "PRODUCTS_34_PARTIAL_V2.json":
                                 json.dumps(self.batteries_v2)})
        write_folder(coupon, {**self.coupon_files, tool.COUPON_SAMPLE: json.dumps(self.sample)})
        notes.mkdir()
        for name, text in self.notes.items():
            (notes / name).write_text(text, encoding="utf-8")
        fixture = self.base / "IDENTITY_FIXTURE.json"
        fixture.write_text(json.dumps(self.fixture), encoding="utf-8")
        self.output = self.base / "out"
        self.sources = (azure, batteries)
        facts = tool.recompute(azure, batteries, coupon, fixture) if self.complete_notes else None
        for name, text in self.notes.items():
            extra = tool.note_requirements(facts).get(name, []) if facts else []
            (notes / name).write_text(text + "\n" + "\n".join(extra), encoding="utf-8")
        self.denylist = self.base / "denylist.txt"
        self.denylist.write_text(self.denied, encoding="utf-8")
        return tool.build(azure, batteries, coupon, fixture, notes, self.output,
                          self.denylist, self.withhold)


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
        self.assertEqual(len(tool.verify_folder(self.output / "batteries_reference")),
                         len(self.battery_files) + 2)
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
        self.assertNotIn("cid_parameters", entries["azure_recovery/STATUS.json"])

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


class CouponTests(Base):
    def test_the_folder_is_included_with_its_manifest(self):
        self.build()
        self.assertEqual(len(tool.verify_folder(self.output / "coupon_source")), 3)

    def test_a_coupon_screenshot_with_identity_strings_is_refused_until_withheld(self):
        self.coupon_files["COUPON.png"] = "owner@example.test"
        with self.assertRaisesRegex(tool.PackageRefused, "COUPON.png"):
            self.build()
        shutil.rmtree(self.base / "a"), shutil.rmtree(self.base / "b")
        shutil.rmtree(self.base / "c"), shutil.rmtree(self.base / "n")
        self.withhold.append("COUPON.png")
        manifest = self.build()
        self.assertIn("coupon_source/COUPON.png", [w["path"] for w in manifest["withheld"]])
        self.assertFalse((self.output / "coupon_source/COUPON.png").exists())

    def test_a_disagreement_with_the_batteries_set_is_recorded_not_resolved(self):
        facts = self.build()["statements_recomputed_from_the_bytes"]["coupon"]
        self.assertEqual(facts["shared_with_batteries"], ["0009"])
        self.assertEqual(facts["field_disagreements"], [
            {"upc": "0009", "field": "digital_deals_description", "whitespace_only": True}])

    def test_a_real_disagreement_is_not_called_whitespace(self):
        self.batteries_v2[0]["digital_deals_description"] = "a c"
        facts = self.build()["statements_recomputed_from_the_bytes"]["coupon"]
        self.assertFalse(facts["field_disagreements"][0]["whitespace_only"])

    def test_a_note_calling_a_real_disagreement_whitespace_is_refused(self):
        """It happened: the sentence required only the words before the claim, so
        a false "in whitespace only" passed on the real data."""
        self.batteries_v2[0]["digital_deals_description"] = "a c"
        self.build()
        path = self.output / "C2_COUPON_SOURCE.md"
        path.write_text(path.read_text().replace("beyond whitespace", "in whitespace only"))
        with self.assertRaisesRegex(tool.PackageRefused, "beyond whitespace"):
            tool.check_notes(self.output, tool.recompute(
                self.output / "azure_recovery", self.output / "batteries_reference",
                self.output / "coupon_source",
                self.output / "promotion_correction/IDENTITY_FIXTURE.json"))

    def test_a_sample_at_another_store_is_refused(self):
        self.sample[1]["store_name"] = "Marianos Vernon Hills"
        with self.assertRaisesRegex(tool.PackageRefused, "West Loop"):
            self.build()

    def test_an_empty_sample_is_refused(self):
        self.sample = []
        with self.assertRaisesRegex(tool.PackageRefused, "West Loop"):
            self.build()

    def test_a_digital_price_in_the_sample_is_refused(self):
        self.sample[0]["digital_deals_price"] = "4.99"
        with self.assertRaisesRegex(tool.PackageRefused, "nobody displayed"):
            self.build()


class WithholdingTests(Base):
    def test_a_withheld_file_is_left_out_and_declared_with_its_hash(self):
        manifest = self.build()
        self.assertFalse((self.output / "azure_recovery/RESTORED_OVERVIEW.png").exists())
        self.assertNotIn("azure_recovery/RESTORED_OVERVIEW.png",
                         {e["path"] for e in manifest["entries"]})
        held = manifest["withheld"][0]
        self.assertEqual(held["path"], "azure_recovery/RESTORED_OVERVIEW.png")
        self.assertEqual(held["sha256"], hashlib.sha256(b"image").hexdigest())
        self.assertEqual(held["bytes"], 5)
        self.assertIn("account-identifying", held["reason"])

    def test_the_transcription_stays(self):
        self.azure_files["RESTORED_OVERVIEW_UI.txt"] = "Replica timeout 600"
        self.build()
        self.assertTrue((self.output / "azure_recovery/RESTORED_OVERVIEW_UI.txt").exists())

    def test_a_known_account_screenshot_cannot_be_included(self):
        self.withhold = []
        with self.assertRaisesRegex(tool.PackageRefused, "Must be withheld"):
            self.build()

    def test_withholding_a_file_that_does_not_exist_is_refused(self):
        self.withhold.append("NOT_THERE.png")
        with self.assertRaisesRegex(tool.PackageRefused, "do not exist"):
            self.build()

    def test_the_old_manifest_may_name_a_withheld_file_and_nothing_else_may(self):
        self.build()
        self.assertEqual(tool.absent_references(self.output, ["azure_recovery/RESTORED_OVERVIEW.png"]), {})
        (self.output / "RESULTS.md").write_text("see RESTORED_OVERVIEW.png")
        self.assertEqual(tool.absent_references(self.output, ["azure_recovery/RESTORED_OVERVIEW.png"]),
                         {"RESULTS.md": ["RESTORED_OVERVIEW.png"]})


class IdentityTests(Base):
    def refused(self, *names):
        with self.assertRaises(tool.PackageRefused) as caught:
            self.build()
        self.assertIn("identity strings", str(caught.exception))
        for name in names:
            self.assertIn(name, str(caught.exception))
        self.assertFalse(self.output.exists(), "a refusal must leave no copy behind")

    def test_each_identity_string_is_refused_in_an_original(self):
        for text in ("owner@example.test", "ACME Utilities Ltd", "/sub/0000AAAA-1111/x"):
            self.setUp()
            self.azure_files["RESTORED_CONTAINER_UI.txt"] = text
            self.refused("RESTORED_CONTAINER_UI.txt")

    def test_url_encoding_does_not_hide_it(self):
        self.azure_files["RESTORED_OVERVIEW_UI.txt"] = "subs%2Fowner%40example.test%2Fx"
        self.refused("RESTORED_OVERVIEW_UI.txt")

    def test_case_does_not_hide_it(self):
        self.azure_files["RESTORED_OVERVIEW_UI.txt"] = "OWNER@EXAMPLE.TEST"
        self.refused("RESTORED_OVERVIEW_UI.txt")

    def test_utf_16_does_not_hide_it(self):
        self.azure_files["NOTE.txt"] = "".join(c + "\x00" for c in "owner@example.test")
        self.refused("NOTE.txt")

    def test_a_batteries_file_is_scanned(self):
        self.battery_files["LISTING_03.txt"] = "acme utilities"
        self.refused("LISTING_03.txt")

    def test_a_note_is_scanned(self):
        self.notes["README.md"] = "Prepared at Acme Utilities"
        self.refused("README.md")

    def test_the_fixture_is_scanned(self):
        self.fixture["operator"] = "owner@example.test"
        self.refused("IDENTITY_FIXTURE.json")

    def test_a_withheld_file_is_not_a_hit(self):
        self.azure_files["RESTORED_OVERVIEW.png"] = "owner@example.test"
        self.build()
        self.assertTrue((self.output / "RESULTS.md").exists())

    def test_an_empty_denylist_is_refused_rather_than_passing_everything(self):
        self.denied = "# only a comment\n\n"
        with self.assertRaisesRegex(tool.PackageRefused, "deny-list is empty"):
            self.build()


class NoteTests(Base):
    def test_a_note_that_does_not_state_a_recomputed_value_is_refused(self):
        self.complete_notes = False
        with self.assertRaisesRegex(tool.PackageRefused, "does not state"):
            self.build()

    def test_a_wrong_value_in_a_note_is_refused(self):
        self.build()
        path = self.output / "C4_BLOCKED_SOURCE_CHRONOLOGY.md"
        path.write_text(path.read_text().replace("1 successful products", "9 successful products"))
        with self.assertRaisesRegex(tool.PackageRefused, "does not state"):
            tool.check_notes(self.output, tool.recompute(
                self.output / "azure_recovery", self.output / "batteries_reference",
                self.output / "coupon_source",
                self.output / "promotion_correction/IDENTITY_FIXTURE.json"))

    def test_the_requirements_come_from_the_bytes(self):
        self.azure_files[tool.CHECKPOINT] = self.azure_files[tool.CHECKPOINT].replace("943", "944")
        self.azure_files["STATUS.json"] = json.dumps({"checkpoint_sha256": hashlib.sha256(
            self.azure_files[tool.CHECKPOINT].encode()).hexdigest()})
        self.build()
        self.assertIn("(944, then 940)", (self.output / "RESULTS.md").read_text())


class VerifyTests(Base):
    def setUp(self):
        super().setUp()
        self.azure_files["RESTORED_OVERVIEW.png"] = "image"

    def test_a_good_package_verifies(self):
        self.build()
        result = tool.verify(self.output, self.denylist)
        self.assertEqual(result["withheld"], 1)
        self.assertGreater(result["files_verified"], 10)
        self.assertEqual(result["statements"]["page_files"]["products"], 2)

    def broken(self, change, pattern):
        self.build()
        change()
        with self.assertRaisesRegex(tool.PackageRefused, pattern):
            tool.verify(self.output, self.denylist)

    def test_an_altered_file_fails(self):
        self.broken(lambda: (self.output / "azure_recovery/RESULTS.md").write_text("x"),
                    "does not match the manifest")

    def test_an_extra_file_fails(self):
        self.broken(lambda: (self.output / "EXTRA.txt").write_text("x"), "disagree")

    def test_a_missing_file_fails(self):
        self.broken(lambda: (self.output / "README.md").unlink(), "disagree")

    def test_a_restored_screenshot_fails(self):
        def restore():
            path = self.output / "azure_recovery/RESTORED_OVERVIEW.png"
            path.write_text("image")
            self.rewrite_manifest(lambda m: m["entries"].append(
                {"path": "azure_recovery/RESTORED_OVERVIEW.png", "bytes": 5,
                 "sha256": hashlib.sha256(b"image").hexdigest()}))
        self.broken(restore, "withheld file is present")

    def test_a_statement_edited_in_the_manifest_fails(self):
        self.broken(lambda: self.rewrite_manifest(
            lambda m: m["statements_recomputed_from_the_bytes"]["batteries"].update(
                products_captured=99)), "do not recompute")

    def test_an_identity_string_in_the_manifest_fails(self):
        self.broken(lambda: self.rewrite_manifest(lambda m: m.update(owner="owner@example.test")),
                    "identity strings")

    def alter(self, name, text):
        """Change a file and keep the root manifest consistent, so that the
        check under test is the one that has to notice."""
        path = self.output / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        entry = {"path": name, "bytes": path.stat().st_size, "sha256": tool.sha256(path)}

        def apply(manifest):
            manifest["entries"] = [e for e in manifest["entries"] if e["path"] != name]
            manifest["entries"].append(entry)
        self.rewrite_manifest(apply)

    def test_a_stated_size_that_is_wrong_fails(self):
        def wrong(manifest):
            manifest["entries"][0]["bytes"] += 1
        self.broken(lambda: self.rewrite_manifest(wrong), "not the size")

    def test_a_note_that_stops_stating_a_value_fails(self):
        self.broken(lambda: self.alter("RESULTS.md", "# nothing stated"), "does not state")

    def test_an_original_changed_from_its_28_october_hash_fails(self):
        self.broken(lambda: self.alter("azure_recovery/RESULTS.md", "edited"),
                    "28 October hash")

    def test_a_coupon_original_changed_from_its_28_october_hash_fails(self):
        self.broken(lambda: self.alter("coupon_source/COUPON.png", "edited"), "28 October hash")

    def test_a_coupon_note_that_stops_naming_a_sample_product_fails(self):
        def drop():
            text = (self.output / "C2_COUPON_SOURCE.md").read_text()
            self.alter("C2_COUPON_SOURCE.md", text.replace("0008", "gone"))
        self.broken(drop, "does not state")

    def test_a_known_account_screenshot_under_another_folder_fails(self):
        self.broken(lambda: self.alter("batteries_reference/RESTORED_CONTAINER.png", "x"),
                    "showing an account")

    def test_a_reference_added_after_the_build_fails(self):
        def add():
            text = (self.output / "C0_PROMOTION_IDENTITY.md").read_text()
            self.alter("C0_PROMOTION_IDENTITY.md", text + "\nsee NOT_HERE.json")
        self.broken(add, "NOT_HERE.json")

    def rewrite_manifest(self, change):
        path = self.output / "MANIFEST_SHA256.json"
        manifest = json.loads(path.read_text())
        change(manifest)
        path.write_text(json.dumps(manifest))


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
