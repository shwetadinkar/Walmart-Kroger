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

WHAT IS KEPT, AND WHAT IS EXCLUDED

A product is never removed because a field is missing or a status is
unfavourable. One with no pickup offer, no price or no UPC stays in the export
with empty strings, and pickup_context.json says why, record by record, along
with the fulfillment flags, sold-by and stock level Kroger returned beside the
price. Only what the brief itself excludes, such as approximate-weight wording,
goes to quarantine.json with its reason. Products absent from a later run carry
forward with their original dates through --previous-run; retention.json keeps
them distinguishable from fresh observations.

Each raw response is kept under raw/, so a later rule change is a re-filter of
what was already fetched, not a re-fetch. Raw responses carry Kroger's `cid`
and must not ship.

STORE VERIFICATION

A configured id is not verification. --location-id, --zipcode and --street are
all required, and the run refuses a /locations response that contradicts any
of them or names another banner, before any product is requested.

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
  python3 tools/kroger_full_sweep.py --location-id 53100502 --zipcode 60061 \\
      --street "1720 N Milwaukee Ave" --output out/sweep

The first form lists candidate locations and stops, so a human picks the store.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import sys as _sys, pathlib as _pathlib
_sys.path.insert(0, str(_pathlib.Path(__file__).resolve().parent.parent))

from marianos_collector.api_trial import api_categories, observe, verify_store
from marianos_collector.config import Store
from marianos_collector.kroger import (
    KrogerClient, Credentials, KrogerError, location_candidates)
from marianos_collector.retention import observation, reconcile, stable_identity
from marianos_collector.schema import FIELDS
# One implementation of the sweep, shared with the collector Source. It used
# to live here, which is why the delivered records never passed through the
# runner's gates.
from marianos_collector.sweep_core import (
    MAX_START, REQUESTED_FULFILLMENT, STATE_VERSION, Budget, _quarantine,
    _raw_path, _street_key, _write, resolve_store, short_of_reported_total,
    sweep)

ROOT = Path(__file__).resolve().parent.parent

# filter.start is a skip count. Eight live requests on 31 October 2026 showed it:
# no parameter and 0 return the same first page, 1 drops the first product, 2 the
# first two, 250 works and 251 is HTTP 400. So pages start at 0, 50 ... 250, and a
# term reaches at most 300 products.

# Bump when records change meaning. A checkpoint from another version holds
# records built under other rules, and resuming would mix the two in one output.

# kroger.KrogerClient.products sends this as filter.fulfillment. Kroger therefore
# returns only products it holds for in-store or curbside at the location, so a
# product offered neither way never reaches the retention rules at all.


















def _does_not_establish(state, rows, by_cat, max_start):
    """What this run cannot show, from what it actually returned."""
    truncated = sorted(set(state["terms_hit_start_cap"])
                       | {f["term"] for f in state["page_failures"]})
    empty_roots = {}
    if not by_cat.get("Seafood"):
        merged = sum(1 for r in rows if r["sub_category"] == "Meat & Seafood")
        empty_roots["Seafood"] = (
            "Kroger files seafood under the single label 'Meat & Seafood', which "
            f"maps to Meat. Seafood cannot be separated from the {merged} records "
            "carrying that label, so this count does not measure seafood.")
    if not by_cat.get("Coffee"):
        labelled = sum(1 for d in state["discovery"].values()
                       if "Coffee" in d["api_categories"])
        empty_roots["Coffee"] = (
            f"{labelled} products carried a Kroger 'Coffee' label, and only that "
            "label reaches this root. Coffee products may be present under other "
            "labels, so this count does not measure coffee.")
    return {
        "complete_category_discovery": (
            "Term-filtered search cannot attest complete category discovery. The "
            "public API has no category enumeration, so a product no term matched "
            "is absent, and nothing here measures how many such products exist."),
        "complete_results_per_term": {
            "limit_per_term": max_start + 50,
            "explanation": (
                f"filter.start is a skip count and Kroger refuses more than 250, so "
                f"a term yields at most {max_start + 50} products. The terms below "
                "reported more than that, or stopped on a failed page, so their "
                "results are truncated."),
            "truncated_terms": truncated,
            "short_of_reported_total": short_of_reported_total(state),
        },
        "populated_roots": empty_roots,
        "products_kroger_did_not_return": (
            f"Requests carry filter.fulfillment={REQUESTED_FULFILLMENT}, so a product "
            "Kroger holds for neither in-store nor curbside at this location is "
            "not returned, and no rule here can retain what was never seen."),
        "displayed_prices_and_deals": {
            "ppm": ("Blank. The public tier carries only regularPerUnitEstimate, "
                    "an estimate and not the displayed price per measure."),
            "volume_deals_description": "Blank. Not carried by the public tier.",
            "volume_deals_price": "Blank. Not carried by the public tier.",
            "digital_deals_description": "Blank. Not carried by the public tier.",
            "digital_deals_price": "Blank. Not carried by the public tier.",
        },
    }


