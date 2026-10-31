"""Retailer observations to exact 22-field, ordered, string-only output."""
from __future__ import annotations

import re
from collections import OrderedDict
from datetime import datetime, timezone
from urllib.parse import urlparse

FIELDS = (
    "zipcode", "store_name", "store_location", "store_logo", "store_brand", "category",
    "sub_category", "product_title", "weight", "regular_price", "sale_price",
    "volume_deals_description", "volume_deals_price", "digital_deals_description",
    "digital_deals_price", "image_url", "url", "upc", "gupc", "ppm", "unit_price", "crawl_date"
)
PRICE_FIELDS = ("regular_price", "sale_price", "volume_deals_price", "digital_deals_price")
_PRIVATE_BRANDS = {"great value", "equate", "mainstays", "onn.", "onn", "parent's choice", "bettergoods", "marketside", "sam's choice", "hyper tough", "athletic works"}
# Wording that means the printed figure is not what the customer receives.
#
# Two patterns, because the two fields are not equally ambiguous. In the WEIGHT
# field a bare "about 2" can only be about weight. In a TITLE it usually is not:
# "Guacamole, 8 oz, about 4 servings" is a fixed-weight, fixed-price product and
# must not be excluded. So the title pattern requires an actual weight unit
# after "about", and the weight pattern additionally accepts a bare number.
#
# The trailing \d also has to be \d+: "about 12 oz" and "about 100 lb" would
# not match a single-digit pattern, so the loose form missed most real
# approximate weights while firing on small counts.
#
# "Approximately" alone says nothing about weight. "Rice 16 oz, approximately 8
# servings" is a fixed-size product, so approximate wording only counts when it
# is attached to a weight: "approx. 2 lb", "approximate weight", "2 lb approx".
_APPROX_WORD = r"(?:approximately|approximate|approx)\b\.?"
_NUMBER = (
    r"(?:\d+\s+\d+/\d+|\d+/\d+|\d*\.?\d+)"
    r"(?:\s*(?:-|to)\s*(?:\d+/\d+|\d*\.?\d+))?"
)
_WEIGHT_UNIT = r"(?:lbs?\b\.?|pounds?\b|ozs?\b\.?|ounces?\b|kgs?\b|kilograms?\b|gs?\b|grams?\b)"
_APPROX_ATTACHED = (
    rf"{_APPROX_WORD}\s*:?\s*~?\s*{_NUMBER}\s*{_WEIGHT_UNIT}"
    rf"|{_APPROX_WORD}\s+(?:net\s+)?(?:weight|wt\b)"
    rf"|(?:weight|wt\b\.?)\s*(?:is\s*)?:?\s*{_APPROX_WORD}"
    rf"|\b{_NUMBER}\s*{_WEIGHT_UNIT}[\s,(]*{_APPROX_WORD}(?![.\s]*\d)"
)
_APPROX_COMMON = (
    rf"{_APPROX_ATTACHED}"
    r"|(?:(?:variable|average|avg\.?|estimated|random)[-\s]?weight"
    r"|weights?\s+(?:may\s+)?var(?:y|ies)"
    r"|(?:sold|priced)\s+by\s+weight)\b"
)
_ABOUT_UNIT = rf"about\s+\d+(?:\.\d+)?\s*{_WEIGHT_UNIT}"
# Titles: approximate wording, or "about N <weight unit>".
_APPROX = re.compile(rf"\b(?:{_APPROX_COMMON}|{_ABOUT_UNIT})", re.I)
# Weight field: the same, plus a bare "about N" or "approx" with no count noun
# after it, which is unambiguous there. "about 4 servings" is still a count.
_APPROX_WEIGHT = re.compile(
    rf"\b(?:{_APPROX_COMMON}|{_ABOUT_UNIT}"
    rf"|(?:{_APPROX_WORD}|about)\s*~?\s*{_NUMBER}(?![\d./]|\s*[a-z])"
    rf"|{_APPROX_WORD}(?![.\s~]*\d))",
    re.I)
_PRICE = re.compile(r"^\$?\d+(?:\.\d{1,2})?$")

class RecordRejected(ValueError):
    pass

