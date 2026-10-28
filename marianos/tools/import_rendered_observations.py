"""Reproduce a bounded private export from rendered observations; no network calls.

Output must be a new directory. It never changes a production/latest pointer.
"""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from marianos_collector.rendered_product import parse_collection


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', type=Path, required=True)
    p.add_argument('--store', type=Path, required=True, help='JSON with id, name, street, zipcode')
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--previous-products', type=Path)
    p.add_argument('--previous-retention', type=Path)
    args = p.parse_args()
    if bool(args.previous_products) != bool(args.previous_retention):
        p.error('Both previous products and retention are required together')
    read = lambda f: json.loads(f.read_text(encoding='utf-8-sig'))
    result = parse_collection([read(f) for f in sorted(args.source.glob('PDP_*.json'))],
        read(args.store), read(args.source / 'CURRENT_STORE.json'),
        previous_rows=read(args.previous_products) if args.previous_products else None,
        previous_retention=read(args.previous_retention) if args.previous_retention else None)
    args.output.mkdir(parents=True, exist_ok=False)
    for name, value in result.items():
        (args.output / (name + '.json')).write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding='utf-8')
    print(json.dumps(result['acceptance']))


if __name__ == '__main__':
    main()
