# Mariano's: confidential client-run live-access checks

## A. What this is

Run these commands **on the client's own computer** with approved API credentials. The resulting JSON contains only status, category counts, and store identifiers. It does **not** include access tokens, API secrets, UPCs, or individual product prices. It is a diagnostic, **not** contest acceptance evidence.

### Step 1 — Check Kroger API and identify the store

For Windows PowerShell:

```powershell
$env:KROGER_CLIENT_ID='CLIENT_ID'
$env:KROGER_CLIENT_SECRET='CLIENT_SECRET'
python tools/live_access_preflight.py --mode kroger --zipcode 60601
```

The first run returns candidate Mariano's location IDs and asks the operator to verify the exact store address. Rerun after checking the address:

```powershell
python tools/live_access_preflight.py --mode kroger --zipcode 60601 --location-id VERIFIED_LOCATION_ID --address-contains 'YOUR_STORE_STREET'
```

Expected: `DIAGNOSTIC_OK` only if the selected store is found and at least one sample product is retrieved. Public search results do not prove full category coverage, original coupon terms, or displayed PPM. The client should not send passwords, API keys, or tokens in their reply.

### Step 2 — Check a category-complete licensed provider

Only if an authorized provider actually exists and its contract is compatible with `examples/provider_page_contract.json`, fill `config/stores_live.json` with the verified location ID. Then run:

```powershell
$env:MARIANOS_DATA_AUTHORIZED='yes'
$env:PROVIDER_BASE_URL='https://licensed-provider.example/api/category-page'
$env:PROVIDER_API_TOKEN='CLIENT_PRIVATE_TOKEN'
python tools/live_access_preflight.py --mode provider --store VERIFIED_LOCATION_ID --sample-roots 2
```

Expected: `DIAGNOSTIC_OK` for **first pages** of two root categories only. This never publishes product data. It does not silently treat public Kroger search as a complete-category feed.

### Step 3 — Share only the diagnostic

Send back `submission_evidence/live_access_preflight.json` and any observed errors, without credentials or screenshots showing tokens. If it passes, follow `HANDOVER.md` for the **full 28-category** `run --source provider` step, export, physical price/PPM/coupon spot-checks, interruption/repeat-run evidence, and Azure deployment. The `submission_gate.py` will remain blocked until all required evidence is verified.

### Step 4 — Azure deployment

After confirming the real feed and verified store, follow `azure/README.md`, begin with `bash azure/deploy_jobs.sh --dry-run`, and deploy only through the client's authorized Azure subscription. Credentials must be provisioned securely by the operator. A successful local diagnostic does not prove Azure deployment.
