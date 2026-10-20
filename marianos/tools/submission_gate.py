"""Independent acceptance gate for observed, licensed LIVE data and manual evidence.

No test fixtures can pass this gate. Passing still requires organizer acceptance.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from marianos_collector.config import categories_from_csv, stores_from_json
from marianos_collector.schema import FIELDS
from marianos_collector.storage import LocalStorage, read_json

REVIEW_ITEMS = (
    'authorized_source_and_data_use_confirmed',
    'store_location_and_fulfillment_verified',
    'complete_28_category_and_subcategory_coverage_verified',
    'random_product_price_and_upc_spot_checks_passed',
    'ppm_volume_and_digital_deals_spotchecked',
    'source_generated_real_records_confirmed',
    'restart_recovery_observed',
    'repeat_run_consistency_observed',
    'azure_scheduled_job_observed',
)

def run(store_id, output, stores_file, categories_file, attestation_file):
    checks = {}
    problems = []
    categories = categories_from_csv(categories_file)
    configured_stores = stores_from_json(stores_file) if stores_file.is_file() else []
    store = next((s for s in configured_stores if s.store_id == store_id), None)
    checks['verified_store_configured'] = store is not None and not store_id.upper().startswith(('DEMO','REPLACE','UNRESOLVED'))
    storage = LocalStorage(output)
    pointer = read_json(storage, f'published/{store_id}/latest.json')
    checks['published_run_exists'] = bool(pointer)
    manifest = read_json(storage,pointer['manifest_key']) if pointer else None
    report = read_json(storage,manifest['report_key']) if manifest else None
    rows = read_json(storage,manifest['data_key']) if manifest else None
    checks['reports_present'] = isinstance(manifest,dict) and isinstance(report,dict) and isinstance(rows,list)
    if checks['reports_present']:
        checks['full_roots_configured'] = len(categories) == 28
        checks['published_full_scope'] = manifest.get('coverage_scope') == 'all_configured_roots' and report.get('coverage_scope') == 'all_configured_roots'
        checks['not_marked_synthetic'] = (report.get('source_is_synthetic') is False and
                                          not 'synthetic' in str(manifest.get('source_mode','')).lower())
        checks['at_least_500_unique_records'] = len(rows) >= 500 and len(rows)==manifest.get('records')
        checks['all_category_roots_reported'] = set(report.get('category_counts',{})) == {c.name for c in categories}
        checks['store_id_and_zip_match'] = bool(store) and manifest.get('store_id') == store_id and manifest.get('zipcode') == store.zipcode and all(r.get('zipcode') == store.zipcode for r in rows)
        checks['all_rows_have_exact_schema'] = all(isinstance(r,dict) and list(r) == list(FIELDS) and all(isinstance(v,str) for v in r.values()) for r in rows)
        checks['downstream_columns_blank'] = all(r.get('gupc') == '' and r.get('unit_price') == '' for r in rows)
        checks['no_synthetic_product_titles'] = all('SYNTHETIC' not in str(r.get('product_title','')).upper() for r in rows)
        checks['examples_and_counts_recorded'] = all(x in report for x in ('field_completeness','example_ppm','example_volume_deals','example_digital_deals','duplicate_placements','runtime_seconds'))
    attestation = {}
    if attestation_file and attestation_file.is_file():
        attestation = json.loads(attestation_file.read_text(encoding='utf-8'))
    checks['human_reviewer_identified'] = bool(str(attestation.get('reviewer','')).strip())
    for k in REVIEW_ITEMS:
        checks['review_' + k] = attestation.get(k) is True
    failed = [k for k,v in checks.items() if not v]
    return {
        'program': 'Marianos Collector',
        'result': 'READY_FOR_FINAL_SUBMISSION_REVIEW' if not failed else 'BLOCKED_PENDING_REAL_DATA_OR_VERIFICATION',
        'generated_at_utc': datetime.now(timezone.utc).isoformat(),
        'store_id': store_id,
        'checked_record_count': len(rows) if isinstance(rows,list) else 0,
        'checks': checks,
        'blockers': failed,
        'notice': 'Automatic checks and attestation cannot establish legal authority or truth by themselves. Final buyer inspection and retailer rights still govern.'
    }


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--store',required=True)
    p.add_argument('--output',type=Path,default=ROOT/'.collector-output')
    p.add_argument('--stores',type=Path,default=ROOT/'config/stores_live.json')
    p.add_argument('--categories',type=Path,default=ROOT/'config/categories.csv')
    p.add_argument('--attestation',type=Path,default=ROOT/'submission_evidence/observed_review.json')
    p.add_argument('--report',type=Path,default=ROOT/'submission_evidence/readiness.json')
    a=p.parse_args()
    result=run(a.store,a.output,a.stores,a.categories,a.attestation)
    a.report.parent.mkdir(parents=True,exist_ok=True)
    a.report.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result,indent=2))
    return 0 if result['result']=='READY_FOR_FINAL_SUBMISSION_REVIEW' else 1

if __name__ == '__main__':
    raise SystemExit(main())
