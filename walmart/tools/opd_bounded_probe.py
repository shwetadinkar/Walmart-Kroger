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

    requests      10 maximum, cumulative
    time          10 minutes maximum, wall clock, across the whole run
    traffic       64 MiB maximum, cumulative across all responses
    response      16 MiB maximum for any single response
    decompressed  256 MiB maximum, cumulative, counted as it expands

Exceeding any of them stops the probe. Bytes are counted as they arrive, so a
refused response and an error body are in the total. The clock covers reads,
decompression, parsing and evidence writing, not only the dispatch of requests:
work runs on a worker thread that the supervisor abandons at the deadline, and
the last 15 seconds (or a tenth of a shorter limit) are reserved for
finalization, which writes what it can and always writes the receipt.

WHAT SUCCESS MEANS
------------------
Exit 0 only when the requested number of catalog offers was matched to a price
row for this store. Exit 3 is an incomplete result, with the reasons stated.
Exit 1 is a failure. A completed transport is not a result. A flag over rows
that were never examined is false, and a miss is reported against the files
actually read, because only one file of each feed is downloaded.

WHAT IT WRITES
--------------
An isolated directory containing the normalized records, the price fields
observed, a receipt, and sanitized evidence: the locator and feed listings, a
sample of the raw rows, and per-response snapshot identity and capture time.
It imports nothing from the collector's storage layer, writes nothing the
collector reads, and merges into no existing dataset.

