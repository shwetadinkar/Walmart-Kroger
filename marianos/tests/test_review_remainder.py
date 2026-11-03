"""Four smaller findings from the independent review of 3 November.

Each is small and each would have been a real wrong answer.

**The endpoint allowlist accepted a trailing newline.** In Python `$` also
matches before a trailing `\\n`, so `/products/0001111078407\\n` passed a check
written to admit exactly thirteen digits and nothing else.

**Nothing tied `--store` to `--location-id`.** Without `--resolve-store` the
store columns come from `stores.json` while the sweep queries
`--location-id`, so `--store <any configured id> --location-id 53100508`
published West Loop data under whatever name the config held. The working
rules stated the observed-columns property unconditionally, which was true only
of the Azure job.

**`Kitchen Dining` was mapped to half a root.** The client's single root spans
the retailer's `28 kitchen` and `40 dining`. Mapping it to `28` alone compared
496 delivered records against the children of half the published structure,
and only a comment admitted it.

**The reconciliation disclaimer hardcoded figures it claimed to derive.** The
page counts, the store name and the three roots with no listing page were
literal text, so running the tool against a newer capture would have produced a
disclaimer contradicting the JSON written beside it. That is the exact failure
the working rules record.
"""

import csv
import json
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import sitemap_reconciliation as recon  # noqa: E402
from marianos_collector import cli  # noqa: E402
from marianos_collector.kroger import Credentials, KrogerClient, KrogerError  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
TAXONOMY = ROOT / "evidence/2026-11-02-marianos-sitemap-taxonomy.json"


def configured_roots():
    with (ROOT / "config/categories.csv").open(newline="", encoding="utf-8-sig") as s:
        return [r["Category (Auto)"].strip() for r in csv.DictReader(s)
                if r.get("Category (Auto)", "").strip()]


class TheAllowlistAdmitsThirteenDigitsAndNothingElse(unittest.TestCase):
    def test_a_trailing_newline_is_refused(self):
        self.assertIsNone(KrogerClient._PRODUCT_BY_ID.match("/products/0001111078407\n"))

    def test_a_trailing_newline_is_refused_by_the_client_too(self):
        client = KrogerClient(Credentials("id", "secret"))
        with self.assertRaises(KrogerError):
            client.get("/products/0001111078407\n")

    def test_the_legitimate_path_still_passes(self):
        self.assertIsNotNone(KrogerClient._PRODUCT_BY_ID.match("/products/0001111078407"))

    def test_other_trailing_whitespace_is_refused(self):
        for suffix in ("\r", "\t", " ", "\n\n", "\r\n"):
            with self.subTest(suffix=repr(suffix)):
                self.assertIsNone(
                    KrogerClient._PRODUCT_BY_ID.match(f"/products/0001111078407{suffix}"))


class TheStoreArgumentMustDescribeTheStoreQueried(unittest.TestCase):
    def test_a_mismatch_without_resolve_store_is_refused(self):
        with self.assertRaises(SystemExit):
            cli.main(["run", "--source", "sweep",
                      "--store", "DEMO-LAKESHORE-60601",
                      "--location-id", "53100508"])

    def test_resolve_store_does_not_need_them_to_match(self):
        """With --resolve-store the columns come from Kroger, so the stores
        file is not consulted and --store is irrelevant. It must fail for the
        missing address assertions, not for the mismatch."""
        with self.assertRaises(SystemExit):
            cli.main(["run", "--source", "sweep", "--store", "DEMO-LAKESHORE-60601",
                      "--location-id", "53100508", "--resolve-store"])

    def test_matching_them_gets_past_this_check(self):
        """It must fail later, on credentials, not here."""
        with self.assertRaises(SystemExit) as caught:
            cli.main(["run", "--source", "sweep", "--store", "53100508",
                      "--location-id", "53100508"])
        self.assertNotIn("--store to equal", str(caught.exception))


