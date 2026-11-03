"""Field-level composition of several data sources into one record set.

WHY THIS EXISTS
---------------
No single source supplies all 22 fields.

  * Kroger Catalog V2 supplies store-bound prices, nFor volume offers, size,
    UPC, categories and the product URL. It exposes no digital coupon terms at
    all, and its `unit` field is not confirmed to be displayed price per
    measure.
  * A website crawl is the only route that has ever shown displayed PPM and
    clippable coupon terms, and it is refused from Azure datacenter egress.
  * An authorized provider supplies whatever its contract supplies, which
    varies by provider and is not knowable in advance.

So the system composes. Each source declares which fields it can supply; a
per-field precedence policy decides who wins; every value in the output can be
traced back to the source that produced it.

SPINE AND ENRICHMENT
--------------------
Sources do not paginate alike. A Catalog V2 sweep pages by offset, a provider
pages by cursor, a crawl pages by whatever the site does. Merging pages from
sources whose cursors do not align is not meaningful.

So exactly one source is the *spine*: it enumerates the assortment and drives
pagination and identity. Every other source is an *enrichment*, looked up per
product by identity and contributing only the fields it declares.

OUTPUT SHAPE IS UNCHANGED
-------------------------
Provenance is deliberately NOT written into the product dicts. The 22-field
output is fixed, ordered and string-only, and a delivered package has already
been verified by hash. Adding a key to the record would change that output.
Provenance is accumulated beside the records and surfaced through
`provenance_report()` for the run manifest instead.
"""
from __future__ import annotations

import logging
from collections import Counter
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass, field

from .schema import FIELDS
from .sources import Page, SourceError

LOG = logging.getLogger("collector")

# Fields the composer never takes from a source: they are set by the collector
# from configuration or the clock, not observed from a retailer.
DERIVED_FIELDS = frozenset(
    {
        "zipcode",
        "store_name",
        "store_location",
        "store_logo",
        "category",
        "sub_category",
        "gupc",
        "unit_price",
        "crawl_date",
    }
)

COMPOSABLE_FIELDS = frozenset(FIELDS) - DERIVED_FIELDS

# Default per-field precedence. Earlier names win when both supply a value.
#
# The ordering encodes what each route can actually evidence:
#   * prices, volume offers and identity come from the authenticated API first,
#     because a store-bound API value is stronger evidence than a parsed page
#   * displayed PPM and digital coupon terms come from the crawl first, because
#     no Kroger API exposes coupon terms and the API's per-measure field is an
#     unconfirmed candidate
DEFAULT_POLICY: dict[str, tuple[str, ...]] = {
    "product_title": ("catalog_v2", "provider", "crawl"),
    "weight": ("catalog_v2", "provider", "crawl"),
    "regular_price": ("catalog_v2", "provider", "crawl"),
    "sale_price": ("catalog_v2", "provider", "crawl"),
    "volume_deals_description": ("catalog_v2", "provider", "crawl"),
    "volume_deals_price": ("catalog_v2", "provider", "crawl"),
    "digital_deals_description": ("crawl", "provider"),
    "digital_deals_price": ("crawl", "provider"),
    "image_url": ("catalog_v2", "provider", "crawl"),
    "url": ("catalog_v2", "provider", "crawl"),
    "upc": ("catalog_v2", "provider", "crawl"),
    "ppm": ("crawl", "provider", "catalog_v2"),
    "store_brand": ("catalog_v2", "provider", "crawl"),
}


class CompositionError(RuntimeError):
    pass


@dataclass
class Availability:
    """Whether a source can run right now, and if not, why not.

    An unavailable source is a normal state, not an error. The crawl is
    unavailable from Azure because the retailer refuses datacenter egress, and
    that refusal is a measured fact rather than a bug to retry around. The run
    continues with the fields that source would have supplied left blank, and
    the reason is recorded so the gap in the output is explained rather than
    merely present.
    """

    available: bool
    reason: str = ""

    @classmethod
    def ok(cls) -> "Availability":
        return cls(True, "")

    @classmethod
    def blocked(cls, reason: str) -> "Availability":
        if not reason:
            raise CompositionError("An unavailable source must state a reason")
        return cls(False, reason)


# A contributed value is evidence only if it is tied to this product, at this
# store, on a fulfilment the brief admits, at a stated time. A lookup returns
# these beside its fields, and a value without them is not merged: an offer read
# for another store or from an undated page must not pass as this product's.
# The same rule as Walmart's composition; it is also what stops a West Loop page
# read reaching a Vernon Hills row.
BINDING_KEY = "_binding"