NOT RUN BY DEFAULT. Requires an entitlement that this project does not hold and
explicit approval. `--dry-run` prints the exact plan and makes no request.
"""
from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import io
import json
import os
import re
import sys
import threading
import time
import zlib
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
MAX_DECOMPRESSED_BYTES = 256 * 1024 * 1024
MAX_ERROR_BODY_BYTES = 64 * 1024
FINALIZE_SECONDS = 15
READ_CHUNK = 64 * 1024
EVIDENCE_ROWS = 200
REQUEST_TIMEOUT = 60
EXIT_OK, EXIT_FAILURE, EXIT_INCOMPLETE = 0, 1, 3
SNAPSHOT_HEADERS = ("ETag", "Last-Modified", "Date", "Content-Length",
                    "x-goog-generation", "x-goog-stored-content-length")
_SECRET_KEY = re.compile(r"token|secret|signature|authorization|credential|password", re.I)
_OFFER_TERMS_KEY = re.compile(r"promo|deal|coupon|rollback|clearance|saving|discount", re.I)
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
    """One cumulative ceiling over everything the run spends."""

    def __init__(self, max_requests=MAX_REQUESTS, max_seconds=MAX_SECONDS,
                 max_total_bytes=MAX_TOTAL_BYTES, max_response_bytes=MAX_RESPONSE_BYTES,
                 max_decompressed_bytes=MAX_DECOMPRESSED_BYTES, finalize_seconds=0):
        self.max_requests = max_requests
        self.max_seconds = max_seconds
        self.max_total_bytes = max_total_bytes
        self.max_response_bytes = max_response_bytes
        self.max_decompressed_bytes = max_decompressed_bytes
        self.finalize_seconds = min(finalize_seconds, max_seconds / 10)
        self.requests = 0
        self.bytes = 0
        self.decompressed_bytes = 0
        self.started = None
        self.stopped = False
        self.log = []
        self.captures = []

    def start(self):
        if self.started is None:
            self.started = time.monotonic()

    def stop(self):
        """Refuse everything from now on. An abandoned worker that wakes after
        the deadline must not spend more or change what the receipt reports."""
        self.stopped = True

    @property
    def work_seconds(self):
        return self.max_seconds - self.finalize_seconds

    def remaining(self):
        self.start()
        return self.work_seconds - (time.monotonic() - self.started)

    def hard_remaining(self):
        self.start()
        return self.max_seconds - (time.monotonic() - self.started)

    def check(self, label):
        if self.stopped:
            raise BudgetExceeded(f"run already stopped, refusing '{label}'")
        if self.remaining() < 0:
            raise BudgetExceeded(
                f"time ceiling reached: {self.elapsed:.0f}s of {self.work_seconds:.0f}s "
                f"working time used, refusing '{label}'")

    def charge(self, label, url):
        self.start()
        if self.requests + 1 > self.max_requests:
            raise BudgetExceeded(
                f"request ceiling reached: {self.max_requests} requests already spent, "
                f"refusing '{label}'")
        self.check(label)
        self.requests += 1
        # Host only. A signed URL's query string carries credentials.
        self.log.append({"n": self.requests, "label": label,
                         "host": urlparse(url).hostname or "",
                         "at_seconds": self.elapsed})

    def record_chunk(self, response_size, chunk_size):
        """Count first, judge second, so a refused body is still in the total."""
        self.bytes += chunk_size
        if response_size > self.max_response_bytes:
            raise BudgetExceeded(
                f"single response of {response_size} bytes exceeds the "
                f"{self.max_response_bytes} byte ceiling")
        if self.bytes > self.max_total_bytes:
            raise BudgetExceeded(
                f"traffic ceiling reached: {self.bytes} bytes of "
                f"{self.max_total_bytes} used")

    def record_body(self, size):
        self.record_chunk(size, size)

    def record_decompressed(self, size):
        self.decompressed_bytes += size
        if self.decompressed_bytes > self.max_decompressed_bytes:
            raise BudgetExceeded(
                f"decompression ceiling reached: {self.decompressed_bytes} bytes of "
                f"{self.max_decompressed_bytes} used")

    def capture(self, label, url, status, size, digest="", headers=None):
        parsed = urlparse(url)
        self.captures.append({
            "label": label, "host": parsed.hostname or "", "path": parsed.path,
            "status": status, "captured_utc": datetime.now(timezone.utc).isoformat(),
            "bytes": size, "sha256": digest,
            "response_headers": {k: headers.get(k) for k in SNAPSHOT_HEADERS
                                 if headers is not None and headers.get(k)}})

    @property
    def elapsed(self):
        return 0.0 if self.started is None else round(time.monotonic() - self.started, 2)

    def report(self):
        return {
            "requests_made": self.requests, "request_ceiling": self.max_requests,
            "elapsed_seconds": self.elapsed, "time_ceiling_seconds": self.max_seconds,
            "finalization_reserve_seconds": self.finalize_seconds,
            "bytes_received": self.bytes, "traffic_ceiling_bytes": self.max_total_bytes,
            "single_response_ceiling_bytes": self.max_response_bytes,
            "bytes_decompressed": self.decompressed_bytes,
            "decompression_ceiling_bytes": self.max_decompressed_bytes,
            "retries_performed": 0,
            "redirects_counted_as_requests": True,
            "requests": list(self.log),
            "captures": list(self.captures),
        }


def read_counted(budget, label, stream, limit=None):
    """Read in chunks, counting and checking the clock as bytes arrive."""
    chunks, size = [], 0
    while True:
        budget.check(label)
        chunk = stream.read(READ_CHUNK)
        if not chunk:
            return b"".join(chunks), size
        size += len(chunk)
        budget.record_chunk(size, len(chunk))
        chunks.append(chunk)
        if limit is not None and size >= limit:
            return b"".join(chunks), size


class _CountingRedirects(HTTPRedirectHandler):
    """Charge each redirect hop, and refuse one that leaves THIS request's host.

    Counting is not sufficient. urllib forwards the Authorization header across
    a cross-host redirect, so a 302 on the token or feed call would hand the
    Bearer token to whatever host the redirect names. Verified on this
    interpreter rather than assumed.
    """

    def __init__(self, budget, allowed_hosts):
        self.budget = budget
        # Per request. A global allowlist let a 302 on the OAuth call redirect
        # to the signed-download host, which is multi-tenant, carrying the
        # Basic credentials with it. An API call may only redirect within the
        # API host; a signed download only within the object store.
        self.allowed_hosts = tuple(allowed_hosts)

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        host = urlparse(newurl).hostname or ""
        if host not in self.allowed_hosts:
            raise ProbeFailure(
                f"Refusing a {code} redirect to {host!r}; this request may only "
                f"redirect within {self.allowed_hosts}. The request carries credentials "
                "and urllib would forward them across hosts.")
        self.budget.charge(f"redirect {code}", newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)

    def http_error_302(self, req, fp, code, msg, headers):
        # urllib reads a redirect's body in full, unbounded and uncounted,
        # before following it. Spend it through the budget first.
        read_counted(self.budget, f"redirect {code} body", fp, MAX_ERROR_BODY_BYTES)
        return super().http_error_302(req, fp, code, msg, headers)

    http_error_301 = http_error_303 = http_error_307 = http_error_302
    http_error_308 = http_error_302


def fetch(budget, label, url, *, headers=None, data=None, method="GET",
          allowed_hosts=None):
    """One request. No retry under any status, by design."""
    host = urlparse(url).hostname or ""
    allowed = tuple(allowed_hosts) if allowed_hosts else (host,)
    if host not in allowed:
        raise ProbeFailure(f"{label} targets {host!r}, which is not in {allowed}")
    budget.charge(label, url)
    opener = build_opener(_CountingRedirects(budget, allowed))
    request = Request(url, data=data, headers=headers or {}, method=method)
    timeout = max(0.01, min(REQUEST_TIMEOUT, budget.remaining()))
    try:
        with opener.open(request, timeout=timeout) as response:
            body, size = read_counted(budget, label, response)
            budget.capture(label, url, response.status, size,
                           hashlib.sha256(body).hexdigest(),
                           getattr(response, "headers", None))
            return response.status, body
    except HTTPError as exc:
        # Deliberately NOT echoing the body. A signed-URL 403 from the object
        # store returns XML that can contain StringToSign and signature
        # material, and this message is written into the receipt.
        _, size = read_counted(budget, label, exc, MAX_ERROR_BODY_BYTES)
        budget.capture(label, url, exc.code, size)
        raise ProbeFailure(
            f"{label} returned HTTP {exc.code}. Stopping; this probe does not retry. "
            "Response body withheld: it can carry signature material.") from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise ProbeFailure(f"{label} failed: {type(exc).__name__}: {exc}") from exc


def get_token(budget, client_id, client_secret):
    basic = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    status, body = fetch(
        budget, "oauth token", TOKEN_URL, method="POST", allowed_hosts=(API_HOST,),
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
    status, body = fetch(budget, label, url, allowed_hosts=(API_HOST,), headers={
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
                        data=json.dumps(body).encode(), allowed_hosts=(API_HOST,),
                        headers={"Authorization": f"Bearer {token}",
                                 "WM_SEC.ACCESS_TOKEN": token,
                                 "WM_CONSUMER.ID": client_id,
                                 "Content-Type": "application/json",
                                 "Accept": "application/json"})
    try:
        return json.loads(raw)
    except ValueError as exc:
        raise ProbeFailure(f"{label} did not return JSON") from exc


def _scan(rows, limit, keep, stats, check):
    kept = []
    for row in rows:
        stats["rows_read"] = stats.get("rows_read", 0) + 1
        if len(stats.setdefault("head", [])) < 5:
            stats["head"].append(row)
        if check and stats["rows_read"] % 2048 == 0:
            check()
        if keep is None or keep(row):
            kept.append(row)
        if limit is not None and len(kept) >= limit:
            stats["stopped_at_limit"] = True
            break
    return kept


def _json_lines(text):
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict):
            yield row


def parse_feed_body(body, kind, limit=None, *, keep=None, stats=None, check=None):
    """Parse a feed body the way walmart_collector/opd.py does.

    The two feeds are NOT the same format, which an earlier version of this
    probe assumed. opd.py:215 reads the PRICE feed with
    csv.DictReader(delimiter="^") and the CATALOG feed as newline-delimited
    JSON *or* a JSON array. Assuming NDJSON for both meant a live run would
    have failed on its last request, and the test that claimed conformance
    served NDJSON from its own mock rather than the documented shape.

    `keep` retains only the rows wanted, so a 256 MiB national feed is scanned
    in full without being materialised. `limit` counts kept rows. `stats` gets
    rows_read, the first rows seen, and whether the limit stopped the scan.
    """
    stats = {} if stats is None else stats
    text = body.decode("utf-8-sig", "replace")
    if kind == "price":
        rows = (dict(r) for r in csv.DictReader(io.StringIO(text), delimiter="^"))
    else:
        stripped = text.lstrip()
        if stripped.startswith("["):
            rows = (r for r in json.loads(stripped) if isinstance(r, dict))
        else:
            rows = _json_lines(stripped)
    return _scan(rows, limit, keep, stats, check)


def gunzip_bounded(budget, label, body):
    """Expand under the decompression ceiling, as the bytes appear."""
    out, data = [], body
    while data:
        expander = zlib.decompressobj(16 + zlib.MAX_WBITS)
        try:
            while not expander.eof:
                budget.check(label)
                chunk = expander.decompress(data, READ_CHUNK)
                data = expander.unconsumed_tail
                if chunk:
                    budget.record_decompressed(len(chunk))
                    out.append(chunk)
                elif not data:
                    raise ProbeFailure(f"{label} is a truncated gzip stream")
        except zlib.error as exc:
            raise ProbeFailure(f"{label} is not readable as gzip: {exc}") from exc
        data = expander.unused_data.lstrip(b"\0")
    return b"".join(out)


def signed_rows(budget, label, url, limit, kind, *, keep=None, stats=None):
    if urlparse(url).hostname not in SIGNED_HOSTS:
        raise ProbeFailure(f"Refusing a signed URL on an unexpected host: "
                           f"{urlparse(url).hostname}")
    status, body = fetch(budget, label, url, allowed_hosts=SIGNED_HOSTS)
    # Decide on the PATH, not the whole URL. Every real signed URL carries a
    # query string, so url.endswith(".gz") is always false for them: the body
    # was never decompressed, every json.loads failed, the except below ate the
    # error, and the probe returned zero rows while reporting a vacuous pass.
    if urlparse(url).path.endswith(".gz") or body[:2] == b"\x1f\x8b":
        body = gunzip_bounded(budget, label, body)
    stats = {} if stats is None else stats
    rows = parse_feed_body(body, kind, limit, keep=keep, stats=stats,
                           check=lambda: budget.check(label))
    budget.check(label)
    if not stats.get("rows_read"):
        raise ProbeFailure(
            f"{label} yielded no parseable {kind} rows from {len(body)} bytes. "
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


def sanitize(value):
    """Keep the shape and the snapshot identity of a response, without what
    would let a reader fetch it: no query strings, no token-like fields."""
    if isinstance(value, dict):
        return {k: sanitize(v) for k, v in value.items() if not _SECRET_KEY.search(str(k))}
    if isinstance(value, list):
        return [sanitize(v) for v in value]
    if isinstance(value, str) and "://" in value:
        return re.sub(r"[?#]\S*", "", value)
    return value


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
            "1 signed price file download, scanned in full for this store",
            "1 signed catalog file download, scanned for the offers found",
        ],
        "cumulative_bounds": {
            "requests": args.max_requests, "seconds": args.max_seconds,
            "total_bytes": MAX_TOTAL_BYTES, "single_response_bytes": MAX_RESPONSE_BYTES,
            "decompressed_bytes": MAX_DECOMPRESSED_BYTES,
            "finalization_reserve_seconds": min(FINALIZE_SECONDS, args.max_seconds / 10)},
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
        "exit_codes": {"0": "the requested matched sample was obtained",
                       "1": "failed or stopped by a ceiling",
                       "3": "ran, but the matched sample is incomplete"},
        "writes": "an isolated directory only; merges into no dataset",
        "azure": "no deployment, no scheduling, no blob write",
    }


def run(args, budget, evidence=None):
    evidence = {} if evidence is None else evidence
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
    evidence["locator_response"] = sanitize(locator)
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
    evidence["catalog_listing"] = sanitize(catalog)
    prices = api_get(budget, "price feed listing", token, client_id,
                     PRICE_FEEDS, {"categoryId": args.category_id})
    evidence["price_listing"] = sanitize(prices)

    # The two feeds use DIFFERENT keys, and the entries are URL strings rather
    # than objects. Both facts are asserted in walmart_collector/opd.py, which
    # is the only code here that has ever spoken to this API. An earlier draft
    # of this probe guessed both wrong and could never have completed a run.
    catalog_urls = feed_urls(catalog, "product_snapshot_data", "catalog")
    price_urls = feed_urls(prices, "price_avail_snapshot_data", "price")

    # Price first, scanned whole, then the catalog for exactly those offers.
    # Reading the first five catalog rows and the first hundred price rows
    # treated "not in this prefix" as "not in the feed".
    price_stats, catalog_stats = {}, {}
    for_store = signed_rows(
        budget, "signed price file", price_urls[0], None, "price",
        keep=lambda r: str(r.get("storeCode")) == args.store, stats=price_stats)
    evidence["price_rows"] = sanitize(
        {"first_rows_of_file": price_stats["head"],
         "rows_for_this_store": for_store[:EVIDENCE_ROWS]})
    by_offer = {str(r.get("offerId")): r for r in for_store if r.get("offerId")}

    matched = signed_rows(
        budget, "signed catalog file", catalog_urls[0], args.products, "catalog",
        keep=lambda r: str(r.get("offerId") or "") in by_offer, stats=catalog_stats)
    evidence["catalog_rows"] = sanitize(
        {"first_rows_of_file": catalog_stats["head"], "rows_matched": matched})

    records = []
    for row in matched:
        offer = str(row.get("offerId") or "")
        price = by_offer[offer]
        records.append({
            "offerId": offer,
            "itemId": str(row.get("itemId") or ""),
            "name": row.get("name"),
            "size": row.get("size"),
            "upc": str(row.get("upc") or ""),
            "price_row_found_for_this_store": True,
            "storeCode": price.get("storeCode"),
            "availability": price.get("availability"),
            "currentPrice": price.get("currentPrice"),
            "unitPriceDisplay": price.get("unitPriceDisplay"),
        })

    files_read = {"catalog": f"1 of {len(catalog_urls)}", "price": f"1 of {len(price_urls)}"}
    incomplete = []
    if not for_store:
        incomplete.append(
            f"no price row for store {args.store} among {price_stats['rows_read']} rows read")
    if len(records) < args.products:
        incomplete.append(
            f"{len(records)} of {args.products} requested offers matched a price row "
            f"for this store; files read: catalog {files_read['catalog']}, "
            f"price {files_read['price']}")
    examined_keys = {k for r in price_stats["head"] + catalog_stats["head"] + for_store[:EVIDENCE_ROWS]
                     for k in r}
    return {
        "status": "INCOMPLETE" if incomplete else "COMPLETE",
        "complete": not incomplete,
        "incomplete_reasons": incomplete,
        "products_requested": args.products,
        "matched_records": len(records),
        "records": records,
        "price_field_observations": observe_price_fields(for_store[:args.products * 5]),
        "store_rows_seen": len(for_store),
        "feed_coverage": {
            "files_read": files_read,
            "price_rows_read": price_stats["rows_read"],
            "catalog_rows_read": catalog_stats["rows_read"],
        },
        # The locator confirmed this store serves INSTORE_PICKUP before any
        # price was read, so a matching storeCode is not the only evidence of
        # the fulfilment context.
        "store_confirmed_as_pickup_store": True,
        # Each flag says what was examined. Over no rows it is false, because
        # "every row" over nothing is not an observation.
        "checks": {
            "every_price_row_matches_requested_store":
                len(for_store) == price_stats["rows_read"] > 0,
            "unit_price_display_present_on_any_row": any(
                str(r.get("unitPriceDisplay") or "").strip() for r in for_store),
            "upc_leading_zeros_preserved": bool(matched) and all(
                isinstance(r.get("upc"), str) and r["upc"] for r in matched),
            "any_offer_terms_field_observed": any(
                _OFFER_TERMS_KEY.search(k) for k in examined_keys),
        },
        "not_established": [
            "that these products are representative of the category",
            "that unitPriceDisplay is populated at useful coverage",
            "that any volume or digital offer terms exist in this feed",
            "that an offer missing here is missing from the feed: only the files "
            "counted in feed_coverage were read",
            "the fulfilment of every price row: the locator shows the store offers "
            "pickup, not that this row's offer is a pickup offer",
            "whether currentPrice on a given row is a regular or a sale price",
        ],
    }


def supervise(args, budget, evidence):
    """Run the work on a thread the deadline can abandon.

    A cooperative check cannot interrupt a json.loads or a stalled socket read,
    so the deadline is held here. The worker is a daemon and writes nothing to
    disk, so abandoning it can neither block exit nor corrupt the output.
    Returns (outcome, failure).
    """
    box = {}

    def work():
        try:
            box["outcome"] = run(args, budget, evidence)
            budget.check("completion")
        except (ProbeFailure, BudgetExceeded) as exc:
            box["failure"] = f"{type(exc).__name__}: {exc}"
        except Exception as exc:  # noqa: BLE001
            # The docstring promises a receipt whether the run succeeded or
            # not, and a narrow except broke that promise for two ordinary
            # cases: an HTML gateway page on the token call raising
            # JSONDecodeError, and a truncated download. Both produced a
            # traceback and no receipt at all.
            box["failure"] = f"unexpected {type(exc).__name__}: {exc}"

    budget.start()
    worker = threading.Thread(target=work, name="opd-probe", daemon=True)
    worker.start()
    worker.join(max(0.0, budget.remaining()))
    if worker.is_alive():
        budget.stop()
        return None, (f"BudgetExceeded: time ceiling reached: a stage was still running "
                      f"after {budget.elapsed:.0f}s and was abandoned")
    return box.get("outcome"), box.get("failure")


def write_atomic(path, payload):
    temporary = path.with_name(path.name + ".partial")
    temporary.write_bytes(payload)
    os.replace(temporary, path)


def finalize(output, receipt, evidence, budget):
    """Write evidence while time remains, then always the receipt."""
    output.mkdir(parents=True, exist_ok=True)
    written, skipped = {}, []
    for name, content in sorted(dict(evidence).items()):
        if budget.hard_remaining() <= 0:
            skipped.append(name)
            continue
        payload = (json.dumps(content, indent=2) + "\n").encode("utf-8")
        (output / "evidence").mkdir(exist_ok=True)
        write_atomic(output / "evidence" / f"{name}.json", payload)
        written[name] = {"bytes": len(payload),
                         "sha256": hashlib.sha256(payload).hexdigest()}
    receipt["evidence"] = {"written": written, "skipped_at_deadline": skipped}
    receipt["budget"] = budget.report()
    write_atomic(output / "RECEIPT.json",
                 (json.dumps(receipt, indent=2) + "\n").encode("utf-8"))


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

    budget = Budget(max_requests=args.max_requests, max_seconds=args.max_seconds,
                    finalize_seconds=FINALIZE_SECONDS)
    started = datetime.now(timezone.utc).isoformat()
    evidence = {}
    outcome, failure = supervise(args, budget, evidence)
    if failure and outcome:
        # Finished, but past a ceiling. What it found stays visible, and it
        # does not read as a success.
        outcome.update(status="INCOMPLETE", complete=False,
                       incomplete_reasons=outcome["incomplete_reasons"] + [failure])
    complete = bool(outcome and outcome.get("complete")) and not failure

    receipt = {
        "probe": "opd_bounded_probe",
        "started_utc": started, "ended_utc": datetime.now(timezone.utc).isoformat(),
        "store_id": args.store, "zipcode": args.zipcode,
        "products_requested": args.products,
        "result_status": "COMPLETE" if complete else "INCOMPLETE",
        "stopped_on_failure": failure is not None,
        "failure": failure,
        "result": outcome,
        "credentials_in_receipt": False,
        "merged_into_any_dataset": False,
        "azure_touched": False,
    }
    finalize(args.output, receipt, evidence, budget)
    print(json.dumps(receipt, indent=2))
    if failure:
        return EXIT_FAILURE
    return EXIT_OK if complete else EXIT_INCOMPLETE


if __name__ == "__main__":
    raise SystemExit(main())
