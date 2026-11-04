"""Container entrypoint: no dynamic CLI flag parsing required in Azure job setup.

The source is chosen by MARIANOS_SOURCE so that one immutable image serves both
authorized routes. Only the two authorized sources are selectable here; the
fixture source is deliberately not reachable from a scheduled job, because a
synthetic run that published to the real Blob namespace would be
indistinguishable from a real one after the fact.
"""
import os
import sys

AUTHORIZED_SOURCES = ('provider', 'catalog_v2', 'sweep')


# Headroom between the collector stopping itself and Azure killing the replica.
# The collector has to finish the term it is on, reconcile retention, publish the
# release and write its report inside this window.
BUDGET_HEADROOM_SECONDS = 900
DEFAULT_REPLICA_TIMEOUT = 7200


def sweep_budget_seconds() -> int:
    """How long the sweep may run, strictly less than the replica timeout.

    **The collector was given exactly as long as Azure allows.** This entrypoint
    passed no budget, so the CLI default of 7200 seconds applied, and
    `deploy_jobs.sh` sets `--replica-timeout 7200`. The collector's own graceful
    budget stop and Azure's kill therefore landed on the same instant, and the
    kill is SIGKILL: not an exception, so `refusal_recorded` never runs. An
    overrunning unattended run would leave **no release and no refusal record**,
    which is precisely the trace that machinery exists to leave, defeated by a
    configuration coincidence rather than by any code.

    The budget is now derived from the replica timeout the job is deployed with,
    minus headroom, and the deploy script exports the same value it deploys so
    the two cannot drift apart.
    """
    explicit = os.getenv('MARIANOS_SWEEP_MAX_SECONDS', '').strip()
    if explicit:
        try:
            value = int(float(explicit))
        except ValueError:
            raise ValueError(
                f'MARIANOS_SWEEP_MAX_SECONDS must be a number, not {explicit!r}')
        if value <= 0:
            raise ValueError('MARIANOS_SWEEP_MAX_SECONDS must be positive')
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
    supervisor existed and is what the tests of the argv itself use.
    """
    sid = os.getenv('MARIANOS_STORE_ID', '')
    if not sid:
        return [sys.executable, '-m', 'marianos_collector', 'list']
    if sid.upper().startswith(('DEMO', 'REPLACE', 'UNRESOLVED')):
        raise ValueError('Azure job requires a real, verified Kroger location ID')

    source = os.getenv('MARIANOS_SOURCE', 'provider').strip()
    if source not in AUTHORIZED_SOURCES:
        raise ValueError(
            f'MARIANOS_SOURCE must be one of {AUTHORIZED_SOURCES}, not {source!r}. '
            'Synthetic fixtures are not runnable from a scheduled job.'
        )

    argv = [sys.executable, '-m', 'marianos_collector', 'run', '--source', source,
            '--authorized-source', '--backend', 'azure', '--store', sid,
            '--stores', '/app/config/stores_live.json', '--minimum-products', '500']

    if source == 'sweep':
        # The public Products API term sweep. Three things differ from the
        # other two routes and all three are deliberate.
        #
        # No --authorized-source: this is the public tier, which is also why
        # the acceptable-use question in ACCEPTABLE_USE_POSITION.md applies to
        # it and is the client's to settle. The flag is dropped rather than
        # passed to avoid a scheduled job asserting an authorization it has
        # not got.
        #
        # --resolve-store, with the ZIP and street asserted: the store columns
        # come from Kroger's own /locations response, never from
        # stores_live.json. The first sweep run shipped 18,351 records with a
        # blank store_name and store_location, and the assigned store id
        # differs from West Loop's by two characters.
        #
        # --uncovered-roots: five of the 28 roots have no Kroger label that
        # maps to them, so without the declaration the zero-products gate
        # fails every scheduled run for a permanent vocabulary reason. The
        # declaration drops only those roots, names them in the release, and
        # fails the run if one of them starts returning products.
        argv = [x for x in argv if x != '--authorized-source']
        location_id = os.getenv('KROGER_LOCATION_ID', '').strip()
        zipcode = os.getenv('MARIANOS_EXPECT_ZIPCODE', '').strip()
        street = os.getenv('MARIANOS_EXPECT_STREET', '').strip()
        if not location_id or location_id.upper().startswith(('DEMO', 'REPLACE', 'UNRESOLVED')):
            raise ValueError('sweep requires KROGER_LOCATION_ID from the Locations API')
        if not zipcode or not street:
            raise ValueError(
                'sweep requires MARIANOS_EXPECT_ZIPCODE and MARIANOS_EXPECT_STREET: the '
                'resolved store is asserted against the address, not assumed from the id')
        argv += ['--location-id', location_id, '--resolve-store',
                 '--expect-zipcode', zipcode, '--expect-street', street,
                 '--sweep-terms', '/app/config/sweep_terms.json',
                 '--uncovered-roots', '/app/config/sweep_coverage.json',
                 '--sweep-work-dir', os.getenv('MARIANOS_SWEEP_WORK_DIR', '/tmp/sweep-work'),
                 '--sweep-max-seconds',
                 str(budget_seconds if budget_seconds else sweep_budget_seconds())]
        return argv

    if source == 'catalog_v2':
        # Kroger's locationId is not necessarily the collector's store_id, so it
        # is passed explicitly rather than assumed equal.
        location_id = os.getenv('KROGER_LOCATION_ID', '').strip()
        if not location_id:
            raise ValueError('catalog_v2 requires KROGER_LOCATION_ID from the Locations API')
        if location_id.upper().startswith(('DEMO', 'REPLACE', 'UNRESOLVED')):
            raise ValueError('KROGER_LOCATION_ID must be a verified Kroger location, not a placeholder')
        argv += ['--location-id', location_id]

    return argv


def replica_timeout_seconds() -> int:
    """The replica timeout the job was deployed with.

    `deploy_jobs.sh` resolves this once, deploys it and forwards the same value
    in, so the figure the supervisor plans against is the figure Azure will
    enforce. They were previously equal only by coincidence.
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
