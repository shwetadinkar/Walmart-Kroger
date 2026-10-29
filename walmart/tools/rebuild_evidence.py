"""Rebuild the Walmart retention ledger and per-identity provenance from archived snapshots.

Offline only. Makes no retailer, provider or cloud request. This is a
deterministic replay of snapshots already obtained, not a new collection.

Outputs carry the regeneration date. Observation dates come from each
provider record's own timestamp and are never rewritten, so a historical
observation is never presented as fresher than it is.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from walmart_collector.brightdata_import import (  # noqa: E402
    _product_id, _validate, import_snapshots,
)

IP_URL = re.compile(r"/ip/(?:[^/]+/)?(\d+)")
UNAVAILABLE = {"OUT_OF_STOCK", "NOT_AVAILABLE"}


def submitted_identities(path: Path) -> dict:
    rows = json.loads(path.read_text(encoding="utf-8"))
    found = {}
    for row in rows:
        match = IP_URL.search(row.get("url", ""))
        if match:
            found[match.group(1)] = row.get("url", "")
    return found


def build_provenance(snapshots: Path) -> dict:
    provenance: dict = {}
    for path in sorted(snapshots.glob("*.json")):
        try:
            records = json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, UnicodeDecodeError):
            continue
        if not isinstance(records, list):
            records = [records]
        file_hash = sha256(path.read_bytes()).hexdigest()
        for index, record in enumerate(records):
            if not isinstance(record, dict) or record.get("error") or record.get("error_code"):
                continue
            if _validate(record, "100", "72712"):
                continue
            identity = _product_id(record)
            if not identity:
                continue
            provenance.setdefault(identity, []).append({
                "snapshot_file": path.name,
                "snapshot_sha256": file_hash,
                "row_index_zero_based": index,
                "source_row_sha256": sha256(
                    json.dumps(record, sort_keys=True, default=str).encode()).hexdigest(),
                "source_observed_at": record.get("timestamp"),
                "available_for_pickup": record.get("available_for_pickup"),
            })
    return provenance


def split_availability(history: dict, identities: set):
    selected = {k: v for k, v in history.items() if k.split(":", 1)[1] in identities}
    unavailable = sum(1 for v in selected.values()
                      if v.get("availability_at_last_observation") in UNAVAILABLE)
    return len(selected) - unavailable, unavailable, len(selected)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--snapshots", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True, help="PRIVATE output folder, never inside git")
    p.add_argument("--store-id", default="100")
    p.add_argument("--zipcode", default="72712")
    p.add_argument("--submission", type=Path, help="Submitted 22-field JSON to reconcile against")
    p.add_argument("--stores", type=Path,
                   default=Path(__file__).resolve().parent.parent / "config" / "stores.json")
    args = p.parse_args(argv)

    stores = json.loads(args.stores.read_text(encoding="utf-8"))["stores"]
    store = next((s for s in stores
                  if s["store_id"] == args.store_id and s["zipcode"] == args.zipcode), None)
    if not store:
        p.error("Store and ZIP not present in configured stores.json")

    inputs = sorted(str(f) for f in args.snapshots.glob("*.json"))
    if not inputs:
        p.error(f"No snapshot JSON files found in {args.snapshots}")

    args.output.mkdir(parents=True, exist_ok=True)
    trial, manifest = import_snapshots(inputs, store, args.output / "_run")
    for name in ("data_22_fields.json", "evidence.json", "rejected.json",
                 "history.json", "manifest.json"):
        (args.output / name).write_bytes((trial / name).read_bytes())

    summary = {
        "regenerated_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "regenerated_from": str(args.snapshots),
        "ledger_identities": manifest["historical_products_in_trial_export"],
        "rejected_product_rows": manifest["rejected_product_rows"],
        "source_error_rows": manifest["source_error_rows"],
        "products_with_confirmed_pickup_price": manifest["products_with_confirmed_pickup_price"],
        "products_with_direct_source_ppm": manifest["products_with_direct_source_ppm"],
    }

    if args.submission:
        wanted = submitted_identities(args.submission)
        provenance = build_provenance(args.snapshots)
        history = json.loads((args.output / "history.json").read_text(encoding="utf-8"))["products"]
        available, unavailable, total = split_availability(history, set(wanted))
        summary.update({
            "submitted_identities": len(wanted),
            "reproduced_from_snapshots": len(set(wanted) & set(provenance)),
            "not_found_in_any_snapshot": sorted(set(wanted) - set(provenance)),
            "submitted_set_pickup_available": available,
            "submitted_set_pickup_unavailable": unavailable,
            "submitted_set_total": total,
        })
        (args.output / "PROVENANCE_615.json").write_text(json.dumps({
            "generated_utc": summary["regenerated_utc"],
            "submitted_identities": len(wanted),
            "reproduced_from_snapshots": len(set(wanted) & set(provenance)),
            "not_found_in_any_snapshot": sorted(set(wanted) - set(provenance)),
            "identities_present_in_snapshots_but_not_in_the_24_october_submission":
                sorted(set(provenance) - set(wanted)),
            "per_identity_sources": provenance,
        }, indent=2) + "\n", encoding="utf-8")

    (args.output / "REBUILD_SUMMARY.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
