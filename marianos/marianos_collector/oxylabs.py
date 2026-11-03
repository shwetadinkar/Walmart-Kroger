"""Oxylabs Web API client, built to the contract at developers.oxylabs.io.

Shaped like `kroger.py` on purpose: one error type, credentials from the
environment only, an injectable opener so tests never touch the network, and
retry rules that live in one place.

**What this will and will not be pointed at.** `/v1/scrape` takes an arbitrary
URL. Pointed at `marianos.com` it would very likely return the displayed price
per measure and the retailer's deal wording, which is the gap this whole
engagement keeps reporting. It is not used that way here. Our datacenter egress
is refused by that retailer, measured from two Azure regions, a second cloud
provider and a plain `curl` of the sitemap; paying a vendor to fetch the page
our egress cannot reach is the thing `CLAUDE.md` refuses by any name, and a new
product name is not a new act. `REFUSED_HOSTS` enforces it in code rather than
leaving it to whoever writes the next caller.

The dedicated target `/v1/scrape/marianos/product` was argued to be a
different matter: a maintained, parsed, retailer-specific interface rather
than page fetching. **That was checked on 3 November and it is false.**
`OPTIONS` on the endpoint returns an output enum of `html`, `markdown`,
`screenshot`, `json`, where `json` is parsed by an LLM against a schema or
prompt the caller supplies. There is no vendor-maintained product parser. The
target resolves a query and accepts store context, and then returns the same
page bytes the generic route would. So it is refused too, by `REFUSED_TARGETS`,
and allowing one while blocking the other would have been incoherent.

Checklist from the vendor's agent page, each enforced here:
key from the environment and never logged; Bearer on every request; a 150
second timeout; any 2xx is success; `query` under 2048 characters; `location`
an ISO 3166-1 alpha-2 code; retries only on timeouts and 408/429/5xx with
exponential backoff and jitter, three attempts; 400 and 401 surfaced and never
retried; `max_results` at most 20; `metadata.request_id` captured for every
call.
"""

from __future__ import annotations

import json
import os
import random
import re
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

BASE = "https://webapi.oxylabs.io"
TIMEOUT = 150
ATTEMPTS = 3
RETRY_STATUS = (408, 429, 500, 502, 503, 504)
MAX_RESULTS_CEILING = 20
MAX_QUERY = 2048
ALPHA2 = re.compile(r"^[A-Z]{2}$")

# Hosts this client will not fetch as an arbitrary URL. Not a blocklist of
# "sites we dislike": it is the one retailer whose refusal of our egress is
# measured and recorded, so that routing round it through a vendor cannot
# happen by someone passing a URL without thinking about it. A dedicated
# target for the same retailer is reached through scrape_target(), which is a
# different interface and not covered by this.
REFUSED_HOSTS = ("marianos.com", "www.marianos.com")

# Dedicated targets for the same retailer. Added after OPTIONS showed the
# endpoint has no vendor parser, so it delivers the page rather than a product
# record and is the same act as fetching the URL.
REFUSED_TARGETS = ("marianos", "kroger")
REFUSAL = (
    "This client will not fetch {host}. That retailer refuses our datacenter "
    "egress, measured on 30 October and 2 November, and having a vendor fetch "
    "the page we cannot reach is the route CLAUDE.md refuses by any name. The "
    "dedicated target is not an exception: OPTIONS on it shows html, markdown, "
    "screenshot and an LLM-parsed json against a caller-supplied schema, so "
    "there is no vendor parser and it delivers the same page. Whether to "
    "collect this retailer through a third party is the client's decision with "
    "his own counsel, not something to arrive at here because it was the only "
    "box left.")

# Country-code TLDs worth one retry with a matching location. Brand-use TLDs
# are skipped because .io or .ai says nothing about where a site is served.
BRAND_TLDS = {"io", "ai", "co", "me", "tv", "fm", "ly"}


class OxylabsError(RuntimeError):
    """Anything that stops a call. Carries the status when there was one."""

    def __init__(self, message, status=None, title="", request_id=""):
        super().__init__(message)
        self.status = status
        self.title = title
        self.request_id = request_id


