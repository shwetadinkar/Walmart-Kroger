"""Local operator checks and safe, explicitly non-acceptance operational reports.

This module never constructs a browser, network client or cloud storage adapter.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import logging
from pathlib import Path
import re

from .production_config import validate_discovery_config
from .storage import LocalStorage

LIMITATIONS = [
    'Full unattended live category/product acceptance remains unverified.',
    'Displayed PPM and complete volume/digital offer coverage remain unverified.',
    'Public API access does not establish partner catalog entitlement.',
    'Offline results and configuration checks are not live source acceptance.',
]


def _cron(value):
    for field, (low, high) in zip(value.split(), [(0,59),(0,23),(1,31),(1,12),(0,7)]):
        for part in field.split(','):
            base, *step = part.split('/')
            if len(step)>1 or (step and (not step[0].isdigit() or not 1<=int(step[0])<=high-low+1)):
                raise ValueError('DISCOVERY_SCHEDULE_RANGE')
            if base=='*':continue
            bounds=base.split('-')
            if len(bounds)>2 or any(not x.isdigit() for x in bounds):raise ValueError('DISCOVERY_SCHEDULE_RANGE')
            nums=[int(x) for x in bounds]
            if any(not low<=x<=high for x in nums) or nums[0]>nums[-1]:raise ValueError('DISCOVERY_SCHEDULE_RANGE')


def check_configuration(document, expected_store=None, expected_zip=None):
    c=validate_discovery_config(document)
    _cron(c['schedule']['cron_utc'])
    if expected_store is not None and expected_store!=c['store']['id']:raise ValueError('STORE_CONFIGURATION_MISMATCH')
    if expected_zip is not None and expected_zip!=c['store']['zipcode']:raise ValueError('ZIP_CONFIGURATION_MISMATCH')
    return {'report_version':1,'kind':'configuration_check','status':'valid',
            'store_id':c['store']['id'],'zipcode':c['store']['zipcode'],
            'configured_roots':len(c['roots']),'limits':c['limits'],
            'output_prefix':c['output_prefix'],'schedule_enabled':False,
            'live_store_verified':False,'submission_ready':False,'limitations':list(LIMITATIONS)}


def _count(value):
    if value is None:return None
    if type(value) is not int or value<0:raise ValueError('REPORT_INVALID_COUNT')
    return value


def _identity(value, pattern):
    if value is None:return None
    if not isinstance(value,str) or not re.fullmatch(pattern,value):raise ValueError('REPORT_INVALID_IDENTITY')
    return value


def _timestamp(value):
    if value is None:return None
    try:
        date=datetime.fromisoformat(value.replace('Z','+00:00'))
        if date.tzinfo is None:raise ValueError()
        return date.astimezone(timezone.utc).isoformat()
    except (TypeError,ValueError,AttributeError):raise ValueError('REPORT_INVALID_TIMESTAMP') from None


def build_report(mode, receipt, configuration=None, validation=None, coverage=None):
    if mode not in ('discovery','api-trial','collection'):raise ValueError('REPORT_MODE')
    documents=[receipt]+[x for x in (configuration,validation,coverage) if x is not None]
    if any(not isinstance(x,dict) for x in documents):raise ValueError('REPORT_OBJECT_REQUIRED')
    c=configuration or {};v=validation or {};cov=coverage or {}
    sid=_identity(receipt.get('store_id'),r'\d{8}|DEMO-[A-Z0-9-]{1,60}')
    run=_identity(receipt.get('execution_id',receipt.get('run_id')),r'[A-Za-z0-9_-]{1,80}')
    if sid is None:raise ValueError('REPORT_STORE_REQUIRED')
    zipcodes=[]
    for doc in documents:
        store=doc.get('store',{})
        if not isinstance(store,dict):raise ValueError('REPORT_STORE_OBJECT')
        for candidate in (doc.get('store_id'),store.get('id')):
            if candidate is not None and candidate!=sid:raise ValueError('REPORT_STORE_MISMATCH')
        for candidate in (doc.get('execution_id'),doc.get('run_id')):
            if run is not None and candidate is not None and candidate!=run:raise ValueError('REPORT_EXECUTION_MISMATCH')
        for zipcode in (doc.get('zipcode'),store.get('zipcode')):
            if zipcode is not None:zipcodes.append(_identity(zipcode,r'\d{5}'))
    if len(set(zipcodes))>1:raise ValueError('REPORT_ZIP_MISMATCH')
    status=receipt.get('status',receipt.get('state'))
    if status not in {'started','running','failed','access_blocked','validated','completed','incomplete'}:
        raise ValueError('REPORT_STATUS')
    if mode=='api-trial' and status=='validated':status='publication_pending'
    metrics=receipt.get('metrics',{})
    if not isinstance(metrics,dict):raise ValueError('REPORT_METRICS')
    flags=[doc['source_is_synthetic'] for doc in documents if 'source_is_synthetic' in doc]
    if any(type(flag) is not bool for flag in flags):raise ValueError('REPORT_SYNTHETIC_FLAG')
    source_kind=receipt.get('source_kind',cov.get('source_kind',''))
    if source_kind=='synthetic-fixture' or str(receipt.get('source_mode','')).startswith('synthetic_fixture'):flags.append(True)
    if len(set(flags))>1:raise ValueError('REPORT_CONFLICTING_SYNTHETIC_EVIDENCE')
    synthetic=flags[0] if flags else None
    # Unknown remains unknown: an API receipt by itself is not independent source verification.
    accepted=None if mode=='discovery' else metrics.get('records',v.get('records',receipt.get('unique_records')))
    quarantine=v.get('quarantined_records')
    excluded=receipt.get('excluded_records_by_reason')
    if mode=='collection' and isinstance(excluded,dict):
        quarantine=sum(_count(x) for x in excluded.values())
    counts={'accepted_records':_count(accepted),'quarantined_records':_count(quarantine),
            'network_requests':_count(receipt.get('attempted_requests')),
            'browser_actions':_count(receipt.get('browser_actions_consumed')),
            'navigation_actions':_count(receipt.get('page_navigation_actions_consumed')),
            'pages_observed':_count(cov.get('pages_observed',receipt.get('pages_observed')))}
    complete=cov.get('all_roots_complete')
    if complete is not None and type(complete) is not bool:raise ValueError('REPORT_COVERAGE_FLAG')
    if complete is True and status!='completed':raise ValueError('REPORT_INCONSISTENT_COMPLETION')
    configured=_count(cov.get('configured_roots',len(c['roots']) if 'roots' in c else None))
    finished=_count(cov.get('complete_roots'))
    if 'roots' in c and configured!=len(c['roots']):raise ValueError('REPORT_CONFIGURED_ROOTS_MISMATCH')
    if finished is not None and configured is not None and finished>configured:raise ValueError('REPORT_IMPOSSIBLE_COVERAGE')
    if complete is True and (not configured or finished!=configured):raise ValueError('REPORT_UNPROVED_COMPLETION')
    error=receipt.get('error_code','')
    code=error if isinstance(error,str) and re.fullmatch(r'net::ERR_[A-Z0-9_]+',error) else None
    known_types={'Error','RuntimeError','ValueError','TimeoutError','CategoryAccessBlocked','OSError','SourceError','ValidationFailure'}
    error_type=receipt.get('error_type',receipt.get('last_error_type'))
    if status not in ('failed','access_blocked','validated','publication_pending'):code=None;error_type=None
    return {'report_version':1,'kind':'run_report','mode':mode,'status':status,
            'execution_id':run,'store_id':sid,'zipcode':zipcodes[0] if zipcodes else None,
            'started_at':_timestamp(receipt.get('started_at')),
            'finished_at':_timestamp(receipt.get('finished_at',receipt.get('timestamp_utc'))),
            'source_is_synthetic':synthetic,'evidence_basis':'local_artifacts_not_independent_live_acceptance',
            'counts':counts,'coverage':{'configured_roots':configured,
                'complete_listing_roots':finished,
                'listing_scope_complete':complete,'product_extraction_complete':False,
                'live_category_acceptance':False},
            'failure':{'code':code,'type':error_type if error_type in known_types else None},
            'submission_ready':False,'limitations':list(LIMITATIONS)}


def markdown(report):
    lines=["# Mariano's operational report",'',
           'This report does not establish live source acceptance. Submission ready: **false**.','']
    for key in ('kind','mode','status','execution_id','store_id','zipcode','source_is_synthetic','live_store_verified'):
        if key in report:lines.append(f'- {key}: {json.dumps(report[key])}')
    for title in ('counts','coverage','limits','failure'):
        if title in report:
            lines.extend(['',f'## {title}',''])
            lines.extend(f'- {key}: {json.dumps(value)}' for key,value in report[title].items())
    lines.extend(['','Unknown/not recorded values are shown as null; they do not mean zero.','','## Limitations',''])
    lines.extend('- '+x for x in report['limitations'])
    return '\n'.join(lines)+'\n'


def save_report(storage, key, report):
    storage.write(key,json.dumps(report,indent=2,allow_nan=False).encode('utf-8'))


def save_execution_report(storage, key, mode, receipt, configuration=None, coverage=None):
    """Supplement the authoritative receipt; never mask its source/storage failure."""
    try:
        save_report(storage,key,build_report(mode,receipt,configuration=configuration,coverage=coverage))
    except Exception:
        logging.getLogger('collector').warning('operational_report_unavailable')


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    sub=p.add_subparsers(dest='command',required=True)
    check=sub.add_parser('check');check.add_argument('--config',required=True,type=Path)
    check.add_argument('--store-id');check.add_argument('--zipcode')
    run=sub.add_parser('report');run.add_argument('--mode',required=True,choices=['discovery','api-trial','collection'])
    run.add_argument('--receipt',required=True,type=Path)
    for name in ('config','validation','coverage'):run.add_argument('--'+name,type=Path)
    for item in (check,run):item.add_argument('--output',type=Path)
    args=p.parse_args(argv)
    try:
        loaded={}
        evidence={}
        for name in ('config','receipt','validation','coverage'):
            path=getattr(args,name,None)
            if path:
                body=path.read_bytes()
                if len(body)>8_000_000:raise ValueError('REPORT_INPUT_TOO_LARGE')
                loaded[name]=json.loads(body.decode('utf-8-sig'))
                evidence[name]=hashlib.sha256(body).hexdigest()
        report=check_configuration(loaded['config'],args.store_id,args.zipcode) if args.command=='check' else build_report(
            args.mode,loaded['receipt'],loaded.get('config'),loaded.get('validation'),loaded.get('coverage'))
        report['input_sha256']=evidence
        if args.output:
            targets={args.output.resolve()/'operational-report.json',args.output.resolve()/'operational-report.md'}
            if any(getattr(args,name,None) and getattr(args,name).resolve() in targets for name in ('config','receipt','validation','coverage')):
                raise ValueError('REPORT_WOULD_OVERWRITE_INPUT')
            storage=LocalStorage(args.output)
            save_report(storage,'operational-report.json',report)
            storage.write('operational-report.md',markdown(report).encode('utf-8'))
        print(json.dumps(report,indent=2,allow_nan=False))
        return 0 if report['status'] in ('valid','completed','validated') else 2
    except (ValueError,TypeError,KeyError,OSError) as exc:
        # Do not echo paths, untrusted data, URLs or exception messages.
        code=str(exc)
        if not re.fullmatch(r'[A-Z][A-Z0-9_]{1,79}',code):code='LOCAL_INPUT_OR_OUTPUT_ERROR'
        print(json.dumps({'status':'invalid','error_code':code,'submission_ready':False}))
        return 2


if __name__=='__main__':raise SystemExit(main())
