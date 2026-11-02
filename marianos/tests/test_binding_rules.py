"""A contribution must be tied to THIS observation, not merely a plausible one.

Two things were wrong. `binding_refusal` tested fulfilment for membership of
("pickup", "in_store") rather than against the fulfilment of the observation
being enriched, so an in-store reading passed as a pickup one. And
`observed_at` was only tested for non-empty text, so any string at all passed
as a timestamp and an observation of any age was as good as a fresh one.

A refused contribution is a real observation that does not apply here. It is
retained with its own context and date rather than vanishing into a tally.
"""

import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from marianos_collector.composition import (  # noqa: E402
    BINDING_KEY,
    CallableEnrichment,
    CompositeSource,
    MAX_OBSERVATION_AGE,
    binding_refusal,
    parse_observed_at,
)
from marianos_collector.sources import Page  # noqa: E402

NOW = datetime(2026, 11, 2, 12, 0, 0, tzinfo=timezone.utc)
FRESH = (NOW - timedelta(hours=2)).isoformat()


class Store:
    store_id = "53100502"
    zipcode = "60061"


class Cat:
    name = "all"


def binding(**over):
    b = {"identity": "0001", "store_id": "53100502",
         "fulfillment": "pickup", "observed_at": FRESH}
    b.update(over)
    return b


def refusal(b, required="pickup", now=NOW):
    return binding_refusal(b, Store(), "0001",
                           required_fulfillment=required, now=now)


class ParsingTheObservationTime(unittest.TestCase):
    def test_a_zulu_timestamp_parses_to_utc(self):
        self.assertEqual(parse_observed_at("2026-11-01T10:00:00Z"),
                         datetime(2026, 11, 1, 10, 0, tzinfo=timezone.utc))

    def test_a_bare_date_parses_and_is_treated_as_utc(self):
        self.assertEqual(parse_observed_at("2026-11-01"),
                         datetime(2026, 11, 1, 0, 0, tzinfo=timezone.utc))

    def test_an_offset_timestamp_is_converted_to_utc(self):
        self.assertEqual(parse_observed_at("2026-11-01T15:30:00+05:30"),
                         datetime(2026, 11, 1, 10, 0, tzinfo=timezone.utc))

    def test_text_that_is_not_a_time_does_not_parse(self):
        for junk in ("", "   ", "yesterday", "soon", "n/a", "2026-13-45"):
            self.assertIsNone(parse_observed_at(junk), junk)


class FulfilmentMustMatchTheObservation(unittest.TestCase):
    def test_a_matching_fulfilment_binds(self):
        self.assertEqual(refusal(binding(fulfillment="pickup"), "pickup"), "")

    def test_an_in_store_reading_does_not_pass_as_pickup(self):
        self.assertEqual(refusal(binding(fulfillment="in_store"), "pickup"),
                         "UNBOUND_FULFILLMENT_MISMATCH")

    def test_a_pickup_reading_does_not_pass_as_in_store(self):
        self.assertEqual(refusal(binding(fulfillment="pickup"), "in_store"),
                         "UNBOUND_FULFILLMENT_MISMATCH")

    def test_a_fulfilment_outside_the_admitted_set_is_refused(self):
        self.assertEqual(refusal(binding(fulfillment="delivery"), "delivery"),
                         "UNBOUND_FULFILLMENT")

    def test_an_undeterminable_required_fulfilment_fails_closed(self):
        self.assertEqual(refusal(binding(), None), "UNBOUND_FULFILLMENT_UNKNOWN")


