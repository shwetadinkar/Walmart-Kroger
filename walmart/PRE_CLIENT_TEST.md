# Before sending to the client — Walmart Azure Collector v0.4.1

**Status: technical testing prototype. Not a finished contest submission.**

This package is derived from v0.4.0. Version 0.4.1 closes the SQLite connections left open by one test and adds a completely offline, repeatable preflight command. No changes to the production OPD endpoint mappings or extraction logic are claimed.

## A. Test it yourself without API access

1. Install Python 3.11 or later.
2. Extract this ZIP and open Windows Command Prompt or PowerShell **inside** the `walmart_azure_collector` folder.
3. Run:

```powershell
python tools/preflight.py
```

The command performs these seven checks:

- Standard-library automated tests with resource warnings enabled;
- Offline end-to-end collection against two stores, store #100 / ZIP 72712 and #5959 / ZIP 77007;
- Official Walmart request-construction dry-run (no HTTP);
- Export of an ordered 22-field JSON synthetic dataset;
- Expected rejection of a dataset with fewer than 500 records;
- Confirmation that rejected test data is not published;
- Confirmation that OPD mode refuses a run without authorization affirmation.

A successful command prints `OFFLINE PREFLIGHT: PASSED` and writes `client-test-output/preflight-report.json`.

The test must be successful **on your own extracted copy** before sharing it. This preflight intentionally runs *without contacting Walmart* even if you have credentials in your environment.

## B. What you can say to the client

You can say the core application and offline mock integration tests passed. You **cannot** claim that 500 genuine Walmart records were collected, coupons were verified, every subcategory was covered, or that this version has completed an observed Azure deployment. The OPD source is implemented against Walmart's documented snapshot and store interfaces but remains unverified against live entitlements and feeds.

## C. What the client should run with their approved credentials

Set credentials on the **client's** machine; do not send them to the developer:

```powershell
$env:WALMART_OPD_CLIENT_ID="<approved client id>"
$env:WALMART_OPD_CLIENT_SECRET="<approved client secret>"
python tools/client_acceptance.py opd --store both --catalog
```

Only after that connectivity probe succeeds, and after checking the mapping in `config/opd_category_mapping.json` against Walmart taxonomy, can the client attempt a small full-data trial:

```powershell
$env:WALMART_DATA_AUTHORIZED="yes"
python -m walmart_collector run --source opd --store 100 --authorized-source --only-categories Food,Beauty --minimum-products 500
```

If these categories together contain fewer than 500 eligible local offers, the threshold causes the expected failure. For an exploratory **non-acceptance** test, explicitly choose a smaller threshold, e.g. `--minimum-products 10`, and use a separate `--output` folder. A trial of two categories is not proof of all 11 categories and their subcategories.

To produce the accepted final sample, full-category coverage and a fresh observed run are still needed; the category mapping, pickup/local fulfillment and promotional classification must be manually checked. Some API fields do not distinguish ordinary sale from regular prices and do not expose complete coupon wording. Do not invent values to fill gaps.

## D. What the client can share back safely

Ask for a **sanitized** report including: HTTP success/failure status, enabled API scopes, which stores were validated, category counts, one small redacted sample of JSON, PPM/UPC comparison findings, and any source-category mapping mismatches. Logs must not contain client secrets, access tokens, signed GCS URLs, or Azure connection strings.

## E. Further work before winning-submission handover

- Confirm API access is approved for this commercial use and correct two stores.
- Confirm full Walmart taxonomy mappings for all category roots and exclusions in the supplied CSV.
- Verify local pickup pricing and accurate deal fields against independent displayed evidence.
- Prove at least 500 real, unique, store-correct records across required categories.
- Test a deliberate interruption, recovery, safe publication, complete 11-category coverage, and Azure environment deployment with persistent OPD cache and secrets.

If the client does not have OPD access, use a properly licensed compatible data source. Walmart Marketplace seller keys are not interchangeable with OPD credentials.