# Where the COMPLETE provenance evidence is persisted beside a release. The
# provenance block in a run report is a capped preview that names this file;
# the preview is never the evidence.
DURABLE_EVIDENCE_FILENAME = "provenance_evidence.json"
# The fulfilments the brief admits at all. Membership here is necessary and
# NOT sufficient: a contribution must also match the fulfilment of the
# observation it is being merged into. Accepting anything in this set was the
# defect, because it let an in-store reading pass as a pickup one.
FULFILMENTS = ("pickup", "in_store")

# An observation describes a shelf at a moment. Past some age it is a
# historical record, not evidence about the run being published. Seven days
# matches the checkpoint staleness rule in runner.py, so the two agree.
MAX_OBSERVATION_AGE = timedelta(days=7)
# Clocks on the observing machine and this one are not the same clock.
FUTURE_TOLERANCE = timedelta(minutes=5)


def parse_observed_at(value):
    """The observation time as an aware UTC datetime, or None if unusable.

    Checking only that the field was non-empty meant any string at all passed
    as a timestamp, so an unparseable or absurd value was indistinguishable
    from a real one.
    """
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith(("Z", "z")):
        text = text[:-1] + "+00:00"
    try:
        stamp = datetime.fromisoformat(text)
    except ValueError:
        return None
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp.astimezone(timezone.utc)


def binding_refusal(binding, store, identity: str, required_fulfillment=None,
                    now=None, max_age=MAX_OBSERVATION_AGE) -> str:
    """Why a contribution cannot be tied to this observation, or "".

    `required_fulfillment` is the fulfilment of the observation being enriched.
    It is not optional in practice: `CompositeSource` always supplies it and
    refuses the contribution when it cannot be determined, because a
    contribution that cannot be tied to a fulfilment is not tied to anything.
    """
    if not isinstance(binding, dict):
        return "UNBOUND_NO_BINDING"
    if str(binding.get("identity") or "") != identity or not identity:
        return "UNBOUND_PRODUCT"
    if str(binding.get("store_id") or "") != store.store_id:
        return "UNBOUND_STORE"
    fulfillment = binding.get("fulfillment")
    if fulfillment not in FULFILMENTS:
        return "UNBOUND_FULFILLMENT"
    if required_fulfillment is None:
        return "UNBOUND_FULFILLMENT_UNKNOWN"
    if fulfillment != required_fulfillment:
        return "UNBOUND_FULFILLMENT_MISMATCH"
    observed = parse_observed_at(binding.get("observed_at"))
    if observed is None:
        return "UNBOUND_TIME"
    now = now or datetime.now(timezone.utc)
    if observed > now + FUTURE_TOLERANCE:
        return "UNBOUND_TIME_FUTURE"
    if now - observed > max_age:
        return "UNBOUND_STALE"
    return ""


class Enrichment:
    """Base class for a source that contributes fields to products it did not enumerate.

    Subclasses set `name` and `fields`, and implement `lookup`. They are called
    once per product, keyed by that product's identity. A lookup that returns
    any field must also return `BINDING_KEY` with identity, store_id,
    fulfillment and observed_at.
    """

    name = "enrichment"
    fields: frozenset = frozenset()

    def availability(self) -> Availability:
        return Availability.ok()

    def lookup(self, store, identity: str, product: dict) -> dict:
        raise NotImplementedError

    def _declared(self, result: dict) -> dict:
        """Keep only fields this source declared, so one source cannot quietly
        start supplying another's fields and bypass the precedence policy."""
        if not isinstance(result, dict):
            raise CompositionError(f"{self.name} returned a non-object enrichment")
        undeclared = set(result) - set(self.fields) - {BINDING_KEY}
        if undeclared:
            raise CompositionError(
                f"{self.name} returned undeclared fields: {sorted(undeclared)}"
            )
        kept = {k: v for k, v in result.items()
                if k != BINDING_KEY and isinstance(v, str) and v}
        if BINDING_KEY in result:
            kept[BINDING_KEY] = result[BINDING_KEY]
        return kept


