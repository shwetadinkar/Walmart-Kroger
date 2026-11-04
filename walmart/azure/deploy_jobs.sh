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

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Resolved ONCE and used for BOTH the deployment and the collector's own budget,
# so the two cannot drift apart. There was no budget at all before: the only
# bound was this timeout, and AZURE_DEPLOYMENT.md says plainly that the jobs are
# not guaranteed to finish in four hours. A replica timeout is a SIGKILL, not an
# exception, so an overrunning run left no release and no refusal record.
REPLICA_TIMEOUT="${REPLICA_TIMEOUT:-21600}"
if (( REPLICA_TIMEOUT <= 1200 )); then
  echo "ERROR: REPLICA_TIMEOUT=$REPLICA_TIMEOUT leaves the collector no room to" >&2
  echo "       stop itself and publish. It must exceed the 1200s headroom." >&2
  exit 1
fi

# The retry plan, resolved once and VALIDATED against the timeout about to be
# deployed. A refused run is retried inside the replica, because Azure's own
# --replica-retry-limit cannot express an interval, so the whole plan has to fit
# inside one replica timeout: a replica timeout is a SIGKILL and would cut the
# plan off mid-way, leaving neither a release nor a refusal record.
#
# Checked by the same code the container runs, read from azure/retry_supervisor.py
# rather than retyped, so a deployment cannot promise a plan the supervisor will
# not deliver.
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
from walmart_collector.cron import shortest_gap_seconds

timeout = int(timeout)
headroom = 1200                     # container_entrypoint.BUDGET_HEADROOM_SECONDS
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
        f"meets the Blob lease, which AZURE_DEPLOYMENT.md relies on to prevent "
        f"two overlapping executions of the same store. A retry plan that "
        f"overruns turns one transient failure into a refused next run.")
if problems:
    print('ERROR: ' + '\n\nERROR: '.join(problems), file=sys.stderr)
    sys.exit(1)

print(f"Retry plan: {plan.attempts} retries at {plan.interval_seconds}s "
      f"({plan.total_runs} runs max), first attempt gets {budget}s, "
      f"inside a {timeout}s replica; next firing is {gap}s away.",
      file=sys.stderr)
print(json.dumps(info))
PY
)" || exit 1

# How a final failure gets out of the container. Validated before any
# deployment, so a --dry-run review shows which route is configured.
#
# Email is optional on purpose. The credential-free route is an Azure Monitor
# log alert matching the marker the supervisor always prints, which needs
# nothing in the image and no secret anywhere. When the operator wants email
# instead, the SMTP credentials are theirs and come from Azure secrets they set.
if [[ -n "${ALERT_EMAIL_TO:-}" ]]; then
  : "${SMTP_HOST:?Set SMTP_HOST when ALERT_EMAIL_TO is set, or a failure can only be logged}"
  if [[ -n "${SMTP_USERNAME:-}" ]]; then
    : "${SMTP_PASSWORD:?Set SMTP_PASSWORD when SMTP_USERNAME is set}"
  fi
  echo "Failure notice: email to $ALERT_EMAIL_TO via $SMTP_HOST:${SMTP_PORT:-587}," \
       "plus the WALMART_RUN_FAILED_AFTER_RETRIES marker in the job log."
else
  echo "Failure notice: no ALERT_EMAIL_TO set, so a final failure prints the" \
       "WALMART_RUN_FAILED_AFTER_RETRIES marker for an Azure Monitor log alert" \
       "to match. See AZURE_DEPLOYMENT.md. Set ALERT_EMAIL_TO and SMTP_HOST for email."
fi

# NOTICE: Azure CLI receives secrets via process arguments. Use a Key Vault secret
# reference and managed identity instead for production (see AZURE_DEPLOYMENT.md).
#
# Two jobs on one expression is deliberate, one per store: AZURE_DEPLOYMENT.md
# states that, and a Blob lease prevents two overlapping executions of the same
# store. The gate above keeps each job's retry plan inside one firing interval,
# so the lease is never asked to arbitrate between a retrying run and its own
# next firing.
for store in ${WALMART_STORE_IDS:-100 5959}; do
  name="walmart-collect-${store}"
  DESCRIPTION="$WALMART_SOURCE"
  [[ "$WALMART_SOURCE" == 'composite' ]] && DESCRIPTION="composite (spine: $WALMART_SPINE)"
  echo "Job: $name | store: $store | source: $DESCRIPTION | schedule (UTC): $CRON"

  SECRETS=("blob-conn=$AZURE_STORAGE_CONNECTION_STRING")
  ENVVARS=("WALMART_STORE_ID=$store"
           'WALMART_DATA_AUTHORIZED=yes'
           "WALMART_SOURCE=$WALMART_SOURCE"
           'AZURE_STORAGE_CONNECTION_STRING=secretref:blob-conn'
           "REPLICA_TIMEOUT=$REPLICA_TIMEOUT"
           "RETRY_ATTEMPTS=$RETRY_ATTEMPTS"
           "RETRY_INTERVAL_SECONDS=$RETRY_INTERVAL_SECONDS"
           "AZURE_BLOB_CONTAINER=${AZURE_BLOB_CONTAINER:-retail-collection}")
  [[ "$WALMART_SOURCE" == 'composite' ]] && ENVVARS+=("WALMART_SPINE=$WALMART_SPINE")

  if [[ -n "${ALERT_EMAIL_TO:-}" ]]; then
    ENVVARS+=("ALERT_EMAIL_TO=$ALERT_EMAIL_TO"
              "SMTP_HOST=$SMTP_HOST"
              "SMTP_PORT=${SMTP_PORT:-587}"
              "ALERT_EMAIL_FROM=${ALERT_EMAIL_FROM:-}")
    if [[ -n "${SMTP_USERNAME:-}" ]]; then
      SECRETS+=("smtp-password=$SMTP_PASSWORD")
      ENVVARS+=("SMTP_USERNAME=$SMTP_USERNAME"
                'SMTP_PASSWORD=secretref:smtp-password')
    fi
  fi

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
    --cron-expression "$CRON" \
    --replica-timeout "$REPLICA_TIMEOUT" \
    --replica-retry-limit 0 \
    --parallelism 1 \
    --replica-completion-count 1 \
    --image "$IMAGE" \
    --cpu 1 --memory 2Gi \
    --secrets "${SECRETS[@]}" \
    --env-vars "${ENVVARS[@]}"
done
