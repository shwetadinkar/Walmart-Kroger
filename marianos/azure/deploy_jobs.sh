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

# The replica timeout, resolved ONCE and used for BOTH the deployment and the
# collector's own budget, so the two cannot drift apart.
#
# They were previously equal by coincidence: this script deployed
# --replica-timeout 7200 and the entrypoint passed no budget, so the CLI default
# of 7200 applied. The collector's graceful stop and Azure's SIGKILL therefore
# landed on the same instant, and SIGKILL is not an exception, so an overrunning
# unattended run would leave no release AND no refusal record. The entrypoint
# derives its budget from REPLICA_TIMEOUT, which is forwarded below.
REPLICA_TIMEOUT="${REPLICA_TIMEOUT:-14400}"
if (( REPLICA_TIMEOUT <= 900 )); then
  echo "ERROR: REPLICA_TIMEOUT=$REPLICA_TIMEOUT leaves the collector no room to" >&2
  echo "       stop itself and publish. It must exceed the 900s headroom." >&2
  exit 1
fi

# The retry plan, resolved once and VALIDATED against the timeout about to be
# deployed. A refused run is retried inside the replica, because Azure's own
# --replica-retry-limit cannot express an interval, so the whole plan has to fit
# inside one replica timeout: a replica timeout is a SIGKILL and would cut the
# plan off mid-way, leaving neither a release nor a refusal record.
#
# Both figures below are checked by the same code the container runs, read from
# azure/retry_supervisor.py rather than retyped, so a deployment cannot promise
# a plan the supervisor will not deliver.
RETRY_ATTEMPTS="${RETRY_ATTEMPTS:-8}"
RETRY_INTERVAL_SECONDS="${RETRY_INTERVAL_SECONDS:-900}"
CRON="${CRON_EXPRESSION:-0 6 * * 1,4}"

RETRY_PLAN="$(python - "$ROOT" "$REPLICA_TIMEOUT" "$RETRY_ATTEMPTS" \
                       "$RETRY_INTERVAL_SECONDS" "$CRON" <<'PY'
import json, sys
root, timeout, attempts, interval, cron = sys.argv[1:6]
sys.path.insert(0, root)
sys.path.insert(0, root + '/azure')
import retry_supervisor as rs
from marianos_collector.cron import shortest_gap_seconds

timeout = int(timeout)
headroom = 900                      # container_entrypoint.BUDGET_HEADROOM_SECONDS
try:
    plan = rs.RetryPlan(attempts=int(attempts), interval_seconds=int(interval),
                        collector_headroom_seconds=headroom)
except ValueError as exc:
    sys.exit(f'Invalid retry plan: {exc}')
try:
    gap = shortest_gap_seconds(cron)
except ValueError as exc:
    sys.exit(f'Cannot compute the gap between firings of {cron!r}: {exc}')

budget = timeout - headroom
info = rs.describe(plan, timeout, budget, gap)

problems = []
if not info['all_attempts_reachable']:
    problems.append(
        f"REPLICA_TIMEOUT={timeout}s cannot reach all {plan.total_runs} attempts.\n"
        f"       {plan.attempts} retries at {plan.interval_seconds}s is "
        f"{plan.waiting_seconds()}s of waiting alone, so the plan needs at least "
        f"{info['minimum_timeout_for_all_attempts']}s even if every attempt fails "
        f"immediately.\n"
        f"       Set REPLICA_TIMEOUT to at least "
        f"{info['minimum_timeout_for_all_attempts']} for all of them to be "
        f"reachable, or {info['timeout_for_full_length_attempts']} for every "
        f"attempt to get a full-length run.\n"
        f"       Lowering RETRY_ATTEMPTS or RETRY_INTERVAL_SECONDS is the other "
        f"way to make it fit. It is refused rather than quietly shortened, "
        f"because a plan that silently stops at attempt 3 is not the plan that "
        f"was configured.")