def api_key() -> str:
    """From the environment only. Never an argument, never logged."""
    key = (os.getenv("OXYLABS_WEB_API_KEY") or os.getenv("OXYLABS_API_KEY") or "").strip()
    if not key:
        raise OxylabsError(
            "OXYLABS_WEB_API_KEY is required in the environment. Credentials stay "
            "with their owner: export it in the shell that runs this, never pass "
            "it as an argument. Nothing was sent.")
    return key


def _problem(payload: bytes):
    """RFC 9457 problem body. Branch on `title`, never on `detail`."""
    try:
        body = json.loads(payload.decode(errors="replace"))
    except Exception:                               # noqa: BLE001
        return "", "", []
    if not isinstance(body, dict):
        return "", "", []
    return (str(body.get("title") or ""), str(body.get("detail") or "")[:500],
            body.get("errors") or [])


class OxylabsClient:
    def __init__(self, key=None, opener=None, base=BASE, sleep=time.sleep):
        self._key = key or api_key()
        self.opener = opener or urlopen
        self.base = base.rstrip("/")
        self.sleep = sleep
        self.request_ids = []          # metadata.request_id per call, for reporting

    # The key is held here and put only into a header. It is never returned,
    # never formatted into a message, and never part of a repr.
    def __repr__(self):
        return f"<OxylabsClient base={self.base!r}>"

    def _post(self, path, body):
        request = Request(
            f"{self.base}{path}", data=json.dumps(body).encode(), method="POST",
            headers={"Content-Type": "application/json",
                     "Authorization": f"Bearer {self._key}"})
        return self._read(request)

    def _get(self, path):
        request = Request(f"{self.base}{path}", method="GET",
                          headers={"Authorization": f"Bearer {self._key}"})
        return self._read(request)

    def _read(self, request):
        for attempt in range(ATTEMPTS):
            try:
                with self.opener(request, timeout=TIMEOUT) as response:
                    status = getattr(response, "status", 200)
                    payload = response.read()
                if not 200 <= status < 300:
                    raise OxylabsError(f"Oxylabs HTTP {status}", status=status)
                parsed = json.loads(payload.decode())
                if not isinstance(parsed, dict):
                    raise OxylabsError("Unexpected Oxylabs JSON shape")
                rid = ((parsed.get("metadata") or {}).get("request_id")
                       if isinstance(parsed.get("metadata"), dict) else "")
                if rid:
                    self.request_ids.append(rid)
                return parsed
            except HTTPError as exc:
                title, detail, errors = _problem(exc.read())
                if exc.code == 401:
                    raise OxylabsError(
                        "Oxylabs HTTP 401: the key was rejected. It may belong to a "
                        "different Oxylabs product. Stopping rather than retrying.",
                        status=401, title=title) from exc
                if exc.code == 400:
                    where = ", ".join(
                        str(e.get("pointer", "")) for e in errors if isinstance(e, dict))
                    raise OxylabsError(
                        f"Oxylabs HTTP 400 validation failed{': ' + where if where else ''}"
                        f"{' - ' + detail if detail else ''}. Not retried.",
                        status=400, title=title) from exc
                if exc.code not in RETRY_STATUS or attempt == ATTEMPTS - 1:
                    raise OxylabsError(f"Oxylabs HTTP {exc.code}"
                                       f"{': ' + title if title else ''}",
                                       status=exc.code, title=title) from exc
            except (TimeoutError, URLError, OSError) as exc:
                if attempt == ATTEMPTS - 1:
                    raise OxylabsError(f"Oxylabs unreachable: {type(exc).__name__}") from exc
            except OxylabsError:
                raise
            # Exponential backoff with jitter, so a retry storm does not
            # synchronise across callers.
            self.sleep((2 ** attempt) + random.random())
        raise OxylabsError("Oxylabs retries exhausted")

    def options(self, path):
        """The typed parameters an endpoint accepts, which is how a capability
        is found without guessing a body and spending a request on a 400."""
        request = Request(f"{self.base}{path}", method="OPTIONS",
                          headers={"Authorization": f"Bearer {self._key}"})
        return self._read(request)

    def scrapers(self):
        """What this account can actually call. One request, and it is the
        thing that settles whether a dedicated Mariano's target exists here
        rather than being inferred from a documentation page."""
        return self._get("/v1/scrapers")

    def search(self, query, max_results=10, location=None):
        query = (query or "").strip()
        if not 1 <= len(query) <= MAX_QUERY:
            raise OxylabsError(f"query must be 1 to {MAX_QUERY} characters")
        if not 1 <= int(max_results) <= MAX_RESULTS_CEILING:
            raise OxylabsError(f"max_results must be 1 to {MAX_RESULTS_CEILING}")
        body = {"query": query, "max_results": int(max_results)}
        if location:
            if not ALPHA2.match(location):
                raise OxylabsError("location must be an ISO 3166-1 alpha-2 code")
            body["location"] = location
        return self._post("/v1/search", body)

    def scrape(self, url, output=("markdown",), location=None, device=None,
               run_js=False):
        host = (urlparse(url).hostname or "").lower()
        if host in REFUSED_HOSTS:
            raise OxylabsError(REFUSAL.format(host=host))
        if not url.lower().startswith(("http://", "https://")):
            raise OxylabsError("url must be absolute http or https")
        body = {"url": url, "output": list(output)}
        if run_js:
            body["run_js"] = True
        if location:
            if not ALPHA2.match(location):
                raise OxylabsError("location must be an ISO 3166-1 alpha-2 code")
            body["location"] = location
        if device:
            body["device"] = device
        return self._post("/v1/scrape", body)

    def scrape_target(self, target, kind, body):
        """A dedicated endpoint, e.g. /v1/scrape/<target>/product.

        This was written believing a dedicated target was a parsed,
        vendor-maintained interface and so a different act from fetching a
        URL. OPTIONS on the Marianos endpoint showed otherwise: the outputs
        are html, markdown, screenshot and an LLM-parsed json against a schema
        the caller supplies. No vendor parser exists, so for the retailer that
        refuses our egress this delivers the same page the generic route
        would, and REFUSED_TARGETS refuses it on the same ground.

        Other targets are unaffected: the refusal is about one retailer's
        measured refusal of us, not about dedicated endpoints as a kind.
        """
        if str(target).lower() in REFUSED_TARGETS:
            raise OxylabsError(REFUSAL.format(host=f"the {target} target"))
        return self._post(f"/v1/scrape/{target}/{kind}", dict(body))


