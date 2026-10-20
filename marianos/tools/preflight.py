"""Offline self-test: no retailer or Azure connections."""
import json
import subprocess
import sys
import tempfile
from pathlib import Path
root=Path(__file__).resolve().parent.parent

def cmd(*args):
    result=subprocess.run([sys.executable,*args],cwd=root,text=True,capture_output=True)
    return {'code':result.returncode,'stdout':result.stdout,'stderr':result.stderr}

def run():
    results={}
    tests=cmd('-m','unittest','discover','-v','tests')
    results['unit_tests_passed']=tests['code']==0
    results['unit_test_summary']=tests['stderr'].splitlines()[-3:]
    with tempfile.TemporaryDirectory(prefix='marianos-preflight-') as temp:
        for sid in ['DEMO-LAKESHORE-60601','DEMO-WESTLOOP-60661']:
            result=cmd('-m','marianos_collector','run','--source','fixture','--store',sid,'--output',temp)
            results[sid+'_fixture_run']=result['code']==0
            exported=Path(temp)/(sid+'.json')
            exp=cmd('-m','marianos_collector','export','--store',sid,'--output',temp,'--export-file',str(exported))
            rows=json.loads(exported.read_text()) if exported.exists() else []
            results[sid+'_exact_22_field_records']=(exp['code']==0 and len(rows)==28 and all(
                  len(r)==22 and list(r)[-1]=='crawl_date' and r['gupc']==r['unit_price']=='' for r in rows))
        rejected=cmd('-m','marianos_collector','run','--source','fixture','--store','DEMO-LAKESHORE-60601','--minimum-products','500','--output',str(Path(temp)/'reject'))
        status=cmd('-m','marianos_collector','status','--store','DEMO-LAKESHORE-60601','--output',str(Path(temp)/'reject'))
        results['reject_insufficient_500']=rejected['code']!=0 and 'Only 28 valid' in rejected['stderr']
        results['never_publish_failed_run']=status['code']==0 and json.loads(status['stdout'])['latest'] is None
    # Full-scale synthetic integration: 560 products, 28 roots, crash/restart,
    # repeated placements and trial/full release isolation. Never live evidence.
    for sid in ['DEMO-LAKESHORE-60601','DEMO-WESTLOOP-60661']:
        sim=cmd('tools/acceptance_simulation.py','--store',sid)
        try:
            parsed=json.loads(sim['stdout'])
        except (ValueError, TypeError):
            parsed={}
        results[sid+'_560_SYNTHETIC_acceptance_simulation']=(
            sim['code']==0 and parsed.get('passed') is True and
            parsed.get('simulated_unique_records')==560 and
            parsed.get('contest_submission_evidence') is False)
    results['offline_passed']=all(v for k,v in results.items() if isinstance(v,bool))
    (root/'client-test-output').mkdir(exist_ok=True)
    (root/'client-test-output'/'preflight.json').write_text(json.dumps(results,indent=2))
    print(json.dumps(results,indent=2))
    return 0 if results['offline_passed'] else 1
if __name__=='__main__':raise SystemExit(run())
