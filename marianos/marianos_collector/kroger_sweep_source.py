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

import hashlib
import json
import logging
from pathlib import Path

from .api_trial import load_category_map, to_raw_product
from .retention import stable_identity
from .sources import Page
from .sweep_core import MAX_START, REQUESTED_FULFILLMENT, STATE_VERSION, Budget, sweep

LOG = logging.getLogger("collector")


class SweepCursorInvalid(RuntimeError):
    """A persisted page cursor no longer identifies the products it was issued for."""

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
        # The out-of-scope products themselves, not just a count of them. The
        # client asked on 4 November that their original retailer labels and
        # identities be retained in a separate reconciliation with source paths
        # and counts, and that no historical observation be discarded. Only a
        # count was kept before, so the identities could not be produced
        # without re-indexing. They are never served under any root: this list
        # is written beside the release, not into it.
        self.out_of_scope: list[dict] = []
        self.malformed: dict[str, int] = {}
        self.responses = 0
        self.products_seen = 0
        self.duplicates = 0
        self.unplaceable = 0
        # Raw responses skipped because they were collected at another
        # location, keyed by the locationId they actually carry. Never empty
        # silently: a non-zero count here means the work directory holds
        # another store's observations and they were refused, not relabelled.
        self.foreign_location: dict[str, int] = {}
        self.terms_indexed: dict[str, int] = {}

    @property
    def product_count(self) -> int:
        return sum(len(v) for v in self.by_root.values())

    def populated_roots(self) -> list[str]:
        return sorted(k for k, v in self.by_root.items() if v)

    def fingerprint(self, root: str) -> str:
        """A digest of the exact products this root would serve, in order.

        The runner persists a page cursor in its checkpoint and resumes in a
        new process, where this index is rebuilt from disk. If the raw
        directory changed in between, a numeric offset into the rebuilt list
        points somewhere else, and products the sweep observed are never
        served by either run. Carrying this digest in the cursor turns that
        into a refusal instead of a silent loss.
        """
        basis = "\n".join(f"{p.get('url') or ''}|{p.get('upc') or ''}"
                          for p in self.by_root.get(root, []))
        return hashlib.sha256(basis.encode()).hexdigest()[:12]


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

        **Every response is checked against the location it was collected at.**
        `to_raw_product` stamps the store columns and
        `store_context_verified: True` from whatever `Store` it is handed, so
        indexing another store's responses would relabel them as this store's
        observations. A work directory shared between two stores did exactly
        that: three West Loop products were served as Vernon Hills, verified,
        with no error and no report line, which is the one thing the working
        rules forbid outright. The sweep writes `locationId` into every
        response file, so the check is a comparison and not a heuristic, and a
        foreign response is refused and counted rather than converted.
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
            where = str(document.get("locationId") or "")
            if where != str(self.location_id):
                # Another store's observation, or one whose store cannot be
                # established. Either way it is not evidence of this store.
                index.foreign_location[where or "(absent)"] = \
                    index.foreign_location.get(where or "(absent)", 0) + 1
                continue
            index.responses += 1
            index.terms_indexed[str(document.get("term") or "")] = \
                index.terms_indexed.get(str(document.get("term") or ""), 0) + 1
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
                    # Retained with the label exactly as the retailer returned
                    # it, so any eventual mapping can be supported by the
                    # retailer's own taxonomy rather than by the search term.
                    index.out_of_scope.append({
                        "identity": identity,
                        "upc": raw.get("upc", ""),
                        "product_title": raw.get("product_title", ""),
                        "retailer_label": label or "",
                        "configured_root": "",
                        "source_response_file": str(path.relative_to(self.raw_dir)),
                        "search_term": str(document.get("term") or ""),
                        "observed_at": observed_at,
                        "product_id": context.get("product_id", ""),
                    })
                    continue
                state = context.get("availability_state")
                raw = dict(raw, sub_category=label, observed_at=observed_at,
                           product_id=context.get("product_id", ""),
                           pickup_available=True if state == "available"
                           else False if state == "unavailable" else None,
                           # RETENTION_POLICY.md requires retention.json to
                           # repeat this per identity. Keeping only
                           # availability_state and product_id left every
                           # runner-route release with an empty
                           # pickup_context, so the whole context travels.
                           pickup_context=dict(
                               context, response_file=str(path.relative_to(self.raw_dir)),
                               observed_at=observed_at))
                index.by_root.setdefault(root, []).append(raw)
        return index

    # -------------------------------------------------------------- page serve

    def fetch(self, store, category, url: str, cursor: str) -> Page:
        """One page of this root's products.

        The cursor is `<fingerprint>:<offset>`, not a bare offset. The runner
        persists it in a checkpoint and resumes in a new process, where this
        index is rebuilt from disk; a bare offset into a list that gained or
        lost files in between points at the wrong products. Measured: across
        two processes, 14 products observed, 10 published, 4 served by neither
        run, `status: validated`, no gate fired, and the only trace was a
        `duplicate_placements: 4` that reads like deduplication working.

        So the offset is only honoured when the root's contents are the ones
        it was issued against. Otherwise this refuses, because the alternative
        is losing observed products quietly, and a run that stops and asks for
        a reset is the behaviour the runner already has for a stale checkpoint.
        """
        index = self.sweep_once(store)
        products = index.by_root.get(category.name, [])
        fingerprint = index.fingerprint(category.name)
        start = 0
        if cursor:
            issued, _, offset = cursor.rpartition(":")
            if not offset.isdecimal():
                raise SweepCursorInvalid(
                    f"Unreadable sweep cursor {cursor!r} for {category.name}")
            if issued != fingerprint:
                raise SweepCursorInvalid(
                    f"The sweep index for {category.name} changed since this cursor was "
                    f"issued ({issued or 'none'} then, {fingerprint} now), so the offset "
                    f"no longer identifies the same products. Reset the checkpoints for "
                    f"this store and rerun; continuing would skip observed products "
                    f"without reporting them.")
            start = int(offset)
        window = products[start:start + self.serve_page_size]
        end = start + self.serve_page_size
        return Page(
            store_id=store.store_id,
            zipcode=store.zipcode,
            store_context_verified=True,
            source_url=url,
            products=window,
            children=[],
            next_cursor=f"{fingerprint}:{end}" if end < len(products) else "",
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

    def provenance_report(self) -> dict:
        """Everything a reviewer needs about what this sweep reached.

        Named `provenance_report` because that is the name the runner looks
        for (`runner.py`, the report assembly). It was called `provenance`,
        which nothing but tests ever called, so none of this reached a single
        release: not the unmapped labels, not the 187 unplaceable products,
        not `page_failures`, not `stopped_reason`, not the coverage limit. The
        working rules claimed the 187 were "counted and named in
        provenance()"; they were counted on an object the CLI discarded. This
        is the same defect the runner's `unresolved_offers` block exists to
        fix, and it is fixed the same way.
        """
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
            # Completed means collected, not merely finished with. An
            # abandoned term is added to `done_terms` so a resume stops
            # retrying it, so counting that list reported 1 of 1 terms
            # completed for a term that collected nothing across three
            # attempts. The two are now separate figures and the abandoned ones
            # are subtracted here.
            "terms_completed": (len(state.get("done_terms", []))
                                - len(state.get("terms_abandoned", []))),
            "terms_done_including_abandoned": len(state.get("done_terms", [])),
            "terms_hit_start_cap": len(state.get("terms_hit_start_cap", [])),
            # Failure EVENTS, one per failed request. A term retried across
            # three resumes contributes three, so this is not a count of
            # affected terms and was read as one; the distinct figure is
            # beside it.
            "page_failures": len(state.get("page_failures", [])),
            "page_failure_events": len(state.get("page_failures", [])),
            "terms_with_a_page_failure": len(
                {f.get("term") for f in state.get("page_failures", [])}),
            # A term whose pages did not all complete is not marked done, so a
            # resume retries it. After MAX_TERM_ATTEMPTS it is marked done and
            # named here. These are terms we stopped trying to collect, which
            # is a coverage fact and belongs in the report rather than only in
            # the checkpoint.
            "terms_abandoned_after_retries": sorted(
                state.get("terms_abandoned", [])),
            "terms_abandoned_count": len(state.get("terms_abandoned", [])),
            # Terms carrying an unfinished attempt. Non-zero means this run
            # left work a resume would pick up, and that the term counts below
            # are not the whole of what the configured terms would yield.
            "terms_incomplete_pending_retry": sorted(
                k for k, n in (state.get("term_attempts") or {}).items()
                if k not in set(state.get("terms_abandoned", []))),
            "stopped_reason": state.get("stopped_reason"),
            "raw_dir": str(self.raw_dir),
            "checkpoint": str(self.checkpoint_path),
            "responses_indexed": index.responses if index else None,
            "products_seen": index.products_seen if index else None,
            "products_served": index.product_count if index else None,
            "duplicate_identities": index.duplicates if index else None,
            "unplaceable_unmapped_products": index.unplaceable if index else None,
            # The identities themselves, for the out-of-scope reconciliation the
            # client asked for. Carried here rather than in the release, because
            # these products belong to no configured root and must not appear
            # under one. Their presence here does not establish completion of
            # any required root.
            "out_of_scope_products": list(index.out_of_scope) if index else None,
            "unmapped_labels": dict(sorted(index.unmapped.items())) if index else None,
            "malformed_by_reason": dict(sorted(index.malformed.items())) if index else None,
            "populated_roots": index.populated_roots() if index else None,
            # Non-zero means the work directory held responses collected at
            # another location and they were refused rather than relabelled as
            # this store's. A reviewer has to be able to see that happened.
            "responses_refused_as_foreign_location": (
                dict(sorted(index.foreign_location.items())) if index else None),
            "terms_the_index_drew_from": len(index.terms_indexed) if index else None,
        }
