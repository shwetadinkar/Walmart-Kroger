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

ROOT = Path(__file__).resolve().parent.parent

# The first run, on 31 October 2026, got HTTP 400 at filter.start=251 on all 63
# terms that reached it, and never failed below it. 201 is the highest start
# that run saw succeed, so each term yields at most 250 products. Starts from
# 202 to 250 were not tried.
MAX_START = 201

# Bump when records change meaning. A checkpoint from another version holds
# records built under other rules, and resuming would mix the two in one output.
STATE_VERSION = 4

# kroger.KrogerClient.products sends this as filter.fulfillment. Kroger therefore
# returns only products it holds for in-store or curbside at the location, so a
# product offered neither way never reaches the retention rules at all.
REQUESTED_FULFILLMENT = "ais,csp"


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


def _street_key(street):
    return " ".join(str(street).replace(".", " ").casefold().split())


def resolve_store(store_response, location_id, expected_zipcode="", expected_street=""):
    """Build the store columns from Kroger's own /locations response.

    Refuses rather than guesses: a missing location, a different locationId,
    or a zipcode or street that contradicts the one asked for all stop the run,
    because every record would carry the wrong store context. The assigned id
    differs from West Loop's by two characters, so the address is asserted too.
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
    # Kroger's `name` often already carries the chain, e.g. chain "MARIANOS"
    # with name "Marianos - Marianos West Loop". Prepending the chain there
    # produces a triple and, worse, a store_name that no longer matches an
    # earlier run against the same store. Only prepend when it is absent.
    chain_name = chain_name.strip()
    if chain_name and name.lower().startswith(chain_name.lower()):
        parts = [name]
    else:
        parts = [p for p in (chain_name, name) if p]
    line = str(address.get("addressLine1") or "").strip()
    city = str(address.get("city") or "").strip()
    state = str(address.get("state") or "").strip()
    if not line or not city:
        raise KrogerError(f"Location {location_id!r} has an incomplete address")
    if expected_street and _street_key(line) != _street_key(expected_street):
        raise KrogerError(
            f"Location {location_id!r} is at {line!r}, not {expected_street!r}")
    return {
        "zipcode": zipcode,
        "store_name": " - ".join(parts) if parts else f"Store {location_id}",
        "store_location": f"{line}, {city}, {state} {zipcode}".strip(),
    }


def _raw_path(raw_dir, key, start):
    slug = re.sub(r"[^a-z0-9]+", "-", key.lower()).strip("-")
    digest = hashlib.sha256(key.encode()).hexdigest()[:8]
    return Path(raw_dir) / f"{slug}-{digest}" / f"start_{start:04d}.json"


def _quarantine(state, product, key, start, index, exc):
    """Keep a refused product's identity and reason; the body stays under raw/."""
    reason = str(exc) if isinstance(exc, ValueError) else f"MALFORMED_PRODUCT:{type(exc).__name__}"
    p = product if isinstance(product, dict) else {}
    ident = str(p.get("productId") or p.get("upc") or f"{key}@{start}#{index}")
    entry = state["quarantine"].setdefault(ident, {
        "upc": str(p.get("upc") or ""), "productId": str(p.get("productId") or ""),
        "description": str(p.get("description") or ""), "reason": reason,
        "found_by": []})
    entry["found_by"].append(key)


def sweep(client, location_id, store, terms_by_category, budget, pages_per_term,
          checkpoint_path=None, state=None, log=print, max_start=MAX_START,
          category_map=None, raw_dir=None):
    category_map = category_map or {}
    state = state or {"state_version": STATE_VERSION,
                      "records": {}, "done_terms": [], "term_counts": {},
                      "category_disagreements": [], "errors": [],
                      "page_failures": [], "terms_hit_start_cap": [],
                      "unmapped": {}, "discovery": {}, "quarantine": {},
                      "contexts": {}, "observations": {}}
    records = state["records"]
    done = set(state["done_terms"])
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
                    # Written before anything reads it, so a rule that refuses
                    # a product can never cost the response that showed it.
                    observed_at = datetime.now(timezone.utc).isoformat()
                    raw_file = ""
                    if raw_dir:
                        path = _raw_path(raw_dir, key, start)
                        _write(path, {"locationId": location_id, "term": term,
                                      "term_root": category, "start": start,
                                      "observed_at": observed_at, "response": result})
                        raw_file = str(path.relative_to(raw_dir))
                    response_sha256 = hashlib.sha256(
                        json.dumps(result, sort_keys=True).encode()).hexdigest()
                    data = result.get("data") or []
                    for index, raw in enumerate(data):
                        # The search term is how a product was FOUND, not what
                        # it is. A probe of 17 Produce terms returned 2400
                        # products of which 2112 carried a different Kroger
                        # category. So the product's own label decides, via an
                        # explicit map, and an unmapped label is never guessed.
                        try:
                            rec, context = observe(raw, store, observed_at[:10], category_map)
                            identity = stable_identity(rec, location_id)
                        except (ValueError, TypeError, KeyError, AttributeError) as exc:
                            _quarantine(state, raw, key, start, index, exc)
                            continue
                        root, label = rec["category"], rec["sub_category"]
                        api_cats = api_categories(raw)
                        found += 1
                        state["discovery"][identity] = {
                            "found_by_term": term, "term_root": category,
                            "api_categories": api_cats, "assigned_root": root}
                        if identity not in records:
                            context.update(observed_at=observed_at, raw_file=raw_file,
                                           response_sha256=response_sha256,
                                           requested_fulfillment=REQUESTED_FULFILLMENT)
                            state["contexts"][identity] = context
                            state["observations"][identity] = dict(
                                observation(rec, location_id, observed_at,
                                            [{"kind": "api_response", "file": raw_file,
                                              "sha256": response_sha256, "url": rec["url"]}],
                                            context["availability_state"]),
                                pickup_context=context)
                        if not root:
                            state["unmapped"].setdefault(label or "(none)", []) \
                                .append(identity)
                            records.setdefault(identity, rec)
                            continue
                        if category and root != category:
                            state["category_disagreements"].append(
                                {"identity": identity, "upc": rec["upc"], "found_by_term": term,
                                 "term_root": category, "assigned_root": root,
                                 "api_categories": api_cats})
                        records.setdefault(identity, rec)
                    if len(data) < 50:
                        break
                state["term_counts"][key] = found
                done.add(key)
                state["done_terms"] = sorted(done)
                if checkpoint_path:
                    _write(checkpoint_path, state)
                log(f"  {category:28} {term:24} +{found:3}  "
                    f"total {len(records):5}  req {budget.requests}")
                sys.stdout.flush()
    except Budget.Exhausted as exc:
        stopped = str(exc)
        log(f"\nSTOPPED: {exc}. Progress is checkpointed; rerun with --resume.")
        sys.stdout.flush()
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
            "limit_per_term": max_start + 49,
            "explanation": (
                f"Requests stop at filter.start={max_start}, so a term yields at "
                f"most {max_start + 49} products. Kroger refused filter.start=251 "
                "with HTTP 400 on all 63 terms that reached it in the 31 October "
                "run. The terms below reached the limit or stopped on a failed "
                "page, so their results are truncated."),
            "truncated_terms": truncated,
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
        "unique_upcs": len({r["upc"] for r in rows if r["upc"]}),
        "records_without_upc": sum(1 for r in rows if not r["upc"]),
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
                   help="Highest filter.start to request. Kroger refused 251 on "
                        "every term that reached it; terms that reach this "
                        "limit are named in the report.")
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
        expected_context=(store["zipcode"], store["store_location"]))
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
