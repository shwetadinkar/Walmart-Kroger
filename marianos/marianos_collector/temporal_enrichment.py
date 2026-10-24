"""Conservative, separately exported website enrichment with observation-time checks."""
import argparse
from collections import Counter
import copy
from datetime import datetime,timezone
from decimal import Decimal,InvalidOperation
import hashlib
import json
from pathlib import Path
from urllib.parse import urlsplit
from .api_trial import encode,enrich,verify_store
from .schema import FIELDS


def _stamp(value):
    stamp=datetime.fromisoformat(value)
    if stamp.tzinfo is None:raise ValueError('UNZONED_OBSERVATION')
    return stamp


def merge_export(rows,provenance,evidence,store_document,maximum_age_seconds=3600):
    if not 1<=maximum_age_seconds<=3600:raise ValueError('Enrichment time window must be 1..3600 seconds')
    sid=store_document['locationId'];zipcode=store_document['address']['zipCode']
    store=verify_store(store_document,sid,zipcode)
    products=[];quarantine=[];rejected=[];out_provenance=copy.deepcopy(provenance);digital_pending=0;volume_pending=0
    by_upc={}
    for e in evidence:by_upc.setdefault(e.get('upc'),[]).append(e)
    if len({r['upc'] for r in rows})!=len(rows):raise ValueError('INPUT_DUPLICATE_UPC')
    for original in rows:
        if (list(original)!=list(FIELDS) or not all(isinstance(v,str) for v in original.values())
                or original['zipcode']!=zipcode or original['store_location']!=store.store_location):
            raise ValueError('INVALID_INPUT_SCHEMA_OR_STORE')
        row=dict(original);upc=row['upc'];api_stamp=_stamp(provenance[upc]['observed_at'])
        if api_stamp.astimezone(timezone.utc).date().isoformat()!=row['crawl_date']:raise ValueError('API_CRAWL_DATE_MISMATCH')
        candidates=[]
        for item in by_upc.get(upc,[]):
            try:gap=abs((_stamp(item['observed_at'])-api_stamp).total_seconds())
            except (ValueError,KeyError,TypeError):
                rejected.append({'upc':upc,'reason':'INVALID_OBSERVATION_TIME'});continue
            if item.get('store_id')!=sid:
                rejected.append({'upc':upc,'reason':'WEBSITE_STORE_MISMATCH'});continue
            source=urlsplit(item.get('url',''));target=urlsplit(row['url'])
            if source.scheme!='https' or source.hostname not in ('marianos.com','www.marianos.com') or source.path!=target.path:
                rejected.append({'upc':upc,'reason':'WEBSITE_PRODUCT_URL_MISMATCH'});continue
            if gap>maximum_age_seconds:
                rejected.append({'upc':upc,'reason':'OBSERVATION_TIME_GAP','seconds':gap});continue
            if not item.get('displayed_regular_price'):
                rejected.append({'upc':upc,'reason':'WEBSITE_PRICE_UNVERIFIED'});continue
            candidates.append((gap,item))
        if candidates:
            gap,item=min(candidates,key=lambda value:value[0])
            conflicts=[]
            for field,observed in [('regular_price','displayed_regular_price'),('sale_price','displayed_sale_price')]:
                if observed in item:
                    try:matches=Decimal(item[observed] or '0')==Decimal(row[field] or '0')
                    except (InvalidOperation,TypeError):matches=False
                    if not matches:conflicts.append('WEBSITE_API_'+field.upper()+'_CONFLICT')
            if item.get('pickup_available') is False:conflicts.append('WEBSITE_PICKUP_UNAVAILABLE')
            if conflicts:
                quarantine.append({'api_record':original,'website_evidence':item,'reasons':conflicts,'observation_gap_seconds':gap})
                continue
            if item.get('pickup_available') is not True:
                rejected.append({'upc':upc,'reason':'WEBSITE_PICKUP_NOT_VERIFIED'})
            else:
                usable=dict(item)
                if usable.get('volume_deals_description') and usable.get('volume_terms_complete') is not True:
                    usable['volume_deals_description']=usable['volume_deals_price']='';volume_pending+=1
                if usable.get('digital_deals_description') and usable.get('digital_terms_complete') is not True:
                    usable['digital_deals_description']=usable['digital_deals_price']='';digital_pending+=1
                elif usable.get('digital_details_required'):digital_pending+=1
                try:row=enrich(row,usable,sid)
                except ValueError:
                    rejected.append({'upc':upc,'reason':'WEBSITE_FIELD_OR_CONTEXT_UNVERIFIED'});row=dict(original)
                else:
                    digest=hashlib.sha256(encode(item)).hexdigest()
                    out_provenance[upc]['website_fields']={f:{'observed_at':item['observed_at'],'source_url':item['url'],
                        'evidence_sha256':digest,'observation_gap_seconds':gap} for f in FIELDS if row[f]!=original[f]}
        products.append(row)
    return {'products':products,'quarantine':quarantine,'rejected_evidence':rejected,'provenance':out_provenance,
            'report':{'input_records':len(rows),'records':len(products),'unique_upcs':len({r['upc'] for r in products}),
                      'quarantined_records':len(quarantine),'maximum_observation_gap_seconds':maximum_age_seconds,
                      'rejected_evidence_counts':dict(Counter(e['reason'] for e in rejected)),
                      'digital_details_pending':digital_pending,'volume_details_pending':volume_pending,
                      'field_completeness':{f:sum(bool(r[f]) for r in products) for f in FIELDS},
                      'source_is_synthetic':None,'source_verification':'not independently determined by merge function',
                      'category_complete':False,'submission_ready':False}}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('products','provenance','evidence','verified-store','output'):p.add_argument('--'+name,required=True,type=Path)
    args=p.parse_args()
    read=lambda path:json.loads(path.read_text(encoding='utf-8-sig'))
    store=read(args.verified_store);store=store.get('data',store)
    result=merge_export(read(args.products),read(args.provenance),read(args.evidence),store)
    if args.output.exists() and any(args.output.iterdir()):raise ValueError('Output must be a new empty review directory')
    args.output.mkdir(parents=True,exist_ok=True)
    for name,value in result.items():(args.output/(name+'.json')).write_bytes(encode(value))
    print(json.dumps(result['report']))

if __name__=='__main__':main()
