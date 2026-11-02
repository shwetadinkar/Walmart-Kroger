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
                 '--sweep-work-dir', os.getenv('MARIANOS_SWEEP_WORK_DIR', '/tmp/sweep-work')]
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


if __name__ == '__main__':
    os.execv(sys.executable, command())
