"""Zero-credential verification for a fresh client handover.

Runs only offline/synthetic checks. NEVER sends requests to Walmart.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIELDS = (
    'zipcode','store_name','store_location','store_logo','store_brand','category',
    'sub_category','product_title','weight','regular_price','sale_price',
    'volume_deals_description','volume_deals_price','digital_deals_description',
    'digital_deals_price','image_url','url','upc','gupc','ppm','unit_price','crawl_date'
)


def call(args: list[str], cwd=ROOT, env=None) -> dict:
    p = subprocess.run([sys.executable, *args], cwd=cwd, text=True, env=env,
                       capture_output=True, errors='replace')
    return {'exit_code': p.returncode, 'stdout': p.stdout, 'stderr': p.stderr}


def main() -> int:
    parser = argparse.ArgumentParser(description='Offline-only verified client preflight (never calls Walmart)')
    parser.add_argument('--report', type=Path, default=ROOT / 'client-test-output/preflight-report.json')
    args = parser.parse_args()
    checks = []
    def check(name, ok, detail):
        checks.append({'name': name, 'passed': bool(ok), 'detail': detail})
        print(('PASS' if ok else 'FAIL') + '  ' + name + ': ' + detail)

    check('Supported Python', sys.version_info >= (3, 11), sys.version.split()[0])
    with tempfile.TemporaryDirectory(prefix='walmart-preflight-') as d:
        tmp = Path(d)
        suite = call(['-W', 'always::ResourceWarning', '-m', 'unittest', 'discover', '-v', 'tests'])
        warnings = 'ResourceWarning' in suite['stderr'] or 'ResourceWarning' in suite['stdout']
        count_line = next((line.strip() for line in suite['stderr'].splitlines()
                           if line.startswith('Ran ') and 'tests' in line), 'No test count found')
        check('Unit/integration suite and resource cleanup', suite['exit_code'] == 0 and not warnings
              and 'OK' in suite['stderr'], count_line + ('; resource warnings detected' if warnings else '; no ResourceWarning'))

        offline = call(['tools/client_acceptance.py', 'offline', '--store', 'both', '--output', str(tmp / 'offline')])
        report = tmp / 'offline/offline-test-report.json'
        proof = json.loads(report.read_text()) if report.is_file() else {}
        checks_offline = proof.get('checks') or {}
        stores = checks_offline.get('store_tests') or []
        ok = (offline['exit_code'] == 0 and proof.get('passed') is True and
              proof.get('produced_real_walmart_data') is False and
              {x['store_id'] for x in stores} == {'100', '5959'} and
              all(x['passed'] and x['categories'] == 11 for x in stores))
        check('Two-store synthetic acceptance', ok,
              f"{len(stores)} stores; "+', '.join(f"{s['store_id']}={s['records']} synthetic rows" for s in stores))

        dry = call(['tools/walmart_opd_smoke_test.py', '--store', 'both', '--dry-run'])
        check('Walmart request dry-run (NO HTTP)', dry['exit_code'] == 0,
              'Request layout only; never authenticated or connected to Walmart')

        dest = tmp / 'valid'
        fixture = call(['-m', 'walmart_collector', 'run', '--source', 'fixture',
                        '--store', '100', '--output', str(dest)])
        target = tmp / 'candidate-SYNTHETIC.json'
        export = call(['-m', 'walmart_collector', 'export', '--store', '100',
                       '--output', str(dest), '--export-file', str(target)])
        rows = json.loads(target.read_text(encoding='utf-8')) if target.is_file() else []
        fields_ok = (bool(rows) and all(list(row) == list(FIELDS) and
                       all(isinstance(v, str) for v in row.values()) and
                       row['gupc'] == row['unit_price'] == '' for row in rows))
        check('Exact 22-field JSON export (SYNTHETIC)',
              fixture['exit_code'] == export['exit_code'] == 0 and fields_ok,
              f'{len(rows)} synthetic rows; correct field order and blank downstream fields')

        rejected = tmp / 'should_fail'
        reject = call(['-m', 'walmart_collector', 'run', '--source', 'fixture',
                       '--store', '100', '--output', str(rejected), '--minimum-products', '500'])
        status = call(['-m', 'walmart_collector', 'status', '--store', '100', '--output', str(rejected)])
        state = json.loads(status['stdout']) if status['exit_code'] == 0 else {}
        check('Reject insufficient records without publication',
              reject['exit_code'] != 0 and status['exit_code'] == 0 and state.get('latest') is None,
              f'Rejected as expected (exit {reject["exit_code"]}); latest={state.get("latest")}')

        # Remove all potential live access from this subprocess. This preflight
        # must remain 100% offline even on a developer machine with credentials.
        blocked_env = os.environ.copy()
        for name in ('WALMART_OPD_CLIENT_ID', 'WALMART_OPD_CLIENT_SECRET',
                     'PROVIDER_BASE_URL', 'PROVIDER_API_TOKEN'):
            blocked_env.pop(name, None)
        blocked_env['WALMART_DATA_AUTHORIZED'] = 'no'
        no_keys = call(['-m', 'walmart_collector', 'run', '--source', 'opd',
                        '--store', '100', '--authorized-source', '--output', str(tmp / 'no-keys')],
                       env=blocked_env)
        # Running with --authorized-source but *without* affirmative env must reject.
        check('OPD fails closed with no authorization affirmation',
              no_keys['exit_code'] != 0, 'No live requests; permission affirmation not supplied')

    result = {'version': '0.4.1', 'generated_utc': datetime.now(timezone.utc).isoformat(),
              'mode': 'OFFLINE_PRE_CLIENT_TEST_ONLY',
              'passed': all(x['passed'] for x in checks), 'checks': checks,
              'live_api_tested': False, 'real_product_records': 0,
              'azure_deployment_tested': False,
              'remaining': ['Client Walmart OPD authorization and scopes',
                            'Taxonomy mappings / store-specific pickup checks',
                            'Actual 500 product sample and promotions audit',
                            'Azure deployment with persistent cache and secrets']}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('\nOFFLINE PREFLIGHT: ' + ('PASSED' if result['passed'] else 'FAILED'))
    print('Report: ' + str(args.report))
    print('Real Walmart products collected: 0. Do NOT submit this as live data evidence.')
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
