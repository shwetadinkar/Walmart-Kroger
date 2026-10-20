# Mariano's Azure Collector v0.2.1 — live-access testing handoff

**Current status: software-complete for offline integration, not buyer-accepted and NOT a genuine 500-product contest entry.** We have no authorized full-coverage Mariano's data feed, verified production Kroger location IDs, actual product collection, or observed Azure deployment. Never present offline generated records as if they came from Mariano's.

## One-command developer test

```bash
python tools/preflight.py
```

This runs automated tests for the collector and mock API, checks two illustrative Chicago stores, and simulates a 560-item **SYNTHETIC** complete 28-root run with a crash/restart. A separate `tools/submission_gate.py` refuses to mark the entry ready without live data AND manually signed-off acceptance evidence.

## Key improvements in 0.2.0

- 28-root/560-product offline acceptance simulation with simulated interruption and resume.
- Subset trial releases live under `trials/...`, isolated from full `published/...` releases.
- Actual Azure Container Apps Jobs creation script (dry-run first), with mandatory verified store IDs, provider secrets, blob storage and UTC twice-weekly schedule.
- Final live-data verification gate with product schema checks, >=500 genuine records, category counts, human sign-off, coupon/PPM/store spotchecks and Azure evidence.
- Full recipient instructions in `HANDOVER.md`, `SUBMISSION_STATUS.md`, `azure/README.md`.

---

## Original v0.1.0 notes (preserved for reference)

**Status: an offline-tested, fail-closed collection framework with real Kroger Public API location/product diagnostic. It is NOT a completed Mariano's contest entry.** No authenticated live retailer requests, 500 real products, Playwright website crawl, full subcategory enumeration, or Azure deployment have been demonstrated.

This project is adapted from the prior Walmart Azure Collector, but **the retailers use different APIs and different category trees**. It is a separate standalone project. Do not send synthetic output as real collection evidence.

## What's inside

- `config/categories.csv` — exact **28** Mariano's category roots supplied in the contest CSV (including Coupons, Beer Wine Liquor and the `/pl/` catalog groups).
- `config/stores_demo.json` — two *illustrative*, not verified Kroger location IDs, for offline testing. The street addresses come from Mariano's public store directory. The `DEMO-...` IDs must **never** be used for live collection.
- `config/stores_live.template.json` — example for an explicitly verified `locationId` returned by Kroger Locations API.
- `marianos_collector/kroger.py` — documented Kroger Public API OAuth, ZIP-based store discovery and product-price diagnostics. **Search terms do not enumerate full categories**. These responses are never promoted to contest-ready output.
- `marianos_collector/sources.py` — synthetic fixture reader and a strict authorized-provider page contract. Only a licensed provider capable of full category navigation and location proof can feed the production collector.
- `marianos_collector/runner.py` — subcategory queues, pagination cursors, durable checkpoints, deduplication, yield checks, failures and atomic publishing.
- `marianos_collector/schema.py` — ordered 22-field strings, private-brand classification, approximate-weight exclusion, deal validation, displayed PPM only, blank gupc and unit_price.
- `marianos_collector/storage.py` — local file storage and optional Azure Blob Storage with per-store locks.
- `azure/README.md` — Azure deployment design and secret handling.
- `SHARED_REQUIREMENTS.docx` — the provided shared specification.

## Quick start — works without keys

Requires Python 3.11+ and only the standard library for offline tests.

```sh
python -m unittest discover -v tests
python tools/preflight.py
python -m marianos_collector list
python -m marianos_collector run --source fixture --store DEMO-LAKESHORE-60601
python -m marianos_collector export --store DEMO-LAKESHORE-60601 --export-file demo.json
```

**SYNTHETIC DEMO ONLY.** The offline fixtures deliberately provide one pretend product per root (28 records) for both store contexts. They do not demonstrate genuine product extraction, legitimate category/subcategory completeness, or 500-product contest eligibility.

## Kroger API — authenticated diagnostic only

Kroger documents the Public API at https://developer.kroger.com/ and an official Postman collection at https://www.postman.com/kroger/the-kroger-co-s-public-workspace/collection/ki6utqb/kroger-public-apis . Register an application and use only the API scopes and data uses approved for the client.

**PowerShell** (client keeps their own credentials):

```powershell
$env:KROGER_CLIENT_ID="CLIENT_ID"
$env:KROGER_CLIENT_SECRET="CLIENT_SECRET"
python -m marianos_collector kroger-locations --zipcode 60601 --address-contains "Benton"
```

