"""Conservative, separately exported website enrichment with observation-time checks."""
import argparse
from collections import Counter
import copy
from datetime import datetime,timezone
from decimal import Decimal,InvalidOperation
import hashlib
import json
import re
from pathlib import Path
from urllib.parse import urlsplit
from .api_trial import encode,enrich,verify_store,usable_product_selection
from .schema import FIELDS


def _stamp(value):
    stamp=datetime.fromisoformat(value)
    if stamp.tzinfo is None:raise ValueError('UNZONED_OBSERVATION')
    return stamp


def merge_export(rows,provenance,evidence,store_document,maximum_age_seconds=3600,
                 previous_rows=None,previous_retention=None,collection_at=None):
    from .retention import stable_identity,provenance_for,observation,reconcile
    if not 1<=maximum_age_seconds<=3600:raise ValueError('Enrichment time window must be 1..3600 seconds')
    sid=store_document['locationId'];zipcode=store_document['address']['zipCode']
    store=verify_store(store_document,sid,zipcode)
    products=[];quarantine=[];rejected=[];availability_audit=[];out_provenance=copy.deepcopy(provenance)
    digital_pending=0;volume_pending=0;observations={};seen=set()
    for original in rows:
        if (list(original)!=list(FIELDS) or not all(isinstance(v,str) for v in original.values())
                or original['zipcode']!=zipcode or original['store_location']!=store.store_location):
            raise ValueError('INVALID_INPUT_SCHEMA_OR_STORE')
        identity=stable_identity(original,sid)
        if identity in seen:raise ValueError('INPUT_DUPLICATE_IDENTITY')
        seen.add(identity);row=dict(original);upc=row['upc'];p=provenance_for(provenance,row,sid)
        api_at=p['observed_at'];api_stamp=_stamp(api_at)
        if api_stamp.astimezone(timezone.utc).date().isoformat()!=row['crawl_date']:raise ValueError('API_CRAWL_DATE_MISMATCH')
        pk=identity if identity in out_provenance or not upc else upc
        out_provenance.setdefault(pk,copy.deepcopy(p))
        refs=copy.deepcopy(p.get('source_refs',[]))
        if not refs and p.get('api_response_sha256'):
            refs=[{'kind':'api_response','sha256':p['api_response_sha256'],'url':row['url'],'observed_at':api_at,'hash_basis':'original_source_provenance'}]
        obs=observation(row,sid,api_at,refs,p.get('availability_state','unknown'))
        obs['field_observed_at']={f:api_at for f in FIELDS if row[f]}
        candidates=[]
        for item in evidence:
            # Never use a shared blank UPC as an identity join.
            if upc:
                if item.get('upc')!=upc:continue
            else:
                try:
                    if stable_identity(item,sid)!=identity:continue
                except ValueError:continue
            if not usable_product_selection(item):
                rejected.append({'upc':upc,'reason':'WEBSITE_VARIANT_SELECTION_UNUSABLE'});continue
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
            text=item.get('observed_text','');primary=item.get('primary_text','')
            if (not isinstance(text,str) or store.store_location.split(',')[0] not in text
                    or 'Pickup at Marianos' not in text or (upc and upc not in text)):
                rejected.append({'upc':upc,'reason':'WEBSITE_CONTEXT_UNVERIFIED'});continue
            if item.get('pickup_available') is False:
                verified=(isinstance(primary,str) and (not upc or re.findall(r'UPC:\s*(\d+)\b',primary)==[upc])
                    and re.search(r'\bPickup\s*\n\s*(?:Out of Stock|Unavailable|Not Available)\b',primary,re.I))
                if not verified:
                    rejected.append({'upc':upc,'reason':'WEBSITE_UNAVAILABILITY_UNVERIFIED'});continue
            if item.get('pickup_available') is not False and not item.get('displayed_regular_price'):
                rejected.append({'upc':upc,'reason':'WEBSITE_PRICE_UNVERIFIED'});continue
            candidates.append((gap,item))
        if candidates:
            gap,item=min(candidates,key=lambda value:value[0]);at=item['observed_at']
            digest=hashlib.sha256(encode(item)).hexdigest()
            obs['source_refs'].append({'url':item['url'],'sha256':digest,'observed_at':at})
            if _stamp(at)>=api_stamp:
                obs['observed_at']=at;row['crawl_date']=_stamp(at).astimezone(timezone.utc).date().isoformat()
            available=item.get('pickup_available')
            obs['availability_state']='available' if available is True else 'unavailable' if available is False else 'unknown'
            obs['availability_evidence_at']=at
            conflicts=[]
            for field,observed in [('regular_price','displayed_regular_price'),('sale_price','displayed_sale_price')]:
                if observed in item and row[field] and item[observed]:
                    try:matches=Decimal(item[observed])==Decimal(row[field])
                    except (InvalidOperation,TypeError):matches=False
                    if not matches:conflicts.append('WEBSITE_API_'+field.upper()+'_CONFLICT')
                elif observed in item and field=='sale_price' and row[field] and not item[observed]:
                    conflicts.append('WEBSITE_API_SALE_PRICE_CONFLICT')
            if available is False or conflicts:
                for field in ('regular_price','sale_price','ppm','volume_deals_description','volume_deals_price','digital_deals_description','digital_deals_price'):
                    row[field]=''
                if available is False:
                    audit={'upc':upc,'stable_identity':identity,'status':'pickup_unavailable','store_id':sid,'observed_at':at,
                        'observation_gap_seconds':gap,'evidence_sha256':digest,'api_record':copy.deepcopy(original),'website_evidence':copy.deepcopy(item)}
                    availability_audit.append(audit)
                    out_provenance[pk]['availability']={k:copy.deepcopy(v) for k,v in audit.items() if k not in ('api_record','website_evidence')}
                if conflicts:quarantine.append({'api_record':copy.deepcopy(original),'website_evidence':copy.deepcopy(item),
                    'reasons':conflicts,'observation_gap_seconds':gap,'identity_retained_in_output':True})
            elif available is not True:
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
                    rejected.append({'upc':upc,'reason':'WEBSITE_FIELD_OR_CONTEXT_UNVERIFIED'});row=dict(original);obs['observed_at']=api_at
                else:
                    out_provenance[pk]['website_fields']={f:{'observed_at':at,'source_url':item['url'],
                        'evidence_sha256':digest,'observation_gap_seconds':gap} for f in FIELDS if row[f]!=original[f]}
                    for f in FIELDS:
                        if row[f]!=original[f] and row[f]:obs['field_observed_at'][f]=at
        products.append(row);observations[identity]=obs
    collection_at=collection_at or max((o['observed_at'] for o in observations.values()),key=_stamp,default=None)
    if collection_at is None:raise ValueError('COLLECTION_TIMESTAMP_REQUIRED')
    accumulated=reconcile(products,observations,sid,collection_at,previous_rows,previous_retention)
    products=accumulated['products']
    return {'products':products,'retention':accumulated['retention'],'quarantine':quarantine,'availability_audit':availability_audit,
        'rejected_evidence':rejected,'provenance':out_provenance,
        'report':{'input_records':len(rows),'records':len(products),'unique_upcs':len({r['upc'] for r in products if r['upc']}),
            'current_records':accumulated['current_records'],'carried_forward_records':accumulated['carried_forward_records'],
            'unavailable_records_retained':len(availability_audit),'quarantined_records':len(quarantine),
            'quarantine_excludes_identity':False,'maximum_observation_gap_seconds':maximum_age_seconds,
            'rejected_evidence_counts':dict(Counter(e['reason'] for e in rejected)),
            'digital_details_pending':digital_pending,'volume_details_pending':volume_pending,
            'field_completeness':{f:sum(bool(r[f]) for r in products) for f in FIELDS},
            'source_is_synthetic':None,'source_verification':'not independently determined by merge function',
            'category_complete':False,'submission_ready':False}}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('products','provenance','evidence','verified-store','output'):p.add_argument('--'+name,required=True,type=Path)
    p.add_argument('--previous-products',type=Path)
    p.add_argument('--previous-retention',type=Path)
    p.add_argument('--collection-at')
    args=p.parse_args()
    if bool(args.previous_products)!=bool(args.previous_retention):p.error('Previous products and retention sidecar are required together')
    read=lambda path:json.loads(path.read_text(encoding='utf-8-sig'))
    store=read(args.verified_store);store=store.get('data',store)
    result=merge_export(read(args.products),read(args.provenance),read(args.evidence),store,
        previous_rows=read(args.previous_products) if args.previous_products else None,
        previous_retention=read(args.previous_retention) if args.previous_retention else None,collection_at=args.collection_at)
    if args.output.exists() and any(args.output.iterdir()):raise ValueError('Output must be a new empty review directory')
    args.output.mkdir(parents=True,exist_ok=True)
    for name,value in result.items():(args.output/(name+'.json')).write_bytes(encode(value))
    print(json.dumps(result['report']))

if __name__=='__main__':main()
