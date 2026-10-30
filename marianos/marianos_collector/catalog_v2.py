"""Kroger Catalog V2 partner API: client and collector source adapter.

WHY THIS EXISTS
---------------
The Kroger *public* Products API (see kroger.py) carries the fields this brief
needs, but Kroger's "Acceptable Use of Public APIs" prohibits systematically
gathering response data to create a database, and prohibits comparing prices
among other retailers. This collector does both by design, so the public tier
is closed to it regardless of which fields it exposes. Catalog V2 is the
partner tier; a partner agreement is the instrument that grants those rights.

That is why the public client stays diagnostic-only and this module is the
production route.

WHAT IS VERIFIED AND WHAT IS NOT
--------------------------------
Every endpoint path, query parameter and response field named below was read
from Kroger's own published OpenAPI document for Catalog V2, version 1.5.5.
Nothing here is inferred from a blog post or a client library.

What has NOT been verified, because it requires credentials this project does
not hold:

  * the accepted values of `filter.locations.fulfillment.eq` (the contract
    marks it required but publishes no enum), hence CATALOG_V2_FULFILLMENT
  * the OAuth scope string a partner agreement issues, hence CATALOG_V2_SCOPE
  * whether `price.unit` is the retailer-displayed price per measure or the
    price for the unit of sale. The contract says only `string, eg "USD 5.00"`.
    See `_ppm_candidate` — it is NOT written to the ppm field by default.

Anything in that list is configurable rather than guessed silently, and the
run manifest records which value was used.

SHAPE MISMATCH, AND HOW IT IS HANDLED
-------------------------------------
The rest of this collector is built around a category crawl: fetch a category
URL, read its products and child categories, follow a cursor. Catalog V2 is not
a crawl. It has no category filter at all. Its three endpoints are driven by
store location, optionally narrowed by UPC list or an updatedAt range, and
paged with page.offset / page.size.

So this adapter sweeps the whole location once, groups the products by the
category each product reports about itself, and then serves the existing
per-category Page interface out of that result. The runner, normalizer, schema,
storage and retention logic are untouched.

A sweep is a stronger coverage claim than a crawl, not a weaker one: a crawl can
only reach categories it discovers by following links, whereas a paged sweep of
a location is exhaustive by construction when the API reports hasMore=false.
"""
from __future__ import annotations

import base64
import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

from .sources import AccessChallenge, Page, SourceError

LOG = logging.getLogger("collector")

ROOT = "https://api.kroger.com"
PRODUCTS = "/catalog/v2/products"
PRODUCTS_INVENTORY = "/catalog/v2/products-inventory"
DELETED_ITEMS = "/catalog/v2/deleted-items"

# Contract: page.size allowed range is [1 - 50].
MAX_PAGE_SIZE = 50
# Contract: locations[] has maxItems 20. A single-store sweep asks for one.
MAX_LOCATIONS = 20

_MONEY = re.compile(r"^(?:[A-Z]{3}\s*)?\$?(\d+(?:\.\d{1,2})?)$")


class CatalogV2Error(RuntimeError):
    pass


def _money(value) -> str:
    """Normalize a contract money string to a bare amount, or "" if it is not one.

    The contract uses two different money spellings in the same response:
    `defaultDescription` is already a display string such as "$4.99", while
    `nFor.price` and `unit` are ISO-prefixed such as "USD 18.00". The 22-field
    schema wants a bare amount and rejects anything else, so both spellings are
    reduced here rather than in four separate call sites.

    Anything that is not recognisably a single amount returns "" instead of a
    guess. A price we cannot read is a missing price, never an invented one.
    """
    if value is None:
        return ""
    text = str(value).strip()
    if not text:
        return ""
    match = _MONEY.fullmatch(text)
    return match.group(1) if match else ""


@dataclass
class Credentials:
    client_id: str
    client_secret: str

    @classmethod
    def from_environment(cls) -> "Credentials":
        instance = cls(
            os.getenv("KROGER_CLIENT_ID", ""),
            os.getenv("KROGER_CLIENT_SECRET", ""),
        )
        if not instance.client_id or not instance.client_secret:
            raise CatalogV2Error(
                "KROGER_CLIENT_ID and KROGER_CLIENT_SECRET are required. "
                "Partner credentials stay with their owner and are never sent to a third party."
            )
        return instance


