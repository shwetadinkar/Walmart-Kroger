#!/usr/bin/env python3
"""Offline structural verification of the submitted Walmart Store #100 trial JSON.

Requires only Python 3.11+. No network, secrets, paid API requests or Azure needed.
Passing this checker does NOT prove that store-local prices, promotions,
full subcategory traversal or Azure execution were observed.
"""
import collections
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit

EXPECTED = (
    "zipcode", "store_name", "store_location", "store_logo", "store_brand",
    "category", "sub_category", "product_title", "weight", "regular_price",
    "sale_price", "volume_deals_description", "volume_deals_price",
    "digital_deals_description", "digital_deals_price", "image_url", "url",
    "upc", "gupc", "ppm", "unit_price", "crawl_date",
)
CATEGORIES = {
    "Food", "Household Essentials", "Personal Care", "Beauty", "Diapering",
    "Feeding", "Health & Wellness", "Pets", "Balloons", "Art Supplies",
    "Office Supplies",
}
FILE = Path(__file__).with_name("Walmart_Store100_615_Trial_22Field.json")


def validate(path=FILE):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    errors = []
    if not isinstance(data, list):
        raise ValueError("Expected a JSON array")
    seen = set()
    counts = collections.Counter()
    price_fields = ("regular_price", "sale_price", "ppm", "unit_price")
    blank = collections.Counter()
    for i, item in enumerate(data, 1):
        if not isinstance(item, dict):
            errors.append(f"row {i}: expected object")
            continue
        if tuple(item) != EXPECTED:
            errors.append(f"row {i}: 22-field schema/order mismatch")
        if any(not isinstance(v, str) for v in item.values()):
            errors.append(f"row {i}: all 22 values must be strings")
        if item.get("zipcode") != "72712" or item.get("store_name") != "Walmart Supercenter #100":
            errors.append(f"row {i}: wrong store or ZIP")
        cat = item.get("category")
        if cat not in CATEGORIES:
            errors.append(f"row {i}: unapproved category {cat!r}")
        counts[cat] += 1
        url = item.get("url", "")
        parsed = urlsplit(url)
        if parsed.netloc not in ("walmart.com", "www.walmart.com") or not re.search(r"/ip/.+/\d+$", parsed.path):
            errors.append(f"row {i}: invalid Walmart item URL")
        if url in seen:
            errors.append(f"row {i}: repeated product URL")
        seen.add(url)
        for field in price_fields:
            if not item.get(field):
                blank[field] += 1
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", item.get("crawl_date", "")):
            errors.append(f"row {i}: missing/invalid observation date")
    if len(data) < 500:
        errors.append(f"only {len(data)} products; minimum 500")
    for category in sorted(CATEGORIES - set(counts)):
        errors.append("missing category: " + category)
    if errors:
        for error in errors[:30]:
            print("FAIL:", error, file=sys.stderr)
        print(f"{len(errors)} failures", file=sys.stderr)
        return 1
    print(f"PASS: {len(data)} distinct 22-field Walmart Store #100 candidates across {len(counts)} categories")
    print("Categories:", json.dumps(dict(sorted(counts.items())), sort_keys=True))
    print("Blank fields:", json.dumps(dict(blank), sort_keys=True))
    print("IMPORTANT: structural validation only; not store-price, PPM, promotions, traversal, or Azure certification")
    return 0


if __name__ == "__main__":
    raise SystemExit(validate(sys.argv[1] if len(sys.argv) > 1 else FILE))
