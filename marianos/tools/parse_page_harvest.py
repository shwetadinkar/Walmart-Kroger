"""Parse search-result cards harvested from the retailer's own pages into fields.

Input is the raw harvest: one row per product card, carrying the term that found
it, the UPC taken from the product link, the displayed price-per-measure string
exactly as rendered, and the card's remaining visible lines in order.

This parser reads. It does not compute, convert or fill. A card whose shape is
not recognised is reported, never guessed at: `parse` returns a reason and the
caller keeps the row with empty fields. Nothing here derives a rate from price
and size, and nothing rewrites the rendered notation of a rate.
"""

import csv
import json
import re
import sys
from collections import Counter

PRICE = re.compile(r"^\$[0-9][0-9,]*\.?[0-9]*$")
SALE_LINE = re.compile(r"^Sale:\s*\$")
# Labels the retailer renders above the price block.
LEADING_LABELS = {"Everyday Low Price", "Sponsored", "New", "Best Seller",
                  "Prices May Vary", "Price Cut"}
# The restatement sentence the retailer renders under a sold-by-weight price,
# either "about $1.45 each" or "Sale: about $3.38 each discounted from $7.18".
ABOUT_RESTATEMENT = re.compile(r"^(sale:\s*)?about\s+\$", re.I)
# The retailer renders sold-by-weight items as the three lines
# "about" / "$1.45" / "each", then restates them as "about $1.45 each".
# That price is explicitly approximate and is not a fixed shelf price, so it is
# recorded under its own name and left out of regular_price. The per-measure
# rate shown beside it is a displayed rate and is kept in ppm unchanged.
ABOUT_EACH = re.compile(r"^about\s+\$[0-9][0-9,]*\.?[0-9]*\s+each$", re.I)


def parse(term, upc, path, ppm, lines):
    """Return (record, reason). reason is '' when the card was fully recognised."""
    rec = {
        "term": term,
        "upc": upc,
        "url_path": path,
        "ppm": ppm,
        "price_label": "",
        "regular_price": "",
        "sale_price": "",
        "product_title": "",
        "size": "",
        "deal_lines": [],
        "approximate_each_price": "",
        "approximate_each_regular_price": "",
        "price_basis": "fixed",
    }

    rest = list(lines)

    while rest and rest[0] in LEADING_LABELS:
        rec["price_label"] = rest.pop(0)

    # Sold-by-weight shape: "about", one or two prices, "each", then a
    # restatement sentence. Two prices means the approximate price is marked
    # down from an approximate regular price.
    if rest and rest[0].lower() == "about":
        j, approx = 1, []
        while j < len(rest) and PRICE.match(rest[j]):
            approx.append(rest[j])
            j += 1
        if approx and j < len(rest) and rest[j].lower() == "each":
            j += 1
            if j < len(rest) and ABOUT_RESTATEMENT.match(rest[j]):
                j += 1
            rec["approximate_each_price"] = approx[0]
            if len(approx) > 1:
                rec["approximate_each_regular_price"] = approx[1]
                rec["price_basis"] = "about each on sale, sold by weight"
            else:
                rec["price_basis"] = "about each, sold by weight"
            rest = rest[j:]
            if not rest:
                return rec, "sold by weight, no title"
            rec["product_title"] = rest.pop(0)
            if rest and not PRICE.match(rest[0]):
                rec["size"] = rest.pop(0)
            rec["deal_lines"] = [x for x in rest if x]
            return rec, ""

    if rec["price_label"] == "Prices May Vary":
        rec["price_basis"] = "prices may vary"
        if not rest:
            return rec, "prices may vary, no title"
        rec["product_title"] = rest.pop(0)
        if rest:
            rec["size"] = rest.pop(0)
        rec["deal_lines"] = [x for x in rest if x]
        return rec, ""

    prices = []
    while rest and PRICE.match(rest[0]):
        prices.append(rest.pop(0))

    # The retailer also renders a sentence restating a markdown. It is not a
    # price token and carries no value this schema needs.
    if rest and SALE_LINE.match(rest[0]):
        rest.pop(0)

    if not prices:
        return rec, "no price token"

    # Rendered order is current price first, then the price it is compared to.
    current = prices[0]
    compared = prices[1] if len(prices) > 1 else prices[0]
    if current == compared:
        rec["regular_price"] = current
    else:
        rec["sale_price"] = current
        rec["regular_price"] = compared

    if not rest:
        return rec, "no title"
    rec["product_title"] = rest.pop(0)

    if rest:
        rec["size"] = rest.pop(0)

    rec["deal_lines"] = [x for x in rest if x]
    return rec, ""


def main(src, out_json, out_report):
    rows = list(csv.DictReader(open(src, encoding="utf-8"), delimiter="\t"))
    parsed, reasons = [], Counter()

    for r in rows:
        lines = [x for x in r["lines"].split("|") if x]
        rec, reason = parse(r["term"], r["upc"], r["path"], r["ppm"], lines)
        rec["parse_reason"] = reason
        parsed.append(rec)
        reasons[reason or "ok"] += 1

    by_upc = {}
    for rec in parsed:
        by_upc.setdefault(rec["upc"], []).append(rec)

    conflicts = []
    for upc, group in by_upc.items():
        for field in ("ppm", "regular_price", "sale_price"):
            seen = {g[field] for g in group if g[field]}
            if len(seen) > 1:
                conflicts.append(
                    {"upc": upc, "field": field, "values": sorted(seen),
                     "terms": sorted({g["term"] for g in group})}
                )

    json.dump(parsed, open(out_json, "w", encoding="utf-8"), indent=1, ensure_ascii=False)

    report = {
        "source": src,
        "cards": len(rows),
        "distinct_upcs": len(by_upc),
        "parse_outcomes": dict(reasons),
        "ppm_present": sum(1 for p in parsed if p["ppm"]),
        "deal_text_present": sum(1 for p in parsed if p["deal_lines"]),
        "sale_price_present": sum(1 for p in parsed if p["sale_price"]),
        "sold_by_weight": sum(1 for p in parsed if p["approximate_each_price"]),
        "price_basis": dict(Counter(p["price_basis"] for p in parsed)),
        "size_present": sum(1 for p in parsed if p["size"]),
        "terms": sorted({p["term"] for p in parsed}),
        "cross_term_conflicts": conflicts,
        "ppm_units": dict(Counter(
            p["ppm"].split("/", 1)[1] for p in parsed if "/" in p["ppm"]
        ).most_common()),
        "ppm_notation": "as rendered by the retailer; not reformatted or rounded",
        "deal_wording": "verbatim card lines; not composed",
    }
    json.dump(report, open(out_report, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    return report


if __name__ == "__main__":
    rep = main(sys.argv[1], sys.argv[2], sys.argv[3])
    print(json.dumps({k: v for k, v in rep.items()
                      if k not in ("terms", "cross_term_conflicts")}, indent=1))
    print("conflicts:", len(rep["cross_term_conflicts"]))
