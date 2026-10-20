"""Container entrypoint: no dynamic CLI flag parsing required in Azure job setup."""
import os
import sys

def command():
    sid = os.getenv('MARIANOS_STORE_ID', '')
    if not sid:
        return [sys.executable, '-m', 'marianos_collector', 'list']
    if sid.upper().startswith(('DEMO', 'REPLACE', 'UNRESOLVED')):
        raise ValueError('Azure job requires a real, verified Kroger location ID')
    return [sys.executable, '-m', 'marianos_collector', 'run', '--source', 'provider',
            '--authorized-source', '--backend', 'azure', '--store', sid,
            '--stores', '/app/config/stores_live.json', '--minimum-products', '500']

if __name__ == '__main__':
    os.execv(sys.executable, command())
