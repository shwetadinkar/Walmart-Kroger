# Walmart I/O OPD integration — client execution guide (v0.4.1)

**Status:** Implemented against the *documented* Walmart I/O OPD catalog, store locator, and store pricing **snapshot APIs**. The live path has NOT been run using Walmart credentials. A successful offline test is not evidence of real Walmart prices. API access and permission to collect/store/export data must be confirmed by the account holder. Do not send credentials to the developer or attach them to contest submissions.

## What is actually implemented

- OAuth client-credentials authentication with expiry-aware token refresh.
- Postal-code **pickup** store discovery; exact fulfillment store ID matching.
- Retrieve documented Product Catalog Snapshot metadata (`product_snapshot_data`) and Pricing & Availability Snapshot metadata (`price_avail_snapshot_data`) by category ID.
- Download approved signed Google Cloud Storage `.json.gz` and `.csv.gz` snapshot files, **stream** JSON and `^`-delimited CSV (no all-file RAM buffering).
- Join catalog `offerId` with `price` `offerId` and **require** `storeCode == requested store`, `availability == AVAILABLE`, no marketplace offers, no online-only offers.
- 22-field JSON, `ppm` copied directly from `unitPriceDisplay`; `upc` unchanged; `gupc` and `unit_price` empty; missing coupons/volume offers left blank; local validation and publication protections.
- SQLite file-level transactional imports with resume, category-level checkpoints and safe last-successful-release pointers.
- 11 configurable category mappings with **provisional** breadcrumb segment aliases. These need client-side taxonomy/category-coverage verification. Excluded Food `Recipes`/`Shop All Foods` and Pets `Farm Animals` are omitted.

## Key caveats

1. The **catalog and price snapshots are daily**. They are not a guarantee of identical live website prices at the time of the run.
2. The price API's `currentPrice` is a selling price. We place it in `regular_price` as a provisional output convention because the source does **not** identify a complete regular-versus-sale decomposition. **The client must approve or correct this mapping before acceptance.** We do not use `msrp` as a regular price.
3. The documented OPD snapshot schemas do **not** establish complete digital-coupon or multi-buy offer information. Fields remain empty; the contest needs a separate authorized source for promotion details.
4. The OPD taxonomy may not exactly match the category URLs and subcategory scopes in the client's CSV. `opd_category_mapping.json` is **provisional**. Compare every mapped category and descendant using Walmart's documented taxonomy API and a manual sample. A nonzero output is not proof of exhaustive coverage.
5. A product listed as available in a store-specific price snapshot may not be eligible for the exact same pickup fulfillment context on the Walmart website. Compare random records with the website or another permitted fulfillment feed.
6. Permission to access the OPD API does not necessarily grant permission to retain, bulk-extract, or resell product data for this contest. Validate scope with Walmart/the client.
7. Offline integration tests mock Walmart responses; no real product prices have been measured here.

## Prerequisites

Python 3.11+; client-owned and approved Walmart OPD credentials; Walmart OPD product-catalog and price-snapshot entitlements; permission to use downloaded data; adequate disk space to stream/index feed files. Use a **persistent** directory for `--opd-cache` on Azure. This repository has no active Walmart credentials.

## Windows PowerShell commands

```powershell
cd walmart_azure_collector
python -m unittest discover -v tests
python tools/client_acceptance.py offline --store both

$env:WALMART_OPD_CLIENT_ID="YOUR_APPROVED_CLIENT_ID"
$env:WALMART_OPD_CLIENT_SECRET="YOUR_APPROVED_SECRET"
$env:WALMART_DATA_AUTHORIZED="yes"

# First: check authentication and store locator. Catalog option checks feed metadata.
python tools/client_acceptance.py opd --store both --catalog

# Next: collect trial subset, minimum 500 from at least 2 categories.
python -m walmart_collector run --source opd --store 100 --authorized-source --only-categories Food,Beauty --minimum-products 500

# Run Houston independently if desired.
python -m walmart_collector run --source opd --store 5959 --authorized-source --only-categories Food,Beauty --minimum-products 500

# Inspect and export the latest successfully validated Bentonville run.
python -m walmart_collector status --store 100
python -m walmart_collector export --store 100 --export-file client-test-output/bentonville-products.json
```

For Linux / macOS, replace `$env:VAR="value"` with `export VAR="value"`. Store secrets in a secure environment or Azure Key Vault; never put them in script files or commit them to Git.

For full collection, omit `--only-categories` and check all 11 categories. For production use `--backend azure` after configuring Blob Storage, and mount persistent `--opd-cache` storage.

## What a client should send back to the developer

- Which API scopes/permissions were granted (not the key itself).
- Sanitized success/failure report (status codes and **non-secret** error details), total and per-category counts, elapsed time.
- A small representative redacted sample of the 22-field JSON and which store was confirmed.
- Differences noted in random comparisons of UPC, displayed PPM, current price, local pickup, digital/volume offers.
- Any category mappings from the Walmart Taxonomy API that differ from the starter mapping.

**Never send** access tokens, OAuth client secrets, entire signed Google Cloud Storage URLs, or production connection strings.

## Relevant Walmart first-party documentation

- https://walmart.io/docs/opd/quick-start-guide/catalog-pricing-and-availability-realtime
- https://walmart.io/docs/opd/quick-start-guide/catalog-pricing-and-availability-snapshot
- https://walmart.io/docs/opd/quick-start-guide/catalog-product-snapshot
- https://walmart.io/docs/opd/quick-start-guide/catalog-taxonomy
- https://walmart.io/docs/opd/quick-start-guide/catalog-store-service-locator
