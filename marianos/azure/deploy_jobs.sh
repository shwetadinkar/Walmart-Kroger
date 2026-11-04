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

# Which authorized route this deployment uses. Both run the same image.
#   provider   - approved third-party feed implementing the Page contract
#   catalog_v2 - Kroger Catalog V2 partner API (see marianos/CATALOG_V2_RUNBOOK.md)
#   sweep      - Kroger PUBLIC Products API term sweep, driven by the collector.
#                Publishes to the trial namespace only, because term-filtered
#                search cannot attest category coverage. Carries no displayed
#                price per measure and no deal wording: the public tier has
#                neither. Sits under the open question in
#                marianos/ACCEPTABLE_USE_POSITION.md.
# The synthetic fixture source is intentionally not deployable.
MARIANOS_SOURCE="${MARIANOS_SOURCE:-provider}"
case "$MARIANOS_SOURCE" in
  provider|catalog_v2|sweep) ;;
  *) echo "MARIANOS_SOURCE must be 'provider', 'catalog_v2' or 'sweep', not '$MARIANOS_SOURCE'" >&2; exit 2;;
esac

if [[ "$MARIANOS_SOURCE" == 'provider' ]]; then
  : "${PROVIDER_BASE_URL:?Set PROVIDER_BASE_URL to approved HTTPS provider endpoint}"
  [[ "$PROVIDER_BASE_URL" == https://* ]] || { echo 'PROVIDER_BASE_URL must start with https://' >&2; exit 2; }
else
  # Kroger's locationId is not necessarily the collector's store_id.
  : "${KROGER_LOCATION_ID:?Set KROGER_LOCATION_ID from a verified Kroger Locations response}"
  case "$KROGER_LOCATION_ID" in
    DEMO*|REPLACE*|UNRESOLVED*) echo 'KROGER_LOCATION_ID must be a verified location, not a placeholder' >&2; exit 2;;
  esac
fi

if [[ "$MARIANOS_SOURCE" == 'sweep' ]]; then
  # The sweep resolves its store from Kroger's own /locations response rather
  # than from stores_live.json, and asserts the address: the assigned store id
  # differs from West Loop's by two characters, and the first sweep run shipped
  # 18,351 records with a blank store_name and store_location.
  : "${MARIANOS_EXPECT_ZIPCODE:?Set MARIANOS_EXPECT_ZIPCODE to the ZIP the resolved store must be in}"
  : "${MARIANOS_EXPECT_STREET:?Set MARIANOS_EXPECT_STREET to the street the resolved store must be at}"
fi

if [[ "$MODE" == '--execute' ]]; then
  : "${AZURE_STORAGE_CONNECTION_STRING:?Required; use Azure Key Vault in production}"
  if [[ "$MARIANOS_SOURCE" == 'provider' ]]; then
    : "${PROVIDER_API_TOKEN:?Required; use Azure Key Vault in production}"
  else
    : "${KROGER_CLIENT_ID:?Required; use Azure Key Vault in production}"
    : "${KROGER_CLIENT_SECRET:?Required; use Azure Key Vault in production}"
  fi
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
  echo "Job: $JOB_NAME | store_id: $STORE_ID | source: $MARIANOS_SOURCE | schedule (UTC): $CRON"
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
  # The replica timeout, resolved once and used for BOTH the deployment and the
  # collector's own budget, so the two cannot drift apart.
  #
  # They were previously equal by coincidence: this script deployed
  # --replica-timeout 7200 and the entrypoint passed no budget, so the CLI
  # default of 7200 applied. The collector's graceful stop and Azure's SIGKILL
  # therefore landed on the same instant, and SIGKILL is not an exception, so an
  # overrunning unattended run would leave no release AND no refusal record.
  # The entrypoint derives its budget from REPLICA_TIMEOUT minus headroom, and
  # that variable is passed in below so it sees the figure actually deployed.
  REPLICA_TIMEOUT="${REPLICA_TIMEOUT:-7200}"
  if (( REPLICA_TIMEOUT <= 900 )); then
    echo "ERROR: REPLICA_TIMEOUT=$REPLICA_TIMEOUT leaves the collector no room to" >&2
    echo "       stop itself and publish. It must exceed the 900s headroom." >&2
    exit 1
  fi

  SECRETS=("marianos-blob=$AZURE_STORAGE_CONNECTION_STRING")
  ENVVARS=('AZURE_STORAGE_CONNECTION_STRING=secretref:marianos-blob'
           'MARIANOS_DATA_AUTHORIZED=yes'
           "MARIANOS_SOURCE=$MARIANOS_SOURCE"
           "AZURE_BLOB_CONTAINER=${AZURE_BLOB_CONTAINER:-marianos-collection}"
           "REPLICA_TIMEOUT=$REPLICA_TIMEOUT"
           "MARIANOS_STORE_ID=$STORE_ID")
  if [[ "$MARIANOS_SOURCE" == 'provider' ]]; then
    SECRETS+=("marianos-provider-token=$PROVIDER_API_TOKEN")
    ENVVARS+=("PROVIDER_BASE_URL=$PROVIDER_BASE_URL"
              'PROVIDER_API_TOKEN=secretref:marianos-provider-token')
  else
    SECRETS+=("kroger-client-id=$KROGER_CLIENT_ID" "kroger-client-secret=$KROGER_CLIENT_SECRET")
    ENVVARS+=('KROGER_CLIENT_ID=secretref:kroger-client-id'
              'KROGER_CLIENT_SECRET=secretref:kroger-client-secret'
              "KROGER_LOCATION_ID=$KROGER_LOCATION_ID"
              "CATALOG_V2_FULFILLMENT=${CATALOG_V2_FULFILLMENT:-curbside}")
    # Only set when the partner agreement issues a scope other than the default.
    [[ -n "${CATALOG_V2_SCOPE:-}" ]] && ENVVARS+=("CATALOG_V2_SCOPE=$CATALOG_V2_SCOPE")
    # CATALOG_V2_UNIT_IS_PPM is deliberately NOT forwarded, and the collector
    # ignores it. It used to promote Catalog V2's `unit` field, whose meaning
    # the contract does not state, into the published `ppm` column, on an
    # unattended job, with no shape validation anywhere. An env var is a
    # toggle, not a gate, and `ppm` is the displayed per-measure rate. The
    # field is carried in the audit record instead, so what it means can still
    # be settled from a live response: by a reviewed code change, not a
    # deployment variable.
  fi
  if [[ "$MARIANOS_SOURCE" == 'sweep' ]]; then
    ENVVARS+=("MARIANOS_EXPECT_ZIPCODE=$MARIANOS_EXPECT_ZIPCODE"
              "MARIANOS_EXPECT_STREET=$MARIANOS_EXPECT_STREET")
    # MARIANOS_DATA_AUTHORIZED is set above for every job. The sweep does not
    # pass --authorized-source, so it does not assert an authorization it has
    # not got; see container_entrypoint.py.
    #
    # The sweep's own checkpoint and its raw API responses live under
    # MARIANOS_SWEEP_WORK_DIR, which defaults to container-local /tmp. Each
    # execution of an Azure Container Apps job gets a fresh container, so
    # without a mounted volume there is no resume ACROSS executions: a stopped
    # sweep restarts from term one next time. The runner's own checkpoint is in
    # Blob storage and does survive. Set MARIANOS_SWEEP_WORK_DIR to a mounted
    # path to make the sweep resumable between executions; this script does not
    # mount one, and no observed run has exercised that.
    [[ -n "${MARIANOS_SWEEP_WORK_DIR:-}" ]] && ENVVARS+=("MARIANOS_SWEEP_WORK_DIR=$MARIANOS_SWEEP_WORK_DIR")
  fi
  az containerapp job create \
    --name "$JOB_NAME" --resource-group "$RESOURCE_GROUP" \
    --environment "$CONTAINERAPPS_ENVIRONMENT" \
    --trigger-type Schedule --cron-expression "$CRON" \
    --parallelism 1 --replica-completion-count 1 \
    --replica-timeout "$REPLICA_TIMEOUT" --replica-retry-limit 0 \
    --cpu "${CPU:-0.5}" --memory "${MEMORY:-1.0Gi}" \
    --image "$IMAGE" \
    --secrets "${SECRETS[@]}" \
    --env-vars "${ENVVARS[@]}" \
    --output none
  echo "Created: $JOB_NAME (not yet live-validated)"
done
