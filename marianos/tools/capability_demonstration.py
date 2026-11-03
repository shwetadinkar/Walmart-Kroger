#!/usr/bin/env python3
"""Does the sweep-through-collector path exercise the four capabilities?

The client asked, on 3 November: "Please deliver the exact revised commit,
commands and evidence that this same acquisition path exercises retention,
resume, trial separation and failed-run publication protection. Keep the
acknowledged category and unattended enrichment gaps explicit."

This runs the four scenarios and writes down what happened. It is runnable
with no credentials and no network, which is the point: anyone can execute it
and read the transcript rather than taking a claim on trust.

**What it does and does not evidence, stated first because it decides how much
the transcript is worth.**

It drives the real `Collector`, the real `KrogerSweepSource`, the real schema,
the real retention reconciliation and the real storage layer. Nothing is
stubbed except the Kroger HTTP client, which replays canned responses instead
of calling the API. So it evidences that **the code path behaves as described**
and that the sweep source, specifically, reaches that behaviour.

It is **not** evidence about live data, this store's assortment, or any figure
in the delivered dataset. The products in it are invented. Real collection at
the assigned store is a separate claim with separate evidence: the 26,166
record run of 31 October, which did not go through this path, which is the gap
this work exists to close.

It is also **not** evidence of Azure operation. Nothing here runs on Azure and
no schedule fires. That remains the weakest of the five evidence claims.
"""

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from marianos_collector.config import Category, Store  # noqa: E402
from marianos_collector.kroger_sweep_source import (  # noqa: E402
    KrogerSweepSource, SweepCursorInvalid)
from marianos_collector.runner import (  # noqa: E402
    Collector, ValidationFailure, storage_namespaces)
from marianos_collector.storage import LocalStorage, read_json  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent

STORE = Store("53100502", "60061", "Marianos - Marianos Vernon Hills",
              "1720 N Milwaukee Ave, Vernon Hills, IL 60061", "")
CATEGORIES = [Category("Dairy", "https://www.marianos.com/d/dairy"),
              Category("Produce", "https://www.marianos.com/d/produce")]
CATEGORY_MAP = {"Dairy": "Dairy", "Produce": "Produce"}


def offer(regular=2.98, curbside=True, stock="HIGH", sold_by="UNIT", size="18 ct"):
    item = {"soldBy": sold_by, "size": size,
            "fulfillment": {"curbside": curbside},
            "price": {"regular": regular} if regular is not None else {}}
    if stock is not None:
        item["inventory"] = {"stockLevel": stock}
    return item


def product(upc, categories=("Dairy",), **offer_kw):
    return {"productId": upc, "upc": upc, "description": f"Item {upc}",
            "brand": "Kroger", "productPageURI": f"/p/item/{upc}",
            "categories": list(categories), "items": [offer(**offer_kw)],
            "images": []}


class ReplayClient:
    """Stands in for KrogerClient. Replays responses; makes no request."""

    def __init__(self, by_term):
        self.by_term = by_term
        self.calls = []

    def products(self, location_id, term, offset=0, limit=50):
        self.calls.append((term, offset))
        items = self.by_term.get(term, [])
        return {"data": items[offset:offset + limit],
                "meta": {"pagination": {"total": len(items)}}}

    def get(self, path):
        raise RuntimeError(f"no replay for {path}")


def source(by_term, work, terms, **kw):
    return KrogerSweepSource(ReplayClient(by_term), "53100502", work, terms,
                             category_map=CATEGORY_MAP, **kw)


TERMS = {"Dairy": ["milk"], "Produce": ["apples"]}


def dairy(n, **kw):
    return [product(f"000111106{i:04d}", ("Dairy",), **kw) for i in range(n)]


def produce(n, **kw):
    return [product(f"000222206{i:04d}", ("Produce",), **kw) for i in range(n)]


# --------------------------------------------------------------- scenarios


