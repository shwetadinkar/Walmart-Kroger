"""The Vernon Hills package: every stated fact is recomputed, or the build refuses."""
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import build_vernon_hills_package as tool
from build_evidence_package import PackageRefused

RAW_CID = "cid=abc123private"
DENIED = "someone.private"


def row(upc, category="Dairy", **changes):
    base = dict.fromkeys(tool.FIELDS, "")
    base.update(zipcode=tool.ZIPCODE, store_name=tool.STORE_NAME, store_location=tool.STORE_LOCATION,
                store_brand="no", category=category, sub_category=category, product_title="T",
                weight="1 oz", regular_price="2.50", upc=upc, crawl_date="2026-10-31",
                url=f"https://www.marianos.com/p/x/{upc}")
    base.update(changes)
    return base


def product(upc):
    return {"productId": upc, "upc": upc, "productPageURI": f"/p/x/{upc}?{RAW_CID}",
            "items": [{"price": {"regular": 2.5, "promo": 0}}]}


class Spine:
    """A small spine with one term of every kind the sample rule treats apart."""

    def __init__(self, root):
        self.root = pathlib.Path(root)
        self.spine = self.root / "spine"
        (self.spine / "raw").mkdir(parents=True)
        self.rows, self.context, self.discovery = [], {}, {}
        self.index_pages = []
        self.number = 0
        # At the limit: five full pages, Kroger reporting more.
        for page in range(5):
            self.page("Dairy", "milk", 1 + page * 50, 50, 900, "Dairy")
        # Ended short of the reported total.
        self.page("Produce", "apple", 1, 47, 309, "Produce")
        # One short: what filter.start=1 appears to skip.
        self.page("Frozen", "peas", 1, 6, 7, "Frozen")
        # No result.
        self.page("Coffee", "beans", 1, 0, 0, "")
        for root_name in tool.EMPTY_ROOTS:
            if root_name != "Coffee":
                self.page(root_name, "nothing", 1, 0, 0, "")
        for item in self.discovery.values():
            item["api_categories"].append(tool.SEAFOOD_LABEL)
        self.report = self.make_report()
        self.write()

    def page(self, root, term, start, count, total, category):
        products = []
        for _ in range(count):
            self.number += 1
            upc = f"{self.number:013d}"
            products.append(product(upc))
            self.rows.append(row(upc, category))
            identity = f"{tool.STORE_ID}:product:{upc}"
            file = f"{root}-{term}/start_{start:04d}.json".replace(" ", "-")
            self.context[identity] = {"product_id": upc, "raw_file": file}
            self.discovery[identity] = {"term_root": root, "assigned_root": category,
                                        "api_categories": [category]}
        path = self.spine / "raw" / f"{root}-{term}".replace(" ", "-") / f"start_{start:04d}.json"
        path.parent.mkdir(exist_ok=True)
        path.write_text(json.dumps({
            "locationId": tool.STORE_ID, "term": term, "term_root": root, "start": start,
            "observed_at": f"2026-10-31T14:{self.number % 60:02d}:00+00:00",
            "response": {"data": products, "meta": {"pagination": {"total": total}}}}))

    def make_report(self):
        counts = {}
        for r in self.rows:
            counts[r["category"]] = counts.get(r["category"], 0) + 1
        return {"locationId": tool.STORE_ID, "elapsed_seconds": 100.0,
                "requests_spent": len(list((self.spine / "raw").rglob("*.json"))),
                "unique_products": len(self.rows), "unique_upcs": len(self.rows),
                "terms_that_hit_the_start_cap": ["Dairy||milk"], "terms_completed": 8,
                "categories_with_zero_products": list(tool.EMPTY_ROOTS),
                "count_by_category": dict(sorted(counts.items())),
                "field_completeness": {f: sum(bool(r[f]) for r in self.rows) for f in tool.FIELDS},
                "page_failures": [], "stopped_reason": None,
                "offer_status": {"qualifying_pickup_offer": len(self.rows)},
                "acceptable_use_decision": "Kroger " + tool.ACCEPTABLE_USE + " known."}

    def write(self):
        put = lambda name, value: (self.spine / name).write_text(json.dumps(value))
        put("data_22_fields.json", self.rows)
        put("run_report.json", self.report)
        put("store_verification.json", {
            "locationId": tool.STORE_ID, "verified_utc": "2026-10-31T14:00:00+00:00",
            "resolved": {"zipcode": tool.ZIPCODE, "store_name": tool.STORE_NAME,
                         "store_location": tool.STORE_LOCATION},
            "response": {"data": {"locationId": tool.STORE_ID}}})
        put("pickup_context.json", self.context)
        put("discovery_provenance.json", self.discovery)
        put("category_disagreements.json", [])
        put("unmapped_categories.json", {})
        put("quarantine.json", {})
        put("retention.json", {})
        put("checkpoint.json", {})
        self.log = self.root / "run.log"
        self.log.write_text("log\n")
        self.deny = self.root / "deny.txt"
        self.deny.write_text(DENIED + "\n")
        self.notes()

    def facts(self):
        index = tool.index_raw(self.spine / "raw")
        seed = tool.sha256(self.spine / "data_22_fields.json")
        sample = tool.choose_sample(index, seed)
        pages = {n: json.loads(tool.CID.sub(tool.MASK, (self.spine / "raw" / n).read_bytes()))
                 for n in sample}
        return tool.recompute(self.spine, index, pages, ROOT)

    def notes(self):
        self.note_dir = self.root / "notes"
        self.note_dir.mkdir(exist_ok=True)
        required = tool.note_requirements(self.facts())
        for name in tool.NOTES:
            (self.note_dir / name).write_text("\n".join(required.get(name, ["note"])) + "\n")

    def build(self, name="package"):
        self.output = self.root / name
        return tool.build(self.spine, self.log, self.note_dir, ROOT, self.output, self.deny)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.s = Spine(self.tmp.name)

    def refused(self, text, call=None):
        with self.assertRaises(PackageRefused) as caught:
            (call or self.s.build)()
        self.assertIn(text, str(caught.exception))

    def edit(self, name, change):
        path = self.s.spine / name
        value = json.loads(path.read_text())
        change(value)
        path.write_text(json.dumps(value))


