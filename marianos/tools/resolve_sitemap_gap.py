#!/usr/bin/env python3
"""Decide what the sitemap products missing from our data actually show.

`sitemap_reconciliation.py` finds that 326 of the 890 products in the
retailer's own SEO product sitemap are absent from the delivered dataset. That
figure on its own means nothing, because a sitemap is site-wide: the product
may not be carried at this store. Two very different facts produce the same
absence, and the reports must not merge them.

This resolves each one against the store, by id, through Kroger's documented
product-details endpoint. The verdicts are:

  priced_at_this_store            the location returned a regular price, which
                                  is evidence it carries the product. Counted
                                  in the lower bound of what the sweep missed.
  stocked_at_this_store           no price, but an explicit stock level at the
                                  location. Also carriage evidence.
  in_catalogue_no_store_evidence  the catalogue record came back with neither.
                                  UNDETERMINED: Kroger returns the catalogue
                                  record whether or not the store carries the
                                  product, so this is neither a missed product
                                  nor a confirmed absence.
  absent_from_catalogue           nothing returned, or HTTP 404. Absence from
                                  our data is not a collection gap.
  unresolved                      the lookup failed some other way. An
                                  unanswered question is not an answer.

**The honest output is a range, not a number.** The lower bound counts only
products with price or stock evidence; the upper bound adds the undetermined
ones. Neither end estimates the whole catalogue: the 890 sitemap products are
an SEO subset the retailer chose, not a random sample, so the rate among them
projects onto nothing.

The first version of this tool got that wrong. It returned a carriage verdict
for **any** product the endpoint returned, and treated a 404 as a lookup
failure. On the real run of 326 ids it reported 324 carried and **zero**
confirmed absences, which is not a finding about the store but a classifier
that never says no. Its own docstring stated the correct rule and the code did
not implement it. It was caught in review here before the number was used,
by reading the run's own output: zero absences out of 326 is a classifier,
not a store.

Nothing is published from this. It writes a report. The products it finds are
not appended to the dataset: they would be observations made by a different
method on a different date, and merging them silently into a 31 October sweep
would misdate them. If the client wants them collected they are collected by a
run, not by this tool.

Credentials are never passed on the command line and never printed. Run it
yourself:

    cd marianos
    set -a; . ./.env.kroger; set +a
    python3 tools/resolve_sitemap_gap.py --location-id 53100502 --probe-only
    python3 tools/resolve_sitemap_gap.py --location-id 53100502 \\
      --out reports/<today>-sitemap-gap

Start with --probe-only: one request, so a wrong assumption about the endpoint
costs one call rather than 326. Note what the probe reports as well as whether
it worked - on the real run the probe item itself had no price at the location,
which was the defect showing itself in the very first call.

To correct the verdicts on a report you already have, without spending the
calls again:

    python3 tools/resolve_sitemap_gap.py \\
      --reclassify reports/<run>/GAP_RESOLUTION.json \\
      --out reports/<run>
"""

import argparse
import json
import textwrap
from collections import Counter
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


PRICED = "priced_at_this_store"
STOCKED = "stocked_at_this_store"
NO_STORE_EVIDENCE = "in_catalogue_no_store_evidence"
ABSENT = "absent_from_catalogue"
UNRESOLVED = "unresolved"

CARRIAGE_EVIDENCE = (PRICED, STOCKED)


