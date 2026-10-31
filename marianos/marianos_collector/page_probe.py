"""A bounded, paced read of product pages at one proved store.

Measures the source as much as it reads it: how many pages are served before
the site refuses, what the refusal looks like, and how long the batch took. The
first sign of refusal ends the run. No page is requested twice, and nothing
here changes identity, routes around a refusal, or answers a challenge.

Everything is written as it happens, so a killed run keeps what it observed.
"""
import hashlib
import json
import re
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from .browser_session import (AccessBlocked, prepare_store, refusal_sign,
                              safe_browser_error_code)

MAXIMUM_PAGES = 30
SITE_HOST = 'www.marianos.com'
PAGE_PACE_SECONDS = 30
# What a page shows at once measure is displayed, without promising it will.
MEASURED_SIZE = re.compile(r'\b(?:fl oz|oz|ct|lb|gal|qt|pt|l|ml|g|kg)\b', re.I)


def _rank(row):
    """Sale first, a measured size next, then a stable hash so that the order is
    reproducible and not the order in which search terms happened to run."""
    return (0 if row['sale_price'] else 1,
            0 if MEASURED_SIZE.search(row['weight']) else 1,
            hashlib.sha256(row['upc'].encode()).hexdigest())


def select_products(rows, context_by_upc, target=25):
    """One product per root, then a second pass over the largest roots.

    Only products with a qualifying pickup offer are eligible: a page price can
    then be compared with an API price for the same offer. This selects what to
    read; it deletes nothing from anything.
    """
    if not 1 <= target <= MAXIMUM_PAGES:
        raise ValueError('PROBE_TARGET_OUTSIDE_BOUND')
    by_root = {}
    for row in rows:
        context = context_by_upc.get(row['upc'], {})
        if (row['category'] and row['url'] and row['regular_price']
                and context.get('offer_status') == 'qualifying_pickup_offer'):
            by_root.setdefault(row['category'], []).append(row)
    for candidates in by_root.values():
        candidates.sort(key=_rank)
    roots = sorted(by_root, key=lambda name: (-len(by_root[name]), name))
    selected, depth = [], 0
    while len(selected) < target and any(len(by_root[r]) > depth for r in roots):
        for root in roots:
            if len(selected) < target and len(by_root[root]) > depth:
                selected.append(by_root[root][depth])
        depth += 1
    return [{'upc': r['upc'], 'category': r['category'], 'url': r['url'],
             'page_url': r['url'] + '?fulfillment=PICKUP', 'title': r['product_title'],
             'selected_because': {'api_sale_price': bool(r['sale_price']),
                                  'measured_size': bool(MEASURED_SIZE.search(r['weight']))}}
            for r in selected]


def _sha256(data):
    return hashlib.sha256(data).hexdigest()


class Capture:
    """Files under one new directory, each hashed as it lands."""

    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=False)
        self.hashes = {}

    def bytes(self, name, data):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        self.hashes[name] = _sha256(data)
        return name

    def json(self, name, value):
        return self.bytes(name, json.dumps(value, indent=1, ensure_ascii=False).encode())


class Measurements:
    """Status of first-party subresources, because a site can refuse its own
    data calls while still serving the document around them."""

    def __init__(self):
        self.refused = []

    def on_response(self, response):
        if urlsplit(response.url).hostname == SITE_HOST and response.status in (403, 429):
            self.refused.append({'status': response.status,
                                 'path': urlsplit(response.url).path})

    def take(self):
        taken, self.refused = self.refused, []
        return taken


def _now():
    return datetime.now(timezone.utc).isoformat()


def _body(page):
    try:
        return page.locator('body').inner_text(timeout=5000)
    except Exception:
        return ''


def _page_bytes(capture, stem, page, response):
    """Everything the page gave, as served and as rendered. A failed part is
    recorded as absent; it does not end the read."""
    saved = {}
    parts = [('served.html', lambda: response.body()),
             ('rendered.html', lambda: page.content().encode()),
             ('aria.txt', lambda: page.locator('body').aria_snapshot().encode()),
             ('page.png', lambda: page.screenshot(full_page=True))]
    for suffix, read in parts:
        try:
            saved[suffix] = capture.bytes(f'pages/{stem}.{suffix}', read())
        except Exception as exc:
            saved[suffix] = ''
            saved[suffix + '_error'] = safe_browser_error_code(exc)
    return saved


