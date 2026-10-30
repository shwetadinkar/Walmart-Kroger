"""Offline Bright Data Walmart snapshot importer (never makes retailer/API requests).

A *trial* evidence normalizer, not a replacement for full-category collection or
proof of local price correctness. Raw snapshots remain outside the repository.
"""
from __future__ import annotations

import argparse
from collections import Counter, OrderedDict
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import re
from urllib.parse import urlsplit
from uuid import uuid4

from .schema import FIELDS, _APPROX, _PRIVATE_BRANDS

ROOT_IDS = {
    "976759": "Food", "1115193": "Household Essentials",
    "1005862": "Personal Care", "1085666": "Beauty",
    "486190": "Diapering", "133283": "Feeding",
    "976760": "Health & Wellness", "5440": "Pets",
    "3956207": "Balloons", "5899871": "Art Supplies",
    "1229749": "Office Supplies",
}
WALMART_SELLER = {"walmart.com", "walmart"}


def _string(value):
    return "" if value is None else str(value).strip()


def _iso(ts):
    if not isinstance(ts, str) or not ts:
        return ""
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            return ""
        return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    except ValueError:
        return ""


def _spec(raw, keys):
    vals = {_string(x.get("name")).casefold(): _string(x.get("value"))
            for x in raw.get("specifications", []) if isinstance(x, dict)}
    return next((vals[k.casefold()] for k in keys if vals.get(k.casefold())), "")


# Walmart category_ids are a primary category HIERARCHY. Several approved
# categories live under a broader root department (Baby, Arts & Crafts, Party).
APPROVED_CATEGORY_PATHS = (
    (("976759",), "Food"),
    (("1115193",), "Household Essentials"),
    (("1005862",), "Personal Care"),
    (("1085666",), "Beauty"),
    (("5427", "486190"), "Diapering"),
    (("5427", "133283"), "Feeding"),
    (("976760",), "Health & Wellness"),
    (("5440",), "Pets"),
    (("2637", "1042319", "1212898", "3956207"), "Balloons"),
    (("1334134", "5899871"), "Art Supplies"),
    (("1229749",), "Office Supplies"),
)


def _root_category(raw):
    """Validate the product's *primary* category ancestry, not related pages."""
    raw_path = _string(raw.get("category_ids"))
    hierarchy = tuple(raw_path.split(":"))
    if hierarchy and hierarchy[0] == "0":
        hierarchy = hierarchy[1:]
    category = ""
    if raw_path and raw_path not in {"-1", "0"}:
        for prefix, label in APPROVED_CATEGORY_PATHS:
            if len(hierarchy) >= len(prefix) and hierarchy[:len(prefix)] == prefix:
                category = label
                break
        if not category:
            return ""
    else:
        # Some actual provider responses report -1 instead of category_ids.
        # A direct approved top-level root URL is acceptable in that case;
        # nested category claims require genuine hierarchy evidence.
        url = _string(raw.get("root_category_url"))
        ids = re.findall(r"(?<!\d)\d{4,8}(?!\d)", urlsplit(url).path)
        if len(ids) != 1 or ids[0] not in ROOT_IDS:
            return ""
        category = ROOT_IDS[ids[0]]
        if category in {"Diapering", "Feeding", "Balloons", "Art Supplies"}:
            return ""

    ancestors = [str(x.get("name", "")).casefold().strip()
                 for x in raw.get("breadcrumbs", []) if isinstance(x, dict)]
    names = ancestors + [_string(raw.get("category_name")).casefold().strip()]
    if category == "Food" and any(x in {"recipes", "shop all foods"} for x in names):
        return ""
    if category == "Pets" and any(x == "farm animals" for x in names):
        return ""
    return category


def _product_id(raw):
    identity = _string(raw.get("product_id"))
    url = _string(raw.get("url"))
    m = re.search(r"/ip/(?:[^/]+/)?(\d+)(?:[/?#]|$)", url)
    if not identity or not m or m.group(1) != identity:
        return ""
    return identity


def _read_items(path):
    if path.suffix.lower() in {".ndjson", ".jsonl"}:
        records = [json.loads(s) for s in path.read_text(encoding="utf-8").splitlines() if s.strip()]
    else:
        records = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(records, list) or any(not isinstance(r, dict) for r in records):
        raise ValueError(f"Expected JSON array of objects: {path}")
    return records


