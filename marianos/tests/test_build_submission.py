"""The submission package builder.

No test imported `build_submission.py` at all, which the change-to-test map
reports. It is the tool that writes the client-facing README and the package
checksum manifest, so an untrue sentence or an unhashed file in it reaches the
client directly.

Two properties here are the ones that have gone wrong. The README stated the
page-read date as a literal "1 November", which became false the moment a
second read was added: 202 of the delivered values were observed on
3 November. And anything shipped alongside the release has to be covered by
`MANIFEST_SHA256.json`, or the package carries a file that cannot be verified.
"""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import build_submission as tool  # noqa: E402

NAMESPACE = "trials/test"
STORE = "53100502"
RELEASE = "20261103T175940Z_426c12e8"


def record(upc, **over):
    row = {k: "" for k in (
        "zipcode", "store_name", "store_location", "store_logo", "store_brand",
        "category", "sub_category", "product_title", "weight", "regular_price",
        "sale_price", "volume_deals_description", "volume_deals_price",
        "digital_deals_description", "digital_deals_price", "image_url", "url",
        "upc", "gupc", "ppm", "unit_price", "crawl_date")}
    row.update(upc=upc, store_name="Marianos - Marianos Vernon Hills",
               zipcode="60061", product_title=f"Item {upc}", regular_price="1.99")
    row.update(over)
    return row


class TheReadDatesComeFromTheMergeReport(unittest.TestCase):

    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        td = Path(self._td.name)
        self.root = td / "out"
        base = self.root / NAMESPACE / STORE / "runs" / RELEASE
        base.mkdir(parents=True)
        (base / "data.json").write_text(json.dumps([record("0001")]))
        (base / "report.json").write_text(json.dumps({"store_id": STORE}))
        (base / "manifest.json").write_text(json.dumps({"release": RELEASE}))

        self.enriched = td / "merged"
        self.enriched.mkdir()
        (self.enriched / "data_22_fields_enriched.json").write_text(json.dumps([
            record("0001", ppm="$1.00/oz"), record("0002", ppm="$2.00/oz")]))
        (self.enriched / "merge_report.json").write_text(json.dumps({
            "page_reads": [
                {"file": "a.json", "observed_at": "2026-11-01T08:45:00+00:00",
                 "records": 656},
                {"file": "b.json", "observed_at": "2026-11-03T20:00:00+00:00",
                 "records": 279},
            ],
            "products_whose_values_came_from_each_read": {
                "2026-11-01T08:45:00+00:00": 540,
                "2026-11-03T20:00:00+00:00": 202,
            },
            "page_distinct_upcs": 742,
            "page_upcs_matched_in_api": 730,
            "page_upcs_not_in_api": 12,
            "fields_populated_after_merge": {
                "ppm": 727, "volume_deals_description": 146,
                "digital_deals_description": 49},
            "values_by_field_and_source": {"ppm": {"crawl": 727}},
            "conflicts": 0,
            "refused_as_unbound": {},
        }))
        self.out = td / "pkg"

    def tearDown(self):
        self._td.cleanup()

    def build(self, extra=()):
        tool.main(["--output-root", str(self.root), "--namespace", NAMESPACE,
                   "--store", STORE, "--release", RELEASE,
                   "--enriched-from", str(self.enriched),
                   "--out", str(self.out), *extra])
        self.readme = " ".join((self.out / "README.md").read_text().split())
        self.manifest = json.loads(
            (self.out / "MANIFEST_SHA256.json").read_text())

    def test_both_read_dates_appear_and_neither_is_hardcoded(self):
        self.build()
        self.assertIn("2026-11-01", self.readme)
        self.assertIn("2026-11-03", self.readme)

    def test_it_does_not_claim_a_single_read_date(self):
        """The literal that was there said "on 1 November" and nothing else,
        which attributed 202 values observed on 3 November to the wrong day."""
        self.build()
        self.assertNotIn("pages at this store on 1 November", self.readme)

    def test_the_per_read_counts_are_stated(self):
        self.build()
        self.assertIn("540 observed 2026-11-01", self.readme)
        self.assertIn("202 observed 2026-11-03", self.readme)

    def test_a_single_read_still_reads_naturally(self):
        one = json.loads((self.enriched / "merge_report.json").read_text())
        one["page_reads"] = one["page_reads"][:1]
        one["products_whose_values_came_from_each_read"] = {
            "2026-11-01T08:45:00+00:00": 540}
        (self.enriched / "merge_report.json").write_text(json.dumps(one))
        self.build()
        self.assertIn("on 2026-11-01", self.readme)
        self.assertNotIn("2026-11-03", self.readme)


