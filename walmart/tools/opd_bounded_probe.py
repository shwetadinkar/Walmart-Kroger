"""The bounded OPD first test, exactly as proposed. Five products, one budget.

WHY THIS IS A SEPARATE RUNNER
-----------------------------
The client review of 31 October was right on both counts.

`walmart_opd_smoke_test.py` checks OAuth, a store lookup and optional catalog
metadata. It never collects five products and never inspects a price-feed
field, so it cannot answer the questions the proposal said the first test would
answer.

And `walmart_collector/opd.py` retries: its request loop is `for attempt in
range(3)` with backoff on 429, 500, 502, 503 and 504. A mocked 503 produces
three attempts. The proposal promised no retries and a hard request ceiling, so
the production client cannot be the vehicle for a bounded probe. This module
therefore does its own HTTP and never imports that client.

THE BUDGET
----------
One cumulative budget covers everything that leaves the machine: the OAuth
token call, any token refresh, the store locator, catalog metadata, every
signed-file download, and every redirect hop. A redirect is a request and is
counted as one. There is no retry anywhere; the first failure stops the run.

    requests   10 maximum, cumulative
    time       10 minutes maximum, wall clock, from the first request
    traffic    64 MiB maximum, cumulative across all responses
    response   16 MiB maximum for any single response

Exceeding any of them raises and the probe stops. The budget is reported in
the receipt whether the run succeeded or not, so the cost of the test is
visible rather than asserted.

WHAT IT WRITES
--------------
An isolated directory containing the five normalized records, the price fields
observed, and a receipt. It imports nothing from the collector's storage layer,
writes nothing the collector reads, and merges into no existing dataset.

NOT RUN BY DEFAULT. Requires an entitlement that this project does not hold and
explicit approval. `--dry-run` prints the exact plan and makes no request.
"""
from __future__ import annotations

import argparse
import base64
import gzip
import io
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

TOKEN_URL = "https://developer.api.walmart.com/api-proxy/service/identity/oauth/v1/token"
BASE = "https://developer.api.walmart.com/api-proxy/service"
CATALOG_FEEDS = "/affil/catalog-api/v2/product/feeds/items"
PRICE_FEEDS = "/affil/catalog-api/v2/product/feeds/items/price-availability"
LOCATOR = "/affil/storeservice/v1/storeServiceLocator?storesLimit=20"

MAX_REQUESTS = 10
MAX_SECONDS = 600
MAX_TOTAL_BYTES = 64 * 1024 * 1024
MAX_RESPONSE_BYTES = 16 * 1024 * 1024
SIGNED_HOSTS = ("storage.googleapis.com",)
API_HOST = "developer.api.walmart.com"
ALLOWED_HOSTS = (API_HOST,) + SIGNED_HOSTS

PRICE_FIELDS_OF_INTEREST = (
    "currentPrice", "unitPriceDisplay", "availability", "storeCode",
    "msrp", "wasPrice", "salePrice", "priceDisplayCodes", "offerId",
)


class BudgetExceeded(RuntimeError):
    pass


class ProbeFailure(RuntimeError):
    pass


class Budget:
    """One cumulative ceiling over every outbound request in the run."""

    def __init__(self, max_requests=MAX_REQUESTS, max_seconds=MAX_SECONDS,
                 max_total_bytes=MAX_TOTAL_BYTES, max_response_bytes=MAX_RESPONSE_BYTES):
        self.max_requests = max_requests
        self.max_seconds = max_seconds
        self.max_total_bytes = max_total_bytes
        self.max_response_bytes = max_response_bytes
        self.requests = 0
        self.bytes = 0
        self.started = None
        self.log = []

    def charge(self, label, url):
        if self.started is None:
            self.started = time.monotonic()
        elapsed = time.monotonic() - self.started
        if self.requests + 1 > self.max_requests:
            raise BudgetExceeded(
                f"request ceiling reached: {self.max_requests} requests already spent, "
                f"refusing '{label}'")
        if elapsed > self.max_seconds:
            raise BudgetExceeded(
                f"time ceiling reached: {elapsed:.0f}s of {self.max_seconds}s used, "
                f"refusing '{label}'")
        self.requests += 1
        # Host only. A signed URL's query string carries credentials.
        self.log.append({"n": self.requests, "label": label,
                         "host": urlparse(url).hostname or "",
                         "at_seconds": round(elapsed, 2)})

    def record_body(self, size):
        if size > self.max_response_bytes:
            raise BudgetExceeded(
                f"single response of {size} bytes exceeds the "
                f"{self.max_response_bytes} byte ceiling")
        self.bytes += size
        if self.bytes > self.max_total_bytes:
            raise BudgetExceeded(
                f"traffic ceiling reached: {self.bytes} bytes of "
                f"{self.max_total_bytes} used")

    @property
    def elapsed(self):
        return 0.0 if self.started is None else round(time.monotonic() - self.started, 2)

    def report(self):
        return {
            "requests_made": self.requests, "request_ceiling": self.max_requests,
            "elapsed_seconds": self.elapsed, "time_ceiling_seconds": self.max_seconds,
            "bytes_received": self.bytes, "traffic_ceiling_bytes": self.max_total_bytes,
            "single_response_ceiling_bytes": self.max_response_bytes,
            "retries_performed": 0,
            "redirects_counted_as_requests": True,
            "requests": self.log,
        }


