"""Command-line entry point for local tests, approved data feeds, and Azure jobs."""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

from .config import categories_from_csv, stores_from_json
from .runner import Collector
from .sources import FixtureSource, AuthorizedProviderSource
from .opd import OPDClient, WalmartOPDSnapshotSource
from .storage import LocalStorage, AzureBlobStorage, read_json

PROJECT = Path(__file__).resolve().parent.parent

class JsonFormatter(logging.Formatter):
    def format(self, record):
        value = {"level":record.levelname,"event":getattr(record,"event",record.getMessage()),
                 "message":record.getMessage()}
        for key in ("store_id", "category", "pages", "products", "records", "release", "source_mode", "attempt"):
            if hasattr(record, key):
                value[key] = getattr(record,key)
        return json.dumps(value)


def build_parser():
    parser = argparse.ArgumentParser(prog="walmart-collector", description="Walmart store-specific collection using approved data sources")
    parser.add_argument("command", choices=["list", "run", "status", "export", "clear-checkpoints"])
    parser.add_argument("--stores", type=Path, default=PROJECT / "config/stores.json")
    parser.add_argument("--categories", type=Path, default=PROJECT / "config/categories.csv")
    parser.add_argument("--store", default=os.environ.get("WALMART_STORE_ID", "100"), help="Walmart store ID, NOT just a ZIP code")
    parser.add_argument("--backend", choices=["local", "azure"], default="local")
    parser.add_argument("--output", type=Path, default=PROJECT / ".collector-output")
    parser.add_argument("--container", default=os.environ.get("AZURE_BLOB_CONTAINER", "retail-collection"))
    parser.add_argument("--source", choices=["fixture", "provider", "opd"], default="fixture")
    parser.add_argument("--fixtures", type=Path, default=PROJECT / "fixtures")
    parser.add_argument("--opd-mapping", type=Path, default=PROJECT / "config/opd_category_mapping.json")
    parser.add_argument("--opd-cache", type=Path, default=None, help="Persistent directory; mount a persistent volume on Azure")
    parser.add_argument("--opd-page-size", type=int, default=100)
    parser.add_argument("--only-categories", default="", help="Trial subset, e.g. Food,Beauty; not proof of complete category coverage")
    parser.add_argument("--minimum-products", type=int, default=None)
    parser.add_argument("--authorized-source", action="store_true", help="Affirm client's authorized/contractual feed access")
    parser.add_argument("--canaries", type=Path, help="Optional JSON dictionary category to required product IDs")
    parser.add_argument("--export-file", type=Path, help="Destination for latest successful exact-schema JSON")
    parser.add_argument("--confirm-reset", action="store_true", help="Clear incomplete checkpoints; prior releases are untouched")
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(JsonFormatter())
    log = logging.getLogger("collector")
    log.addHandler(handler)
    log.setLevel(logging.INFO)
    try:
        categories = categories_from_csv(args.categories)
        if args.only_categories:
            requested = {x.strip() for x in args.only_categories.split(",") if x.strip()}
            unknown = requested - {c.name for c in categories}
            if unknown or len(requested) < 2:
                parser.error("--only-categories requires at least two existing categories; unknown: " + str(unknown))
            categories = [c for c in categories if c.name in requested]
            print("CAUTION: trial only; category coverage is incomplete.", file=sys.stderr)
        stores = stores_from_json(args.stores)
        if args.command == "list":
            print(json.dumps({"stores":[s.__dict__ for s in stores],"categories":[c.__dict__ for c in categories]},indent=2))
            return 0
        store = next((s for s in stores if s.store_id == args.store), None)
        if store is None:
            parser.error(f"Store ID not configured: {args.store}")
        if args.backend == "azure":
            conn = os.environ.get("AZURE_STORAGE_CONNECTION_STRING", "")
            if not conn:
                parser.error("AZURE_STORAGE_CONNECTION_STRING must be supplied as a secret")
            storage = AzureBlobStorage(conn, args.container)
        else:
            storage = LocalStorage(args.output)
        if args.command == "status":
            latest = read_json(storage, f"published/{store.store_id}/latest.json")
            print(json.dumps({"store_id":store.store_id, "latest":latest,
                              "manifest":read_json(storage,latest["manifest_key"]) if latest else None},indent=2))
            return 0
        if args.command == "export":
            latest = read_json(storage, f"published/{store.store_id}/latest.json")
            if latest is None or not args.export_file:
                parser.error("Export requires a successful prior run and --export-file")
            manifest = read_json(storage, latest["manifest_key"])
            body = storage.read(manifest["data_key"])
            if body is None:
                raise FileNotFoundError("Missing published data")
            args.export_file.parent.mkdir(parents=True,exist_ok=True)
            args.export_file.write_bytes(body)
            print(json.dumps({"exported":str(args.export_file),"rows":manifest["records"],"source_mode":manifest["source_mode"]}))
            return 0
        if args.command == "clear-checkpoints":
            if not args.confirm_reset:
                parser.error("Specify --confirm-reset; this discards partial (not published) category progress")
            with storage.locked(store.store_id):
                for c in categories:
                    storage.delete(f"checkpoints/{store.store_id}/{c.slug}.json")
            print("Partial checkpoints reset. Previous successful release untouched.")
            return 0
        if args.minimum_products is not None and args.minimum_products < 1:
            parser.error("Minimum products must be >= 1")
        if args.source == "provider":
            if not args.authorized_source or os.environ.get("WALMART_DATA_AUTHORIZED") != "yes":
                parser.error("Provider mode requires --authorized-source and WALMART_DATA_AUTHORIZED=yes")
            source = AuthorizedProviderSource(os.environ.get("PROVIDER_BASE_URL", ""),os.environ.get("PROVIDER_API_TOKEN", ""))
            min_products = args.minimum_products or 500
        elif args.source == "opd":
            if not args.authorized_source or os.environ.get("WALMART_DATA_AUTHORIZED") != "yes":
                parser.error("OPD mode requires --authorized-source and WALMART_DATA_AUTHORIZED=yes")
            credentials = (os.environ.get("WALMART_OPD_CLIENT_ID", ""),
                           os.environ.get("WALMART_OPD_CLIENT_SECRET", ""))
            client = OPDClient(*credentials)
            mappings = json.loads(args.opd_mapping.read_text(encoding="utf-8"))
            cache_dir = args.opd_cache or (args.output / "opd-cache")
            source = WalmartOPDSnapshotSource(client, cache_dir, mappings, page_size=args.opd_page_size)
            min_products = args.minimum_products or 500
        else:
            source = FixtureSource(args.fixtures)
            min_products = args.minimum_products or 1
            print("WARNING: DEMO MODE — all records are synthetic and cannot serve as contest proof.",file=sys.stderr)
        canaries = json.loads(args.canaries.read_text(encoding="utf-8")) if args.canaries else {}
        result = Collector(storage, source, categories, min_products=min_products, canaries=canaries).run(store)
        print(json.dumps({"manifest": result["manifest"],"report":result["report"]}, indent=2))
        return 0
    except (Exception, KeyboardInterrupt) as exc:
        log.error("run_failed",extra={"event":"run_failed", "store_id":args.store})
        print(f"ERROR: {exc}",file=sys.stderr)
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
