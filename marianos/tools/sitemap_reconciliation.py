#!/usr/bin/env python3
"""Reconcile the delivered records against the retailer's OWN published taxonomy.

Why this exists. Every coverage statement in this project so far has been
bounded by the same admission: term-filtered search cannot attest complete
category discovery, so we could describe what we collected but not what we
collected it *out of*. There was no denominator.

The retailer publishes one. `robots.txt` advertises a sitemap, the sitemap
index lists a product-listing sitemap, and that file enumerates 461 listing
pages whose numeric ids encode their own depth: 2 digits a department, 5 a
subcategory, 10 a leaf. That is the retailer's own category structure, read
from the retailer's own file, and it is captured at
`evidence/2026-11-02-marianos-sitemap-taxonomy.json`.

What this tool establishes:

- Which of the client's 28 roots correspond to a published department, which
  to a subcategory, and which to no published listing page at all. Through an
  explicit map. An unmapped root is reported, never guessed.
- How many of the 890 products in the retailer's SEO product sitemap are in
  the delivered dataset, and the id of every one that is not.

What it does NOT establish, and the report says so in its own words:

- Coverage of the catalogue. The product sitemap is an SEO subset: 890 URLs
  against 26,166 products collected from the API at one store. Absence from it
  proves nothing and presence in it is not a sample of anything.
- That a product in the sitemap but not in our data is a collection gap. A
  sitemap is site-wide; the product may simply not be carried at this store.
  Only a per-id store-bound lookup separates those two, which is what
  `resolve_sitemap_gap.py` is for.
- That the published taxonomy is the whole taxonomy. It is not. `bakery`,
  `floral` and `wine` have no listing page in the sitemap at all, yet the
  Kroger API labels produce all three. The site's listing taxonomy and the
  API's category labels are two different vocabularies, each incomplete
  relative to the other, and this report names which source evidences which
  root rather than pretending either is authoritative.
"""

import argparse
import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# The client's 28 roots against the retailer's published listing taxonomy.
# Every id and slug here was copied from a sitemap URL in the captured
# evidence file; none is inferred. A root mapped to None has no published
# listing page, which is a fact about the sitemap and not about the store.
#
# The point of this map is that it is checkable: run the tool and every id is
# asserted to exist in the evidence file, so a wrong id fails loudly rather
# than producing a confident wrong report.
ROOT_TO_SITE = {
    "Coupons": None,                               # a savings surface; coupons-sitemap.xml is separate
    "Produce": "06",                               # fresh-fruits-vegetables
    "Meat": "05",                                  # meat-seafood
    "Seafood": "05004",                            # fish, inside meat-seafood
    "Deli": "13",
    "Bakery": None,                                # no listing page in the sitemap
    "Floral": None,                                # no listing page in the sitemap
    "Grocery": "01",                               # pantry
    "Dairy": "02",                                 # dairy-eggs
    "Frozen": "19",                                # frozen-foods
    "Natural Organic": "18",                       # natural-organic
    "Beverages": "04",
    "Breakfast": "03",
    "Coffee": "04003",                             # coffee, inside beverages
    "Candy": "23",
    "Beer Wine Liquor": None,                      # no listing page in the sitemap
    "Health": "22",                                # health-wellness
    "Personal Care": "21",
    "Beauty": "20",
    "Baby": "10",
    "Household": "26",                             # cleaning-and-household
    # Two departments, because the client's single root spans both. Mapping it
    # to 28 alone compared 496 delivered records against the children of half
    # the published structure, and only a comment admitted it.
    "Kitchen Dining": ("28", "40"),                # kitchen and dining
    "Pet Supplies": "27",                          # pet
    "Candles Home Fragrances": "32001",            # candles-home-fragrances, inside home-decor
    "Batteries": "26003",                          # batteries, inside cleaning-and-household
    "Light Bulbs": "26002",                        # light-bulbs, inside cleaning-and-household
    "School Office": "35",                         # school-office
    "Hardware Home Improvement": "33",
}

DEPTH_LABEL = {2: "department", 5: "subcategory", 10: "leaf"}


