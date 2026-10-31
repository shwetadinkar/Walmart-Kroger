"""Observe official Kroger API products as 22-field records.

Ported from `marianos-live-api-west-loop` and `marianos-fresh-runs-category-
evidence`, and changed by the client's retention principle (31 October 2026):
a product is never removed because a field is missing or a status is
unfavourable. So:

  - The qualifying-offer test classifies. A product with no local pickup offer,
    no price or no UPC stays in the export with empty strings for what was not
    observed, and the reason sits beside it in the per-record context.
  - An unmapped Kroger label leaves `category` empty. Neither source branch did
    this; both wrote the raw label into `category`, which the client's CSV does
    not contain.
  - The label map is config/category_map.json. There is one map.
  - The published URL is scheme, host and path only. Kroger appends `?cid=`
    carrying the API client id, which must not ship in a deliverable.

Keyword searches never exhaust a retailer category, so nothing here claims to.
"""
from __future__ import annotations

import argparse
from collections import Counter
from decimal import Decimal
import hashlib
import json
import math
from pathlib import Path
import re
from urllib.parse import urlsplit

from .config import Store
from .kroger import Credentials, KrogerClient
from .schema import FIELDS, make_record, make_retained_record
from .storage import LocalStorage

SITE = "https://www.marianos.com"
CATEGORY_MAP_PATH = Path(__file__).resolve().parent.parent / "config/category_map.json"
TERMS = ('milk','bread','cheese','yogurt','eggs','butter','cereal','pasta','rice','beans',
         'soup','sauce','coffee','tea','juice','water','crackers','cookies','chips','chocolate',
         'frozen pizza','ice cream','flour','sugar','oil','spices','canned vegetables',
         'frozen vegetables','chicken','bacon','seafood','deli','shampoo','toothpaste',
         'soap','detergent','paper towels','diapers','dog food','cat food')


def load_category_map():
    return json.loads(CATEGORY_MAP_PATH.read_text(encoding="utf-8"))["map"]


def encode(value):
    return json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False).encode('utf-8')


def verify_store(document, location_id, zipcode):
    if not isinstance(document, dict):
        raise ValueError("MALFORMED_STORE")
    address = document.get("address") or {}
    if (document.get("locationId") != location_id
            or document.get("chain") != "MARIANOS"
            or "mariano" not in str(document.get("name", "")).lower()
            or address.get("zipCode") != zipcode
            or not address.get("addressLine1")):
        raise ValueError("STORE_MISMATCH")
    return Store(location_id, zipcode, document["name"],
                 f"{address['addressLine1']}, {address.get('city', '')}, "
                 f"{address.get('state', '')} {zipcode}")


def money(value):
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not math.isfinite(value) or value < 0):
        raise ValueError("INVALID_PRICE")
    return format(Decimal(str(value)).quantize(Decimal(".01")), ".2f")


def api_categories(product):
    cats = product.get("categories")
    return [c for c in cats if isinstance(c, str)] if isinstance(cats, list) else []


def map_category(categories, category_map):
    """(client_root, kroger_label) from the product's own categories.

    Returns ("", label) when no label maps. An unmapped label is reported, not
    guessed into a root: a wrong category is worse than an absent one, because
    it survives review as though it were evidence.
    """
    for label in categories:
        root = category_map.get(label)
        if root:
            return root, label
    return "", (categories[0] if categories else "")


def _observed_money(value):
    """A usable price, or empty. Zero is empty: read as a price it would mean free."""
    try:
        return money(value) if value else ""
    except ValueError:
        return ""


def _offer_gaps(item):
    """Why this item is not a qualifying local pickup offer; empty if it is."""
    gaps = []
    fulfillment = item.get("fulfillment")
    price = item.get("price")
    if str(item.get("soldBy") or "").upper() != "UNIT":
        gaps.append("NOT_SOLD_BY_UNIT")
    if not isinstance(fulfillment, dict) or fulfillment.get("curbside") is not True:
        gaps.append("NO_CURBSIDE_PICKUP")
    if not item.get("size"):
        gaps.append("NO_SIZE")
    regular = price.get("regular") if isinstance(price, dict) else None
    if not _observed_money(regular):
        gaps.append("NO_POSITIVE_REGULAR_PRICE")
    return gaps