def make_record(raw: dict, store, category: str, sub_category: str, crawl_date: str) -> dict:
    if not isinstance(raw, dict):
        raise RecordRejected("Product is not a JSON object")
    if raw.get("store_id") != store.store_id or raw.get("zipcode") != store.zipcode:
        raise RecordRejected("STORE_MISMATCH")
    if raw.get("seller_type") != "walmart":
        raise RecordRejected("INELIGIBLE_SELLER")
    if raw.get("fulfillment") not in ("pickup", "in_store"):
        raise RecordRejected("INELIGIBLE_FULFILLMENT")
    if raw.get("store_context_verified") is not True:
        raise RecordRejected("UNVERIFIED_PRODUCT_LOCATION")
    weight = str(raw.get("weight") or "")
    if _APPROX_WEIGHT.search(weight):
        raise RecordRejected("APPROXIMATE_WEIGHT")
    title = str(raw.get("product_title") or "").strip()
    url = str(raw.get("url") or "").strip()
    if not title:
        raise RecordRejected("MISSING_TITLE")
    # The weight field is not the only place this wording appears. A product
    # titled "Chicken Breast, Average Weight 1 lb" with size "1 lb" passed every
    # check, because only the weight field was ever searched. The title carries
    # the retailer's own description of what is being sold, so it is searched
    # too. Fixed-weight family packs and multipacks are untouched: nothing here
    # matches "Family Pack", a count, or a plain weight.
    if _APPROX.search(title):
        raise RecordRejected("APPROXIMATE_WEIGHT_IN_TITLE")
    p = urlparse(url)
    if p.scheme != "https" or not p.hostname or not (p.hostname == "walmart.com" or p.hostname.endswith(".walmart.com")):
        raise RecordRejected("INVALID_PRODUCT_URL")

    result = OrderedDict((f, "") for f in FIELDS)
    for f in FIELDS:
        if f in raw and f not in {"zipcode", "store_name", "store_location", "store_logo", "category", "sub_category", "gupc", "unit_price", "crawl_date"}:
            value = raw[f]
            if value is None:
                value = ""
            if not isinstance(value, (str, int, float)):
                raise RecordRejected(f"UNEXPECTED_FIELD_TYPE:{f}")
            result[f] = str(value)
    result["zipcode"] = store.zipcode
    result["store_name"] = store.store_name
    result["store_location"] = store.store_location
    result["store_logo"] = store.store_logo
    result["category"] = category
    result["sub_category"] = sub_category
    result["product_title"] = title
    result["weight"] = weight
    result["url"] = url
    result["crawl_date"] = crawl_date
    result["gupc"] = ""
    result["unit_price"] = ""
    brand = str(raw.get("brand") or "").strip().lower()
    result["store_brand"] = "yes" if brand in _PRIVATE_BRANDS else "no"

    for field in PRICE_FIELDS:
        value = result[field].strip()
        if value and not _PRICE.fullmatch(value):
            raise RecordRejected(f"INVALID_PRICE:{field}")
        result[field] = value.lstrip("$") if value else ""
    dig_desc = result["digital_deals_description"].strip()
    dig_price = result["digital_deals_price"].strip()
    if dig_price and not dig_desc:
        raise RecordRejected("DIGITAL_PRICE_WITHOUT_DESCRIPTION")
    if dig_desc and not re.search(r"\b(?:clip|clipp(?:ed|ing)|activat(?:e|ion)|add (?:to |the )?(?:account|offer)|save (?:the |this )?(?:offer|coupon)|digital coupon)\b", dig_desc, re.I):
        raise RecordRejected("UNVERIFIED_DIGITAL_DEAL")
    if re.search(r"\b(?:walmart cash|cashback|cash back)\b", dig_desc, re.I):
        raise RecordRejected("CASHBACK_MISCLASSIFIED_AS_DIGITAL")
    if result["volume_deals_price"] and not result["volume_deals_description"]:
        raise RecordRejected("VOLUME_PRICE_WITHOUT_DESCRIPTION")
    return result


def fingerprint(record: dict, raw: dict) -> str:
    # Stable within one store; avoid making the same product duplicate across subcategories.
    identity = str(raw.get("product_id") or "").strip()
    if not identity:
        identity = record["upc"] or record["url"].split("?", 1)[0]
    return record["zipcode"] + ":" + identity


def utc_day() -> str:
    return datetime.now(timezone.utc).date().isoformat()