def classify(document):
    """What this store's response actually evidences about carriage.

    The first version of this returned "carried_and_missed" for **any**
    returned product and only recorded `has_regular_price` as a detail it
    never used. Its own docstring stated the correct rule - at least one item
    the store prices or stocks - and the code did not implement it. The result
    was 0 `not_carried` out of 326, which is not a finding about the store but
    a classifier that never says no. It was caught in review here before the
    number reached anyone.

    Kroger's product-details endpoint returns the catalogue record whether or
    not the location carries the product, so presence in the response is not
    evidence of carriage. A price or an explicit stock level **at this
    location** is. Absence of both is not evidence either way, and it says so
    rather than picking a side.
    """
    data = document.get("data") if isinstance(document, dict) else None
    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list) or not data:
        return ABSENT, {"_why": "Kroger returned no product for this id at this location"}
    product = next((p for p in data if isinstance(p, dict)), None)
    if product is None:
        return ABSENT, {"_why": "Kroger returned no product object for this id"}

    items = product.get("items") if isinstance(product.get("items"), list) else []
    priced = any(isinstance(i, dict) and isinstance(i.get("price"), dict)
                 and i["price"].get("regular") for i in items)
    stock_levels = [str((i.get("inventory") or {}).get("stockLevel") or "")
                    for i in items if isinstance(i, dict)
                    and isinstance(i.get("inventory"), dict)]
    stocked = any(level for level in stock_levels)

    detail = {
        "description": str(product.get("description") or ""),
        "categories": product.get("categories") if isinstance(product.get("categories"), list) else [],
        "items": len(items),
        "has_regular_price": priced,
        # Recorded from the first version onward only as a count; the levels
        # themselves were not kept, so an earlier report cannot be
        # reclassified on stock. They are kept now.
        "stock_levels": stock_levels,
    }
    if priced:
        return PRICED, dict(detail, _why="the location returned a regular price")
    if stocked:
        return STOCKED, dict(detail, _why="the location returned an explicit stock level")
    return NO_STORE_EVIDENCE, dict(
        detail, _why=("the catalogue record came back with no price and no stock level "
                      "at this location, so whether the store carries it is unknown"))


def classify_error(message: str):
    """A 404 is an answer, not a failure.

    Lumping it into `unresolved` conflated "we could not find out" with "we
    found out it is gone", which are different facts about the dataset.
    """
    if "404" in str(message):
        return ABSENT, {"_why": f"Kroger returned HTTP 404 for this id: {message}"}
    return UNRESOLVED, {"error": str(message)}


def reclassify(previous: dict) -> dict:
    """Recompute verdicts from a saved report, with no new requests.

    Offered because the first run's verdicts were wrong and re-spending 326
    calls to correct an error of mine is not the client's cost to bear. What
    can be recovered from a saved report is the price test and the 404 test;
    stock levels were not retained by the first version, so a product with no
    price cannot be narrowed further here and stays undetermined.
    """
    out, counts = {}, Counter()
    for product_id, record in (previous.get("results") or {}).items():
        if record.get("verdict") == "unresolved" or record.get("error"):
            verdict, detail = classify_error(record.get("error", ""))
        elif record.get("has_regular_price"):
            verdict, detail = PRICED, {"_why": "the location returned a regular price"}
        else:
            verdict, detail = NO_STORE_EVIDENCE, {
                "_why": ("no price at this location, and the first run did not retain "
                         "stock levels, so carriage is undetermined from this report")}
        counts[verdict] += 1
        out[product_id] = dict(record, verdict=verdict, **detail)
    return {"results": out, "counts": dict(counts)}


# The keys of a first-run report whose content the reclassification contradicts.
# `counts` holds the wrong numbers; the two `_means` keys hold the wrong prose,
# which is the worse of the two because prose is what gets quoted.
SUPERSEDED_KEYS = ("counts", "_carried_and_missed_means", "_not_carried_means")

TOOL_NAME = "tools/resolve_sitemap_gap.py"
MARKER_WIDTH = 79


def P(text: str) -> str:
    """One paragraph, wrapped. The marker is read by a client, so it is wrapped
    like prose. Wrapping it here rather than by choosing where the f-strings
    break means the wrap stays right whatever width the numbers turn out to be:
    the first version broke mid-sentence around a three-digit count and ran a
    line to 89 characters around a one-digit one."""
    return textwrap.fill(text, width=MARKER_WIDTH)