def select_offer(product):
    """(item, gaps): the qualifying item, else the closest one, with what it lacks.

    A classifier. Nothing here decides whether the product is delivered.
    """
    items = product.get("items")
    items = [x for x in items if isinstance(x, dict)] if isinstance(items, list) else []
    if not items:
        return {}, ["NO_ITEMS"]
    ranked = [(_offer_gaps(x), x) for x in items]
    gaps, item = min(ranked, key=lambda pair: len(pair[0]))
    return item, gaps


def availability_state(item):
    """From explicit inventory. A fulfillment capability flag does not prove stock."""
    inventory = item.get("inventory")
    stock = inventory.get("stockLevel") if isinstance(inventory, dict) else None
    if stock in ("TEMPORARILY_OUT_OF_STOCK", "OUT_OF_STOCK"):
        return "unavailable"
    return "available" if stock in ("HIGH", "LOW") else "unknown"


def _front_image(product):
    for image in product.get("images") or []:
        if image.get("perspective") == "front" or image.get("default"):
            sizes = image.get("sizes") or []
            url = next((s["url"] for size in ("xlarge", "large", "medium", "small")
                        for s in sizes if s.get("size") == size and s.get("url")), "")
            if url:
                return url
    return ""


def _identity_basis(upc, url):
    if url:
        return "productId"
    return "upc" if upc else ""


def observe(product, store, crawl_date, category_map=None):
    """(22-field record, per-record context). Refuses only what is not a product.

    What is missing is an empty string in the record and a reason in the context.
    Raises ValueError for a non-object, and RecordRejected for the exclusions the
    brief itself makes, such as approximate-weight wording.
    """
    if not isinstance(product, dict):
        raise ValueError("MALFORMED_PRODUCT")
    category_map = load_category_map() if category_map is None else category_map
    gaps = []
    upc = product.get("upc")
    if not isinstance(upc, str) or not re.fullmatch(r"\d{8,14}", upc):
        upc = ""
        gaps.append("NO_VALID_UPC")
    uri = product.get("productPageURI") or ""
    parsed = urlsplit(uri) if isinstance(uri, str) else urlsplit("")
    url = SITE + parsed.path
    tail = parsed.path.split("/")[-1]
    product_id = product.get("productId")
    if (parsed.scheme or parsed.netloc
            or not parsed.path.startswith("/p/")
            or not re.fullmatch(r"[A-Za-z0-9_-]{4,80}", tail)
            or (product_id and tail != str(product_id))):
        url = ""
        gaps.append("NO_VALID_PRODUCT_URI")
    item, offer_gaps = select_offer(product)
    category, label = map_category(api_categories(product), category_map)
    price = item.get("price") if isinstance(item.get("price"), dict) else {}
    promo = price.get("promo")
    raw = {"store_id": store.store_id, "zipcode": store.zipcode,
           "seller_type": "marianos", "fulfillment": "pickup",
           "store_context_verified": True, "brand": product.get("brand", ""),
           "product_title": product.get("description", ""),
           "weight": item.get("size") or "",
           "regular_price": _observed_money(price.get("regular")),
           "sale_price": _observed_money(promo) if isinstance(promo, (int, float)) and promo > 0 else "",
           "image_url": _front_image(product), "url": url, "upc": upc}
    record, refused = make_retained_record(raw, store, category, label, crawl_date)
    context = {
        "location_id": store.store_id,
        "identity_basis": _identity_basis(upc, url),
        "product_id": str(product.get("productId") or ""),
        "offer_status": "no_qualifying_pickup_offer" if offer_gaps else "qualifying_pickup_offer",
        "offer_gaps": offer_gaps,
        "record_gaps": gaps,
        "value_refusals": refused,
        "sold_by": str(item.get("soldBy") or ""),
        "fulfillment": item.get("fulfillment") if isinstance(item.get("fulfillment"), dict) else {},
        "stock_level": (item.get("inventory") or {}).get("stockLevel", "")
                       if isinstance(item.get("inventory"), dict) else "",
        "availability_state": availability_state(item),
    }
    return record, context


