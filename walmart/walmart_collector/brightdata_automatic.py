"""Bright Data snapshot orchestration and safely versioned Azure Blob trial publication.

No live collection is performed unless an explicit gated trigger is supplied.
The *published* production pointer is never touched: local price/PPM evidence is absent.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

from .brightdata_import import ROOT_IDS, import_snapshots

API_ROOT = "https://api.brightdata.com/datasets/v3"
ZIP_DATASET = "gd_m693oc1r1gebnayxq"  # Confirm against account before enabling a run.


def utc_now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def json_bytes(obj):
    return (json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


class BrightDataError(RuntimeError):
    pass


class HTTPBrightData:
    """Minimal HTTPS-only API wrapper, no third-party HTTP dependencies."""
    def __init__(self, token, timeout=60):
        if not token:
            raise ValueError("BRIGHTDATA_API_KEY must be configured privately")
        self.token = token
        self.timeout = timeout

    def request(self, method, path, params=None, data=None):
        url = API_ROOT + path + ("?" + urlencode(params) if params else "")
        headers = {"Authorization": "Bearer " + self.token, "Accept": "application/json"}
        if data is not None:
            headers["Content-Type"] = "application/json"
        request = Request(url, method=method, headers=headers,
                          data=json.dumps(data).encode("utf-8") if data is not None else None)
        try:
            with urlopen(request, timeout=self.timeout) as res:
                return json.loads(res.read())
        except (HTTPError, URLError) as exc:
            # Never put provider response bodies in logs: they may contain identifying data.
            status = getattr(exc, "code", "network_error")
            raise BrightDataError(f"Bright Data API {method} {path}: HTTP/network {status}") from exc
        except json.JSONDecodeError as exc:
            raise BrightDataError(f"Bright Data API {method} {path} did not return JSON") from exc

    def trigger(self, dataset_id, inputs, max_records):
        if not isinstance(max_records, int) or max_records < 1:
            raise ValueError("An explicit positive result cap is required for paid API triggers")
        result = self.request("POST", "/trigger", {
            "dataset_id": dataset_id, "type": "discover_new", "discover_by": "category_url",
            "format": "json", "include_errors": "true", "limit_multiple_results": max_records,
        }, inputs)
        sid = result.get("snapshot_id") if isinstance(result, dict) else None
        if not sid or not str(sid).startswith("s_"):
            raise BrightDataError("Trigger response lacks a valid snapshot_id")
        return sid

    def progress(self, snapshot_id):
        result = self.request("GET", "/progress/" + valid_snapshot(snapshot_id))
        if not isinstance(result, dict) or result.get("status") not in {"starting", "running", "ready", "failed"}:
            raise BrightDataError("Unexpected progress response")
        return result["status"]

    def snapshot(self, snapshot_id):
        result = self.request("GET", "/snapshot/" + valid_snapshot(snapshot_id), {"format": "json"})
        if not isinstance(result, list) or any(not isinstance(x, dict) for x in result):
            raise BrightDataError("Snapshot is not an array of product/error objects")
        return result


def valid_snapshot(snapshot_id):
    import re
    if not re.fullmatch(r"s_[A-Za-z0-9_\-]{6,100}", snapshot_id):
        raise ValueError("Invalid snapshot_id")
    return snapshot_id


def approved_input_categories(path, store_id, zipcode):
    """Reject off-scope URLs and store substitutions *before* billable collection."""
    import re
    result = []
    with Path(path).open(newline="", encoding="utf-8-sig") as f:
        for line in csv.DictReader(f):
            url = line.get("url", "").strip().split("?", 1)[0]
            if urlsplit(url).scheme != "https" or urlsplit(url).hostname != "www.walmart.com":
                raise ValueError("Category URLs must use https://www.walmart.com")
            segments = re.findall(r"(?<!\d)\d{4,8}(?!\d)", urlsplit(url).path)
            if not (set(segments) & set(ROOT_IDS)):
                raise ValueError(f"Non-allowlisted Walmart category URL: {url}")
            if line.get("zip_code", "").strip() != zipcode or line.get("store_id", "").strip() != store_id:
                raise ValueError("Input CSV contains a different store or ZIP")
            low = url.lower()
            if "farm-animals" in low or "shop-all-food" in low or "recipes" in low:
                raise ValueError("Excluded subcategory requested")
            row = {"url": url, "zip_code": zipcode, "store_id": store_id}
            for field in ("shipping_type", "max_product"):
                if line.get(field, "").strip():
                    row[field] = (int(line[field]) if field == "max_product" else line[field].strip())
            result.append(row)
    if not result or len(result) > 500:
        raise ValueError("A non-empty, bounded input manifest (<=500 categories) is required")
    return result


class LocalStore:
    """Private filesystem for no-cloud tests and safe local dry runs."""
    def __init__(self, root):
        self.root = Path(root)
    def get(self, key):
        p = self.root / key
        return p.read_bytes() if p.exists() else None
    def put(self, key, data):
        p = self.root / key
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)


class AzureBlobStore:
    """Azure SDK loads only inside authorized Azure runs, not during offline tests."""
    def __init__(self, connection_string, container):
        from azure.storage.blob import BlobServiceClient  # type: ignore
        service = BlobServiceClient.from_connection_string(connection_string)
        self.container = service.get_container_client(container)
        self.container.create_container() if not self.container.exists() else None
    def get(self, key):
        try:
            from azure.core.exceptions import ResourceNotFoundError  # type: ignore
            return self.container.download_blob(key).readall()
        except ResourceNotFoundError:
            return None
    def put(self, key, data):
        self.container.upload_blob(name=key, data=data, overwrite=True)


def execute(store, api, storage, snapshot_id=None, trigger_inputs=None, max_records=None,
            dataset_id=ZIP_DATASET, poll_seconds=15, max_polls=30):
    """Resume pending snapshot; never trigger another while a previous one awaits completion."""
    prefix = f'brightdata-trials/{store["store_id"]}'
    state_key = prefix + "/state.json"
    old_state = storage.get(state_key)
    state = json.loads(old_state) if old_state else {}
    if state.get("phase") == "complete" and snapshot_id == state.get("snapshot_id"):
        done = storage.get(prefix + "/latest-trial.json")
        if done:
            return json.loads(done)
    if state.get("snapshot_id") and state.get("phase") in {"triggered", "collecting", "ready"}:
        sid = valid_snapshot(state["snapshot_id"])
        if snapshot_id and sid != snapshot_id:
            raise RuntimeError("Prior snapshot pending; must resume it before switching snapshot IDs")
    elif snapshot_id:
        sid = valid_snapshot(snapshot_id)
        state = {"snapshot_id": sid, "phase": "collecting", "created_at": utc_now()}
        storage.put(state_key, json_bytes(state))
    elif trigger_inputs is not None:
        sid = api.trigger(dataset_id, trigger_inputs, max_records)
        # Small unavoidable network→checkpoint window; provider API has no idempotency key here.
        state = {"snapshot_id": sid, "phase": "triggered", "created_at": utc_now()}
        storage.put(state_key, json_bytes(state))
    else:
        raise RuntimeError("No pending snapshot. Supply --snapshot-id, or separately approve a trigger.")

    status = "running"
    for _ in range(max_polls):
        status = api.progress(sid)
        if status in {"ready", "failed"}:
            break
        if poll_seconds:
            time.sleep(poll_seconds)
    if status == "failed":
        state["phase"] = "failed"; state["updated_at"] = utc_now()
        storage.put(state_key, json_bytes(state))
        raise BrightDataError("Bright Data reported the snapshot failed; history was not modified")
    if status != "ready":
        state["phase"] = "collecting"; state["updated_at"] = utc_now()
        storage.put(state_key, json_bytes(state))
        return {"status": "pending", "snapshot_id": sid}

    raw = api.snapshot(sid)
    if not raw:
        raise BrightDataError("Empty snapshot cannot overwrite the previous trial")
    with tempfile.TemporaryDirectory(prefix="walmart-bd-") as temp:
        temp = Path(temp)
        original = temp / "source.json"
        original.write_bytes(json_bytes(raw))
        previous = storage.get(prefix + "/history.json")
        historyfile = None
        if previous:
            historyfile = temp / "history.json"; historyfile.write_bytes(previous)
        trial, manifest = import_snapshots([original], store, temp, historyfile)
        if manifest["current_candidate_store_products"] == 0:
            raise BrightDataError("No accepted store-scoped product: do not update latest trial or history")
        # Publish immutable run files first; only then update latest trial/history.
        run_root = prefix + "/runs/" + manifest["run_id"]
        storage.put(run_root + "/raw/source.json", original.read_bytes())
        for filename in ("data_22_fields.json", "evidence.json", "rejected.json", "history.json", "manifest.json"):
            storage.put(run_root + "/" + filename, (trial / filename).read_bytes())
        result = {"status": "trial_ready_not_accepted", "snapshot_id": sid,
                  "run": run_root, "record_count": manifest["historical_products_in_trial_export"],
                  "fresh_candidates": manifest["current_candidate_store_products"],
                  "confirmed_local_prices": manifest["products_with_confirmed_pickup_price"],
                  "confirmed_ppm": manifest["products_with_direct_source_ppm"]}
        storage.put(prefix + "/history.json", (trial / "history.json").read_bytes())
        storage.put(prefix + "/latest-trial.json", json_bytes(result))
        state.update({"phase": "complete", "updated_at": utc_now(), "trial_run": run_root})
        storage.put(state_key, json_bytes(state))
        return result


def main(argv=None, api_factory=HTTPBrightData):
    parser = argparse.ArgumentParser(description="Auto-import Bright Data into private, versioned Walmart trial storage")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--snapshot-id", help="Existing ready/pending snapshot; no new billable collection")
    group.add_argument("--trigger", action="store_true", help="Request NEW collection; requires explicit permission")
    parser.add_argument("--inputs-csv", type=Path, help="Approved category URLs and store/ZIP for a new collection")
    parser.add_argument("--max-records", type=int, help="Explicit maximum result count per trigger (pilot cost gate)")
    parser.add_argument("--dataset-id", default=ZIP_DATASET)
    parser.add_argument("--store-id", default=os.environ.get("WALMART_STORE_ID", "100"))
    parser.add_argument("--zipcode", default=os.environ.get("WALMART_ZIPCODE", "72712"))
    parser.add_argument("--stores", type=Path, default=Path(__file__).resolve().parent.parent / "config" / "stores.json")
    parser.add_argument("--local-root", type=Path, help="Private local storage for tests; otherwise Azure Blob")
    parser.add_argument("--poll-seconds", type=int, default=20)
    parser.add_argument("--max-polls", type=int, default=180)
    parser.add_argument("--dry-run", action="store_true", help="Validate input manifest; NO API or Azure access")
    args = parser.parse_args(argv)
    stores = json.loads(args.stores.read_text(encoding="utf-8"))["stores"]
    store = next((s for s in stores if s["store_id"] == args.store_id and s["zipcode"] == args.zipcode), None)
    if store is None:
        parser.error("Unknown configured Walmart store/ZIP combination")
    inputs = approved_input_categories(args.inputs_csv, args.store_id, args.zipcode) if args.inputs_csv else None
    if args.trigger and not args.dry_run:
        if os.environ.get("WALMART_DATA_AUTHORIZED") != "yes" or os.environ.get("BRIGHTDATA_COLLECTION_APPROVED") != "yes":
            parser.error("New billable collection denied: require explicit authorized-source and collection approval")
        if inputs is None or not args.max_records or args.max_records < 1:
            parser.error("New collection requires approved input CSV and strictly positive --max-records")
    if args.dry_run:
        print(json.dumps({"mode": "dry-run-no-network", "inputs": len(inputs or []), "store_id": args.store_id,
                          "zipcode": args.zipcode, "trigger_allowed": args.trigger,
                          "max_records": args.max_records}, indent=2))
        return 0
    if not os.environ.get("BRIGHTDATA_API_KEY"):
        parser.error("BRIGHTDATA_API_KEY secret is missing")
    if args.local_root:
        storage = LocalStore(args.local_root)
    else:
        conn = os.environ.get("AZURE_STORAGE_CONNECTION_STRING")
        if not conn:
            parser.error("AZURE_STORAGE_CONNECTION_STRING required for Azure mode")
        storage = AzureBlobStore(conn, os.environ.get("AZURE_BLOB_CONTAINER", "retail-collection"))
    result = execute(store, api_factory(os.environ["BRIGHTDATA_API_KEY"]), storage,
                     snapshot_id=args.snapshot_id,
                     trigger_inputs=inputs if args.trigger else None,
                     max_records=args.max_records, dataset_id=args.dataset_id,
                     poll_seconds=args.poll_seconds, max_polls=args.max_polls)
    print(json.dumps(result, indent=2))
    return 0 if result["status"] != "pending" else 2


if __name__ == "__main__":
    raise SystemExit(main())
