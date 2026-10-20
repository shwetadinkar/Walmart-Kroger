"""Full 28-root offline production-path exercise, using SYNTHETIC mock pages.

NEVER submit these records as retailer evidence. No network calls occur.
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from marianos_collector.config import categories_from_csv, stores_from_json
from marianos_collector.runner import Collector, ValidationFailure
from marianos_collector.sources import Page, SourceError
from marianos_collector.storage import LocalStorage, read_json


class SyntheticAcceptanceProvider:
    source_mode = "synthetic_fixture_acceptance_simulation_NEVER_CONTEST_EVIDENCE"

    def __init__(self, fail_once_at: int = -1):
        self.calls = 0
        self.fail_once_at = fail_once_at
        self.interrupted = False

    def fetch(self, store, category, url, cursor):
        self.calls += 1
        if self.calls == self.fail_once_at and not self.interrupted:
            self.interrupted = True
            raise SourceError("SIMULATED recoverable interruption")
        # 10 root products plus 10 second-page products for each of 28 roots.
        # Add a child node to exercise subcategory queue, with duplicate products
        # to validate cross-placement deduplication and count reporting.
        cats = categories_from_csv(ROOT / "config/categories.csv")
        num = next(i for i, c in enumerate(cats) if c.name == category.name)
        if '/pl/synthetic-subcategory/' in url:
            positions = (0, 1)
            next_cursor = ""
            children = []
        else:
            positions = range(0, 10) if not cursor else range(10, 20)
            next_cursor = "p2" if not cursor else ""
            # Subcategory discovery only on first root page.
            children = [{"name": category.name + " Demo Subcategory", "url": f"https://www.marianos.com/pl/synthetic-subcategory/{num:04d}"}] if not cursor else []
        products = []
        for j in positions:
            idx = num * 1000 + j
            record = {
                "product_id": f"SYNTHETIC-{store.store_id}-{idx}",
                "store_id": store.store_id,
                "zipcode": store.zipcode,
                "store_context_verified": True,
                "seller_type": "marianos",
                "fulfillment": "pickup",
                "product_title": f"SYNTHETIC TEST PRODUCT {idx} - NOT REAL RETAIL DATA",
                "weight": "12 oz",
                "brand": "Private Selection" if j == 0 else "Synthetic Mock Brand",
                "regular_price": "3.99",
                "sale_price": "3.29" if j in (0, 3) else "",
                "image_url": "",
                "url": f"https://www.marianos.com/p/synthetic-test-product-{idx}",
                "upc": f"SYNTHETIC-{idx:012d}",
                "ppm": "($0.27/oz)" if j % 4 == 0 else "",
                "volume_deals_description": "2 for $5.00" if j == 1 else "",
                "volume_deals_price": "2.50" if j == 1 else "",
                "digital_deals_description": "Clip Digital Coupon: Save $1" if j == 2 else "",
                "digital_deals_price": ""  # Do not invent unshown final coupon price.
            }
            products.append(record)
        return Page(store_id=store.store_id, zipcode=store.zipcode,
                    store_context_verified=True, source_url=url,
                    products=products, children=children, next_cursor=next_cursor,
                    subcategories_complete=True,
                    location_evidence_url="")


def execute(store_id: str = 'DEMO-LAKESHORE-60601') -> dict:
    cats = categories_from_csv(ROOT / 'config/categories.csv')
    stores = stores_from_json(ROOT / 'config/stores_demo.json')
    store = next(x for x in stores if x.store_id == store_id)
    with tempfile.TemporaryDirectory(prefix='marianos-acceptance-simulation-') as td:
        storage = LocalStorage(Path(td))
        source = SyntheticAcceptanceProvider(fail_once_at=9)
        previous_failed = False
        try:
            Collector(storage, source, cats, min_products=500).run(store)
        except SourceError as e:
            previous_failed = 'SIMULATED recoverable' in str(e)
        no_failed_publication = read_json(storage, f'published/{store.store_id}/latest.json') is None
        result = Collector(storage, source, cats, min_products=500).run(store)
        report = result['report']
        manifest = result['manifest']
        # Trial must NEVER replace the full 28-root latest pointer.
        old_ptr = read_json(storage, f'published/{store.store_id}/latest.json')
        trial = Collector(storage, SyntheticAcceptanceProvider(), cats[:2], min_products=20, trial=True).run(store)
        unchanged_full_ptr = old_ptr == read_json(storage, f'published/{store.store_id}/latest.json')
        trial_ptr = read_json(storage, f"trials/{__import__('hashlib').sha256(json.dumps([(c.name, c.url) for c in cats[:2]],sort_keys=True,separators=(',',':')).encode()).hexdigest()[:12]}/{store.store_id}/latest.json")
        # Note: the above signature matches runner's canonical hashing convention.
        assertions = {
            'simulated_interruption_detected': previous_failed,
            'simulated_failed_run_not_published': no_failed_publication,
            'successful_resume': source.interrupted,
            'all_28_roots': len(report['category_counts']) == 28,
            'at_least_500_synthetic_unique_records': report['unique_records'] == 560,
            'cross_placement_duplicates_reported': report['duplicate_placements'] >= 56,
            'ppm_samples_present': bool(report['example_ppm']),
            'volume_deal_samples_present': bool(report['example_volume_deals']),
            'digital_deal_samples_present': bool(report['example_digital_deals']),
            'trial_does_not_overwrite_full_run': unchanged_full_ptr and trial_ptr is not None,
            'simulation_correctly_marked_synthetic': report['source_is_synthetic'] is True,
            'trial_correctly_marked_subset': trial['report']['coverage_scope'] == 'subset_trial'
        }
        return {
            'kind': 'SYNTHETIC_OFFLINE_SIMULATION_ONLY',
            'generated_live_product_records': 0,
            'authorized_api_connected': False,
            'contest_submission_evidence': False,
            'tested_store': store_id,
            'simulated_unique_records': report['unique_records'],
            'categories_count': len(report['category_counts']),
            'synthetic_duplicate_placements': report['duplicate_placements'],
            'source_calls': source.calls,
            'simulation_runtime_seconds': report['runtime_seconds'],
            'checks': assertions,
            'passed': all(assertions.values())
        }


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--store', choices=['DEMO-LAKESHORE-60601','DEMO-WESTLOOP-60661'],default='DEMO-LAKESHORE-60601')
    ap.add_argument('--output',type=Path)
    args=ap.parse_args()
    result=execute(args.store)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result,indent=2))
    return 0 if result['passed'] else 1

if __name__ == '__main__':
    raise SystemExit(main())
