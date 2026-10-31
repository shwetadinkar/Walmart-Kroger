"""Bounded, resumable official API trial collection. Not full category enumeration."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
from urllib.request import urlopen

from .api_trial import TERMS, encode, import_snapshot, normalize, verify_store
from .kroger import Credentials, KrogerClient
from .storage import LocalStorage, AzureBlobStorage
from .execution_state import execute_once
from .retention import stable_identity

class BudgetOpener:
    def __init__(self,maximum,opener=urlopen):
        if not 1 <= maximum <= 200:raise ValueError('Network budget must be 1..200')
        self.maximum,self.opener,self.used=maximum,opener,0
        self.on_attempt=None
    def __call__(self,*args,**kwargs):
        if self.used>=self.maximum:raise ValueError('NETWORK_BUDGET_EXHAUSTED')
        self.used+=1
        if self.on_attempt:self.on_attempt(self.used)
        return self.opener(*args,**kwargs)

def collect(client,storage,location_id,zipcode,run_id,terms=TERMS,maximum_queries=40,target=650,canary_upc=''):
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}',run_id):raise ValueError('Unsafe run ID')
    if not re.fullmatch(r'\d{8}',location_id) or not re.fullmatch(r'\d{5}',zipcode):raise ValueError('Invalid store configuration')
    if not 1<=maximum_queries<=40 or not 1<=target<=1000:raise ValueError('Invalid collection bounds')
    if not terms or len(terms)>40:raise ValueError('Invalid search terms')
    store_response=client.get('/locations/'+location_id)
    store_document=store_response.get('data')
    store=verify_store(store_document,location_id,zipcode)
    prefix=f'checkpoints/{location_id}/{run_id}'
    config={'location_id':location_id,'zipcode':zipcode,'terms':list(terms),
            'maximum_queries':maximum_queries,'target':target,'per_search':50,'offset':1,'canary_upc':canary_upc}
    config_key=prefix+'/config.json'
    prior=storage.read(config_key)
    if prior and json.loads(prior)!=config:raise ValueError('CHECKPOINT_CONFIGURATION_MISMATCH')
    storage.write(config_key,encode(config))
    storage.write(prefix+'/verified_store.json',encode(store_response))
    records={};new_queries=0;cached_queries=0;completed=[]
    for index,term in enumerate(terms[:maximum_queries]):
        key=prefix+f'/page_{index:02d}.json'
        previous=storage.read(key)
        if previous:
            page=json.loads(previous)
            if page.get('term')!=term or page.get('locationId')!=location_id:raise ValueError('CHECKPOINT_PAGE_MISMATCH')
            cached_queries+=1
        else:
            if index and index%10==0:
                verify_store(client.get('/locations/'+location_id).get('data'),location_id,zipcode)
            payload=client.products(location_id,term,offset=1,limit=50)
            if not isinstance(payload.get('data'),list) or not payload['data']:raise ValueError('EMPTY_OR_BLOCKED_SEARCH')
            if index==0 and canary_upc and not any(p.get('upc')==canary_upc for p in payload['data']):
                raise ValueError('CONFIGURED_CANARY_MISSING')
            page={'locationId':location_id,'term':term,'observed_at':datetime.now(timezone.utc).isoformat(),'response':payload}
            storage.write(key,encode(page));new_queries+=1
        for product in page['response']['data']:
            try:
                row=normalize(product,store,page['observed_at'][:10])
                records.setdefault(stable_identity(row,location_id),row)
            except (ValueError,KeyError,TypeError,AttributeError):continue
            if len(records)>=target:break
        completed.append(term)
        status={'location_id':location_id,'source_prefix':prefix,'unique_records':len(records),
                'completed_terms':completed,'new_queries_this_run':new_queries,
                'cached_queries_this_run':cached_queries,'submission_ready':False}
        storage.write(prefix+'/progress.json',encode(status))
        print(json.dumps({'event':'search_checkpointed','term':term,'unique_records':len(records)}),flush=True)
        if len(records)>=target:break
    return status

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--location-id',required=True)
    parser.add_argument('--zipcode',required=True)
    parser.add_argument('--run-id',required=True,help='Reuse only to resume the same snapshot. Use a new ID for fresh collection.')
    parser.add_argument('--execution-id',default='',help='Azure execution identity for audit; never a credential.')
    parser.add_argument('--run-origin',choices=('azure-execution','explicit-resume','fresh-local'),default='explicit-resume')
    parser.add_argument('--output',type=Path,default=Path('.collector-output/api-trial'))
    parser.add_argument('--backend',choices=('local','azure'),default='local')
    parser.add_argument('--container',default='marianos-api-trials')
    parser.add_argument('--output-prefix',default='trials',help='Separate freshness pilots from the preserved baseline.')
    parser.add_argument('--maximum-queries',type=int,default=40)
    parser.add_argument('--maximum-requests',type=int,default=60)
    parser.add_argument('--target',type=int,default=650)
    parser.add_argument('--minimum',type=int,default=500)
    parser.add_argument('--canary-upc',default='')
    args=parser.parse_args(argv)
    if not 1<=args.minimum<=args.target<=1000:parser.error('Require 1 <= minimum <= target <= 1000')
    budget=BudgetOpener(args.maximum_requests)
    client=KrogerClient(Credentials.from_environment(),opener=budget)
    if args.backend=='azure':
        storage=AzureBlobStorage.from_environment(args.container)
    else:storage=LocalStorage(args.output)
    configuration={'zipcode':args.zipcode,'terms':list(TERMS),'maximum_queries':args.maximum_queries,
                   'maximum_requests':args.maximum_requests,'target':args.target,'minimum':args.minimum,
                   'canary_upc':args.canary_upc,'execution_id':args.execution_id,'run_origin':args.run_origin,
                   'output_prefix':args.output_prefix}
    with storage.locked(args.location_id):
        result=execute_once(storage,args.location_id,args.run_id,configuration,budget,
                            lambda:_collect_and_export(args,client,storage))
    print(json.dumps({'event':'api_trial_duplicate_skipped' if result['duplicate_skipped'] else 'api_trial_validated',
                      **result,'submission_ready':False}),flush=True)


def _collect_and_export(args,client,storage):
    status=collect(client,storage,args.location_id,args.zipcode,args.run_id,TERMS,args.maximum_queries,args.target,args.canary_upc)
    with tempfile.TemporaryDirectory(prefix='marianos-api-') as scratch:
        source=Path(scratch)/'source';source.mkdir()
        prefix=status['source_prefix']
        for name in ['verified_store.json']+[f'page_{i:02d}.json' for i in range(len(status['completed_terms']))]:
            (source/name).write_bytes(storage.read(prefix+'/'+name))
        export=Path(scratch)/'normalized'
        destination=f'{args.output_prefix}/{args.location_id}'
        prior=storage.read(destination+'/latest.json')
        if prior:
            export.mkdir();(export/'latest.json').write_bytes(prior)
            pointer=json.loads(prior)
            for field in ('data_key','report_key','provenance_key','retention_key'):
                if pointer.get(field):
                    key=pointer[field]
                    if not key.startswith('runs/') or '..' in key or '\\' in key:raise ValueError('INVALID_PRIOR_OUTPUT_KEY')
                    body=storage.read(destination+'/'+key)
                    if body is None:raise ValueError('PRIOR_OUTPUT_MISSING')
                    target=export/key;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(body)
        report=import_snapshot(source,export,args.location_id,args.zipcode,args.minimum)
        pointer=json.loads((export/'latest.json').read_text(encoding='utf-8'))
        destination=f'{args.output_prefix}/{args.location_id}'
        previous=storage.read(destination+'/latest.json')
        if previous and report['current_records']<int(json.loads(previous).get('current_records',json.loads(previous).get('records',0)))*0.8:
            raise ValueError('MATERIAL_YIELD_DROP: previous trial preserved')
        for file in (export/'runs').rglob('*.json'):
            if hasattr(storage,'assert_lock_held'):storage.assert_lock_held()
            storage.write(destination+'/'+file.relative_to(export).as_posix(),file.read_bytes())
    return pointer,{'records':report['records'],'product_queries':status['new_queries_this_run'],
                    'cached_product_pages':status['cached_queries_this_run']}

if __name__=='__main__':
    try:main()
    except Exception as exc:
        print(json.dumps({'event':'api_trial_failed','error_type':type(exc).__name__,
                          'notice':'Checkpoints preserved; no final acceptance claimed.'}),flush=True)
        raise SystemExit(1)
