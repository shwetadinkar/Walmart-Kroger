# OPD integration verification

Execution date: 2026-10-20.

- The adapter is implemented for **documented official endpoints**, including signed compressed product and store-pricing snapshots.
- The Walmart OPD adapter is integrated into `python -m walmart_collector run --source opd`.
- Offline tests cover two stores, joining offerId/store-specific prices, marketplace exclusion, PPM preservation, subcategory assignment, recovery/publisher preservation and JSON streaming.
- **No authenticated API run was possible**, because approved Walmart credentials were not provided.
- The 500 real-record live proof and observed Azure run remain outstanding.
- Exact category/subcategory completeness, price-role distinction, promotional prices and local pickup verification require further source coverage or client sign-off.

## Local test commands actually run

```bash
python -m unittest discover -q tests   # 35 tests, passed
python tools/client_acceptance.py offline --store both  # exit 0; 13 synthetic records/store
WALMART_DATA_AUTHORIZED=yes python -m walmart_collector run --source opd --store 100 --authorized-source --only-categories Food,Beauty --minimum-products 500  # exit 1: missing client credentials (expected)
```

The offline acceptance command uses the pre-existing synthetic fixtures; the OPD integration tests use mocked documented catalog and pricing API feed shapes. **No real feed was downloaded.**
