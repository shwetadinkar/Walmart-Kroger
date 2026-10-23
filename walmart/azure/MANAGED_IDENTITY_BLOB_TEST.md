> **RESULT — OBSERVED SUCCESS ON 24 OCTOBER 2026:** The user executed the updated `walmart63-collector` image in the personal Azure trial, and the job wrote `brightdata-trials/100/azure-verification/runs/20261023T215838Z_610df5e2.json` using Managed Identity. The uploaded report is preserved at [client review / Azure verification JSON](../submission/2026-10-24/azure_blob_verification_20261023T215838Z.json). It records `records_checked=615`, `provider_api_called=false`, 11 category groups, and zero verified local prices and PPM. The later sections describe **how to reproduce the already completed test**, not work still pending.

# Walmart Store #100 — Azure Managed Identity read/write verification

**Version:** 24 October 2026, managed-identity smoke-test update.  
**Scope:** Walmart contest #63 only. No Mariano's files changed.

## Completed infrastructure (user-observed)

- Azure subscription: `Azure subscription 1`, South India.
- Resource group: `rg-walmart63-trial`.
- Existing Container Apps Environment: `env-walmart63`.
- Existing Container Apps Job: `walmart63-collector` (Consumption, manual trigger); prior job execution **Succeeded** with code in `BRIGHTDATA_JOB_MODE=dry-run`.
- Existing private Blob Storage account: `stwalmart63trial1024`; container: `retail-collection`.
- User uploaded `Walmart_Store100_615_Trial_22Field.json` to the container root and confirmed the file listing (613.59 KiB).
- User confirmed the `walmart63-collector` job's **system-assigned managed identity** was granted **Storage Blob Data Contributor** role on the storage account.

The subsequently observed Managed Identity Blob smoke test **also succeeded**. The steps below document its reproducible configuration, not a new collection.

## New code behavior

- `AzureBlobStore` can now authenticate with **ManagedIdentityCredential**, using the non-secret HTTPS account URL `AZURE_STORAGE_ACCOUNT_URL`.
- Connection-string authentication remains available as a legacy fallback; **do not put storage keys in plain job environment variables or GitHub**. Managed Identity is preferred.
- The storage container must already exist; the job does not create containers or escalate permissions.
- New `BRIGHTDATA_JOB_MODE=blob-smoke` is a **NO-BRIGHT-DATA** mode. It downloads the manually uploaded 615-row trial JSON using Managed Identity, checks all 22 ordered string fields, the expected record count, distinct product URLs, store name/ZIP and permitted category groups, and uploads only a small verification report.
- The audit report will appear at `brightdata-trials/100/azure-verification/runs/<timestamp>_<id>.json`.
- The smoke test does **not** seed the collector's `history.json`, change `published/100/latest.json` or `latest-trial.json`, prove local prices or scrape anything. A history migration requires original private provider provenance files and a separately approved plan.

## A. Build a NEW image version

1. Go to [Walmart 63 — Build Azure Docker image](https://github.com/shwetadinkar/Walmart-Kroger/actions/workflows/walmart-ghcr.yml).
2. Select **Run workflow**, branch `main`, and run once after this code update; verify the job is green. The workflow includes offline regression tests.
3. The action publishes to GHCR under both `trial` and an immutable **full commit-SHA** tag. For reliable rollout to Azure, use the full SHA shown on the new Actions run, not an old cached `trial` image.
4. Since the Docker image is intentionally public and holds only the public program, select **Public** image settings in Azure. There are no credentials inside the image.

## B. Update existing Container Apps Job (do not create a second job)

In the Azure Portal, open `walmart63-collector` → **Container** (or edit the job's container configuration). Update the image to:

```text
Registry login server: ghcr.io
Image and tag: shwetadinkar/walmart63-collector:<FULL_NEW_COMMIT_SHA>
```

Keep the existing `env-walmart63` environment, Consumption workload, manual trigger and System-assigned identity.

Set these **non-secret** environment variables in the container configuration:

| Name | Value |
|---|---|
| `BRIGHTDATA_JOB_MODE` | `blob-smoke` |
| `AZURE_STORAGE_ACCOUNT_URL` | `https://stwalmart63trial1024.blob.core.windows.net` |
| `AZURE_BLOB_CONTAINER` | `retail-collection` |
| `WALMART_STORE_ID` | `100` |
| `WALMART_ZIPCODE` | `72712` |

Do **not** provide `BRIGHTDATA_API_KEY`, `BRIGHTDATA_COLLECTION_APPROVED`, `AZURE_STORAGE_CONNECTION_STRING` or any raw secret.

Save/apply the updated container configuration. Verify that the updated version is active before starting a new execution. Role assignments may need a few minutes to propagate.

## C. Run and verify

- Click **Run now** exactly once. Open **Execution history** and confirm `Succeeded`.
- In console logs, expected summary: `"status": "blob_read_write_succeeded"`, `"mode": "blob-smoke-no-provider"`, `"records_checked": 615`, `"provider_api_called": false`, `"report_blob": "brightdata-trials/100/azure-verification/runs/...json"`.
- In the Azure portal, open **Storage accounts → stwalmart63trial1024 → Containers → retail-collection**; browse into `brightdata-trials/100/azure-verification/runs/` and verify the new report JSON. Do not confuse it with the previously uploaded raw trial JSON.
- Save the job execution ID, screenshot, UTC timestamps and verification JSON for the contest review package.

If the run fails:
- `401` / `403`: recheck system-assigned identity and **Storage Blob Data Contributor** assignment; verify selected Blob account/container.
- `ResourceNotFoundError`: verify the 615-row file is in the **container root**, with the exact expected name and case.
- `ModuleNotFoundError: azure.identity` or `Unsupported ... blob-smoke`: Azure is still using the OLD image. Rebuild and use the new immutable SHA tag.

## Acceptance limitations

- A **successful blob smoke** proves managed-identity Blob download, structural validation of the manually uploaded 615 rows, and metadata upload by our own job. It is **not** proof of live scraping/pagination, new billed Bright Data collection, preservation of the original ingestion history, selected-Store-100 pickup prices, displayed PPM or complete promotion terms.
- Leave all jobs in **Manual** mode until costs, idempotent resumability and data acceptance are independently verified.
- Azure resources/Log Analytics can consume free-trial credit. Review Azure Cost Management; no paid provider collection is triggered by the smoke test.
