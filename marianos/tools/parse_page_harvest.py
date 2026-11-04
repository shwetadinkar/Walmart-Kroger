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
# The retailer also renders an in-store location above the price block, with a
# varying number, so it cannot sit in the set above. Seen on 4 November as
# "Aisle 18"; earlier harvests did not carry it. It is a shelf location, not a
# price or a label about one, so it is skipped rather than recorded: nothing in
# the 22 fields holds it.
AISLE = re.compile(r"^(aisle|aisles)\b", re.I)
# The restatement sentence the retailer renders under a sold-by-weight price,
# either "about $1.45 each" or "Sale: about $3.38 each discounted from $7.18".
ABOUT_RESTATEMENT = re.compile(r"^(sale:\s*)?about\s+\$", re.I)
# The retailer renders sold-by-weight items as the three lines
# "about" / "$1.45" / "each", then restates them as "about $1.45 each".
# That price is explicitly approximate and is not a fixed shelf price, so it is
# recorded under its own name and left out of regular_price. The per-measure
# rate shown beside it is a displayed rate and is kept in ppm unchanged.
ABOUT_EACH = re.compile(r"^about\s+\$[0-9][0-9,]*\.?[0-9]*\s+each$", re.I)

# Lines the retailer renders on a product card that are NOT deal text. A stock
# status and a payment eligibility are not offers, and "View 2 Offers" and
# "11 more options" are navigation into other pages. None of the 22 fields
# holds any of them, so they are recorded on the page record for provenance and
# published nowhere.
#
# This matters because deal lines used to be whatever was left over after the
# title and size were taken, which published "Low Stock" into
# volume_deals_description on 47 records of the 1 November read and "View 2
# Offers" on 12 more. Found on 4 November by comparing the two harvests at the
# same store: a record whose size read "Coupon: $1.79 lb Honeycrisp Apples" on
# 1 November read "SNAP EBT" on 4 November, which is not a change in the data.
STOCK_LABELS = {"Low Stock", "Out of Stock", "In Stock", "Limited Availability"}
ELIGIBILITY_LABELS = {"SNAP EBT", "FSA/HSA"}
VARIANT_LINK = re.compile(
    r"^\d+\s+more\s+(option|size|flavor|flavour|color|colour|variet|count)", re.I)
OFFER_LINK = re.compile(r"^view\s+\d+\s+offer", re.I)

# A deal is identified by what the retailer wrote, not by being left over.
# Every one of the 50 distinct card lines across the 1 and 4 November harvests
# was checked against this: it matches every real offer and no badge or link.
DEAL_MARKER = re.compile(
    r"""
      ^coupon:                      # Coupon: Save $1.00 on Energizer
    | ^cash\s*back:                 # Cash Back: $5.00 Cash Back on ...
    | ^buy\s+\d                     # Buy 1, Get 1 Free / Buy 2 Save $4
    | ^get\s+\d                     # Get 2 for $5
    | ^save\s+\$?\d                 # Save $15 when you spend $60
    | ^spend\s+\$?\d                # Spend $50 save $10
    | ^limit\s+\d\b                 # a bare "Limit 2" offer line
    | ^mix\s*(?:and|&)\s*match      # Mix and match 4 for $10
    | ^\d+\s*/\s*\$\d               # 3/$12 When you buy 3 or more
    | ^\d+\s+for\s+\$\d             # 2 For $4.00
    | ^\d+(?:\.\d+)?\s*¢\s+each  # 99c each when you buy 5 or more
    | \bwhen\s+you\s+(?:buy|spend)\b  # ... when you buy 3 or more
    """,
    re.I | re.X)
"""Identify an offer by an anchored grammar, not by substring words.

The first version matched `\\bfree\\b`, `\\bmix\\b`, `\\blimit\\b`, `\\bbuy\\b`,
`\\bsave\\b` and `\\bget\\b` anywhere in a line. Across the two real harvests
that classified about 40 **product titles** as offers: "Gluten Free",
"Caffeine-Free", "Lactose Free", "Fat Free", "BPA-Free", "Free Range",
"Flicker Free", "WILTON SPRINKLES GOLD METALLIC MIX TALL", and a chicken breast
title ending "(Limit 2 at sale price)".

Nothing was mis-published, because titles are popped positionally before the
remaining lines are classified. But it was reachable through a single
unrecognised leading line, which is exactly what `Aisle 25` was between the
1 and 4 November harvests: one new label shifts the positions, the title lands
in the deal slot, and `volume_deals_description` becomes a product name with
`parse_reason` empty, reported as fully recognised. Silent, and no count would
reveal it.

Found by an independent review on 4 November. Every one of the 1,464 distinct
card lines across both harvests is checked against this in
`tests/test_parse_page_harvest.py`, from the files rather than from a list
typed here.
"""


def classify_card_line(line):
    """Return one of stock, eligibility, offer_link, variant_link, deal, other."""
    text = (line or "").strip()
    if not text:
        return "other"
    if text in STOCK_LABELS:
        return "stock"
    if text in ELIGIBILITY_LABELS:
        return "eligibility"
    if OFFER_LINK.match(text):
        return "offer_link"
    if VARIANT_LINK.match(text):
        return "variant_link"
    if DEAL_MARKER.search(text):
        return "deal"
    return "other"


def looks_like_size(line):
    """A size is a line that is not a deal and not one of the card's badges.

    Deals are identified positively, so the unrecognised case falls to the size
    slot rather than into a published deal column. That direction is the safe
    one: a size left in the size field is published nowhere, while a size in
    volume_deals_description would be published as an offer the retailer never
    made.
    """
    return bool((line or "").strip()) and classify_card_line(line) == "other"


def sort_card_lines(rest):
    """Split the remaining card lines into deals and the labels that are not."""
    deals, stock, labels = [], "", []
    for line in rest:
        kind = classify_card_line(line)
        if kind == "deal":
            deals.append(line)
        elif kind == "stock":
            stock = stock or line.strip()
        elif kind in ("eligibility", "offer_link", "variant_link"):
            labels.append(line.strip())
        elif line.strip():
            labels.append(line.strip())
    return deals, stock, labels


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
        # Recorded so nothing the card rendered is silently dropped. Neither is
        # published: the 22 fields have no column for a stock status or a
        # payment eligibility, and a navigation link is not an observation
        # about the product.
        "stock_label": "",
        "non_deal_labels": [],
        "approximate_each_price": "",
        "approximate_each_regular_price": "",
        "price_basis": "fixed",
    }

    rest = list(lines)

    while rest and (rest[0] in LEADING_LABELS or AISLE.match(rest[0])):
        popped = rest.pop(0)
        if popped in LEADING_LABELS:
            rec["price_label"] = popped

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
            if rest and not PRICE.match(rest[0]) and looks_like_size(rest[0]):
                rec["size"] = rest.pop(0)
            rec["deal_lines"], rec["stock_label"], rec["non_deal_labels"] = \
                sort_card_lines(rest)
            return rec, ""

    if rec["price_label"] == "Prices May Vary":
        rec["price_basis"] = "prices may vary"
        if not rest:
            return rec, "prices may vary, no title"
        rec["product_title"] = rest.pop(0)
        if rest and looks_like_size(rest[0]):
            rec["size"] = rest.pop(0)
        rec["deal_lines"], rec["stock_label"], rec["non_deal_labels"] = \
            sort_card_lines(rest)
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

    if rest and looks_like_size(rest[0]):
        rec["size"] = rest.pop(0)

    rec["deal_lines"], rec["stock_label"], rec["non_deal_labels"] = \
        sort_card_lines(rest)
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
