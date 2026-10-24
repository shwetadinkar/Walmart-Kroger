> **Verified live update — 24 October 2026:** Official Kroger API verified West Loop location 53100508 / ZIP 60661. Real collection: 650 unique products; conservative export after conflict quarantine: 604. Website enrichment: 158 displayed PPM values and 29 volume descriptions in retained rows. See [API trial runbook](API_TRIAL_RUNBOOK.md). This is not complete 28-root or Azure acceptance proof. Older zero-live-data statements below describe the pre-API baseline.
# Mariano's collector — client handover and observed acceptance

**This is a technical testing package. Do not submit as a completed final contest entry until the live acceptance gate succeeds.** It contains no live product records and no production credentials.

## 1. Developer test without credentials

Use Python 3.11+:

```bash
python tools/preflight.py
```

Look for `offline_passed: true` and the two `_560_SYNTHETIC_acceptance_simulation: true` results. This exercises the real 22-field normalization, 28 category roots, synthetic pagination/subcategories, duplicate handling, checkpoint recovery and safe release. Product names explicitly contain `SYNTHETIC`; these may not be sent as actual retailer output.

## 2. Verify a real Mariano's location and approved API scopes

Obtain your own Kroger application credentials through https://developer.kroger.com/ and follow the data-use terms.

```powershell
$env:KROGER_CLIENT_ID='YOUR_CLIENT_ID'
$env:KROGER_CLIENT_SECRET='YOUR_CLIENT_SECRET'
python -m marianos_collector kroger-locations --zipcode 60601 --address-contains Benton
```

Match brand, postal address and actual returned location ID. Then run a **diagnostic**, not a completed category crawl:

```powershell
python -m marianos_collector kroger-trial --location-id VERIFIED_LOCATION_ID --terms milk,bread
```

The public product search is useful for authentication and spot-checking store-specific prices, but its term pagination does not prove traversal of all categories/subcategories, complete coupons or site-displayed PPM.

## 3. Configure a full-category authorized feed

The production collector expects the approved data provider to implement `examples/provider_page_contract.json` and attest complete traversal of each retailer category URL, store context, prices, deal types, and pages. This provider is **not included** and does not materialize automatically from Kroger Public API credentials.

Copy `config/stores_live.template.json` to `config/stores_live.json` and replace the ID with an actually confirmed Mariano's `locationId`. Then set environment variables *in a secure terminal*:

```bash
export MARIANOS_DATA_AUTHORIZED=yes
export PROVIDER_BASE_URL=https://your-approved-provider.example/api/category-page
export PROVIDER_API_TOKEN='<secure-value>'
python -m marianos_collector run --source provider --authorized-source \
  --store VERIFIED_LOCATION_ID --stores config/stores_live.json \
  --minimum-products 500
```

Every one of the 28 roots must complete successfully. For a narrow exploratory test, add `--only-categories 'Produce,Dairy'`: this writes only into the `trials/` namespace and **cannot overwrite** the production `latest` pointer.

## 4. Verify result and run Azure

```bash
python -m marianos_collector export --store VERIFIED_LOCATION_ID \
  --stores config/stores_live.json --export-file marianos_live.json
```

Inspect `published/VERIFIED_LOCATION_ID/latest.json` and its manifest/report using local or Azure Blob storage. Validate ZIP, address, regular/sale prices, clipped coupon/volume offer semantics, UPC and displayed PPM against live site or verified authorized source. Don't accept missing category pages as empty.

Azure: follow `azure/README.md` and `bash azure/deploy_jobs.sh --dry-run`; use `--execute` only after images, secrets and the environment are ready. The job is scheduled Monday/Thursday by default. Check Azure monitoring and perform observed recovery and repeat run tests.

## 5. Final submission gate

Copy `submission_evidence/observed_review.template.json` to `submission_evidence/observed_review.json`. A real reviewer must personally verify each false-by-default check and enter their name. **Do not check these boxes until proven.** Then run:

```bash
python tools/submission_gate.py --store VERIFIED_LOCATION_ID \
  --output .collector-output --stores config/stores_live.json \
  --attestation submission_evidence/observed_review.json
```

A zero exit status indicates the *internal* submission gate passed. It does not claim that the organizer has inspected or accepted the work. Attach the original JSON, manifest, validated report, recorded fresh execution, store/price comparisons, evidence screenshots, timings and Azure instructions.

## 6. No-source acceptance blockers

Without an approved category-complete feed and credentials, the project cannot honestly demonstrate 500 real products, exact displayed deal terms/PPM, or observed Azure deployment. A polished simulated run cannot replace these buyer requirements.