def _validate(raw, store_id, zipcode):
    """Validate record identity and store-scoped *assortment*; not price proof."""
    if not _product_id(raw):
        return "BAD_OR_MISMATCHED_PRODUCT_ID_URL"
    if any(_string(raw.get(key)) != store_id for key in ("store_id", "pickup_store_id", "retailer_store_id")):
        return "STORE_ID_MISSING_OR_MISMATCHED"
    if _string(raw.get("zip_code")) != zipcode or _string(raw.get("pickup_zipcode")) != zipcode:
        return "ZIP_MISSING_OR_MISMATCHED"
    if _string(raw.get("seller")).casefold() not in WALMART_SELLER or _string(raw.get("retailer")).casefold() not in WALMART_SELLER:
        return "UNVERIFIED_WALMART_SELLER"
    if not _root_category(raw):
        return "OUTSIDE_REQUIRED_CATEGORY_ROOTS"
    pickup = raw.get("pickup_extras")
    if not isinstance(pickup, dict) or not _string(pickup.get("location")):
        return "MISSING_PICKUP_LOCATION_EVIDENCE"
    available = raw.get("available_for_pickup")
    status = _string(pickup.get("availability_status")).upper()
    if (available, status) not in {(True, "IN_STOCK"), (False, "OUT_OF_STOCK"), (False, "NOT_AVAILABLE")}:
        return "PICKUP_AVAILABILITY_CONTRADICTION"
    title = _string(raw.get("product_name"))
    if not title:
        return "MISSING_PRODUCT_TITLE"
    net = _spec(raw, ("Net content statement", "Product net content parent", "Size", "Weight"))
    if _APPROX.search(title) or _APPROX.search(net):
        return "APPROXIMATE_WEIGHT"
    return ""


def _format_price(value):
    if isinstance(value, bool) or value is None:
        return ""
    v = str(value).strip().lstrip("$")
    return v if re.fullmatch(r"\d+(?:\.\d{1,2})?", v) else ""


def _instant(stamp):
    """Parse an `_iso` timestamp into a comparable UTC datetime, or None.

    `_iso` keeps whatever fractional-second precision the source supplied, so
    two otherwise valid timestamps can differ in precision. Comparing them as
    strings is NOT chronological: "...00Z" sorts after "...00.500Z" because
    "Z" is a higher codepoint than ".", which would read a half-second-older
    observation as newer. Every ordering decision therefore compares parsed
    instants, never the raw strings.
    """
    if not stamp:
        return None
    try:
        return datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except ValueError:
        return None


def _freshness(incoming, prior):
    """Decide whether an incoming observation may replace persisted history.

    Stored history is only ever replaced by an observation that is *provably*
    newer. Undated, equal or older observations are retained as audit evidence
    and must never move stored values or observation dates backwards, including
    when they arrive in a separate import run.

    Ordering is by parsed UTC instant, so observations recorded at different
    fractional-second precisions compare correctly in both directions.
    """
    if not prior:
        return True, "first_observation"
    incoming_at = _instant(incoming)
    stored_at = _instant(prior.get("last_source_observed_at") or "")
    if incoming_at is None and stored_at is None:
        return False, "undated_incoming_and_undated_stored_not_orderable"
    if incoming_at is None:
        return False, "undated_incoming_cannot_prove_newer_than_stored"
    if stored_at is None:
        return True, "stored_observation_undated_incoming_dated"
    if incoming_at > stored_at:
        return True, "newer_than_stored"
    if incoming_at == stored_at:
        return False, "same_observation_time_as_stored"
    return False, "older_than_stored"


def _conflicting_fields(raw, store, prior):
    """Fields where a non-applied observation disagrees with stored history.

    Converted without carry-forward so the comparison reflects only what this
    observation itself asserts.
    """
    candidate, _ = _convert(raw, store, None)
    stored = (prior or {}).get("record", {})
    return sorted(name for name in FIELDS
                  if candidate.get(name) and stored.get(name)
                  and candidate[name] != stored[name])