def retention(work: Path, out: Path) -> dict:
    """A product the API stops returning must stay, with its original date."""
    storage = LocalStorage(out)
    first = source({"milk": dairy(4), "apples": produce(3)}, work / "a", TERMS)
    one = Collector(storage, first, CATEGORIES, min_products=1, trial=True).run(STORE)
    rows_one = json.loads(storage.read(one["manifest"]["data_key"]))
    gone = sorted(r["upc"] for r in rows_one if r["category"] == "Dairy")[-1]

    # Second run: the API no longer returns that product, and one of the
    # remaining is unavailable and unpriced.
    second = source({"milk": dairy(3) + [product("0001111069999", ("Dairy",),
                                                 regular=None, stock="OUT_OF_STOCK")],
                     "apples": produce(3)}, work / "b", TERMS)
    two = Collector(storage, second, CATEGORIES, min_products=1, trial=True).run(STORE)
    rows_two = json.loads(storage.read(two["manifest"]["data_key"]))
    by_upc = {r["upc"]: r for r in rows_two}

    unpriced = by_upc.get("0001111069999", {})
    return {
        "capability": "Indefinite retention of eligible products",
        "what_was_done": (
            "Two runs through the collector with the sweep source. Between them one "
            "product stopped being returned by the API, and a new one arrived with no "
            "price and out of stock."),
        "first_run_records": one["report"]["unique_records"],
        "second_run_records": two["report"]["unique_records"],
        "product_the_api_stopped_returning": gone,
        "it_is_still_in_the_second_release": gone in by_upc,
        "its_crawl_date_is_unchanged": (
            by_upc.get(gone, {}).get("crawl_date")
            == next(r["crawl_date"] for r in rows_one if r["upc"] == gone)),
        "carried_forward_count": two["report"]["carried_forward_records"],
        "current_count": two["report"]["current_records"],
        "unpriced_out_of_stock_product_retained": bool(unpriced),
        "its_regular_price_is_blank_not_invented": unpriced.get("regular_price") == "",
        "verdict": (
            "PASS" if (gone in by_upc and unpriced and unpriced.get("regular_price") == "")
            else "FAIL"),
    }


def resume(work: Path, out: Path) -> dict:
    """An interrupted run resumes from its checkpoint without re-fetching."""
    storage = LocalStorage(out)
    client_terms = {"milk": dairy(8), "apples": produce(6)}

    interrupted = source(client_terms, work, TERMS, serve_page_size=4)
    stopped = ""
    try:
        Collector(storage, interrupted, CATEGORIES, min_products=1, trial=True,
                  max_pages=1).run(STORE)
    except ValidationFailure as exc:
        stopped = str(exc)

    namespace, checkpoint_root = storage_namespaces(CATEGORIES, True)
    checkpoint = read_json(storage, f"{checkpoint_root}/{STORE.store_id}/dairy.json")

    # Resume in a fresh source object, as a new process would.
    resumed_client = ReplayClient(client_terms)
    resumed = KrogerSweepSource(resumed_client, "53100502", work, TERMS,
                                category_map=CATEGORY_MAP, serve_page_size=4)
    done = Collector(storage, resumed, CATEGORIES, min_products=1,
                     trial=True).run(STORE)

    return {
        "capability": "Resume from a durable checkpoint",
        "what_was_done": (
            "A run was interrupted mid-category by the page safety limit, leaving a "
            "checkpoint. A second run with a fresh source object resumed it."),
        "first_run_stopped_with": stopped,
        "checkpoint_survived": bool(checkpoint),
        "checkpoint_pages_staged": len(checkpoint["pages"]) if checkpoint else 0,
        "checkpoint_queue_carried_a_cursor": bool(
            checkpoint and checkpoint["queue"] and checkpoint["queue"][0]["cursor"]),
        "api_calls_made_by_the_resumed_sweep": len(resumed_client.calls),
        "_why_zero_calls": (
            "The sweep checkpointed each completed term, so the resumed sweep "
            "re-fetched nothing. The products it serves were re-read from the "
            "persisted API responses on disk."),
        "resumed_run_published": done["report"]["unique_records"],
        "verdict": "PASS" if (checkpoint and not resumed_client.calls
                              and done["report"]["unique_records"]) else "FAIL",
    }