class Facts(Base):
    def test_truncation_is_read_from_the_captures(self):
        found = tool.truncation(tool.index_raw(self.s.spine / "raw"))
        self.assertEqual(found["limited"], ["Dairy||milk"])
        self.assertEqual(found["short"], [{"term": "Produce||apple", "reported_total": 309,
                                           "received": 47}])
        self.assertEqual(found["exactly_one_short"], 1)
        self.assertEqual(found["with_results_below_limit"], 2)
        self.assertEqual(len(found["zero_result_terms"]), 5)

    def test_duplicates_are_recomputed_from_the_rows(self):
        self.assertEqual(self.s.facts()["duplicate_upcs"], 0)
        rows = [row("1"), row("1"), row("2"), row(""), row("")]
        self.assertEqual(tool.duplicate_upcs(rows), 1)
        self.assertEqual(tool.duplicate_upcs(rows[2:]), 0)

    def test_placements_collapsed_counts_repeats(self):
        self.assertEqual(self.s.facts()["placements_returned"], self.s.facts()["records"])
        path = self.s.spine / "raw/Produce-apple/start_0001.json"
        page = json.loads(path.read_text())
        page["response"]["data"].append(page["response"]["data"][0])
        path.write_text(json.dumps(page))
        self.assertEqual(self.s.facts()["duplicate_placements_collapsed"], 1)

    def test_completeness_covers_all_22_fields(self):
        facts = self.s.facts()
        self.assertEqual(list(facts["field_completeness"]), list(tool.FIELDS))
        self.assertEqual(facts["field_completeness"]["upc"], facts["records"])
        self.assertEqual(facts["field_completeness"]["ppm"], 0)

    def test_cost_follows_the_measured_run(self):
        cost = self.s.facts()["cost"]
        self.assertEqual(cost["runs_per_month"], 8.67)
        self.assertEqual(cost["vcpu_seconds_per_month"], 433)
        self.assertEqual(cost["gib_seconds_per_month"], 867)