def write_supersession_marker(source: Path, previous: dict, report: dict) -> Path:
    """Leave a signal beside a report whose verdicts have been recomputed.

    The first run's report is kept byte-identical, because it is the evidence
    that the defect was real and a corrected file cannot evidence that. But a
    file kept unchanged carries its own wrong numbers and its own wrong prose,
    and someone opening it later - a reviewer, the client, a future run of this
    repository - has nothing local telling them so. The marker is that signal,
    written by the tool rather than by hand, so it cannot drift from the
    reclassification it describes.
    """
    counts = previous.get("counts", {}) or {}
    low = report["lower_bound_missed_by_the_sweep"]
    high = report["upper_bound_missed_by_the_sweep"]
    wrong = [k for k in SUPERSEDED_KEYS if k in previous]

    blocks = [
        f"# {source.name} is superseded",
        P(f"This file is the **first run** of `{TOOL_NAME}` and its verdicts are wrong. "
          f"It is kept unchanged on purpose: it is the evidence that the defect was "
          f"real, and a corrected file cannot evidence that."),
        P(f"**Do not read a number out of it.** The corrected figures are in "
          f"`GAP_RESOLUTION_RECLASSIFIED.json`, recomputed from this file with no new "
          f"requests."),
        "## What was wrong",
        P(f"It returned a carriage verdict for any product the endpoint returned. "
          f"Kroger's product-details endpoint returns the catalogue record whether or "
          f"not the queried location carries the product, so the response arriving "
          f"evidences nothing about the store. A price or an explicit stock level **at "
          f"that location** does. It also treated a 404 as a lookup failure rather than "
          f"as an answer."),
        P(f"So it reported {counts.get('carried_and_missed', '?')} carried and "
          f"{counts.get('not_carried', '?')} confirmed absences out of "
          f"{previous.get('ids_checked', '?')}, which is a property of the classifier "
          f"and not a finding about the store: a classifier that cannot say no carries "
          f"no information when it says yes."),
        "## What replaces it",
        "\n".join([
            f"- `{PRICED}`: **{report['counts'].get(PRICED, 0)}**",
            f"- `{STOCKED}`: **{report['counts'].get(STOCKED, 0)}**"
            f" (see the note below before reading this one)",
            f"- `{NO_STORE_EVIDENCE}`: **{report['counts'].get(NO_STORE_EVIDENCE, 0)}**"
            f" (evidence neither way)",
            f"- `{ABSENT}`: **{report['counts'].get(ABSENT, 0)}**",
        ]),
        P(f"Products missed by the sweep: at least **{low}**, at most **{high}**. A "
          f"range, because that is what the measurement supports. Neither end "
          f"estimates total catalogue coverage."),
        P(f"A zero against `{STOCKED}` is **not** a finding that nothing is stocked. "
          f"The first run recorded only whether a price existed and not stock levels, "
          f"so no product in it can be classified on stock at all, and every product "
          f"without a price falls to `{NO_STORE_EVIDENCE}` whatever its stock. A fresh "
          f"run retains stock levels and would move some of those either way. That is "
          f"why the upper bound is kept rather than dropped."),
        "## The keys in this file not to rely on",
        "\n".join([f"- `{k}`" for k in wrong])
        or "- (none of the known keys are present)",
        P(f"`_carried_and_missed_means` is the one to watch. It describes its count as "
          f"a hard lower bound on the coverage gap, and that count is the uncorrected "
          f"{counts.get('carried_and_missed', '?')}. The lower bound is the "
          f"`{PRICED}` figure above."),
    ]
    marker = source.parent / "SUPERSEDED.md"
    marker.write_text("\n\n".join(blocks) + "\n")
    return marker


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--location-id", default="",
                   help="Required unless --reclassify")
    p.add_argument("--absent", type=Path,
                   default=ROOT / "reports/2026-11-02-sitemap-reconciliation/absent_from_delivered.json")
    p.add_argument("--out", type=Path)
    p.add_argument("--reclassify", type=Path,
                   help="Recompute verdicts from a saved GAP_RESOLUTION.json without "
                        "making any request. Use this when the classifier was wrong "
                        "rather than re-spending the calls.")
    p.add_argument("--probe-only", action="store_true",
                   help="One request, to confirm the endpoint works before spending 326")
    p.add_argument("--limit", type=int, default=0, help="Stop after this many ids")
    p.add_argument("--pause", type=float, default=0.25,
                   help="Seconds between requests. Keep it unhurried")
    a = p.parse_args(argv)

    if a.reclassify:
        if not a.out:
            p.error("--out is required with --reclassify")
        previous = json.loads(a.reclassify.read_text())
        redone = reclassify(previous)
        report = {
            "_what": ("Verdicts recomputed from a saved report, with no new requests. "
                      "The first run's classifier returned a carriage verdict for any "
                      "returned product, which produced zero confirmed absences out of "
                      "326 and was wrong."),
            "reclassified_from": str(a.reclassify),
            "original_counts": previous.get("counts"),
            "counts": redone["counts"],
            "lower_bound_missed_by_the_sweep": sum(
                redone["counts"].get(v, 0) for v in CARRIAGE_EVIDENCE),
            "upper_bound_missed_by_the_sweep": (
                sum(redone["counts"].get(v, 0) for v in CARRIAGE_EVIDENCE)
                + redone["counts"].get(NO_STORE_EVIDENCE, 0)),
            "_stock_was_not_retained": (
                "The first run recorded only whether a price existed, not stock "
                "levels, so a product with no price cannot be narrowed here and stays "
                "undetermined. A fresh run now retains stock levels and would move "
                "some of those either way."),
            "results": redone["results"],
        }
        a.out.mkdir(parents=True, exist_ok=True)
        (a.out / "GAP_RESOLUTION_RECLASSIFIED.json").write_text(json.dumps(report, indent=1))
        marker = write_supersession_marker(a.reclassify, previous, report)
        print(json.dumps({k: v for k, v in report.items() if k != "results"}, indent=1)[:1400])
        print(f"\nwrote {a.out}")
        print(f"wrote {marker}")
        return 0

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
    counts = Counter()
    for n, product_id in enumerate(wanted, 1):
        try:
            verdict, detail = classify(lookup(client, product_id, a.location_id))
        except KrogerError as exc:
            verdict, detail = classify_error(exc)
        results[product_id] = dict(detail, verdict=verdict)
        counts[verdict] += 1
        if n % 25 == 0 or n == len(wanted):
            print(f"  {n}/{len(wanted)}  {dict(counts)}", flush=True)
        time.sleep(a.pause)

    resolved = sum(counts[v] for v in CARRIAGE_EVIDENCE) + counts[ABSENT]
    report = {
        "_what": ("Each product the retailer publishes in its SEO sitemap but that is "
                  "absent from the delivered dataset, resolved against this store by id."),
        "location_id": a.location_id,
        "started_utc": started,
        "finished_utc": datetime.now(timezone.utc).isoformat(),
        "ids_checked": len(wanted),
        "ids_available": len(ids),
        "counts": dict(counts),
        "lower_bound_missed_by_the_sweep": sum(counts[v] for v in CARRIAGE_EVIDENCE),
        "upper_bound_missed_by_the_sweep": (
            sum(counts[v] for v in CARRIAGE_EVIDENCE) + counts[NO_STORE_EVIDENCE]),
        "_what_each_verdict_means": {
            PRICED: ("The location returned a regular price, which is evidence it "
                     "carries the product, and our sweep did not reach it. Counted in "
                     "the lower bound."),
            STOCKED: ("No price, but the location returned an explicit stock level. "
                      "Also carriage evidence. Counted in the lower bound."),
            NO_STORE_EVIDENCE: (
                "The catalogue record came back with no price and no stock level at "
                "this location. Kroger returns the catalogue record whether or not the "
                "store carries the product, so this is UNDETERMINED - neither a missed "
                "product nor a confirmed absence. It is the difference between the "
                "lower and upper bound."),
            ABSENT: ("Kroger returned nothing, or HTTP 404, for this id at this "
                     "location. Its absence from our data is not a collection gap."),
            UNRESOLVED: "The lookup failed for some other reason. An unanswered question.",
        },
        "_the_bounds": (
            "lower_bound_missed_by_the_sweep counts only products with price or stock "
            "evidence at this location. upper_bound adds the undetermined ones. The "
            "honest figure is the range, and neither end is an estimate of the whole "
            "catalogue: these 890 sitemap products are an SEO subset the retailer "
            "chose, not a random sample, so the rate among them projects onto nothing."),
        "_nothing_here_is_published": (
            "No product found here has been added to the dataset. These are "
            "observations made by a different method on a later date, and merging "
            "them into a 31 October sweep would misdate them. Collect them with a "
            "run if they are wanted."),
        "results": results,
    }
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / "GAP_RESOLUTION.json").write_text(json.dumps(report, indent=1))
    print(json.dumps({"counts": dict(counts), "resolved": resolved,
                      "lower_bound": report["lower_bound_missed_by_the_sweep"],
                      "upper_bound": report["upper_bound_missed_by_the_sweep"],
                      "out": str(a.out)}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
