#!/usr/bin/env bash
set -euo pipefail

# This is a template, not an executed deployment.
# Prerequisites: az login; Azure containerapp extension; existing resource group,
# environment, registry permissions, and an ALREADY AUTHORIZED route.
: "${RESOURCE_GROUP:?set existing Azure resource group}"
: "${CONTAINERAPPS_ENVIRONMENT:?set existing Container Apps environment}"
: "${IMAGE:?set accessible Docker image e.g. myacr.azurecr.io/walmart-collector:0.1}"
: "${AZURE_STORAGE_CONNECTION_STRING:?set Azure Blob Storage connection string securely}"

# Which authorized route this deployment uses. All run the same image.
#   provider  - approved third-party feed implementing the Page contract
#   opd       - Walmart I/O OPD catalog and price snapshot (see OPD_CLIENT_RUNBOOK.md)
#   composite - one of the above as the spine, with per-field enrichment
# The synthetic fixture source is intentionally not deployable.
WALMART_SOURCE="${WALMART_SOURCE:-provider}"
case "$WALMART_SOURCE" in
  provider|opd|composite) ;;
  *) echo "WALMART_SOURCE must be provider, opd or composite, not '$WALMART_SOURCE'" >&2; exit 2;;
esac

WALMART_SPINE="${WALMART_SPINE:-opd}"
if [[ "$WALMART_SOURCE" == 'composite' ]]; then
  case "$WALMART_SPINE" in
    provider|opd) ;;
    *) echo "WALMART_SPINE must be provider or opd, not '$WALMART_SPINE'" >&2; exit 2;;
  esac
fi

# Whichever route actually enumerates the assortment decides which credentials
# are required.
EFFECTIVE_ROUTE="$WALMART_SOURCE"
[[ "$WALMART_SOURCE" == 'composite' ]] && EFFECTIVE_ROUTE="$WALMART_SPINE"

if [[ "$EFFECTIVE_ROUTE" == 'provider' ]]; then
  : "${PROVIDER_BASE_URL:?set approved provider HTTPS endpoint}"
  [[ "$PROVIDER_BASE_URL" == https://* ]] || { echo 'PROVIDER_BASE_URL must start with https://' >&2; exit 2; }
  : "${PROVIDER_API_TOKEN:?set authorized provider token securely}"
else
  : "${WALMART_OPD_CLIENT_ID:?set OPD client id securely}"
  : "${WALMART_OPD_CLIENT_SECRET:?set OPD client secret securely}"
fi

# NOTICE: Azure CLI receives secrets via process arguments. Use a Key Vault secret
# reference and managed identity instead for production (see AZURE_DEPLOYMENT.md).
for store in ${WALMART_STORE_IDS:-100 5959}; do
  name="walmart-collect-${store}"
  DESCRIPTION="$WALMART_SOURCE"
  [[ "$WALMART_SOURCE" == 'composite' ]] && DESCRIPTION="composite (spine: $WALMART_SPINE)"
  echo "Job: $name | store: $store | source: $DESCRIPTION | schedule (UTC): ${CRON_EXPRESSION:-0 6 * * 1,4}"

  SECRETS=("blob-conn=$AZURE_STORAGE_CONNECTION_STRING")
  ENVVARS=("WALMART_STORE_ID=$store"
           'WALMART_DATA_AUTHORIZED=yes'
           "WALMART_SOURCE=$WALMART_SOURCE"
           'AZURE_STORAGE_CONNECTION_STRING=secretref:blob-conn'
           "AZURE_BLOB_CONTAINER=${AZURE_BLOB_CONTAINER:-retail-collection}")
  [[ "$WALMART_SOURCE" == 'composite' ]] && ENVVARS+=("WALMART_SPINE=$WALMART_SPINE")

  if [[ "$EFFECTIVE_ROUTE" == 'provider' ]]; then
    SECRETS+=("provider-token=$PROVIDER_API_TOKEN")
    ENVVARS+=("PROVIDER_BASE_URL=$PROVIDER_BASE_URL"
              'PROVIDER_API_TOKEN=secretref:provider-token')
  else
    SECRETS+=("opd-client-id=$WALMART_OPD_CLIENT_ID" "opd-client-secret=$WALMART_OPD_CLIENT_SECRET")
    ENVVARS+=('WALMART_OPD_CLIENT_ID=secretref:opd-client-id'
              'WALMART_OPD_CLIENT_SECRET=secretref:opd-client-secret')
  fi

  if [[ "${1:---dry-run}" == '--dry-run' ]]; then
    echo 'DRY RUN: no network requests or Azure changes. Never include secrets in logs.'
    continue
  fi

  az containerapp job create \
    --name "$name" \
    --resource-group "$RESOURCE_GROUP" \
    --environment "$CONTAINERAPPS_ENVIRONMENT" \
    --trigger-type Schedule \
    --cron-expression "${CRON_EXPRESSION:-0 6 * * 1,4}" \
    --replica-timeout "${REPLICA_TIMEOUT:-14400}" \
    --replica-retry-limit 0 \
    --parallelism 1 \
    --replica-completion-count 1 \
    --image "$IMAGE" \
    --cpu 1 --memory 2Gi \
    --secrets "${SECRETS[@]}" \
    --env-vars "${ENVVARS[@]}"
done
