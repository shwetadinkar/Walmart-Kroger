"""Walmart I/O OPD *documented* catalog + store-price snapshot integration.

Authenticated only. The documentation does not provide coupon/volume deal details;
those fields are not fabricated. An OPD feed is NOT a proof of exact site taxonomy
coverage or contractual right to store/export data; both require client review.

Documented endpoints: Walmart I/O OPD Product Catalog Snapshot, Store Locator,
Pricing & Availability Snapshot, Pricing & Availability Realtime.
"""
from __future__ import annotations

import csv
import gzip
import io
import json
import os
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from .sources import Page, SourceError, AccessChallenge

BASE = "https://developer.api.walmart.com/api-proxy/service"
TOKEN = "/identity/oauth/v1/token"
LOCATOR = "/affil/storeservice/v1/storeServiceLocator?storesLimit=20"
CATALOG = "/affil/catalog-api/v2/product/feeds/items"
PRICE_SNAPSHOT = "/affil/catalog-api/v2/product/feeds/items/price-availability"
REALTIME = "/affil/catalog-api/v2/product/items/price-availability/"


class OPDClient:
    def __init__(self, client_id: str, client_secret: str, timeout=60):
        if not client_id or not client_secret:
            raise SourceError("Missing WALMART_OPD_CLIENT_ID / WALMART_OPD_CLIENT_SECRET")
        self.client_id, self._secret, self.timeout = client_id, client_secret, timeout
        self._token = ""
        self._token_until = 0.0

    def _json(self, method, path, data=None, token=True, allow_refresh=True):
        import urllib.parse
        hdr = {"WM_CONSUMER.ID": self.client_id, "Accept": "application/json"}
        if token:
            self._authorize()
            hdr["Authorization"] = "Bearer " + self._token
            hdr["Content-Type"] = "application/json"
            body = json.dumps(data).encode() if data is not None else None
        else:
            hdr.update({"Content-Type": "application/x-www-form-urlencoded", "cache-control": "no-cache"})
            body = urllib.parse.urlencode(data).encode() if data else None
        req = Request(BASE + path, headers=hdr, data=body, method=method)
        for attempt in range(3):
            try:
                with urlopen(req, timeout=self.timeout) as resp:
                    value = json.load(resp)
                break
            except HTTPError as exc:
                if exc.code == 401 and token and allow_refresh:
                    self._token, self._token_until = "", 0
                    return self._json(method, path, data=data, token=token, allow_refresh=False)
                if exc.code in (401, 403):
                    raise AccessChallenge(f"Walmart OPD {path.split('?')[0]} HTTP {exc.code}; access/permission denied") from None
                if exc.code in (429, 500, 502, 503, 504) and attempt < 2:
                    time.sleep(2**attempt)
                    continue
                raise SourceError(f"Walmart OPD {path.split('?')[0]} HTTP {exc.code}") from None
            except (URLError, OSError) as exc:
                if attempt < 2:
                    time.sleep(2**attempt)
                    continue
                raise SourceError(f"OPD request failed: {type(exc).__name__}") from None
            except ValueError:
                raise SourceError("Invalid OPD JSON document") from None
        if not isinstance(value, dict):
            raise SourceError("Invalid OPD JSON response")
        return value

    def _authorize(self):
        if self._token and time.monotonic() < self._token_until:
            return
        data = self._json("POST", TOKEN, {
            "grant_type":"client_credentials", "client_id":self.client_id,
            "client_secret":self._secret}, token=False)
        token = data.get("access_token")
        if not isinstance(token, str) or not token:
            raise AccessChallenge("OAuth did not return an access token")
        self._token = token
        self._token_until = time.monotonic() + max(0, int(data.get("expires_in", 3600)) - 90)

    def verify_store(self, store):
        response = self._json("POST", LOCATOR, {
            "payload": {"postalCode": store.zipcode, "filter": ["INSTORE_PICKUP"]}})
        if response.get("status") != "OK":
            raise SourceError("OPD store locator did not report OK")
        accesspoints = response.get("payload", {}).get("accessPointList", [])
        if not isinstance(accesspoints, list):
            raise SourceError("Malformed OPD accessPointList")
        matches = [x for x in accesspoints if isinstance(x, dict) and
                   str(x.get("fulfillmentStoreId")) == store.store_id and
                   x.get("fulfillmentType") == "INSTORE_PICKUP"]
        if not matches:
            raise SourceError(f"Store #{store.store_id} not found as pickup store for ZIP {store.zipcode}")
        # PostalCode may include ZIP+4 and different delivery boundary; store ID+pickup
        # are authoritative for the store context; check address when present.
        address = matches[0].get("serviceAddress") or {}
        state = address.get("state") or address.get("stateOrProvinceName")
        if state and (f", {state} " not in store.store_location):
            raise SourceError("Store address state mismatch")
        return matches[0]

    def get_feeds(self, kind, category_id):
        if kind not in ("catalog", "price") or not category_id.isdigit():
            raise SourceError("Unsupported feed kind or invalid configured category ID")
        path = (CATALOG if kind == "catalog" else PRICE_SNAPSHOT) + "?categoryId=" + category_id
        result = self._json("GET", path)
        name = "product_snapshot_data" if kind == "catalog" else "price_avail_snapshot_data"
        feeds = result.get(name)
        if not isinstance(feeds, list) or not feeds or any(not isinstance(x, str) for x in feeds):
            raise SourceError(f"OPD {kind} category {category_id} has no usable signed feed URLs")
        for url in feeds:
            validate_signed_url(url)
        date = str(result.get("snapshot_date", ""))
        if not date or len(date) < 10:
            raise SourceError("Missing OPD snapshot date")
        try:
            date_day = datetime.strptime(date[:10], "%Y-%m-%d").date()
        except ValueError:
            raise SourceError("Invalid OPD snapshot date") from None
        if abs((datetime.now(timezone.utc).date() - date_day).days) > 4:
            raise SourceError(f"Stale or implausibly dated OPD snapshot: {date_day}")
        return date_day.isoformat(), feeds

    def realtime(self, offer_ids, store):
        if not 1 <= len(offer_ids) <= 20:
            raise SourceError("Realtime endpoint supports 1–20 offers per request")
        doc = self._json("POST", REALTIME, {"offerIds":offer_ids,
                    "storeIds":[int(store.store_id)], "zipCode":store.zipcode})
        if doc.get("status") != "OK":
            raise SourceError("Realtime API response not fully OK (partial results rejected)")
        results = doc.get("payload")
        if not isinstance(results, list):
            raise SourceError("Realtime response missing payload")
        for x in results:
            if str(x.get("storeId")) != store.store_id:
                raise SourceError("Realtime response mixed stores")
        return results


