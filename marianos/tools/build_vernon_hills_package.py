#!/usr/bin/env python3
"""Build the Vernon Hills collection package from the 31 October spine.

Standard library only, and needs nothing outside its own folder, so a package
can verify itself: `--verify <package>` recomputes every fact from the bytes
shipped. Every figure a note states is recomputed here, and a build that cannot
establish one is refused before anything is written.

The raw captures do not ship whole. `raw_index.json` lists all of them with
their hashes, and a sample chosen by a rule, seeded by the data file's hash,
ships with Kroger's `cid` masked. That cid is not the older application's, so
the earlier decision to ship cids byte-exact does not cover it.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit

# A package verifies its own file list, so running from it must not add to it.
sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_evidence_package import (PackageRefused, _flat, _REFERENCE, _ADDRESS, _TEXT,  # noqa: E402
                                    identity_hits, read_denylist, sha256)

STORE_ID = "53100502"
ZIPCODE = "60061"
STORE_NAME = "Marianos - Marianos Vernon Hills"
STORE_LOCATION = "1720 N Milwaukee Ave, Vernon Hills, IL 60061"
OTHER_STORE = "53100508"
FIELDS = ("zipcode", "store_name", "store_location", "store_logo", "store_brand", "category",
          "sub_category", "product_title", "weight", "regular_price", "sale_price",
          "volume_deals_description", "volume_deals_price", "digital_deals_description",
          "digital_deals_price", "image_url", "url", "upc", "gupc", "ppm", "unit_price",
          "crawl_date")
BLANK_ON_EVERY_ROW = ("ppm", "volume_deals_description", "volume_deals_price",
                      "digital_deals_description", "digital_deals_price", "gupc", "unit_price")
LIMIT_PER_TERM = 250
SKIP_TOLERANCE = 1
EMPTY_ROOTS = ("Batteries", "Coffee", "Coupons", "Light Bulbs", "Seafood")
NO_LABEL_FOR = ("Batter", "Bulb", "Coffee", "Coupon")
SEAFOOD_LABEL = "Meat & Seafood"

DATA_FILES = ("data_22_fields.json", "run_report.json", "store_verification.json",
              "pickup_context.json", "discovery_provenance.json",
              "category_disagreements.json", "unmapped_categories.json", "quarantine.json")
LEFT_OUT_FILES = {"retention.json": "per-identity observation history; 22 fields and "
                                    "pickup_context.json carry each product's state",
                  "checkpoint.json": "working state of the run; every product in it is in "
                                     "the data file"}
NOTES = ("README.md", "CHECKLIST.md", "DOES_NOT_ESTABLISH.md",
         "R6_COMPLETENESS_AND_BLOCKING.md", "R7_FAILED_RUN_PROTECTION.md",
         "R8_ARCHITECTURE_AND_SERVICES.md", "R9_OPERATING_COST.md",
         "R10_EVIDENCE_OF_GENERATION.md")
SOURCES = ("tools/kroger_full_sweep.py", "marianos_collector/api_trial.py",
           "marianos_collector/kroger.py", "marianos_collector/schema.py",
           "marianos_collector/retention.py", "marianos_collector/runner.py",
           "marianos_collector/storage.py", "marianos_collector/sources.py",
           "config/category_map.json", "config/sweep_terms.json", "config/categories.csv",
           "azure/deploy_jobs.sh", "Dockerfile")
# A note's description of the code must still be true of the code shipped with it.
CODE_CLAIMS = {
    "tools/kroger_full_sweep.py": ('state["page_failures"].append', 'if len(data) < 50:',
                                   'if start > max_start:', 'expected_context='),
    "marianos_collector/runner.py": ("Zero eligible products", "Suspicious yield collapse",
                                     "Missing canary product", "PUBLISHED_IDENTITY_LOST",
                                     "Location context mismatch",
                                     "Provider cannot attest complete subcategory discovery",
                                     "latest pointer is committed LAST"),
    "marianos_collector/kroger.py": ("if exc.code not in (429,500,502,503,504)",
                                     "Acceptable Use of Public APIs"),
}
NOT_IN_SWEEP = ("marianos_collector.runner", "marianos_collector.storage", "azure", "brightdata")
ACCEPTABLE_USE = "prohibits systematically gathering response data"
RUNS_PER_MONTH_NUMERATOR, RUNS_PER_MONTH_DENOMINATOR = 104, 12
VCPU, GIB = 0.5, 1
CID = re.compile(rb"cid=[^\"&\\\s]+")
MASK = b"cid=MASKED"
AUDIT_PAGES, TRUNCATED_TERMS_IN_FULL = 30, 3
# The comment in config/category_map.json predates the file's final name. That
# config ran unchanged, so it ships unchanged, and only this one name is excused.
OUTDATED_NAMES = {"source/config/category_map.json": {"unmapped.json"}}


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def key(entry):
    return f"{entry['term_root']}||{entry['term']}"


def index_raw(raw):
    """One line per capture. No page content, so no cid, and it can ship."""
    entries = []
    for path in sorted(Path(raw).rglob("*.json")):
        page = read(path)
        response = page["response"]
        entries.append({
            "path": path.relative_to(raw).as_posix(), "bytes": path.stat().st_size,
            "sha256": sha256(path), "term_root": page["term_root"], "term": page["term"],
            "start": page["start"], "observed_at": page["observed_at"],
            "location_id": page["locationId"], "returned": len(response.get("data") or []),
            "reported_total": ((response.get("meta") or {}).get("pagination") or {}).get("total")})
    return entries


def terms_from(index):
    terms = {}
    for entry in sorted(index, key=lambda e: (key(e), e["start"])):
        term = terms.setdefault(key(entry), {"received": 0, "last_start": 0, "paths": [],
                                             "root": entry["term_root"], "reported_total": 0})
        term["received"] += entry["returned"]
        term["last_start"] = entry["start"]
        term["last_returned"] = entry["returned"]
        term["paths"].append(entry["path"])
        if isinstance(entry["reported_total"], int):
            term["reported_total"] = entry["reported_total"]
    return terms


def truncation(index):
    """Terms stopped by this run's limit, and terms ending short without reaching it."""
    terms = terms_from(index)
    limited = sorted(k for k, t in terms.items() if t["last_start"] == 201 and t["last_returned"] == 50)
    short = sorted(({"term": k, "reported_total": t["reported_total"], "received": t["received"]}
                    for k, t in terms.items() if k not in limited
                    and t["reported_total"] - t["received"] > SKIP_TOLERANCE),
                   key=lambda s: s["term"])
    if any(terms[k]["reported_total"] <= LIMIT_PER_TERM for k in limited):
        raise PackageRefused("A term at the limit does not report more than the limit")
    below = [t for k, t in terms.items() if k not in limited and t["reported_total"] > 0]
    return {"terms": len(terms), "limited": limited, "short": short,
            "with_results_below_limit": len(below),
            "exactly_one_short": sum(t["reported_total"] - t["received"] == 1 for t in below),
            "zero_result_terms": sorted(k for k, t in terms.items() if t["reported_total"] == 0),
            "reported_total_at_1000": sum(t["reported_total"] == 1000 for t in terms.values())}