class ARootMaySpanMoreThanOneDepartment(unittest.TestCase):
    def setUp(self):
        if not TAXONOMY.is_file():
            self.skipTest("taxonomy evidence absent")
        self.tax = json.loads(TAXONOMY.read_text())
        self.report = recon.reconcile(self.tax, [], configured_roots())
        self.rows = {r["root"]: r for r in self.report["roots"]}

    def test_kitchen_dining_names_both_departments(self):
        row = self.rows["Kitchen Dining"]
        self.assertEqual(row["published_listing_id"], "28, 40")
        self.assertEqual(row["published_listing_slug"], "kitchen, dining")

    def test_its_children_include_the_dining_departments(self):
        """35 under kitchen alone; the dining department adds its own."""
        self.assertGreater(self.rows["Kitchen Dining"]["published_children"], 35)

    def test_a_single_department_root_is_unaffected(self):
        row = self.rows["Dairy"]
        self.assertEqual(row["published_listing_id"], "02")
        self.assertEqual(row["published_depth"], "department")

    def test_a_wrong_id_in_a_multi_department_root_still_fails_loudly(self):
        with unittest.mock.patch.dict(recon.ROOT_TO_SITE,
                                      {"Kitchen Dining": ("28", "99")}):
            with self.assertRaises(SystemExit) as caught:
                recon.reconcile(self.tax, [], configured_roots())
        self.assertIn("absent from the captured taxonomy", str(caught.exception))


class TheDisclaimerDerivesEveryFigure(unittest.TestCase):
    def setUp(self):
        if not TAXONOMY.is_file():
            self.skipTest("taxonomy evidence absent")

    def written(self, rows, taxonomy_path=None):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "out"
            data = Path(td) / "data.json"
            data.write_text(json.dumps(rows))
            recon.main(["--taxonomy", str(taxonomy_path or TAXONOMY),
                        "--data", str(data), "--out", str(out)])
            return (out / "DOES_NOT_ESTABLISH.md").read_text()

    def row(self, store_name="Marianos - Test Store"):
        return {"url": "", "upc": "", "category": "Dairy", "store_name": store_name}

    def test_the_store_comes_from_the_data_not_the_template(self):
        text = self.written([self.row("Marianos - Somewhere Else")])
        self.assertIn("Marianos - Somewhere Else", text)
        self.assertNotIn("Vernon Hills", text)

    def test_the_page_counts_come_from_the_capture(self):
        shrunk = json.loads(TAXONOMY.read_text())
        keep = [e for e in shrunk["listing_pages"]["entries"]
                if e["depth"] == "department"][:3]
        shrunk["listing_pages"] = {
            "total": len(keep), "departments": len(keep),
            "subcategories": 0, "leaves": 0, "entries": keep}
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "tax.json"
            path.write_text(json.dumps(shrunk))
            # Only the roots those three departments cover stay mapped.
            ids = {e["id"] for e in keep}
            trimmed = {k: v for k, v in recon.ROOT_TO_SITE.items()
                       if v is None or set(recon.ids_for(v) if hasattr(recon, "ids_for")
                                           else ((v,) if isinstance(v, str) else v)) <= ids}
            with unittest.mock.patch.object(recon, "ROOT_TO_SITE", trimmed):
                text = self.written([self.row()], taxonomy_path=path)
        self.assertIn(f"{len(keep)} published listing pages", text)
        self.assertNotIn("461 published listing pages", text)

    def test_the_unlisted_roots_are_derived_and_named_in_full(self):
        """Named in full: my hardcoded version said "wine"."""
        text = self.written([self.row()])
        for root in ("`Beer Wine Liquor`", "`Bakery`", "`Floral`", "`Coupons`"):
            with self.subTest(root=root):
                self.assertIn(root, text)

    def test_the_records_claim_is_separate_from_the_naming_claim(self):
        """One dataset can have the roots unlisted and no records in them. The
        earlier wording asserted both at once."""
        text = self.written([self.row()])
        self.assertIn("Of those, none carry", text)

    def test_against_the_delivered_data_it_names_the_roots_with_records(self):
        delivered = ROOT / "out/vernon-hills-merged-rerun-2026-11-01-v2/data_22_fields_enriched.json"
        if not delivered.is_file():
            self.skipTest("delivered dataset absent")
        rows = json.loads(delivered.read_text())
        text = self.written(rows)
        self.assertIn("Bakery", text)
        self.assertIn("Beer Wine Liquor", text)
        self.assertNotIn("Of those, none carry", text)

    def test_the_shipped_disclaimer_agrees_with_the_shipped_json(self):
        """The failure mode being prevented: a disclaimer contradicting the
        JSON written beside it."""
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "out"
            data = Path(td) / "data.json"
            data.write_text(json.dumps([self.row()]))
            recon.main(["--taxonomy", str(TAXONOMY), "--data", str(data),
                        "--out", str(out)])
            report = json.loads((out / "RECONCILIATION.json").read_text())
            text = (out / "DOES_NOT_ESTABLISH.md").read_text()
        self.assertIn(f"{report['published_listing_pages']} published listing pages", text)
        self.assertIn(f"{report['published_departments']} departments", text)
        self.assertIn(f"{report['seo_product_sitemap']['published']}", text)


if __name__ == "__main__":
    unittest.main()
