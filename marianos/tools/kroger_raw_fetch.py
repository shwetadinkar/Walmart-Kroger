#!/usr/bin/env python3
"""Fetch raw Kroger Products API responses and write them to disk. Nothing else.

WHY THIS EXISTS SEPARATELY

Network time is the slow part and rules are the part that changes. A sweep that
normalizes while it fetches throws the raw response away, so every later rule
change costs another full set of API calls. This tool only fetches and stores.
Normalization, filtering, category mapping and the 22-field schema are applied
afterwards, offline, against these files, as many times as needed.

It therefore applies NO rules. It does not map categories, build URLs, test for
a pickup offer, or decide what is publishable. Those belong downstream, where
they can be re-run for free.

OUTPUT

  <output>/manifest.json            what was requested, what came back
  <output>/pages/<term>__<start>.json   one raw response per page, verbatim
  <output>/store_verification.json  the /locations response for the store

Each page file is the API's response body unmodified, plus the term, start and
observation timestamp that produced it. Resuming skips pages already on disk,
so an interrupted run costs only the pages it had not reached.

USAGE

  source .env.kroger
  python3 tools/kroger_raw_fetch.py --location-id 53100508 --zipcode 60661 \
    --output out/raw-2026-10-31
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import sys as _sys, pathlib as _pathlib
_sys.path.insert(0, str(_pathlib.Path(__file__).resolve().parent.parent))

from marianos_collector.kroger import Credentials, KrogerClient, KrogerError

ROOT = Path(__file__).resolve().parent.parent
SCHEMA_VERSION = "raw-1"


def safe_name(term, start):
    """A filename that cannot escape the pages directory."""
    slug = re.sub(r"[^a-z0-9]+", "-", term.lower()).strip("-") or "term"
    return f"{slug[:48]}__{int(start):06d}.json"


def write_json(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=1))
    tmp.replace(path)


def fetch(client, location_id, terms_by_category, pages_dir, max_requests,
          max_seconds, max_start, pages_per_term, log=print):
    """Fetch every term to exhaustion. Returns a manifest, never raises on a page."""
    started = time.monotonic()
    requests = 0
    pages = []
    failures = []
    stopped = None

    for category, terms in terms_by_category.items():
        for term in terms:
            for page in range(pages_per_term):
                start = 1 + page * 50          # filter.start is 1-based
                if start > max_start:
                    failures.append({"term": term, "category": category,
                                     "start": start, "reason": "MAX_START"})
                    break

                target = pages_dir / safe_name(term, start)
                if target.exists():
                    # Already fetched by an earlier run. Read its count so
                    # pagination still terminates correctly on a resume.
                    try:
                        prior = json.loads(target.read_text())
                        pages.append({"term": term, "category": category,
                                      "start": start, "returned": prior["returned"],
                                      "file": target.name, "resumed": True})
                        if prior["returned"] < 50:
                            break
                        continue
                    except Exception:
                        pass                   # unreadable: refetch it

                if requests >= max_requests:
                    stopped = f"request ceiling {max_requests} reached"
                elif time.monotonic() - started > max_seconds:
                    stopped = f"time ceiling {max_seconds:.0f}s reached"
                if stopped:
                    log(f"\nSTOPPED: {stopped}. Rerun the same command to resume.")
                    return manifest(location_id, terms_by_category, pages,
                                    failures, requests, started, stopped,
                                    max_start, pages_per_term)

                requests += 1
                try:
                    body = client.products(location_id, term, offset=start, limit=50)
                except KrogerError as exc:
                    # One term failing is not the run. The failure is recorded
                    # because where Kroger refuses is itself a measurement.
                    failures.append({"term": term, "category": category,
                                     "start": start, "reason": str(exc)})
                    break

                data = body.get("data") or []
                write_json(target, {
                    "term": term, "term_category": category, "start": start,
                    "locationId": location_id,
                    "observed_at": datetime.now(timezone.utc).isoformat(),
                    "returned": len(data), "response": body})
                pages.append({"term": term, "category": category, "start": start,
                              "returned": len(data), "file": target.name})
                if len(data) < 50:
                    break

            got = sum(p["returned"] for p in pages if p["term"] == term)
            log(f"  {category:28} {term:24} {got:5} rows   req {requests}")
            sys.stdout.flush()

    return manifest(location_id, terms_by_category, pages, failures, requests,
                    started, stopped, max_start, pages_per_term)


def manifest(location_id, terms_by_category, pages, failures, requests, started,
             stopped, max_start, pages_per_term):
    by_reason = {}
    for f in failures:
        by_reason[f["reason"]] = by_reason.get(f["reason"], 0) + 1
    by_start = {}
    for f in failures:
        if f["reason"] != "MAX_START":
            by_start[f["start"]] = by_start.get(f["start"], 0) + 1
    return {
        "schema_version": SCHEMA_VERSION,
        "mode": "KROGER_PUBLIC_API_RAW_CAPTURE",
        "what_this_is_not": (
            "Raw API responses only. No rule of any kind has been applied: no "
            "category mapping, no product URL, no pickup-offer test, no "
            "approximate-weight exclusion, no schema validation. These files "
            "are not a dataset and nothing here is publishable as collected."),
        "locationId": location_id,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "requests_spent": requests,
        "elapsed_seconds": round(time.monotonic() - started, 1),
        "stopped_reason": stopped,
        "terms_requested": sum(len(v) for v in terms_by_category.values()),
        "terms_fetched": len({p["term"] for p in pages}),
        "pages_written": len(pages),
        "rows_returned_including_duplicates": sum(p["returned"] for p in pages),
        "max_start": max_start,
        "pages_per_term": pages_per_term,
        "failures": failures,
        "failures_by_reason": by_reason,
        "failures_by_start_value": dict(sorted(by_start.items())),
        "pages": pages,
    }


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--location-id", required=True)
    p.add_argument("--zipcode", default="")
    p.add_argument("--terms", default=str(ROOT / "config/sweep_terms.json"))
    p.add_argument("--only-category", action="append", default=[])
    p.add_argument("--pages-per-term", type=int, default=20)
    p.add_argument("--max-start", type=int, default=1000)
    p.add_argument("--max-requests", type=int, default=8000)
    p.add_argument("--max-seconds", type=float, default=14400)
    p.add_argument("--output", required=True)
    args = p.parse_args(argv)

    try:
        creds = Credentials.from_environment()
    except Exception as exc:
        print(f"Credentials not available: {exc}\n"
              "source .env.kroger first.", file=sys.stderr)
        return 2
    client = KrogerClient(creds)

    out = Path(args.output)
    pages_dir = out / "pages"
    pages_dir.mkdir(parents=True, exist_ok=True)

    store_response = client.get("/locations/" + args.location_id)
    data = store_response.get("data") or {}
    got = str(data.get("locationId") or "")
    if got != str(args.location_id):
        print(f"Asked for {args.location_id}, response describes {got!r}. Stopping.",
              file=sys.stderr)
        return 2
    zipcode = str((data.get("address") or {}).get("zipCode") or "")[:5]
    if args.zipcode and zipcode != args.zipcode:
        print(f"Location {args.location_id} is in {zipcode}, not {args.zipcode}. "
              "Stopping.", file=sys.stderr)
        return 2
    write_json(out / "store_verification.json",
               {"locationId": args.location_id,
                "verified_utc": datetime.now(timezone.utc).isoformat(),
                "response": store_response})
    print(f"Store {args.location_id}: {data.get('name')}, {zipcode}\n", flush=True)

    config = json.loads(Path(args.terms).read_text())
    terms_by_category = config["terms"]
    if args.only_category:
        wanted = set(args.only_category)
        terms_by_category = {k: v for k, v in terms_by_category.items() if k in wanted}

    print(f"Raw capture: {sum(len(v) for v in terms_by_category.values())} terms, "
          f"ceiling {args.max_requests} requests / {args.max_seconds:.0f}s, "
          f"filter.start capped at {args.max_start}\n", flush=True)

    m = fetch(client, args.location_id, terms_by_category, pages_dir,
              args.max_requests, args.max_seconds, args.max_start,
              args.pages_per_term)
    write_json(out / "manifest.json", m)
    print(f"\n{m['pages_written']} pages, "
          f"{m['rows_returned_including_duplicates']} rows including duplicates, "
          f"{m['requests_spent']} requests, {m['elapsed_seconds']}s")
    if m["failures_by_start_value"]:
        print(f"page failures by start value: {m['failures_by_start_value']}")
    print(f"Written to {out}/   (raw only, no rules applied)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
