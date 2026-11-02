"""The Kroger public Products API term sweep, as importable code.

This lived in `tools/kroger_full_sweep.py`, which meant the 26,166 records
delivered on 31 October were produced outside the collector: no publication
gate, no retention reconciliation, no trial and published namespace
separation, and no resume driven by the runner. The client identified that gap
directly. The sweep now lives here so a Source can drive it and the tool can
keep importing it, with one implementation rather than two.

What the sweep can and cannot attest is unchanged by the move. The public API
has no category enumeration, `filter.start` is a skip count Kroger refuses
past 250, and a term therefore reaches at most 300 products however many exist
behind it. Any source built on this declares `coverage_attested = False`.
"""

import hashlib
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from .api_trial import api_categories, observe
from .kroger import KrogerError
from .retention import observation, stable_identity


# filter.start is a skip count. Eight live requests on 31 October 2026 showed
# it: no parameter and 0 return the same first page, 1 drops the first
# product, 250 works and 251 is HTTP 400. So pages start at 0, 50 ... 250, and
# a term reaches at most 300 products.
MAX_START = 250

# Bump when records change meaning. A checkpoint from another version holds
# records built under other rules, and resuming would mix the two.
STATE_VERSION = 5

# Sent as filter.fulfillment, so Kroger returns only products it holds for
# in-store or curbside at the location.
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
                    start = page * 50
                    if start > max_start:
                        # Only a limit if Kroger says there is more behind it.
                        if state.get("term_totals", {}).get(key, start + 1) > start:
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
                    pagination = (result.get("meta") or {}).get("pagination") or {}
                    if isinstance(pagination.get("total"), int):
                        state.setdefault("term_totals", {})[key] = pagination["total"]
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
                    # Kroger can return a short page with more behind it, so a
                    # short page ends a term only when no total says otherwise.
                    # That rule left "sugar" at 49 of a reported 1,000.
                    total = pagination.get("total")
                    if not data or (start + 50 >= total if isinstance(total, int)
                                    else len(data) < 50):
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

def short_of_reported_total(state):
    """Terms that ended below the limit with products Kroger said were there.

    The total is Kroger's figure and pages can run short, so a small difference
    may be nothing missing; what it establishes is only that the two disagree.
    """
    capped = set(state["terms_hit_start_cap"]) | {f["term"] for f in state["page_failures"]}
    short = [{"term": key, "reported_total": total, "received": state["term_counts"].get(key, 0)}
             for key, total in state.get("term_totals", {}).items() if key not in capped]
    return sorted((s for s in short if s["reported_total"] > s["received"]),
                  key=lambda s: s["term"])