def _convert(raw, store, history):
    """Produce 22-field rows; only a pickup-specific confirmed price may populate it."""
    record = OrderedDict((name, "") for name in FIELDS)
    record["zipcode"] = store["zipcode"]
    record["store_name"] = store["store_name"]
    record["store_location"] = store["store_location"]
    record["store_logo"] = store.get("store_logo", "")
    record["category"] = _root_category(raw)
    record["sub_category"] = _string(raw.get("category_name"))
    record["product_title"] = _string(raw.get("product_name"))
    record["weight"] = _spec(raw, ("Net content statement", "Product net content parent", "Weight", "Size"))
    record["image_url"] = _string(raw.get("main_image"))
    record["url"] = _string(raw.get("url")).split("?", 1)[0]
    record["upc"] = _string(raw.get("upc"))
    brand = _spec(raw, ("Brand",)) or _string(raw.get("brand"))
    record["store_brand"] = "yes" if brand.casefold() in _PRIVATE_BRANDS else "no"
    stamp = _iso(raw.get("timestamp"))
    # This field is a date, but only when the source has provided an observation timestamp.
    record["crawl_date"] = stamp[:10] if stamp else ""
    # The provider's `final_price` is an ONLINE price. It is NOT known to be the
    # local pickup selected price. Do not put it into regular/sale_price.
    pickup = raw.get("pickup_extras", {})
    eligible_pickup = raw.get("available_for_pickup") is True
    price = _format_price(pickup.get("fulfillment_price")) if eligible_pickup else ""
    record["regular_price"] = price
    # Bright Data's numeric `unit_price` has no proof of direct display. Do not calculate PPM.
    # The generic promotion_fulltext "Price when purchased online" is not a volume/digital deal.
    # Keep original promotion text in audit only.
    prior = history.get("record", {}) if isinstance(history, dict) else {}
    carried_fields = []
    # Preserve older descriptive evidence when a partial source response omits it.
    # Carried field timestamps remain explicitly recorded in the evidence sidecar.
    for field in ("sub_category", "weight", "image_url", "upc"):
        if not record[field] and prior.get(field):
            record[field] = prior[field]
            carried_fields.append(field)
    if not eligible_pickup and prior:
        for field in ("regular_price", "sale_price", "volume_deals_description",
                      "volume_deals_price", "digital_deals_description", "digital_deals_price", "ppm"):
            if prior.get(field) and not record[field]:
                record[field] = prior[field]
                carried_fields.append(field)
    provenance = {
        "source_observed_at": stamp or None,
        "date_basis": "source_timestamp" if stamp else "unknown_no_source_timestamp",
        "available_for_pickup": raw.get("available_for_pickup"),
        "pickup_status": pickup.get("availability_status"),
        "price_status": "fresh_pickup_price" if price else ("carried_prior_verified" if "regular_price" in carried_fields else "online_price_unverified"),
        "online_price_candidate_unverified": _format_price(raw.get("final_price")),
        "provider_unit_price_candidate_not_proven_displayed": raw.get("unit_price"),
        "provider_unit": raw.get("unit"),
        "promotion_text_unclassified": _string(raw.get("promotion_fulltext")),
        "carried_fields": carried_fields,
        "carried_field_observed_at": {field: history.get("field_observed_at", {}).get(field) for field in carried_fields} if history else {},
        "classification": "candidate_store_assortment_not_price_verified",
    }
    return record, provenance