def choose_sample(index, seed):
    """A rule, not a selection: anyone can recompute it from raw_index.json."""
    rank = lambda text: hashlib.sha256(f"{seed}:{text}".encode()).hexdigest()
    terms = terms_from(index)
    facts = truncation(index)
    chosen, reasons = {}, {}

    def take(path, why):
        chosen[path] = True
        reasons.setdefault(path, []).append(why)

    for root in sorted({t["root"] for t in terms.values()}):
        productive = [k for k, t in terms.items() if t["root"] == root and t["received"]]
        if productive:
            take(terms[min(productive, key=rank)]["paths"][0], f"first page, root {root}")
    roots_seen = set()
    for name in sorted(facts["limited"], key=rank):
        if len(roots_seen) < TRUNCATED_TERMS_IN_FULL and terms[name]["root"] not in roots_seen:
            roots_seen.add(terms[name]["root"])
            for path in terms[name]["paths"]:
                take(path, "every page of a term stopped at the limit")
    for item in facts["short"]:
        for path in terms[item["term"]]["paths"]:
            take(path, "every page of a term ending short of its reported total")
    for name in facts["zero_result_terms"]:
        for path in terms[name]["paths"]:
            take(path, "a term with no result")
    remaining = sorted((e["path"] for e in index if e["path"] not in chosen), key=rank)
    for path in remaining[:AUDIT_PAGES]:
        take(path, "seeded audit page")
    return {path: reasons[path] for path in sorted(chosen)}