def product_ids(rows):
    """Every id a delivered row can be matched on: the URL tail and the UPC."""
    ids = set()
    for row in rows:
        match = re.search(r"/p/[^/]+/(\d+)$", str(row.get("url") or ""))
        if match:
            ids.add(match.group(1))
        if row.get("upc"):
            ids.add(str(row["upc"]))
    return ids


def reconcile(taxonomy, rows, configured_roots):
    entries = {e["id"]: e for e in taxonomy["listing_pages"]["entries"]}

    def ids_for(value):
        if value is None:
            return ()
        return (value,) if isinstance(value, str) else tuple(value)

    unknown_ids = sorted(i for v in ROOT_TO_SITE.values()
                         for i in ids_for(v) if i not in entries)
    if unknown_ids:
        raise SystemExit(
            f"Mapped listing ids absent from the captured taxonomy: {unknown_ids}. "
            "Recapture the sitemap or correct the map; do not publish this report.")
    unmapped_roots = sorted(set(configured_roots) - set(ROOT_TO_SITE))
    stale_roots = sorted(set(ROOT_TO_SITE) - set(configured_roots))

    delivered = product_ids(rows)
    by_root = Counter(r.get("category") or "(none)" for r in rows)

    roots = []
    for name in configured_roots:
        site_ids = ids_for(ROOT_TO_SITE.get(name))
        mapped = [entries[i] for i in site_ids]
        children = [e for e in entries.values()
                    if e["id"] not in site_ids
                    and any(e["id"].startswith(i) for i in site_ids)]
        depths = {DEPTH_LABEL[len(i)] for i in site_ids}
        roots.append({
            "root": name,
            "records_delivered": by_root.get(name, 0),
            "published_listing_id": ", ".join(site_ids),
            "published_listing_slug": ", ".join(e["slug"] for e in mapped),
            "published_depth": ", ".join(sorted(depths)) if depths else "none",
            "published_children": len(children),
            "evidenced_by": (
                "retailer sitemap and Kroger API labels"
                if site_ids and by_root.get(name) else
                "retailer sitemap only, no records collected" if site_ids else
                "Kroger API labels only, no published listing page"
                if by_root.get(name) else
                "neither"),
        })

    seo = taxonomy["seo_product_pages"]
    seo_ids = [e["id"] for e in seo["entries"]]
    present = [i for i in seo_ids if i in delivered]
    absent = [i for i in seo_ids if i not in delivered]

    return {
        "taxonomy_captured_utc": taxonomy["captured_utc"],
        "taxonomy_evidence": "evidence/2026-11-02-marianos-sitemap-taxonomy.json",
        "published_listing_pages": taxonomy["listing_pages"]["total"],
        "published_departments": taxonomy["listing_pages"]["departments"],
        "published_subcategories": taxonomy["listing_pages"]["subcategories"],
        "published_leaves": taxonomy["listing_pages"]["leaves"],
        "configured_roots": len(configured_roots),
        "roots_with_a_published_department": sum(
            1 for r in roots if "department" in r["published_depth"]),
        "roots_published_only_as_a_subcategory": sum(
            1 for r in roots if r["published_depth"] == "subcategory"),
        "roots_with_no_published_listing_page": sum(
            1 for r in roots if r["published_depth"] == "none"),
        "roots_unmapped_and_therefore_unreported": unmapped_roots,
        "mapped_roots_not_in_the_configured_set": stale_roots,
        "roots": roots,
        "seo_product_sitemap": {
            "published": seo["total"],
            "in_delivered_dataset": len(present),
            "absent_from_delivered_dataset": len(absent),
            "absent_ids": absent,
            "_caution": seo["_caution"],
        },
        "records_with_no_category": by_root.get("(none)", 0) + by_root.get("", 0),
    }