class CatalogV2Client:
    """Thin OAuth + GET client restricted to the three documented Catalog V2 paths."""

    def __init__(self, creds: Credentials, opener=None, pause: float = 0.2, scope: str = ""):
        self.creds = creds
        self.opener = opener or urlopen
        self.pause = pause
        # Published docs do not state the partner scope string; a partner
        # agreement does. Overridable so an agreement's actual scope can be
        # supplied without editing code.
        self.scope = scope or os.getenv("CATALOG_V2_SCOPE", "product.compact")
        self._token = ""
        self._expires = 0.0

    def _read(self, request):
        for attempt in range(3):
            try:
                if self.pause:
                    time.sleep(self.pause)
                with self.opener(request, timeout=30) as response:
                    if getattr(response, "status", 200) != 200:
                        raise CatalogV2Error("Unexpected Catalog V2 response status")
                    payload = response.read(16_000_001)
                    if len(payload) > 16_000_000:
                        raise CatalogV2Error("Catalog V2 response exceeds 16MB")
                parsed = json.loads(payload)
                if not isinstance(parsed, dict):
                    raise CatalogV2Error("Catalog V2 returned a non-object document")
                return parsed
            except HTTPError as exc:
                if exc.code in (401, 403):
                    # 403 here usually means the credential is real but the
                    # partner agreement does not carry Catalog V2. That is an
                    # entitlement answer, not a transient fault, so it is
                    # raised as a challenge and never retried.
                    raise AccessChallenge(
                        f"Catalog V2 HTTP {exc.code}: credential rejected or partner "
                        f"entitlement does not cover this scope"
                    ) from exc
                if exc.code not in (429, 500, 502, 503, 504) or attempt == 2:
                    raise CatalogV2Error(f"Catalog V2 HTTP {exc.code}") from exc
            except (TimeoutError, URLError, OSError) as exc:
                if attempt == 2:
                    raise CatalogV2Error(f"Catalog V2 unavailable: {exc}") from exc
            except (ValueError, TypeError) as exc:
                raise CatalogV2Error(f"Invalid Catalog V2 JSON: {exc}") from exc
            time.sleep(2 ** attempt)
        raise CatalogV2Error("Catalog V2 retries exhausted")

    def token(self) -> str:
        if self._token and time.monotonic() < self._expires - 90:
            return self._token
        basic = base64.b64encode(
            f"{self.creds.client_id}:{self.creds.client_secret}".encode()
        ).decode()
        body = urlencode({"grant_type": "client_credentials", "scope": self.scope}).encode()
        request = Request(
            ROOT + "/v1/connect/oauth2/token",
            data=body,
            headers={
                "Authorization": f"Basic {basic}",
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
            },
            method="POST",
        )
        result = self._read(request)
        token = result.get("access_token")
        if not isinstance(token, str) or not token:
            raise CatalogV2Error("Catalog V2 token response carried no access_token")
        self._token = token
        self._expires = time.monotonic() + int(result.get("expires_in", 1800))
        return token

    def get(self, path: str, params: dict) -> dict:
        if path not in (PRODUCTS, PRODUCTS_INVENTORY, DELETED_ITEMS):
            raise CatalogV2Error("Only the three documented Catalog V2 paths are permitted")
        url = ROOT + path + "?" + urlencode(params)
        request = Request(
            url,
            headers={"Authorization": f"Bearer {self.token()}", "Accept": "application/json"},
        )
        try:
            return self._read(request)
        except AccessChallenge:
            raise
        except CatalogV2Error as exc:
            if "401" in str(exc):
                self._token = ""
                request = Request(
                    url,
                    headers={
                        "Authorization": f"Bearer {self.token()}",
                        "Accept": "application/json",
                    },
                )
                return self._read(request)
            raise


def _first_location(product: dict, location_id: str) -> dict:
    """Return the requested store's location block, or {} if this product has none.

    A sweep filtered to one store should only return that store, but the
    contract permits up to 20 location blocks per product. Selecting by id
    rather than taking locations[0] is what keeps a multi-location response
    from silently attributing another store's price to this one. That exact
    failure (a Mariano's request answered with a Kroger-banner record) has
    already been observed once on a different provider in this project.
    """
    locations = product.get("locations")
    if not isinstance(locations, list):
        return {}
    for entry in locations:
        if isinstance(entry, dict) and str(entry.get("id") or "") == location_id:
            return entry
    return {}