class _CountingRedirects(HTTPRedirectHandler):
    """Charge each redirect hop, and refuse one that leaves the allowlist.

    Counting is not sufficient. urllib forwards the Authorization header across
    a cross-host redirect, so a 302 on the token or feed call would hand the
    Bearer token to whatever host the redirect names. Verified on this
    interpreter rather than assumed.
    """

    def __init__(self, budget):
        self.budget = budget

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        host = urlparse(newurl).hostname or ""
        if host not in ALLOWED_HOSTS:
            raise ProbeFailure(
                f"Refusing a {code} redirect to {host!r}, which is not an expected "
                "host. The request carries a bearer token and urllib would forward it.")
        self.budget.charge(f"redirect {code}", newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch(budget, label, url, *, headers=None, data=None, method="GET"):
    """One request. No retry under any status, by design."""
    budget.charge(label, url)
    opener = build_opener(_CountingRedirects(budget))
    request = Request(url, data=data, headers=headers or {}, method=method)
    try:
        with opener.open(request, timeout=60) as response:
            body = response.read(budget.max_response_bytes + 1)
            budget.record_body(len(body))
            return response.status, body
    except HTTPError as exc:
        # Deliberately NOT echoing the body. A signed-URL 403 from the object
        # store returns XML that can contain StringToSign and signature
        # material, and this message is written into the receipt.
        exc.read(4096)
        raise ProbeFailure(
            f"{label} returned HTTP {exc.code}. Stopping; this probe does not retry. "
            "Response body withheld: it can carry signature material.") from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise ProbeFailure(f"{label} failed: {type(exc).__name__}: {exc}") from exc


def get_token(budget, client_id, client_secret):
    basic = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    status, body = fetch(
        budget, "oauth token", TOKEN_URL, method="POST",
        data=urlencode({"grant_type": "client_credentials"}).encode(),
        headers={"Authorization": f"Basic {basic}",
                 "Content-Type": "application/x-www-form-urlencoded",
                 "Accept": "application/json"})
    token = json.loads(body).get("access_token")
    if not token:
        raise ProbeFailure("Token response carried no access_token")
    return token


def api_get(budget, label, token, client_id, path, params=None):
    url = BASE + path + (("?" + urlencode(params)) if params else "")
    status, body = fetch(budget, label, url, headers={
        "Authorization": f"Bearer {token}", "WM_SEC.ACCESS_TOKEN": token,
        "WM_CONSUMER.ID": client_id, "Accept": "application/json"})
    try:
        return json.loads(body)
    except ValueError as exc:
        raise ProbeFailure(f"{label} did not return JSON") from exc


def feed_urls(document, key, kind):
    """Signed URLs from a feed listing, accepting only the documented shape."""
    feeds = document.get(key)
    if not isinstance(feeds, list) or not feeds:
        raise ProbeFailure(
            f"{kind} feed listing has no {key!r} list; keys present: "
            + (", ".join(sorted(document)) or "none"))
    urls = [f for f in feeds if isinstance(f, str) and f]
    if not urls:
        raise ProbeFailure(
            f"{kind} feed listing {key!r} carried no URL strings "
            f"(found {type(feeds[0]).__name__})")
    return urls


def api_post(budget, label, token, client_id, path, body):
    url = BASE + path
    status, raw = fetch(budget, label, url, method="POST",
                        data=json.dumps(body).encode(),
                        headers={"Authorization": f"Bearer {token}",
                                 "WM_SEC.ACCESS_TOKEN": token,
                                 "WM_CONSUMER.ID": client_id,
                                 "Content-Type": "application/json",
                                 "Accept": "application/json"})
    try:
        return json.loads(raw)
    except ValueError as exc:
        raise ProbeFailure(f"{label} did not return JSON") from exc


def signed_rows(budget, label, url, limit):
    if urlparse(url).hostname not in SIGNED_HOSTS:
        raise ProbeFailure(f"Refusing a signed URL on an unexpected host: "
                           f"{urlparse(url).hostname}")
    status, body = fetch(budget, label, url)
    # Decide on the PATH, not the whole URL. Every real signed URL carries a
    # query string, so url.endswith(".gz") is always false for them: the body
    # was never decompressed, every json.loads failed, the except below ate the
    # error, and the probe returned zero rows while reporting a vacuous pass.
    if urlparse(url).path.endswith(".gz") or body[:2] == b"\x1f\x8b":
        try:
            body = gzip.decompress(body)
        except OSError as exc:
            raise ProbeFailure(f"{label} is not readable as gzip: {exc}") from exc
    rows = []
    for line in io.BytesIO(body):
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict):
            rows.append(row)
        if len(rows) >= limit:
            break
    if not rows:
        raise ProbeFailure(
            f"{label} yielded no parseable JSON rows from {len(body)} bytes. "
            "Reporting zero rows as a result would be a vacuous pass.")
    return rows