def build_report(state, store, location_id, budget, args, accumulated):
    rows = accumulated["products"]
    contexts = list(state["contexts"].values())
    by_cat = {}
    for r in rows:
        by_cat[r["category"]] = by_cat.get(r["category"], 0) + 1
    completeness = {f: sum(1 for r in rows if str(r[f]).strip()) for f in FIELDS}
    swept = {k.split("||")[0] for k in state["term_counts"]}
    return {
        "mode": "KROGER_PUBLIC_API_SWEEP",
        "acceptable_use_decision": (
            "Run on the instruction of the account holder whose Kroger credentials were used. "
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
        "unique_upcs": len({r["upc"] for r in rows if r["upc"]}),
        "records_without_upc": sum(1 for r in rows if not r["upc"]),
        "duplicate_upcs": sum(1 for r in rows if r["upc"]) - len({r["upc"] for r in rows if r["upc"]}),
        "upc_collisions": accumulated.get("upc_collisions", []),
        "duplicate_placements_collapsed": sum(state["term_counts"].values()) - len(state["records"]),
        "current_records": accumulated["current_records"],
        "carried_forward_records": accumulated["carried_forward_records"],
        "offer_status": dict(sorted(Counter(c["offer_status"] for c in contexts).items())),
        "offer_gaps": dict(sorted(Counter(g for c in contexts for g in c["offer_gaps"]).items())),
        "identity_basis": dict(sorted(Counter(c["identity_basis"] for c in contexts).items())),
        "availability_state": dict(sorted(Counter(c["availability_state"] for c in contexts).items())),
        "values_refused": dict(sorted(Counter(
            v["reason"] for c in contexts for v in c["value_refusals"]).items())),
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
            "`category` is the client root that the product's OWN Kroger "
            "category maps to, via config/category_map.json. `sub_category` is "
            "that raw Kroger label. The search term is how a product was found, "
            "not what it is, and is recorded per product in "
            "discovery_provenance.json instead. A Kroger label with no mapping "
            "leaves `category` empty and is listed in unmapped_categories.json "
            "rather than being guessed into a root."),
        "records_with_unmapped_category": sum(
            len(v) for v in state.get("unmapped", {}).values()),
        "unmapped_labels": sorted(state.get("unmapped", {})),
        "category_disagreements": len(state["category_disagreements"]),
        "page_failures": state.get("page_failures", []),
        "terms_that_hit_the_start_cap": sorted(set(state.get("terms_hit_start_cap", []))),
        "max_start": args.max_start,
        "record_errors": len(state["errors"]),
        "does_not_establish": _does_not_establish(state, rows, by_cat, args.max_start),
        "quarantined_products": len(state["quarantine"]),
        "quarantine_reasons": dict(sorted(Counter(
            q["reason"] for q in state["quarantine"].values()).items())),
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
    p.add_argument("--category-map", default=str(ROOT / "config/category_map.json"))
    p.add_argument("--only-category", action="append", default=[])
    p.add_argument("--pages-per-term", type=int, default=20)
    p.add_argument("--max-start", type=int, default=MAX_START,
                   help="Highest filter.start to request. Kroger refuses 251. "
                        "Terms that reach this limit are named in the report.")
    p.add_argument("--max-requests", type=int, default=8000)
    p.add_argument("--max-seconds", type=float, default=14400)
    p.add_argument("--street", default="",
                   help="Street address the location must report, e.g. "
                        "'1720 N Milwaukee Ave'. Required with --location-id.")
    p.add_argument("--store-logo", default="",
                   help="The retailer's logo URL, if one has been observed. Neither "
                        "Kroger API supplies one, so the field is blank without it.")
    p.add_argument("--previous-run", default="",
                   help="Output folder of an earlier run at this same store, whose "
                        "products carry forward if absent from this one.")
    p.add_argument("--output", default="out/kroger_sweep")
    p.add_argument("--resume", action="store_true")
    args = p.parse_args(argv)
    logo = urlparse(args.store_logo)
    if args.store_logo and (logo.scheme != "https" or not (
            logo.hostname == "marianos.com" or str(logo.hostname).endswith(".marianos.com"))):
        p.error("--store-logo must be an https URL on marianos.com")

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

    if not args.zipcode or not args.street:
        print("--location-id needs --zipcode and --street: a configured id alone "
              "is not verification.", file=sys.stderr)
        return 2

    # Before any network call or write, so a mistaken rerun leaves the earlier
    # run's folder exactly as it was.
    out = Path(args.output)
    checkpoint = out / "checkpoint.json"
    state = None
    if checkpoint.exists():
        if not args.resume:
            print(f"{checkpoint} already exists. Use --resume to continue that "
                  "run, or a new --output.", file=sys.stderr)
            return 2
        state = json.loads(checkpoint.read_text())
        if state.get("state_version") != STATE_VERSION:
            print(f"{checkpoint} was written under different record rules and "
                  "cannot be resumed. Use a new --output.", file=sys.stderr)
            return 2

    # Resolve the store from Kroger rather than from flags, so a repeat run
    # against the same location produces byte-identical store columns and the
    # two runs are actually comparable. Also the brief's "evidence that the
    # correct store was selected".
    store_response = client.get("/locations/" + args.location_id)
    store = resolve_store(store_response, args.location_id, args.zipcode, args.street)
    verify_store(store_response["data"], args.location_id, store["zipcode"])
    if args.store_name:
        store["store_name"] = args.store_name
    if args.store_location:
        store["store_location"] = args.store_location
    print(f"Store {args.location_id}: {store['store_name']}, "
          f"{store['store_location']}, {store['zipcode']}\n", flush=True)

    _write(out / "store_verification.json",
           {"locationId": args.location_id,
            "resolved": store,
            "verified_utc": datetime.now(timezone.utc).isoformat(),
            "response": store_response})
    if state:
        print(f"Resuming: {len(state['records'])} records, "
              f"{len(state['done_terms'])} terms already done.")

    config = json.loads(Path(args.terms).read_text())
    terms_by_category = config["terms"]
    category_map = json.loads(Path(args.category_map).read_text())["map"]
    if args.only_category:
        wanted = set(args.only_category)
        terms_by_category = {k: v for k, v in terms_by_category.items() if k in wanted}
        if not terms_by_category:
            print(f"No such category in {args.terms}", file=sys.stderr)
            return 2

    budget = Budget(args.max_requests, args.max_seconds)
    print(f"Sweeping location {args.location_id}: "
          f"{sum(len(v) for v in terms_by_category.values())} terms, "
          f"up to {args.pages_per_term} pages each, "
          f"ceiling {args.max_requests} requests / {args.max_seconds:.0f}s, "
          f"filter.start capped at {args.max_start}\n", flush=True)
    record_store = Store(args.location_id, store["zipcode"], store["store_name"],
                         store["store_location"], args.store_logo)
    state = sweep(client, args.location_id, record_store, terms_by_category, budget,
                  args.pages_per_term, checkpoint, state,
                  max_start=args.max_start, category_map=category_map,
                  raw_dir=out / "raw")

    previous_rows, previous_retention = [], {}
    if args.previous_run:
        previous = Path(args.previous_run)
        previous_rows = json.loads((previous / "data_22_fields.json").read_text())
        previous_retention = json.loads((previous / "retention.json").read_text())
    accumulated = reconcile(
        list(state["records"].values()), state["observations"], args.location_id,
        datetime.now(timezone.utc).isoformat(), previous_rows, previous_retention,
        expected_context=(store["zipcode"], store["store_location"]),
        upc_collisions="record")
    rows = accumulated["products"]
    _write(out / "data_22_fields.json", rows)
    _write(out / "retention.json", accumulated["retention"])
    _write(out / "pickup_context.json", state["contexts"])
    _write(out / "run_report.json", build_report(state, store, args.location_id,
                                                 budget, args, accumulated))
    _write(out / "category_disagreements.json", state["category_disagreements"])
    _write(out / "unmapped_categories.json", state["unmapped"])
    _write(out / "discovery_provenance.json", state["discovery"])
    _write(out / "quarantine.json", state["quarantine"])
    print(f"\n{len(rows)} unique products across "
          f"{len({r['category'] for r in rows})} categories "
          f"in {budget.requests} requests, {budget.elapsed}s")
    print(f"Written to {out}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
