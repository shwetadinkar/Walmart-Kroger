#!/usr/bin/env python3
"""Run the bounded Vernon Hills page probe. Output must be a new directory.

An ordinary isolated browser with no saved session and no proxy. `--plan` selects
and prints the products without touching the network.
"""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from marianos_collector.page_probe import Capture, run_probe, select_products

STORE = {'id': '53100502', 'name': 'Marianos Vernon Hills',
         'street': '1720 N Milwaukee Ave', 'zipcode': '60061'}
START_URL = 'https://www.marianos.com/'


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--spine', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--target', type=int, default=25)
    p.add_argument('--plan', action='store_true')
    args = p.parse_args()
    read = lambda name: json.loads((args.spine / name).read_text(encoding='utf-8'))
    context = {c['product_id']: c for c in read('pickup_context.json').values()}
    targets = select_products(read('data_22_fields.json'), context, args.target)
    if args.plan:
        print(json.dumps(targets, indent=1, ensure_ascii=False))
        return
    from playwright.sync_api import sync_playwright
    capture = Capture(args.output)
    capture.json('selection.json', targets)
    capture.json('store.json', STORE)
    with sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        try:
            page = browser.new_context(locale='en-US').new_page()
            page.set_default_timeout(15000)
            result = run_probe(page, targets, STORE, START_URL, capture)
            result['browser'] = {'engine': 'chromium', 'version': browser.version,
                                 'headless': True, 'saved_session': False, 'proxy': False}
            capture.json('probe_run.json', result)
        finally:
            browser.close()
    capture.json('MANIFEST_SHA256.json', capture.hashes)
    print(json.dumps({k: result[k] for k in ('pages_requested', 'pages_served', 'outcomes',
                                             'elapsed_seconds', 'stopped')}))


if __name__ == '__main__':
    main()
