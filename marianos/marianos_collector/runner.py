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
from .retention import observation, reconcile, stable_identity, stamp
from .schema import FIELDS, RecordRejected, make_retained_record
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
        # Prevent two-category experiments from replacing the complete 28-root dataset.
        category_signature = _payload_hash([(c.name, c.url) for c in categories])[:12]
        self.namespace = f"trials/{category_signature}" if trial else "published"
        self.checkpoint_root = f"checkpoints-trials/{category_signature}" if trial else "checkpoints"

    def _checkpoint_key(self, store, category):
        return f"{self.checkpoint_root}/{store.store_id}/{category.slug}.json"

    def _collect_category(self, store, category):
        cp_key = self._checkpoint_key(store, category)
        cp = read_json(self.storage, cp_key)
        config_id = _payload_hash({"store":store.store_id, "category":category.name, "url":category.url})
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
                "seen_urls":[category.url], "seen_requests":[], "pages":[], "finished":False
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
            page_id = len(cp["pages"])
            stage_key = f"staging/{store.store_id}/{cp['run_id']}/{category.slug}/{page_id:07d}.json"
            stage = {"task":task,"page":page.__dict__,"observed_at":datetime.now(timezone.utc).isoformat()}
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
        # A source that tracks offers it could not publish, or accumulates
        # provenance, starts each run clean. Without this a reused source
        # reports another run's numbers: three runs of one CompositeSource gave
        # per-source value totals of 178, then 356, then 534. The walmart runner
        # already did this; the marianos delegation was dead code until now.
        if hasattr(self.source, "reset_unresolved"):
            self.source.reset_unresolved()
        start = time.monotonic()
        with self.storage.locked(store.store_id):
            return self._run_locked(store, start)

    def _run_locked(self, store, start):
        pointer_key = f"{self.namespace}/{store.store_id}/latest.json"
        previous_pointer = read_json(self.storage, pointer_key)
        previous_manifest = read_json(self.storage, previous_pointer["manifest_key"]) if previous_pointer else None
        if previous_pointer and previous_manifest is None:
            raise ValidationFailure("Previous successful manifest is missing")
        all_stages = {}
        LOG.info("run_started", extra={"event":"run_started", "store_id":store.store_id, "source_mode":self.source.source_mode})
        for cat in self.categories:
            all_stages[cat.name] = self._collect_category(store, cat)
        records = []
        observations = {}
        value_refusals = Counter()
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
                    observed_at = raw.get("observed_at") or stage.get("observed_at")
                    if not observed_at:
                        raise ValidationFailure("MISSING_STAGE_OBSERVATION_TIMESTAMP")
                    try:
                        rec, refused = make_retained_record(raw, store, cat.name, sub_category or str(raw.get("sub_category") or ""), stamp(observed_at).date().isoformat())
                        identity = stable_identity(rec, store.store_id)
                    except RecordRejected as ex:
                        reason = str(ex)
                        if reason in {"STORE_MISMATCH", "UNVERIFIED_PRODUCT_LOCATION"}:
                            raise ValidationFailure(reason) from ex
                        rejected[reason] += 1
                        continue
                    except ValueError as ex:
                        rejected[str(ex)] += 1
                        continue
                    value_refusals.update(r["reason"] for r in refused)
                    per_cat.add(identity)
                    observed_ids.add(str(raw.get("product_id") or rec["upc"] or ""))
                    if identity in seen:
                        duplicates += 1
                        continue
                    seen.add(identity)
                    records.append(rec)
                    available = raw.get("pickup_available")
                    observations[identity] = observation(
                        rec, store.store_id, observed_at,
                        [{"url":stage["page"]["source_url"], "sha256":_payload_hash(stage)}],
                        "available" if available is True else "unavailable" if available is False else "unknown")
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
        if not self.categories:
            raise ValidationFailure("No configured categories")
        collection_at = datetime.now(timezone.utc).isoformat()
        prior_rows, prior_retention = [], {}
        if previous_manifest:
            prior_rows = read_json(self.storage, previous_manifest["data_key"])
            if any(r["zipcode"] != store.zipcode or r["store_location"] != store.store_location for r in prior_rows):
                raise ValidationFailure("PRIOR_STORE_CONTEXT_MISMATCH")
            if not previous_manifest.get("retention_key"):
                raise ValidationFailure("PREVIOUS_RETENTION_METADATA_REQUIRED")
            prior_retention = read_json(self.storage, previous_manifest["retention_key"])
        accumulated = reconcile(records, observations, store.store_id, collection_at, prior_rows, prior_retention)
        records = accumulated["products"]
        # A release that loses a published identity must not validate, whatever
        # produced the loss.
        kept = {stable_identity(r, store.store_id) for r in records}
        lost = sorted({stable_identity(r, store.store_id) for r in prior_rows} - kept)
        if lost:
            raise ValidationFailure(f"PUBLISHED_IDENTITY_LOST: {lost[:5]}")
        if not all(list(rec.keys()) == list(FIELDS) and all(isinstance(v, str) for v in rec.values()) for rec in records):
            raise ValidationFailure("Exact output schema validation failed")
        field_counts = {f:sum(bool(x[f]) for x in records) for f in FIELDS}
        field_completeness = {f:{"nonempty":field_counts[f], "percentage":round(100*field_counts[f]/len(records),2)} for f in FIELDS}
        report = {
            "store_id": store.store_id, "zipcode":store.zipcode, "source_mode":self.source.source_mode,
            "source_is_synthetic": self.source.source_mode.startswith("synthetic_fixture"),
            "status":"validated", "timestamp_utc":datetime.now(timezone.utc).isoformat(),
            "runtime_seconds":round(time.monotonic()-start,3),
            "unique_records":len(records),"duplicate_placements":duplicates,
            "current_records":accumulated["current_records"],"carried_forward_records":accumulated["carried_forward_records"],
            "submission_ready":False,"values_refused_by_reason":dict(value_refusals),
            "category_counts":category_counts, "new_output_records_by_category":seen_products_by_category,
            "excluded_records_by_reason":dict(rejected),"field_completeness":field_completeness,
            "example_ppm":[{"title":r["product_title"],"ppm":r["ppm"]} for r in records if r["ppm"]][:5],
            "example_volume_deals":[{"title":r["product_title"],"description":r["volume_deals_description"],"displayed_price":r["volume_deals_price"]} for r in records if r["volume_deals_description"]][:5],
            "example_digital_deals":[{"title":r["product_title"],"description":r["digital_deals_description"],"displayed_price":r["digital_deals_price"]} for r in records if r["digital_deals_description"]][:5],
            "pages_by_category":{k:len(v) for k,v in all_stages.items()},
            "location_evidence_urls":[st["page"].get("location_evidence_url", "") for stages in all_stages.values() for st in stages if st["page"].get("location_evidence_url")][:15],
            "coverage_scope": "subset_trial" if self.trial else "all_configured_roots",
            "independent_live_review_required": True,
            # Offers the source saw but could not publish, and why. Without this
            # the record lives only on the source object, which the CLI discards
            # after run(), so the gap between what was seen and what was
            # published would be unexplainable from the release itself.
            **({"unresolved_offers": {
                    "count": len(self.source.unresolved_offers),
                    "by_reason": dict(Counter(u.get("reason", "")
                                              for u in self.source.unresolved_offers)),
                    "sample": self.source.unresolved_offers[:25]}}
               if hasattr(self.source, "unresolved_offers") else {}),
            # A composed run can take different fields from different sources,
            # so the report has to say which source produced what. Sources that
            # do not compose have nothing to add here.
            **(
                {"provenance": self.source.provenance_report()}
                if hasattr(self.source, "provenance_report")
                else {}
            ),
            "caution":"This is NOT contest proof if source_is_synthetic=true, or coverage_scope=subset_trial. Live providers require independent verification."
        }
        release = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")+"_"+uuid.uuid4().hex[:8]
        prefix = f"{self.namespace}/{store.store_id}/runs/{release}"
        data_key, report_key, manifest_key = prefix+"/data.json", prefix+"/report.json", prefix+"/manifest.json"
        # Versioned artifacts first. latest pointer is committed LAST.
        write_json(self.storage, data_key, records)
        write_json(self.storage, report_key, report)
        retention_key = prefix+"/retention.json"
        write_json(self.storage, retention_key, accumulated["retention"])
        manifest = {"store_id":store.store_id, "zipcode":store.zipcode, "release":release, "data_key":data_key,
                    "report_key":report_key, "retention_key":retention_key, "category_counts":category_counts, "records":len(records), "source_mode":self.source.source_mode,
                    "coverage_scope": "subset_trial" if self.trial else "all_configured_roots"}
        write_json(self.storage, manifest_key, manifest)
        if hasattr(self.storage, "assert_lock_held"):
            self.storage.assert_lock_held()
        write_json(self.storage, pointer_key, {"manifest_key":manifest_key,"release":release})
        # Checkpoints are discarded after successful publication; staged pages remain for audit.
        for cat in self.categories:
            self.storage.delete(self._checkpoint_key(store, cat))
        LOG.info("run_published", extra={"event":"run_published", "store_id":store.store_id,"records":len(records),"release":release})
        return {"manifest":manifest,"report":report}
