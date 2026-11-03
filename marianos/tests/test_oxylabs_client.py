"""The Oxylabs client, against a mocked transport. No network, dummy key only.

Three things matter here beyond the vendor's checklist. A 400 or 401 must stop
rather than be retried, because retrying a rejected key three times is how a
trial credit is spent on nothing. The thin-page ladder must be driven by the
content returned, not the status, because a 200 carrying an empty shell is the
exact case it exists for. And `scrape()` must refuse marianos.com as an
arbitrary URL: that retailer refuses our egress, and having a vendor fetch the
page we cannot reach is the route CLAUDE.md refuses by any name.
"""

import io
import json
import sys
import unittest
from pathlib import Path
from urllib.error import HTTPError, URLError

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from marianos_collector.oxylabs import (  # noqa: E402
    ATTEMPTS, OxylabsClient, OxylabsError, content_is_thin, country_for, read_page)

KEY = "dummy-key-for-tests"


class Response(io.BytesIO):
    def __init__(self, payload, status=200):
        super().__init__(json.dumps(payload).encode())
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def opener_for(sequence):
    """Each call pops the next outcome: a dict to return, or an exception."""
    calls = []

    def opener(request, timeout=None):
        calls.append({"url": request.full_url, "method": request.get_method(),
                      "headers": dict(request.header_items()),
                      "body": json.loads(request.data.decode()) if request.data else None,
                      "timeout": timeout})
        outcome = sequence.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return Response(outcome)

    opener.calls = calls
    return opener


def http_error(code, body=None):
    return HTTPError("https://webapi.oxylabs.io/v1/search", code, "err", {},
                     io.BytesIO(json.dumps(body or {}).encode()))


class TheContractOnEveryRequest(unittest.TestCase):
    def client(self, sequence):
        return OxylabsClient(key=KEY, opener=opener_for(sequence), sleep=lambda s: None)

    def test_bearer_on_every_request(self):
        opener = opener_for([{"results": []}, {"results": []}])
        client = OxylabsClient(key=KEY, opener=opener, sleep=lambda s: None)
        client.search("milk")
        client.scrapers()
        for call in opener.calls:
            self.assertEqual(call["headers"].get("Authorization"), f"Bearer {KEY}")

    def test_the_timeout_is_set(self):
        opener = opener_for([{"results": []}])
        OxylabsClient(key=KEY, opener=opener, sleep=lambda s: None).search("milk")
        self.assertEqual(opener.calls[0]["timeout"], 150)

    def test_the_key_is_never_in_the_repr(self):
        self.assertNotIn(KEY, repr(self.client([])))

    def test_the_request_id_is_captured(self):
        client = self.client([{"results": [], "metadata": {"request_id": "abc123"}}])
        client.search("milk")
        self.assertEqual(client.request_ids, ["abc123"])

    def test_any_2xx_is_success(self):
        opener = opener_for([])

        def two_oh_two(request, timeout=None):
            return Response({"results": [{"markdown": "x" * 500}]}, status=202)

        client = OxylabsClient(key=KEY, opener=two_oh_two, sleep=lambda s: None)
        self.assertTrue(client.scrape("https://example.com")["results"])


class ValidationHappensBeforeAnythingIsSent(unittest.TestCase):
    def client(self):
        self.opener = opener_for([])
        return OxylabsClient(key=KEY, opener=self.opener, sleep=lambda s: None)

    def test_an_overlong_query_is_refused(self):
        with self.assertRaises(OxylabsError):
            self.client().search("x" * 2049)
        self.assertEqual(self.opener.calls, [])

    def test_max_results_above_twenty_is_refused(self):
        with self.assertRaises(OxylabsError):
            self.client().search("milk", max_results=21)
        self.assertEqual(self.opener.calls, [])

    def test_a_location_that_is_not_alpha_2_is_refused(self):
        with self.assertRaises(OxylabsError):
            self.client().search("milk", location="usa")
        self.assertEqual(self.opener.calls, [])

    def test_a_relative_url_is_refused(self):
        with self.assertRaises(OxylabsError):
            self.client().scrape("example.com/page")
        self.assertEqual(self.opener.calls, [])


