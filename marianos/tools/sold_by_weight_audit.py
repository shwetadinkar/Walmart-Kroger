"""Find delivered products the retailer itself displays as sold by weight.

The brief excludes approximate-weight products. The exclusion in `schema.py`
reads the title and the weight field for approximate wording, which is the
right test when those fields carry it. The Kroger API does not: it reports a
clean `1 lb` for products the retailer's own page prices as "about $1.45
each". So the exclusion has nothing to match and the product passes.

The client made the point that an approximate price alone cannot tell you
whether the title or size carries excluded weight wording, and asked for the
actual source observations. This produces them: for each product, what the API
said and what the page displayed, side by side, so the judgement can be made on
evidence rather than on either source alone.

It changes nothing. No row is excluded or edited here. Removing a product is a
decision for the client, and this repository does not delete rows on its own
reading of a rule.
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from marianos_collector import schema  # noqa: E402

# What the page said about how the product is priced. The first two are the
# retailer's own sold-by-weight presentation.
WEIGHT_BASES = ("about each, sold by weight", "about each on sale, sold by weight")


def audit(records, page_cards):
    by_upc = {r["upc"]: r for r in records if r.get("upc")}
    findings, unmatched = [], 0

    for card in page_cards:
        upc = (card.get("upc") or "").strip()
        basis = card.get("price_basis", "")
        if basis not in WEIGHT_BASES and basis != "prices may vary":
            continue
        record = by_upc.get(upc)
        if record is None:
            unmatched += 1
            continue

        title = record.get("product_title", "")
        weight = record.get("weight", "")
        findings.append({
            "upc": upc,
            "category": record.get("category", ""),
            "api_observation": {
                "product_title": title,
                "weight": weight,
                "regular_price": record.get("regular_price", ""),
                "url": record.get("url", ""),
            },
            "page_observation": {
                "price_basis": basis,
                "approximate_each_price": card.get("approximate_each_price", ""),
                "approximate_each_regular_price":
                    card.get("approximate_each_regular_price", ""),
                "displayed_rate": card.get("ppm", ""),
                "size_as_rendered": card.get("size", ""),
                "term_that_found_it": card.get("term", ""),
                "path": card.get("url_path", ""),
            },
            "existing_exclusion": {
                "title_matches_approximate_wording":
                    bool(schema._APPROX.search(title)),
                "weight_matches_approximate_wording":
                    bool(schema._APPROX_WEIGHT.search(weight)),
            },
        })

    caught = sum(1 for f in findings
                 if f["existing_exclusion"]["title_matches_approximate_wording"]
                 or f["existing_exclusion"]["weight_matches_approximate_wording"])

    return {
        "delivered_records": len(records),
        "page_cards_examined": len(page_cards),
        "products_the_page_prices_by_weight_or_variably": len(findings),
        "of_those_caught_by_the_existing_exclusion": caught,
        "of_those_the_exclusion_cannot_see": len(findings) - caught,
        "page_cards_with_no_delivered_record": unmatched,
        "api_weight_values_on_these_products":
            dict(Counter(f["api_observation"]["weight"] for f in findings).most_common()),
        "by_category":
            dict(Counter(f["category"] for f in findings).most_common()),
        "by_price_basis":
            dict(Counter(f["page_observation"]["price_basis"] for f in findings).most_common()),
        "findings": findings,
        "what_this_does_not_establish": [
            "A rate for the rest of the delivered set. Only products the page "
            "read reached can be checked this way, and it reached a small "
            "fraction. The status of the others is unknown and is not estimated "
            "here.",
            "That these products should be removed. The brief excludes "
            "approximate-weight products and the page evidence says these are "
            "sold by weight, but the decision to drop delivered rows is the "
            "client's. Nothing is excluded by this tool.",
            "That the exclusion rule is wrong. It tests the title and the "
            "weight field, which is correct. The API simply does not put the "
            "wording there.",
        ],
    }


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--records", required=True)
    p.add_argument("--page", required=True, help="parsed page-harvest cards")
    p.add_argument("--out", required=True)
    a = p.parse_args(argv)

    result = audit(json.loads(Path(a.records).read_text(encoding="utf-8")),
                   json.loads(Path(a.page).read_text(encoding="utf-8")))
    Path(a.out).write_text(json.dumps(result, indent=1, ensure_ascii=False),
                           encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items()
                      if k not in ("findings", "what_this_does_not_establish")},
                     indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