def duplicate_upcs(rows):
    upcs = [row["upc"] for row in rows if row["upc"]]
    return len(upcs) - len(set(upcs))


def check_rows(rows):
    for number, row in enumerate(rows):
        if tuple(row) != FIELDS:
            raise PackageRefused(f"Row {number} is not the 22 fields in order")
        if any(not isinstance(value, str) for value in row.values()):
            raise PackageRefused(f"Row {number} holds a value that is not a string")
        if (row["store_name"], row["store_location"], row["zipcode"]) != (
                STORE_NAME, STORE_LOCATION, ZIPCODE):
            raise PackageRefused(f"Row {number} is not labelled Vernon Hills")
        for field in BLANK_ON_EVERY_ROW:
            if row[field]:
                raise PackageRefused(f"Row {number} has a value in {field}; the notes say none")
        if urlsplit(row["url"]).query:
            raise PackageRefused(f"Row {number} carries a query in its url")


def check_sample(pages, rows, context):
    """Each sampled product must be in the data, as the page returned it."""
    by_upc = {row["upc"]: row for row in rows}
    first_seen = {c["product_id"]: c["raw_file"] for c in context.values()}
    products = compared = 0
    for name, page in pages.items():
        for product in page["response"].get("data") or []:
            products += 1
            row = by_upc.get(product.get("upc"))
            if row is None:
                raise PackageRefused(f"{name}: {product.get('upc')} is not in the data")
            if urlsplit(product.get("productPageURI", "")).path not in row["url"]:
                raise PackageRefused(f"{name}: {product.get('upc')} has another url in the data")
            if first_seen.get(product.get("productId")) == name:
                compared += 1
                prices = {f"{item['price'][kind]:.2f}" for item in product.get("items") or []
                          if isinstance(item.get("price"), dict)
                          for kind in ("regular", "promo") if item["price"].get(kind)}
                if row["regular_price"] and row["regular_price"] not in prices:
                    raise PackageRefused(f"{name}: {row['upc']} has another price in the data")
    return {"products_on_sampled_pages": products, "first_observations_compared": compared}


def empty_root_facts(discovery, rows):
    labels = Counter(label for item in discovery.values() for label in set(item["api_categories"]))
    roots = {}
    for root in EMPTY_ROOTS:
        found = [item for item in discovery.values() if item["term_root"] == root]
        roots[root] = {"products_found_by_its_terms": len(found),
                       "assigned_to": dict(Counter(i["assigned_root"] for i in found).most_common())}
    for fragment in NO_LABEL_FOR:
        if any(fragment.lower() in label.lower() for label in labels):
            raise PackageRefused(f"A Kroger label contains {fragment!r}; the notes say none does")
    if SEAFOOD_LABEL not in labels:
        raise PackageRefused("No Meat & Seafood label; the notes rely on it")
    return {"kroger_labels": len(labels), "roots": roots,
            "seafood_label_records": sum(r["sub_category"] == SEAFOOD_LABEL for r in rows)}


