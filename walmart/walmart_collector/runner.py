"""End-to-end collection, crash-safe checkpoints, validation and promotion."""
from __future__ import annotations

import hashlib
import json
import logging
import time
import uuid
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any

from .config import check_retailer_url, is_excluded_subcategory
from .schema import FIELDS, RecordRejected, fingerprint, make_record, utc_day
from .storage import read_json, write_json

LOG = logging.getLogger("collector")

class ValidationFailure(RuntimeError):
    pass

def _payload_hash(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

class Collector:
    def __init__(self, storage, source, categories, min_products=500, previous_ratio=0.5, max_pages=100000, canaries=None, trial=False):
        self.storage = storage
        self.source = source
        self.categories = categories
        self.min_products = min_products
        self.previous_ratio = previous_ratio
        self.max_pages = max_pages
        self.canaries = canaries or {}
        self.trial = trial
        # Trial and full releases, checkpoints and staging never share a namespace.
        # A trial of Food/Beauty cannot replace the 11-category latest pointer.
        definition = [(c.name, c.url) for c in categories]
        self.scope = ("trial-" + _payload_hash(definition)[:16]) if trial else "full"

    def _published_root(self, store):
        return (f"trials/{store.store_id}/{self.scope}"
                if self.trial else f"published/{store.store_id}")

    def _checkpoint_key(self, store, category):
        return f"checkpoints/{store.store_id}/{self.scope}/{category.slug}.json"

    def _collect_category(self, store, category):
        cp_key = self._checkpoint_key(store, category)
        cp = read_json(self.storage, cp_key)
        config_id = _payload_hash({"store":store.store_id, "category":category.name, "url":category.url,
                                   "source": self.source.source_mode, "scope": self.scope})
        if cp:
            started = datetime.fromisoformat(cp["started_at"])
            if cp["config_id"] != config_id or datetime.now(timezone.utc) - started > timedelta(days=7):
                raise ValidationFailure(f"Stale/mismatched checkpoint for {category.name}: explicit reset required")
            LOG.info("resume_checkpoint", extra={"event": "resume_checkpoint", "category": category.name, "pages":len(cp["pages"])})
        else:
            cp = {
                "config_id":config_id, "run_id":uuid.uuid4().hex,
                "started_at":datetime.now(timezone.utc).isoformat(),
                "queue":[{"url":category.url, "sub_category":"", "cursor":""}],
                "seen_urls":[category.url], "seen_requests":[], "pages":[], "finished":False,
                "source_revision":""
            }
            write_json(self.storage, cp_key, cp)

        while cp["queue"]:
            if len(cp["pages"]) >= self.max_pages:
                raise ValidationFailure(f"Page safety limit reached for {category.name}")
            task = cp["queue"][0]
            signature = _payload_hash({"url": task["url"], "cursor":task["cursor"]})
            if signature in cp["seen_requests"]:
                raise ValidationFailure(f"Repeated page/cursor discovered in {category.name}")
            page = self.source.fetch(store, category, task["url"], task["cursor"])
            if page.store_id != store.store_id or page.zipcode != store.zipcode or not page.store_context_verified:
                raise ValidationFailure(f"Location context mismatch: {category.name}")
            if self.source.source_mode.startswith("authorized_provider") and not page.location_evidence_url:
                raise ValidationFailure("Authorized provider did not provide independent location evidence URI")
            if page.source_url.split("?",1)[0] != task["url"].split("?",1)[0]:
                raise ValidationFailure("Provider source URL does not match the page being collected")
            if not page.subcategories_complete:
                raise ValidationFailure(f"Provider cannot attest complete subcategory discovery: {category.name}")
            for prod in page.products:
                if not isinstance(prod, dict):
                    raise ValidationFailure("Provider returned malformed product")
                if prod.get("store_id") != store.store_id or prod.get("zipcode") != store.zipcode or prod.get("store_context_verified") is not True:
                    raise ValidationFailure("Product-level store context mismatch or unknown")
            revision = getattr(page, "source_revision", "")
            if not isinstance(revision, str):
                raise ValidationFailure("Invalid source revision in page")
            if cp["pages"] and revision != cp.get("source_revision", ""):
                raise ValidationFailure(f"Source snapshot changed during {category.name}; reset required")
            if not cp["pages"]:
                cp["source_revision"] = revision
            page_id = len(cp["pages"])
            stage_key = f"staging/{store.store_id}/{self.scope}/{cp['run_id']}/{category.slug}/{page_id:07d}.json"
            stage = {"task":task,"page":page.__dict__}
            # Stage first, then advance checkpoint; on crash an orphan staged page is harmless.
            write_json(self.storage, stage_key, stage)
            cp["pages"].append({"key":stage_key, "sha256":_payload_hash(stage)})
            cp["seen_requests"].append(signature)
            cp["queue"].pop(0)
            if page.next_cursor:
                next_sig = _payload_hash({"url":task["url"], "cursor":page.next_cursor})
                if next_sig in cp["seen_requests"]:
                    raise ValidationFailure("Pagination cursor loop")
                cp["queue"].append({**task, "cursor":page.next_cursor})
            for child in page.children:
                if is_excluded_subcategory(child["name"], category.exclusions):
                    continue
                check_retailer_url(child["url"])
                if child["url"] not in cp["seen_urls"]:
                    cp["seen_urls"].append(child["url"])
                    cp["queue"].append({"url":child["url"], "sub_category":child["name"], "cursor":""})
            write_json(self.storage, cp_key, cp)
            LOG.info("page_saved", extra={"event":"page_saved", "store_id":store.store_id, "category":category.name, "pages":len(cp["pages"]), "products":len(page.products)})
        if not cp["finished"]:
            cp["finished"] = True
            write_json(self.storage, cp_key, cp)
        stages = []
        for p in cp["pages"]:
            stage = read_json(self.storage, p["key"])
            if stage is None or _payload_hash(stage) != p["sha256"]:
                raise ValidationFailure(f"Missing/corrupt staged page: {p['key']}")
            stages.append(stage)
        return stages

    def run(self, store):
        start = time.monotonic()
        with self.storage.locked(store.store_id):
            return self._run_locked(store, start)

    def _run_locked(self, store, start):
        pointer_key = self._published_root(store) + "/latest.json"
        previous_pointer = read_json(self.storage, pointer_key)
        previous_manifest = read_json(self.storage, previous_pointer["manifest_key"]) if previous_pointer else None
        if previous_pointer and previous_manifest is None:
            raise ValidationFailure("Previous successful manifest is missing")
        all_stages = {}
        LOG.info("run_started", extra={"event":"run_started", "store_id":store.store_id, "source_mode":self.source.source_mode})
        for cat in self.categories:
            all_stages[cat.name] = self._collect_category(store, cat)
        records = []
        seen = set()
        category_counts = {}
        rejected = Counter()
        duplicates = 0
        seen_products_by_category = {}
        for cat in self.categories:
            observed_ids = set()
            per_cat = set()
            count = 0
            for stage in all_stages[cat.name]:
                sub_category = stage["task"]["sub_category"]
                for raw in stage["page"]["products"]:
                    try:
                        rec = make_record(raw, store, cat.name, sub_category or str(raw.get("sub_category") or ""), utc_day())
                    except RecordRejected as ex:
                        reason = str(ex)
                        if reason in {"STORE_MISMATCH", "UNVERIFIED_PRODUCT_LOCATION"}:
                            raise ValidationFailure(reason) from ex
                        rejected[reason] += 1
                        continue
                    identity = fingerprint(rec, raw)
                    per_cat.add(identity)
                    observed_ids.add(str(raw.get("product_id") or rec["upc"] or ""))
                    if identity in seen:
                        duplicates += 1
                        continue
                    seen.add(identity)
                    records.append(rec)
                    count += 1
            category_counts[cat.name] = len(per_cat)
            seen_products_by_category[cat.name] = count
            if len(per_cat) == 0:
                raise ValidationFailure(f"Zero eligible products: {cat.name} (failed is not empty)")
            if previous_manifest:
                prior_count = previous_manifest.get("category_counts", {}).get(cat.name)
                if isinstance(prior_count, int) and prior_count > 0 and len(per_cat) < prior_count * self.previous_ratio:
                    raise ValidationFailure(f"Suspicious yield collapse in {cat.name}: {len(per_cat)} vs prior {prior_count}")
            required_canaries = self.canaries.get(cat.name, [])
            if any(str(x) not in observed_ids for x in required_canaries):
                raise ValidationFailure(f"Missing canary product in {cat.name}")
        if len(records) < self.min_products:
            raise ValidationFailure(f"Only {len(records)} valid unique products, minimum {self.min_products}")
        if len([x for x in category_counts.values() if x > 0]) < 2:
            raise ValidationFailure("Contest demo must cover multiple categories")
        if not all(list(rec.keys()) == list(FIELDS) and all(isinstance(v, str) for v in rec.values()) for rec in records):
            raise ValidationFailure("Exact output schema validation failed")
        field_counts = {f:sum(bool(x[f]) for x in records) for f in FIELDS}
        field_completeness = {f:{"nonempty":field_counts[f], "percentage":round(100*field_counts[f]/len(records),2)} for f in FIELDS}
        report = {
            "store_id": store.store_id, "zipcode":store.zipcode, "source_mode":self.source.source_mode,
            "source_is_synthetic": self.source.source_mode.startswith("synthetic_fixture"),
            "scope": "trial" if self.trial else "full", "source_coverage_attested": bool(
                getattr(self.source, "coverage_attested", False)),
            "status":"validated", "timestamp_utc":datetime.now(timezone.utc).isoformat(),
            "runtime_seconds":round(time.monotonic()-start,3),
            "unique_records":len(records),"duplicate_placements":duplicates,
            "category_counts":category_counts, "new_output_records_by_category":seen_products_by_category,
            "excluded_records_by_reason":dict(rejected),"field_completeness":field_completeness,
            "example_ppm":[{"title":r["product_title"],"ppm":r["ppm"]} for r in records if r["ppm"]][:5],
            "example_volume_deals":[{"title":r["product_title"],"description":r["volume_deals_description"],"displayed_price":r["volume_deals_price"]} for r in records if r["volume_deals_description"]][:5],
            "example_digital_deals":[{"title":r["product_title"],"description":r["digital_deals_description"],"displayed_price":r["digital_deals_price"]} for r in records if r["digital_deals_description"]][:5],
            "pages_by_category":{k:len(v) for k,v in all_stages.items()},
            "location_evidence_urls":[st["page"].get("location_evidence_url", "") for stages in all_stages.values() for st in stages if st["page"].get("location_evidence_url")][:15],
            "caution":"This is NOT contest proof if source_is_synthetic=true. Live providers require independent verification."
        }
        release = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")+"_"+uuid.uuid4().hex[:8]
        prefix = f"{self._published_root(store)}/runs/{release}"
        data_key, report_key, manifest_key = prefix+"/data.json", prefix+"/report.json", prefix+"/manifest.json"
        # Versioned artifacts first. latest pointer is committed LAST.
        write_json(self.storage, data_key, records)
        write_json(self.storage, report_key, report)
        manifest = {"store_id":store.store_id, "zipcode":store.zipcode, "release":release, "data_key":data_key,
                    "report_key":report_key, "category_counts":category_counts, "records":len(records), "source_mode":self.source.source_mode,
                    "scope": "trial" if self.trial else "full"}
        write_json(self.storage, manifest_key, manifest)
        if hasattr(self.storage, "assert_lock_held"):
            self.storage.assert_lock_held()
        write_json(self.storage, pointer_key, {"manifest_key":manifest_key,"release":release})
        # Checkpoints are discarded after successful publication; staged pages remain for audit.
        for cat in self.categories:
            self.storage.delete(self._checkpoint_key(store, cat))
        LOG.info("run_published", extra={"event":"run_published", "store_id":store.store_id,"records":len(records),"release":release})
        return {"manifest":manifest,"report":report}