def trial_separation(work: Path, out: Path) -> dict:
    """A sweep run cannot write to the published namespace."""
    storage = LocalStorage(out)
    src = source({"milk": dairy(3), "apples": produce(3)}, work, TERMS)

    refused = ""
    try:
        Collector(storage, src, CATEGORIES, min_products=1, trial=False)
    except ValidationFailure as exc:
        refused = str(exc)

    run = Collector(storage, source({"milk": dairy(3), "apples": produce(3)},
                                    work / "t", TERMS),
                    CATEGORIES, min_products=1, trial=True).run(STORE)
    namespace, _ = storage_namespaces(CATEGORIES, True)
    published = sorted(p.name for p in (out / "published").glob("*")) if (out / "published").is_dir() else []

    return {
        "capability": "Trial and published namespace separation",
        "what_was_done": (
            "A sweep source was asked to publish a full release, then run as a trial."),
        "full_release_refused_with": refused,
        "trial_namespace_used": namespace,
        "manifest_key": run["manifest"]["data_key"],
        "wrote_under_trials": run["manifest"]["data_key"].startswith("trials/"),
        "published_namespace_contents": published,
        "report_declares_scope": run["report"]["scope"],
        "report_declares_coverage_attested": run["report"]["source_coverage_attested"],
        "verdict": "PASS" if (refused and run["manifest"]["data_key"].startswith("trials/")
                              and not published) else "FAIL",
    }


def failed_run_protection(work: Path, out: Path) -> dict:
    """A degraded run must not replace a good release."""
    storage = LocalStorage(out)
    good = Collector(storage, source({"milk": dairy(6), "apples": produce(6)},
                                     work / "good", TERMS),
                     CATEGORIES, min_products=1, trial=True).run(STORE)
    namespace, _ = storage_namespaces(CATEGORIES, True)
    pointer_key = f"{namespace}/{STORE.store_id}/latest.json"
    pointer_before = read_json(storage, pointer_key)

    def clear_checkpoints():
        """Each scenario must test its own gate.

        A failed run leaves its checkpoint behind, and the next run resumes it
        — including the staged pages the failed run produced. The first version
        of this demonstration did not clear them, so the second bad run
        inherited the first one's single-product pages and was refused by the
        yield gate instead of the gate it was meant to exercise. The refusal
        looked right and evidenced nothing. That a failed run's checkpoint is
        resumable is real behaviour and is reported below, not hidden by
        clearing it silently.
        """
        for category in CATEGORIES:
            storage.delete(f"{checkpoint_root}/{STORE.store_id}/{category.slug}.json")

    _, checkpoint_root = storage_namespaces(CATEGORIES, True)

    # Gate one: a collapsed yield against the previous release.
    clear_checkpoints()
    collapsed = ""
    try:
        Collector(storage, source({"milk": dairy(1), "apples": produce(1)},
                                  work / "bad", TERMS),
                  CATEGORIES, min_products=1, trial=True).run(STORE)
    except ValidationFailure as exc:
        collapsed = str(exc)

    # Gate two, a different one: below the minimum product floor.
    clear_checkpoints()
    floor = ""
    try:
        Collector(storage, source({"milk": dairy(6), "apples": produce(6)},
                                  work / "floor", TERMS),
                  CATEGORIES, min_products=10_000, trial=True).run(STORE)
    except ValidationFailure as exc:
        floor = str(exc)

    # Gate three: a run at the wrong store cannot overwrite this store's data.
    clear_checkpoints()
    wrong_store = ""
    try:
        other = Store("53100502", "60661", "Marianos - Marianos West Loop",
                      "40 S Halsted St, Chicago, IL 60661", "")
        Collector(storage, source({"milk": dairy(6), "apples": produce(6)},
                                  work / "other", TERMS),
                  CATEGORIES, min_products=1, trial=True).run(other)
    except (ValidationFailure, ValueError) as exc:
        wrong_store = str(exc)

    pointer_after = read_json(storage, pointer_key)
    gates = {"yield_collapse": collapsed, "minimum_product_floor": floor,
             "wrong_store_context": wrong_store}
    return {
        "capability": "Failed-run publication protection",
        "what_was_done": (
            "A good release was published, then three bad runs were attempted, each "
            "against a different gate: a collapsed yield, a run below the minimum "
            "product floor, and a run carrying another store's context. Checkpoints "
            "were cleared between them so each run exercises its own gate."),
        "good_release": good["manifest"]["release"],
        "good_release_records": good["report"]["unique_records"],
        "gates_that_refused": gates,
        "each_gate_refused_for_its_own_reason": len(set(gates.values())) == len(gates),
        "latest_pointer_unchanged": pointer_before == pointer_after,
        "latest_pointer_still_names": (pointer_after or {}).get("release"),
        "_note_on_checkpoints": (
            "A failed run leaves a resumable checkpoint, and a later run resumes it "
            "with the failed run's staged pages. The protections still held here, but "
            "it means a rerun after a failure can republish the failed run's pages "
            "rather than collecting afresh. Use clear-checkpoints after a failure. "
            "This is reported, not fixed."),
        "verdict": "PASS" if (all(gates.values())
                              and len(set(gates.values())) == len(gates)
                              and pointer_before == pointer_after) else "FAIL",
    }


