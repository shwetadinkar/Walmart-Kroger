# Mariano's pilot in the existing Azure environment

Recovered from the verified Walmart runbook: subscription Azure subscription 1, resource group `rg-walmart63-trial`, Container Apps environment `env-walmart63`, region South India, storage account `stwalmart63trial1024`, existing private container `retail-collection`.

Create a separate **manual** job `marianos-westloop-api-pilot`. Do not edit `walmart63-collector` or replace its image, environment variables, identity or Blob files.

`existing_environment_pilot.json` describes the separate job. It reuses the environment and container; it does not create a new environment, storage account, registry or schedule. Its JSON syntax is checked locally; Azure validation/deployment remains unverified. Supply an immutable image digest built after the managed-identity changes. The earlier `0b1959e...` image cannot run the new identity path.

The initial job is limited to five normalized records, one product query, six total HTTP attempts, ten minutes and no replica retries. The Products API query may return up to 50 source products; only five qualifying records are selected. OAuth and store checks consume the same six-request budget. This is a small Azure feasibility run, not the 604-record delivery or a full-category run.

The API client ID and secret are secure deployment parameters and Container Apps job secrets. Do not put them in template files, ordinary environment variables, terminal arguments, screenshots, source archives or GitHub. Prefer Key Vault references for maintained deployments. Passing a secure parameter protects the template definition; authorized Azure administrators can still access the resulting resource secrets.

The new job uses its own system-assigned managed identity. Before it can use existing Blob storage, an Azure administrator must approve and grant **Storage Blob Data Contributor at the existing retail-collection container scope** to that new identity. Do not change the Walmart identity. Role assignment expands access and must be confirmed before applying it.

Storage authentication uses `AZURE_STORAGE_ACCOUNT_URL` and ManagedIdentityCredential. No storage account key is needed, and the managed-identity path never creates a container. Outputs and locks use the unique Mariano's location 53100508 (`trials/53100508/`, `checkpoints/53100508/`, `locks/53100508.lock`). The role scope still grants access to the whole shared container; use a separately created Mariano's container if stronger retailer isolation is required.

After permission propagation, run once and inspect execution status, console summary, checkpoint objects and `trials/53100508/latest.json`. Download the exported records and validate store, ZIP, ordered fields and provenance. A successful image build or role assignment is not a successful collection.

Only after the pilot is observed may a separately named run request target 650 / minimum 500 / maximum 40 queries / maximum 60 requests. Changing bounds under the same run ID fails closed. Retain manual execution until the scheduled run and monitoring requirements have been reviewed. Keyword sampling does not establish complete-category coverage.

Current dependency: sign into the Azure portal in this chat, then inspect the existing resources and review the new job before deployment. No Azure mutations have been made in this continuation.