def recompute(data, index, sample_pages, source):
    rows = read(data / "data_22_fields.json")
    report = read(data / "run_report.json")
    verification = read(data / "store_verification.json")
    discovery = read(data / "discovery_provenance.json")
    context = read(data / "pickup_context.json")
    unmapped = read(data / "unmapped_categories.json")
    check_rows(rows)
    if verification["locationId"] != STORE_ID or verification["response"]["data"]["locationId"] != STORE_ID:
        raise PackageRefused("The store verification is not for Vernon Hills")
    if verification["resolved"] != {"zipcode": ZIPCODE, "store_name": STORE_NAME,
                                    "store_location": STORE_LOCATION}:
        raise PackageRefused("The store columns differ from the verified store")
    if report["locationId"] != STORE_ID or any(e["location_id"] != STORE_ID for e in index):
        raise PackageRefused("A capture or the report is for another store")
    upcs = [row["upc"] for row in rows if row["upc"]]
    counts = Counter(row["category"] for row in rows)
    trunc = truncation(index)
    returned = sum(e["returned"] for e in index)
    facts = {
        "records": len(rows), "distinct_upcs": len(set(upcs)),
        "duplicate_upcs": duplicate_upcs(rows),
        "duplicate_urls": len(rows) - len({row["url"] for row in rows}),
        "records_without_upc": len(rows) - len(upcs),
        "placements_returned": returned, "duplicate_placements_collapsed": returned - len(rows),
        "category_counts": dict(sorted(counts.items())),
        "named_roots_populated": sum(1 for name in counts if name),
        "records_with_no_root": counts.get("", 0),
        "field_completeness": {f: sum(bool(row[f]) for row in rows) for f in FIELDS},
        "crawl_dates": sorted({row["crawl_date"] for row in rows}),
        "runtime_seconds": report["elapsed_seconds"], "requests": report["requests_spent"],
        "captures": len(index), "raw_bytes": sum(e["bytes"] for e in index),
        "first_capture": min(e["observed_at"] for e in index),
        "last_capture": max(e["observed_at"] for e in index),
        "store_verified_utc": verification["verified_utc"],
        "truncation": trunc, "empty_roots": empty_root_facts(discovery, rows),
        "unmapped_label_placements": sum(len(v) for v in unmapped.values()),
        "unmapped_distinct_products": len({i for v in unmapped.values() for i in v}),
        "sample": check_sample(sample_pages, rows, context),
        "sale_prices": sum(bool(row["sale_price"]) for row in rows),
        "offer_status": report["offer_status"],
    }
    mismatches = {
        "unique_products": (report["unique_products"], facts["records"]),
        "unique_upcs": (report["unique_upcs"], facts["distinct_upcs"]),
        "requests": (report["requests_spent"], facts["captures"]),
        "limited terms": (sorted(set(report["terms_that_hit_the_start_cap"])), trunc["limited"]),
        "terms": (report["terms_completed"], trunc["terms"]),
        "zero roots": (report["categories_with_zero_products"], list(EMPTY_ROOTS)),
        "category counts": (report["count_by_category"], facts["category_counts"]),
        "field completeness": (report["field_completeness"], facts["field_completeness"]),
    }
    wrong = [name for name, (stated, found) in mismatches.items() if stated != found]
    if wrong:
        raise PackageRefused(f"The run report and the bytes disagree on: {wrong}")
    if report["page_failures"] or report["stopped_reason"]:
        raise PackageRefused("The run reports a failure the notes do not describe")
    if ACCEPTABLE_USE not in report["acceptable_use_decision"]:
        raise PackageRefused("The acceptable-use statement is missing from the run report")
    facts["source_checks"] = check_source(source)
    runs = RUNS_PER_MONTH_NUMERATOR / RUNS_PER_MONTH_DENOMINATOR
    facts["cost"] = {
        "runs_per_month": round(runs, 2),
        "vcpu_seconds_per_month": round(runs * report["elapsed_seconds"] * VCPU),
        "gib_seconds_per_month": round(runs * report["elapsed_seconds"] * GIB),
        "kroger_requests_per_month": round(runs * report["requests_spent"]),
        "raw_gb_per_month": round(runs * facts["raw_bytes"] / 1e9, 1)}
    return facts


def check_source(source):
    for name, needles in CODE_CLAIMS.items():
        text = (source / name).read_text(encoding="utf-8")
        missing = [needle for needle in needles if needle not in text]
        if missing:
            raise PackageRefused(f"{name} no longer does what the notes say: {missing}")
    sweep = (source / "tools/kroger_full_sweep.py").read_text(encoding="utf-8").lower()
    imports = "\n".join(line for line in sweep.splitlines() if line.startswith(("import ", "from ")))
    used = [word for word in NOT_IN_SWEEP if word in imports]
    if used:
        raise PackageRefused(f"The sweep now depends on: {used}")
    return {"sweep_imports_no_paid_service": True, "sweep_imports_no_publication_gate": True}


