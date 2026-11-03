#!/usr/bin/env python3
"""Per-product verdicts for the 34 products the page prices by weight.

The client's instruction of 3 November, in full, because the whole tool turns
on it:

    "Approximate-weight exclusion depends on the actual source wording about
    weight/size. Do not remove all 34 products merely because they are sold by
    weight or have an approximate total price. Supply their exact title,
    size/weight wording and page evidence; exclude those with
    approximate-weight wording and keep eligible genuine
    fixed-size/bulk/multipack identities. Do not infer that API '1 lb' proves
    the page has no excluded wording."

Four consequences, and the tool is built around them:

1. **The verdict is driven by title and size/weight wording only.** The page's
   price basis — "about $1.45 each, sold by weight" — is *pricing*, not the
   product's size or weight field. `schema._APPROX_WEIGHT` does match "sold by
   weight", so feeding the price basis into the rule would exclude 31 of the
   34 on exactly the grounds he ruled out. It is recorded on every row and
   drives nothing.

2. **Retain is the default.** A product leaves the dataset only when wording
   we actually observed excludes it.

3. **"Not excluded" is not the same as "determined".** Where no page size or
   weight wording was captured, the honest verdict is UNDETERMINED: the API
   size is not evidence about the page, which is his last sentence. An
   undetermined product stays in the dataset.

4. **The patterns are imported, not restated.** `schema._APPROX` and
   `schema._APPROX_WEIGHT` are the shipped rule. A second copy here could
   disagree with the one that actually filters.

This tool decides nothing on its own. It writes a table for the client, who
said the call is his.
"""

import argparse
import re
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from marianos_collector.schema import _APPROX, _APPROX_WEIGHT  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent

EXCLUDE = "EXCLUDE"
KEEP = "KEEP"
UNDETERMINED = "UNDETERMINED"


def wording_matches(text: str, pattern) -> str:
    """The matched substring, so the verdict quotes its own evidence."""
    if not text:
        return ""
    found = pattern.search(str(text))
    return found.group(0) if found else ""


# A size is a quantity and a unit. Anything else in that slot is not a size,
# whatever else it is.
_SIZE = re.compile(
    r"\b\d+(?:\.\d+)?\s*(?:fl\s*oz|oz|ounces?|lbs?|pounds?|g|grams?|kg|kilograms?"
    r"|ml|l|litres?|liters?|ct|count|each|pk|packs?|pieces?|dozen)\b", re.I)
# Offer and price wording. The page capture put this in the size slot for four
# products, which is why "not approximate" cannot be read as "a fixed size".
_OFFER = re.compile(r"(?:coupon|buy\s*\d|get\s*\d|free|save|%\s*off|\boff\b|\$)", re.I)


def looks_like_a_size(text: str) -> bool:
    """Whether this captured text is a size at all.

    `Buy 1, Get 1 Free` carries no approximate-weight wording, and reading
    that as evidence of a fixed size would keep a product on the strength of a
    promotional badge. Three of the seven captures were exactly that.
    """
    text = str(text or "").strip()
    if not text or _OFFER.search(text):
        return False
    return bool(_SIZE.search(text))


def verdict_for(record: dict) -> dict:
    api = record.get("api_observation") or {}
    page = record.get("page_observation") or {}

    title = str(api.get("product_title") or "")
    api_weight = str(api.get("weight") or "")
    page_size = str(page.get("size_as_rendered") or "").strip()

    hits = {
        "api_title": wording_matches(title, _APPROX),
        "api_weight_field": wording_matches(api_weight, _APPROX_WEIGHT),
        "page_size_wording": wording_matches(page_size, _APPROX_WEIGHT),
    }
    excluded_by = {k: v for k, v in hits.items() if v}

    if excluded_by:
        verdict, reason = EXCLUDE, (
            "Observed wording about size or weight is approximate: "
            + "; ".join(f"{k} matched {v!r}" for k, v in excluded_by.items()))
    elif looks_like_a_size(page_size):
        verdict, reason = KEEP, (
            f"The page rendered a size of {page_size!r}, a quantity and a unit, with "
            "no approximate-weight wording. An eligible fixed-size identity on the "
            "evidence held.")
    elif page_size:
        verdict, reason = UNDETERMINED, (
            f"The page capture holds {page_size!r} in the size slot, which is "
            "promotional or price text rather than a size, so it is not evidence of "
            "a fixed size. That it carries no approximate-weight wording says "
            "nothing: a promotional badge would not. Retained, and the page's size "
            "element still needs reading.")
    else:
        verdict, reason = UNDETERMINED, (
            "No page size or weight wording was captured for this product. The API "
            f"size {api_weight!r} is not evidence about the page, so whether the page "
            "carries excluded wording is unknown. Retained, because a product is "
            "never removed on an absent value.")

    return {
        "upc": record.get("upc", ""),
        "category": record.get("category", ""),
        "verdict": verdict,
        "reason": reason,
        "exact_wording_observed": {
            "api_product_title": title,
            "api_weight_field": api_weight,
            "page_size_as_rendered": page_size,
        },
        "matched_exclusion_wording": excluded_by,
        "page_pricing_evidence_not_used_for_the_verdict": {
            "price_basis": page.get("price_basis", ""),
            "approximate_each_price": page.get("approximate_each_price", ""),
            "approximate_each_regular_price": page.get("approximate_each_regular_price", ""),
            "displayed_rate": page.get("displayed_rate", ""),
            "_why_not_used": (
                "This is the basis on which the retailer prices the product, not the "
                "product's size or weight. The exclusion rule matches 'sold by "
                "weight', so using this field would exclude 31 of 34 on the ground "
                "the client ruled out."),
        },
        "page_path": page.get("path", ""),
        "product_url": api.get("url", ""),
        "regular_price": api.get("regular_price", ""),
    }


