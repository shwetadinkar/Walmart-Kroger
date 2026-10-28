"""Accumulated assortment with explicit observation freshness outside the 22 fields."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import re
from urllib.parse import urlsplit
from .schema import FIELDS, PRICE_FIELDS


def stamp(value):
    parsed=datetime.fromisoformat(value.replace('Z','+00:00'))
    if parsed.tzinfo is None:raise ValueError('UNZONED_RETENTION_TIMESTAMP')
    return parsed.astimezone(timezone.utc)


def stable_identity(row, store_id):
    p=urlsplit(row.get('url',''))
    tail=p.path.rstrip('/').split('/')[-1]
    if (p.scheme!='https' or p.hostname not in ('marianos.com','www.marianos.com')
            or not p.path.startswith('/p/') or not re.fullmatch(r'[A-Za-z0-9_-]{4,80}',tail)):
        raise ValueError('UNVERIFIED_STABLE_PRODUCT_IDENTITY')
    return str(store_id)+':product:'+tail


def provenance_for(provenance,row,store_id):
    return provenance.get(stable_identity(row,store_id),provenance.get(row.get('upc',''),{}))


def observation(row, store_id, observed_at, source_refs=None, availability_state='unknown'):
    stamp(observed_at)
    return {'observed_at':observed_at,'source_refs':deepcopy(source_refs or []),
            'availability_state':availability_state if availability_state in ('available','unavailable') else 'unknown'}


def reconcile(rows, observations, store_id, collection_at, previous_rows=None, previous_retention=None):
    """Current missing values remain blank; only absent/stale identities carry old rows."""
    collected=stamp(collection_at);previous_rows=previous_rows or [];prior=previous_retention or {}
    previous={};current={};result=[];metadata={}
    contexts={(r['zipcode'],r['store_location']) for r in rows}
    for row in previous_rows:
        identity=stable_identity(row,store_id)
        if contexts and (row['zipcode'],row['store_location']) not in contexts:raise ValueError('RETENTION_STORE_CONTEXT_MISMATCH')
        if identity in previous:raise ValueError('DUPLICATE_PRIOR_IDENTITY')
        previous[identity]=deepcopy(row)
    for row in rows:
        if list(row)!=list(FIELDS) or not all(isinstance(v,str) for v in row.values()):raise ValueError('RETENTION_SCHEMA')
        identity=stable_identity(row,store_id)
        if identity in current and current[identity]!=row:raise ValueError('CONFLICTING_CURRENT_IDENTITY')
        current[identity]=deepcopy(row)
    for identity in dict.fromkeys([*current,*previous]):
        old=deepcopy(prior.get(identity,{}));row=current.get(identity);reason=''
        if row is not None:
            evidence=observations.get(identity)
            if not evidence:raise ValueError('MISSING_DIRECT_OBSERVATION')
            observed=stamp(evidence['observed_at'])
            if observed>collected:raise ValueError('OBSERVATION_AFTER_COLLECTION')
            if observed.date().isoformat()!=row['crawl_date']:raise ValueError('RETENTION_CRAWL_DATE_MISMATCH')
            if old.get('last_observed_at') and observed<stamp(old['last_observed_at']):
                row=None;reason='STALE_OBSERVATION_IGNORED'
        if row is None:
            if identity not in previous:raise ValueError('STALE_WITHOUT_PREVIOUS_RECORD')
            row=previous[identity]
            if not old:raise ValueError('MISSING_PRIOR_RETENTION_METADATA')
            old.update(observation_status='carried_forward',carry_forward_reason=reason or 'NOT_RETURNED_IN_CURRENT_COLLECTION')
            for field in old.get('field_status',{}):
                if row.get(field):old['field_status'][field]='historical_carried_forward'
            old['last_successful_collection_at']=collection_at if collected>=stamp(old['last_successful_collection_at']) else old['last_successful_collection_at']
            metadata[identity]=old;result.append(row);continue
        at=evidence['observed_at'];history=deepcopy(old.get('historical_prices',{}))
        if identity in previous:
            for field in PRICE_FIELDS:
                value=previous[identity][field]
                if value:history[field]={'value':value,'observed_at':old.get('price_observed_at',{}).get(field,'')}
        availability=evidence.get('availability_state','unknown')
        metadata[identity]={'stable_identity':identity,'retailer_product_id':identity.split(':product:',1)[1],
            'first_seen_at':old.get('first_seen_at',at),'last_observed_at':at,'observation_status':'current',
            'last_successful_collection_at':collection_at,'availability_state':availability,
            'availability_evidence_at':evidence.get('availability_evidence_at',at) if availability!='unknown' else '',
            'price_observed_at':{field:evidence.get('field_observed_at',{}).get(field,at) if row[field] else '' for field in PRICE_FIELDS},
            'field_observed_at':{field:evidence.get('field_observed_at',{}).get(field,at) if row[field] else '' for field in FIELDS},
            'field_status':{field:'observed' if row[field] else 'unobserved' for field in FIELDS},
            'historical_prices':history,'source_refs':deepcopy(evidence.get('source_refs',[])),
            'carry_forward_reason':''}
        result.append(row)
    upcs={}
    for row in result:
        if row['upc']:
            identity=stable_identity(row,store_id)
            if row['upc'] in upcs and upcs[row['upc']]!=identity:raise ValueError('UPC_IDENTITY_COLLISION')
            upcs[row['upc']]=identity
    return {'products':result,'retention':metadata,'current_records':sum(m['observation_status']=='current' for m in metadata.values()),
            'carried_forward_records':sum(m['observation_status']=='carried_forward' for m in metadata.values())}


def seed_retention(rows,provenance,store_id,collection_at):
    observations={}
    for row in rows:
        p=provenance_for(provenance,row,store_id);at=p['observed_at']
        refs=deepcopy(p.get('source_refs',[]))
        if not refs:
            refs=[{'kind':'prior_export_record','url':row['url'],'observed_at':at,
                'sha256':hashlib.sha256(json.dumps(row,sort_keys=True,ensure_ascii=False).encode()).hexdigest()}]
        observations[stable_identity(row,store_id)]=observation(row,store_id,at,refs,p.get('availability_state','unknown'))
    return reconcile(rows,observations,store_id,collection_at)['retention']
