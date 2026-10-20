# Azure Container Apps Jobs — conditional deployment

The CLI deployer in `deploy_jobs.sh` **actually creates** scheduled jobs only with `--execute`. By default it performs an offline `--dry-run`. It cannot deploy until approved provider credentials, a verified `locationId`, an Azure subscription, Azure CLI access, and a pushed image exist. Docker builds and Azure charges have not been verified in this project.

## Prerequisites

1. Obtain a full-category **authorized** data source implementing `examples/provider_page_contract.json`. A Kroger Public Products API `filter.term` search cannot serve as a complete category enumeration without additional approved coverage evidence.
2. Get each Mariano's `locationId` using `python -m marianos_collector kroger-locations --zipcode ...` with the appropriate Kroger API credentials. Verify address/brand in the returned response. Enter IDs in `config/stores_live.json` (copy the template). This file is baked into the Docker image; never use `DEMO-...` IDs.
3. Create an Azure resource group, Container Apps environment, Blob Storage account/container, and a container registry. Run `az login` with the proper subscription context.
4. Build and push a tagged container image that includes your verified store configuration. Example commands (substitute registry and tag):

```bash
cp config/stores_live.template.json config/stores_live.json
# Edit to use verified live IDs before proceeding.
docker build -t myregistry.azurecr.io/marianos-collector:0.2.0 .
docker push myregistry.azurecr.io/marianos-collector:0.2.0
```

5. Set environment variables in the operator's secure shell/CI store:

```bash
export RESOURCE_GROUP='my-rg'
export CONTAINERAPPS_ENVIRONMENT='my-jobs-env'
export IMAGE='myregistry.azurecr.io/marianos-collector:0.2.0'
export PROVIDER_BASE_URL='https://approved-provider.example/api/category-page'
# Only for --execute: supplied by secure secret storage (do not commit).
export PROVIDER_API_TOKEN='***'
export AZURE_STORAGE_CONNECTION_STRING='***'
```

6. Check job definitions **without** Azure calls:

```bash
bash azure/deploy_jobs.sh --dry-run
```

7. When environment/permissions are approved, deploy:

```bash
bash azure/deploy_jobs.sh --execute
```

**Security:** This example passes secret values to the Azure CLI and they may be visible to local process inspection. For production, have the Azure administrator configure Key Vault references and managed identity instead. Do not put credentials in screenshots, ZIPs, logs or Freelancer entries. The image may need separate registry-pull authorization through its Azure identity; deploying is not proof of execution.

**Schedule:** default `0 6 * * 1,4` = Monday/Thursday 06:00 UTC. Override using `CRON_EXPRESSION`. The CLI creates one job per verified store. Each job uses an Azure Blob lease so concurrent runs for the same store fail closed. Set `REPLICA_TIMEOUT`, `CPU`, `MEMORY` based on measured production load. Execution logs should be reviewed using `az containerapp job execution list` and Azure Monitor.

**Publication:** The collector stages data, validates every category and promotes `latest.json` only after a full successful run. A two-category trial lives in a separate trial namespace and cannot replace the complete published data.

References:
- https://learn.microsoft.com/en-us/azure/container-apps/jobs
- https://learn.microsoft.com/en-us/cli/azure/containerapp/job