def note_requirements(facts):
    """What each note must state, taken from the bytes, not from memory."""
    trunc, cost = facts["truncation"], facts["cost"]
    roots = facts["empty_roots"]["roots"]
    return {
        "README.md": [f"{facts['records']:,}", f"{facts['captures']} captures",
                      f"{facts['raw_bytes']:,} bytes", "cid"],
        "CHECKLIST.md": [f"{facts['records']:,} records", f"{facts['runtime_seconds']} seconds",
                         f"{facts['duplicate_upcs']} duplicate UPCs",
                         f"{facts['duplicate_placements_collapsed']:,}",
                         f"{facts['named_roots_populated']} of 28",
                         f"{facts['sale_prices']:,}"] + [
                             f"`{k}` | {v:,}" for k, v in facts["field_completeness"].items()] + [
                             f"| {k or '(no root)'} | {v:,} |"
                             for k, v in facts["category_counts"].items()],
        "DOES_NOT_ESTABLISH.md": trunc["limited"] + [s["term"] for s in trunc["short"]] + [
            f"{len(trunc['limited'])} terms", f"{len(trunc['short'])} terms",
            f"{trunc['exactly_one_short']} of {trunc['with_results_below_limit']}",
            f"{facts['empty_roots']['seafood_label_records']:,} records",
            f"{facts['empty_roots']['kroger_labels']} labels",
            f"{facts['unmapped_label_placements']}", f"{facts['records_with_no_root']}"] + [
                f"{name}: {item['products_found_by_its_terms']:,} products"
                for name, item in roots.items()],
        "R6_COMPLETENESS_AND_BLOCKING.md": ["Zero eligible products", "Suspicious yield collapse",
                                            "not applied to this dataset",
                                            f"{len(trunc['short'])} terms"],
        "R7_FAILED_RUN_PROTECTION.md": ["latest", "PUBLISHED_IDENTITY_LOST",
                                        "not applied to this dataset"],
        "R8_ARCHITECTURE_AND_SERVICES.md": ["No paid service", "kroger_full_sweep.py",
                                            "Bright Data", "Azure"],
        "R9_OPERATING_COST.md": [f"{cost['vcpu_seconds_per_month']:,} vCPU-seconds",
                                 f"{cost['gib_seconds_per_month']:,} GiB-seconds",
                                 f"{cost['kroger_requests_per_month']:,} requests",
                                 f"{cost['raw_gb_per_month']} GB"],
        "R10_EVIDENCE_OF_GENERATION.md": [f"{facts['captures']} captures",
                                          f"{facts['sample']['products_on_sampled_pages']:,}",
                                          f"{facts['sample']['first_observations_compared']:,}",
                                          "cid=MASKED"],
    }


def check_notes(notes, facts):
    for name, required in note_requirements(facts).items():
        text = _flat((Path(notes) / name).read_text(encoding="utf-8"))
        missing = [item for item in required if _flat(item) not in text]
        if missing:
            raise PackageRefused(f"{name} does not state: {missing[:6]}")
    for name in NOTES:
        for line in (Path(notes) / name).read_text(encoding="utf-8").splitlines():
            if re.search(r"\bDear\b|\bHi\b|\bHello\b", line):
                raise PackageRefused(f"{name} is addressed to someone: {line[:40]}")


def unmasked_cids(paths):
    return sorted(Path(p).name for p in paths
                  if any(found != MASK for found in CID.findall(Path(p).read_bytes())))


def absent_references(root, index, left_out):
    names = {p.name for p in root.rglob("*") if p.is_file()} | {"MANIFEST_SHA256.json"}
    names |= {Path(e["path"]).name for e in index} | set(left_out)
    absent = {}
    for path in root.rglob("*"):
        if path.is_file() and path.suffix in _TEXT and path.name != "MANIFEST_SHA256.json":
            text = _ADDRESS.sub(" ", path.read_text(encoding="utf-8", errors="replace"))
            relative = path.relative_to(root).as_posix()
            missing = set(_REFERENCE.findall(text)) - names - OUTDATED_NAMES.get(relative, set())
            if missing:
                absent[relative] = sorted(missing)
    return absent


