"""Container entrypoint: no dynamic CLI flag parsing required in Azure job setup."""
import os
import sys
import re
from datetime import datetime, timezone

def command():
    sid = os.getenv('MARIANOS_STORE_ID', '')
    if not sid:
        return [sys.executable, '-m', 'marianos_collector', 'list']
    if sid.upper().startswith(('DEMO', 'REPLACE', 'UNRESOLVED')):
        raise ValueError('Azure job requires a real, verified Kroger location ID')
    if os.getenv('MARIANOS_MODE','provider') == 'api-trial':
        zipcode=os.getenv('MARIANOS_ZIPCODE','')
        if not re.fullmatch(r'\d{8}',sid) or not re.fullmatch(r'\d{5}',zipcode):
            raise ValueError('API trial requires an eight-digit store ID and five-digit ZIP')
        run_id=os.getenv('MARIANOS_RUN_ID') or datetime.now(timezone.utc).strftime('%Y%m%d')
        return [sys.executable,'-m','marianos_collector.api_collection','--backend','azure',
                '--location-id',sid,'--zipcode',zipcode,'--run-id',run_id,
                '--container',os.getenv('AZURE_BLOB_CONTAINER','marianos-api-trials'),
                '--target','650','--minimum','500','--maximum-queries','40','--maximum-requests','60']
    return [sys.executable, '-m', 'marianos_collector', 'run', '--source', 'provider',
            '--authorized-source', '--backend', 'azure', '--store', sid,
            '--stores', '/app/config/stores_live.json', '--minimum-products', '500']

if __name__ == '__main__':
    os.execv(sys.executable, command())