class Sample(Base):
    def chosen(self, seed="a"):
        return tool.choose_sample(tool.index_raw(self.s.spine / "raw"), seed)

    def test_the_rule_takes_every_kind_of_page(self):
        reasons = " ".join(x for why in self.chosen().values() for x in why)
        chosen = self.chosen()
        self.assertEqual(sum("Dairy-milk" in path for path in chosen), 5)
        self.assertIn("Produce-apple/start_0001.json", chosen)
        self.assertIn("Coffee-beans/start_0001.json", chosen)
        self.assertIn("first page, root Frozen", reasons)
        self.assertIn("a term with no result", reasons)
        self.assertIn("every page of a term ending short of its reported total",
                      chosen["Produce-apple/start_0001.json"])

    def test_seeded_audit_varies_with_the_seed_and_repeats_with_it(self):
        index = [{"path": f"Z-t{n}/start_0001.json", "term_root": "Z", "term": f"t{n}", "start": 1,
                  "returned": 3, "reported_total": 4, "bytes": 1} for n in range(200)]
        first = tool.choose_sample(index, "a")
        self.assertEqual(first, tool.choose_sample(index, "a"))
        self.assertNotEqual(set(first), set(tool.choose_sample(index, "b")))
        self.assertEqual(len(first), 1 + tool.AUDIT_PAGES)

    def test_limited_terms_in_full_come_from_different_roots(self):
        index = [{"path": f"{root}-t{n}/start_{start:04d}.json", "term_root": root, "term": f"t{n}",
                  "start": start, "returned": 50, "reported_total": 900, "bytes": 1}
                 for root in "ABCD" for n in range(2) for start in (1, 51, 101, 151, 201)]
        chosen = tool.choose_sample(index, "a")
        full = [p for p, why in chosen.items() if "every page of a term stopped at the limit" in why]
        self.assertEqual(len(full), tool.TRUNCATED_TERMS_IN_FULL * 5)
        self.assertEqual(len({p[0] for p in full}), tool.TRUNCATED_TERMS_IN_FULL)


