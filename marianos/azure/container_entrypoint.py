"""Container entrypoint: no dynamic CLI flag parsing required in Azure job setup."""
import os
import sys
import re
import json
from pathlib import Path
from marianos_collector.run_context import execution_context

def command():
    sid = os.getenv('MARIANOS_STORE_ID', '')
    mode=os.getenv('MARIANOS_MODE','provider')
    if not sid:
        if mode=='discovery':raise ValueError('Discovery requires an explicit verified store')
        return [sys.executable, '-m', 'marianos_collector', 'list']
    if sid.upper().startswith(('DEMO', 'REPLACE', 'UNRESOLVED')):
        raise ValueError('Azure job requires a real, verified Kroger location ID')
    if mode=='discovery':
        from marianos_collector.production_config import validate_discovery_config
        name=os.getenv('MARIANOS_DISCOVERY_CONFIG','discovery.westloop.example.json')
        if '..' in name or not re.fullmatch(r'[A-Za-z0-9_.-]+\.json',name):raise ValueError('Unsafe discovery configuration name')
        directory=(Path(__file__).resolve().parents[1]/'config').resolve()
        config=(directory/name).resolve()
        if config.parent!=directory:raise ValueError('Discovery configuration escaped shipped directory')
        document=validate_discovery_config(json.loads(config.read_text(encoding='utf-8')))
        if document['store']['id']!=sid or document['store']['zipcode']!=os.getenv('MARIANOS_ZIPCODE',''):
            raise ValueError('Discovery configuration and job store/ZIP disagree')
        context=execution_context()
        if context.origin!='azure-execution':raise ValueError('Discovery job requires Azure execution identity')
        return [sys.executable,'-m','marianos_collector.discovery_job','--backend','azure',
                '--config',str(config),'--run-id',context.run_id,
                '--container',os.getenv('AZURE_BLOB_CONTAINER','retail-collection')]
    if mode == 'api-trial':
        zipcode=os.getenv('MARIANOS_ZIPCODE','')
        if not re.fullmatch(r'\d{8}',sid) or not re.fullmatch(r'\d{5}',zipcode):
            raise ValueError('API trial requires an eight-digit store ID and five-digit ZIP')
        target=int(os.getenv('MARIANOS_TARGET','650'))
        minimum=int(os.getenv('MARIANOS_MINIMUM','500'))
        queries=int(os.getenv('MARIANOS_MAX_QUERIES','40'))
        requests=int(os.getenv('MARIANOS_MAX_REQUESTS','60'))
        if not (1 <= minimum <= target <= 650 and 1 <= queries <= 40 and 1 <= requests <= 60):
            raise ValueError('Azure trial bounds exceed the approved ceiling')
        context=execution_context()
        return [sys.executable,'-m','marianos_collector.api_collection','--backend','azure',
                '--location-id',sid,'--zipcode',zipcode,'--run-id',context.run_id,
                '--execution-id',context.execution_name,'--run-origin',context.origin,
                '--container',os.getenv('AZURE_BLOB_CONTAINER','marianos-api-trials'),
                '--output-prefix',os.getenv('MARIANOS_OUTPUT_PREFIX','trials'),
                '--target',str(target),'--minimum',str(minimum),'--maximum-queries',str(queries),
                '--maximum-requests',str(requests)]
    return [sys.executable, '-m', 'marianos_collector', 'run', '--source', 'provider',
            '--authorized-source', '--backend', 'azure', '--store', sid,
            '--stores', '/app/config/stores_live.json', '--minimum-products', '500']

if __name__ == '__main__':
    os.execv(sys.executable, command())
