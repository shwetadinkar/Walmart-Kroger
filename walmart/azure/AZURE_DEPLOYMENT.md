# Azure deployment (not yet deployed; v0.5.0)

## Architecture

Two scheduled Azure Container Apps Jobs (one per store) run the same immutable image, with `WALMART_STORE_ID` set differently. They use a **single Azure Blob container** for remote staging, checkpoints, versioned data, and per-store 60-second renewable leases. Each job starts Monday and Thursday at **06:00 UTC** (`0 6 * * 1,4`). A Blob lease prevents two overlapping executions of the **same store**. OPD snapshot collection now publishes only to the trial namespace; do not schedule OPD as a complete production scraper. The jobs are not guaranteed to finish in four hours; adjust `--replica-timeout 14400` based on a measured full run.

## Prerequisites

1. Confirm authorization to obtain the requested Walmart pricing and a provider capable of the documented `Page` contract. Walmart.com HTML/browser access is not automatically authorized.
2. Have an existing Azure resource group, Container Apps environment, and Azure Storage account. Give the job identity proper access to its image registry.
3. Build and publish the image. For Azure Container Registry, use `az acr build --registry YOUR_REGISTRY --image walmart-collector:0.1 .` from project root.
4. Create a private Blob container or let the Azure SDK create one; protect its connection string. Ensure the Azure identity or storage credential has Blob read, write, lease permissions.
5. Prefer a **managed identity + Azure Key Vault references** for production. The CLI template in `deploy_jobs.sh` passes environment-supplied secrets through Azure CLI process arguments during creation and is only a controlled demonstration; never commit secret values or echo them to logs.

## Quick example

Configure `RESOURCE_GROUP`, `CONTAINERAPPS_ENVIRONMENT`, `IMAGE`, `PROVIDER_BASE_URL`, `PROVIDER_API_TOKEN`, `AZURE_STORAGE_CONNECTION_STRING` as local environment variables. Run `bash azure/deploy_jobs.sh` after reviewing it and the resulting Azure resources. If the registry is private, first configure Azure Container Apps to authenticate via managed identity. The script does not set up a registry, private network, secret rotation, alerts, cost quotas, or a provider subscription.

The job Docker image runs:

```bash
walmart-collector run --source provider --authorized-source --backend azure
```

`WALMART_STORE_ID` is read from the environment. The live mode refuses to start without the `--authorized-source` affirmation AND `WALMART_DATA_AUTHORIZED=yes`, plus a configured HTTPS provider endpoint and API token.

## Run, inspect, recover

```bash
az containerapp job execution list --name walmart-collect-100 --resource-group "$RESOURCE_GROUP"
az containerapp job execution list --name walmart-collect-5959 --resource-group "$RESOURCE_GROUP"
```

Structured JSON logs go to standard error (capture with Azure Monitor / Log Analytics if configured). Inspect the Blob container keys:

- `published/<store_id>/latest.json` — pointer to only the last validated complete run
- `published/<store_id>/runs/<release>/data.json` — exact 22-field records
- `published/<store_id>/runs/<release>/report.json` — category and validation report
- `published/<store_id>/runs/<release>/manifest.json` — version metadata
- `checkpoints/<store_id>/<category>.json` — in-progress cursor/queue; retained on failure
- `staging/<store_id>/<run_id>/<category>/<page>.json` — source pages needed for actual resume

On interruption, rerun within seven days: the queue resumes without repeating completed category/page stages. After seven days, review the old data, then use `clear-checkpoints --confirm-reset` only after confirming a fresh run is appropriate. Reset does not delete the successful snapshot. Staging can grow; implement lifecycle rules **only for old, confirmed-unused staging**, never active checkpoint references.

## Critical limitations and validation

This image has **not been tested in the buyer's Azure subscription**. The remote approved provider is not supplied, so there is no live 500-record proof. Schedule, IAM, network connectivity, provider reliability, store evidence, domain-specific product accuracy and operational costs require real acceptance testing. Compute, Blob writes/checkpoints, Azure Monitor ingestion, registry, networking and provider data access may all incur charges.

If the data source requires more than 4 hours for all categories, plan job partitioning with per-category locks / a coordinator; do not turn up concurrency against retailer endpoints without the provider's contract and budget allowing it.

Official Microsoft documentation: https://learn.microsoft.com/en-us/azure/container-apps/jobs-get-started-cli

## Walmart OPD (v0.4) integration warning

When using `--source opd`, provide `WALMART_OPD_CLIENT_ID`, `WALMART_OPD_CLIENT_SECRET`, and `WALMART_DATA_AUTHORIZED=yes` securely. Always include `--authorized-source` and `--opd-cache` pointing to a **persistent mounted volume** (e.g. Azure Files). Ephemeral Container Apps storage cannot preserve the SQLite feed-import checkpoints across container restarts. The source uses `--backend azure` for final published outputs; live API and Azure deployment have not been verified. Audit the provisional category mappings and price-role semantics before treating any live output as contest-ready. Read `OPD_CLIENT_RUNBOOK.md`.

## Retries and failure alerting

A refused run is retried by `retry_supervisor.py` inside the same replica:
eight retries at fifteen minute intervals by default, then a failure notice.
The two scheduled jobs still fire together on `0 6 * * 1,4`, one per store, and
the Blob lease still prevents two overlapping executions of the same store. The
deployment now also refuses a replica timeout that is not shorter than the gap
between firings, so the lease is never asked to arbitrate between a retrying
run and that same job's next firing.

`bash azure/deploy_jobs.sh --dry-run` prints the resolved plan and the
configured failure route. It **refuses** a `REPLICA_TIMEOUT` that cannot reach
every configured attempt and quotes the figure to set: eight retries at 900s is
7200s of waiting alone, so the default plan needs at least 11220s. The default
is now 21600s, up from 14400s.

**The first attempt gets the whole window and retries get what it leaves**, so
a run that succeeds is never starved to pay for retries it does not need, and a
run stopped by its own `--max-seconds` budget is not retried: there is nothing
left to retry it with, and the next attempt would get less time, not more.

Not retried: a usage error, and a bot challenge. Everything else is, including
an expired credential.

### Getting told about a failure

A final failure always prints one line to the job log:

```
WALMART_RUN_FAILED_AFTER_RETRIES store=... source=... runs=9 exit_codes=1,1,...
```

**The credential-free route is an Azure Monitor log alert on that string**,
needing nothing deployed with the image and no secret anywhere:

```kusto
ContainerAppConsoleLogs_CL
| where Log_s contains "WALMART_RUN_FAILED_AFTER_RETRIES"
| project TimeGenerated, Log_s
```

**Deliberately filtered on the marker alone.** Microsoft's
`learn.microsoft.com/azure/container-apps/log-monitoring` documents this table
for container *apps*: it does not mention jobs and documents no job-name
column. `ContainerName_s` is the container's name, not the job's, so narrowing
on it would most likely match nothing and the alert would stay silent through a
real failure. The marker carries the store and source itself. Both stores write
the same marker, so add a job-name filter only after confirming in your own
workspace which column holds it.

For email from the job itself, set `ALERT_EMAIL_TO` and `SMTP_HOST` when
deploying, plus `SMTP_USERNAME` and `SMTP_PASSWORD` if the relay authenticates.
The password is stored as an Azure secret and referenced with `secretref:`; it
is in no file here. A failed email never replaces the failure it reports.