DOES_NOT_ESTABLISH = """\
# What this reconciliation does not establish

**It is not a coverage percentage, and no figure in it should be read as one.**

The retailer's product-listing sitemap gives, for the first time in this
project, a denominator for *categories*: {pages} published listing pages, being
{departments} departments, {subcategories} subcategories and {leaves} leaves,
read from the retailer's own file on {captured}. That is what the numbers above
count.

It gives no denominator for *products*. The product sitemap holds {seo}
URLs. {collected} products were collected from the Kroger API at this one
store. The sitemap is therefore an SEO subset of the catalogue, not the
catalogue, and three things follow that have to be said plainly:

- **{absent} of those {seo} products are not in the delivered dataset.** That
  is not {absent} missed products. A sitemap is site-wide and a product in it
  may not be carried at {store} at all. Separating a collection gap from
  an assortment fact needs a store-bound lookup per id, which is what
  `tools/resolve_sitemap_gap.py` does and what has not been run yet.
- **Presence in the sitemap is not a random sample**, so the {present} that
  are present support no estimate of the whole.
- **The published taxonomy is not the whole taxonomy.** {no_page} have no
  listing page in the sitemap at all. Of those, {api_only_count} carry
  delivered records that the Kroger API's own labels produced. So the site's
  listing vocabulary and the API's category labels are two different
  vocabularies, each incomplete relative to the other. Neither is treated here
  as authoritative, and the per-root table says which source evidences which
  root.

**It says nothing about price, measure, promotion or stock.** A sitemap carries
URLs. Every value in the delivered records still comes from where it came from
before, and the two fields the public API does not carry are still blank.

**It is a capture, not a feed.** The sitemap was read in a browser on an
ordinary residential connection. The same URL fetched from a datacenter was
refused before any HTTP exchange, the same refusal shape measured from two
Azure regions on 30 October. No challenge was answered and none was bypassed.
So this taxonomy is a dated artefact that a scheduled run reconciles against,
not something a scheduled run can refresh by itself.
"""


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--taxonomy", type=Path,
                   default=ROOT / "evidence/2026-11-02-marianos-sitemap-taxonomy.json")
    p.add_argument("--data", type=Path, required=True,
                   help="A delivered 22-field dataset to reconcile")
    p.add_argument("--categories", type=Path, default=ROOT / "config/categories.csv")
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args(argv)

    import csv
    with a.categories.open(newline="", encoding="utf-8-sig") as stream:
        configured = [r["Category (Auto)"].strip() for r in csv.DictReader(stream)
                      if r.get("Category (Auto)", "").strip()]

    taxonomy = json.loads(a.taxonomy.read_text())
    rows = json.loads(a.data.read_text())
    report = reconcile(taxonomy, rows, configured)
    report["data_file"] = str(a.data)
    report["records"] = len(rows)

    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / "RECONCILIATION.json").write_text(json.dumps(report, indent=1))
    # Every figure substituted, none written in. The first version stated the
    # page counts, the store and the three unlisted roots as literal text while
    # claiming to derive them, so running it against a newer capture would have
    # produced a disclaimer contradicting the JSON beside it. That is the exact
    # failure the working rules record: a release note once stated a property
    # that was false and falsifiable in one command.
    # Two separate facts, because one dataset can satisfy the first and not
    # the second. The earlier wording asserted both at once and would have read
    # as false against a dataset with no records in those roots.
    no_page = sorted(r["root"] for r in report["roots"]
                     if r["published_depth"] == "none")
    api_only = sorted(r["root"] for r in report["roots"]
                      if r["evidenced_by"].startswith("Kroger API labels only"))
    stores = sorted({str(r.get("store_name") or "").strip() for r in rows} - {""})
    (a.out / "DOES_NOT_ESTABLISH.md").write_text(DOES_NOT_ESTABLISH.format(
        captured=report["taxonomy_captured_utc"],
        seo=report["seo_product_sitemap"]["published"],
        collected=len(rows),
        absent=report["seo_product_sitemap"]["absent_from_delivered_dataset"],
        present=report["seo_product_sitemap"]["in_delivered_dataset"],
        pages=report["published_listing_pages"],
        departments=report["published_departments"],
        subcategories=report["published_subcategories"],
        leaves=report["published_leaves"],
        store=", ".join(stores) if stores else "this store",
        no_page=", ".join(f"`{r}`" for r in no_page) or "No roots",
        api_only_count=(f"{len(api_only)} ({', '.join(api_only)})" if api_only
                        else "none")))
    (a.out / "absent_from_delivered.json").write_text(json.dumps(
        report["seo_product_sitemap"]["absent_ids"], indent=1))

    print(json.dumps({k: v for k, v in report.items() if k != "roots"}, indent=1)[:2000])
    print(f"\nwrote {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
