# West Loop official API trial — operating guide

## Verified result

Official Locations API: Mariano's West Loop, locationId **53100508**, 40 S Halsted St, Chicago, IL **60661**. The initial collection returned 650 distinct qualifying products after 14 keyword searches. The integrated second run resumed from 598 to 650 after an API failure, using four network requests during resumption.

Conservative export: **604 unique products**, after 46 were quarantined for API/website regular-price conflicts or website pickup unavailable/unverified status. Retained rows include **158 literal displayed PPM values**, **29 volume-offer descriptions**, and **234 API promo prices**. Website evidence covers 204 original products. Subsequent website requests returned Access Denied and were stopped. Digital-coupon conditions remain unverified.

This is a genuine-data trial, not proof of complete traversal of all 28 CSV roots, all subcategories, or an accepted Azure deployment. Known API category aliases are mapped; otherwise original API taxonomy labels are preserved. Subcategories come only from matched website breadcrumbs. The independent final submission gate remains unchanged.

## Fresh bounded collection

Provide `KROGER_CLIENT_ID` and `KROGER_CLIENT_SECRET` through private process environment or Key Vault. Never place secrets in source, command arguments or screenshots.

From `marianos/`:

```sh
python -m marianos_collector.api_collection --location-id 53100508 --zipcode 60661 --run-id NEW_SNAPSHOT_ID --output .collector-output/api-trial --target 650 --minimum 500 --maximum-queries 40 --maximum-requests 60 --canary-upc 0001111042852
```

At most 40 searches, 50 products each; stop at 650 qualifying unique UPCs. The 60-network-request ceiling includes OAuth, store checks and retries. The store/banner/ZIP is checked at startup and periodically. A configured canary must appear in the first response.

Reuse the same run ID and unchanged configuration to resume. Successful pages are reused; a changed configuration fails closed. Use a new run ID for a fresh retailer snapshot. Cached replay is not a fresh run.

Local per-store locks prevent overlap. Azure mode uses Blob leases and remote durable checkpoints. Failed/partial collections do not replace a successful trial. A material yield drop greater than 20% also blocks replacement. Trial objects live under `trials/STORE_ID/`, separate from full-category `published/` objects.

## Rebuild preserved evidence

Source snapshots contain `verified_store.json` and timestamped `page_00.json`, etc.

```sh
python -m marianos_collector.website_evidence WEBSITE_DOM_JSON WEBSITE_ENRICHMENT_JSON
python -m marianos_collector.api_trial --source SOURCE_SNAPSHOT --output .collector-output/review --location-id 53100508 --zipcode 60661 --minimum 500 --maximum 650 --website-evidence WEBSITE_ENRICHMENT_JSON
```

The exporter creates 22 ordered string fields, preserves UPCs and source URLs/images, rejects approximate/variable weights and non-pickup offers, and deduplicates by UPC. `gupc` and `unit_price` stay empty. PPM and deal prices are never calculated. Known website/API regular-price conflicts and unavailable pickup observations are quarantined. Source, store and website evidence hashes identify immutable versions.

## Checks

```sh
python -m unittest discover -v tests
python tools/preflight.py
```

Preflight's complete-category recovery simulations are **synthetic**, separate from the actual API interruption/resumption evidence.

## Azure

`azure/api_trial_job.bicep` references an existing environment, managed identity and Key Vault secrets. It defaults to a manual job. After an observed Azure execution is approved, `enableSchedule=true` enables Monday/Thursday 06:00 UTC (11:30 India time).

Build the existing Dockerfile. `MARIANOS_MODE=api-trial` selects the official API collector with Azure Blob checkpoints. The default provider path remains unchanged. Scheduling a keyword trial does not establish complete-category collection.

Still needed: Azure subscription/resource group/environment, image/registry, existing identity permissions, Key Vault secret URLs and Blob access. No resources or schedules were created. Azure CLI and Docker were unavailable locally. The Linux image build and publication subsequently passed in GitHub Actions run 40074405189; see reports/2026-10-24-west-loop/CONTINUATION.md for the immutable digest. The Bicep compiler download timed out. Template fields were checked against Microsoft's reference; template compilation and Azure deployment remain unverified. No monthly cost is asserted without the actual region, resources and measured usage.

## Remaining final acceptance

- Complete category/subcategory enumeration independent of keyword search.
- Resolution of price/availability conflicts and website access.
- Complete digital-coupon clipping/activation conditions.
- Buyer-observed fresh run and random product/price/PPM comparisons.
- Actual Azure deployment, observed schedule/recovery and recorded walkthrough.

Do not claim these milestones passed. No Bright Data collection credits were used by the API trial.

References: [Products API](https://developer.kroger.com/api-products/api/product-api-public), [Locations API](https://developer.kroger.com/api-products/api/location-api-public), [Azure job schema](https://learn.microsoft.com/en-us/azure/templates/microsoft.app/2024-03-01/jobs).