SUMMARY = """\
# The 34 sold-by-weight products, one verdict each, {date}

The client asked for exact title, size/weight wording and page evidence per
product, with approximate-weight wording excluded and genuine fixed-size,
bulk and multipack identities kept. He also said not to remove all 34 merely
for being sold by weight or carrying an approximate total price, and not to
infer from an API size of `1 lb` that the page has no excluded wording.

| Verdict | Products |
|---|---:|
| EXCLUDE, observed size or weight wording is approximate | {exclude} |
| KEEP, a genuine page size was observed and is not approximate | {keep} |
| UNDETERMINED, no usable page size wording to judge by | {undetermined} |

**Nothing has been removed.** The verdicts are a recommendation; the decision
is the client's, and an UNDETERMINED product stays in the dataset either way.

## What decided each verdict

Only two things: the product's title, and its size or weight wording. The
shipped patterns `schema._APPROX` and `schema._APPROX_WEIGHT` are imported
rather than restated, so this table cannot disagree with the rule that
actually filters.

The page's pricing basis is on every row and decided nothing. `_APPROX_WEIGHT`
matches `sold by weight`, and {by_weight} of the 34 pages carry that phrase in
their pricing basis, so feeding it to the rule would have excluded them on
precisely the ground the client ruled out. It is pricing, not size.

## Why {undetermined} are undetermined

The page capture produced a genuine size, a quantity and a unit, for
{with_size} of the 34. For {slot_held_promo} more it put promotional or price
text in the size slot, for example `Buy 1, Get 1 Free` and
`Coupon: $1.79 lb Honeycrisp Apples`. That text carries no approximate-weight
wording, but a promotional badge would not, so it is no evidence of a fixed
size and those products are undetermined rather than kept. For the rest there
is no size or weight wording at all.

That the capture mislabelled four slots is itself a defect in the capture, and
it is reported here rather than relied on.

That is a gap in the capture, not a property of the products. It cannot be
closed by reasoning from the API size, which is the client's point. It needs a
page observation that reads the size or weight element specifically, for those
{undetermined} product paths. Those paths are listed in `verdicts.json`.

## What this does not establish

- **That the EXCLUDE set is complete.** It is complete with respect to the
  wording captured. A product with no page size wording could carry excluded
  wording that was never read.
- **That the KEEP set is safe to keep for ever.** It is eligible on the
  evidence held today. A later page read could show otherwise.
- **Anything about the other 26,132 delivered products.** This covers the 34
  the page priced by weight among the {examined} page cards examined, out of
  {delivered} delivered records. The page read reached a subset chosen for
  spread across roots, not a random sample, so no rate here estimates the
  whole.
"""


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--audit", type=Path,
                   default=ROOT / "reports/2026-11-02-sold-by-weight/data/sold_by_weight_audit.json")
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--date", default="3 November 2026")
    a = p.parse_args(argv)

    audit = json.loads(a.audit.read_text())
    findings = audit.get("findings") or []
    if not findings:
        raise SystemExit(f"{a.audit} carries no findings")

    verdicts = [verdict_for(r) for r in findings]
    counts = {v: sum(1 for x in verdicts if x["verdict"] == v)
              for v in (EXCLUDE, KEEP, UNDETERMINED)}
    with_size = sum(1 for x in verdicts
                    if looks_like_a_size(
                        x["exact_wording_observed"]["page_size_as_rendered"]))
    slot_held_promo = sum(
        1 for x in verdicts
        if x["exact_wording_observed"]["page_size_as_rendered"]
        and not looks_like_a_size(x["exact_wording_observed"]["page_size_as_rendered"]))
    by_weight = sum(1 for x in verdicts
                    if "by weight" in str(x["page_pricing_evidence_not_used_for_the_verdict"]
                                          ["price_basis"]).lower())

    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / "verdicts.json").write_text(json.dumps({
        "_what": ("One verdict per product, decided from observed title and "
                  "size/weight wording only. Nothing has been removed."),
        "generated": a.date,
        "source_audit": str(a.audit),
        "counts": counts,
        "products": verdicts,
        "undetermined_page_paths": [x["page_path"] for x in verdicts
                                    if x["verdict"] == UNDETERMINED and x["page_path"]],
    }, indent=1))
    (a.out / "VERDICTS.md").write_text(SUMMARY.format(
        date=a.date, exclude=counts[EXCLUDE], keep=counts[KEEP],
        undetermined=counts[UNDETERMINED], with_size=with_size,
        by_weight=by_weight, slot_held_promo=slot_held_promo,
        examined=audit.get("page_cards_examined", "?"),
        delivered=audit.get("delivered_records", "?")))

    print(json.dumps({"counts": counts, "genuine_page_size_captured": with_size,
                      "size_slot_held_promo_text": slot_held_promo,
                      "pages_whose_pricing_says_by_weight": by_weight,
                      "out": str(a.out)}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