def describe(root, facts, sample, index, spine_hashes):
    by_path = {e["path"]: e for e in index}
    entries = []
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        name = path.relative_to(root).as_posix()
        if name == "MANIFEST_SHA256.json":
            continue
        entry = {"path": name, "bytes": path.stat().st_size, "sha256": sha256(path)}
        if name.startswith("raw_sample/"):
            relative = name.split("/", 1)[1]
            entry.update(origin="masked copy", original_sha256=by_path[relative]["sha256"],
                         why=sample[relative])
        elif name.startswith("data/"):
            entry["origin"] = "original, unchanged"
        entries.append(entry)
    left = [{"path": name, "bytes": item["bytes"], "sha256": item["sha256"],
             "reason": LEFT_OUT_FILES[name]} for name, item in spine_hashes.items()]
    left.append({"path": "raw/", "files": len(index) - len(sample),
                 "bytes": sum(e["bytes"] for e in index if e["path"] not in sample),
                 "reason": "too large to ship whole; hashed in raw_index.json"})
    return {"package": "marianos-vernon-hills-2026-10-31", "store": STORE_ID,
            "files": len(entries),
            "self": "MANIFEST_SHA256.json lists every other file and cannot hash itself",
            "statements_recomputed_from_the_bytes": facts, "left_out": left, "entries": entries}


def build(spine, log, notes, source, output, denylist):
    spine, notes, source, output = map(Path, (spine, notes, source, output))
    if output.exists() and any(output.iterdir()):
        raise PackageRefused(f"{output} is not empty")
    if any(OTHER_STORE in name for name in (str(spine), str(output))):
        raise PackageRefused("Paths name the West Loop store")
    denied = read_denylist(denylist)
    index = index_raw(spine / "raw")
    seed = sha256(spine / "data_22_fields.json")
    sample = choose_sample(index, seed)
    pages = {name: json.loads(CID.sub(MASK, (spine / "raw" / name).read_bytes()))
             for name in sample}
    facts = recompute(spine, index, pages, source)
    check_notes(notes, facts)
    plan = [(spine / name, f"data/{name}") for name in DATA_FILES]
    plan.append((Path(log), f"data/{Path(log).name}"))
    plan += [(notes / name, name) for name in NOTES]
    plan += [(source / name, f"source/{name}") for name in SOURCES]
    here = Path(__file__).resolve().parent
    plan += [(here / name, f"tools/{name}") for name in
             ("build_vernon_hills_package.py", "build_evidence_package.py")]
    # Before anything is written, so a refusal leaves no copy behind.
    hits = identity_hits([origin for origin, _ in plan], denied)
    if hits:
        raise PackageRefused(f"Files containing identity strings: {hits}")
    leaked = unmasked_cids([origin for origin, target in plan if target.startswith("data/")])
    if leaked:
        raise PackageRefused(f"Files carrying an unmasked cid: {leaked}")
    masked = {name: CID.sub(MASK, (spine / "raw" / name).read_bytes()) for name in sample}
    if any(needle in data.lower() for needle in (d.encode() for d in denied) for data in masked.values()):
        raise PackageRefused("A sampled page contains an identity string")
    for origin, target in plan:
        destination = output / target
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(origin, destination)
    for name, data in masked.items():
        destination = output / "raw_sample" / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
    (output / "raw_index.json").write_text(json.dumps(index, indent=0) + "\n", encoding="utf-8")
    absent = absent_references(output, index, LEFT_OUT_FILES)
    if absent:
        shutil.rmtree(output)
        raise PackageRefused(f"References to absent files: {absent}")
    spine_hashes = {name: {"bytes": (spine / name).stat().st_size, "sha256": sha256(spine / name)}
                    for name in LEFT_OUT_FILES}
    manifest = describe(output, facts, sample, index, spine_hashes)
    (output / "MANIFEST_SHA256.json").write_text(json.dumps(manifest, indent=2) + "\n",
                                                 encoding="utf-8")
    return manifest


