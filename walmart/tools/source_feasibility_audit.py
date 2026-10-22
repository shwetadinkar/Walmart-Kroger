"""Audit a SAVED, authorized third-party raw response without inventing evidence.

Reads actual JSON/NDJSON exported by a permitted provider. Never contacts Walmart,
never triggers a paid service, and never republishes raw product data. Generic
field paths are mapped explicitly by the operator after inspecting the response.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import re

CRITICAL = (
    "product_id", "product_title", "upc", "weight", "price_display",
    "ppm_display", "store_id", "zipcode", "seller", "fulfillment",
    "availability", "volume_deals_description", "digital_deals_description",
)

def read_records(path: Path):
    if path.suffix.lower() in (".ndjson", ".jsonl"):
        items = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    else:
        obj = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(obj, list):
            items = obj
        elif isinstance(obj, dict) and isinstance(obj.get("records"), list):
            items = obj["records"]
        else:
            raise ValueError("Input must be a JSON array, {records:[...]}, or NDJSON")
    if not all(isinstance(x, dict) for x in items):
        raise ValueError("Each raw source record must be an object")
    return items

def get_path(obj, field_path):
    if not field_path:
        return None
    value = obj
    for part in field_path.split("."):
        if isinstance(value, dict):
            value = value.get(part)
        elif isinstance(value, list) and part.isdecimal() and int(part) < len(value):
            value = value[int(part)]
        else:
            return None
    return value

def observed(value):
    return value is not None and value != "" and value != [] and value != {}

def audit(records, mapping, store_id, zipcode, source, requests_observed=None, synthetic=False):
    if not isinstance(mapping, dict):
        raise ValueError("Mapping must be a JSON object of field names to source paths")
    for k, v in mapping.items():
        if k not in CRITICAL:
            raise ValueError(f"Unsupported mapping key: {k}")
        if not isinstance(v, str):
            raise ValueError(f"Mapping value for {k} must be a source path string")
    if not isinstance(records, list) or not all(isinstance(r, dict) for r in records):
        raise ValueError("Records must be a list of objects")
    count = len(records)
    fields = {
        field: sum(observed(get_path(r, mapping.get(field, ""))) for r in records)
        for field in CRITICAL
    }
    mismatches, unknown = [], []
    for field, expected in (("store_id", str(store_id)), ("zipcode", str(zipcode))):
        for index, r in enumerate(records):
            value = get_path(r, mapping.get(field, ""))
            if not observed(value):
                unknown.append((index, field))
            elif str(value).strip() != expected:
                mismatches.append({"index": index, "field": field, "observed": str(value)[:100]})
    upcs = [
        str(get_path(r, mapping.get("upc", ""))).strip()
        for r in records if observed(get_path(r, mapping.get("upc", "")))
    ]
    invalid_upcs = sum(not bool(re.fullmatch(r"\d{8}|\d{12}|\d{13}|\d{14}", v)) for v in upcs)
    identifiers = [
        str(get_path(r, mapping.get("product_id", "")))
        for r in records if observed(get_path(r, mapping.get("product_id", "")))
    ]
    duplicates = sum(n - 1 for n in Counter(identifiers).values() if n > 1)
    unavailable_tokens = {"not_available", "unavailable", "out_of_stock", "out of stock", "not available", "false"}
    unavailable = sum(
        str(get_path(r, mapping.get("availability", ""))).strip().lower() in unavailable_tokens
        for r in records
    )
    coverage = {
        name: {"observed": n, "total": count, "percent": round(100 * n / count, 2) if count else 0}
        for name, n in fields.items()
    }
    blockers = []
    if synthetic:
        blockers.append("SYNTHETIC_TEST_INPUT_NOT_LIVE_EVIDENCE")
    if not count:
        blockers.append("NO_RECORDS")
    if mismatches:
        blockers.append("STORE_OR_ZIP_MISMATCH")
    if unknown:
        blockers.append("STORE_OR_ZIP_EVIDENCE_MISSING")
    if invalid_upcs:
        blockers.append("SOME_UPCS_INVALID_FORMAT")
    if count and not fields["ppm_display"]:
        blockers.append("NO_DIRECTLY_DISPLAYED_PPM")
    if count and not fields["fulfillment"]:
        blockers.append("NO_FULFILLMENT_PROVENANCE")
    if count and not fields["seller"]:
        blockers.append("NO_SELLER_PROVENANCE")
    if count and not fields["upc"]:
        blockers.append("NO_SOURCE_UPCS")
    if count and not fields["volume_deals_description"]:
        blockers.append("NO_VOLUME_DEAL_EXAMPLES_YET")
    if count and not fields["digital_deals_description"]:
        blockers.append("NO_DIGITAL_DEAL_EXAMPLES_YET")
    blockers.append("FULL_CATEGORY_AND_AZURE_ACCEPTANCE_UNVERIFIED")
    return {
        "evidence_type": "synthetic_test" if synthetic else "operator_supplied_raw_source_sample_unverified",
        "source_label": source,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "store_id_expected": str(store_id),
        "zipcode_expected": str(zipcode),
        "records_inspected": count,
        "requests_observed": requests_observed,
        "requests_per_product_observed": round(requests_observed / count, 4)
            if requests_observed is not None and count else None,
        "field_coverage": coverage,
        "store_or_zip_mismatches": mismatches[:20],
        "store_or_zip_unknown_count": len(unknown),
        "invalid_upc_format_count": invalid_upcs,
        "duplicate_product_id_count": duplicates,
        "unavailable_records_present": unavailable,
        "blockers": blockers,
        "contest_ready": False,
        "notes": "Accompany this diagnostic with dated raw source data, rights confirmation, page/category manifests and independent human comparisons. This report cannot prove authorization or retailer correctness."
    }

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--input", type=Path, required=True)
    ap.add_argument("--mapping", type=Path, required=True)
    ap.add_argument("--store-id", required=True)
    ap.add_argument("--zipcode", required=True)
    ap.add_argument("--source", required=True)
    ap.add_argument("--requests-observed", type=int, default=None)
    ap.add_argument("--synthetic", action="store_true")
    ap.add_argument("--output", type=Path, default=Path("source-feasibility-report.json"))
    args = ap.parse_args(argv)
    if args.requests_observed is not None and args.requests_observed < 0:
        ap.error("Measured requests cannot be negative")
    records = read_records(args.input)
    mapping = json.loads(args.mapping.read_text(encoding="utf-8"))
    result = audit(records, mapping, args.store_id, args.zipcode, args.source, args.requests_observed, args.synthetic)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"records_inspected": result["records_inspected"], "blockers": result["blockers"], "report": str(args.output)}, indent=2))
    return 0 if result["records_inspected"] else 2

if __name__ == "__main__":
    raise SystemExit(main())
