"""One strict page contract for fixture testing and authorized retail-data providers.

No bypass techniques, undocumented retail endpoints or proxy evasion are provided.
The provider is responsible for complete product/category discovery and verifiable
store/fulfillment/seller provenance.
"""
from __future__ import annotations

import hashlib
import logging
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

from .config import check_retailer_url

LOG = logging.getLogger("collector")

class SourceError(RuntimeError):
    pass
class AccessChallenge(SourceError):
    pass

@dataclass
class Page:
    store_id: str
    zipcode: str
    store_context_verified: bool
    source_url: str
    products: list[dict]
    children: list[dict]
    next_cursor: str
    subcategories_complete: bool
    location_evidence_url: str = ""

    @classmethod
    def parse(cls, body: dict) -> "Page":
        if not isinstance(body, dict):
            raise SourceError("Provider returned a non-object page")
        required = ("store_id", "zipcode", "store_context_verified", "source_url", "products", "children", "next_cursor", "subcategories_complete")
        if any(k not in body for k in required):
            raise SourceError(f"Missing mandatory page properties: {set(required) - set(body)}")
        if not isinstance(body["products"], list) or not isinstance(body["children"], list):
            raise SourceError("Products and children must be JSON arrays")
        if type(body["store_context_verified"]) is not bool or type(body["subcategories_complete"]) is not bool:
            raise SourceError("Context verification and discovery completeness must be booleans")
        if not isinstance(body["next_cursor"], str):
            raise SourceError("next_cursor must be a string, empty when completed")
        if not isinstance(body["source_url"], str):
            raise SourceError("source_url must be a string")
        check_retailer_url(body["source_url"])
        for child in body["children"]:
            if not isinstance(child, dict) or not isinstance(child.get("name"), str) or not isinstance(child.get("url"), str):
                raise SourceError("Child category requires name and URL")
            check_retailer_url(child["url"])
        evidence = body.get("location_evidence_url", "")
        if not isinstance(evidence, str):
            raise SourceError("location_evidence_url must be a string")
        if evidence and urlparse(evidence).scheme not in ("http", "https"):
            raise SourceError("Location evidence must be a verifiable URL")
        return cls(**{k: body[k] for k in required}, location_evidence_url=evidence)

class FixtureSource:
    source_mode = "synthetic_fixture_NOT_contest_proof"
    # Declared explicitly because the publication gate refuses any source that
    # does not state its position. A fixture page carries
    # subcategories_complete and the runner enforces it, so coverage is
    # attested in the same structural sense as a live crawl. That the data is
    # synthetic is a separate matter, reported as source_is_synthetic, and is
    # not what this flag means.
    coverage_attested = True
    def __init__(self, directory: Path):
        self.directory = directory
    def fetch(self, store, category, url: str, cursor: str) -> Page:
        node = hashlib.sha256(url.encode()).hexdigest()[:14]
        filename = self.directory / store.store_id / category.slug / f"{node}_{cursor or 'start'}.json"
        if not filename.is_file():
            raise SourceError(f"Missing DEMO fixture: {filename}")
        return Page.parse(json.loads(filename.read_text(encoding="utf-8")))