def validate_signed_url(url):
    u = urlparse(url)
    if u.scheme != "https" or u.hostname != "storage.googleapis.com" or not u.path.endswith((".gz", ".json")):
        raise SourceError("OPD returned an unexpected feed download domain or extension")


def _stream_json_values(raw_stream, max_object_bytes=16_000_000):
    """Read newline-delimited JSON OR a JSON array with bounded memory (stdlib)."""
    decoder = json.JSONDecoder()
    buffer, array = "", None
    stream = io.TextIOWrapper(raw_stream, encoding="utf-8-sig")
    ended = False
    while True:
        buffer = buffer.lstrip()
        if array is None and buffer:
            if buffer.startswith("["):
                array, buffer = True, buffer[1:]
            else:
                array = False
        buffer = buffer.lstrip()
        if array is True and buffer.startswith(","):
            buffer = buffer[1:].lstrip()
        if array is True and buffer.startswith("]"):
            buffer = buffer[1:].strip()
            if buffer or stream.read(1).strip():
                raise SourceError("Unexpected characters after JSON array")
            return
        if buffer:
            try:
                value, end = decoder.raw_decode(buffer)
            except json.JSONDecodeError:
                pass
            else:
                if not isinstance(value, dict):
                    raise SourceError("Catalog feed item is not a JSON object")
                yield value
                buffer = buffer[end:]
                continue
        if ended:
            if buffer:
                raise SourceError("Incomplete catalog JSON feed")
            if array is True:
                raise SourceError("Unclosed JSON catalog array")
            return
        chunk = stream.read(65536)
        if not chunk:
            ended = True
        else:
            buffer += chunk
            if len(buffer.encode("utf-8")) > max_object_bytes:
                raise SourceError("Catalog JSON object exceeds configured safety limit")


