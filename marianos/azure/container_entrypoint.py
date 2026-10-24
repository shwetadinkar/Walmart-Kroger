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
        target=int(os.getenv('MARIANOS_TARGET','650'))
        minimum=int(os.getenv('MARIANOS_MINIMUM','500'))
        queries=int(os.getenv('MARIANOS_MAX_QUERIES','40'))
        requests=int(os.getenv('MARIANOS_MAX_REQUESTS','60'))
        if not (1 <= minimum <= target <= 650 and 1 <= queries <= 40 and 1 <= requests <= 60):
            raise ValueError('Azure trial bounds exceed the approved ceiling')
        run_id=os.getenv('MARIANOS_RUN_ID') or datetime.now(timezone.utc).strftime('%Y%m%d')
        return [sys.executable,'-m','marianos_collector.api_collection','--backend','azure',
                '--location-id',sid,'--zipcode',zipcode,'--run-id',run_id,
                '--container',os.getenv('AZURE_BLOB_CONTAINER','marianos-api-trials'),
                '--target',str(target),'--minimum',str(minimum),'--maximum-queries',str(queries),
                '--maximum-requests',str(requests)]
    return [sys.executable, '-m', 'marianos_collector', 'run', '--source', 'provider',
            '--authorized-source', '--backend', 'azure', '--store', sid,
            '--stores', '/app/config/stores_live.json', '--minimum-products', '500']

if __name__ == '__main__':
    os.execv(sys.executable, command())
