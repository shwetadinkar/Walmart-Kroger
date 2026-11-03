#!/usr/bin/env python3
"""Does `marianos_product` return a price per measure and the retailer's deal wording?

That is the only question this answers, and it is the question the whole
Oxylabs assessment now turns on. `OXYLABS_ASSESSMENT.md` was wrong twice about
this vendor: it claimed no dedicated Kroger or grocery target exists, and that
the Walmart sources carry no store id. Both were false. What is genuinely
unknown is whether the parsed output of `marianos_product` carries a unit price
or price-per-measure field, and any promotion, deal or coupon text. No output
schema reachable on 3 November 2026 mentions either.

Those two fields are the entire Mariano's enrichment gap. `ppm` and the four
volume and digital deal columns are at 0 percent in every release produced
through the API, because the public Kroger Products API carries none of them
and they exist only on the rendered page.

**This probe is stronger than a field inventory, deliberately.** It draws its
UPCs from records that already hold a page-read `ppm` observed on the retailer's
own page. So if Oxylabs returns a rate, it can be compared against a rate we
watched the retailer display, rather than merely noted as present. A field that
exists but disagrees with the page is not the field we need.

What it does not do:

- **It publishes nothing.** No record is added to or changed in any dataset.
  A value from here would be an observation by a different method on a
  different date, and merging it into an earlier run would misdate it.
- **It does not assume access.** The client's instruction was explicit: do not
  assume additional access or an approved run. Credentials are read from the
  environment only, never from a command line, same rule as the Kroger keys.
- **It is bounded.** `--count` is capped, and the cap is enforced before the
  first request rather than counted afterwards.

Run `--dry-run` first. It sends nothing and prints the exact payloads, because
the Classic request shape for this target is not something this file should
pretend to be certain of: the parameter names come from the vendor's endpoint
reference, and the first real response is what confirms them. If the shape is
wrong, `--source-name` and `--query-field` override it without editing code.

    export OXYLABS_USERNAME=...        # never on the command line
    export OXYLABS_PASSWORD=...
    python3 tools/oxylabs_probe.py --dry-run
    python3 tools/oxylabs_probe.py --out reports/oxylabs-probe
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

ENDPOINT = "https://realtime.oxylabs.io/v1/queries"
HARD_CAP = 25            # Enforced before the first request, not after.
DEFAULT_COUNT = 5

STORE_ID = "53100502"
DELIVERY_ZIP = "60061"
FULFILLMENT = "pickup"

# Key-name patterns for the two fields the gap is made of. Matching is on the
# key NAME only: a match is a candidate to read, never a confirmed field, and
# the report prints the full key inventory beside it so a field whose name does
# not match these cannot be missed.
RATE_PATTERNS = ("unit_price", "unitprice", "price_per", "per_unit", "perunit",
                 "ppm", "price_per_unit", "unit_of_measure", "unit")
DEAL_PATTERNS = ("promo", "deal", "coupon", "saving", "discount", "offer",
                 "was_price", "sale")


def credentials():
    user = os.environ.get("OXYLABS_USERNAME", "")
    secret = os.environ.get("OXYLABS_PASSWORD", "")
    if not user or not secret:
        raise SystemExit(
            "OXYLABS_USERNAME and OXYLABS_PASSWORD are required in the environment.\n"
            "Credentials stay with their owner: export them in the shell that runs\n"
            "this, never pass them as arguments. Nothing was sent.")
    return user, secret


def subjects(data_path: Path, count: int):
    """UPCs to probe, preferring ones whose displayed rate we already observed.

    A record with a page-read `ppm` makes the answer checkable: the vendor's
    rate can be compared against one read off the retailer's own page. Records
    without one can only ever answer "a field exists", which is the weaker
    half of the question.
    """
    records = json.loads(data_path.read_text())
    withrate = [r for r in records if (r.get("ppm") or "").strip()
                and (r.get("upc") or "").strip()]
    chosen = withrate[:count]
    if len(chosen) < count:
        rest = [r for r in records if (r.get("upc") or "").strip()
                and r not in chosen]
        chosen += rest[:count - len(chosen)]
    return [{"upc": r["upc"], "product_title": r.get("product_title", ""),
             "observed_ppm": r.get("ppm", ""),
             "observed_regular_price": r.get("regular_price", ""),
             "observed_weight": r.get("weight", "")} for r in chosen]


def payload(subject, source_name, query_field, with_store):
    body = {"source": source_name, query_field: subject["upc"], "parse": True}
    if with_store:
        body.update({"store_id": STORE_ID, "delivery_zip": DELIVERY_ZIP,
                     "fulfillment_type": FULFILLMENT})
    return body


def flatten(obj, prefix=""):
    """Every leaf key path in the parsed content, so a field cannot be missed
    because it sits one level deeper than expected."""
    out = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            out.update(flatten(v, f"{prefix}.{k}" if prefix else str(k)))
    elif isinstance(obj, list):
        for i, v in enumerate(obj[:3]):        # first three are enough to see shape
            out.update(flatten(v, f"{prefix}[{i}]"))
    else:
        out[prefix] = obj
    return out


def candidates(paths, patterns):
    hits = {}
    for path, value in paths.items():
        leaf = path.lower()
        if any(p in leaf for p in patterns):
            hits[path] = value
    return hits


def send(body, user, secret, timeout):
    request = urllib.request.Request(
        ENDPOINT, data=json.dumps(body).encode(), method="POST",
        headers={"Content-Type": "application/json",
                 "Authorization": "Basic " + base64.b64encode(
                     f"{user}:{secret}".encode()).decode()})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:2000]
        return exc.code, {"_http_error": detail}
    except Exception as exc:                   # noqa: BLE001
        return 0, {"_transport_error": f"{type(exc).__name__}: {exc}"}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--from-data", type=Path,
                   default=ROOT / "out/vernon-hills-merged-rerun-2026-11-01-v2"
                                  "/data_22_fields_enriched.json")
    p.add_argument("--count", type=int, default=DEFAULT_COUNT,
                   help=f"UPCs to probe. Capped at {HARD_CAP}")
    p.add_argument("--out", type=Path)
    p.add_argument("--dry-run", action="store_true",
                   help="Print the payloads and send nothing")
    p.add_argument("--source-name", default="marianos_product",
                   help="Override if the Classic source name differs")
    p.add_argument("--query-field", default="query",
                   help="Override if the product identifier field differs")
    p.add_argument("--no-store-context", action="store_true",
                   help="Omit store_id, delivery_zip and fulfillment_type, to "
                        "see whether they change the answer")
    p.add_argument("--timeout", type=int, default=90)
    a = p.parse_args(argv)

    if a.count < 1 or a.count > HARD_CAP:
        p.error(f"--count must be between 1 and {HARD_CAP}. This is a capability "
                f"probe, not a collection run.")
    if not a.from_data.is_file():
        p.error(f"{a.from_data} not found. Pass --from-data with a delivered dataset.")
    if not a.dry_run and not a.out:
        p.error("--out is required for a real run, so the responses are kept")

    picked = subjects(a.from_data, a.count)
    rated = sum(1 for s in picked if s["observed_ppm"])
    print(f"{len(picked)} UPCs, {rated} of them with a page-read ppm already observed",
          file=sys.stderr)

    bodies = [(s, payload(s, a.source_name, a.query_field, not a.no_store_context))
              for s in picked]

    if a.dry_run:
        print(json.dumps({
            "_what": "Exactly what would be sent. Nothing was sent.",
            "endpoint": ENDPOINT,
            "requests": len(bodies),
            "auth": "HTTP Basic from OXYLABS_USERNAME / OXYLABS_PASSWORD",
            "payloads": [b for _, b in bodies],
            "subjects": picked,
        }, indent=1))
        return 0

    user, secret = credentials()
    a.out.mkdir(parents=True, exist_ok=True)
    results = []
    for subject, body in bodies:
        status, document = send(body, user, secret, a.timeout)
        (a.out / f"raw_{subject['upc']}.json").write_text(json.dumps(
            {"request": body, "status": status, "response": document}, indent=1))
        content = {}
        for item in (document.get("results") or []):
            if isinstance(item, dict) and isinstance(item.get("content"), (dict, list)):
                content = item["content"]
                break
        paths = flatten(content)
        results.append({
            "upc": subject["upc"],
            "product_title": subject["product_title"],
            "http_status": status,
            "observed_ppm_from_page": subject["observed_ppm"],
            "observed_regular_price": subject["observed_regular_price"],
            "observed_weight": subject["observed_weight"],
            "rate_field_candidates": candidates(paths, RATE_PATTERNS),
            "deal_field_candidates": candidates(paths, DEAL_PATTERNS),
            "all_leaf_keys": sorted(paths),
            "parsed_content_present": bool(content),
        })

    any_rate = [r for r in results if r["rate_field_candidates"]]
    any_deal = [r for r in results if r["deal_field_candidates"]]
    report = {
        "_what": ("Whether marianos_product returns a price per measure and the "
                  "retailer's deal wording. Nothing here is published; a value from "
                  "this probe is an observation by a different method on a different "
                  "date and merging it into an earlier run would misdate it."),
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "endpoint": ENDPOINT,
        "source_name": a.source_name,
        "store_context_sent": not a.no_store_context,
        "requests_made": len(results),
        "responses_with_parsed_content": sum(
            1 for r in results if r["parsed_content_present"]),
        "upcs_with_a_rate_field_candidate": len(any_rate),
        "upcs_with_a_deal_field_candidate": len(any_deal),
        "_how_to_read_this": (
            "rate_field_candidates and deal_field_candidates match on the KEY NAME "
            "only. A candidate is something to read, not a confirmed field, and "
            "all_leaf_keys is printed so a field whose name matches neither pattern "
            "cannot be missed. Where observed_ppm_from_page is non-empty, compare it "
            "against the candidate value: a rate that disagrees with what the page "
            "displayed is not the field we need."),
        "_verdict_is_not_computed_here": (
            "Deliberately. Whether a candidate IS the displayed rate is a judgement "
            "about two strings, and this file will not make it silently."),
        "results": results,
    }
    (a.out / "OXYLABS_PROBE.json").write_text(json.dumps(report, indent=1) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k != "results"}, indent=1))
    print(f"\nwrote {a.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