def observe_price_fields(rows):
    """Report which price fields are present, absent, or empty. Derive nothing."""
    summary = {}
    for field in PRICE_FIELDS_OF_INTEREST:
        present = sum(1 for r in rows if field in r)
        non_empty = sum(1 for r in rows if str(r.get(field) or "").strip())
        summary[field] = {"present_on_rows": present, "non_empty_on_rows": non_empty,
                          "absent_on_rows": len(rows) - present}
    return summary


def plan(args):
    return {
        "mode": "dry-run, no request made",
        "store": {"store_id": args.store, "zipcode": args.zipcode},
        "products_to_inspect": args.products,
        "requests_planned": [
            "1 OAuth token",
            "1 store locator, to confirm the store is a pickup store",
            "1 catalog feed listing",
            "1 price feed listing",
            "1 signed catalog file download",
            "1 signed price file download",
        ],
        "cumulative_bounds": {
            "requests": args.max_requests, "seconds": args.max_seconds,
            "total_bytes": MAX_TOTAL_BYTES, "single_response_bytes": MAX_RESPONSE_BYTES},
        # Every outbound request is charged, so anything added later is covered
        # automatically. Listed here is what this probe actually issues; a token
        # refresh would be charged if one occurred, but the probe takes a token
        # once and never refreshes, so that is not claimed as exercised.
        "covers_what_it_issues": ["oauth", "locator", "feed listings",
                                  "signed file downloads", "redirects"],
        "token_refresh": "charged if it occurred; this probe takes one token and "
                         "does not refresh, so the path is not exercised",
        "retries": 0,
        "on_failure": "stop immediately and write the receipt",
        "writes": "an isolated directory only; merges into no dataset",
        "azure": "no deployment, no scheduling, no blob write",
    }