class CallableEnrichment(Enrichment):
    """Wraps a plain function as an enrichment source.

    This is how a website crawl, a second provider, or any operator-supplied
    fetcher is plugged in without this module having to know what it is. The
    availability callable is separate from the lookup so a source can report
    itself unavailable without being called once per product.
    """

    def __init__(self, name: str, fields, lookup, availability=None):
        if not name:
            raise CompositionError("An enrichment source needs a name")
        unknown = set(fields) - COMPOSABLE_FIELDS
        if unknown:
            raise CompositionError(f"{name} declares non-composable fields: {sorted(unknown)}")
        self.name = name
        self.fields = frozenset(fields)
        self._lookup = lookup
        self._availability = availability or (lambda: Availability.ok())

    def availability(self) -> Availability:
        return self._availability()

    def lookup(self, store, identity: str, product: dict) -> dict:
        return self._declared(self._lookup(store, identity, product) or {})


def unavailable_crawl(reason: str, fields=("ppm", "digital_deals_description", "digital_deals_price")):
    """A website-crawl enrichment that is registered but cannot currently run.

    Registered rather than omitted on purpose. The system's shape should show
    that a crawl is a first-class source for the two field groups no API
    supplies, and that it is blocked for a stated reason, so that the day it
    can run the change is configuration rather than architecture.
    """
    return CallableEnrichment(
        name="crawl",
        fields=fields,
        lookup=lambda store, identity, product: {},
        availability=lambda: Availability.blocked(reason),
    )


@dataclass
class _Trace:
    sources_by_field: dict = field(default_factory=dict)
    conflicts: list = field(default_factory=list)
    bindings_by_field: dict = field(default_factory=dict)


