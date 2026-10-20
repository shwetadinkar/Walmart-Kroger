#!/usr/bin/env bash
# Create one Azure Container Apps scheduled job per VERIFIED Mariano's store.
# Does not perform a deployment unless --execute is passed.
# Requires the container image to be built/pushed and config/stores_live.json baked in.
set -euo pipefail

MODE="${1:---dry-run}"
if [[ "$MODE" != "--execute" && "$MODE" != "--dry-run" ]]; then
  echo "Usage: bash azure/deploy_jobs.sh [--dry-run|--execute]" >&2
  exit 2
fi
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STORES_FILE="${STORES_FILE:-$ROOT/config/stores_live.json}"
if [[ ! -f "$STORES_FILE" ]]; then
  echo "Missing stores_live.json: configure verified locationIds before deployment." >&2
  exit 2
fi
: "${RESOURCE_GROUP:?Set RESOURCE_GROUP}"
: "${CONTAINERAPPS_ENVIRONMENT:?Set CONTAINERAPPS_ENVIRONMENT}"
: "${IMAGE:?Set IMAGE to published container image}"
: "${PROVIDER_BASE_URL:?Set PROVIDER_BASE_URL to approved HTTPS provider endpoint}"
[[ "$PROVIDER_BASE_URL" == https://* ]] || { echo 'PROVIDER_BASE_URL must start with https://' >&2; exit 2; }
if [[ "$MODE" == '--execute' ]]; then
  : "${PROVIDER_API_TOKEN:?Required; use Azure Key Vault in production}"
  : "${AZURE_STORAGE_CONNECTION_STRING:?Required; use Azure Key Vault in production}"
  command -v az >/dev/null || { echo 'Azure CLI not installed' >&2; exit 2; }
  az account show --output none || { echo 'az login required' >&2; exit 2; }
fi

# Read JSON via Python; no jq dependency. This validation also rejects DEMO IDs.
STORE_DATA="$(python - "$STORES_FILE" <<'PY'
import json, sys, re
try:
    doc=json.load(open(sys.argv[1], encoding='utf-8'))
    stores=[x for x in doc['stores'] if x.get('enabled',True)]
    assert stores, 'No enabled stores'
    for s in stores:
        sid=str(s['store_id'])
        assert not sid.upper().startswith(('DEMO','REPLACE','UNRESOLVED'))
        assert re.fullmatch(r'[0-9A-Za-z_-]{4,25}', sid)
        assert re.fullmatch(r'\d{5}', str(s['zipcode']))
        assert 'mariano' in str(s['store_name']).lower()
        print(sid)
except (AssertionError,KeyError,ValueError) as ex:
    print('Invalid verified store configuration: '+str(ex), file=sys.stderr)
    sys.exit(2)
PY
)" || exit 2
mapfile -t STORE_IDS <<< "$STORE_DATA"
if ((${#STORE_IDS[@]} == 0)) || [[ -z "${STORE_IDS[0]:-}" ]]; then
  echo "No validated stores found; refusing to deploy" >&2
  exit 2
fi

for STORE_ID in "${STORE_IDS[@]}"; do
  CLEAN_ID="$(printf %s "$STORE_ID" | tr '[:upper:]_' '[:lower:]-' | cut -c1-20)"
  JOB_NAME="marianos-$CLEAN_ID"
  CRON="${CRON_EXPRESSION:-0 6 * * 1,4}"
  echo "Job: $JOB_NAME | store_id: $STORE_ID | schedule (UTC): $CRON"
  if [[ "$MODE" == '--dry-run' ]]; then
    echo 'DRY RUN: no network requests or Azure changes. Never include secrets in logs.'
    continue
  fi
  if az containerapp job show -n "$JOB_NAME" -g "$RESOURCE_GROUP" --output none 2>/dev/null; then
    echo "Job already exists: $JOB_NAME. Review manually; not overwriting." >&2
    exit 1
  fi
  # NOTE: Passing secret values to CLI args exposes them to local process inspection.
  # Preferred production method is managed identity + Key Vault references set by Azure admin.
  az containerapp job create \
    --name "$JOB_NAME" --resource-group "$RESOURCE_GROUP" \
    --environment "$CONTAINERAPPS_ENVIRONMENT" \
    --trigger-type Schedule --cron-expression "$CRON" \
    --parallelism 1 --replica-completion-count 1 \
    --replica-timeout "${REPLICA_TIMEOUT:-7200}" --replica-retry-limit 0 \
    --cpu "${CPU:-0.5}" --memory "${MEMORY:-1.0Gi}" \
    --image "$IMAGE" \
    --secrets "marianos-provider-token=$PROVIDER_API_TOKEN" "marianos-blob=$AZURE_STORAGE_CONNECTION_STRING" \
    --env-vars "PROVIDER_BASE_URL=$PROVIDER_BASE_URL" \
               'PROVIDER_API_TOKEN=secretref:marianos-provider-token' \
               'AZURE_STORAGE_CONNECTION_STRING=secretref:marianos-blob' \
               'MARIANOS_DATA_AUTHORIZED=yes' \
               "AZURE_BLOB_CONTAINER=${AZURE_BLOB_CONTAINER:-marianos-collection}" \
               "MARIANOS_STORE_ID=$STORE_ID" \
    --output none
  echo "Created: $JOB_NAME (not yet live-validated)"
done
