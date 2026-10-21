"""Independent fail-closed evidence check for the Walmart contest.

Does NOT pretend to verify external URLs or user assertions. The buyer must review
real snapshots, prices, authorized access, and an observed Azure execution.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

FIELDS = (
    "zipcode", "store_name", "store_location", "store_logo", "store_brand",
    "category", "sub_category", "product_title", "weight", "regular_price",
    "sale_price", "volume_deals_description", "volume_deals_price",
    "digital_deals_description", "digital_deals_price", "image_url", "url",
    "upc", "gupc", "ppm", "unit_price", "crawl_date",
)
CHECKS = (
    "authorized_collection_verified",
    "assigned_store_verified",
    "complete_category_and_subcategory_audit",
    "pickup_and_in_store_eligibility_audit",
    "marketplace_and_shipping_exclusion_audit",
    "ppm_promotion_and_price_spotcheck",
    "interruption_and_repeat_run_observed",
    "azure_execution_observed",
)


def inspect(data: dict, report: dict, review: dict, categories: list[str], raw_bytes: bytes) -> dict:
    rows = data if isinstance(data, list) else []
    report = report if isinstance(report, dict) else {}
    review = review if isinstance(review, dict) else {}
    errors = []
    def check(ok, reason):
        if not ok:
            errors.append(reason)

    check(isinstance(data, list), "Data must be a JSON array")
    check(len(rows) >= 500, "At least 500 genuine unique records required")
    check(not report.get("source_is_synthetic", True), "Synthetic or undocumented source is not accepted")
    check(report.get("scope") == "full", "Trial/subset output is not full coverage")
    check(report.get("status") == "validated", "Collector report not validated")
    check(report.get("source_coverage_attested") is True,
          "Automated source category coverage not attested (requires independent review)")
    actual_categories = report.get("category_counts") or {}
    check(set(actual_categories) == set(categories) and
          all(isinstance(actual_categories.get(c), int) and actual_categories[c] > 0 for c in categories),
          "Every supplied category must have a valid count")
    check(report.get("unique_records") == len(rows), "Record count disagrees with report")
    check(len(rows) == len({(r.get("zipcode", ""), r.get("url", "").split("?", 1)[0])
                            for r in rows if isinstance(r, dict)}),
          "Duplicate product URLs within a store; inspect manually")
    check(all(isinstance(r, dict) and tuple(r) == FIELDS and
              all(isinstance(value, str) for value in r.values()) and
              r.get("gupc") == r.get("unit_price") == "" for r in rows),
          "Each record must match exact 22-field schema, ordering and blank downstream fields")
    check(bool(rows) and len({r.get("zipcode") for r in rows if isinstance(r, dict)}) == 1,
          "A contest sample must belong to a single store ZIP")
    check(review.get("data_sha256") == hashlib.sha256(raw_bytes).hexdigest(),
          "Signed-off review must identify exact data SHA-256")
    check(bool(review.get("assigned_store_id")), "Assigned store ID missing in review")
    check(bool(review.get("reviewer")) and bool(review.get("reviewed_at_utc")),
          "Human reviewer and review timestamp are required")
    attestations = review.get("attestations", {})
    references = review.get("evidence", {})
    for item in CHECKS:
        check(attestations.get(item) is True and isinstance(references.get(item), str)
              and references.get(item).strip(), f"Unverified: {item} (attestation + evidence reference required)")
    return {
        "status": "PASS_REQUIRES_BUYER_CONFIRMATION" if not errors else "BLOCKED",
        "records": len(rows), "required_categories": len(categories),
        "errors": errors,
        "warning": "A successful local gate does NOT independently authenticate Walmart data or prove Azure operation. The buyer must verify evidence."
    }


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--data", type=Path, required=True, help="Exact collector data.json")
    p.add_argument("--report", type=Path, required=True, help="Matching collector report.json")
    p.add_argument("--review", type=Path, required=True, help="Manual evidence review JSON")
    p.add_argument("--categories", type=Path, default=Path(__file__).resolve().parents[1]/"config/categories.csv")
    p.add_argument("--output", type=Path, help="Optional gate result path")
    args = p.parse_args(argv)
    try:
        raw = args.data.read_bytes()
        with args.categories.open(encoding="utf-8-sig", newline="") as f:
            categories = [r["Category (Auto)"] for r in csv.DictReader(f)]
        result = inspect(json.loads(raw), json.loads(args.report.read_text()),
                         json.loads(args.review.read_text()), categories, raw)
    except (ValueError, OSError, KeyError) as exc:
        result = {"status":"BLOCKED", "errors":[f"Cannot read evidence package: {type(exc).__name__}"]}
    serialized = json.dumps(result, indent=2)
    print(serialized)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized + "\n", encoding="utf-8")
    return 0 if result["status"].startswith("PASS_") else 2


if __name__ == "__main__":
    raise SystemExit(main())
