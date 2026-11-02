#!/usr/bin/env python3
"""Decide whether the sitemap products missing from our data are a gap or not.

`sitemap_reconciliation.py` finds that 326 of the 890 products in the
retailer's own SEO product sitemap are absent from the delivered dataset. That
figure on its own means nothing, because a sitemap is site-wide: the product
may not be carried at this store. Two very different facts produce the same
absence, and the reports must not merge them.

This resolves each one against the store, by id, through Kroger's documented
product-details endpoint. For every absent id the answer is one of:

  carried_and_missed    the store returns the product, so the term sweep did
                        not reach it. This is a real coverage gap and the
                        count is the first hard lower bound this project has
                        on how much the sweep misses.
  not_carried           the store returns nothing for it. Absence from our
                        data is correct and is an assortment fact.
  unresolved            the lookup itself failed. Recorded as neither, with
                        the error, because an unanswered question is not an
                        answer.

Nothing is published from this. It writes a report. The products it finds are
not appended to the dataset: they would be observations made by a different
method on a different date, and merging them silently into a 31 October sweep
would misdate them. If the client wants them collected they are collected by a
run, not by this tool.

Credentials are never passed on the command line and never printed. Run it
yourself:

    cd marianos
    set -a; . ./.env.kroger; set +a
    python3 tools/resolve_sitemap_gap.py \\
      --location-id 53100502 \\
      --absent reports/2026-11-02-sitemap-reconciliation/absent_from_delivered.json \\
      --out reports/2026-11-02-sitemap-gap

Start with --probe-only. It makes exactly one request and reports whether the
product-details path works at all with these credentials, so a wrong
assumption about the endpoint costs one call rather than 326.
"""

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import sys as _sys
_sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from marianos_collector.kroger import Credentials, KrogerClient, KrogerError  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def lookup(client, product_id, location_id):
    """The store's answer for one product id, or a reason it had none."""
    return client.get(f"/products/{product_id}",
                      {"filter.locationId": location_id})


def classify(document):
    """carried_and_missed or not_carried, from the response alone.

    `data` present with at least one item that the store prices or stocks is
    the store carrying it. An empty data array is Kroger saying it has nothing
    for that id at that location.
    """
    data = document.get("data") if isinstance(document, dict) else None
    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list) or not data:
        return "not_carried", {}
    product = next((p for p in data if isinstance(p, dict)), None)
    if product is None:
        return "not_carried", {}
    items = product.get("items") if isinstance(product.get("items"), list) else []
    return "carried_and_missed", {
        "description": str(product.get("description") or ""),
        "categories": product.get("categories") if isinstance(product.get("categories"), list) else [],
        "items": len(items),
        # Recorded, not published. See the module docstring.
        "has_regular_price": any(
            isinstance(i, dict) and isinstance(i.get("price"), dict)
            and i["price"].get("regular") for i in items),
    }


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--location-id", required=True)
    p.add_argument("--absent", type=Path,
                   default=ROOT / "reports/2026-11-02-sitemap-reconciliation/absent_from_delivered.json")
    p.add_argument("--out", type=Path)
    p.add_argument("--probe-only", action="store_true",
                   help="One request, to confirm the endpoint works before spending 326")
    p.add_argument("--limit", type=int, default=0, help="Stop after this many ids")
    p.add_argument("--pause", type=float, default=0.25,
                   help="Seconds between requests. Keep it unhurried")
    a = p.parse_args(argv)

    if a.location_id.upper().startswith(("DEMO", "REPLACE", "UNRESOLVED")):
        p.error("--location-id must be a verified Kroger location, not a placeholder")

    ids = json.loads(a.absent.read_text())
    if not isinstance(ids, list) or not ids:
        p.error(f"{a.absent} holds no ids")

    client = KrogerClient(Credentials.from_environment())

    if a.probe_only:
        try:
            document = lookup(client, ids[0], a.location_id)
        except KrogerError as exc:
            print(json.dumps({
                "probe": "failed", "product_id": ids[0], "error": str(exc),
                "meaning": ("The product-details path did not work with these "
                            "credentials. Nothing further was attempted. Do not "
                            "assume the endpoint exists on this tier; check the "
                            "developer reference before changing this tool."),
            }, indent=1))
            return 1
        verdict, detail = classify(document)
        print(json.dumps({"probe": "worked", "product_id": ids[0],
                          "verdict": verdict, "detail": detail,
                          "next": f"Rerun without --probe-only to resolve all {len(ids)} ids"},
                         indent=1))
        return 0

    if not a.out:
        p.error("--out is required unless --probe-only")

    wanted = ids[:a.limit] if a.limit else ids
    started = datetime.now(timezone.utc).isoformat()
    results = {}
    counts = {"carried_and_missed": 0, "not_carried": 0, "unresolved": 0}
    for n, product_id in enumerate(wanted, 1):
        try:
            verdict, detail = classify(lookup(client, product_id, a.location_id))
        except KrogerError as exc:
            verdict, detail = "unresolved", {"error": str(exc)}
        results[product_id] = dict(detail, verdict=verdict)
        counts[verdict] += 1
        if n % 25 == 0 or n == len(wanted):
            print(f"  {n}/{len(wanted)}  {counts}", flush=True)
        time.sleep(a.pause)

    resolved = counts["carried_and_missed"] + counts["not_carried"]
    report = {
        "_what": ("Each product the retailer publishes in its SEO sitemap but that is "
                  "absent from the delivered dataset, resolved against this store by id."),
        "location_id": a.location_id,
        "started_utc": started,
        "finished_utc": datetime.now(timezone.utc).isoformat(),
        "ids_checked": len(wanted),
        "ids_available": len(ids),
        "counts": counts,
        "_carried_and_missed_means": (
            "The store returns this product and our sweep did not reach it. This is a "
            "real coverage gap in the term sweep and the count is a hard LOWER bound "
            "on it, not an estimate of it: these 890 sitemap products are an SEO "
            "subset chosen by the retailer, not a random sample of the catalogue, so "
            "the rate among them supports no projection onto the whole."),
        "_not_carried_means": (
            "The store returns nothing for this id. Its absence from our data is "
            "correct and is a fact about the assortment, not about our collection."),
        "_nothing_here_is_published": (
            "No product found here has been added to the dataset. These are "
            "observations made by a different method on a later date, and merging "
            "them into a 31 October sweep would misdate them. Collect them with a "
            "run if they are wanted."),
        "results": results,
    }
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / "GAP_RESOLUTION.json").write_text(json.dumps(report, indent=1))
    print(json.dumps({"counts": counts, "resolved": resolved,
                      "out": str(a.out)}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
