> **Update v0.4.1:** An official Walmart OPD snapshot-to-collector adapter is now included. See [`OPD_CLIENT_RUNBOOK.md`](OPD_CLIENT_RUNBOOK.md) for runnable client commands and unresolved acceptance limitations.

# Client testing and evidence — v0.4.1

This handover distinguishes **three different proofs**. They are *not interchangeable*.

| Test | Credentials | What it proves | What it does not prove |
|---|---|---|---|
| Offline | None | 22-column schema, CSV categories, mock HTTP integration, checkpoint/restart, duplicate and rejection rules | Live Walmart data |
| Walmart OPD connectivity | Client-approved Walmart I/O `client_id` and `client_secret` | OAuth works; expected pickup store appears; optionally catalog feed metadata | Product-level location prices, coupons or 500 items |
| Full provider feed | An approved **feed API** URL + token that returns the documented project contract | Full Python collector can enumerate pages, produce 22 fields and pass automated dataset gates | Independent verification of the retailer data, license, every coupon, or Azure runtime |

**Two distinct live integration routes:** `--source opd` now supports the documented Walmart OPD catalog + pricing snapshots using Walmart-approved credentials. `--source provider` expects the different normalized JSON contract in `examples/approved_provider_page_contract.json` and its own provider token; they are not interchangeable. The OPD path is implemented but has NOT been run with real credentials or verified against actual store prices, full taxonomy, coupons, and Azure deployment. Do not promise that adding a key guarantees 500 accepted products.

## A. Tester / developer — no keys, no Azure account

Python 3.11+ from the extracted project root:

```bash
python tools/client_acceptance.py offline
```

This runs all automated tests, including a **mock HTTP round trip** through `AuthorizedProviderSource`, plus two fixture store-level runs. It writes `client-test-output/offline-test-report.json`, accurately labeled **OFFLINE_TEST_ONLY**. The test store IDs and ZIPs are #100/72712 and #5959/77007. The sample rows are imaginary. All 11 root categories come from the client's actual CSV.

Optional manual commands:

```bash
python -m unittest discover -v tests
python tools/walmart_opd_smoke_test.py --store both --dry-run
```

A successful local result is valuable evidence of software reliability but **not an accepted 500-real-products contest demonstration**.

## B. Client — Walmart I/O OPD key connectivity, no key sharing

Client must have Walmart-approved API subscription and permission for this specific data use. In the *client's own terminal*, configure:

**Linux/macOS:**

```bash
export WALMART_OPD_CLIENT_ID='their_approved_client_id'
export WALMART_OPD_CLIENT_SECRET='their_approved_client_secret'
python tools/client_acceptance.py opd --store both --catalog
```

**Windows PowerShell:**

```powershell
$env:WALMART_OPD_CLIENT_ID='their_approved_client_id'
$env:WALMART_OPD_CLIENT_SECRET='their_approved_client_secret'
python tools/client_acceptance.py opd --store both --catalog
```

This exercises OAuth, ZIP/store pickup lookup, optional feed metadata only, and writes `client-test-output/opd-connectivity-report.json`. It does not print credentials or OAuth tokens. A 401/403 or no expected store is a failure to investigate, not a successful test.

Official docs: <https://walmart.io/docs/opd/quick-start-guide/catalog-store-service-locator> and <https://www.walmart.io/docs/opd/recipe-register/catalog-product-snapshot>.

## C. Client — actual feed integration once available

Prerequisite: approved/licensed provider *with an adapter* that returns the exact `Page` JSON described in `examples/approved_provider_page_contract.json`. This is **not** a standard Walmart OPD endpoint.

**Linux/macOS:**

```bash
export PROVIDER_BASE_URL='https://their-approved-feed.example/api/catalog'
export PROVIDER_API_TOKEN='their_authorized_feed_token'
export WALMART_DATA_AUTHORIZED=yes
python tools/client_acceptance.py provider --store 100 --confirm-authorized --minimum-products 500
```

**Windows PowerShell:**

```powershell
$env:PROVIDER_BASE_URL='https://their-approved-feed.example/api/catalog'
$env:PROVIDER_API_TOKEN='their_authorized_feed_token'
$env:WALMART_DATA_AUTHORIZED='yes'
python tools/client_acceptance.py provider --store 100 --confirm-authorized --minimum-products 500
```

Use `--store both` for both locations. Run from an environment with approved network access. A successful full run generates, under `client-test-output/`:

- `candidate_store_100.json` — 22-field JSON candidate, at least 500 records if the threshold was satisfied.
- `candidate_store_100_report.json` — counts by category, missing fields, runtime, deals, displayed PPM examples.
- `provider-test-report.json` — test outcome and remaining manual review warning.
- `private-collection-data/` — durable stages, checkpoints, previous successful versions (protect as non-public).

The application refuses to run with missing permission affirmation/credentials, incomplete categories, store mismatch, fewer than 500 records, suspicious category yield, or erroneous schemas. It retains the last successful publication on errors.

**Important:** A provider URL must be real and be mapped to the required contract. Do not enter `https://developer.api.walmart.com/...` as the `PROVIDER_BASE_URL`; that API uses a different interface. Adapting OPD catalog + location pricing + fulfillment + promotions is development work requiring authorized test results.

## D. Manual client acceptance checklist

- [ ] Confirm the assigned store (test stores #100/#5959 are proposals only), data usage permission and licence.
- [ ] Verify at least 500 distinct, genuine, eligible product observations for the same intended store, from multiple required categories.
- [ ] Verify that all **11** root categories and **all eligible nested subcategories** were processed. A nonzero top-level count alone does not prove complete coverage.
- [ ] Randomly compare 20+ observed records against primary-source pages or independently verified data for **the same store**: UPC, price, displayed PPM, availability/fulfillment, and deal text.
- [ ] Include at least one normal sale, volume deal, and clipping-required digital deal if displayed; do not invent examples if none is available.
- [ ] Demonstrate shutdown mid-run, restart from a checkpoint and preservation of the last successful version.
- [ ] Perform an observed run in the client's Azure environment, verify scheduled-jobs configuration, lock behavior, logs, and costs.
- [ ] Keep keys in their own environment / Azure Key Vault, never in source files, screenshots, GitHub or contest upload.

These acceptance steps reflect the shared requirements attachment. The only automatically tested parts are indicated by mode and evidence.