class Build(Base):
    def test_round_trip_verifies_from_the_package_alone(self):
        self.s.build()
        result = tool.verify(self.s.output, self.s.deny)
        self.assertEqual(result["identity_scan"], "clean")
        self.assertEqual(result["records"], len(self.s.rows))

    def test_standalone_with_nothing_but_the_folder(self):
        self.s.build()
        copy = pathlib.Path(self.tmp.name) / "elsewhere" / "pkg"
        shutil.copytree(self.s.output, copy)
        for _ in range(2):  # a second run proves the first left nothing behind
            done = subprocess.run(
                [sys.executable, "-I", "tools/build_vernon_hills_package.py", "--verify", "."],
                cwd=copy, capture_output=True, text=True)
            self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("not run", done.stdout)

    def test_the_whole_raw_folder_does_not_ship(self):
        index = tool.index_raw(self.s.spine / "raw")
        for start in range(1, 41):
            self.s.page("Grocery", f"term{start}", 1, 1, 2, "Grocery")
        self.s.report = self.s.make_report()
        self.s.report["terms_completed"] = 48
        self.s.write()
        manifest = self.s.build()
        shipped = list((self.s.output / "raw_sample").rglob("*.json"))
        total = len(tool.index_raw(self.s.spine / "raw"))
        self.assertLess(len(shipped), total)
        left = [item for item in manifest["left_out"] if item["path"] == "raw/"][0]
        self.assertEqual(left["files"], total - len(shipped))
        self.assertGreater(total, len(index))
        self.assertEqual(len(json.loads((self.s.output / "raw_index.json").read_text())), total)

    def test_cid_is_masked_and_the_original_hash_kept(self):
        manifest = self.s.build()
        name = "Produce-apple/start_0001.json"
        shipped = (self.s.output / "raw_sample" / name).read_bytes()
        self.assertNotIn(b"abc123private", shipped)
        self.assertIn(b"cid=MASKED", shipped)
        entry = [e for e in manifest["entries"] if e["path"] == "raw_sample/" + name][0]
        self.assertEqual(entry["original_sha256"], tool.sha256(self.s.spine / "raw" / name))
        self.assertNotEqual(entry["sha256"], entry["original_sha256"])

    def test_left_out_files_are_declared_and_absent(self):
        manifest = self.s.build()
        names = {item["path"] for item in manifest["left_out"]}
        self.assertEqual(names, {"retention.json", "checkpoint.json", "raw/"})
        self.assertFalse((self.s.output / "data/retention.json").exists())

    def test_output_must_be_empty(self):
        self.s.output = pathlib.Path(self.tmp.name) / "package"
        self.s.output.mkdir()
        (self.s.output / "x").write_text("x")
        self.refused("is not empty")

    def test_identity_in_a_shipped_file_refuses_and_writes_nothing(self):
        self.edit("run_report.json", lambda r: r.update(operator=DENIED))
        self.refused("identity strings")
        self.assertFalse((pathlib.Path(self.tmp.name) / "package").exists())

    def test_identity_in_a_sampled_page_refuses(self):
        path = self.s.spine / "raw/Produce-apple/start_0001.json"
        path.write_text(path.read_text().replace('"term":', f'"x": "{DENIED}", "term":'))
        self.s.notes()
        self.refused("identity string")

    def test_unmasked_cid_in_a_data_file_refuses(self):
        self.edit("quarantine.json", lambda q: q.update(u="/p/x/1?cid=abc"))
        self.refused("unmasked cid")

    def test_empty_denylist_refuses(self):
        self.s.deny.write_text("# nothing\n")
        self.refused("deny-list is empty")

    def test_reference_to_an_absent_file_refuses_and_removes_the_package(self):
        with open(self.s.note_dir / "README.md", "a") as note:
            note.write("See nowhere_at_all.json\n")
        self.refused("absent files")
        self.assertFalse((pathlib.Path(self.tmp.name) / "package").exists())


