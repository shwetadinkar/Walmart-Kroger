# Walmart — automatic Bright Data + Azure setup (v0.7.0 pilot architecture)

**Status as observed 24 October 2026:** The Walmart Python image has been deployed **in a personal Azure Free Trial**, not the client's subscription. A manual no-provider dry-run succeeded, and a subsequent system-assigned Managed Identity test **read the manually uploaded 615-row trial JSON and wrote a separate Blob verification report** ([source report](../submission/2026-10-24/azure_blob_verification_20261023T215838Z.json)). **No paid Bright Data trigger, live end-to-end product collection, production schedule, or Azure interruption recovery has been tested.** The 615 data rows remain trial candidates with no independent local price or displayed PPM validation. Mariano's is unchanged.

## Observed Azure verification (current quick route)

The existing managed-identity job is `walmart63-collector` in `env-walmart63` / `rg-walmart63-trial` (South India), using `ghcr.io/shwetadinkar/walmart63-collector`. The latest successful no-provider Blob report is [here](../submission/2026-10-24/azure_blob_verification_20261023T215838Z.json). For reproduction use [Managed Identity Blob runbook](MANAGED_IDENTITY_BLOB_TEST.md). The following ACR-specific CLI example is **an unexecuted alternative deployment recipe**, not a record of what was tested.

## What it actually does

1. Azure Container Apps Job invokes `tools/brightdata_start.py`.
2. In `BRIGHTDATA_JOB_MODE=trigger` (requires explicit permissions and positive `BRIGHTDATA_RECORD_CAP`), the script requests the configured ZIP/category dataset via `POST /datasets/v3/trigger` using JSON array inputs. Records are capped by the supplied provider query limit (must verify server-side enforcement and charges). The dataset's input schema must first be proven with a no-charge/capped small run.
3. `state.json` stores the returned snapshot ID in **private Blob Storage**. Reruns of an unfinished job resume polling, not trigger a duplicate. Bright Data's ready snapshot is downloaded with `GET /datasets/v3/snapshot/{snapshot_id}`.
4. Existing v0.6 importer checks Store #100, ZIP 72712, seller, category, UPC/product identity, pickup evidence and availability, and maps to exactly 22 fields. An unavailable product is retained. Historical, source-observed records and original dates persist independently of each Container App invocation.
5. Azure Blob gets `brightdata-trials/100/runs/<run>/raw/source.json`, `data_22_fields.json`, `evidence.json`, `history.json`, `manifest.json`, `rejected.json`; `brightdata-trials/100/latest-trial.json` points to the newest **trial**.
6. **Crucial:** production `published/100/latest.json` is untouched because the source still lacks proven pickup-specific prices, directly displayed PPM, full digital/volume offer terms and complete-category verification. Client should not treat these trial results as a live-compliant production feed.

## Minimum Azure environment (client-provided subscription)

- A resource group, one Container Apps Environment, and a **private** Storage Account / Blob container `retail-collection`. A container registry is needed for a build, but **Azure Container Registry is optional**: the observed working setup uses a public GitHub Container Registry (GHCR) image.
- Permissions to push image to ACR; job permission to pull it; storage credentials or preferably managed identity (`Storage Blob Data Contributor`).
- An authorized Bright Data account and API token stored privately as a Container Apps Job secret/Key Vault reference. Never paste keys into GitHub, ChatGPT, contest submissions or public logs. Enable cost alerts and provider spending caps before collection.
- For Azure portal walkthrough: https://learn.microsoft.com/en-us/azure/container-apps/jobs-get-started-portal

### Prepare and build (only after subscription/compute spend approval)

Run from `walmart/` on a client-managed machine with Azure CLI. Replace all `<...>` placeholders with the client's chosen values. These are **commands to run**, not commands that this project has executed.

```bash
az login
az extension add --name containerapp --upgrade
az provider register --namespace Microsoft.App
az provider register --namespace Microsoft.Storage
az provider register --namespace Microsoft.OperationalInsights

# Use an existing approved RG/ACR/environment, or have the client create them in the Azure portal.
export RESOURCE_GROUP='<CLIENT_RG>'
export ENVIRONMENT='<CLIENT_CONTAINER_APPS_ENVIRONMENT>'
export REGISTRY='<CLIENT_ACR_NAME>'

az acr build --registry "$REGISTRY" --image walmart-brightdata:0.7 \
  --file azure/Dockerfile.brightdata .

# Create a MANUAL job first: safe Docker default is dry-run.
az containerapp job create --name walmart-brightdata-100 \
  --resource-group "$RESOURCE_GROUP" --environment "$ENVIRONMENT" \
  --trigger-type Manual --replica-timeout 14400 --replica-retry-limit 0 \
  --parallelism 1 --replica-completion-count 1 \
  --image "${REGISTRY}.azurecr.io/walmart-brightdata:0.7" \
  --cpu 0.5 --memory 1Gi \
  --env-vars "BRIGHTDATA_JOB_MODE=dry-run" "WALMART_STORE_ID=100" "WALMART_ZIPCODE=72712"

az containerapp job start -n walmart-brightdata-100 -g "$RESOURCE_GROUP"
az containerapp job execution list -n walmart-brightdata-100 -g "$RESOURCE_GROUP" -o table
```

