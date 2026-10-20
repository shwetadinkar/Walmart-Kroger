"""Client-executed, non-publishing connectivity check for approved Mariano's feeds.

Produces a small, sanitized report. Never writes API secrets, bearer tokens,
product records, or provider signed URLs to its report. It does not substitute
for the independent full-catalog 500-record acceptance test.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from marianos_collector.config import categories_from_csv, stores_from_json
from marianos_collector.kroger import Credentials, KrogerClient, location_candidates, trial
from marianos_collector.schema import RecordRejected, make_record, utc_day
from marianos_collector.sources import AuthorizedProviderSource


def _result(mode: str) -> dict:
    return {
        "mode": mode,
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "result": "NOT_RUN",
        "api_secret_included": False,
        "product_data_included": False,
        "full_category_coverage_verified": False,
        "verified_500_real_products": False,
        "azure_run_verified": False,
        "suitable_as_final_contest_proof": False,
        "warnings": [],
    }


def diagnose_kroger(zipcode: str, location_id: str, address_contains: str, terms: str) -> dict:
    """Checks location identity and a small search sample; public search is not exhaustive."""
    result = _result("KROGER_PUBLIC_API_DIAGNOSTIC")
    client = KrogerClient(Credentials.from_environment())
    matches = location_candidates(client, zipcode, address_contains)
    result["marianos_location_candidates"] = [
        {"location_id": m["locationId"], "zipcode": m["zipcode"], "city": m["city"],
         "store_name": m["name"], "street": m["address"]} for m in matches
    ]
    if not matches:
        result["result"] = "NO_MATCHING_MARIANOS_STORE"
        return result
    if not location_id:
        result["result"] = "NEEDS_VERIFIED_LOCATION_ID"
        result["warnings"].append("Choose the exact store ID after checking its address and rerun.")
        return result
    selected = [m for m in matches if m["locationId"] == location_id]
    if len(selected) != 1:
        result["result"] = "LOCATION_ID_NOT_MATCHED"
        return result
    sample_terms = [s.strip() for s in terms.split(",") if s.strip()]
    if not sample_terms:
        result["result"] = "NO_SEARCH_TERMS"
        return result
    data = trial(client, location_id, sample_terms, limit_per_term=10, max_pages=1)
    result["location_id_verified_in_search"] = True
    result["term_search_counts"] = data["matches_by_term"]
    result["unique_preview_count"] = data["unique_preview_records"]
    result["result"] = "DIAGNOSTIC_OK" if data["unique_preview_records"] else "NO_SAMPLE_PRODUCTS"
    result["warnings"].append(
        "Kroger public term search does not prove complete categories, original coupon wording, or displayed PPM."
    )
    return result


def diagnose_provider(stores_file: Path, store_id: str, categories_file: Path, category_limit: int) -> dict:
    """Read only the first page of a few configured roots via the approved feed."""
    result = _result("APPROVED_PROVIDER_FIRST_PAGE_DIAGNOSTIC")
    if os.environ.get("MARIANOS_DATA_AUTHORIZED") != "yes":
        result["result"] = "AUTHORIZATION_CONFIRMATION_MISSING"
        return result
    stores = stores_from_json(stores_file)
    store = next((s for s in stores if s.store_id == store_id), None)
    if not store or store_id.upper().startswith(("DEMO", "REPLACE", "UNRESOLVED")):
        result["result"] = "VERIFIED_STORE_CONFIGURATION_REQUIRED"
        return result
    provider = AuthorizedProviderSource(os.getenv("PROVIDER_BASE_URL", ""), os.getenv("PROVIDER_API_TOKEN", ""))
    cats = categories_from_csv(categories_file)
    if len(cats) != 28:
        result["result"] = "CATEGORY_CONFIGURATION_INCOMPLETE"
        return result
    result["configured_category_roots"] = len(cats)
    result["store_id"] = store.store_id
    result["zipcode"] = store.zipcode
    root_results = []
    all_ok = True
    for cat in cats[:category_limit]:
        row = {"category": cat.name, "page_has_verified_store": False,
               "first_page_product_count": 0, "eligible_preview_count": 0,
               "subcategories_on_first_page": 0, "has_next_page": False}
        try:
            page = provider.fetch(store, cat, cat.url, "")
            if page.store_id != store.store_id or page.zipcode != store.zipcode or not page.store_context_verified:
                raise ValueError("Store or ZIP mismatch on category page")
            if not page.location_evidence_url:
                raise ValueError("Missing independent store location evidence")
            if not page.subcategories_complete:
                raise ValueError("Provider cannot attest complete child discovery for this page")
            row["page_has_verified_store"] = True
            row["first_page_product_count"] = len(page.products)
            row["subcategories_on_first_page"] = len(page.children)
            row["has_next_page"] = bool(page.next_cursor)
            for raw in page.products:
                if raw.get("store_id") != store.store_id or raw.get("zipcode") != store.zipcode:
                    raise ValueError("Product-level store mismatch")
                try:
                    make_record(raw, store, cat.name, "", utc_day())
                except RecordRejected as err:
                    if str(err) in ("STORE_MISMATCH", "UNVERIFIED_PRODUCT_LOCATION"):
                        raise ValueError("Product-level location verification failed") from err
                else:
                    row["eligible_preview_count"] += 1
            if not page.products and not page.children and not page.next_cursor:
                raise ValueError("Root has neither products nor discoverable pages/subcategories")
        except Exception as exc:
            row["status"] = "FAILED"
            row["error_type"] = type(exc).__name__
            # Do not expose raw provider error strings: they might include signed URLs.
            all_ok = False
        else:
            row["status"] = "OK"
        root_results.append(row)
    result["sampled_roots"] = root_results
    result["result"] = "DIAGNOSTIC_OK" if all_ok else "PROVIDER_SAMPLE_FAILED"
    result["warnings"].append("First-page checks do NOT establish full 28-root/subcategory completeness or 500 real records.")
    return result


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--mode", choices=("kroger", "provider"), required=True)
    p.add_argument("--zipcode", default="60601")
    p.add_argument("--location-id", default="")
    p.add_argument("--address-contains", default="")
    p.add_argument("--terms", default="milk,bread")
    p.add_argument("--store", default="")
    p.add_argument("--stores", type=Path, default=ROOT / "config/stores_live.json")
    p.add_argument("--categories", type=Path, default=ROOT / "config/categories.csv")
    p.add_argument("--sample-roots", type=int, default=2)
    p.add_argument("--report", type=Path, default=ROOT / "submission_evidence/live_access_preflight.json")
    a = p.parse_args(argv)
    if not 1 <= a.sample_roots <= 28:
        p.error("--sample-roots must be 1..28")
    if a.mode == "provider" and not a.store:
        p.error("Provider mode requires --store VERIFIED_LOCATION_ID")
    try:
        if a.mode == "kroger":
            result = diagnose_kroger(a.zipcode, a.location_id, a.address_contains, a.terms)
        else:
            result = diagnose_provider(a.stores, a.store, a.categories, a.sample_roots)
    except Exception as exc:
        result = _result(a.mode.upper())
        result["result"] = "CONNECTION_FAILED"
        result["error_type"] = type(exc).__name__
        result["warnings"].append("Review API permissions, store identity, source availability and provider contract.")
    a.report.parent.mkdir(parents=True, exist_ok=True)
    a.report.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0 if result["result"] == "DIAGNOSTIC_OK" else 1


if __name__ == "__main__":
    raise SystemExit(main())