def _price_blocks(location: dict) -> dict:
    """Pull the first regular/promo price pair out of a location's inventory."""
    inventory = location.get("inventory")
    if not isinstance(inventory, list):
        return {}
    for entry in inventory:
        if not isinstance(entry, dict):
            continue
        prices = entry.get("prices")
        if not isinstance(prices, list):
            continue
        for price_set in prices:
            if isinstance(price_set, dict) and (
                isinstance(price_set.get("regular"), dict)
                or isinstance(price_set.get("promo"), dict)
            ):
                return {
                    "regular": price_set.get("regular") or {},
                    "promo": price_set.get("promo") or {},
                    "discount_label": str(price_set.get("discountLabel") or ""),
                    "instock": bool(entry.get("instock")),
                    "stock": entry.get("stock") if isinstance(entry.get("stock"), dict) else {},
                }
    return {}


def _ppm_candidate(price: dict) -> str:
    """The `unit` field, which MAY be the displayed price per measure.

    Deliberately not written to the ppm output field. The Catalog V2 contract
    documents this only as `string, example "USD 5.00"` and does not say
    whether it is a per-measure rate or the price for the unit of sale. Telling
    the client PPM is closed on the strength of a field name and a plausible
    example is exactly the kind of claim this project has had to retract once
    already.

    It is carried through to the audit record so that the first live response
    settles the question from real data, and promoted to ppm only when the
    operator sets CATALOG_V2_UNIT_IS_PPM=yes having checked it.
    """
    return str(price.get("unit") or "")


def _volume_deal(promo: dict) -> tuple[str, str, str]:
    """Return (description, price, wording_source) for an nFor volume offer.

    The brief requires retailer wording to be preserved rather than rebuilt.
    Catalog V2 supplies the volume offer as structured data — nFor.quantity and
    nFor.price — not as the shelf sentence. A string such as "4 for $18.00"
    is therefore COMPOSED here, and the third return value says so, so that the
    run manifest can record it and nobody downstream mistakes it for verbatim
    retailer text.

    If a future agreement exposes the offer wording itself, map it here and
    return "verbatim".
    """
    n_for = promo.get("nFor")
    if not isinstance(n_for, dict):
        return "", "", ""
    quantity = str(n_for.get("quantity") or "").strip()
    amount = _money(n_for.get("price"))
    if not quantity or not amount:
        return "", "", ""
    return f"{quantity} for ${amount}", amount, "composed_from_nFor"


def _category_path(product: dict) -> tuple[str, str]:
    """Best-effort (category, sub_category) from the product's own classification.

    Catalog V2 returns `categories` as an array whose items the contract
    describes only as having a `parent` object, so the concrete shape is
    settled by the first live response. Both the string form and the
    {name,parent} form are handled; anything else yields empty strings rather
    than a guess, and the record is still emitted so the row is not lost over a
    descriptive field.
    """
    categories = product.get("categories")
    if not isinstance(categories, list) or not categories:
        return "", ""
    first = categories[0]
    if isinstance(first, str):
        return first, ""
    if not isinstance(first, dict):
        return "", ""
    name = str(first.get("name") or "")
    parent = first.get("parent")
    if isinstance(parent, dict):
        parent_name = str(parent.get("name") or "")
        if parent_name:
            return parent_name, name
    if isinstance(parent, str) and parent:
        return parent, name
    return name, ""


def _image_url(product: dict) -> str:
    images = product.get("images")
    if isinstance(images, str):
        return images
    if not isinstance(images, list):
        return ""
    for image in images:
        if isinstance(image, str) and image:
            return image
        if isinstance(image, dict):
            direct = image.get("url")
            if isinstance(direct, str) and direct:
                return direct
            sizes = image.get("sizes")
            if isinstance(sizes, list):
                for size in sizes:
                    if isinstance(size, dict) and isinstance(size.get("url"), str):
                        return size["url"]
    return ""


@dataclass
class SweepResult:
    by_category: dict
    product_count: int
    pages_fetched: int
    complete: bool
    audit: list = field(default_factory=list)