def verify(output, denylist=None):
    """Recompute everything from the package alone. Returns the facts checked."""
    output = Path(output)
    manifest = read(output / "MANIFEST_SHA256.json")
    listed = {entry["path"]: entry for entry in manifest["entries"]}
    present = {p.relative_to(output).as_posix() for p in output.rglob("*") if p.is_file()}
    present.discard("MANIFEST_SHA256.json")
    if set(listed) != present:
        raise PackageRefused(f"Manifest and files disagree: {sorted(set(listed) ^ present)[:5]}")
    for name, entry in listed.items():
        if sha256(output / name) != entry["sha256"] or (output / name).stat().st_size != entry["bytes"]:
            raise PackageRefused(f"{name} does not match the manifest")
    index = read(output / "raw_index.json")
    by_path = {e["path"]: e for e in index}
    sample = choose_sample(index, sha256(output / "data/data_22_fields.json"))
    shipped = {name.split("/", 1)[1] for name in present if name.startswith("raw_sample/")}
    if shipped != set(sample):
        raise PackageRefused("The sample shipped is not the one the rule selects")
    pages = {}
    for name in sample:
        page = read(output / "raw_sample" / name)
        entry = by_path[name]
        if listed[f"raw_sample/{name}"]["original_sha256"] != entry["sha256"]:
            raise PackageRefused(f"{name} names another original than the index")
        if (page["term"], page["start"], page["observed_at"]) != (
                entry["term"], entry["start"], entry["observed_at"]):
            raise PackageRefused(f"{name} is not the capture the index describes")
        pages[name] = page
    leaked = unmasked_cids([p for p in output.rglob("*") if p.is_file()
                            and p.parts[len(output.parts)] in ("data", "raw_sample")])
    if leaked:
        raise PackageRefused(f"Files carrying an unmasked cid: {leaked[:5]}")
    facts = recompute(output / "data", index, pages, output / "source")
    if facts != manifest["statements_recomputed_from_the_bytes"]:
        raise PackageRefused("The manifest's statements do not recompute from the bytes")
    check_notes(output, facts)
    absent = absent_references(output, index, LEFT_OUT_FILES)
    if absent:
        raise PackageRefused(f"References to absent files: {absent}")
    scan = "not run: no deny-list given"
    if denylist:
        hits = identity_hits([output / name for name in present] + [output / "MANIFEST_SHA256.json"],
                             read_denylist(denylist))
        if hits:
            raise PackageRefused(f"Files containing identity strings: {hits[:5]}")
        scan = "clean"
    return {"files_verified": len(present), "identity_scan": scan, "sample_pages": len(sample),
            "records": facts["records"], "duplicate_upcs": facts["duplicate_upcs"]}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--verify", help="Check a built package and build nothing")
    p.add_argument("--identity-denylist")
    for name in ("--spine", "--log", "--notes", "--source", "--output", "--facts-only"):
        p.add_argument(name)
    args = p.parse_args(argv)
    try:
        if args.verify:
            result = verify(args.verify, args.identity_denylist)
        elif args.facts_only:
            spine = Path(args.spine)
            index = index_raw(spine / "raw")
            sample = choose_sample(index, sha256(spine / "data_22_fields.json"))
            pages = {n: json.loads(CID.sub(MASK, (spine / "raw" / n).read_bytes())) for n in sample}
            result = recompute(spine, index, pages, Path(args.source))
            Path(args.facts_only).write_text(json.dumps(result, indent=1), encoding="utf-8")
            result = {"facts_written": args.facts_only, "sample_pages": len(sample)}
        else:
            if not all((args.spine, args.log, args.notes, args.source, args.output,
                        args.identity_denylist)):
                p.error("A build needs --spine --log --notes --source --output --identity-denylist")
            manifest = build(args.spine, args.log, args.notes, args.source, args.output,
                             args.identity_denylist)
            result = {"files": manifest["files"]}
    except PackageRefused as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
