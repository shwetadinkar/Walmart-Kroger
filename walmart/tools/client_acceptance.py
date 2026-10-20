"""Reproducible test handover for the retailer-data project.

Modes:
  offline: zero network or secrets; real HTTP adapter tested via mocks + fixture end-to-end.
  opd: official Walmart I/O OAuth / store locator ONLY, using approved OPD credentials.
  provider: full collector through an independently provisioned authorized normalized feed.

These modes must never be confused with one another when reporting evidence.
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
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from walmart_collector.config import categories_from_csv, stores_from_json
from walmart_collector.runner import Collector
from walmart_collector.sources import FixtureSource, AuthorizedProviderSource
from walmart_collector.storage import LocalStorage, read_json


def timestamp():
    return datetime.now(timezone.utc).isoformat()


def save_report(directory: Path, name: str, report: dict):
    directory.mkdir(parents=True, exist_ok=True)
    file = directory / name
    file.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(f"Result report: {file}")


def selected_stores(value):
    stores = stores_from_json(ROOT / 'config/stores.json')
    selected = stores if value == 'both' else [s for s in stores if s.store_id == value]
    if not selected:
        raise ValueError(f"Unconfigured store: {value}")
    return selected


def run_offline(args):
    # Running the unittest suite also runs mocked-network tests of the live adapter.
    cp = subprocess.run([sys.executable, '-m', 'unittest', 'discover', '-v', 'tests'],
                        cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    print(cp.stdout)
    checks = {"unit_tests_passed": cp.returncode == 0, "store_tests": []}
    if cp.returncode == 0:
        categories = categories_from_csv(ROOT / 'config/categories.csv')
        for store in selected_stores(args.store):
            with tempfile.TemporaryDirectory(prefix=f"walmart-test-{store.store_id}-") as d:
                storage = LocalStorage(Path(d))
                result = Collector(storage, FixtureSource(ROOT / 'fixtures'), categories,
                                   min_products=11).run(store)
                rows = read_json(storage, result['manifest']['data_key'])
                report = result['report']
                checks['store_tests'].append({
                    'store_id': store.store_id, 'zipcode': store.zipcode,
                    'records': len(rows), 'categories': len(report['category_counts']),
                    'source': 'SYNTHETIC_OFFLINE_FIXTURES',
                    'passed': len(rows) == 13 and len(report['category_counts']) == 11
                               and all(r['zipcode'] == store.zipcode for r in rows)
                })
    passed = checks['unit_tests_passed'] and all(item['passed'] for item in checks['store_tests'])
    result = {"mode": "OFFLINE_TEST_ONLY", "time_utc": timestamp(), "passed": passed,
              "produced_real_walmart_data": False,
              "proves_live_walmart_api_access": False,
              "checks": checks}
    save_report(args.output, 'offline-test-report.json', result)
    print(json.dumps(result, indent=2))
    return 0 if passed else 1


def run_opd(args):
    command = [sys.executable, str(ROOT / 'tools/walmart_opd_smoke_test.py'), '--store', args.store]
    if args.catalog:
        command.append('--catalog')
    p = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
    if p.stdout:
        print(p.stdout)
    if p.stderr:
        print(p.stderr, file=sys.stderr)
    report = {"mode": "WALMART_OPD_CONNECTIVITY_ONLY", "time_utc": timestamp(),
              "passed": p.returncode == 0, "exit_code": p.returncode,
              "produced_real_walmart_product_records": False,
              "proves_store_price_collection": False,
              "note": "OAuth / store locator / optional feed metadata ONLY. Not integrated with the 500-product collector.",
              "probe_output": p.stdout.strip(), "error_output": p.stderr.strip()}
    save_report(args.output, 'opd-connectivity-report.json', report)
    return p.returncode


def run_provider(args):
    endpoint = os.environ.get('PROVIDER_BASE_URL', '')
    token = os.environ.get('PROVIDER_API_TOKEN', '')
    if not args.confirm_authorized or os.environ.get('WALMART_DATA_AUTHORIZED') != 'yes':
        print('Provider mode requires --confirm-authorized and WALMART_DATA_AUTHORIZED=yes.', file=sys.stderr)
        return 2
    if not endpoint or not token:
        print('Provider mode needs PROVIDER_BASE_URL + PROVIDER_API_TOKEN for a compatible authorized feed. '
              'Walmart OPD client ID / secret alone are NOT sufficient.', file=sys.stderr)
        return 2
    if args.minimum_products < 1:
        print('--minimum-products must be positive', file=sys.stderr)
        return 2
    cats = categories_from_csv(ROOT / 'config/categories.csv')
    stores = selected_stores(args.store)
    source = AuthorizedProviderSource(endpoint, token)
    statuses = []
    for store in stores:
        try:
            storage = LocalStorage(args.output / 'private-collection-data')
            result = Collector(storage, source, cats, min_products=args.minimum_products).run(store)
            data = read_json(storage, result['manifest']['data_key'])
            export = args.output / f"candidate_store_{store.store_id}.json"
            export.parent.mkdir(parents=True, exist_ok=True)
            export.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
            validation = result['report']
            report_file = args.output / f"candidate_store_{store.store_id}_report.json"
            report_file.write_text(json.dumps(validation, indent=2) + '\n', encoding='utf-8')
            statuses.append({"store_id":store.store_id, "zipcode":store.zipcode, "passed_pipeline":True,
                             "count": len(data), "categories":len(validation['category_counts']),
                             "json_path":str(export), "validation_report_path":str(report_file),
                             "requires_manual_retailer_comparison":True})
        except Exception as exc:
            statuses.append({"store_id":store.store_id, "zipcode":store.zipcode,
                             "passed_pipeline":False, "error":str(exc)})
    passed = all(s['passed_pipeline'] for s in statuses)
    report = {"mode":"AUTHORIZED_FEED_CANDIDATE", "time_utc":timestamp(),
              "passed":passed, "fully_contest_verified":False,
              "note":"Review source licence, local prices, original UPC/PPM, coupons and fulfillment with the customer. This harness does not certify these independently.",
              "minimum_products_per_store":args.minimum_products, "store_results":statuses}
    save_report(args.output, 'provider-test-report.json', report)
    print(json.dumps(report, indent=2))
    return 0 if passed else 1


def main():
    parser = argparse.ArgumentParser(description='Offline, official API, and authorized provider testing with truthful reports')
    parser.add_argument('mode', choices=['offline','opd','provider'])
    parser.add_argument('--store', choices=['both','100','5959'], default='both')
    parser.add_argument('--output', type=Path, default=ROOT / 'client-test-output')
    parser.add_argument('--catalog', action='store_true', help='OPD only: query catalog feed metadata')
    parser.add_argument('--confirm-authorized', action='store_true', help='Provider only: affirm that feed access and use are authorized')
    parser.add_argument('--minimum-products', type=int, default=500)
    args = parser.parse_args()
    try:
        if args.mode == 'offline':
            return run_offline(args)
        if args.mode == 'opd':
            return run_opd(args)
        return run_provider(args)
    except Exception as exc:
        print(f'Acceptance test error: {exc}', file=sys.stderr)
        return 1

if __name__ == '__main__':
    raise SystemExit(main())