class Refusals(Base):
    def test_report_disagreeing_with_rows(self):
        self.edit("run_report.json", lambda r: r.update(unique_products=1))
        self.refused("unique_products")

    def test_report_disagreeing_on_limited_terms(self):
        self.edit("run_report.json", lambda r: r.update(terms_that_hit_the_start_cap=[]))
        self.refused("limited terms")

    def test_report_disagreeing_on_requests(self):
        self.edit("run_report.json", lambda r: r.update(requests_spent=1))
        self.refused("disagree on: ['requests']")

    def test_report_disagreeing_on_completeness(self):
        self.edit("run_report.json", lambda r: r["field_completeness"].update(upc=0))
        self.refused("field completeness")

    def test_report_with_a_failed_page(self):
        self.edit("run_report.json", lambda r: r.update(page_failures=[{"term": "x"}]))
        self.refused("failure")

    def test_report_without_the_acceptable_use_statement(self):
        self.edit("run_report.json", lambda r: r.update(acceptable_use_decision="fine"))
        self.refused("acceptable-use")

    def test_row_labelled_as_another_store(self):
        self.edit("data_22_fields.json", lambda rows: rows[0].update(
            store_name="Marianos - Marianos West Loop"))
        self.refused("not labelled Vernon Hills")

    def test_capture_from_another_store(self):
        path = self.s.spine / "raw/Produce-apple/start_0001.json"
        path.write_text(path.read_text().replace(tool.STORE_ID, tool.OTHER_STORE))
        self.refused("another store")

    def test_verification_for_another_store(self):
        self.edit("store_verification.json", lambda v: v.update(locationId=tool.OTHER_STORE))
        self.refused("not for Vernon Hills")

    def test_store_columns_differing_from_verification(self):
        self.edit("store_verification.json", lambda v: v["resolved"].update(store_name="Other"))
        self.refused("differ from the verified store")

    def test_a_value_in_a_field_the_notes_call_blank(self):
        for field in ("ppm", "digital_deals_description", "volume_deals_description", "gupc"):
            with self.subTest(field=field):
                self.edit("data_22_fields.json", lambda rows: rows[0].update({field: "x"}))
                self.refused(field)
                self.edit("data_22_fields.json", lambda rows: rows[0].update({field: ""}))

    def test_fields_out_of_order_or_not_strings(self):
        self.edit("data_22_fields.json", lambda rows: rows[0].pop("gupc"))
        self.refused("22 fields")
        self.edit("data_22_fields.json", lambda rows: rows[0].update(gupc=""))
        self.refused("22 fields")

    def test_a_null_value(self):
        self.edit("data_22_fields.json", lambda rows: rows[0].update(weight=None))
        self.refused("not a string")

    def test_a_query_in_a_url(self):
        self.edit("data_22_fields.json", lambda rows: rows[0].update(
            url=rows[0]["url"] + "?cid=x"))
        self.refused("query")

    def test_sampled_product_missing_from_the_data(self):
        self.edit("data_22_fields.json", lambda rows: rows[0].update(upc="9"))
        self.edit("data_22_fields.json", lambda rows: rows[50].update(upc="8"))
        self.refused("not in the data")

    def test_sampled_product_with_another_url(self):
        self.edit("data_22_fields.json", lambda rows: rows[255].update(
            url="https://www.marianos.com/p/y/1"))
        self.refused("another url")

    def test_sampled_product_with_another_price(self):
        self.edit("data_22_fields.json", lambda rows: rows[255].update(regular_price="9.99"))
        self.refused("another price")

    def test_a_kroger_label_the_notes_say_does_not_exist(self):
        self.edit("discovery_provenance.json", lambda d: next(iter(d.values()))[
            "api_categories"].append("Coffee & Tea"))
        self.refused("label contains")

    def test_no_seafood_label(self):
        self.edit("discovery_provenance.json", lambda d: [
            v["api_categories"].remove(tool.SEAFOOD_LABEL) for v in d.values()])
        self.refused("Meat & Seafood")

    def test_a_term_at_the_limit_reporting_no_more(self):
        for path in (self.s.spine / "raw").glob("Dairy-milk/*.json"):
            path.write_text(path.read_text().replace('"total": 900', '"total": 250'))
        self.refused("does not report more")

    def test_a_note_missing_a_required_fact(self):
        note = self.s.note_dir / "DOES_NOT_ESTABLISH.md"
        note.write_text(note.read_text().replace("Dairy||milk", "other"))
        self.refused("Dairy||milk")

    def test_a_note_addressed_to_someone(self):
        with open(self.s.note_dir / "README.md", "a") as note:
            note.write("Dear reader,\n")
        self.refused("addressed to someone")

    def test_source_that_no_longer_does_what_the_notes_say(self):
        source = pathlib.Path(self.tmp.name) / "source"
        for name in tool.SOURCES:
            (source / name).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(ROOT / name, source / name)
        runner = source / "marianos_collector/runner.py"
        runner.write_text(runner.read_text().replace("PUBLISHED_IDENTITY_LOST", "gone"))
        self.refused("no longer does", lambda: tool.check_source(source))

    def test_a_sweep_that_grows_a_paid_dependency(self):
        source = pathlib.Path(self.tmp.name) / "source"
        for name in tool.SOURCES:
            (source / name).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(ROOT / name, source / name)
        sweep = source / "tools/kroger_full_sweep.py"
        sweep.write_text("import azure.storage\n" + sweep.read_text())
        self.refused("depends on", lambda: tool.check_source(source))


