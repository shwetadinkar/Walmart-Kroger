#!/usr/bin/env bash
set -euo pipefail
# Intentionally creates ONLY a non-collecting manual job; no API costs are incurred.
# Azure resource creation/image storage may incur charges; require explicit approval.
if [[ "${AZURE_DEPLOY_APPROVED:-}" != "yes" ]]; then
    echo "STOP: Set AZURE_DEPLOY_APPROVED=yes only after Azure account owner agrees to any Azure charges." >&2
    exit 2
fi
: "${RESOURCE_GROUP:?Name of existing approved Resource Group required}"
: "${CONTAINERAPPS_ENVIRONMENT:?Existing Container Apps Environment required}"
: "${IMAGE:?Prebuilt authorized ACR image required, e.g. myacr.azurecr.io/walmart-brightdata:0.7}"
: "${WALMART_STORE_ID:=100}"
: "${WALMART_ZIPCODE:=72712}"

az containerapp job create \
  --name "walmart-brightdata-${WALMART_STORE_ID}" \
  --resource-group "$RESOURCE_GROUP" \
  --environment "$CONTAINERAPPS_ENVIRONMENT" \
  --trigger-type Manual \
  --replica-timeout 14400 --replica-retry-limit 0 \
  --parallelism 1 --replica-completion-count 1 \
  --image "$IMAGE" --cpu 0.5 --memory 1Gi \
  --env-vars 'BRIGHTDATA_JOB_MODE=dry-run' \
      "WALMART_STORE_ID=${WALMART_STORE_ID}" "WALMART_ZIPCODE=${WALMART_ZIPCODE}"
echo 'Created safe manual job (dry-run only). No scraping scheduled or triggered.'