class TheCompleteProvenanceEvidenceShips(unittest.TestCase):
    """provenance.json carries a preview capped at 200 and names the file with
    the complete history. The client asked for that history beyond a preview,
    and the builder used to copy the summary and leave the named file behind."""

    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        td = Path(self._td.name)
        self.root = td / "out"
        base = self.root / NAMESPACE / STORE / "runs" / RELEASE
        base.mkdir(parents=True)
        (base / "data.json").write_text(json.dumps([record("0001")]))
        self.enriched = td / "merged"
        self.enriched.mkdir()
        (self.enriched / "data_22_fields_enriched.json").write_text(
            json.dumps([record("0001", ppm="$1.00/oz")]))
        (self.enriched / "provenance.json").write_text(json.dumps(
            {"complete_evidence_artifact": "provenance_evidence.json"}))
        self.out = td / "pkg"

    def tearDown(self):
        self._td.cleanup()

    def build(self):
        tool.main(["--output-root", str(self.root), "--namespace", NAMESPACE,
                   "--store", STORE, "--release", RELEASE,
                   "--enriched-from", str(self.enriched), "--out", str(self.out)])

    def test_the_named_evidence_file_is_copied_and_hashed(self):
        (self.enriched / "provenance_evidence.json").write_text('{"all": []}')
        self.build()
        self.assertTrue((self.out / "provenance_evidence.json").is_file())
        manifest = json.loads((self.out / "MANIFEST_SHA256.json").read_text())
        self.assertIn("provenance_evidence.json", manifest)

    def test_a_named_evidence_file_that_is_missing_is_refused(self):
        with self.assertRaises(SystemExit):
            self.build()


class AnythingShippedAlongsideIsHashed(unittest.TestCase):

    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        td = Path(self._td.name)
        self.root = td / "out"
        base = self.root / NAMESPACE / STORE / "runs" / RELEASE
        base.mkdir(parents=True)
        (base / "data.json").write_text(json.dumps([record("0001")]))
        self.out = td / "pkg"
        self.extra_file = td / "ACQUISITION.md"
        self.extra_file.write_text("# proposal\n", encoding="utf-8")
        self.extra_dir = td / "reconciliation"
        self.extra_dir.mkdir()
        (self.extra_dir / "README.md").write_text("# recon\n", encoding="utf-8")
        (self.extra_dir / "rows.csv").write_text("upc\n0001\n", encoding="utf-8")

    def tearDown(self):
        self._td.cleanup()

    def build(self, extra=()):
        tool.main(["--output-root", str(self.root), "--namespace", NAMESPACE,
                   "--store", STORE, "--release", RELEASE,
                   "--out", str(self.out), *extra])
        self.manifest = json.loads(
            (self.out / "MANIFEST_SHA256.json").read_text())
        self.readme = " ".join((self.out / "README.md").read_text().split())

    def test_an_included_file_is_copied_and_hashed(self):
        self.build(["--include", str(self.extra_file)])
        self.assertTrue((self.out / "ACQUISITION.md").is_file())
        self.assertIn("ACQUISITION.md", self.manifest)

    def test_an_included_directory_is_copied_whole_and_every_file_hashed(self):
        self.build(["--include", str(self.extra_dir)])
        for rel in ("reconciliation/README.md", "reconciliation/rows.csv"):
            self.assertTrue((self.out / rel).is_file(), rel)
            self.assertIn(rel.replace("/", os.sep), self.manifest)

    def test_every_file_in_the_package_is_in_the_manifest(self):
        """The property that makes the package verifiable. Asserted over the
        whole tree rather than over the names passed in."""
        self.build(["--include", str(self.extra_file),
                    "--include", str(self.extra_dir)])
        on_disk = {str(p.relative_to(self.out))
                   for p in self.out.rglob("*") if p.is_file()
                   and p.name != "MANIFEST_SHA256.json"}
        self.assertEqual(on_disk, set(self.manifest))

    def test_the_readme_names_what_was_included(self):
        self.build(["--include", str(self.extra_file),
                    "--include", str(self.extra_dir)])
        self.assertIn("Also in this package", self.readme)
        self.assertIn("ACQUISITION.md", self.readme)
        self.assertIn("reconciliation/", self.readme)

    def test_no_include_leaves_no_empty_section(self):
        self.build()
        self.assertNotIn("Also in this package", self.readme)

    def test_a_missing_include_path_is_refused_rather_than_skipped(self):
        with self.assertRaises(SystemExit):
            self.build(["--include", str(self.out.parent / "nope.md")])


if __name__ == "__main__":
    unittest.main()
