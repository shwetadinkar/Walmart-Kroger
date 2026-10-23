"""One-time migration of a validated PRIVATE trial history to Azure Blob. Never overwrite."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from walmart_collector.brightdata_automatic import AzureBlobStore, LocalStore
from walmart_collector.schema import FIELDS


def seed(history_file, storage, store_id="100", zipcode="72712", confirm=False):
    hist = json.loads(Path(history_file).read_text(encoding="utf-8"))
    if hist.get("store_id") != store_id or hist.get("zipcode") != zipcode or not isinstance(hist.get("products"), dict):
        raise ValueError("History store/ZIP/products structure mismatch")
    for key, value in hist["products"].items():
        if not key.startswith(store_id + ":") or list(value.get("record", {})) != list(FIELDS):
            raise ValueError("Invalid product identity or noncompliant field ordering")
    key = f"brightdata-trials/{store_id}/history.json"
    if storage.get(key) is not None:
        raise RuntimeError("A prior Azure/local history already exists; refusing to overwrite it")
    if confirm:
        storage.put(key, Path(history_file).read_bytes())
    return {"store_id": store_id, "products": len(hist["products"]), "key": key, "uploaded": confirm}


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--history", required=True, type=Path)
    p.add_argument("--store-id", default="100")
    p.add_argument("--zipcode", default="72712")
    p.add_argument("--local-root", type=Path, help="For local testing; omit to use private Azure Blob")
    p.add_argument("--confirm-upload", action="store_true")
    a=p.parse_args(argv)
    store=LocalStore(a.local_root) if a.local_root else AzureBlobStore(os.environ["AZURE_STORAGE_CONNECTION_STRING"],os.environ.get("AZURE_BLOB_CONTAINER", "retail-collection"))
    print(json.dumps(seed(a.history,store,a.store_id,a.zipcode,a.confirm_upload),indent=2))


if __name__=="__main__":
    main()