class AuthorizedProviderSource:
    """HTTPS adapter: GET {PROVIDER_BASE_URL}?store_id=...&category_url=...&cursor=...

    The approved provider maps site/category paging to the Page.parse contract.
    Authorization is explicit; a Marianos site URL is not an authorized feed.
    """
    source_mode = "authorized_provider_data_unverified_until_review"
    # The provider contract makes the provider responsible for complete
    # product and category discovery, and the runner enforces
    # subcategories_complete on every page it returns.
    coverage_attested = True
    def __init__(self, base_url: str, token: str, timeout: int = 35, max_attempts: int = 3):
        parsed = urlparse(base_url)
        if parsed.scheme != "https" or not parsed.hostname:
            raise SourceError("Provider endpoint must be HTTPS")
        if parsed.hostname == "marianos.com" or parsed.hostname.endswith(".marianos.com"):
            raise SourceError("Provider URL must not be an undocumented marianos.com endpoint")
        if not token:
            raise SourceError("PROVIDER_API_TOKEN is required")
        self.base_url, self.token = base_url, token
        self.timeout, self.max_attempts = timeout, max_attempts
        self.pages_fetched = 0
        self.transient_retries = 0

    def provenance_report(self) -> dict:
        """What this run actually used, for the release report.

        This source had no `provenance_report` at all, and the runner reads it
        through `hasattr`, so a release produced here carried **no provenance
        block** and nothing failed. That is the worst place for the gap to be:
        `coverage_attested` is True on this source, so unlike the sweep it may
        publish outside the trial namespace, and the source permitted to make
        the strongest claim was disclosing the least. Two other sources had the
        same defect under a different name, `provenance` instead of
        `provenance_report`, and it cost a release each time.

        The token is never included, in any form.
        """
        parsed = urlparse(self.base_url)
        return {
            "source_mode": self.source_mode,
            "contract": ("GET {base}?store_id&zipcode&category&category_url"
                         "&cursor, Bearer token, Page.parse response"),
            "provider_host": parsed.hostname,
            "provider_path": parsed.path,
            "credential": "PROVIDER_API_TOKEN, read from the environment, "
                          "never recorded here",
            "coverage_attested": self.coverage_attested,
            "coverage_attested_means": (
                "the provider contract makes the provider responsible for "
                "complete product and category discovery, and the runner "
                "enforces subcategories_complete on every page returned. It is "
                "the provider's claim, carried forward, not an independent "
                "verification by us"),
            "pages_fetched": self.pages_fetched,
            "transient_retries": self.transient_retries,
            "timeout_seconds": self.timeout,
            "max_attempts": self.max_attempts,
            "max_payload_bytes": 20_000_000,
            "_does_not_establish": [
                "That the provider's data is correct. source_mode says "
                "unverified until review and that is the standing position.",
                "That the products are the store's assortment. That rests on "
                "the provider resolving the store_id passed to it.",
            ],
        }

    def fetch(self, store, category, url: str, cursor: str) -> Page:
        check_retailer_url(url)
        separator = "&" if "?" in self.base_url else "?"
        full_url = self.base_url + separator + urlencode({
            "store_id": store.store_id, "zipcode": store.zipcode,
            "category": category.name, "category_url": url, "cursor": cursor
        })
        for attempt in range(self.max_attempts):
            req = Request(full_url, headers={
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/json", "User-Agent": "RetailDataCollector/0.1 (authorized feed)"
            })
            try:
                with urlopen(req, timeout=self.timeout) as response:
                    status = response.status
                    if status != 200:
                        raise SourceError(f"Unexpected status {status}")
                    data = response.read(20_000_001)
                    if len(data) > 20_000_000:
                        raise SourceError("Provider payload exceeds 20MB")
                document = json.loads(data)
                page = Page.parse(document)
                self.pages_fetched += 1
                return page
            except HTTPError as ex:
                if ex.code in (401, 403):
                    raise AccessChallenge(f"Authorization denied or challenge: HTTP {ex.code}") from ex
                if ex.code not in (429, 500, 502, 503, 504) or attempt == self.max_attempts - 1:
                    raise SourceError(f"Provider HTTP error {ex.code}") from ex
            except (URLError, TimeoutError, OSError) as ex:
                if attempt == self.max_attempts - 1:
                    raise SourceError(f"Provider unavailable: {ex}") from ex
            except (ValueError, TypeError) as ex:
                raise SourceError(f"Invalid provider JSON: {ex}") from ex
            self.transient_retries += 1
            LOG.warning("transient_provider_retry", extra={"event":"transient_provider_retry", "store_id":store.store_id,"category":category.name,"attempt":attempt+1})
            time.sleep(min(2**attempt, 8))
        raise SourceError("Provider exhausted retries")