class RetryOnlyWhereTheContractSaysSo(unittest.TestCase):
    def run_with(self, sequence):
        opener = opener_for(sequence)
        client = OxylabsClient(key=KEY, opener=opener, sleep=lambda s: None)
        return client, opener

    def test_a_401_stops_immediately(self):
        client, opener = self.run_with([http_error(401, {"title": "Unauthorized"})])
        with self.assertRaises(OxylabsError) as caught:
            client.search("milk")
        self.assertEqual(caught.exception.status, 401)
        self.assertEqual(len(opener.calls), 1, "a rejected key was retried")

    def test_a_400_stops_immediately_and_names_the_field(self):
        client, opener = self.run_with([http_error(400, {
            "title": "Validation failed",
            "errors": [{"pointer": "/max_results"}]})])
        with self.assertRaises(OxylabsError) as caught:
            client.search("milk")
        self.assertEqual(len(opener.calls), 1)
        self.assertIn("/max_results", str(caught.exception))

    def test_a_429_is_retried_then_succeeds(self):
        client, opener = self.run_with([http_error(429), {"results": [1]}])
        self.assertEqual(client.search("milk")["results"], [1])
        self.assertEqual(len(opener.calls), 2)

    def test_a_500_is_retried_up_to_the_attempt_limit(self):
        client, opener = self.run_with([http_error(500)] * ATTEMPTS)
        with self.assertRaises(OxylabsError):
            client.search("milk")
        self.assertEqual(len(opener.calls), ATTEMPTS)

    def test_a_timeout_is_retried(self):
        client, opener = self.run_with([URLError("timed out"), {"results": [1]}])
        client.search("milk")
        self.assertEqual(len(opener.calls), 2)

    def test_a_404_is_not_retried(self):
        client, opener = self.run_with([http_error(404)])
        with self.assertRaises(OxylabsError):
            client.search("milk")
        self.assertEqual(len(opener.calls), 1)

    def test_backoff_grows_and_is_jittered(self):
        waited = []
        opener = opener_for([http_error(500), http_error(500), {"results": []}])
        OxylabsClient(key=KEY, opener=opener, sleep=waited.append).search("milk")
        self.assertEqual(len(waited), 2)
        self.assertGreater(waited[1], waited[0])
        self.assertNotEqual(waited[0], int(waited[0]), "no jitter was applied")


class TheRefusedHostIsEnforcedInCode(unittest.TestCase):
    """Not left to whoever writes the next caller."""

    def client(self):
        self.opener = opener_for([])
        return OxylabsClient(key=KEY, opener=self.opener, sleep=lambda s: None)

    def test_the_retailer_is_refused_as_an_arbitrary_url(self):
        with self.assertRaises(OxylabsError) as caught:
            self.client().scrape("https://www.marianos.com/p/some-product/0001")
        self.assertIn("refuses our datacenter egress", str(caught.exception))
        self.assertEqual(self.opener.calls, [], "a request was sent anyway")

    def test_it_is_refused_whatever_the_path_or_scheme(self):
        for url in ("http://marianos.com/", "https://marianos.com/pl/dairy/01",
                    "https://WWW.MARIANOS.COM/search?q=milk"):
            with self.subTest(url=url):
                with self.assertRaises(OxylabsError):
                    self.client().scrape(url)

    def test_the_dedicated_target_for_that_retailer_is_refused_too(self):
        """This test asserted the opposite until 3 November. OPTIONS on the
        endpoint showed its outputs are html, markdown, screenshot and an
        LLM-parsed json against a caller-supplied schema: there is no vendor
        parser, so it delivers the same page as the generic route and
        allowing one while blocking the other was incoherent."""
        self.opener = opener_for([])
        client = OxylabsClient(key=KEY, opener=self.opener, sleep=lambda s: None)
        with self.assertRaises(OxylabsError) as caught:
            client.scrape_target("marianos", "product", {"query": "0001"})
        self.assertIn("refuses our datacenter egress", str(caught.exception))
        self.assertEqual(self.opener.calls, [], "a request was sent anyway")

    def test_a_dedicated_target_for_another_retailer_still_works(self):
        """The refusal is about one retailer's measured refusal of us, not
        about dedicated endpoints as a kind."""
        opener = opener_for([{"results": [{"content": {}}]}])
        client = OxylabsClient(key=KEY, opener=opener, sleep=lambda s: None)
        client.scrape_target("bestbuy", "product", {"query": "0001"})
        self.assertTrue(opener.calls[0]["url"].endswith("/v1/scrape/bestbuy/product"))

    def test_other_hosts_are_not_blocked(self):
        opener = opener_for([{"results": [{"markdown": "x" * 500}]}])
        client = OxylabsClient(key=KEY, opener=opener, sleep=lambda s: None)
        client.scrape("https://example.com/page")
        self.assertEqual(len(opener.calls), 1)


