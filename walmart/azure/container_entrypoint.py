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


def budget_seconds() -> int:
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


def command():
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
    argv += ['--max-seconds', str(budget_seconds())]
    return argv


if __name__ == '__main__':
    os.execv(sys.executable, command())
