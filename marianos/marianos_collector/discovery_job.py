"""Configured unattended discovery; no successful-product pointer is modified."""
import argparse,hashlib,json,re,uuid
from datetime import datetime,timezone
from pathlib import Path
from .production_config import validate_discovery_config
from .category_traversal import CategoryTraversal,CategoryAccessBlocked,encoded
from .storage import LocalStorage,AzureBlobStorage
from .operations import save_execution_report

def _now():return datetime.now(timezone.utc)

def run_discovery(document,storage,run_id,driver_factory):
    c=validate_discovery_config(document)
    if not isinstance(run_id,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}',run_id):raise ValueError('DISCOVERY_EXECUTION_ID')
    sid=c['store']['id'];prefix=f"{c['output_prefix']}/{sid}/{run_id}"
    digest=hashlib.sha256(encoded(c)).hexdigest()
    with storage.locked(sid):
        raw=storage.read(prefix+'/budget.json')
        state=json.loads(raw) if raw else {'config_sha256':digest,'started_at':_now().isoformat(),'actions':0,'page_actions':0}
        if state['config_sha256']!=digest:raise ValueError('DISCOVERY_CONFIGURATION_CHANGED')
        if state.get('access_blocked'):raise CategoryAccessBlocked('DISCOVERY_ACCESS_BLOCKED_STOP')
        previous=storage.read(prefix+'/receipt.json')
        if previous and json.loads(previous)['status'] in ('completed','incomplete'):
            return json.loads(storage.read(prefix+'/coverage.json'))
        storage.write(prefix+'/configuration.json',encoded(c))
        storage.write(prefix+'/budget.json',encoded(state))
        def remaining():return c['limits']['wall_seconds']-(_now()-datetime.fromisoformat(state['started_at'])).total_seconds()
        def guard(kind='action'):
            if remaining()<=0:raise RuntimeError('DISCOVERY_WALL_BUDGET_EXHAUSTED')
            if state['actions']>=c['limits']['browser_actions']:raise RuntimeError('DISCOVERY_ACTION_BUDGET_EXHAUSTED')
            if kind=='page':
                if state.get('page_actions',0)>=c['limits']['total_pages']:raise RuntimeError('DISCOVERY_PAGE_BUDGET_EXHAUSTED')
                state['page_actions']=state.get('page_actions',0)+1
            state['actions']+=1
            storage.write(prefix+'/budget.json',encoded(state)) # count before any external action, including bootstrap
        receipt={'execution_id':run_id,'store_id':sid,'started_at':state['started_at'],'status':'running','submission_ready':False}
        storage.write(prefix+'/receipt.json',encoded(receipt));driver=None;report=None
        try:
            if remaining()<=0:raise RuntimeError('DISCOVERY_WALL_BUDGET_EXHAUSTED')
            driver=driver_factory(c,guard,remaining())
            report=CategoryTraversal(storage,driver,c['roots'],sid,c['store']['zipcode'],run_id,
                max_categories=c['limits']['categories'],maximum_pages=c['limits']['pages_per_category'],
                maximum_total_pages=c['limits']['total_pages'],output_prefix=c['output_prefix']).run()
            report.update(automated_driver_invoked=True,product_extraction_complete=False,variant_discovery_complete=False,
                          source_is_synthetic=driver.source_kind=='synthetic-fixture',submission_ready=False)
            storage.write(prefix+'/coverage.json',encoded(report))
            receipt['status']='completed' if report['all_roots_complete'] else 'incomplete'
            receipt.update(pages_observed=report['pages_observed'],pending_nodes=report['pending_nodes'],source_kind=driver.source_kind)
            return report
        except Exception as exc:
            evidence=getattr(exc,'discovery_evidence',None)
            if evidence is None and driver is not None and callable(getattr(driver,'capture_failure',None)):
                try:evidence=driver.capture_failure()
                except Exception:receipt['failure_capture_unavailable']=True
            if evidence is not None:
                storage.write(prefix+'/failure-source.json',encoded(evidence))
                if evidence.get('error_code'):receipt['error_code']=evidence['error_code']
            if isinstance(exc,CategoryAccessBlocked):
                state['access_blocked']=True;storage.write(prefix+'/budget.json',encoded(state))
                receipt['status']='access_blocked'
            else:receipt['status']='failed'
            # Raw exception strings may contain URLs/headers; evidence belongs in controlled source files.
            receipt['error_type']=type(exc).__name__
            raise
        finally:
            receipt.update(finished_at=_now().isoformat(),browser_actions_consumed=state['actions'],page_navigation_actions_consumed=state.get('page_actions',0))
            storage.write(prefix+'/receipt.json',encoded(receipt))
            save_execution_report(storage,prefix+'/operational-report.json','discovery',receipt,c,report)
            if driver is not None:driver.close()

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config',type=Path,required=True);p.add_argument('--run-id',default=None)
    p.add_argument('--output',type=Path);p.add_argument('--backend',choices=['local','azure'],default='local')
    p.add_argument('--container',default='retail-collection')
    args=p.parse_args();c=validate_discovery_config(json.loads(args.config.read_text(encoding='utf-8-sig')))
    if args.backend=='local' and args.output is None:p.error('--output is required for local storage')
    storage=LocalStorage(args.output) if args.backend=='local' else AzureBlobStorage.from_environment(args.container)
    from .browser_session import create_discovery_driver
    if args.run_id:run_id=args.run_id
    elif args.backend=='azure':
        from .run_context import execution_context
        run_id=execution_context().run_id
    else:run_id='local-'+uuid.uuid4().hex
    try:
        result=run_discovery(c,storage,run_id,create_discovery_driver)
    except Exception as exc:
        print(json.dumps({'execution_id':run_id,'status':'access_blocked' if isinstance(exc,CategoryAccessBlocked) else 'failed','error_type':type(exc).__name__,'receipt_prefix':f"{c['output_prefix']}/{c['store']['id']}/{run_id}",'submission_ready':False}))
        return 2
    print(json.dumps({'execution_id':run_id,'status':'discovery_finished','complete_listing_roots':result['complete_roots'],'configured_roots':len(c['roots']),'pages_observed':result['pages_observed'],'submission_ready':False}))
    return 0 if result['all_roots_complete'] else 2

if __name__=='__main__':raise SystemExit(main())