def read_product(page, target, capture, measurements, store, settle_ms=15000):
    """One navigation, one attempt. Returns the observation and any refusal."""
    observation = {'upc': target['upc'], 'category': target['category'],
                   'url': target['page_url'], 'requested_at': _now()}
    started = time.monotonic()
    try:
        response = page.goto(target['page_url'], wait_until='domcontentloaded')
    except Exception as exc:
        code = safe_browser_error_code(exc)
        observation.update(outcome='refused', refusal=code, status=None,
                           seconds=round(time.monotonic() - started, 3))
        return observation, code
    try:
        page.wait_for_function(
            "u => document.body && document.body.innerText.includes('UPC: ' + u)",
            arg=target['upc'], timeout=settle_ms)
    except Exception:
        observation['upc_not_displayed_within_ms'] = settle_ms
    text = _body(page)
    observation.update(
        status=response.status if response is not None else None,
        final_url=page.url, observed_at=_now(),
        seconds=round(time.monotonic() - started, 3),
        files=_page_bytes(capture, target['upc'], page, response) if response is not None else {},
        text_file=capture.bytes(f"pages/{target['upc']}.text.txt", text.encode()),
        subresources_refused=measurements.take())
    sign = refusal_sign(response, text)
    if not sign and urlsplit(page.url).hostname != SITE_HOST:
        sign = 'LEFT_SITE'
    if not sign and observation['subresources_refused']:
        sign = 'SUBRESOURCE_' + str(observation['subresources_refused'][0]['status'])
    if not sign and response is not None and response.status == 404:
        observation['outcome'] = 'not_found'
        return observation, ''
    if not sign and not (store['name'] in text and store['street'] in text):
        # A site that silently drops the selected store has changed what it is
        # serving; and a price without a store is not evidence about the store.
        sign = 'STORE_CONTEXT_LOST'
    if sign:
        observation.update(outcome='refused', refusal=sign)
        return observation, sign
    observation['outcome'] = 'served'
    capture.json(f"PDP_{target['upc']}.json", {
        'observed_at': observation['observed_at'], 'url': target['page_url'], 'text': text})
    return observation, ''


def run_probe(page, targets, store, start_url, capture, pace_seconds=PAGE_PACE_SECONDS,
              sleep=time.sleep, monotonic=time.monotonic):
    """Store selection, then each target once, pace_seconds apart, until refused."""
    if len(targets) > MAXIMUM_PAGES:
        raise ValueError('PROBE_TARGET_OUTSIDE_BOUND')
    if len({t['upc'] for t in targets}) != len(targets):
        raise ValueError('PROBE_DUPLICATE_TARGET')
    measurements = Measurements()
    page.on('response', measurements.on_response)
    result = {'started_at': _now(), 'pace_seconds': pace_seconds, 'pages_planned': len(targets),
              'observations': [], 'store_selected': False, 'stopped': None}
    began = monotonic()

    def finish():
        observations = result['observations']
        result.update(finished_at=_now(), elapsed_seconds=round(monotonic() - began, 3),
                      pages_requested=len(observations),
                      pages_served=sum(o['outcome'] == 'served' for o in observations),
                      outcomes=dict(Counter(o['outcome'] for o in observations)))
        capture.json('probe_run.json', result)
        return result

    try:
        proof = prepare_store(page, store, start_url)
        early = measurements.take()
        if early:
            raise AccessBlocked('SUBRESOURCE_' + str(early[0]['status']))
    except Exception as exc:
        blocked = isinstance(exc, AccessBlocked)
        sign = (str(exc) if blocked or isinstance(exc, ValueError)
                else safe_browser_error_code(exc))
        # A transport failure carries no status, so it cannot be called a
        # refusal, and it is not a defect here either. It stops the run the same.
        kind = ('refused' if blocked else
                'transport_failure_unattributed' if sign.startswith('net::') else 'failed')
        result['stopped'] = {'stage': 'store_selection', 'kind': kind, 'sign': sign, 'at': _now(),
                             'after_pages_served': 0,
                             'url': urlsplit(page.url).path if page.url else ''}
        text = _body(page)
        capture.bytes('setup_failure.text.txt', text.encode())
        try:
            capture.bytes('setup_failure.rendered.html', page.content().encode())
            capture.bytes('setup_failure.png', page.screenshot(full_page=True))
        except Exception:
            pass
        return finish()
    result['store_selected'] = True
    capture.json('CURRENT_STORE.json', proof)

    for index, target in enumerate(targets):
        if index:
            sleep(pace_seconds)
        observation, sign = read_product(page, target, capture, measurements, store)
        result['observations'].append(observation)
        capture.json('probe_run.json', result)
        if sign:
            result['stopped'] = {
                'stage': 'product_page', 'kind': 'refused', 'sign': sign, 'at': _now(),
                'ordinal': index + 1, 'upc': target['upc'], 'url': target['page_url'],
                'after_pages_served': sum(o['outcome'] == 'served' for o in result['observations'])}
            break
    return finish()
