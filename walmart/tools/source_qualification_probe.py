"""Bounded qualification probe for a candidate Walmart data source.

PURPOSE
    Answer one question before any production work or spending decision: does a
    candidate provider return a price bound to a *requested* store, together
    with a *displayed* price per measure and offer terms?

WHAT THIS IS NOT
    Not a collector. Not production. Not a contest demonstration. It imports
    nothing from walmart_collector, writes nothing the collector reads, and
    never touches a release, a latest pointer or any existing dataset. Its
    output is a receipt and a findings file, not a product feed.

TRACEABILITY
    Every run writes, to its own timestamped directory:
      INPUT.json        the exact request body sent
      RAW_RESPONSE.json the provider response, unmodified
      RAW_SHA256.txt    hash of that response as received
      RECEIPT.json      run id, UTC start and end, endpoint, counts, bounds
      ACCEPTANCE.json   per-field presence and binding checks
      FINDINGS.md       the same, readable

BOUNDS
    A hard item cap, one request, no retries, and a wall-clock timeout. The
    probe refuses to run outside those bounds rather than silently widening.

Secrets are read from the environment and never written to any output file.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import sys
import urllib.error
import urllib.request
from uuid import uuid4

HARD_ITEM_CAP = 25
APIFY_SYNC = "https://api.apify.com/v2/acts/{actor}/run-sync-get-dataset-items"

# What the brief needs, and where this candidate claims to put it. Presence is
# measured, never assumed: a field that does not come back is recorded absent.
FIELD_CLAIMS = {
    "store_id_returned":  ("storeLocation.storeId", "store the price is reported for; binding is judged separately"),
    "local_price":        ("price", "local store price"),
    "comparison_price":   ("regularPrice", "price before the current offer"),
    "displayed_ppm":      ("unitPriceDisplay", "price per measure as displayed, not computed"),
    "numeric_unit_price": ("unitPrice", "numeric rate; NOT acceptable as displayed PPM"),
    "sale_flag":          ("isOnSale", "on-sale indicator"),
    "discount_amount":    ("discountAmount", "discount amount"),
    "fulfillment_type":   ("fulfillmentType", "STORE / FC / MARKETPLACE, for marketplace exclusion"),
    "upc":                ("upc", "retailer UPC"),
    "weight":             ("sizeText", "pack size"),
}
# Expected to be absent for this retailer; recorded either way.
OFFER_PROBES = ("volumeDeal", "multiBuy", "promotionText", "savings", "badges",
                "digitalCoupon", "coupon", "offerTerms")


def _utc():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _dig(obj, dotted):
    cur = obj
    for part in dotted.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def fetch(actor, token, payload, timeout):
    url = APIFY_SYNC.format(actor=actor)
    body = json.dumps(payload).encode()
    req = urllib.request.Request(
        url, data=body, method="POST",
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.status, resp.read()


def assess(items, store_id):
    """Measure what came back. Absence is a result, not a failure to report."""
    per_field = {}
    for name, (path, meaning) in FIELD_CLAIMS.items():
        present = [i for i in items if _dig(i, path) not in (None, "", [])]
        per_field[name] = {
            "provider_field": path,
            "meaning": meaning,
            "present_in": len(present),
            "of_items": len(items),
            "example": _dig(present[0], path) if present else None,
        }

    bound = [i for i in items if str(_dig(i, "storeLocation.storeId") or "") == str(store_id)]
    unbound = [{"index": n,
                "returned_store": _dig(i, "storeLocation.storeId"),
                "requested_store": str(store_id)}
               for n, i in enumerate(items)
               if str(_dig(i, "storeLocation.storeId") or "") != str(store_id)]

    offers = {}
    for key in OFFER_PROBES:
        hits = [i for i in items if i.get(key) not in (None, "", [], {})]
        offers[key] = {"present_in": len(hits),
                       "example": hits[0].get(key) if hits else None}

    all_keys = sorted({k for i in items for k in i}) if items else []

    return {
        "items_returned": len(items),
        "store_binding": {
            "requested_store_id": str(store_id),
            "items_bound_to_requested_store": len(bound),
            "items_not_bound": unbound,
            "verdict": ("BOUND" if items and not unbound else
                        "NOT_BOUND" if items else "NO_ITEMS"),
        },
        "required_fields": per_field,
        "offer_field_probe": offers,
        "all_keys_observed": all_keys,
        "verdicts": {
            "local_price_available": per_field["local_price"]["present_in"] > 0,
            "displayed_ppm_available": per_field["displayed_ppm"]["present_in"] > 0,
            "comparison_price_available": per_field["comparison_price"]["present_in"] > 0,
            "any_offer_wording_available": any(v["present_in"] for v in offers.values()),
        },
        "note": ("A numeric unitPrice is not a displayed price per measure and must not be "
                 "substituted for one. Absence of offer wording is recorded as absence, not "
                 "inferred from a discount flag."),
    }


def write_findings(path, receipt, acc):
    sb, v = acc["store_binding"], acc["verdicts"]
    L = [f"# Source qualification probe, {receipt['started_utc'][:10]}\n",
         "A bounded probe of one candidate source. Not production, not a collector run, and not "
         "a contest demonstration. No output here is merged into any dataset.\n",
         "## What was asked for\n",
         f"- Actor: `{receipt['actor']}`",
         f"- Requested store: {sb['requested_store_id']}",
         f"- Item cap: {receipt['bounds']['max_items']}, requests: 1, retries: 0, "
         f"timeout: {receipt['bounds']['timeout_seconds']}s",
         f"- Provider plan tier: **{receipt.get('provider_plan_tier', 'unspecified')}**. A trial "
         "result demonstrates capability, not an ongoing entitlement.\n",
         "## Store binding\n",
         f"Verdict: **{sb['verdict']}**. {sb['items_bound_to_requested_store']} of "
         f"{acc['items_returned']} items reported the requested store.\n"]
    if sb["items_not_bound"]:
        L.append("Items not bound to the requested store:\n")
        L.append("| Item | Returned store | Requested |")
        L.append("|---|---|---|")
        for u in sb["items_not_bound"]:
            L.append(f"| {u['index']} | {u['returned_store']} | {u['requested_store']} |")
        L.append("")
    L += ["## Required fields\n",
          "| Requirement | Provider field | Present | Example |", "|---|---|---:|---|"]
    for name, d in acc["required_fields"].items():
        ex = json.dumps(d["example"], ensure_ascii=False)[:40] if d["example"] is not None else "absent"
        L.append(f"| {name} | `{d['provider_field']}` | {d['present_in']}/{d['of_items']} | {ex} |")
    L += ["\n## Offer wording probe\n",
          "Walmart's promotional model is not Kroger's, so these are probed and recorded either way.\n",
          "| Key | Present | Example |", "|---|---:|---|"]
    for k, d in acc["offer_field_probe"].items():
        ex = json.dumps(d["example"], ensure_ascii=False)[:40] if d["example"] is not None else "absent"
        L.append(f"| `{k}` | {d['present_in']} | {ex} |")
    L += ["\n## Verdict\n",
          f"- Local store price: {'available' if v['local_price_available'] else 'NOT available'}",
          f"- Directly displayed PPM: {'available' if v['displayed_ppm_available'] else 'NOT available'}",
          f"- Comparison / was price: {'available' if v['comparison_price_available'] else 'NOT available'}",
          f"- Any offer wording: {'available' if v['any_offer_wording_available'] else 'NOT available'}\n",
          "The raw response is preserved unmodified alongside this file with its SHA-256, so every "
          "statement here can be checked against what the provider actually returned.\n",
          "Shweta\n"]
    Path(path).write_text("\n".join(L), encoding="utf-8")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--actor", default="hypebridge~walmart-product-scraper")
    p.add_argument("--store-id", default="100")
    p.add_argument("--zipcode", default="72712")
    p.add_argument("--item-ids", nargs="*", default=[],
                   help="Specific Walmart item IDs to probe")
    p.add_argument("--search", default="", help="Keyword, used only if no item ids are given")
    p.add_argument("--max-items", type=int, default=5)
    p.add_argument("--timeout", type=int, default=600)
    p.add_argument("--plan-tier", default="unspecified",
                   choices=["trial", "free", "paid", "unspecified"],
                   help="Which commercial tier produced this run. Recorded in the receipt "
                        "because a trial result may not be reproducible without payment.")
    p.add_argument("--output", type=Path, required=True,
                   help="PRIVATE output root, must be outside git")
    p.add_argument("--audit", type=Path,
                   help="Audit a previously saved RAW_RESPONSE.json offline; makes no request")
    args = p.parse_args(argv)

    if args.max_items > HARD_ITEM_CAP:
        p.error(f"--max-items {args.max_items} exceeds the hard cap of {HARD_ITEM_CAP}")

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid4().hex[:8]
    outdir = args.output / "qualification" / run_id
    if outdir.exists():
        p.error("Run id collision")
    outdir.mkdir(parents=True)

    payload = {"storeId": str(args.store_id), "zipCode": str(args.zipcode),
               "maxItems": args.max_items, "getProductDetails": True}
    if args.item_ids:
        payload["itemIds"] = args.item_ids
    elif args.search:
        payload["searchQueries"] = [args.search]
    else:
        p.error("Give --item-ids or --search so the probe is deterministic")

    started = _utc()
    if args.audit:
        raw = args.audit.read_bytes()
        status, endpoint, mode = None, None, "offline_audit_of_saved_response"
    else:
        token = os.environ.get("APIFY_TOKEN")
        if not token:
            p.error("APIFY_TOKEN is not set. The probe will not run without it, and the token "
                    "is never written to any output file.")
        try:
            status, raw = fetch(args.actor, token, payload, args.timeout)
        except urllib.error.HTTPError as exc:
            body = exc.read()[:2000].decode("utf-8", "replace")
            (outdir / "ERROR.json").write_text(json.dumps(
                {"http_status": exc.code, "body": body, "started_utc": started,
                 "ended_utc": _utc(), "retried": False}, indent=2), encoding="utf-8")
            print(f"Provider returned HTTP {exc.code}. Stopped without retrying. "
                  f"See {outdir/'ERROR.json'}", file=sys.stderr)
            return 1
        endpoint, mode = APIFY_SYNC.format(actor=args.actor), "live_bounded_probe"
    ended = _utc()

    (outdir / "RAW_RESPONSE.json").write_bytes(raw)
    (outdir / "RAW_SHA256.txt").write_text(sha256(raw).hexdigest() + "\n", encoding="utf-8")
    (outdir / "INPUT.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    try:
        items = json.loads(raw)
    except ValueError:
        print("Response was not JSON; raw body preserved.", file=sys.stderr)
        return 1
    if not isinstance(items, list):
        items = [items]

    receipt = {
        "run_id": run_id, "mode": mode, "actor": args.actor,
        "endpoint": endpoint, "http_status": status,
        "started_utc": started, "ended_utc": ended,
        "requests_made": 0 if args.audit else 1, "retries": 0,
        "bounds": {"max_items": args.max_items, "hard_cap": HARD_ITEM_CAP,
                   "timeout_seconds": args.timeout},
        "items_returned": len(items),
        "raw_response_sha256": sha256(raw).hexdigest(),
        "source_mode": "qualification_probe_not_production",
        "production_ready": False, "coverage_attested": False,
        "merged_into_any_dataset": False,
        "touches_collector_state": False,
        "secrets_in_output": False,
        "provider_plan_tier": args.plan_tier,
        "result_reproducible_without_payment": args.plan_tier == "free",
        "cost_disclosure_note": (
            "A trial result demonstrates capability, not an ongoing entitlement. Any "
            "production use of this source needs a disclosed paid plan and a measured "
            "running cost."),
    }
    (outdir / "RECEIPT.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")

    acc = assess(items, args.store_id)
    (outdir / "ACCEPTANCE.json").write_text(json.dumps(acc, indent=2) + "\n", encoding="utf-8")
    write_findings(outdir / "FINDINGS.md", receipt, acc)

    print(json.dumps({"output_directory": str(outdir),
                      "items_returned": acc["items_returned"],
                      "store_binding": acc["store_binding"]["verdict"],
                      **acc["verdicts"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
