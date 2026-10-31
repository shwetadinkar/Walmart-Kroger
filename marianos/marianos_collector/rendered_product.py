"""Interpret saved rendered product text; performs no network or session access.

This is a bounded evidence adapter, not an unattended browser implementation or
an attestation of complete category/variant/promotion discovery.
"""
import hashlib
import json
import re
from urllib.parse import urlsplit
from .retention import stable_identity, stamp, observation, reconcile
from .schema import FIELDS


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def parse_product(evidence, store, store_proof):
    observed = stamp(evidence['observed_at'])
    if abs((observed - stamp(store_proof['observed_at'])).total_seconds()) > 3600:
        raise ValueError('STORE_PROOF_OUTSIDE_OBSERVATION_WINDOW')
    verified = [d for d in store_proof['dialogs']
                if all(s in d['text'] for s in (store['name'], store['street'], store['zipcode']))
                and any(r.get('checked') is True and r.get('value') == store['id'] for r in d['radios'])]
    if len(verified) != 1:
        raise ValueError('EXACT_SELECTED_STORE_REQUIRED')
    addresses = [line.strip() for line in verified[0]['text'].splitlines()
                 if store['street'] in line and store['zipcode'] in line]
    if len(addresses) != 1:
        raise ValueError('EXACT_STORE_ADDRESS_REQUIRED')
    text = evidence['text']
    if not all(s in text for s in (store['name'], store['street'])):
        raise ValueError('PRODUCT_STORE_CONTEXT_MISSING')
    if re.search(r'access denied|verify you are human|captcha|unusual traffic', text, re.I):
        raise ValueError('RENDERED_ACCESS_BLOCKED')
    url = evidence['url']
    identity = stable_identity({'url': url}, store['id'])
    path_id = urlsplit(url).path.rstrip('/').rsplit('/', 1)[-1]
    # Only the primary product, never recommendation cards or their offers.
    product = re.split(r'\n(?:Discover More Options|Product Information|Ratings & Reviews)\b', text)[0]
    crumbs = product.split('Breadcrumbs\nHome\n', 1)
    if len(crumbs) != 2 or '\nSkip Carousel' not in crumbs[1]:
        raise ValueError('PRODUCT_BREADCRUMBS_UNVERIFIED')
    trail = crumbs[1].split('\nSkip Carousel', 1)[0].splitlines()
    if len(trail) < 3 or any(not x.strip() for x in trail):
        raise ValueError('PRODUCT_BREADCRUMBS_UNVERIFIED')
    title = trail[-1]
    upcs = re.findall(r'^UPC:\s*(\d+)\s*$', product, re.M)
    if len(upcs) > 1 or (upcs and upcs[0] != path_id):
        raise ValueError('DISPLAYED_UPC_IDENTITY_MISMATCH')
    after_title = product.split('\nSkip Carousel', 1)[1]
    option = re.search(r'^Option\s*:\s*([^\n]+)', after_title, re.M)
    size = re.search(r'^Size\s*:\s*([^\n]+)', after_title, re.M)
    if not size:
        raise ValueError('SELECTED_SIZE_UNVERIFIED')
    # Prices precede the selected variant controls. Repeated identical accessible
    # prices are one quote; distinct unexplained prices are quarantined, not guessed.
    price_region = re.split(r'\n(?:Option\s*:|Size\s*:|Item Availability)', after_title, maxsplit=1)[0]
    prices = set(re.findall(r'^\$(\d+\.\d{2})\s*$', price_region, re.M))
    ppms = set(re.findall(r'^\$\d[\d,.]*/(?:fl oz|oz|lb|ct|each|gal|qt|pt|100 ct|100 g|g|kg|l|L)\s*$', price_region, re.M))
    discrepancies = []
    regular = next(iter(prices)) if len(prices) == 1 else ''
    if len(prices) > 1: discrepancies.append('AMBIGUOUS_DISPLAYED_PRICE')
    if len(ppms) > 1: discrepancies.append('AMBIGUOUS_DISPLAYED_PPM')
    availability = re.search(r'Item Availability\s*\nPickup\s*\n(Available|Unavailable|Out of Stock)\b', product)
    state = ('available' if availability.group(1) == 'Available' else 'unavailable') if availability else 'unknown'
    row = dict.fromkeys(FIELDS, '')
    row.update(zipcode=store['zipcode'], store_name=store['name'],
               store_location=addresses[0], category=trail[0],
               sub_category=trail[-2], product_title=title, weight=size.group(1).strip(),
               regular_price=regular, url=url, upc=upcs[0] if upcs else '',
               ppm=next(iter(ppms)).strip() if len(ppms) == 1 else '',
               crawl_date=observed.date().isoformat())
    savings = product.split('\nSavings\n', 1)[1] if '\nSavings\n' in product else ''
    audit = {'stable_identity': identity, 'observed_at': evidence['observed_at'],
             'availability_state': state, 'selected_option': option.group(1).strip() if option else '',
             'selected_size': size.group(1).strip(), 'source_sha256': digest(evidence),
             'store_proof_sha256': digest(store_proof), 'discrepancies': discrepancies,
             'offers_pending': bool(savings), 'unresolved_offer_text': savings,
             'full_variant_discovery_proved': False, 'complete_offer_discovery_proved': False,
             'source_mode': 'saved_rendered_observation_not_unattended_execution'}
    return row, audit


def parse_collection(evidence, store, store_proof, *, previous_rows=None, previous_retention=None):
    if not evidence:
        raise ValueError('EMPTY_RENDERED_COLLECTION')
    times = [stamp(e['observed_at']) for e in evidence]
    if (max(times) - min(times)).total_seconds() > 3600:
        raise ValueError('MIXED_OBSERVATION_WINDOWS')
    rows, audits, observations = [], {}, {}
    for e in evidence:
        row, audit = parse_product(e, store, store_proof)
        identity = audit['stable_identity']
        if identity in audits:
            raise ValueError('DUPLICATE_RENDERED_IDENTITY_REQUIRES_RECONCILIATION')
        rows.append(row)
        audits[identity] = audit
        observations[identity] = observation(row, store['id'], e['observed_at'],
            [{'kind': 'rendered_product', 'sha256': audit['source_sha256'], 'url': e['url']},
             {'kind': 'selected_store', 'sha256': audit['store_proof_sha256']}], audit['availability_state'])
    collection_at = max(e['observed_at'] for e in evidence if stamp(e['observed_at']) == max(times))
    accumulated = reconcile(rows, observations, store['id'], collection_at,
                                     previous_rows=previous_rows, previous_retention=previous_retention)
    return {'products': accumulated['products'], 'retention': accumulated['retention'], 'provenance': audits,
            'acceptance': {'submission_ready': False, 'complete_category': False,
                           'unattended_execution': False, 'fresh_direct_records': len(rows),
                           'accumulated_records': len(accumulated['products']),
                           'pending_offer_records': sum(a['offers_pending'] for a in audits.values())}}