class CatalogV2Source:
    """Collector source backed by a one-shot paged sweep of a single store location.

    Implements the same fetch(store, category, url, cursor) -> Page contract as
    FixtureSource and AuthorizedProviderSource, so the runner does not change.
    """

    source_mode = "kroger_catalog_v2_partner_api"

    def __init__(
        self,
        client: CatalogV2Client,
        location_id: str,
        fulfillment: str = "",
        page_size: int = MAX_PAGE_SIZE,
        max_pages: int = 2000,
        include_missing_prices: bool = True,
        banner_host: str = "www.marianos.com",
    ):
        if not location_id or location_id.upper().startswith(("DEMO", "REPLACE", "UNRESOLVED")):
            raise CatalogV2Error(
                "Catalog V2 needs a real Kroger locationId confirmed from the Locations API, "
                "not a demo placeholder"
            )
        if not 1 <= page_size <= MAX_PAGE_SIZE:
            raise CatalogV2Error(f"page.size must be within 1..{MAX_PAGE_SIZE}")
        self.client = client
        self.location_id = location_id
        # Required by the contract, with no published enum. Set from the
        # partner agreement; recorded in the manifest either way.
        self.fulfillment = fulfillment or os.getenv("CATALOG_V2_FULFILLMENT", "curbside")
        self.page_size = page_size
        self.max_pages = max_pages
        self.include_missing_prices = include_missing_prices
        self.banner_host = banner_host
        self.unit_is_ppm = os.getenv("CATALOG_V2_UNIT_IS_PPM", "").lower() == "yes"
        self._sweep: SweepResult | None = None

    # ------------------------------------------------------------------ sweep

    def sweep(self, store) -> SweepResult:
        if self._sweep is not None:
            return self._sweep

        by_category: dict = {}
        audit: list = []
        offset = 0
        pages = 0
        complete = False

        while pages < self.max_pages:
            params = {
                "filter.locations.id.eq": self.location_id,
                "filter.locations.fulfillment.eq": self.fulfillment,
                "page.offset": offset,
                "page.size": self.page_size,
            }
            if store.zipcode:
                params["filter.postalCode.eq"] = store.zipcode
            if self.include_missing_prices:
                # Retention requirement: a product carried by the store but
                # currently without a price must stay in the dataset rather
                # than being silently dropped.
                params["option.missingPrices"] = "true"

            document = self.client.get(PRODUCTS, params)
            pages += 1

            data = document.get("data")
            if not isinstance(data, list):
                raise CatalogV2Error("Catalog V2 products response carried no data array")

            for product in data:
                if not isinstance(product, dict):
                    continue
                record, record_audit = self._to_raw_product(product, store)
                if record is None:
                    continue
                category, sub_category = _category_path(product)
                by_category.setdefault(category, {}).setdefault(sub_category, []).append(record)
                audit.append(record_audit)

            meta = document.get("meta")
            page_meta = meta.get("page") if isinstance(meta, dict) else None
            has_more = bool(page_meta.get("hasMore")) if isinstance(page_meta, dict) else False
            if not has_more:
                complete = True
                break
            if not data:
                # hasMore true with an empty page would loop for ever.
                complete = False
                break
            offset += self.page_size

        LOG.info(
            "catalog_v2_sweep_complete",
            extra={
                "event": "catalog_v2_sweep_complete",
                "store_id": store.store_id,
                "category": "",
            },
        )
        self._sweep = SweepResult(
            by_category=by_category,
            product_count=sum(
                len(items)
                for subs in by_category.values()
                for items in subs.values()
            ),
            pages_fetched=pages,
            complete=complete,
            audit=audit,
        )
        return self._sweep

    # ------------------------------------------------------------- normalizing

    def _to_raw_product(self, product: dict, store) -> tuple[dict | None, dict]:
        """Map one Catalog V2 product to the raw dict the schema layer expects."""
        location = _first_location(product, self.location_id)
        if not location:
            # The product exists in the catalogue but not at this store. The
            # schema layer would reject it as STORE_MISMATCH anyway; dropping
            # it here keeps the rejection ledger meaningful.
            return None, {"upc": str(product.get("upc") or ""), "skipped": "not_at_location"}

        prices = _price_blocks(location)
        regular = prices.get("regular") or {}
        promo = prices.get("promo") or {}

        volume_description, volume_price, wording_source = _volume_deal(promo)
        ppm_candidate = _ppm_candidate(regular) or _ppm_candidate(promo)

        url = str(product.get("productPageURL") or "").strip()
        if url:
            parsed = urlparse(url)
            # The schema layer requires a marianos.com product URL. A Kroger
            # banner URL arriving for a Mariano's location is the cross-banner
            # leak described in _first_location, so it is recorded and dropped
            # rather than rewritten into something that would pass validation.
            if parsed.hostname and not (
                parsed.hostname == "marianos.com" or parsed.hostname.endswith(".marianos.com")
            ):
                return None, {
                    "upc": str(product.get("upc") or ""),
                    "skipped": "foreign_banner_url",
                    "url_host": parsed.hostname,
                }

        metadata = product.get("metadata") if isinstance(product.get("metadata"), dict) else {}
        brand = product.get("brand") if isinstance(product.get("brand"), dict) else {}

        raw = {
            "store_id": store.store_id,
            "zipcode": store.zipcode,
            "store_context_verified": True,
            "seller_type": "marianos",
            "fulfillment": "pickup",
            "product_id": str(product.get("upc") or ""),
            "product_title": str(product.get("name") or ""),
            "weight": str(metadata.get("size") or ""),
            "regular_price": _money(regular.get("defaultDescription")),
            "sale_price": _money(promo.get("defaultDescription") or promo.get("promoDescription")),
            "volume_deals_description": volume_description,
            "volume_deals_price": volume_price,
            # No Kroger API on the published list, public or partner, exposes
            # clipping state, household limits or digital offer terms. Blank is
            # the accurate value, not a placeholder.
            "digital_deals_description": "",
            "digital_deals_price": "",
            "upc": str(product.get("upc") or ""),
            "brand": str(brand.get("name") or ""),
            "url": url,
            "image_url": _image_url(product),
            "ppm": ppm_candidate if self.unit_is_ppm else "",
        }

        audit = {
            "upc": raw["upc"],
            "ppm_candidate_unit_field": ppm_candidate,
            "ppm_written": bool(self.unit_is_ppm and ppm_candidate),
            "volume_wording_source": wording_source,
            "discount_label": prices.get("discount_label", ""),
            "instock": prices.get("instock", False),
            "offer_description": str(regular.get("description") or promo.get("description") or ""),
            "effective_date": str(regular.get("effectiveDate") or ""),
            "expired_date": str(regular.get("expiredDate") or ""),
            "sold_by": str(regular.get("soldBy") or promo.get("soldBy") or ""),
            "average_weight_per_unit": str(metadata.get("averageWeightPerUnit") or ""),
        }
        return raw, audit

    # -------------------------------------------------------------- page serve

    def fetch(self, store, category, url: str, cursor: str) -> Page:
        sweep = self.sweep(store)
        bucket = sweep.by_category.get(category.name, {})
        products = [item for items in bucket.values() for item in items]

        start = int(cursor) if cursor.isdecimal() else 0
        window = products[start : start + self.page_size]
        next_cursor = (
            str(start + self.page_size) if start + self.page_size < len(products) else ""
        )

        return Page(
            store_id=store.store_id,
            zipcode=store.zipcode,
            store_context_verified=True,
            source_url=url,
            products=window,
            children=[],
            next_cursor=next_cursor,
            # A paged location sweep is exhaustive by construction once the API
            # reports hasMore=false. If the sweep stopped early this is False
            # and the runner's completeness gate will refuse to publish.
            subcategories_complete=sweep.complete,
            location_evidence_url="",
        )

    # ------------------------------------------------------------- retention

    def deleted_since(self, window: str) -> list:
        """Items removed from this location's assortment in the given range.

        Supports accumulated retention: a product that disappears is marked
        rather than re-dated or dropped, so the delivered dataset keeps the
        store-assortment history the brief asks for.
        """
        document = self.client.get(
            DELETED_ITEMS,
            {
                "filter.locations.id.eq": self.location_id,
                "filter.locations.fulfillment.eq": self.fulfillment,
                "filter.deletedAt.range": window,
            },
        )
        data = document.get("data")
        return data if isinstance(data, list) else []

    def provenance(self) -> dict:
        """Everything a reviewer needs to judge what this run actually used."""
        return {
            "source_mode": self.source_mode,
            "contract": "Kroger Catalog V2 OpenAPI 1.5.5",
            "endpoints": [PRODUCTS, PRODUCTS_INVENTORY, DELETED_ITEMS],
            "location_id": self.location_id,
            "fulfillment_filter": self.fulfillment,
            "fulfillment_filter_verified": False,
            "scope": self.client.scope,
            "scope_verified": False,
            "page_size": self.page_size,
            "option_missing_prices": self.include_missing_prices,
            "unit_field_treated_as_ppm": self.unit_is_ppm,
            "volume_wording": "composed_from_nFor_not_verbatim_retailer_text",
            "digital_deals": "not_exposed_by_any_published_kroger_api",
            "sweep_complete": self._sweep.complete if self._sweep else None,
            "products_swept": self._sweep.product_count if self._sweep else None,
            "pages_fetched": self._sweep.pages_fetched if self._sweep else None,
        }