class ObservationsMustBeFresh(unittest.TestCase):
    def test_a_recent_observation_binds(self):
        self.assertEqual(refusal(binding(observed_at=FRESH)), "")

    def test_an_unparseable_time_is_refused(self):
        self.assertEqual(refusal(binding(observed_at="whenever")), "UNBOUND_TIME")

    def test_an_empty_time_is_refused(self):
        self.assertEqual(refusal(binding(observed_at="")), "UNBOUND_TIME")

    def test_an_observation_from_the_future_is_refused(self):
        future = (NOW + timedelta(days=4)).isoformat()
        self.assertEqual(refusal(binding(observed_at=future)), "UNBOUND_TIME_FUTURE")

    def test_small_clock_skew_is_tolerated(self):
        skewed = (NOW + timedelta(minutes=2)).isoformat()
        self.assertEqual(refusal(binding(observed_at=skewed)), "")

    def test_an_observation_older_than_the_window_is_refused(self):
        old = (NOW - MAX_OBSERVATION_AGE - timedelta(hours=1)).isoformat()
        self.assertEqual(refusal(binding(observed_at=old)), "UNBOUND_STALE")

    def test_an_observation_just_inside_the_window_binds(self):
        edge = (NOW - MAX_OBSERVATION_AGE + timedelta(hours=1)).isoformat()
        self.assertEqual(refusal(binding(observed_at=edge)), "")


class TheOtherBindingChecksStillHold(unittest.TestCase):
    def test_another_product_is_refused(self):
        self.assertEqual(refusal(binding(identity="9999")), "UNBOUND_PRODUCT")

    def test_another_store_is_refused(self):
        self.assertEqual(refusal(binding(store_id="53100508")), "UNBOUND_STORE")

    def test_no_binding_at_all_is_refused(self):
        self.assertEqual(refusal(None), "UNBOUND_NO_BINDING")


class RefusedContributionsAreRetained(unittest.TestCase):
    """Counting a refusal loses the observation. The client asked for the
    historical value to be kept with its own context and dates."""

    @staticmethod
    def _live_binding(**over):
        """Relative to the real clock, because CompositeSource uses the real
        clock. The pinned NOW above is only for calling binding_refusal
        directly, and reusing it here put the timestamp in the future."""
        b = {"identity": "0001", "store_id": "53100502", "fulfillment": "pickup",
             "observed_at": (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()}
        b.update(over)
        return b

    def _composite_with(self, contributed_binding):
        product = {"upc": "0001", "fulfillment": "pickup", "ppm": ""}

        class Spine:
            source_mode = "test_spine"
            unresolved_offers = []

            def fetch(self, store, category, url, cursor):
                return Page(store_id=store.store_id, zipcode=store.zipcode,
                            store_context_verified=True, source_url=url,
                            products=[dict(product)], children=[],
                            next_cursor="", subcategories_complete=True)

        def lookup(store, identity, prod):
            return {"ppm": "$0.33/oz", BINDING_KEY: contributed_binding}

        composite = CompositeSource(
            Spine(), "spine", [CallableEnrichment("crawl", ("ppm",), lookup)])
        merged = composite.fetch(Store(), Cat(), "replay://x", "").products
        return merged, composite.provenance_report()

    def test_a_stale_contribution_is_not_merged(self):
        old = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        merged, _ = self._composite_with(self._live_binding(observed_at=old))
        self.assertEqual(merged[0]["ppm"], "")

    def test_a_stale_contribution_is_kept_with_its_value_and_date(self):
        old = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        _, report = self._composite_with(self._live_binding(observed_at=old))
        self.assertEqual(report["refused_contribution_count"], 1)
        kept = report["refused_contributions"][0]
        self.assertEqual(kept["reason"], "UNBOUND_STALE")
        self.assertEqual(kept["values"]["ppm"], "$0.33/oz")
        self.assertEqual(kept["binding"]["observed_at"], old)

    def test_a_mismatched_fulfilment_is_kept_with_both_fulfilments(self):
        _, report = self._composite_with(self._live_binding(fulfillment="in_store"))
        kept = report["refused_contributions"][0]
        self.assertEqual(kept["reason"], "UNBOUND_FULFILLMENT_MISMATCH")
        self.assertEqual(kept["binding"]["fulfillment"], "in_store")
        self.assertEqual(kept["required_fulfillment"], "pickup")

    def test_a_good_contribution_is_merged_and_not_listed_as_refused(self):
        merged, report = self._composite_with(self._live_binding())
        self.assertEqual(merged[0]["ppm"], "$0.33/oz")
        self.assertEqual(report["refused_contribution_count"], 0)


if __name__ == "__main__":
    unittest.main()
