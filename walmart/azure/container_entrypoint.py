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
    return argv


if __name__ == '__main__':
    os.execv(sys.executable, command())