def signed_records(url, kind):
    """Stream GZIP JSON objects or caret-delimited pricing CSV using stdlib."""
    validate_signed_url(url)
    try:
        with urlopen(Request(url, headers={"Accept":"application/octet-stream"}), timeout=120) as resp:
            with gzip.GzipFile(fileobj=resp) as unpacked:
                if kind == "catalog":
                    yield from _stream_json_values(unpacked)
                else:
                    with io.TextIOWrapper(unpacked, encoding="utf-8-sig", newline="") as text_stream:
                        yield from csv.DictReader(text_stream, delimiter="^")
    except (HTTPError, URLError, OSError, ValueError, EOFError) as exc:
        raise SourceError(f"OPD {kind} compressed feed read failed ({type(exc).__name__})") from None


def _norm(text):
    return " ".join(str(text or "").lower().replace("&", "and").split())


def _category_match(product_path, aliases, exclusions):
    parts = [x.strip() for x in str(product_path or "").split("/") if x.strip()]
    segments = [_norm(x) for x in parts]
    if not any(_norm(alias) in segments for alias in aliases):
        return False
    if any(any(_norm(e) == x or x.startswith(_norm(e) + " ") for x in segments) for e in exclusions):
        return False
    return True


def _valid_offer(product):
    if product.get("marketplace") not in (False, None):
        return False  # Default OPD catalog feed excludes marketplace offers.
    if product.get("isOnlineOnly") is True:
        return False
    if product.get("sellerInfo"):
        return False
    return bool(product.get("offerId") and product.get("name") and product.get("itemId"))


def _to_raw(product, price, store):
    """Map one catalog offer plus its store price row into a raw record.

    RETENTION. A product the store carries but cannot currently sell stays in
    the output with its unsupported values empty. Availability is recorded, not
    used as a filter. Dropping those identities removed them from the dataset
    entirely, which is the opposite of the retention the brief requires.

    ELIGIBILITY. Store membership is established by the PRICE feed, which is
    store scoped, not by the catalog feed, which is per category. So a catalog
    offer with no price row for this store has not been shown to be carried
    here. Those are returned as unresolved rather than published with an
    invented store context. See `unresolved_offers`.
    """
    if not price:
        return None
    if str(price.get("storeCode")) != store.store_id:
        raise SourceError("Snapshot price store mismatch")
    available = price.get("availability", "").upper() == "AVAILABLE"
    price_str = str(price.get("currentPrice") or "").strip()
    # An unavailable offer has no current price to report, and a price carried
    # on an unavailable row is not one a shopper could pay today.
    if not available:
        price_str = ""
    url = str(product.get("productUrlText") or "")
    if url.startswith("/ip/"):
        url = "https://www.walmart.com" + url
    if not url.startswith("https://www.walmart.com/ip/"):
        return None
    # Snapshot currentPrice is not proof of a 'sale' vs regular promotion.
    # MSRP is NOT the ordinary retail price. Leave sale/deals blank unless a
    # separately authorized feed supplies the explicit displayed offer details.
    parts = [p.strip() for p in str(product.get("categoryPath") or "").split("/") if p.strip()]
    return {
        "store_id":store.store_id, "zipcode":store.zipcode,
        "store_context_verified":True, "seller_type":"walmart", "fulfillment":"pickup",
        "product_id":str(product["itemId"]), "product_title":product["name"],
        "weight":product.get("size") or "", "regular_price":price_str,
        "sale_price":"", "volume_deals_description":"", "volume_deals_price":"",
        "digital_deals_description":"", "digital_deals_price":"",
        "url":url, "image_url":product.get("productImage") or "",
        "upc":str(product.get("upc") or ""),
        # unitPriceDisplay belongs to a live offer. On an unavailable row it is
        # not a figure the shelf is showing, so it is left empty rather than
        # carried forward as if it were current.
        "ppm":(price.get("unitPriceDisplay") or "") if available else "",
        "brand":str(product.get("brandName") or ""),
        "sub_category":parts[-1] if parts else ""
    }