**Note:** The job must be granted ACR image-pull permission before starting if registry is private. Refer to Microsoft's `az containerapp job registry set` instructions; **do not** set the ACR admin account public solely to make this work.

### Test existing snapshot without launching a new collection

Have the client put `BRIGHTDATA_API_KEY` and `AZURE_STORAGE_CONNECTION_STRING` in Container Apps Job secrets or Key Vault. Reference the secret names in container environment variables (`BRIGHTDATA_API_KEY=secretref:brightdata-key`, `AZURE_STORAGE_CONNECTION_STRING=secretref:blob-conn`); never write key values into the repository. Change job mode to `snapshot` and specify an **actual** unexpired `BRIGHTDATA_SNAPSHOT_ID` supplied by the client. Start one manual execution and inspect logs and private Blob objects. Downloading existing snapshots may be subject to plan limits; verify with the account.

If the actual `snapshot_id` is unknown, `BRIGHTDATA_JOB_MODE=dry-run` is the correct nonbillable first step. The browser's `sd_...` downloaded **filename** is *not* necessarily the `s_...` API snapshot ID.

### Enable twice-weekly collection only after billing/access acceptance

1. Verify a real Bright Data `category_url` API test and actual category IDs, store/ZIP correctness, cost/returned-record count, and source rights. The 11 broad `/cp/` URLs alone have *not* proven complete subcategory discovery. Generate and approve a complete descendant category input manifest and pagination coverage before production.
2. Set `WALMART_DATA_AUTHORIZED=yes`, `BRIGHTDATA_COLLECTION_APPROVED=yes` and `BRIGHTDATA_RECORD_CAP=<CLIENT_APPROVED_BOUND>` securely in the job environment. **The record cap prevents a truly unlimited production scrape.** Full uncapped traversal requires a separately reviewed design and cost commitment; **not implemented by this pilot**.
3. Set `BRIGHTDATA_JOB_MODE=trigger`, configure the above credentials via secret references, then change the Manual job to a scheduled job or create a separate job with `--trigger-type Schedule --cron-expression '0 6 * * 1,4'`. This means Monday and Thursday **06:00 UTC**. The production schedule must remain disabled until a bounded provider test passes.
4. Validate the first manual end-to-end run in Azure, repeat the same snapshot without a duplicate vendor trigger, and then test an independently fresh run with failure/recovery. Only after observing those tests should we claim automatic twice-weekly production operation.

There is **no need for the client to download/upload JSON manually** once these credentials, subscriptions, schedule and approved inputs are configured. The output is private Azure Blob data; the client's chosen dashboard/software can read `latest-trial.json` and the corresponding versioned `data_22_fields.json`, or they can receive controlled time-limited SAS links generated outside this program.

## Important outstanding engineering risks

- Client acceptance: local price evidence, directly displayed PPM, complete and real digital/volume deals, category coverage and production Azure observation are unverified. Existing trial data must never be represented as acceptance-ready.
- No guaranteed server-side charge cap from this implementation: provider `limit_multiple_results` must be independently verified to enforce paid usage; Azure itself also incurs compute, storage and logging charges. Keep API collection permission off until budget approval.
- This pilot is single-job, single-store. Concurrent runs may race on history. Do not enable multiple overlapping schedules/manual launches; production needs a renewable Blob lease or comparable distributed lock and version-safe transactions.
- The small window between provider trigger acceptance and checkpoint write can create a double-trigger after a process crash. A billing-safe workflow needs provider-side idempotency or a reconciled snapshot listing before authorizing unattended high-volume runs.
- Error-only snapshots do not advance latest-trial; prior history stays intact. Not seeing a product in a partial sample never makes it freshly unavailable.
- Bright Data may return incomplete or mismatched store data (observed in uploaded snapshots). Validation rejects such records; it cannot manufacture missing evidence.

References: https://docs.brightdata.com/api-reference/web-scraper-api/management-apis/monitor-progress and https://learn.microsoft.com/en-us/azure/container-apps/jobs-get-started-cli

### One-time migration of original observed product history (not yet executed in Azure)

The original **615-candidate** complete private evidence/history package must be located and checked for provenance before seeding. Earlier v0.7 examples were written when only 381 products were available. **This is a one-time seed, not a manual operation every week**. Extract that history file to a PRIVATE location accessible to the Azure administrator. With the owner's Blob credentials in their environment, run:

```bash
# Preview/check store, ZIP and exact 22-column order, without uploading:
python tools/seed_azure_history.py --history /private/history.json
# Upload exactly once, only after review:
python tools/seed_azure_history.py --history /private/history.json --confirm-upload
```

This refuses to overwrite an existing remote history. The history migration remains **unexecuted in Azure**, and the records are **trial candidates**, not certified prices. Future automated snapshot downloads read and update the persisted history. Keep the original private evidence archive and source snapshots secure; they are not part of the source repository.
