"""Merge page-read PPM and deal wording into the API record set.

The API sweep enumerates the assortment and supplies category, price, size, UPC
and the product URL. It supplies no displayed price per measure and no deal
wording, because the Kroger public Products API carries neither. The page read
of 1 November supplies exactly those, for the products it covered.

So the API set is the spine and the page read is an enrichment, which is what
`composition.py` is for. This tool does not merge by hand: it builds a
`CallableEnrichment` that declares only the three fields the page may supply,
binds every contribution to the product, store, fulfilment and time it was
observed at, and lets `CompositeSource` apply the precedence policy and record
the provenance. A page value that cannot be bound is refused and counted.

Deal lines are split by the retailer's own label: a line the retailer prefixes
with "Coupon:" is a digital deal, anything else is a volume deal. The text
written is the line as rendered. Nothing is composed, reworded or summarised,
and the raw lines are kept beside the output so the split can be re-checked.
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from parse_page_harvest import classify_card_line  # noqa: E402

from marianos_collector.composition import (  # noqa: E402
    BINDING_KEY,
    CallableEnrichment,
    CompositeSource,
)
from marianos_collector.config import Store  # noqa: E402
from marianos_collector.sources import Page  # noqa: E402

CRAWL_FIELDS = ("ppm", "volume_deals_description", "digital_deals_description")

# The spine is the Kroger public Products API sweep. It is named separately
# from catalog_v2 because it is a different tier with different evidence value,
# and naming it here keeps it ranked rather than falling through as unknown.
POLICY = {
    "ppm": ("crawl", "kroger_public"),
    "volume_deals_description": ("kroger_public", "crawl"),
    "digital_deals_description": ("crawl", "kroger_public"),
}

COUPON_PREFIX = "coupon:"
# The retailer renders two clipped-offer prefixes, not one. "Cash Back:" sits on
# the same digital-offer surface as "Coupon:" and is not a multi-buy offer, so
# putting it in volume_deals_description would describe it as something it is
# not. Both go to the digital column, and the prefix is kept as rendered.
DIGITAL_PREFIXES = ("coupon:", "cash back:", "cashback:")


def split_deals(deal_lines):
    """Return (volume, digital) as the retailer rendered them.

    Lines that are not offers are dropped here as well as in the parser. The
    parser is the one implementation of that judgement and this calls it, so a
    `parsed.json` produced before the parser distinguished them merges to the
    same result as one produced after. Without that, re-merging an older page
    read would reintroduce "Low Stock" into volume_deals_description.
    """
    offers = [x for x in deal_lines if classify_card_line(x) == "deal"]
    volume = [x for x in offers
              if not x.lower().lstrip().startswith(DIGITAL_PREFIXES)]
    digital = [x for x in offers
               if x.lower().lstrip().startswith(DIGITAL_PREFIXES)]
    return "; ".join(volume), "; ".join(digital)


class _Spine:
    """Yields the already-collected API records as one page.

    The sweep has already run and its output is on disk. Re-fetching it would
    be a second collection, not a merge, so this replays what was collected.
    """

    def __init__(self, records, store):
        self.records = records
        self.store = store
        self.unresolved_offers = []

    def fetch(self, store, category, url, cursor):
        return Page(
            store_id=store.store_id,
            zipcode=store.zipcode,
            store_context_verified=True,
            source_url=url,
            products=self.records,
            children=[],
            next_cursor="",
            subcategories_complete=False,
        )


def build_lookup(page_records, store_id, observed_at):
    """Index the page read by UPC and return a composition lookup."""
    by_upc = {}
    for rec in page_records:
        upc = (rec.get("upc") or "").strip()
        if upc:
            by_upc.setdefault(upc, rec)

    def lookup(store, identity, product):
        rec = by_upc.get(identity)
        if not rec:
            return {}
        volume, digital = split_deals(rec.get("deal_lines") or [])
        out = {}
        if rec.get("ppm"):
            out["ppm"] = rec["ppm"]
        if volume:
            out["volume_deals_description"] = volume
        if digital:
            out["digital_deals_description"] = digital
        if not out:
            return {}
        out[BINDING_KEY] = {
            "identity": identity,
            "store_id": store_id,
            "fulfillment": "pickup",
            "observed_at": observed_at,
        }
        return out

    return lookup, by_upc


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--api", required=True, help="data_22_fields.json from the sweep")
    p.add_argument("--page", required=True, help="parsed_full.json from the page read")
    p.add_argument("--store-id", default="53100502")
    p.add_argument("--zipcode", default="60061")
    p.add_argument("--store-name", default="Marianos - Marianos Vernon Hills")
    p.add_argument("--store-location", default="1720 N Milwaukee Ave, Vernon Hills, IL 60061")
    p.add_argument("--observed-at", default="2026-11-01",
                   help="When the pages were read. Must parse and be within the "
                        "composition freshness window, or contributions are refused "
                        "and retained as history instead of merged.")
    p.add_argument("--out", required=True, help="Output directory")
    args = p.parse_args(argv)

    api = json.loads(Path(args.api).read_text(encoding="utf-8"))
    page = json.loads(Path(args.page).read_text(encoding="utf-8"))

    store = Store(store_id=args.store_id, zipcode=args.zipcode,
                  store_name=args.store_name, store_location=args.store_location)

    wrong_store = sorted({r.get("store_name", "") for r in api
                          if r.get("store_name") and r.get("store_name") != args.store_name})
    if wrong_store:
        raise SystemExit(
            "Refusing to merge: the API set carries other store names: "
            f"{wrong_store}. A page read at one store must never be merged "
            "onto another store's rows."
        )

    lookup, by_upc = build_lookup(page, args.store_id, args.observed_at)
    crawl = CallableEnrichment("crawl", CRAWL_FIELDS, lookup)
    # The spine here is a replay of finished 22-field records, which carry no
    # fulfilment column, so the required fulfilment is stated explicitly. The
    # composition refuses a contribution whose fulfilment it cannot determine,
    # and it should: a value not tied to a fulfilment is not tied to anything.
    composite = CompositeSource(_Spine(api, store), "kroger_public",
                                enrichments=[crawl], policy=POLICY,
                                required_fulfillment="pickup")

    class _Cat:
        name = "all"

    merged = composite.fetch(store, _Cat(), "replay://sweep-vernon-hills", "").products

    api_upcs = {(r.get("upc") or "").strip() for r in api if (r.get("upc") or "").strip()}
    page_upcs = set(by_upc)
    unmatched = sorted(page_upcs - api_upcs)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "data_22_fields_enriched.json").write_text(
        json.dumps(merged, indent=1, ensure_ascii=False), encoding="utf-8")

    prov = composite.provenance_report()
    (out / "provenance.json").write_text(
        json.dumps(prov, indent=1, ensure_ascii=False), encoding="utf-8")

    filled = Counter()
    for field_name in CRAWL_FIELDS:
        filled[field_name] = sum(1 for r in merged if str(r.get(field_name, "")).strip())

    report = {
        "api_records": len(api),
        "page_records": len(page),
        "page_distinct_upcs": len(page_upcs),
        "page_upcs_matched_in_api": len(page_upcs & api_upcs),
        "page_upcs_not_in_api": len(unmatched),
        "page_upcs_not_in_api_sample": unmatched[:20],
        "fields_populated_after_merge": dict(filled),
        "values_by_field_and_source": prov["values_by_field_and_source"],
        "conflicts": prov["conflict_count"],
        "refused_as_unbound": prov["contributions_refused_as_unbound"],
        # A re-run against page data older than the composition's freshness
        # window refuses every contribution and would otherwise look like a
        # successful merge that simply found nothing. Say so instead.
        "all_contributions_refused": bool(page) and filled["ppm"] == 0
        and bool(prov["contributions_refused_as_unbound"]),
        "store": {"store_id": args.store_id, "zipcode": args.zipcode,
                  "store_name": args.store_name},
        "does_not_establish": [
            "Coverage. Only products the page read reached carry these fields; "
            "the rest keep empty strings and are not removed.",
            "Category completeness. The spine is a term-filtered sweep and "
            "cannot attest complete category discovery.",
            "That the page and API prices agree. Price is not taken from the "
            "page; any disagreement would be recorded, not resolved.",
        ],
    }
    (out / "merge_report.json").write_text(
        json.dumps(report, indent=1, ensure_ascii=False), encoding="utf-8")

    print(json.dumps({k: v for k, v in report.items()
                      if k not in ("page_upcs_not_in_api_sample", "does_not_establish")},
                     indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
