"""Container entrypoint: no dynamic CLI flag parsing required in Azure job setup.

Mirrors marianos/azure/container_entrypoint.py. The source is chosen by
WALMART_SOURCE so that one immutable image serves every authorized route,
rather than the route being baked into the image's CMD.

Only authorized routes are selectable. The fixture source is deliberately not
reachable from a scheduled job, because a synthetic run that published into the
real Blob namespace would be indistinguishable from a real one after the fact.
"""
import os
import sys

AUTHORIZED_SOURCES = ('provider', 'opd', 'composite')
AUTHORIZED_SPINES = ('provider', 'opd')


# Headroom between the collector stopping itself and Azure killing the replica.
# The collector has to finish the category in hand, reconcile and publish inside
# this window.
BUDGET_HEADROOM_SECONDS = 1200
DEFAULT_REPLICA_TIMEOUT = 14400


def default_budget_seconds() -> int:
    """How long the run may take, strictly less than the replica timeout.

    **There was no budget at all.** The only bound was Azure's
    `--replica-timeout 14400`, and `azure/AZURE_DEPLOYMENT.md` says plainly
    that "the jobs are not guaranteed to finish in four hours". A replica
    timeout is a SIGKILL rather than an exception, so a run that overran left
    no release and no refusal record: the exact failure the refusal machinery
    exists for, on the runs nobody is watching. The same defect existed on the
    Mariano's side with the budget set equal to the timeout; here it was
    absent.
    """
    explicit = os.getenv('WALMART_MAX_SECONDS', '').strip()
    if explicit:
        try:
            value = int(float(explicit))
        except ValueError:
            raise ValueError(
                f'WALMART_MAX_SECONDS must be a number, not {explicit!r}')
        if value <= 0:
            raise ValueError('WALMART_MAX_SECONDS must be positive')
        return value
    timeout = os.getenv('REPLICA_TIMEOUT', '').strip()
    try:
        limit = int(float(timeout)) if timeout else DEFAULT_REPLICA_TIMEOUT
    except ValueError:
        limit = DEFAULT_REPLICA_TIMEOUT
    budget = limit - BUDGET_HEADROOM_SECONDS
    if budget <= 0:
        raise ValueError(
            f'replica timeout {limit}s leaves no room for the collector to stop '
            f'itself and publish; it must exceed {BUDGET_HEADROOM_SECONDS}s')
    return budget


def command(budget_seconds: int = None):
    """The argv for one attempt.

    `budget_seconds` is passed per attempt rather than computed once, because
    the retry supervisor gives each attempt the time actually left in the
    replica window. Called with no budget it falls back to deriving one from
    the replica timeout, which is what a single unsupervised run did before the
    supervisor existed.
    """
    store = os.getenv('WALMART_STORE_ID', '')
    if not store:
        return [sys.executable, '-m', 'walmart_collector', 'list']

    source = os.getenv('WALMART_SOURCE', 'provider').strip()
    if source not in AUTHORIZED_SOURCES:
        raise ValueError(
            f'WALMART_SOURCE must be one of {AUTHORIZED_SOURCES}, not {source!r}. '
            'Synthetic fixtures are not runnable from a scheduled job.'
        )

    argv = [sys.executable, '-m', 'walmart_collector', 'run', '--source', source,
            '--authorized-source', '--backend', 'azure', '--store', store]

    if source == 'composite':
        spine = os.getenv('WALMART_SPINE', 'opd').strip()
        if spine not in AUTHORIZED_SPINES:
            raise ValueError(
                f'WALMART_SPINE must be one of {AUTHORIZED_SPINES}, not {spine!r}'
            )
        argv += ['--spine', spine]

    # OPD output is provisional: the CLI forces it into the trials namespace
    # rather than publishing it as a complete production dataset. Nothing here
    # overrides that, and nothing here should.

    # Only on a run. `list` is not a run and takes no budget.
    argv += ['--max-seconds',
             str(budget_seconds if budget_seconds else default_budget_seconds())]
    return argv


def replica_timeout_seconds() -> int:
    """The replica timeout the job was deployed with.

    `deploy_jobs.sh` resolves this once, deploys it and forwards the same value
    in, so the figure the supervisor plans against is the figure Azure will
    enforce.
    """
    raw = os.getenv('REPLICA_TIMEOUT', '').strip()
    try:
        return int(float(raw)) if raw else DEFAULT_REPLICA_TIMEOUT
    except ValueError:
        return DEFAULT_REPLICA_TIMEOUT


if __name__ == '__main__':
    # `os.execv` used to run here. It replaces this process, so nothing was
    # left to observe the collector's exit code, and a refused unattended run
    # could not be retried: the instruction was eight retries at fifteen
    # minutes, then an email, with the next scheduled run unaffected.
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import retry_supervisor

    argv = command()
    is_run = 'run' in argv
    raise SystemExit(retry_supervisor.main(
        build_argv=command,
        replica_timeout=replica_timeout_seconds(),
        collector_headroom_seconds=BUDGET_HEADROOM_SECONDS,
        argv_for_non_run=None if is_run else argv,
    ))