def import_snapshots(paths, store, outdir, prior_history=None):
    """An immutable trial export; never advances the main collector's latest.json."""
    if not paths:
        raise ValueError("No input files")
    if prior_history is None:
        old = {}
    else:
        prior = json.loads(Path(prior_history).read_text(encoding="utf-8"))
        if prior.get("store_id") != store["store_id"] or prior.get("zipcode") != store["zipcode"]:
            raise ValueError("History store/ZIP mismatch")
        old = prior.get("products", {})
        if not isinstance(old, dict):
            raise ValueError("Malformed history")
    history = json.loads(json.dumps(old))  # do not mutate caller
    error_codes, reject_codes = Counter(), Counter()
    rejected, collisions = [], 0
    input_manifests, candidates = [], {}
    for path in paths:
        path = Path(path)
        raw_bytes = path.read_bytes()
        rows = _read_items(path)
        input_manifests.append({"file": path.name, "sha256": sha256(raw_bytes).hexdigest(), "rows": len(rows)})
        for index, item in enumerate(rows):
            ref = {"file": path.name, "row_index_zero_based": index}
            if item.get("error") or item.get("error_code"):
                code = _string(item.get("error_code")) or "UNKNOWN_SOURCE_ERROR"
                error_codes[code] += 1
                rejected.append({**ref, "reason": "SOURCE_ERROR:" + code})
                continue
            why = _validate(item, store["store_id"], store["zipcode"])
            if why:
                reject_codes[why] += 1
                rejected.append({**ref, "reason": why, "product_id": item.get("product_id")})
                continue
            identity = _product_id(item)
            if identity in candidates:
                collisions += 1
                prev = candidates[identity]
                # Ordered by parsed instant, not string, so mixed fractional-second
                # precision cannot make an older row win the duplicate contest.
                incoming_at = _instant(_iso(item.get("timestamp")))
                kept_at = _instant(_iso(prev["item"].get("timestamp")))
                if incoming_at is None or (kept_at is not None and incoming_at <= kept_at):
                    continue
            candidates[identity] = {"item": item, "source_ref": ref,
                                    "source_row_sha256": sha256(json.dumps(item, sort_keys=True, default=str).encode()).hexdigest()}

    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    evidence = {}
    stale_inputs, stale_conflicts = 0, 0
    for identity, value in sorted(candidates.items()):
        item = value["item"]
        key = f'{store["store_id"]}:{identity}'
        prior = history.get(key)
        stamp = _iso(item.get("timestamp"))
        applied, freshness = _freshness(stamp, prior)
        if not applied:
            # Stale, undated or repeat observations are audited, never applied.
            # Stored values and observation dates are left exactly as they were,
            # so an older import run cannot regress newer persisted history.
            conflicts = _conflicting_fields(item, store, prior)
            stale_inputs += 1
            stale_conflicts += bool(conflicts)
            prior["last_seen_import_at"] = now
            evidence[key] = {
                **value["source_ref"], "source_row_sha256": value["source_row_sha256"],
                "fresh_in_this_import": False, "applied_to_history": False,
                "freshness_decision": freshness,
                "incoming_source_observed_at": stamp or None,
                "stored_source_observed_at": prior.get("last_source_observed_at"),
                "conflicting_fields": conflicts,
                "classification": "stale_or_unorderable_input_retained_as_audit_only",
            }
            continue
        record, provenance = _convert(item, store, prior)
        field_dates = dict((prior or {}).get("field_observed_at", {}))
        for field in FIELDS:
            if record[field] and field not in provenance["carried_fields"]:
                field_dates[field] = stamp or None
        history[key] = {
            "record": record, "first_seen_import_at": (prior or {}).get("first_seen_import_at", now),
            "last_seen_import_at": now, "last_source_observed_at": stamp or None,
            "field_observed_at": field_dates,
            "availability_at_last_observation": provenance["pickup_status"],
        }
        evidence[key] = {**value["source_ref"], "source_row_sha256": value["source_row_sha256"],
                         "applied_to_history": True, "freshness_decision": freshness, **provenance}
    # Do not declare absent products out of stock: this is a partial category/sample import.
    for key, prior in history.items():
        if key not in evidence:
            evidence[key] = {"fresh_in_this_import": False,
                             "classification": "carried_not_observed_partial_crawl",
                             "last_source_observed_at": prior.get("last_source_observed_at")}
    records = [history[k]["record"] for k in sorted(history)]
    assert all(list(rec) == list(FIELDS) and all(isinstance(v, str) for v in rec.values()) for rec in records)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid4().hex[:8]
    trial = Path(outdir) / "trials" / store["store_id"] / run_id
    if trial.exists():
        raise RuntimeError("Run id collision")
    trial.mkdir(parents=True)
    def dump(name, value):
        (trial / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    dump("data_22_fields.json", records)
    dump("evidence.json", evidence)
    dump("rejected.json", rejected)
    dump("history.json", {"store_id": store["store_id"], "zipcode": store["zipcode"], "products": history})
    manifest = {
        "run_id": run_id, "generated_utc": now, "store_id": store["store_id"], "zipcode": store["zipcode"],
        "source": "brightdata_uploaded_snapshots_offline_import", "source_is_synthetic": False,
        "input_files": input_manifests,
        "raw_rows": sum(x["rows"] for x in input_manifests),
        "source_error_rows": sum(error_codes.values()), "source_errors": dict(error_codes),
        "rejected_product_rows": sum(reject_codes.values()), "rejected_reasons": dict(reject_codes),
        "duplicate_product_rows": collisions, "current_candidate_store_products": len(candidates),
        "stale_or_unorderable_input_rows": stale_inputs,
        "stale_inputs_with_conflicting_values": stale_conflicts,
        "history_regression_guard": "stored history is replaced only by a provably newer observation",
        "historical_products_in_trial_export": len(records),
        "pickup_available_candidates": sum(v["item"].get("available_for_pickup") is True for v in candidates.values()),
        "pickup_unavailable_candidates": sum(v["item"].get("available_for_pickup") is False for v in candidates.values()),
        "products_with_confirmed_pickup_price": sum(bool(history[k]["record"]["regular_price"]) for k in history),
        "products_with_direct_source_ppm": sum(bool(history[k]["record"]["ppm"]) for k in history),
        "coverage_complete": False, "azure_run_observed": False, "client_accepted": False,
        "note": "TRIAL: Store-scoped assortment candidates, not certified pickup prices/500-record contest acceptance. Raw responses preserved separately; no vendor endpoint contacted.",
    }
    dump("manifest.json", manifest)
    return trial, manifest


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("snapshots", nargs="+", type=Path, help="Bright Data JSON arrays or NDJSON files")
    p.add_argument("--output", type=Path, required=True, help="PRIVATE output root (not inside git)")
    p.add_argument("--store-id", default="100")
    p.add_argument("--zipcode", default="72712")
    p.add_argument("--history", type=Path, help="Previous trial history.json for perpetual retention")
    p.add_argument("--stores", type=Path, default=Path(__file__).resolve().parent.parent / "config" / "stores.json")
    args = p.parse_args(argv)
    stores = json.loads(args.stores.read_text(encoding="utf-8"))["stores"]
    store = next((s for s in stores if s["store_id"] == args.store_id and s["zipcode"] == args.zipcode), None)
    if not store:
        p.error("Store and ZIP not present in configured stores.json")
    trial, manifest = import_snapshots(args.snapshots, store, args.output, args.history)
    print(json.dumps({"trial_directory": str(trial), **manifest}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())