def normalize(product, store, crawl_date, category_map=None):
    return observe(product, store, crawl_date, category_map)[0]


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
    if evidence.get('upc'):
        if 'primary_text' in evidence and primary_upcs!=[str(evidence['upc'])]:return False
    else:
        from .retention import stable_identity
        try:stable_identity(evidence,evidence.get('store_id',''))
        except ValueError:return False
        if evidence.get('selection_complete') is not True:return False
    resolved_unavailable=(evidence.get('pickup_available') is False and isinstance(primary,str)
        and bool(evidence.get('upc')) and primary_upcs==[str(evidence['upc'])])
    for text in (evidence.get('observed_text',''),evidence.get('primary_text','')):
        if not isinstance(text,str):return False
        if re.search(r'^(?:Option|Size):[ \t]*$',text,re.M):return False
        if re.search(r'This selection is unavailable|Please choose another option',text,re.I) and not resolved_unavailable:return False
    return True


def enrich(record, evidence, store_id):
    if not usable_product_selection(evidence):raise ValueError('WEBSITE_VARIANT_SELECTION_UNUSABLE')
    from .retention import stable_identity
    identity_matches=(evidence.get('upc')==record['upc'] if record['upc'] else
        evidence.get('selection_complete') is True and stable_identity(evidence,store_id)==stable_identity(record,store_id))
    if evidence.get('store_id') != store_id or not identity_matches:
        raise ValueError('WEBSITE_STORE_OR_UPC_MISMATCH')
    text = evidence.get('observed_text','')
    street = record['store_location'].split(',')[0]
    if (record['upc'] and record['upc'] not in text) or street not in text or 'Pickup at Marianos' not in text:
        raise ValueError('MISSING_WEBSITE_CONTEXT')
    result = dict(record)
    for field,observed in (('regular_price','displayed_regular_price'),('sale_price','displayed_sale_price')):
        value=evidence.get(observed,'')
        if not result[field] and value:
            if not isinstance(value,str) or not re.fullmatch(r'\d+(?:\.\d{1,2})?',value):raise ValueError('INVALID_DISPLAYED_PRICE')
            if not re.search(r'(?<![\d.])\$'+re.escape(value)+r'(?![\d.])',text):raise ValueError('PRICE_NOT_DISPLAYED')
            result[field]=value
    for field in ('ppm' ,'sub_category','volume_deals_description','volume_deals_price',
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

def import_snapshot(source, output, location_id, zipcode, minimum=500, website=None):
    from .retention import stable_identity,stamp,seed_retention
    from .temporal_enrichment import merge_export
    source,output=Path(source),Path(output)
    if minimum<1:raise ValueError('INVALID_RECORD_BOUNDS')
    store_document=json.loads((source/'verified_store.json').read_text(encoding='utf-8-sig'))['data']
    store=verify_store(store_document,location_id,zipcode)
    category_map=load_category_map()
    records={};provenance={};rejects=Counter();duplicates=0;pages=[];hashes={}
    for path in sorted(source.glob('page_*.json')):
        body=path.read_bytes();page=json.loads(body)
        if page.get('locationId')!=location_id:raise ValueError('PAGE_STORE_MISMATCH')
        at=page['observed_at'];when=stamp(at);products=page.get('response',{}).get('data')
        if not isinstance(products,list) or not products:raise ValueError('BLOCKED_EMPTY_OR_MALFORMED_PAGE')
        digest=hashlib.sha256(body).hexdigest();hashes[path.name]=digest
        pages.append({'file':path.name,'term':page.get('term',''),'observed_at':at,'returned':len(products)})
        for product in products:
            try:
                row,context=observe(product,store,when.date().isoformat(),category_map)
                identity=stable_identity(row,location_id)
            except (ValueError,TypeError,KeyError,AttributeError) as exc:rejects[str(exc)]+=1;continue
            pk=row['upc'] or identity
            placement={'page':path.name,'term':page.get('term','')}
            if identity in records:
                duplicates+=1
                oldpk=records[identity]['upc'] or identity
                old=provenance[oldpk]
                if stamp(at)<=stamp(old['observed_at']):old['placements'].append(placement);continue
                placements=old['placements']+[placement]
                if oldpk!=pk:provenance.pop(oldpk)
            else:
                placements=[placement]
            records[identity]=row
            provenance[pk]={'productId':product.get('productId'),'pickup_context':context,'api_categories':product.get('categories',[]),
                'original_product_uri':product.get('productPageURI'),'observed_at':at,'placements':placements,
                'website_enriched':False,'assortment_basis':'verified store-scoped API response',
                'availability_state':context['availability_state'],'fulfillment_flags':context['fulfillment'],
                'source_refs':[{'file':path.name,'sha256':digest,'url':row['url'],'observed_at':at}]}
    if len(records)<minimum:raise ValueError(f'Only {len(records)} directly observed qualifying records; minimum {minimum}')
    collection_at=max((p['observed_at'] for p in pages),key=stamp)
    storage=LocalStorage(output)
    with storage.locked(location_id):
        previous=storage.read('latest.json');previous=json.loads(previous) if previous else {}
        prior_rows=[];prior_retention={}
        if previous:
            prior_rows=json.loads(storage.read(previous['data_key']))
            if any(r['zipcode']!=zipcode or r['store_location']!=store.store_location for r in prior_rows):raise ValueError('PRIOR_STORE_CONTEXT_MISMATCH')
            if len(records)<int(previous.get('current_records',previous.get('records',0)))*0.8:
                raise ValueError('MATERIAL_YIELD_DROP: previous trial preserved')
            if previous.get('retention_key'):prior_retention=json.loads(storage.read(previous['retention_key']))
            else:
                old_provenance=json.loads(storage.read(previous['provenance_key']))
                prior_retention=seed_retention(prior_rows,old_provenance,location_id,
                    max((p['observed_at'] for p in old_provenance.values()),key=stamp))
        merged=merge_export(list(records.values()),provenance,website or [],store_document,
            previous_rows=prior_rows,previous_retention=prior_retention)
        rows=merged['products'];retention=merged['retention'];provenance=merged['provenance']
        report={'mode':'OFFICIAL_KROGER_API_TRIAL','store_id':location_id,'zipcode':zipcode,
            'records':len(rows),'unique_upcs':len({r['upc'] for r in rows if r['upc']}),
            'stable_identities':len(retention),'missing_upc_records':sum(not r['upc'] for r in rows),
            'current_records':merged['report']['current_records'],'carried_forward_records':merged['report']['carried_forward_records'],
            'duplicate_placements':duplicates,'pre_quarantine_records':len(records),'quarantined_records':len(merged['quarantine']),
            'quarantine_excludes_identity':False,'rejections':dict(rejects),
            'category_counts':dict(Counter(r['category'] or 'UNMAPPED' for r in rows)),
            'source_pages':pages,'source_sha256':hashes,'verified_store_sha256':hashlib.sha256(encode(store_document)).hexdigest(),
            'website_evidence_sha256':hashlib.sha256(encode(website or [])).hexdigest(),
            'website_price_mismatches':merged['quarantine'],'website_pages_checked':len(website or []),
            'website_digital_details_pending':merged['report']['digital_details_pending'],
            'field_completeness':{f:sum(bool(r[f]) for r in rows) for f in FIELDS},
            'coverage_scope':'bounded_keyword_search_trial','full_category_coverage_verified':False,
            'source_is_synthetic':None,'submission_ready':False,
            'limitations':['Source authenticity is not inferred by importing JSON.','Keyword search is not complete category enumeration.',
                'Carried-forward records preserve prior crawl dates; retention sidecar distinguishes freshness.',
                'Blank PPM/offer fields are unobserved; offline export does not establish Azure/live acceptance.']}
        identity=hashlib.sha256(encode({'hashes':hashes,'rows':rows,'retention':retention,
            'website_hash':report['website_evidence_sha256']})).hexdigest()[:20]
        prefix='runs/'+identity
        for name,value in [('products',rows),('validation',report),('provenance',provenance),('retention',retention),
                ('verified_store',store_document),('website_evidence',website or []),('quarantine',merged['quarantine']),
                ('availability_audit',merged['availability_audit'])]:storage.write(prefix+'/'+name+'.json',encode(value))
        storage.write('latest.json',encode({'run':identity,'records':len(rows),'current_records':report['current_records'],
            'data_key':prefix+'/products.json','report_key':prefix+'/validation.json','provenance_key':prefix+'/provenance.json',
            'retention_key':prefix+'/retention.json','submission_ready':False}))
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--location-id',required=True)
    parser.add_argument('--zipcode',required=True)
    parser.add_argument('--minimum',type=int,default=500)
    parser.add_argument('--website-evidence',type=Path)
    args = parser.parse_args(argv)
    evidence = json.loads(args.website_evidence.read_text(encoding='utf-8')) if args.website_evidence else []
    report = import_snapshot(args.source,args.output,args.location_id,args.zipcode,args.minimum,evidence)
    print(json.dumps(report,indent=2))

if __name__ == '__main__': main()
