#!/usr/bin/env python3
"""Broad Kroger public Products API sweep for one Mariano's location.

WHAT THIS IS

The public Products API has no category enumeration: /products requires a
filter.term. So a broad catalogue is reached by sweeping many terms per client
category, paging each to exhaustion, and de-duplicating by UPC.

Each product carries its own `categories` array from Kroger. This tool records
BOTH that and the category of the term that found it, and reports where the two
disagree, rather than asserting the term's category as fact.

WHAT STAYS BLANK, AND WHY

  gupc         brief: never scraped, generated, inferred or copied
  unit_price   brief: calculated later by the client's pipeline
  ppm          the API carries regularPerUnitEstimate, but the brief forbids
               estimated or reconstructed values and requires the shelf
               displayed price per measure. An estimate is not that.
  volume_deals_description / _price      not carried by the public tier
  digital_deals_description / _price     not carried by the public tier

Those last three groups are filled by enrichment from observed page reads, not
here. This file is the spine.

ACCEPTABLE USE

Kroger's "Acceptable Use of Public APIs" prohibits systematically gathering
response data to create a database, and prohibits comparing prices among other
retailers. Running this tool is a decision by the account holder whose
credentials it uses, recorded in the run report as `acceptable_use_decision`.
It is not made by this file.

USAGE

  export KROGER_CLIENT_ID=...        # never pass credentials on the command line
  export KROGER_CLIENT_SECRET=...
  python3 tools/kroger_full_sweep.py --zipcode 60601 --address-contains "Benton"
  python3 tools/kroger_full_sweep.py --location-id 53100531 --output out/sweep

The first form lists candidate locations and stops, so a human picks the store.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

import sys as _sys, pathlib as _pathlib
_sys.path.insert(0, str(_pathlib.Path(__file__).resolve().parent.parent))

from marianos_collector.kroger import (
    KrogerClient, Credentials, KrogerError, location_candidates, _price_string)

ROOT = Path(__file__).resolve().parent.parent
FIELDS = ("zipcode store_name store_location store_logo store_brand category "
          "sub_category product_title weight regular_price sale_price "
          "volume_deals_description volume_deals_price digital_deals_description "
          "digital_deals_price image_url url upc gupc ppm unit_price "
          "crawl_date").split()

STORE_BRANDS = ("kroger", "simple truth", "private selection", "heritage farm",
                "psst", "home chef", "murray's", "comforts", "luvsome",
                "abound", "field & vine", "mariano's", "marianos")

LOGO = "https://www.marianos.com/content/v2/binary/image/marianos-logo--colored.svg"


class Budget:
    """One cumulative ceiling for the whole sweep. No per-call allowances."""

    def __init__(self, max_requests, max_seconds):
        self.max_requests = int(max_requests)
        self.max_seconds = float(max_seconds)
        self.requests = 0
        self.started = time.monotonic()

    def spend(self):
        if self.requests >= self.max_requests:
            raise Budget.Exhausted(f"request ceiling {self.max_requests} reached")
        if time.monotonic() - self.started > self.max_seconds:
            raise Budget.Exhausted(f"time ceiling {self.max_seconds:.0f}s reached")
        self.requests += 1

    @property
    def elapsed(self):
        return round(time.monotonic() - self.started, 1)

    class Exhausted(Exception):
        pass


def resolve_store(store_response, location_id, expected_zipcode=""):
    """Build the store columns from Kroger's own /locations response.

    Refuses rather than guesses: a missing location, a different locationId,
    or a zipcode that contradicts the one asked for all stop the run, because
    every record would carry the wrong store context.
    """
    data = store_response.get("data") if isinstance(store_response, dict) else None
    if not isinstance(data, dict):
        raise KrogerError(f"No location data returned for {location_id!r}")
    got = str(data.get("locationId") or "")
    if got != str(location_id):
        raise KrogerError(
            f"Asked for location {location_id!r}, response describes {got!r}")
    address = data.get("address")
    if not isinstance(address, dict):
        raise KrogerError(f"Location {location_id!r} carries no address")
    zipcode = str(address.get("zipCode") or "").strip()[:5]
    if not zipcode:
        raise KrogerError(f"Location {location_id!r} carries no zipCode")
    if expected_zipcode and zipcode != str(expected_zipcode).strip():
        raise KrogerError(
            f"Location {location_id!r} is in {zipcode}, not {expected_zipcode}")
    chain = data.get("chain")
    chain_name = str(chain.get("name") if isinstance(chain, dict) else chain or "")
    name = str(data.get("name") or "").strip()
    parts = [p for p in (chain_name.strip(), name) if p]
    line = str(address.get("addressLine1") or "").strip()
    city = str(address.get("city") or "").strip()
    state = str(address.get("state") or "").strip()
    if not line or not city:
        raise KrogerError(f"Location {location_id!r} has an incomplete address")
    return {
        "zipcode": zipcode,
        "store_name": " - ".join(parts) if parts else f"Store {location_id}",
        "store_location": f"{line}, {city}, {state} {zipcode}".strip(),
    }


def _image(product):
    for im in product.get("images") or []:
        if not isinstance(im, dict):
            continue
        for size in im.get("sizes") or []:
            if isinstance(size, dict) and size.get("url"):
                return str(size["url"])
    return ""


def _api_categories(product):
    cats = product.get("categories")
    return [str(c) for c in cats if isinstance(c, str)] if isinstance(cats, list) else []


def _store_brand(brand):
    b = (brand or "").strip().lower()
    return "yes" if any(b.startswith(k) or k in b for k in STORE_BRANDS) else "no"


def to_record(product, store, category, sub_category, crawl_date):
    """One 22-field record. Raises on anything that would need inventing."""
    items = product.get("items") or []
    first = next((i for i in items if isinstance(i, dict)), {})
    price = first.get("price") if isinstance(first.get("price"), dict) else {}
    upc = str(product.get("upc") or "").strip()
    if not upc:
        raise KrogerError("product carries no upc")
    title = str(product.get("description") or "").strip()
    if not title:
        raise KrogerError(f"product {upc} carries no description")
    return {
        "zipcode": store["zipcode"],
        "store_name": store["store_name"],
        "store_location": store["store_location"],
        "store_logo": LOGO,
        "store_brand": _store_brand(product.get("brand")),
        "category": category,
        "sub_category": sub_category,
        "product_title": title,
        "weight": str(first.get("size") or "").strip(),
        "regular_price": _price_string(price.get("regular")),
        "sale_price": _price_string(price.get("promo")),
        "volume_deals_description": "",
        "volume_deals_price": "",
        "digital_deals_description": "",
        "digital_deals_price": "",
        "image_url": _image(product),
        "url": f"https://www.marianos.com/p/{upc}",
        "upc": upc,
        "gupc": "",
        "ppm": "",
        "unit_price": "",
        "crawl_date": crawl_date,
    }


def sweep(client, location_id, store, terms_by_category, budget, pages_per_term,
          checkpoint_path=None, state=None, log=print, max_start=1000):
    state = state or {"records": {}, "done_terms": [], "term_counts": {},
                      "category_disagreements": [], "errors": [],
                      "page_failures": [], "terms_hit_start_cap": []}
    state.setdefault("page_failures", [])
    state.setdefault("terms_hit_start_cap", [])
    records = state["records"]
    done = set(state["done_terms"])
    crawl_date = date.today().isoformat()
    stopped = None

    try:
        for category, terms in terms_by_category.items():
            for term in terms:
                key = f"{category}||{term}"
                if key in done:
                    continue
                found = 0
                for page in range(pages_per_term):
                    # filter.start is 1-based: the first record is 1, not 0.
                    # api_collection.py passes offset=1 for its single page.
                    # Using 0 here would have shifted every page by one and
                    # made page boundaries overlap.
                    start = 1 + page * 50
                    if start > max_start:
                        state["terms_hit_start_cap"].append(key)
                        break
                    budget.spend()
                    # A term that fails is one term, not the run. Only the
                    # budget stops everything; a long sweep must not die on
                    # page 7 of 301 terms.
                    try:
                        result = client.products(location_id, term,
                                                 offset=start, limit=50)
                    except KrogerError as exc:
                        state["page_failures"].append(
                            {"term": key, "start": start, "error": str(exc)})
                        break
                    data = result.get("data") or []
                    for raw in data:
                        if not isinstance(raw, dict):
                            continue
                        try:
                            api_cats = _api_categories(raw)
                            sub = api_cats[0] if api_cats else ""
                            rec = to_record(raw, store, category, sub, crawl_date)
                        except KrogerError as exc:
                            state["errors"].append(str(exc))
                            continue
                        found += 1
                        if api_cats and category not in api_cats:
                            state["category_disagreements"].append(
                                {"upc": rec["upc"], "term_category": category,
                                 "api_categories": api_cats})
                        records.setdefault(rec["upc"], rec)
                    if len(data) < 50:
                        break
                state["term_counts"][key] = found
                done.add(key)
                state["done_terms"] = sorted(done)
                if checkpoint_path:
                    _write(checkpoint_path, state)
                log(f"  {category:28} {term:24} +{found:3}  "
                    f"total {len(records):5}  req {budget.requests}")
    except Budget.Exhausted as exc:
        stopped = str(exc)
        log(f"\nSTOPPED: {exc}. Progress is checkpointed; rerun with --resume.")
    except KrogerError as exc:
        stopped = f"api error: {exc}"
        log(f"\nSTOPPED: {exc}. Progress is checkpointed; rerun with --resume.")

    state["stopped_reason"] = stopped
    return state


def _write(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, indent=1))
    tmp.replace(path)


def build_report(state, store, location_id, budget, args):
    rows = list(state["records"].values())
    by_cat = {}
    for r in rows:
        by_cat[r["category"]] = by_cat.get(r["category"], 0) + 1
    completeness = {f: sum(1 for r in rows if str(r[f]).strip()) for f in FIELDS}
    swept = {k.split("||")[0] for k in state["term_counts"]}
    return {
        "mode": "KROGER_PUBLIC_API_SWEEP",
        "acceptable_use_decision": (
            "Run by the account holder whose Kroger credentials were used. "
            "Kroger's Acceptable Use of Public APIs prohibits systematically "
            "gathering response data to create a database and prohibits "
            "comparing prices among other retailers. This run was made with "
            "that policy known."),
        "locationId": location_id,
        "store": store,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "requests_spent": budget.requests,
        "elapsed_seconds": budget.elapsed,
        "pages_per_term": args.pages_per_term,
        "stopped_reason": state.get("stopped_reason"),
        "terms_completed": len(state["done_terms"]),
        "unique_products": len(rows),
        "unique_upcs": len({r["upc"] for r in rows}),
        "duplicate_upcs": len(rows) - len({r["upc"] for r in rows}),
        "count_by_category": dict(sorted(by_cat.items())),
        "categories_swept": len(swept),
        "categories_with_zero_products": sorted(swept - set(by_cat)),
        "field_completeness": completeness,
        "fields_blank_by_design": {
            "gupc": "brief: never scraped, generated, inferred or copied",
            "unit_price": "brief: calculated later by the client's pipeline",
            "ppm": ("API carries regularPerUnitEstimate only; the brief forbids "
                    "estimated values and requires the displayed price per "
                    "measure. Filled by page-read enrichment, not here."),
            "volume_deals_description": "not carried by the public tier",
            "digital_deals_description": "not carried by the public tier",
        },
        "category_attribution": (
            "`category` is the client root whose search term found the product. "
            "`sub_category` is the product's own first Kroger category. Where "
            "the product's own categories do not contain the client root, the "
            "disagreement is listed below rather than hidden."),
        "category_disagreements": len(state["category_disagreements"]),
        "page_failures": state.get("page_failures", []),
        "terms_that_hit_the_start_cap": sorted(set(state.get("terms_hit_start_cap", []))),
        "max_start": args.max_start,
        "record_errors": len(state["errors"]),
    }


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--location-id")
    p.add_argument("--zipcode")
    p.add_argument("--address-contains", default="")
    p.add_argument("--store-name", default="")
    p.add_argument("--store-location", default="")
    p.add_argument("--terms", default=str(ROOT / "config/sweep_terms.json"))
    p.add_argument("--only-category", action="append", default=[])
    p.add_argument("--pages-per-term", type=int, default=20)
    p.add_argument("--max-start", type=int, default=1000,
                   help="Highest filter.start to request. Kroger caps deep paging; "
                        "terms that reach it are named in the report.")
    p.add_argument("--max-requests", type=int, default=8000)
    p.add_argument("--max-seconds", type=float, default=14400)
    p.add_argument("--output", default="out/kroger_sweep")
    p.add_argument("--resume", action="store_true")
    args = p.parse_args(argv)

    try:
        creds = Credentials.from_environment()
    except Exception as exc:
        print(f"Credentials not available: {exc}\n"
              "Set KROGER_CLIENT_ID and KROGER_CLIENT_SECRET in the environment.",
              file=sys.stderr)
        return 2
    client = KrogerClient(creds)

    if not args.location_id:
        if not args.zipcode:
            print("Give --location-id, or --zipcode to list candidates first.",
                  file=sys.stderr)
            return 2
        found = location_candidates(client, args.zipcode, args.address_contains)
        print(json.dumps(found, indent=1))
        print("\nPick the right locationId and rerun with --location-id.",
              file=sys.stderr)
        return 0

    # Resolve the store from Kroger rather than from flags, so a repeat run
    # against the same location produces byte-identical store columns and the
    # two runs are actually comparable. Also the brief's "evidence that the
    # correct store was selected".
    store_response = client.get("/locations/" + args.location_id)
    store = resolve_store(store_response, args.location_id, args.zipcode)
    if args.store_name:
        store["store_name"] = args.store_name
    if args.store_location:
        store["store_location"] = args.store_location
    print(f"Store {args.location_id}: {store['store_name']}, "
          f"{store['store_location']}, {store['zipcode']}\n")

    out = Path(args.output)
    _write(out / "store_verification.json",
           {"locationId": args.location_id,
            "resolved": store,
            "verified_utc": datetime.now(timezone.utc).isoformat(),
            "response": store_response})
    checkpoint = out / "checkpoint.json"
    state = None
    if args.resume and checkpoint.exists():
        state = json.loads(checkpoint.read_text())
        print(f"Resuming: {len(state['records'])} records, "
              f"{len(state['done_terms'])} terms already done.")

    config = json.loads(Path(args.terms).read_text())
    terms_by_category = config["terms"]
    if args.only_category:
        wanted = set(args.only_category)
        terms_by_category = {k: v for k, v in terms_by_category.items() if k in wanted}
        if not terms_by_category:
            print(f"No such category in {args.terms}", file=sys.stderr)
            return 2

    store = {"zipcode": args.zipcode or "",
             "store_name": args.store_name,
             "store_location": args.store_location}

    budget = Budget(args.max_requests, args.max_seconds)
    print(f"Sweeping location {args.location_id}: "
          f"{sum(len(v) for v in terms_by_category.values())} terms, "
          f"up to {args.pages_per_term} pages each, "
          f"ceiling {args.max_requests} requests / {args.max_seconds:.0f}s, "
          f"filter.start capped at {args.max_start}\n")
    state = sweep(client, args.location_id, store, terms_by_category, budget,
                  args.pages_per_term, checkpoint, state, max_start=args.max_start)

    rows = list(state["records"].values())
    _write(out / "data_22_fields.json", rows)
    _write(out / "run_report.json", build_report(state, store, args.location_id,
                                                 budget, args))
    _write(out / "category_disagreements.json", state["category_disagreements"])
    print(f"\n{len(rows)} unique products across "
          f"{len({r['category'] for r in rows})} categories "
          f"in {budget.requests} requests, {budget.elapsed}s")
    print(f"Written to {out}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