def content_is_thin(document, floor=200):
    """Whether a scrape came back empty or skeletal, so it is worth one retry
    with JavaScript. Measured on the returned content, not on the status: a
    200 carrying an empty shell is the case this exists for."""
    results = document.get("results") if isinstance(document, dict) else None
    if not results:
        return True
    text = ""
    for item in results if isinstance(results, list) else [results]:
        if isinstance(item, dict):
            for key in ("markdown", "content", "html", "text"):
                value = item.get(key)
                if isinstance(value, str):
                    text += value
    return len(text.strip()) < floor


def country_for(url):
    """The country to retry with for a country-code TLD, or None.

    Brand-use TLDs are skipped: .io, .ai and .co are bought for the word, not
    the country, and asking for a Lithuanian exit on a .io would be noise.
    """
    host = (urlparse(url).hostname or "").lower()
    tld = host.rsplit(".", 1)[-1] if "." in host else ""
    if len(tld) != 2 or tld in BRAND_TLDS:
        return None
    return tld.upper()


def read_page(client, url, log=None):
    """Scrape with the retry ladder the vendor's page specifies.

    Plain, then once with JavaScript, then once more with a country location
    if the host sits on a country-code TLD. Still thin after that and the page
    is reported unreadable rather than returned as if it were content.
    """
    say = log or (lambda *a: None)
    document = client.scrape(url)
    if not content_is_thin(document):
        return document, "plain"
    say(f"thin, retrying with run_js: {url}")
    document = client.scrape(url, run_js=True)
    if not content_is_thin(document):
        return document, "run_js"
    country = country_for(url)
    if country:
        say(f"still thin, retrying with run_js and location={country}: {url}")
        document = client.scrape(url, run_js=True, location=country)
        if not content_is_thin(document):
            return document, f"run_js+{country}"
    return None, "unreadable"