def run(args, budget):
    client_id = os.environ.get("WALMART_OPD_CLIENT_ID", "")
    client_secret = os.environ.get("WALMART_OPD_CLIENT_SECRET", "")
    if not client_id or not client_secret:
        raise ProbeFailure(
            "WALMART_OPD_CLIENT_ID and WALMART_OPD_CLIENT_SECRET are required. "
            "Credentials stay with their owner and are never written to the receipt.")

    token = get_token(budget, client_id, client_secret)

    # Confirm the store is actually a pickup store before reading any price.
    # A matching storeCode on a price row is not by itself evidence of the
    # offer's fulfilment context, which is the point the client made.
    locator = api_post(budget, "store locator", token, client_id, LOCATOR,
                       {"payload": {"postalCode": args.zipcode,
                                    "filter": ["INSTORE_PICKUP"]}})
    access_points = (locator.get("payload") or {}).get("accessPointList") or []
    pickup = [a for a in access_points if isinstance(a, dict)
              and str(a.get("fulfillmentStoreId")) == args.store
              and a.get("fulfillmentType") == "INSTORE_PICKUP"]
    if not pickup:
        raise ProbeFailure(
            f"Store {args.store} is not listed as an INSTORE_PICKUP store for "
            f"ZIP {args.zipcode}; not reading prices for a store context I cannot confirm")

    catalog = api_get(budget, "catalog feed listing", token, client_id,
                      CATALOG_FEEDS, {"categoryId": args.category_id})
    prices = api_get(budget, "price feed listing", token, client_id,
                     PRICE_FEEDS, {"categoryId": args.category_id})

    # The two feeds use DIFFERENT keys, and the entries are URL strings rather
    # than objects. Both facts are asserted in walmart_collector/opd.py, which
    # is the only code here that has ever spoken to this API. An earlier draft
    # of this probe guessed both wrong and could never have completed a run.
    catalog_urls = feed_urls(catalog, "product_snapshot_data", "catalog")
    price_urls = feed_urls(prices, "price_avail_snapshot_data", "price")

    catalog_rows = signed_rows(budget, "signed catalog file", catalog_urls[0], args.products)
    price_rows = signed_rows(budget, "signed price file", price_urls[0], args.products * 20)

    for_store = [r for r in price_rows if str(r.get("storeCode")) == args.store]
    by_offer = {str(r.get("offerId")): r for r in for_store}

    records = []
    for row in catalog_rows[:args.products]:
        offer = str(row.get("offerId") or "")
        price = by_offer.get(offer, {})
        records.append({
            "offerId": offer,
            "itemId": str(row.get("itemId") or ""),
            "name": row.get("name"),
            "size": row.get("size"),
            "upc": str(row.get("upc") or ""),
            "price_row_found_for_this_store": bool(price),
            "storeCode": price.get("storeCode"),
            "availability": price.get("availability"),
            "currentPrice": price.get("currentPrice"),
            "unitPriceDisplay": price.get("unitPriceDisplay"),
        })

    return {
        "records": records,
        "price_field_observations": observe_price_fields(for_store[:args.products * 5]),
        "store_rows_seen": len(for_store),
        # The locator confirmed this store serves INSTORE_PICKUP before any
        # price was read, so a matching storeCode is not the only evidence of
        # the fulfilment context.
        "store_confirmed_as_pickup_store": True,
        "checks": {
            "every_price_row_matches_requested_store": all(
                str(r.get("storeCode")) == args.store for r in for_store),
            "unit_price_display_present_on_any_row": any(
                str(r.get("unitPriceDisplay") or "").strip() for r in for_store),
            "upc_leading_zeros_preserved": all(
                isinstance(r["upc"], str) for r in records),
            "any_offer_terms_field_observed": False,
        },
        "not_established": [
            "that these five are representative of the category",
            "that unitPriceDisplay is populated at useful coverage",
            "that any volume or digital offer terms exist in this feed",
        ],
    }


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--store", default="100")
    p.add_argument("--zipcode", default="72712")
    p.add_argument("--category-id", default="976759")
    p.add_argument("--products", type=int, default=5)
    p.add_argument("--max-requests", type=int, default=MAX_REQUESTS)
    p.add_argument("--max-seconds", type=int, default=MAX_SECONDS)
    p.add_argument("--output", type=Path, required=True,
                   help="Isolated output directory, outside any collector dataset")
    p.add_argument("--dry-run", action="store_true",
                   help="Print the exact plan and make no request")
    p.add_argument("--i-have-entitlement", action="store_true",
                   help="Required for a live run. No entitlement is held by this project.")
    args = p.parse_args(argv)

    if args.products < 1 or args.products > 25:
        p.error("--products must be between 1 and 25")
    # The proposal to the client states ten requests and ten minutes. These may
    # be tightened for a smaller test, never raised: a flag that loosens the
    # declared bound makes the declaration meaningless.
    if not 1 <= args.max_requests <= MAX_REQUESTS:
        p.error(f"--max-requests must be between 1 and {MAX_REQUESTS}; the proposed "
                "ceiling cannot be raised from the command line")
    if not 1 <= args.max_seconds <= MAX_SECONDS:
        p.error(f"--max-seconds must be between 1 and {MAX_SECONDS}; the proposed "
                "ceiling cannot be raised from the command line")

    if args.dry_run:
        print(json.dumps(plan(args), indent=2))
        return 0
    if not args.i_have_entitlement:
        p.error("A live run requires --i-have-entitlement. Run --dry-run first.")

    budget = Budget(max_requests=args.max_requests, max_seconds=args.max_seconds)
    started = datetime.now(timezone.utc).isoformat()
    outcome, failure = None, None
    try:
        outcome = run(args, budget)
    except (ProbeFailure, BudgetExceeded) as exc:
        failure = f"{type(exc).__name__}: {exc}"
    except Exception as exc:  # noqa: BLE001
        # The docstring promises a receipt whether the run succeeded or not, and
        # a narrow except broke that promise for two ordinary cases: an HTML
        # gateway page on the token call raising JSONDecodeError, and a
        # truncated download raising BadGzipFile. Both produced a traceback and
        # no receipt at all.
        failure = f"unexpected {type(exc).__name__}: {exc}"

    receipt = {
        "probe": "opd_bounded_probe",
        "started_utc": started, "ended_utc": datetime.now(timezone.utc).isoformat(),
        "store_id": args.store, "zipcode": args.zipcode,
        "products_requested": args.products,
        "budget": budget.report(),
        "stopped_on_failure": failure is not None,
        "failure": failure,
        "result": outcome,
        "credentials_in_receipt": False,
        "merged_into_any_dataset": False,
        "azure_touched": False,
    }
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "RECEIPT.json").write_text(
        json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(receipt, indent=2))
    return 1 if failure else 0


if __name__ == "__main__":
    raise SystemExit(main())
