"""The term sweep as a collector Source, so the runner drives it.

The 26,166 records delivered on 31 October were produced by `tools/
kroger_full_sweep.py`, outside the collector. That meant they never passed the
publication gate, retention reconciliation, the trial and published namespace
separation, or a resume driven by the runner. The client identified the gap
directly. `sweep_core` moved the sweep into the package; this module is the
adapter that lets `Collector` drive it.

How it works, and why in two phases:

1. **Sweep.** `sweep_core.sweep` runs the terms, checkpointing after each one
   and writing the full API response for every page under `raw/`. That is the
   observation of record.
2. **Index.** Every raw response is read back off disk and mapped to raw
   products through `api_trial.to_raw_product`, bucketed by the product's own
   mapped root.

Phase 2 reads the files rather than the sweep's return value on purpose. The
sweep's checkpoint holds *finished records*, so a resumed sweep would have
records for the terms already done and no products to hand the runner, and the
two runs would deliver different things. Indexing from the persisted responses
is identical whether the sweep ran fresh or resumed, and it is the
re-filter-rather-than-re-fetch property the fourth defect in the working rules
asked for, actually used rather than merely claimed.

What this source cannot attest, and so declares:

- `coverage_attested = False`. The public Products API has no category
  enumeration. `filter.start` is a skip count Kroger refuses past 250, so one
  term reaches at most 300 products however many sit behind it.
- A product whose retailer label is not in the explicit category map has no
  configured root to be delivered under. It is counted and named in
  `provenance()`, never guessed into a root. In the 31 October data that is
  187 of 26,166 products.
- Five of the client's 28 roots came back empty in that run, because Kroger's
  label vocabulary has no equivalent, not because the shelf is empty. The
  runner refuses a release with an empty configured root, which is correct, so
  a run through this source names the roots it can populate.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from .api_trial import load_category_map, to_raw_product
from .retention import stable_identity
from .sources import Page
from .sweep_core import MAX_START, REQUESTED_FULFILLMENT, STATE_VERSION, Budget, sweep

LOG = logging.getLogger("collector")

# 0, 50 ... 250. One more page would ask for start 300, which Kroger refuses.
PAGES_PER_TERM = MAX_START // 50 + 1

# How many products one Page carries to the runner. Each page is staged and
# hashed, so this trades staging files against page size; it does not affect
# what is collected.
SERVE_PAGE_SIZE = 250


class SweepIndex:
    """Raw products bucketed by the root their own retailer label maps to."""

    def __init__(self):
        self.by_root: dict[str, list[dict]] = {}
        self.identities: set[str] = set()
        self.unmapped: dict[str, int] = {}
        self.malformed: dict[str, int] = {}
        self.responses = 0
        self.products_seen = 0
        self.duplicates = 0
        self.unplaceable = 0

    @property
    def product_count(self) -> int:
        return sum(len(v) for v in self.by_root.values())

    def populated_roots(self) -> list[str]:
        return sorted(k for k, v in self.by_root.items() if v)


class KrogerSweepSource:
    """Collector source backed by the Kroger public Products API term sweep.

    Implements the same `fetch(store, category, url, cursor) -> Page` contract
    as `FixtureSource`, `AuthorizedProviderSource` and `CatalogV2Source`, so
    the runner does not change.
    """

    source_mode = "kroger_public_products_api_term_sweep"
    # Term-filtered search cannot enumerate a category. Declared False so the
    # runner confines the output to the trial namespace and the report carries
    # source_coverage_attested=false. The per-page subcategories_complete flag
    # this source returns is False for the same reason.
    coverage_attested = False

    def __init__(self, client, location_id: str, work_dir: Path,
                 terms_by_category: dict | None = None, category_map: dict | None = None,
                 max_requests: int = 1500, max_seconds: float = 7200.0,
                 pages_per_term: int = PAGES_PER_TERM,
                 serve_page_size: int = SERVE_PAGE_SIZE, resume: bool = True):
        if not location_id or location_id.upper().startswith(("DEMO", "REPLACE", "UNRESOLVED")):
            raise ValueError(
                "The term sweep needs a real Kroger locationId confirmed from the "
                "Locations API, not a demo placeholder")
        if serve_page_size < 1:
            raise ValueError("serve_page_size must be at least 1")
        self.client = client
        self.location_id = location_id
        self.work_dir = Path(work_dir)
        self.terms_by_category = terms_by_category or {}
        self.category_map = load_category_map() if category_map is None else category_map
        self.max_requests = max_requests
        self.max_seconds = max_seconds
        self.pages_per_term = pages_per_term
        self.serve_page_size = serve_page_size
        self.resume = resume
        self._index: SweepIndex | None = None
        self._state: dict | None = None

    # ------------------------------------------------------------------ paths

    @property
    def checkpoint_path(self) -> Path:
        return self.work_dir / "checkpoint.json"

    @property
    def raw_dir(self) -> Path:
        return self.work_dir / "raw"

    # ------------------------------------------------------------------ sweep

    def _resume_state(self) -> dict | None:
        """The checkpoint, if it is one this code can legitimately continue.

        A checkpoint written under other record rules holds records built under
        those rules. Refusing it is `sweep_core`'s existing position and is not
        softened here: the alternative is a dataset that is half one rule set
        and half another, with nothing in it saying which.
        """
        if not self.resume or not self.checkpoint_path.is_file():
            return None
        try:
            state = json.loads(self.checkpoint_path.read_text())
        except (OSError, ValueError) as exc:
            # `message` is a reserved LogRecord attribute: putting one in
            # `extra` raises inside logging itself, which would turn a
            # recoverable unreadable checkpoint into a crashed run. The text
            # goes in the message, not the extras.
            LOG.warning("sweep_checkpoint_unreadable: %s", exc, extra={
                "event": "sweep_checkpoint_unreadable", "store_id": self.location_id,
                "category": ""})
            return None
        if not isinstance(state, dict) or state.get("state_version") != STATE_VERSION:
            LOG.warning("sweep_checkpoint_version_refused", extra={
                "event": "sweep_checkpoint_version_refused", "store_id": self.location_id,
                "category": ""})
            return None
        return state

    def sweep_once(self, store) -> SweepIndex:
        if self._index is not None:
            return self._index
        if not self.terms_by_category:
            raise ValueError("The term sweep has no search terms configured")
        budget = Budget(self.max_requests, self.max_seconds)
        self._state = sweep(
            self.client, self.location_id, store, self.terms_by_category, budget,
            self.pages_per_term, checkpoint_path=self.checkpoint_path,
            state=self._resume_state(), log=self._log_term,
            category_map=self.category_map, raw_dir=self.raw_dir)
        self._index = self._index_raw(store)
        LOG.info("sweep_indexed: %s products in %s roots from %s responses",
                 self._index.product_count, len(self._index.populated_roots()),
                 self._index.responses,
                 extra={"event": "sweep_indexed", "store_id": store.store_id,
                        "category": ""})
        return self._index

    def _log_term(self, line):
        LOG.info("sweep_term_done: %s", line.strip(), extra={
            "event": "sweep_term_done", "store_id": self.location_id, "category": ""})

    def _index_raw(self, store) -> SweepIndex:
        """Map every persisted API response to raw products, bucketed by root.

        Deterministic: the files are walked in sorted order and products keep
        the order the response gave them, so two indexings of the same raw
        directory produce the same pages in the same order.
        """
        index = SweepIndex()
        for path in sorted(self.raw_dir.rglob("start_*.json")):
            try:
                document = json.loads(path.read_text())
            except (OSError, ValueError) as exc:
                index.malformed[f"UNREADABLE_RESPONSE:{type(exc).__name__}"] = \
                    index.malformed.get(f"UNREADABLE_RESPONSE:{type(exc).__name__}", 0) + 1
                continue
            if not isinstance(document, dict):
                index.malformed["RESPONSE_NOT_OBJECT"] = index.malformed.get("RESPONSE_NOT_OBJECT", 0) + 1
                continue
            index.responses += 1
            observed_at = str(document.get("observed_at") or "")
            response = document.get("response")
            data = response.get("data") if isinstance(response, dict) else None
            for product in data if isinstance(data, list) else []:
                index.products_seen += 1
                try:
                    raw, root, label, context = to_raw_product(product, store, self.category_map)
                    identity = stable_identity(raw, self.location_id)
                except (ValueError, TypeError, KeyError, AttributeError) as exc:
                    reason = str(exc) if isinstance(exc, ValueError) else \
                        f"MALFORMED_PRODUCT:{type(exc).__name__}"
                    index.malformed[reason] = index.malformed.get(reason, 0) + 1
                    continue
                if identity in index.identities:
                    # The same product is reached by several terms. First
                    # observation wins, which is what the sweep's own
                    # records.setdefault does.
                    index.duplicates += 1
                    continue
                index.identities.add(identity)
                if not root:
                    # No configured root, because the retailer's own label is
                    # not in the explicit map. Counted and named, never guessed
                    # into a root by the term that found it.
                    index.unmapped[label or "(none)"] = index.unmapped.get(label or "(none)", 0) + 1
                    index.unplaceable += 1
                    continue
                state = context.get("availability_state")
                raw = dict(raw, sub_category=label, observed_at=observed_at,
                           product_id=context.get("product_id", ""),
                           pickup_available=True if state == "available"
                           else False if state == "unavailable" else None)
                index.by_root.setdefault(root, []).append(raw)
        return index

    # -------------------------------------------------------------- page serve

    def fetch(self, store, category, url: str, cursor: str) -> Page:
        index = self.sweep_once(store)
        products = index.by_root.get(category.name, [])
        start = int(cursor) if cursor.isdecimal() else 0
        window = products[start:start + self.serve_page_size]
        end = start + self.serve_page_size
        return Page(
            store_id=store.store_id,
            zipcode=store.zipcode,
            store_context_verified=True,
            source_url=url,
            products=window,
            children=[],
            next_cursor=str(end) if end < len(products) else "",
            # Term-filtered search discovers no children and enumerates no
            # category, so this is False by construction and not a value this
            # source could ever honestly set True.
            subcategories_complete=False,
            location_evidence_url="",
        )

    # --------------------------------------------------------------- reporting

    def populated_roots(self) -> list[str]:
        """Roots the sweep actually found products for.

        The runner reads this to check a declaration of uncovered roots
        against what the route really reached, so a stale declaration cannot
        quietly suppress a root that has started working.
        """
        return self._index.populated_roots() if self._index else []

    def missing_roots(self, categories) -> list[str]:
        """Configured roots the sweep did not populate.

        The runner refuses a release with an empty configured root, so this is
        what a caller needs in order to choose a category set the sweep can
        actually fill, rather than discovering it as a validation failure.
        """
        if self._index is None:
            return []
        return [c.name for c in categories if not self._index.by_root.get(c.name)]

    def provenance(self) -> dict:
        index, state = self._index, self._state or {}
        return {
            "source_mode": self.source_mode,
            "contract": "Kroger public Products API, /v1/products",
            "location_id": self.location_id,
            "requested_fulfillment": REQUESTED_FULFILLMENT,
            "coverage_attested": self.coverage_attested,
            "coverage_limit": (
                "filter.start is a skip count Kroger refuses past 250, so one term "
                "reaches at most 300 products however many sit behind it, and the "
                "public API has no category enumeration at all"),
            "terms_configured": sum(len(v) for v in self.terms_by_category.values()),
            "terms_completed": len(state.get("done_terms", [])),
            "terms_hit_start_cap": len(state.get("terms_hit_start_cap", [])),
            "page_failures": len(state.get("page_failures", [])),
            "stopped_reason": state.get("stopped_reason"),
            "raw_dir": str(self.raw_dir),
            "checkpoint": str(self.checkpoint_path),
            "responses_indexed": index.responses if index else None,
            "products_seen": index.products_seen if index else None,
            "products_served": index.product_count if index else None,
            "duplicate_identities": index.duplicates if index else None,
            "unplaceable_unmapped_products": index.unplaceable if index else None,
            "unmapped_labels": dict(sorted(index.unmapped.items())) if index else None,
            "malformed_by_reason": dict(sorted(index.malformed.items())) if index else None,
            "populated_roots": index.populated_roots() if index else None,
        }
