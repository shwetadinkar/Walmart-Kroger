#!/usr/bin/env bash
set -euo pipefail

# This is a template, not an executed deployment.
# Prerequisites: az login; Azure containerapp extension; existing resource group,
# environment, registry permissions, and an ALREADY AUTHORIZED provider license.
: "${RESOURCE_GROUP:?set existing Azure resource group}"
: "${CONTAINERAPPS_ENVIRONMENT:?set existing Container Apps environment}"
: "${IMAGE:?set accessible Docker image e.g. myacr.azurecr.io/walmart-collector:0.1}"
: "${PROVIDER_BASE_URL:?set approved provider HTTPS endpoint}"
: "${PROVIDER_API_TOKEN:?set authorized provider token securely}"
: "${AZURE_STORAGE_CONNECTION_STRING:?set Azure Blob Storage connection string securely}"

# NOTICE: Azure CLI receives secrets via process arguments. Use a Key Vault secret
# reference and managed identity instead for production (see AZURE_DEPLOYMENT.md).
for store in 100 5959; do
  name="walmart-collect-${store}"
  az containerapp job create \
    --name "$name" \
    --resource-group "$RESOURCE_GROUP" \
    --environment "$CONTAINERAPPS_ENVIRONMENT" \
    --trigger-type Schedule \
    --cron-expression '0 6 * * 1,4' \
    --replica-timeout 14400 \
    --replica-retry-limit 0 \
    --parallelism 1 \
    --replica-completion-count 1 \
    --image "$IMAGE" \
    --cpu 1 --memory 2Gi \
    --secrets "provider-token=$PROVIDER_API_TOKEN" "blob-conn=$AZURE_STORAGE_CONNECTION_STRING" \
    --env-vars \
        "WALMART_STORE_ID=$store" \
        'WALMART_DATA_AUTHORIZED=yes' \
        "PROVIDER_BASE_URL=$PROVIDER_BASE_URL" \
        'PROVIDER_API_TOKEN=secretref:provider-token' \
        'AZURE_STORAGE_CONNECTION_STRING=secretref:blob-conn' \
        'AZURE_BLOB_CONTAINER=retail-collection'
done