Examine the response and verify that the brand, full street address and ZIP identify **Mariano's Lakeshore East**, rather than another Kroger banner. Record the API-returned `locationId`, then:

```powershell
python -m marianos_collector kroger-trial --location-id VERIFIED_LOCATION_ID --terms milk,bread
```

The diagnostic reports retrieved UPC, description, size, regular price and promo price **where returned**, without treating `promo` as a digital coupon, inventing PPM or manufacturing a product-page URL. It marks `suitable_as_contest_proof: false` because term search is not complete category traversal. Use `--zipcode 60661 --address-contains "Halsted"` to find Mariano's West Loop. The location ID must come from the client's actual verified API response; the CSV does not specify one.

### Why the public API alone is insufficient for contest acceptance

The Kroger Public Products endpoint uses `filter.term` and `filter.locationId`. The interface does **not** attest that it has enumerated every `/d/`, `/pl/`, coupon category and subcategory URL supplied by the client; it does not necessarily supply retailer-displayed PPM or all coupon limits/clip requirements. **We cannot convert a handful of searches into “all 28 categories complete.”** The API may still help verify store selection and local pricing.

Kroger's website terms restrict automated extraction. Do not use undocumented website endpoints or Playwright automation unless authorized for that exact collection use. Merely possessing an API key does not make collection and republishing legally permitted.

## Full collector with approved category-complete provider

A provider must expose an HTTPS API that returns the strict page contract shown in `examples/provider_page_contract.json` and authenticates with a secret. The provider must independently attest that:

1. `store_id`, `zipcode` and product-level `store_context_verified` correspond to the correct Mariano's physical location;
2. all product pages and all **available** subcategories under the requested CSV root were crawled, including coupons;
3. pagination cursors represent genuine progress and are safe to resume;
4. price, displayed PPM, regular/sale, volume deals and digital coupons are faithful retailer observations, with unobserved fields left empty;
5. product URLs remain original Mariano's URLs and all values are authorized for the agreed use.

Configure a **real** verified location ID in your stores JSON, then set secret environment variables. Example:

```sh
export MARIANOS_DATA_AUTHORIZED=yes
export PROVIDER_BASE_URL=https://your-approved-provider.example/api/category-page
export PROVIDER_API_TOKEN=REDACTED
python -m marianos_collector run --source provider --authorized-source \
    --store VERIFIED_LOCATION_ID --stores config/stores_live.json \
    --minimum-products 500
```

The example endpoint is a placeholder, not an operating service. The run fails if any category fails, if a location changes, if records fall below the minimum, or if any provider page cannot verify subcategory completeness. The most recent successful output is unchanged on failure.

After a successful run:

```sh
python -m marianos_collector export --store VERIFIED_LOCATION_ID \
    --stores config/stores_live.json --export-file marianos.json
```

For a sample trial on **two** category roots, add `--only-categories "Produce,Dairy"`; this is not sufficient as proof of complete category coverage.

## Acceptance and limits

- JSON keys: exactly 22 in the required order; `gupc` and `unit_price` are empty strings; `crawl_date` last. Missing fields are `""`.
- If no site-displayed PPM is available, `ppm` is empty; numeric Kroger unit-price calculations are **not** copied into it.
- Standard API price `promo` means sale/promo amount, not proof of clipping. Digital coupon price stays empty unless explicitly and reliably observed.
- `store_brand` is yes for known Mariano's/Kroger private labels, otherwise no.
- Category counts, duplicates, field completeness, example deals and PPM and staged evidence are preserved in the run's report.
- Every root must have at least one eligible product in an accepted production run; a truly legitimate empty root requires separate client-approved validation rules.
- A global 500-product threshold is applied for provider mode.
- Official Kroger API credentials and scopes, any actual provider, live website compatibility, full 28-category mapping, source-rights, Azure cost and deployment are **not verified**.

See `HANDOVER.md` for client testing and limitations. No secrets or telemetry are embedded.

## v0.2.1: confidential live-access handoff

See `ORGANIZER_ACCESS_REQUEST.md` for the client access request. Once the client has an approved source, `CLIENT_LIVE_TEST_STEPS.md` shows how to run `tools/live_access_preflight.py` without sharing secrets or publishing data. The Kroger diagnostic does not confer complete category coverage.