class WalmartOPDSnapshotSource:
    """Implements collector Page API from official signed snapshot archives.

    Cache is reusable for resume on local persistent disks. For Azure, mount an
    Azure Files volume or similar persistent directory. Incomplete file imports
    roll back transactionally and resume at complete-file boundaries.
    """
    source_mode = "authorized_provider_walmart_opd_snapshot_NEEDS_COVERAGE_AUDIT"
    # OPD snapshots are candidates, not proof that every website category,
    # promotion or individual pickup offer is represented.
    coverage_attested = False

    def __init__(self, client, root: Path, mappings: dict, page_size=100):
        self.client, self.root, self.mappings = client, Path(root), mappings
        self.page_size = page_size
        if not 1 <= page_size <= 1000:
            raise SourceError("Invalid OPD local page size")
        self.root.mkdir(parents=True, exist_ok=True)
        self._verified = set()
        # Catalog offers seen for a configured category that carry no price row
        # for the requested store. Their eligibility is genuinely unknown, so
        # they are neither published nor discarded.
        self.unresolved_offers = []

    def _db_path(self, store, category):
        return self.root / store.store_id / (category.slug + ".sqlite3")

    def _prepare(self, db, store, category):
        settings = self.mappings.get(category.name)
        if not isinstance(settings, dict):
            raise SourceError(f"Missing Walmart OPD category mapping: {category.name}")
        top_id = str(settings.get("feed_category_id", ""))
        aliases = settings.get("path_segments", [])
        if not top_id.isdigit() or not isinstance(aliases, list) or not aliases or any(not isinstance(v, str) for v in aliases):
            raise SourceError(f"OPD mapping unconfigured: {category.name}")
        if store.store_id not in self._verified:
            self.client.verify_store(store)
            self._verified.add(store.store_id)
        db.executescript("""
            CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS done (kind TEXT, path TEXT, snapshot TEXT,
                PRIMARY KEY(kind,path,snapshot));
            CREATE TABLE IF NOT EXISTS catalog (offer TEXT PRIMARY KEY, payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS price (offer TEXT PRIMARY KEY, payload TEXT NOT NULL);
        """)
        today = datetime.now(timezone.utc).date().isoformat()
        current = db.execute("SELECT value FROM meta WHERE key='built_on'").fetchone()
        if current and current[0] == today:
            return
        cat_date, cat_urls = self.client.get_feeds("catalog", top_id)
        p_date, p_urls = self.client.get_feeds("price", top_id)
        marker = f"{cat_date}/{p_date}/{top_id}/{','.join(aliases)}"
        existing = db.execute("SELECT value FROM meta WHERE key='signature'").fetchone()
        if existing is None or existing[0] != marker:
            with db:
                db.execute("DELETE FROM catalog")
                db.execute("DELETE FROM price")
                db.execute("DELETE FROM done")
                db.execute("DELETE FROM meta")
                db.execute("INSERT INTO meta VALUES('signature', ?)", (marker,))
        # Per-file transaction means a failed download is automatically rolled
        # back and retried on resume. Signed URL query strings are not persisted.
        for kind, snapshot, urls in (("catalog", cat_date, cat_urls), ("price", p_date, p_urls)):
            for url in urls:
                path = urlparse(url).path
                if db.execute("SELECT 1 FROM done WHERE kind=? AND path=? AND snapshot=?",
                              (kind,path,snapshot)).fetchone():
                    continue
                with db:
                    for item in signed_records(url, kind):
                        if kind == "catalog":
                            if not isinstance(item, dict) or not _valid_offer(item):
                                continue
                            if not _category_match(item.get("categoryPath"), aliases, category.exclusions):
                                continue
                            db.execute("INSERT OR REPLACE INTO catalog VALUES(?,?)", (
                                str(item["offerId"]), json.dumps(item, default=str)))
                        else:
                            if not isinstance(item, dict) or str(item.get("storeCode")) != store.store_id:
                                continue
                            # Store the price row whatever it says. Dropping
                            # non-AVAILABLE or unpriced rows here removed the
                            # identity from the dataset entirely, which defeats
                            # the retention requirement: a product the store
                            # carries but cannot currently sell must stay in the
                            # output with its unsupported values left empty, not
                            # disappear. Availability is recorded, not used as a
                            # filter.
                            offer = str(item.get("offerId") or "")
                            if offer:
                                db.execute("INSERT OR REPLACE INTO price VALUES(?,?)", (offer,json.dumps(item)))
                    db.execute("INSERT INTO done VALUES(?,?,?)", (kind,path,snapshot))
        # Catalog membership, not the price join, is what decides whether this
        # category yielded anything. A category whose products are all currently
        # unavailable is a real state of the store and must still be retained.
        count = db.execute("SELECT COUNT(*) FROM catalog").fetchone()[0]
        if count == 0:
            raise SourceError(f"OPD snapshot for {category.name} found zero eligible local offers")
        with db:
            db.execute("INSERT OR REPLACE INTO meta VALUES('built_on', ?)",(today,))

    def fetch(self, store, category, url, cursor):
        if url != category.url:
            raise SourceError("OPD snapshot source only supports configured category roots")
        path = self._db_path(store, category)
        path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(path, timeout=30)
        try:
            self._prepare(db,store,category)
            revision_row = db.execute("SELECT value FROM meta WHERE key='signature'").fetchone()
            revision = revision_row[0] if revision_row else ""
            # LEFT JOIN, not INNER. An inner join silently deleted every catalog
            # identity that had no matching price row, which is exactly the
            # unavailable and unpriced population the brief requires be kept.
            count = db.execute("SELECT COUNT(*) FROM catalog").fetchone()[0]
            offset = int(cursor) if cursor else 0
            if offset < 0 or offset >= count:
                raise SourceError("Invalid OPD pagination cursor")
            items = db.execute(
                "SELECT c.payload, p.payload FROM catalog c "
                "LEFT JOIN price p ON c.offer=p.offer ORDER BY c.offer LIMIT ? OFFSET ?",
                (self.page_size, offset)).fetchall()
        finally:
            db.close()
        products = []
        for p,q in items:
            catalog = json.loads(p)
            if not q:
                # No store price row, so this store's assortment has not been
                # shown to include it. Recorded as unresolved rather than
                # published with a store context we cannot evidence.
                self.unresolved_offers.append({
                    "offer_id": str(catalog.get("offerId") or ""),
                    "item_id": str(catalog.get("itemId") or ""),
                    "name": str(catalog.get("name") or ""),
                    "store_id": store.store_id,
                    "category": category.name,
                    "reason": "catalog offer has no price row for this store; "
                              "store assortment membership unestablished",
                })
                continue
            rec = _to_raw(catalog, json.loads(q), store)
            if rec:
                products.append(rec)
        next_cursor = str(offset + self.page_size) if offset + self.page_size < count else ""
        return Page(store_id=store.store_id, zipcode=store.zipcode,
            store_context_verified=True, source_url=url, products=products,
            children=[], next_cursor=next_cursor,
            subcategories_complete=True,
            location_evidence_url=f"https://www.walmart.com/store/{store.store_id}",
            source_revision=revision)
