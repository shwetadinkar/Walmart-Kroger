"""Reprocess retained genuine evidence; controlled scenarios are never fresh source runs."""
import argparse,copy,hashlib,json,sys
from pathlib import Path
from datetime import datetime,timezone
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from marianos_collector.temporal_enrichment import merge_export
from marianos_collector.retention import stable_identity,observation,reconcile,stamp
from marianos_collector.schema import FIELDS


def build(evidence_root,output):
    root=Path(evidence_root);output=Path(output);output.mkdir(parents=True,exist_ok=True)
    p=root/'B_WEBSITE_SAMPLES_SEPARATE_DATES'/'2026-10-25_light_bulbs'
    read=lambda name:json.loads((p/name).read_text(encoding='utf-8-sig'))
    rows=read('products.json');provenance=read('provenance.json');website=read('website_evidence_parsed.json')
    document=read('verified_store.json')['data'];sid=document['locationId']
    a=merge_export(rows,provenance,[],document);b=merge_export(rows,provenance,website,document,
        previous_rows=a['products'],previous_retention=a['retention'])
    target=output/'CORRECTED_HISTORICAL_LIGHT_BULBS';target.mkdir(exist_ok=True)
    for name,value in b.items():(target/(name+'.json')).write_text(json.dumps(value,indent=2,ensure_ascii=False),encoding='utf-8')
    unavailable=next(x for x in b['products'] if any(v['upc']==x['upc'] for v in b['availability_audit']))
    original=next(x for x in rows if x['url']==unavailable['url']);identity=stable_identity(original,sid)
    at=max((m['last_observed_at'] for m in b['retention'].values()),key=stamp)
    available=next(x for x in b['products'] if x['regular_price'])
    def obs_for(r,metadata):
        m=metadata[stable_identity(r,sid)]
        return {stable_identity(r,sid):{'observed_at':m['last_observed_at'],'source_refs':m['source_refs'],
            'availability_state':m['availability_state'],'field_observed_at':m['field_observed_at']}}
    cases=[]
    def case(name,before,after,metadata,controlled,changes,refs):
        for r in (before,after):assert list(r)==list(FIELDS) and all(isinstance(v,str) for v in r.values())
        cases.append({'case':name,'before':before,'after':after,'retention':metadata,
            'controlled_replay':controlled,'changed_input_fields':changes,'source_references':refs,
            'not_a_new_live_collection':True})
    refs=[{'file':name,'sha256':hashlib.sha256((p/name).read_bytes()).hexdigest()} for name in
        ['products.json','provenance.json','website_evidence_parsed.json','verified_store.json']]
    case('available_api_then_unavailable_website',original,unavailable,b['retention'][identity],False,[],refs)
    case('api_price_then_missing_current_website_quote',original,unavailable,b['retention'][identity],False,[],refs)
    missing=copy.deepcopy(available);missing['upc']=''
    c=reconcile([missing],obs_for(missing,b['retention']),sid,at,b['products'],b['retention'])
    case('missing_upc_stable_url',available,next(x for x in c['products'] if x['url']==missing['url']),
        c['retention'][stable_identity(missing,sid)],True,['upc suppressed to exercise absent-source-field handling; original UPC remains in frozen evidence'],refs)
    current=[r for r in b['products'] if r['url']!=available['url']]
    observations={k:v for r in current for k,v in obs_for(r,b['retention']).items()}
    c=reconcile(current,observations,sid,at,b['products'],b['retention'])
    case('absent_from_later_snapshot',available,next(x for x in c['products'] if x['url']==available['url']),
        c['retention'][stable_identity(available,sid)],True,['one record deliberately omitted from replay; no claim of actual later source absence'],refs)
    old=next(r for r in rows if r['url']==available['url']);oldp=provenance[old['upc']]
    c=reconcile([old,old],{stable_identity(old,sid):observation(old,sid,oldp['observed_at'])},sid,at,
        b['products'],b['retention'])
    case('duplicate_stale_observation',available,next(x for x in c['products'] if x['url']==available['url']),
        c['retention'][stable_identity(available,sid)],True,['older actual API observation replayed twice against later website-enriched state'],refs)
    for n,item in enumerate(cases,1):
        d=output/'BEFORE_AFTER_CASES'/f'{n:02d}_{item["case"]}';d.mkdir(parents=True,exist_ok=True)
        for name in ['before','after','retention']:(d/(name+'.json')).write_text(json.dumps(item[name],indent=2,ensure_ascii=False),encoding='utf-8')
        (d/'EVIDENCE_AND_BOUNDARY.json').write_text(json.dumps({k:v for k,v in item.items() if k not in ('before','after','retention')},indent=2),encoding='utf-8')
    summary={'generated_at':datetime.now(timezone.utc).isoformat(),'historical_observation_dates':['2026-10-25'],
        'records':len(b['products']),'unavailable_in_delivered_json':len(b['availability_audit']),
        'direct_ppm_records':b['report']['field_completeness']['ppm'],'cases':len(cases),
        'genuine_api_to_website_transitions':2,'controlled_missing_field_absence_duplicate_scenarios':3,
        'live_forced_resume_proved':False,'fresh_integrated_collection':False,'submission_ready':False}
    (output/'RETENTION_EVIDENCE_SUMMARY.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    return summary

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--evidence-root',required=True,type=Path);p.add_argument('--output',required=True,type=Path)
    a=p.parse_args();print(json.dumps(build(a.evidence_root,a.output)))
