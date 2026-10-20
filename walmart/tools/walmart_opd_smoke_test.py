"""Official Walmart I/O OPD read-only connectivity test.

Requires access approved for the intended use, plus WALMART_OPD_CLIENT_ID
and WALMART_OPD_CLIENT_SECRET. Never prints secrets or access tokens.

Endpoints from official Walmart I/O OPD documentation:
  POST /identity/oauth/v1/token
  POST /affil/storeservice/v1/storeServiceLocator
  GET  /affil/catalog-api/v2/product/feeds/items (optional metadata only)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

BASE = "https://developer.api.walmart.com/api-proxy/service"
STORES = {"100": ("72712", "Bentonville, AR"), "5959": ("77007", "Houston, TX")}


class ProbeError(RuntimeError):
    """Expected connectivity, access or response problem (no secrets included)."""


def api_json(method: str, path: str, headers: dict[str, str], data: dict | None = None, timeout: int = 20) -> dict:
    body = None
    if data is not None:
        if headers.get("Content-Type") == "application/x-www-form-urlencoded":
            body = urllib.parse.urlencode(data).encode("utf-8")
        else:
            body = json.dumps(data).encode("utf-8")
    req = urllib.request.Request(BASE + path, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            result = json.load(resp)
    except urllib.error.HTTPError as exc:
        # Do not print response bodies, which might expose sensitive account details.
        suffix = "check credentials and API subscription" if exc.code in (401, 403) else "check API status, permissions and request shape"
        raise ProbeError(f"{path}: HTTP {exc.code}; {suffix}") from None
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise ProbeError(f"{path}: network or TLS error ({type(exc).__name__})") from None
    except (ValueError, TypeError):
        raise ProbeError(f"{path}: response was not valid JSON") from None
    if not isinstance(result, dict):
        raise ProbeError(f"{path}: JSON response is not an object")
    return result


def get_token(client_id: str, client_secret: str) -> str:
    data = api_json(
        "POST", "/identity/oauth/v1/token",
        {"wm_consumer.id": client_id, "Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json", "cache-control": "no-cache"},
        {"grant_type": "client_credentials", "client_id": client_id, "client_secret": client_secret},
    )
    token = data.get("access_token")
    if not isinstance(token, str) or not token:
        raise ProbeError("OAuth endpoint did not return access_token")
    return token


def store_ids_from_response(data: dict) -> list[dict]:
    payload = data.get("payload", {})
    aps = payload.get("accessPointList", []) if isinstance(payload, dict) else []
    if not isinstance(aps, list):
        raise ProbeError("Unexpected store locator response: accessPointList not a list")
    return [ap for ap in aps if isinstance(ap, dict)]


def query_store(client_id: str, token: str, store_id: str) -> dict:
    zip_code, city = STORES[store_id]
    result = api_json(
        "POST", "/affil/storeservice/v1/storeServiceLocator?storesLimit=20",
        {"wm_consumer.id": client_id, "Authorization": "Bearer " + token, "Content-Type": "application/json", "Accept": "application/json"},
        {"payload": {"postalCode": zip_code, "filter": ["INSTORE_PICKUP"]}},
    )
    accesspoints = store_ids_from_response(result)
    matching = [p for p in accesspoints if str(p.get("fulfillmentStoreId", "")) == store_id]
    output = {"zip": zip_code, "expected_store_id": store_id, "expected_area": city,
              "accesspoints_returned": len(accesspoints), "store_found": bool(matching),
              "store_name": matching[0].get("accessPointName", "") if matching else "",
              "status": "STORE_CONFIRMED" if matching else "STORE_NOT_CONFIRMED"}
    return output


def query_catalog_metadata(client_id: str, token: str) -> dict:
    result = api_json(
        "GET", "/affil/catalog-api/v2/product/feeds/items",
        {"wm_consumer.id": client_id, "Authorization": "Bearer " + token, "Accept": "application/json"},
    )
    feeds = result.get("product_snapshot_data", [])
    if not isinstance(feeds, list):
        raise ProbeError("Catalog response has no expected product_snapshot_data array")
    # Never print time-limited signed URLs.
    return {"snapshot_date": result.get("snapshot_date", ""), "feed_files": len(feeds),
            "note": "Catalog metadata only. Feed not downloaded; not store-specific."}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Walmart I/O OPD authorized smoke test")
    parser.add_argument("--store", choices=[*STORES, "both"], default="both")
    parser.add_argument("--dry-run", action="store_true", help="Show request plan without making calls or needing credentials")
    parser.add_argument("--catalog", action="store_true", help="Also check catalog feed metadata (not store prices)")
    args = parser.parse_args(argv)
    ids = list(STORES) if args.store == "both" else [args.store]
    plan = {"mode": "DRY_RUN" if args.dry_run else "LIVE_AUTHENTICATED_API",
            "credential_required": not args.dry_run,
            "oauth_endpoint": BASE + "/identity/oauth/v1/token",
            "store_locator_endpoint": BASE + "/affil/storeservice/v1/storeServiceLocator",
            "stores": [{"store_id": sid, "zipcode": STORES[sid][0]} for sid in ids],
            "optional_catalog_metadata": args.catalog}
    if args.dry_run:
        print(json.dumps(plan, indent=2))
        print("NOTE: This only checks the planned request; NO Walmart API data was obtained.")
        return 0

    cid = os.environ.get("WALMART_OPD_CLIENT_ID", "").strip()
    secret = os.environ.get("WALMART_OPD_CLIENT_SECRET", "").strip()
    if not cid or not secret:
        print("Missing WALMART_OPD_CLIENT_ID and/or WALMART_OPD_CLIENT_SECRET. Run --dry-run first.", file=sys.stderr)
        return 2
    try:
        token = get_token(cid, secret)
        print("OAuth authentication: SUCCESS (access token hidden)")
        ok = True
        for sid in ids:
            result = query_store(cid, token, sid)
            print(json.dumps(result, indent=2))
            ok = ok and result["store_found"]
        if args.catalog:
            print("Catalog metadata:", json.dumps(query_catalog_metadata(cid, token), indent=2))
        print("NOTE: Store lookup/catalog metadata alone do not prove local product prices, PPM, coupon fields, or rights for this use.")
        return 0 if ok else 3
    except ProbeError as exc:
        print("API TEST FAILED:", exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