class CompositeSource:
    """One spine source plus any number of enrichment sources.

    Implements the same fetch() contract as every other source, so the runner,
    schema, storage and retention logic are untouched.
    """

    def __init__(self, spine, spine_name: str, enrichments=None, policy=None,
                 required_fulfillment=None):
        if not hasattr(spine, "fetch"):
            raise CompositionError("The spine must implement fetch()")
        self.spine = spine
        self.spine_name = spine_name
        # When set, every contribution must carry this fulfilment. When not,
        # it is taken per product from the observation being enriched.
        self.required_fulfillment = required_fulfillment
        self.enrichments = list(enrichments or [])
        names = [spine_name] + [e.name for e in self.enrichments]
        if len(set(names)) != len(names):
            raise CompositionError(f"Duplicate source names: {names}")
        self.policy = dict(policy or DEFAULT_POLICY)

        unknown = set(self.policy) - COMPOSABLE_FIELDS
        if unknown:
            raise CompositionError(f"Policy names non-composable fields: {sorted(unknown)}")

        self._traces: dict[str, _Trace] = {}
        self._field_sources = Counter()
        self._conflicts: list = []
        self._skipped: dict[str, str] = {}
        self._unbound = Counter()
        self._refused = []
        self._bindings: dict = {}

    # --- delegation ----------------------------------------------------
    #
    # A composite wraps a spine, and anything the runner asks of a source must
    # reach it. Forwarding names one at a time lost three in turn here:
    # `unresolved_offers`, `reset_unresolved`, and then `coverage_attested`,
    # which made the composite publish path unrunnable - the CLI decided scope
    # from the spine's attestation while the runner read the composite's, found
    # nothing, and refused every authorized composite release. The same
    # omission silently skipped the uncovered-roots staleness gate, because
    # `populated_roots` never reached the spine either.
    #
    # So forwarding is the default, ported from the Walmart module which had
    # already been fixed this way: every public attribute the composite does
    # not define itself comes from the spine, read live, and one the spine
    # lacks stays absent. The gate judges the spine's own statement and nothing
    # here claims coverage on its behalf. `unresolved_offers` is no longer
    # forwarded as an empty list either, so a spine that keeps no such record
    # does not read as a count of zero.
    #
    # Defined here rather than forwarded: fetch, source_mode, reset_unresolved,
    # provenance_report, durable_evidence and spine_source_mode, which do the
    # spine's work plus the composite's.

    def __getattr__(self, name):
        if name.startswith("_") or "spine" not in self.__dict__:
            raise AttributeError(name)
        return getattr(self.__dict__["spine"], name)

    def reset_unresolved(self):
        if hasattr(self.spine, "reset_unresolved"):
            self.spine.reset_unresolved()
        # Provenance is per run too. Accumulating it across runs on a reused
        # instance would misreport which source produced how many values.
        self._traces = {}
        self._field_sources = Counter()
        self._conflicts = []
        self._skipped = {}
        self._unbound = Counter()
        self._refused = []
        self._bindings = {}

    @property
    def spine_source_mode(self) -> str:
        """What actually enumerated the data.

        The runner's mode-dependent checks read this rather than
        `source_mode`, because `source_mode` reports `composite(...)`, which
        starts with neither `synthetic_fixture` nor `authorized_provider`.
        Wrapping a fixture therefore cleared `source_is_synthetic` and hid the
        synthetic label; wrapping a provider skipped the location-evidence
        check that mode requires. The composite must not be able to launder
        the spine's identity.

        The `getattr` makes this recurse, so a composite wrapped in another
        composite still reports the real enumerating source.
        """
        return getattr(self.spine, "spine_source_mode", self.spine.source_mode)

    @property
    def source_mode(self) -> str:
        parts = [self.spine_name] + [
            e.name for e in self.enrichments if e.availability().available
        ]
        return "composite(" + "+".join(parts) + ")"

    # --------------------------------------------------------------- merging

    def _identity(self, product: dict) -> str:
        return str(product.get("product_id") or product.get("upc") or product.get("url") or "")

    def _rank(self, field_name: str, source_name: str) -> int:
        """Lower is better. A source absent from a field's policy ranks last,
        so it can still fill a blank but never displaces a ranked source."""
        order = self.policy.get(field_name)
        if not order:
            return 0 if source_name == self.spine_name else 1
        try:
            return order.index(source_name)
        except ValueError:
            return len(order)

    def _bound(self, enrichment, store, identity: str, product: dict) -> dict:
        """A lookup's fields, or nothing if they cannot be tied to this product."""
        result = dict(enrichment.lookup(store, identity, product) or {})
        binding = result.pop(BINDING_KEY, None)
        if not result:
            return {}
        required = self.required_fulfillment or (product or {}).get("fulfillment")
        refusal = binding_refusal(binding, store, identity,
                                  required_fulfillment=required)
        if refusal:
            self._unbound[(enrichment.name, refusal)] += len(result)
            # Retained, not merely counted. A refused contribution is a real
            # observation that does not apply here; it is kept with its own
            # context and date so it stays available as history.
            self._refused.append({
                "source": enrichment.name, "reason": refusal,
                "identity": identity, "required_fulfillment": required,
                "binding": binding if isinstance(binding, dict) else None,
                "values": {k: v for k, v in result.items()},
            })
            return {}
        self._bindings[(identity, enrichment.name)] = dict(binding)
        return result

    def _merge(self, product: dict, contributions: list) -> dict:
        """Apply per-field precedence across the spine and every enrichment.

        `contributions` is [(source_name, {field: value})], spine first.
        """
        identity = self._identity(product)
        trace = self._traces.setdefault(identity, _Trace())
        merged = dict(product)

        for field_name in COMPOSABLE_FIELDS:
            offers = [
                (self._rank(field_name, name), index, name, values[field_name])
                for index, (name, values) in enumerate(contributions)
                if field_name in values and values[field_name]
            ]
            if not offers:
                continue
            offers.sort(key=lambda item: (item[0], item[1]))
            _, _, winner, value = offers[0]
            merged[field_name] = value
            trace.sources_by_field[field_name] = winner
            if (identity, winner) in self._bindings:
                trace.bindings_by_field[field_name] = self._bindings[(identity, winner)]
            self._field_sources[(field_name, winner)] += 1

            # Record disagreement rather than resolving it quietly. Two sources
            # reporting different prices for the same product at the same store
            # is a finding about the sources, and the client should see it.
            for _, _, other_name, other_value in offers[1:]:
                if other_value != value:
                    conflict = {
                        "identity": identity,
                        "field": field_name,
                        "kept": {"source": winner, "value": value,
                                 "binding": self._bindings.get((identity, winner))},
                        "discarded": {"source": other_name, "value": other_value,
                                      "binding": self._bindings.get((identity, other_name))},
                    }
                    trace.conflicts.append(conflict)
                    self._conflicts.append(conflict)
        return merged

    # ----------------------------------------------------------------- fetch

    def fetch(self, store, category, url: str, cursor: str) -> Page:
        page = self.spine.fetch(store, category, url, cursor)

        live = []
        for enrichment in self.enrichments:
            status = enrichment.availability()
            if status.available:
                live.append(enrichment)
            elif enrichment.name not in self._skipped:
                self._skipped[enrichment.name] = status.reason
                LOG.warning(
                    "enrichment_unavailable",
                    extra={
                        "event": "enrichment_unavailable",
                        "store_id": store.store_id,
                        "category": category.name,
                    },
                )

        if not live:
            for product in page.products:
                self._merge(product, [(self.spine_name, product)])
            return page

        merged_products = []
        for product in page.products:
            identity = self._identity(product)
            contributions = [(self.spine_name, product)]
            for enrichment in live:
                try:
                    contributions.append(
                        (enrichment.name, self._bound(enrichment, store, identity, product))
                    )
                except CompositionError:
                    # A source breaking its own declaration is a defect here,
                    # not a transient fault, so it is not swallowed.
                    raise
                except SourceError as exc:
                    # One enrichment failing on one product must not lose the
                    # product. The spine's value stands and the miss is counted.
                    self._skipped.setdefault(
                        enrichment.name, f"partial failures during run: {exc}"
                    )
            merged_products.append(self._merge(product, contributions))

        page.products = merged_products
        return page

    # ------------------------------------------------------------ provenance

    def provenance_report(self) -> dict:
        by_field: dict[str, dict] = {}
        for (field_name, source_name), count in self._field_sources.items():
            by_field.setdefault(field_name, {})[source_name] = count
        return {
            "source_mode": self.source_mode,
            "spine": self.spine_name,
            "enrichments": [e.name for e in self.enrichments],
            "enrichments_unavailable": dict(self._skipped),
            "policy": {k: list(v) for k, v in self.policy.items()},
            "values_by_field_and_source": by_field,
            "conflicts": self._conflicts[:200],
            "conflict_count": len(self._conflicts),
            "products_traced": len(self._traces),
            "contributions_refused_as_unbound": {
                f"{name}:{reason}": count for (name, reason), count in self._unbound.items()},
            # Counts say how many were refused; these say what they were, so a
            # refused observation is retained with its own context and date
            # rather than disappearing into a tally.
            #
            # This is a PREVIEW. The client's point on 3 November: "if that is
            # the persisted evidence, later refused observations are still
            # lost. Keep complete durable history separately; a capped report
            # preview is fine when it points to that complete record." The
            # complete list is `durable_evidence()`, which the runner and the
            # merge tool both persist as their own artefact, and the two keys
            # below say how many there are and where to read them.
            "refused_contributions_preview": self._refused[:200],
            "refused_contributions_preview_capped_at": 200,
            "refused_contribution_count": len(self._refused),
            "complete_evidence_artifact": DURABLE_EVIDENCE_FILENAME,
            # Per field, per product: which source won and WHEN that source
            # observed it. Also his point: the freshness window "must not
            # relabel an older observed price or offer as newly observed on a
            # later run. Preserve each source observation time and its
            # context." A count here, the times themselves in the artefact.
            "field_observations_recorded": sum(
                len(t.bindings_by_field) for t in self._traces.values()),
        }

    def durable_evidence(self) -> dict:
        """The complete record, for persisting beside the release.

        Everything in here is uncapped on purpose. `provenance_report()` is a
        preview that points at this; nothing in the pipeline may treat the
        preview as the evidence.
        """
        observations = {}
        for identity, trace in sorted(self._traces.items()):
            per_field = {}
            for field_name, binding in sorted(trace.bindings_by_field.items()):
                source = trace.sources_by_field.get(field_name, "")
                per_field[field_name] = {
                    "source": source,
                    # The observation time of the source that supplied this
                    # field, kept per field rather than per record, so a page
                    # value read on a later date is never presented as having
                    # been observed when the spine was.
                    "source_observed_at": (binding or {}).get("observed_at", ""),
                    "binding": binding,
                }
            if per_field:
                observations[identity] = per_field
        return {
            "_what": ("The complete provenance evidence for this run. The "
                      "provenance block in the run report is a capped preview "
                      "and points here. Nothing may be read as complete from "
                      "that preview."),
            "source_mode": self.source_mode,
            "spine": self.spine_name,
            "refused_contributions": self._refused,
            "refused_contribution_count": len(self._refused),
            "conflicts": self._conflicts,
            "conflict_count": len(self._conflicts),
            "field_observations": observations,
            "field_observation_count": sum(len(v) for v in observations.values()),
        }

    def provenance_for(self, identity: str) -> dict:
        trace = self._traces.get(identity)
        return dict(trace.sources_by_field) if trace else {}

    def evidence_for(self, identity: str) -> dict:
        """Per field: which source won and the observation it was bound to,
        with every conflict on this product. `conflicts` in provenance_report
        is capped for reading; this is not."""
        trace = self._traces.get(identity)
        if not trace:
            return {"fields": {}, "conflicts": []}
        return {"fields": {name: {"source": source,
                                  "binding": trace.bindings_by_field.get(name)}
                           for name, source in sorted(trace.sources_by_field.items())},
                "conflicts": list(trace.conflicts)}