class Tampering(Base):
    def setUp(self):
        super().setUp()
        self.s.build()
        self.manifest_path = self.s.output / "MANIFEST_SHA256.json"

    def rehash(self):
        manifest = json.loads(self.manifest_path.read_text())
        for entry in manifest["entries"]:
            path = self.s.output / entry["path"]
            entry["sha256"], entry["bytes"] = tool.sha256(path), path.stat().st_size
        self.manifest_path.write_text(json.dumps(manifest))

    def verify(self):
        return tool.verify(self.s.output, self.s.deny)

    def test_a_changed_file(self):
        with open(self.s.output / "README.md", "a") as note:
            note.write("x")
        self.refused("does not match", self.verify)

    def test_an_added_file(self):
        (self.s.output / "extra.txt").write_text("x")
        self.refused("disagree", self.verify)

    def test_a_removed_file(self):
        (self.s.output / "data/quarantine.json").unlink()
        self.refused("disagree", self.verify)

    def test_a_changed_row_with_the_manifest_rehashed(self):
        path = self.s.output / "data/data_22_fields.json"
        rows = json.loads(path.read_text())
        rows[300]["regular_price"] = "9.99"
        path.write_text(json.dumps(rows))
        self.rehash()
        with self.assertRaises(PackageRefused):
            self.verify()

    def test_a_changed_statement(self):
        manifest = json.loads(self.manifest_path.read_text())
        manifest["statements_recomputed_from_the_bytes"]["duplicate_upcs"] = 7
        self.manifest_path.write_text(json.dumps(manifest))
        self.refused("do not recompute", self.verify)

    def test_a_substituted_sample_page(self):
        name = "raw_sample/Produce-apple/start_0001.json"
        path = self.s.output / name
        page = json.loads(path.read_text())
        page["start"] = 51
        path.write_text(json.dumps(page))
        self.rehash()
        self.refused("not the capture the index describes", self.verify)

    def test_a_sample_page_removed_from_the_rule(self):
        name = "raw_sample/Produce-apple/start_0001.json"
        (self.s.output / name).unlink()
        manifest = json.loads(self.manifest_path.read_text())
        manifest["entries"] = [e for e in manifest["entries"] if e["path"] != name]
        self.manifest_path.write_text(json.dumps(manifest))
        self.refused("not the one the rule selects", self.verify)

    def test_a_sample_entry_naming_another_original(self):
        manifest = json.loads(self.manifest_path.read_text())
        entry = [e for e in manifest["entries"] if e["path"].startswith("raw_sample/")][0]
        entry["original_sha256"] = "0" * 64
        self.manifest_path.write_text(json.dumps(manifest))
        self.refused("another original", self.verify)

    def test_a_cid_restored_to_a_sample_page(self):
        name = "raw_sample/Produce-apple/start_0001.json"
        path = self.s.output / name
        path.write_text(path.read_text().replace("cid=MASKED", RAW_CID))
        self.rehash()
        self.refused("unmasked cid", self.verify)

    def test_an_identity_string_added_with_the_manifest_rehashed(self):
        with open(self.s.output / "README.md", "a") as note:
            note.write(DENIED)
        self.rehash()
        self.refused("identity strings", self.verify)

    def test_a_note_that_lost_a_fact(self):
        path = self.s.output / "R9_OPERATING_COST.md"
        path.write_text("nothing\n")
        self.rehash()
        self.refused("does not state", self.verify)

    def test_a_shipped_source_changed_under_the_notes(self):
        path = self.s.output / "source/marianos_collector/runner.py"
        path.write_text(path.read_text().replace("Zero eligible products", "changed"))
        self.rehash()
        self.refused("no longer does", self.verify)


if __name__ == "__main__":
    unittest.main()
