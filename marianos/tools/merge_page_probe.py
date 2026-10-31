#!/usr/bin/env python3
"""Merge a page probe onto a spine through composition.py. No network calls.

Reads the spine and the probe; writes only to a new directory. API values stay
in place: page reads take `ppm`, and a page `regular_price` that differs from
the API's is recorded as a conflict with the API value kept. A probe that read
no page registers the source as unavailable, with its reason.

Volume and digital wording is not taken from a page here. `rendered_product`
keeps Savings text as `unresolved_offer_text`, and it stays unresolved until a
reading of that text has been checked against real pages from this store.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from marianos_collector.composition import (BINDING_KEY, Availability, CallableEnrichment,
                                            CompositeSource)
from marianos_collector.config import Category, Store
from marianos_collector.rendered_product import digest, parse_product
from marianos_collector.schema import FIELDS
from marianos_collector.sources import Page

API = 'kroger_public_api'
PAGE = 'crawl'
PAGE_FIELDS = ('ppm', 'regular_price')
POLICY = {'ppm': (PAGE,), 'regular_price': (API, PAGE)}


class Spine:
    """The delivered spine, served as one page; identity is the UPC."""
    source_mode = 'kroger_public_api_spine'

    def __init__(self, rows, store):
        self.rows = rows
        self.store = store

    def fetch(self, store, category, url, cursor):
        return Page(store_id=store.store_id, zipcode=store.zipcode, store_context_verified=True,
                    source_url=url, products=[dict(r) for r in self.rows], children=[],
                    next_cursor='', subcategories_complete=True)


def read_pages(probe):
    """{upc: (row, audit, evidence)} and a line for each page that would not parse."""
    store = json.loads((probe / 'store.json').read_text(encoding='utf-8'))
    proof_file = probe / 'CURRENT_STORE.json'
    pages, unparsed = {}, []
    if not proof_file.exists():
        return pages, unparsed
    proof = json.loads(proof_file.read_text(encoding='utf-8'))
    for path in sorted(probe.glob('PDP_*.json')):
        evidence = json.loads(path.read_text(encoding='utf-8'))
        try:
            row, audit = parse_product(evidence, store, proof)
        except ValueError as exc:
            unparsed.append({'file': path.name, 'reason': str(exc)})
            continue
        pages[row['upc']] = (row, audit, evidence)
    return pages, unparsed


def page_source(pages, reason):
    def lookup(store, identity, product):
        if identity not in pages:
            return {}
        row, audit, evidence = pages[identity]
        return {**{f: row[f] for f in PAGE_FIELDS if row[f]},
                BINDING_KEY: {'identity': identity, 'store_id': store.store_id,
                              'fulfillment': 'pickup', 'observed_at': evidence['observed_at'],
                              'evidence_sha256': digest(evidence)}}
    availability = (lambda: Availability.blocked(reason)) if not pages else None
    return CallableEnrichment(PAGE, PAGE_FIELDS, lookup, availability=availability)


def merge(rows, pages, store, reason):
    composite = CompositeSource(Spine(rows, store), API, [page_source(pages, reason)], policy=POLICY)
    page = composite.fetch(store, Category(name='spine', url=''), '', '')
    products = [{f: p.get(f, '') for f in FIELDS} for p in page.products]
    evidence = {r['upc']: composite.evidence_for(r['upc']) for r in rows}
    return products, evidence, composite.provenance_report()


def stop_reason(run):
    stopped = run.get('stopped') or {}
    return (f"{stopped.get('stage')}: {stopped.get('sign')} at {stopped.get('at')}; "
            f"{run.get('pages_served')} pages served" if stopped
            else f"{run.get('pages_served')} pages served; none usable")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--spine', type=Path, required=True)
    p.add_argument('--probe', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    source = args.spine / 'data_22_fields.json'
    rows = json.loads(source.read_text(encoding='utf-8'))
    run = json.loads((args.probe / 'probe_run.json').read_text(encoding='utf-8'))
    first = rows[0]
    store = Store(store_id='53100502', zipcode=first['zipcode'],
                  store_name=first['store_name'], store_location=first['store_location'])
    pages, unparsed = read_pages(args.probe)
    products, evidence, report = merge(rows, pages, store, stop_reason(run))
    args.output.mkdir(parents=True, exist_ok=False)
    report.update(spine_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                  products=len(products), pages_merged=len(pages), pages_unparsed=unparsed,
                  values_changed_from_spine=sum(a != b for a, b in zip(rows, products)))
    write = lambda name, value: (args.output / name).write_text(
        json.dumps(value, indent=1, ensure_ascii=False), encoding='utf-8')
    write('data_22_fields.json', products)
    write('field_provenance.json', evidence)
    write('composition_report.json', report)
    print(json.dumps({k: report[k] for k in ('products', 'pages_merged', 'conflict_count',
          'enrichments_unavailable', 'values_changed_from_spine', 'values_by_field_and_source')}))


if __name__ == '__main__':
    main()