if not info['finishes_before_the_next_firing']:
    problems.append(
        f"REPLICA_TIMEOUT={timeout}s is not shorter than the {gap}s gap between "
        f"firings of {cron!r}.\n"
        f"       An execution could still be running when the scheduler fires "
        f"again. Azure's cron fires independently of how long an execution "
        f"takes, so the next run is not delayed - it starts beside this one and "
        f"meets the Blob lease, which refuses it. A retry plan that overruns "
        f"turns one transient failure into a refused next run.")
if problems:
    print('ERROR: ' + '\n\nERROR: '.join(problems), file=sys.stderr)
    sys.exit(1)

# The human summary is printed here, by the code that holds the figures, rather
# than re-parsed in shell. One place, and no second chance to misreport it.
print(f"Retry plan: {plan.attempts} retries at {plan.interval_seconds}s "
      f"({plan.total_runs} runs max), first attempt gets {budget}s, "
      f"inside a {timeout}s replica; next firing is {gap}s away.",
      file=sys.stderr)
print(json.dumps(info))
PY
)" || exit 1

# How a final failure gets out of the container. Validated here, before any
# deployment, so a --dry-run review shows which route is configured.
#
# Email is optional on purpose. The credential-free route is an Azure Monitor
# log alert matching the marker the supervisor always prints, which needs
# nothing in the image and no secret anywhere. When the operator wants email
# instead, the SMTP credentials are theirs and come from Azure secrets they
# set: no SMTP password lives in this repository, and none is ever pasted into
# a session.
if [[ -n "${ALERT_EMAIL_TO:-}" ]]; then
  : "${SMTP_HOST:?Set SMTP_HOST when ALERT_EMAIL_TO is set, or a failure can only be logged}"
  if [[ -n "${SMTP_USERNAME:-}" ]]; then
    : "${SMTP_PASSWORD:?Set SMTP_PASSWORD when SMTP_USERNAME is set}"
  fi
  echo "Failure notice: email to $ALERT_EMAIL_TO via $SMTP_HOST:${SMTP_PORT:-587}," \
       "plus the MARIANOS_RUN_FAILED_AFTER_RETRIES marker in the job log."
else
  echo "Failure notice: no ALERT_EMAIL_TO set, so a final failure prints the" \
       "MARIANOS_RUN_FAILED_AFTER_RETRIES marker for an Azure Monitor log alert" \
       "to match. See azure/README.md. Set ALERT_EMAIL_TO and SMTP_HOST for email."
fi

for STORE_ID in "${STORE_IDS[@]}"; do
  CLEAN_ID="$(printf %s "$STORE_ID" | tr '[:upper:]_' '[:lower:]-' | cut -c1-20)"
  JOB_NAME="marianos-$CLEAN_ID"
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
  SECRETS=("marianos-blob=$AZURE_STORAGE_CONNECTION_STRING")
  ENVVARS=('AZURE_STORAGE_CONNECTION_STRING=secretref:marianos-blob'
           'MARIANOS_DATA_AUTHORIZED=yes'
           "MARIANOS_SOURCE=$MARIANOS_SOURCE"
           "AZURE_BLOB_CONTAINER=${AZURE_BLOB_CONTAINER:-marianos-collection}"
           "REPLICA_TIMEOUT=$REPLICA_TIMEOUT"
           "RETRY_ATTEMPTS=$RETRY_ATTEMPTS"
           "RETRY_INTERVAL_SECONDS=$RETRY_INTERVAL_SECONDS"
           "MARIANOS_STORE_ID=$STORE_ID")

  if [[ -n "${ALERT_EMAIL_TO:-}" ]]; then
    ENVVARS+=("ALERT_EMAIL_TO=$ALERT_EMAIL_TO"
              "SMTP_HOST=$SMTP_HOST"
              "SMTP_PORT=${SMTP_PORT:-587}"
              "ALERT_EMAIL_FROM=${ALERT_EMAIL_FROM:-}")
    if [[ -n "${SMTP_USERNAME:-}" ]]; then
      SECRETS+=("marianos-smtp-password=$SMTP_PASSWORD")
      ENVVARS+=("SMTP_USERNAME=$SMTP_USERNAME"
                'SMTP_PASSWORD=secretref:marianos-smtp-password')
    fi
  fi
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
