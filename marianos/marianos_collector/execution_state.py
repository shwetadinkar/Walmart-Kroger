"""Durable execution receipts. Caller must hold the existing per-store lock."""
from datetime import datetime, timezone
import hashlib
import json
import re
from .operations import save_execution_report


def _encode(value):
    return json.dumps(value,sort_keys=True,indent=2,allow_nan=False).encode()


def execute_once(storage,store_id,run_id,configuration,budget,work):
    if not re.fullmatch(r'\d{8}',store_id) or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}',run_id):
        raise ValueError('Invalid execution storage identity')
    receipt_key=f'executions/{store_id}/{run_id}.json'
    output_prefix=configuration.get('output_prefix','trials')
    if not isinstance(output_prefix,str) or not re.fullmatch(r'[a-z][a-z0-9-]{0,39}',output_prefix):
        raise ValueError('Invalid output namespace')
    destination=f'{output_prefix}/{store_id}'
    config_hash=hashlib.sha256(_encode(configuration)).hexdigest()
    previous=storage.read(receipt_key)
    receipt=json.loads(previous) if previous else {
        'run_id':run_id,'store_id':store_id,'config_sha256':config_hash,
        'started_at':datetime.now(timezone.utc).isoformat(),'attempted_requests':0,'state':'started'}
    if receipt.get('config_sha256')!=config_hash:
        raise ValueError('EXECUTION_CONFIGURATION_MISMATCH')

    def save():
        if hasattr(storage,'assert_lock_held'):storage.assert_lock_held()
        storage.write(receipt_key,_encode(receipt))

    def verify_immutable():
        hashes=receipt.get('object_sha256',{})
        if not hashes:raise ValueError('EXECUTION_RECEIPT_MISSING_OBJECTS')
        for key,digest in hashes.items():
            body=storage.read(destination+'/'+key)
            if body is None or hashlib.sha256(body).hexdigest()!=digest:
                raise ValueError('EXECUTION_RECEIPT_OBJECT_CORRUPT')

    if receipt['state']=='completed':
        verify_immutable()
        return {**receipt['metrics'],'original_product_queries':receipt['metrics'].get('product_queries',0),
                'product_queries':0,'cached_product_pages':0,'duplicate_skipped':True,'execution_run_id':run_id,
                'network_requests':0,'execution_network_requests':receipt['attempted_requests']}
    budget.used=int(receipt['attempted_requests'])
    if not 0<=budget.used<=budget.maximum:raise ValueError('INVALID_PERSISTED_REQUEST_BUDGET')
    requests_before=budget.used
    def counted(used):
        receipt['attempted_requests']=used
        save()
    budget.on_attempt=counted
    try:
        if receipt['state']!='validated':
            receipt['state']='running';save()
            pointer,metrics=work()
            hashes={}
            for field in ('data_key','report_key','provenance_key')+tuple(f for f in ('retention_key',) if pointer.get(f)):
                key=pointer[field]
                if not isinstance(key,str) or not key.startswith('runs/') or '..' in key or '\\' in key:
                    raise ValueError('INVALID_IMMUTABLE_OUTPUT_KEY')
                body=storage.read(destination+'/'+key)
                if body is None:raise ValueError('VALIDATED_OUTPUT_MISSING')
                hashes[key]=hashlib.sha256(body).hexdigest()
            pointer={**pointer,'execution_run_id':run_id,'execution_started_at':receipt['started_at']}
            receipt.update(state='validated',pointer=pointer,metrics=metrics,object_sha256=hashes)
            save()
        verify_immutable()
        latest_body=storage.read(destination+'/latest.json')
        latest=json.loads(latest_body) if latest_body else {}
        newer=latest.get('execution_started_at','')>receipt['started_at']
        if not newer:
            if hasattr(storage,'assert_lock_held'):storage.assert_lock_held()
            storage.write(destination+'/latest.json',_encode(receipt['pointer']))
        receipt.update(state='completed',finished_at=datetime.now(timezone.utc).isoformat(),
                       superseded_by_later_success=bool(newer))
        receipt['duration_seconds']=(datetime.fromisoformat(receipt['finished_at'])-
                                     datetime.fromisoformat(receipt['started_at'])).total_seconds()
        save()
        return {**receipt['metrics'],'duplicate_skipped':False,'execution_run_id':run_id,
                'network_requests':budget.used-requests_before,'execution_network_requests':budget.used,
                'duration_seconds':receipt['duration_seconds'],'superseded_by_later_success':bool(newer)}
    except Exception as exc:
        # Keep a validated candidate resumable if pointer publication failed.
        receipt['state']='validated' if receipt['state'] in ('validated','completed') else 'failed'
        receipt['last_error_type']=type(exc).__name__
        save()
        raise
    finally:
        budget.on_attempt=None
        save_execution_report(storage,f'executions/{store_id}/{run_id}.operations.json','api-trial',receipt,configuration)
