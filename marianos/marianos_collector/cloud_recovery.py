"""Isolated, explicitly approved API recovery experiment; never normal publication.

Logical checkpoint identity and platform execution identity are separate. This
does not change the production entrypoint or prove website/category coverage.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
import re
from .api_collection import BudgetOpener, collect
from .kroger import Credentials, KrogerClient
from .storage import AzureBlobStorage

SID = '53100508'


def now():
    return datetime.now(timezone.utc).isoformat()


def encode(value):
    return json.dumps(value, sort_keys=True, indent=2).encode()


def run_attempt(storage, client, budget, trial_id, platform_execution, stage, crash):
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,40}', trial_id):
        raise ValueError('INVALID_RECOVERY_TRIAL_ID')
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,200}', platform_execution):
        raise ValueError('INVALID_PLATFORM_EXECUTION')
    if stage not in ('interrupt', 'resume', 'fresh') or budget.maximum > 6:
        raise ValueError('INVALID_RECOVERY_STAGE_OR_BUDGET')
    prefix = f'recovery-review/{SID}/{trial_id}/'
    budget_key = prefix + 'budget.json'
    ready_key = prefix + 'durable-checkpoint.json'
    attempt_key = prefix + 'attempts/' + platform_execution + '.json'
    logical_id = trial_id + ('-fresh' if stage == 'fresh' else '-resume')
    page_key = f'checkpoints/{SID}/{logical_id}/page_00.json'
    with storage.locked(SID):
        if storage.read(attempt_key):
            raise ValueError('RECOVERY_PLATFORM_ATTEMPT_ALREADY_RECORDED')
        ready = storage.read(ready_key)
        if stage == 'interrupt' and ready:
            raise ValueError('INTERRUPTION_ALREADY_PREPARED')
        if stage == 'resume' and not ready:
            raise ValueError('NO_DURABLE_RECOVERY_CHECKPOINT')
        if stage == 'fresh' and not storage.read(prefix + 'resume-completed.json'):
            raise ValueError('RESUME_MUST_COMPLETE_FIRST')
        shared = json.loads(storage.read(budget_key) or b'{"attempts":0}')
        if type(shared.get('attempts')) is not int or not 0 <= shared['attempts'] <= 8:
            raise ValueError('INVALID_SHARED_RECOVERY_BUDGET')
        record = {'stage': stage, 'logical_run_id': logical_id,
                  'platform_execution': platform_execution, 'started_at': now(),
                  'network_attempts_this_process': 0, 'state': 'started'}
        storage.write(attempt_key, encode(record))

        def counted(used):
            if shared['attempts'] >= 8:
                raise ValueError('RECOVERY_EIGHT_ATTEMPT_LIMIT')
            shared['attempts'] += 1
            storage.write(budget_key, encode(shared))
            record['network_attempts_this_process'] = used
            storage.write(attempt_key, encode(record))

        class ScopedStorage:
            def read(self, key):
                return storage.read(prefix + key)
            def write(self, key, data):
                storage.write(prefix + key, data)
                if stage == 'interrupt' and key.endswith('/progress.json'):
                    body = storage.read(prefix + page_key)
                    marker = {'sha256': hashlib.sha256(body).hexdigest(),
                              'logical_run_id': logical_id, 'persisted_at': now()}
                    storage.write(ready_key, encode(marker))
                    record.update(state='checkpoint_saved_before_forced_exit', checkpoint_sha256=marker['sha256'])
                    storage.write(attempt_key, encode(record))
                    crash()
                    raise RuntimeError('FORCED_EXIT_DID_NOT_TERMINATE')

        budget.on_attempt = counted
        try:
            status = collect(client, ScopedStorage(), SID, '60661', logical_id,
                             terms=('milk',), maximum_queries=1, target=5)
            if stage == 'resume':
                body = storage.read(prefix + page_key)
                unchanged = hashlib.sha256(body).hexdigest() == json.loads(ready)['sha256']
                if not unchanged or status['new_queries_this_run'] != 0 or status['cached_queries_this_run'] != 1:
                    raise ValueError('RECOVERY_CHECKPOINT_NOT_REUSED')
                record['checkpoint_unchanged'] = True
            if stage == 'fresh' and (status['new_queries_this_run'] != 1 or status['cached_queries_this_run'] != 0):
                raise ValueError('FRESH_EXECUTION_REUSED_CACHE')
            record.update(state='completed', ended_at=now(), new_queries=status['new_queries_this_run'],
                          selected_records=status['unique_records'], aggregate_http_attempts=shared['attempts'],
                          submission_ready=False, complete_category=False)
            storage.write(attempt_key, encode(record))
            if stage == 'resume':
                storage.write(prefix + 'resume-completed.json', encode(record))
            return record
        finally:
            budget.on_attempt = None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--trial-id', required=True)
    parser.add_argument('--stage', required=True, choices=('interrupt', 'resume', 'fresh'))
    parser.add_argument('--container', default='marianos-api-trials')
    parser.add_argument('--approved-live-test', action='store_true')
    args = parser.parse_args()
    execution = os.getenv('CONTAINER_APP_JOB_EXECUTION_NAME', '')
    if not args.approved_live_test or not execution:
        parser.error('Explicit live approval and actual Azure execution metadata required')
    storage = AzureBlobStorage.from_environment(args.container)
    budget = BudgetOpener(6)
    client = KrogerClient(Credentials.from_environment(), opener=budget)
    result = run_attempt(storage, client, budget, args.trial_id, execution, args.stage,
                         lambda: os._exit(77))
    print(json.dumps(result), flush=True)


if __name__ == '__main__':
    main()
