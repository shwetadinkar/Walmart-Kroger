"""Normalize official Kroger API products into the 22-field record.

Ported from `marianos-live-api-west-loop`, the stricter of the two branches
that carry this file: `marianos-fresh-runs-category-evidence` also accepts
in-store-only offers and blank prices. Two deliberate differences from the
source:

  - An unmapped Kroger label leaves `category` empty. The source wrote the raw
    label into `category`, which is a value the client's CSV does not contain.
  - The label map is passed in from config/category_map.json, so there is one
    map. `api_trial.CATEGORY_MAP` was merged into it.

Keyword searches never exhaust a retailer category, so nothing here claims to.
"""
from __future__ import annotations

from decimal import Decimal
import math
import re
from urllib.parse import urlsplit

from .config import Store
from .schema import make_record

SITE = "https://www.marianos.com"


def verify_store(document, location_id, zipcode):
    if not isinstance(document, dict):
        raise ValueError("MALFORMED_STORE")
    address = document.get("address") or {}
    if (document.get("locationId") != location_id
            or document.get("chain") != "MARIANOS"
            or "mariano" not in str(document.get("name", "")).lower()
            or address.get("zipCode") != zipcode
            or not address.get("addressLine1")):
        raise ValueError("STORE_MISMATCH")
    return Store(location_id, zipcode, document["name"],
                 f"{address['addressLine1']}, {address.get('city', '')}, "
                 f"{address.get('state', '')} {zipcode}")


def money(value):
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not math.isfinite(value) or value < 0):
        raise ValueError("INVALID_PRICE")
    return format(Decimal(str(value)).quantize(Decimal(".01")), ".2f")


def api_categories(product):
    cats = product.get("categories")
    return [c for c in cats if isinstance(c, str)] if isinstance(cats, list) else []


def map_category(categories, category_map):
    """(client_root, kroger_label) from the product's own categories.

    Returns ("", label) when no label maps. An unmapped label is reported, not
    guessed into a root: a wrong category is worse than an absent one, because
    it survives review as though it were evidence.
    """
    for label in categories:
        root = category_map.get(label)
        if root:
            return root, label
    return "", (categories[0] if categories else "")


def _qualifying_offer(item):
    """A local pickup offer sold by the unit, at a price Kroger actually gave."""
    if not isinstance(item, dict):
        return False
    fulfillment = item.get("fulfillment")
    price = item.get("price")
    if (str(item.get("soldBy") or "").upper() != "UNIT"
            or not isinstance(fulfillment, dict)
            or fulfillment.get("curbside") is not True
            or not item.get("size")
            or not isinstance(price, dict)):
        return False
    regular = price.get("regular")
    return (isinstance(regular, (int, float)) and not isinstance(regular, bool)
            and math.isfinite(regular) and regular > 0)


def _front_image(product):
    for image in product.get("images") or []:
        if image.get("perspective") == "front" or image.get("default"):
            sizes = image.get("sizes") or []
            url = next((s["url"] for size in ("xlarge", "large", "medium", "small")
                        for s in sizes if s.get("size") == size and s.get("url")), "")
            if url:
                return url
    return ""


def normalize(product, store, crawl_date, category_map):
    """One validated record, or ValueError naming why the product was refused."""
    if not isinstance(product, dict):
        raise ValueError("MALFORMED_PRODUCT")
    upc = product.get("upc")
    if not isinstance(upc, str) or not re.fullmatch(r"\d{8,14}", upc):
        raise ValueError("INVALID_UPC")
    uri = product.get("productPageURI") or ""
    parsed = urlsplit(uri)
    if (parsed.scheme or parsed.netloc or parsed.fragment
            or not parsed.path.startswith("/p/")
            or parsed.path.split("/")[-1] != str(product.get("productId", ""))):
        raise ValueError("INVALID_PRODUCT_URI")
    item = next((x for x in product.get("items") or [] if _qualifying_offer(x)), None)
    if not item:
        raise ValueError("NO_QUALIFYING_LOCAL_PICKUP_OFFER")
    category, label = map_category(api_categories(product), category_map)
    price = item["price"]
    promo = price.get("promo")
    raw = {"store_id": store.store_id, "zipcode": store.zipcode,
           "seller_type": "marianos", "fulfillment": "pickup",
           "store_context_verified": True, "brand": product.get("brand", ""),
           "product_title": product.get("description", ""),
           "weight": item["size"], "regular_price": money(price["regular"]),
           "sale_price": money(promo) if isinstance(promo, (int, float)) and promo > 0 else "",
           "image_url": _front_image(product), "url": SITE + uri, "upc": upc}
    return make_record(raw, store, category, label, crawl_date)
