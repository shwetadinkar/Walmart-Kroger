"""Official API trials; never claim that keyword searches exhaust retailer categories."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
import math
from pathlib import Path
import re
from urllib.parse import urlsplit

from .config import Store
from .kroger import Credentials, KrogerClient
from .schema import FIELDS, make_record
from .storage import LocalStorage

TERMS = ('milk','bread','cheese','yogurt','eggs','butter','cereal','pasta','rice','beans',
         'soup','sauce','coffee','tea','juice','water','crackers','cookies','chips','chocolate',
         'frozen pizza','ice cream','flour','sugar','oil','spices','canned vegetables',
         'frozen vegetables','chicken','bacon','seafood','deli','shampoo','toothpaste',
         'soap','detergent','paper towels','diapers','dog food','cat food')
CATEGORY_MAP = {'Natural & Organic':'Natural Organic','Dairy':'Dairy','Bakery':'Bakery',
                'Breakfast':'Breakfast','Frozen':'Frozen','Deli':'Deli','Beverages':'Beverages',
                'Produce':'Produce','Grocery':'Grocery','Candy':'Candy','Coffee':'Coffee',
                'Baby':'Baby','Beauty':'Beauty','Health':'Health','Pet Care':'Pet Supplies'}

def encode(value):
    return json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False).encode('utf-8')

def verify_store(document, location_id, zipcode):
    if not isinstance(document, dict):
        raise ValueError('MALFORMED_STORE')
    address = document.get('address') or {}
    if (document.get('locationId') != location_id or document.get('chain') != 'MARIANOS'
            or 'mariano' not in str(document.get('name','')).lower()
            or address.get('zipCode') != zipcode or not address.get('addressLine1')):
        raise ValueError('STORE_MISMATCH')
    return Store(location_id, zipcode, document['name'],
                 f"{address['addressLine1']}, {address.get('city','')}, {address.get('state','')} {zipcode}")

def money(value):
    if isinstance(value, bool) or not isinstance(value, (int,float)) or not math.isfinite(value) or value < 0:
        raise ValueError('INVALID_PRICE')
    return format(Decimal(str(value)).quantize(Decimal('.01')), '.2f')

def normalize(product, store_document, crawl_date):
    store = verify_store(store_document, store_document.get('locationId'), store_document.get('address',{}).get('zipCode'))
    upc = product.get('upc')
    if not isinstance(upc,str) or not re.fullmatch(r'\d{8,14}',upc):
        raise ValueError('INVALID_UPC')
    uri = product.get('productPageURI','')
    parsed = urlsplit(uri)
    if (parsed.scheme or parsed.netloc or parsed.fragment or not parsed.path.startswith('/p/')
            or parsed.path.split('/')[-1] != str(product.get('productId',''))):
        raise ValueError('INVALID_PRODUCT_URI')
    item = next((x for x in product.get('items',[]) if x.get('soldBy','').upper() == 'UNIT'
                 and x.get('fulfillment',{}).get('curbside') is True
                 and x.get('size') and isinstance(x.get('price'),dict)
                 and isinstance(x['price'].get('regular'),(int,float))
                 and not isinstance(x['price'].get('regular'),bool)
                 and x['price']['regular'] > 0),None)
    if not item:
        raise ValueError('NO_QUALIFYING_LOCAL_PICKUP_OFFER')
    categories = product.get('categories') or []
    # Preserve an unmapped source label rather than invent a CSV-root assignment.
    category = next((CATEGORY_MAP[c] for c in categories if c in CATEGORY_MAP),
                    str(categories[0]) if categories else '')
    image = ''
    for im in product.get('images',[]):
        if im.get('perspective') == 'front' or im.get('default'):
            sizes = im.get('sizes') or []
            image = next((x['url'] for size in ('xlarge','large','medium','small')
                          for x in sizes if x.get('size') == size and x.get('url')), '')
            if image: break
    price = item['price']
    raw = {'store_id':store.store_id,'zipcode':store.zipcode,'seller_type':'marianos',
           'fulfillment':'pickup','store_context_verified':True,
           'brand':product.get('brand',''),'product_title':product.get('description',''),
           'weight':item['size'],'regular_price':money(price['regular']),
           'sale_price':money(price['promo']) if isinstance(price.get('promo'),(int,float)) and price['promo'] > 0 else '',
           'image_url':image,'url':'https://www.marianos.com'+uri,'upc':upc}
    return make_record(raw,store,category,'',crawl_date)

def _displayed_passages(text,value,fragments):
    """Join complete displayed lines in source order; never clip a number or condition."""
    if (not isinstance(fragments,list) or not fragments
            or not all(isinstance(part,str) and bool(part.strip()) for part in fragments)
            or value!='\n'.join(fragments)):return False
    position=0
    for part in fragments:
        found=text.find(part,position)
        while found>=0:
            end=found+len(part)
            if (found==0 or text[found-1]=='\n') and (end==len(text) or text[end]=='\n'):
                position=end;break
            found=text.find(part,found+1)
        else:return False
    return True


def usable_product_selection(evidence):
    """Resolve SKU selection separately from current pickup availability."""
    if 'selection_complete' in evidence and evidence['selection_complete'] is not True:return False
    primary=evidence.get('primary_text','')
    primary_upcs=re.findall(r'UPC:\s*(\d+)\b',primary) if isinstance(primary,str) else []
    if 'primary_text' in evidence and primary_upcs!=[str(evidence.get('upc',''))]:return False
    resolved_unavailable=(evidence.get('pickup_available') is False and isinstance(primary,str)
        and bool(evidence.get('upc')) and primary_upcs==[str(evidence['upc'])])
    for text in (evidence.get('observed_text',''),evidence.get('primary_text','')):
        if not isinstance(text,str):return False
        if re.search(r'^(?:Option|Size):[ \t]*$',text,re.M):return False
        if re.search(r'This selection is unavailable|Please choose another option',text,re.I) and not resolved_unavailable:return False
    return True


def enrich(record, evidence, store_id):
    if not usable_product_selection(evidence):raise ValueError('WEBSITE_VARIANT_SELECTION_UNUSABLE')
    if evidence.get('pickup_available') is False:raise ValueError('WEBSITE_PICKUP_UNAVAILABLE')
    if evidence.get('store_id') != store_id or evidence.get('upc') != record['upc']:
        raise ValueError('WEBSITE_STORE_OR_UPC_MISMATCH')
    text = evidence.get('observed_text','')
    street = record['store_location'].split(',')[0]
    if record['upc'] not in text or street not in text or 'Pickup at Marianos' not in text:
        raise ValueError('MISSING_WEBSITE_CONTEXT')
    result = dict(record)
    for field in ('ppm','sub_category','volume_deals_description','volume_deals_price',
                  'digital_deals_description','digital_deals_price'):
        value = evidence.get(field,'')
        literal=isinstance(value,str) and value in text
        supplied=evidence.get('displayed_fragments')
        if value and field in ('volume_deals_description','digital_deals_description'):
            if isinstance(supplied,dict) and field in supplied:
                literal=_displayed_passages(text,value,supplied[field])
        if value and not literal:
            raise ValueError('VALUE_NOT_DISPLAYED')
        if value: result[field] = value
    if result['digital_deals_description'] and not re.search(r'clip|digital coupon|activat',result['digital_deals_description'],re.I):
        raise ValueError('DIGITAL_CONDITION_UNVERIFIED')
    if result['digital_deals_price'] and not result['digital_deals_description']:
        raise ValueError('DIGITAL_PRICE_WITHOUT_CONDITIONS')
    for field in ('volume_deals_price','digital_deals_price'):
        value=result[field]
        if value and (not re.fullmatch(r'\$?\d+(?:\.\d{1,2})?',value)
                      or '$'+value.lstrip('$') not in text):
            raise ValueError('DEAL_PRICE_NOT_EXPLICITLY_DISPLAYED')
    store=Store(store_id,result['zipcode'],result['store_name'],result['store_location'],result['store_logo'])
    raw=dict(result,store_id=store_id,seller_type='marianos',fulfillment='pickup',
             store_context_verified=True,brand='Kroger' if result['store_brand']=='yes' else '')
    return make_record(raw,store,result['category'],result['sub_category'],result['crawl_date'])

def import_snapshot(source, output, location_id, zipcode, minimum=500, maximum=650, website=None):
    source, output = Path(source), Path(output)
    if minimum < 1 or maximum < minimum:
        raise ValueError('INVALID_RECORD_BOUNDS')
    store_document = json.loads((source/'verified_store.json').read_text(encoding='utf-8'))['data']
    store = verify_store(store_document,location_id,zipcode)
    records, provenance, rejects = {}, {}, Counter()
    duplicate_placements, pages, source_hashes = 0, [], {}
    website_by_upc = {e['upc']:e for e in (website or [])}
    for path in sorted(source.glob('page_*.json')):
        body = path.read_bytes()
        page = json.loads(body)
        if page.get('locationId') != location_id:
            raise ValueError('PAGE_STORE_MISMATCH')
        stamp = datetime.fromisoformat(page['observed_at'])
        if stamp.tzinfo is None:
            raise ValueError('UNZONED_OBSERVATION_TIMESTAMP')
        crawl_date = stamp.astimezone(timezone.utc).date().isoformat()
        products = page.get('response',{}).get('data')
        if not isinstance(products,list) or not products:
            raise ValueError('BLOCKED_EMPTY_OR_MALFORMED_PAGE')
        source_hashes[path.name] = hashlib.sha256(body).hexdigest()
        pages.append({'file':path.name,'term':page.get('term',''),'observed_at':page['observed_at'],'returned':len(products)})
        for product in products:
            try:
                row = normalize(product,store_document,crawl_date)
            except (ValueError, TypeError, KeyError) as exc:
                rejects[str(exc)] += 1
                continue
            upc = row['upc']
            if upc in records:
                duplicate_placements += 1
                provenance[upc]['placements'].append({'page':path.name,'term':page.get('term','')})
                continue
            if len(records) >= maximum: continue
            if upc in website_by_upc:
                row = enrich(row,website_by_upc[upc],location_id)
            records[upc] = row
            provenance[upc] = {'productId':product.get('productId'),'api_categories':product.get('categories',[]),
                               'original_product_uri':product.get('productPageURI'),
                               'observed_at':page['observed_at'], 'placements':[{'page':path.name,'term':page.get('term','')}],
                               'website_enriched':upc in website_by_upc}
    if len(records) < minimum:
        raise ValueError(f'Only {len(records)} qualifying records; minimum {minimum}')
    rows = list(records.values())
    price_mismatches = []
    quarantined = []
    for row in rows:
        observed = website_by_upc.get(row['upc'], {})
        reasons=[]
        if observed.get('displayed_regular_price') and observed['displayed_regular_price'] != row['regular_price']:
            price_mismatches.append({'upc':row['upc'],'api_regular':row['regular_price'],
                                     'website_regular':observed['displayed_regular_price']})
            reasons.append('WEBSITE_API_REGULAR_PRICE_CONFLICT')
        if (observed.get('displayed_regular_price') and 'displayed_sale_price' in observed
                and observed['displayed_sale_price'] != row['sale_price']):
            price_mismatches.append({'upc':row['upc'],'api_sale':row['sale_price'],
                                     'website_sale':observed['displayed_sale_price']})
            reasons.append('WEBSITE_API_SALE_PRICE_CONFLICT')
        if observed.get('pickup_available') is False:
            reasons.append('WEBSITE_PICKUP_UNAVAILABLE_OR_UNVERIFIED')
        if reasons:quarantined.append({'record':row,'reasons':reasons})
    excluded={q['record']['upc'] for q in quarantined}
    rows=[r for r in rows if r['upc'] not in excluded]
    if len(rows)<minimum:raise ValueError(f'Only {len(rows)} records after conflict quarantine; minimum {minimum}')
    store_hash=hashlib.sha256(encode(store_document)).hexdigest()
    website_hash=hashlib.sha256(encode(website or [])).hexdigest()
    identity = hashlib.sha256(encode({'hashes':source_hashes,'rows':rows,
                                      'store_hash':store_hash,'website_hash':website_hash})).hexdigest()[:20]
    report = {'mode':'OFFICIAL_KROGER_API_TRIAL','store_id':location_id,'zipcode':zipcode,
              'records':len(rows),'unique_upcs':len(rows),'duplicate_placements':duplicate_placements,
              'pre_quarantine_records':len(records),'quarantined_records':len(quarantined),
              'rejections':dict(rejects),'category_counts':dict(Counter(r['category'] or 'UNMAPPED' for r in rows)),
              'source_pages':pages,'source_sha256':source_hashes,
              'verified_store_sha256':store_hash,'website_evidence_sha256':website_hash,
              'website_price_mismatches':price_mismatches,
              'website_pages_checked':sum(p['website_enriched'] for p in provenance.values()),
              'website_digital_details_pending':sum(bool(e.get('digital_details_required')) for e in website_by_upc.values()),
              'field_completeness':{f:sum(bool(r[f]) for r in rows) for f in FIELDS},
              'coverage_scope':'bounded_keyword_search_trial','full_category_coverage_verified':False,
              'category_label_policy':'Known aliases mapped; otherwise original API category label. Not proof of CSV-root coverage.',
              'source_is_synthetic':False,'submission_ready':False,
              'limitations':['Keyword search is not complete category enumeration.',
                             'Blank PPM or offer fields are unobserved, not confirmed absent.',
                             'Website enrichment applies only to explicitly matched store/UPC evidence.',
                             'Azure execution and human acceptance are not established by this export.']}
    storage = LocalStorage(output)
    with storage.locked(location_id):
        previous=storage.read('latest.json')
        if previous and len(rows) < int(json.loads(previous).get('records',0))*0.8:
            raise ValueError('MATERIAL_YIELD_DROP: previous trial preserved')
        prefix = f'runs/{identity}'
        storage.write(prefix+'/products.json',encode(rows))
        storage.write(prefix+'/validation.json',encode(report))
        storage.write(prefix+'/provenance.json',encode(provenance))
        storage.write(prefix+'/verified_store.json',encode(store_document))
        storage.write(prefix+'/website_evidence.json',encode(website or []))
        storage.write(prefix+'/quarantine.json',encode(quarantined))
        storage.write('latest.json',encode({'run':identity,'records':len(rows),
                                         'data_key':prefix+'/products.json','report_key':prefix+'/validation.json',
                                         'provenance_key':prefix+'/provenance.json','submission_ready':False}))
    return report

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--location-id',required=True)
    parser.add_argument('--zipcode',required=True)
    parser.add_argument('--minimum',type=int,default=500)
    parser.add_argument('--maximum',type=int,default=650)
    parser.add_argument('--website-evidence',type=Path)
    args = parser.parse_args(argv)
    evidence = json.loads(args.website_evidence.read_text(encoding='utf-8')) if args.website_evidence else []
    report = import_snapshot(args.source,args.output,args.location_id,args.zipcode,args.minimum,args.maximum,evidence)
    print(json.dumps(report,indent=2))

if __name__ == '__main__': main()
