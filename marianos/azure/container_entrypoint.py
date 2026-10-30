"""Container entrypoint: no dynamic CLI flag parsing required in Azure job setup.

The source is chosen by MARIANOS_SOURCE so that one immutable image serves both
authorized routes. Only the two authorized sources are selectable here; the
fixture source is deliberately not reachable from a scheduled job, because a
synthetic run that published to the real Blob namespace would be
indistinguishable from a real one after the fact.
"""
import os
import sys

AUTHORIZED_SOURCES = ('provider', 'catalog_v2')


def command():
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


if __name__ == '__main__':
    os.execv(sys.executable, command())