GAPS = """\
## The gaps, kept explicit as asked

**Category coverage is not established and this path does not establish it.**
The Kroger public Products API has no category enumeration. `filter.start` is a
skip count refused past 250, so one term reaches at most 300 products however
many sit behind it, and on the 31 October run 69 of 301 terms hit that ceiling.
Five of the 28 configured roots return nothing from this API and are declared,
with reasons, in `config/sweep_coverage.json`. A sweep run therefore covers 23
roots and says so in its own release report. Nothing above changes that.

**Enrichment is not unattended.** Displayed price per measure and retailer deal
wording exist only on the rendered retailer page. The public API carries
neither. The 592 rates and the deal wordings in the delivered set came from an
attended browser session, and the page route stopped after 28 page loads on 1
November. No unattended route to those fields is available today, which is set
out in `ROUTES_AND_AUTONOMY.md`.

**Nothing here ran on Azure.** No schedule fired, nothing ran in the client's
environment, and the delivered 26,166 did not come from Azure. The deployment
template and a three-execution manual pilot of 28 October are the whole of the
Azure evidence, and that pilot was at West Loop on a five-product selection of
one term.

**The data above is invented.** The transcript evidences the code path, not an
assortment, a price or a count. Real collection at the assigned store is the
separate 26,166 record run of 31 October, which did not go through this path.
"""


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args(argv)

    commit = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"],
                            capture_output=True, text=True).stdout.strip()
    dirty = subprocess.run(["git", "-C", str(ROOT), "status", "--porcelain"],
                           capture_output=True, text=True).stdout.strip()

    results = []
    for name, run in (("retention", retention), ("resume", resume),
                      ("trial_separation", trial_separation),
                      ("failed_run_protection", failed_run_protection)):
        work = Path(tempfile.mkdtemp(prefix=f"demo-{name}-"))
        out = Path(tempfile.mkdtemp(prefix=f"store-{name}-"))
        try:
            results.append(run(work, out))
        finally:
            shutil.rmtree(work, ignore_errors=True)
            shutil.rmtree(out, ignore_errors=True)

    report = {
        "_what": ("The sweep-through-collector path exercised against the four "
                  "capabilities the client named. Runnable with no credentials and "
                  "no network; only the Kroger HTTP client is replayed."),
        "commit": commit,
        "working_tree_clean": not dirty,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "source_mode": KrogerSweepSource.source_mode,
        "coverage_attested": KrogerSweepSource.coverage_attested,
        "capabilities": results,
        "all_pass": all(r["verdict"] == "PASS" for r in results),
    }
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / "CAPABILITIES.json").write_text(json.dumps(report, indent=1))
    (a.out / "GAPS.md").write_text(GAPS)
    print(json.dumps({r["capability"]: r["verdict"] for r in results}, indent=1))
    print(f"commit {commit}  clean={not dirty}  all_pass={report['all_pass']}")
    print(f"wrote {a.out}")
    return 0 if report["all_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