class TheThinPageLadder(unittest.TestCase):
    def test_empty_results_count_as_thin(self):
        self.assertTrue(content_is_thin({"results": []}))
        self.assertTrue(content_is_thin({}))

    def test_a_skeletal_two_hundred_char_page_counts_as_thin(self):
        self.assertTrue(content_is_thin({"results": [{"markdown": "short"}]}))

    def test_real_content_does_not(self):
        self.assertFalse(content_is_thin({"results": [{"markdown": "x" * 400}]}))

    def test_a_200_carrying_an_empty_shell_still_triggers_the_retry(self):
        """Driven by the content, not the status. This is the whole point."""
        opener = opener_for([{"results": [{"markdown": ""}]},
                             {"results": [{"markdown": "y" * 400}]}])
        client = OxylabsClient(key=KEY, opener=opener, sleep=lambda s: None)
        document, how = read_page(client, "https://example.com/p")
        self.assertEqual(how, "run_js")
        self.assertTrue(opener.calls[1]["body"]["run_js"])
        self.assertNotIn("run_js", opener.calls[0]["body"])

    def test_a_country_tld_gets_one_more_try_with_that_country(self):
        opener = opener_for([{"results": []}, {"results": []},
                             {"results": [{"markdown": "z" * 400}]}])
        client = OxylabsClient(key=KEY, opener=opener, sleep=lambda s: None)
        _, how = read_page(client, "https://example.lt/p")
        self.assertEqual(how, "run_js+LT")
        self.assertEqual(opener.calls[2]["body"]["location"], "LT")

    def test_a_brand_tld_does_not_get_a_country_retry(self):
        """.io is bought for the word, not the country."""
        self.assertIsNone(country_for("https://example.io/p"))
        opener = opener_for([{"results": []}, {"results": []}])
        client = OxylabsClient(key=KEY, opener=opener, sleep=lambda s: None)
        document, how = read_page(client, "https://example.io/p")
        self.assertIsNone(document)
        self.assertEqual(how, "unreadable")
        self.assertEqual(len(opener.calls), 2)

    def test_an_unreadable_page_is_reported_not_returned_as_content(self):
        opener = opener_for([{"results": []}, {"results": []}, {"results": []}])
        client = OxylabsClient(key=KEY, opener=opener, sleep=lambda s: None)
        document, how = read_page(client, "https://example.es/p")
        self.assertIsNone(document, "an empty page was handed back as if it were content")
        self.assertEqual(how, "unreadable")

    def test_a_good_page_is_not_retried(self):
        opener = opener_for([{"results": [{"markdown": "x" * 400}]}])
        client = OxylabsClient(key=KEY, opener=opener, sleep=lambda s: None)
        _, how = read_page(client, "https://example.com/p")
        self.assertEqual(how, "plain")
        self.assertEqual(len(opener.calls), 1)

    def test_country_for_reads_the_tld_not_the_path(self):
        self.assertEqual(country_for("https://shop.example.es/uk/page"), "ES")
        self.assertEqual(country_for("https://example.co.uk/p"), "UK")
        self.assertIsNone(country_for("https://example.com/es"))


class CapabilityIsAskedRatherThanGuessed(unittest.TestCase):
    def test_options_uses_the_options_method_and_the_bearer(self):
        opener = opener_for([{"parameters": {}}])
        client = OxylabsClient(key=KEY, opener=opener, sleep=lambda s: None)
        client.options("/v1/scrape/marianos/product")
        self.assertEqual(opener.calls[0]["method"], "OPTIONS")
        self.assertEqual(opener.calls[0]["headers"].get("Authorization"),
                         f"Bearer {KEY}")
        self.assertTrue(opener.calls[0]["url"].endswith("/v1/scrape/marianos/product"))


class TheKeyComesFromTheEnvironment(unittest.TestCase):
    def test_a_missing_key_says_so_and_sends_nothing(self):
        import os
        from unittest import mock
        from marianos_collector import oxylabs
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(OxylabsError) as caught:
                oxylabs.api_key()
        self.assertIn("Nothing was sent", str(caught.exception))

    def test_either_variable_name_works(self):
        import os
        from unittest import mock
        from marianos_collector import oxylabs
        for name in ("OXYLABS_WEB_API_KEY", "OXYLABS_API_KEY"):
            with self.subTest(name=name):
                with mock.patch.dict(os.environ, {name: "k"}, clear=True):
                    self.assertEqual(oxylabs.api_key(), "k")

    def test_the_key_is_never_an_argument_to_the_module(self):
        source = (Path(__file__).resolve().parent.parent
                  / "marianos_collector/oxylabs.py").read_text()
        self.assertIn("OXYLABS_WEB_API_KEY", source)
        self.assertNotIn("--api-key", source)


if __name__ == "__main__":
    unittest.main()
