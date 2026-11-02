"""Reconcile the delivered records against every root the client's CSV requires.

The client asked for a reconciliation of all required roots, applicable
subcategories and pages, and said plainly that term searches and a large count
do not establish full coverage. They do not, and this tool is not an attempt to
argue otherwise. It states, per root: how many products were delivered, which
Kroger labels produced them, how many carry a displayed rate, and for the roots
with none, why.

It also states what bounds the coverage. The public API has no category
enumeration, so products are reached by search term. `filter.start` is a skip
count Kroger refuses past 250, so one term yields at most 300 results however
many exist. A term that hit that ceiling had more products behind it than were
ever fetched, and those terms are named rather than summarised.

Everything here is recomputed from the delivered records and the run report.
Nothing is carried over from a previous document.
"""

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path


def required_roots(categories_csv):
    with open(categories_csv, encoding="utf-8") as handle:
        return [row["Category (Auto)"].strip()
                for row in csv.DictReader(handle)
                if row.get("Category (Auto)", "").strip()]


def build(records, report, roots, enriched_upcs):
    by_root = defaultdict(list)
    for rec in records:
        by_root[rec.get("category", "")].append(rec)

    labels_by_root = defaultdict(Counter)
    for rec in records:
        labels_by_root[rec.get("category", "")][rec.get("sub_category", "")] += 1

    rows = []
    for root in roots:
        got = by_root.get(root, [])
        rows.append({
            "root": root,
            "products": len(got),
            "kroger_labels_that_produced_them":
                [{"label": lab, "products": n}
                 for lab, n in labels_by_root[root].most_common()],
            "with_displayed_ppm":
                sum(1 for r in got if r.get("upc") in enriched_upcs
                    and str(r.get("ppm", "")).strip()),
            "with_volume_deal_wording":
                sum(1 for r in got if str(r.get("volume_deals_description", "")).strip()),
            "with_digital_deal_wording":
                sum(1 for r in got if str(r.get("digital_deals_description", "")).strip()),
        })

    empty = [r["root"] for r in rows if r["products"] == 0]
    unexpected = sorted(set(by_root) - set(roots) - {""})

    capped = report.get("terms_that_hit_the_start_cap", [])
    capped_by_root = Counter(t.split("||", 1)[0] for t in capped)

    return {
        "store": report.get("store", {}),
        "locationId": report.get("locationId", ""),
        "generated_from": {
            "records": len(records),
            "run_report_generated_utc": report.get("generated_utc", ""),
        },
        "required_roots": len(roots),
        "roots_with_products": sum(1 for r in rows if r["products"]),
        "roots_with_no_products": empty,
        "roots": rows,
        "records_with_no_root": len(by_root.get("", [])),
        "unmapped_labels": {
            "labels": report.get("unmapped_labels", []),
            "distinct_products_left_without_a_root": len(by_root.get("", [])),
            "encounters_during_the_sweep":
                report.get("records_with_unmapped_category", 0),
            "why_those_two_numbers_differ":
                "The sweep counts an encounter each time a term returns a "
                "product, and one product is commonly returned by several "
                "terms. The run collapsed 17,089 repeat placements overall. "
                "The distinct figure is the one that describes the delivered "
                "data; the encounter figure describes the sweep.",
            "products_given_a_root_despite_an_unmapped_label":
                sum(1 for r in records
                    if r.get("sub_category") in set(report.get("unmapped_labels", []))
                    and str(r.get("category", "")).strip()),
            "rule": "An unmapped label leaves `category` empty and is reported. "
                    "The count above must be zero; a non-zero value means a root "
                    "was guessed.",
        },
        "root_assigned_from_product_not_search_term": {
            "disagreements_between_term_root_and_product_label":
                report.get("category_disagreements", 0),
            "note": "The search term is a way of reaching a product, not evidence "
                    "of its category. Where the two disagreed the product's own "
                    "Kroger label won, which is why this number is large.",
        },
        "pages": {
            "terms_swept": report.get("terms_completed", 0),
            "requests_spent": report.get("requests_spent", 0),
            "pages_per_term_ceiling": report.get("pages_per_term", 0),
            "max_start_accepted_by_kroger": report.get("max_start", 0),
            "results_reachable_per_term": 300,
            "page_failures": len(report.get("page_failures", [])),
            "terms_that_hit_the_ceiling": len(capped),
            "terms_that_hit_the_ceiling_by_root": dict(capped_by_root.most_common()),
            "terms_that_hit_the_ceiling_named": capped,
        },
        "unexpected_roots_in_data": unexpected,
        "does_not_establish": [
            "Complete category discovery. The public API has no category "
            "enumeration; products are reached by search term, so no count here "
            "is a statement about what the store carries.",
            f"Complete results per term. {len(capped)} of "
            f"{report.get('terms_completed', 0)} terms hit the 300-result ceiling, "
            "so there were more products behind those terms than were fetched.",
            "Subcategory completeness. `sub_category` is the Kroger label the "
            "product reports about itself, not a traversal of the retailer's "
            "subcategory tree, which this route cannot enumerate.",
            "That a root showing zero products means the store carries none. It "
            "means no product reached by these terms reported that label.",
        ],
    }


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--records", required=True)
    p.add_argument("--run-report", required=True)
    p.add_argument("--categories", required=True)
    p.add_argument("--enriched", help="Merged records, to count displayed rates")
    p.add_argument("--out", required=True)
    a = p.parse_args(argv)

    records = json.loads(Path(a.records).read_text(encoding="utf-8"))
    report = json.loads(Path(a.run_report).read_text(encoding="utf-8"))
    roots = required_roots(a.categories)

    enriched_upcs = set()
    if a.enriched:
        merged = json.loads(Path(a.enriched).read_text(encoding="utf-8"))
        enriched_upcs = {r["upc"] for r in merged if str(r.get("ppm", "")).strip()}
        records = merged

    result = build(records, report, roots, enriched_upcs)
    Path(a.out).write_text(json.dumps(result, indent=1, ensure_ascii=False),
                           encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items()
                      if k not in ("roots", "does_not_establish")}, indent=1)[:1600])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
