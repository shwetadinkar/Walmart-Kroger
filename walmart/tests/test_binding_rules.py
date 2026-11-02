"""Walmart parity for the binding rules.

The same two defects existed in both composition modules: fulfilment was
tested for membership of the admitted set rather than against the fulfilment
of the observation being enriched, and `observed_at` was only tested for
non-empty text. The Mariano's suite covers the rule in depth; this file exists
so the Walmart module cannot drift away from it unnoticed.
"""

import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from walmart_collector.composition import (  # noqa: E402
    MAX_OBSERVATION_AGE,
    binding_refusal,
    parse_observed_at,
)

NOW = datetime(2026, 11, 2, 12, 0, 0, tzinfo=timezone.utc)


class Store:
    store_id = "100"
    zipcode = "72712"


def binding(**over):
    b = {"identity": "1026071385", "store_id": "100", "fulfillment": "pickup",
         "observed_at": (NOW - timedelta(hours=2)).isoformat()}
    b.update(over)
    return b


def refusal(b, required="pickup", now=NOW):
    return binding_refusal(b, Store(), "1026071385",
                           required_fulfillment=required, now=now)


class WalmartBindingParity(unittest.TestCase):
    def test_a_matching_fresh_contribution_binds(self):
        self.assertEqual(refusal(binding()), "")

    def test_an_in_store_reading_does_not_pass_as_pickup(self):
        self.assertEqual(refusal(binding(fulfillment="in_store"), "pickup"),
                         "UNBOUND_FULFILLMENT_MISMATCH")

    def test_an_undeterminable_required_fulfilment_fails_closed(self):
        self.assertEqual(refusal(binding(), None), "UNBOUND_FULFILLMENT_UNKNOWN")

    def test_an_unparseable_time_is_refused(self):
        self.assertEqual(refusal(binding(observed_at="recently")), "UNBOUND_TIME")

    def test_a_future_observation_is_refused(self):
        self.assertEqual(
            refusal(binding(observed_at=(NOW + timedelta(days=2)).isoformat())),
            "UNBOUND_TIME_FUTURE")

    def test_a_stale_observation_is_refused(self):
        old = (NOW - MAX_OBSERVATION_AGE - timedelta(hours=1)).isoformat()
        self.assertEqual(refusal(binding(observed_at=old)), "UNBOUND_STALE")

    def test_another_store_is_still_refused(self):
        self.assertEqual(refusal(binding(store_id="4376")), "UNBOUND_STORE")

    def test_the_time_parser_matches_the_marianos_one(self):
        self.assertEqual(parse_observed_at("2026-11-01T10:00:00Z"),
                         datetime(2026, 11, 1, 10, 0, tzinfo=timezone.utc))
        self.assertIsNone(parse_observed_at("whenever"))


if __name__ == "__main__":
    unittest.main()
