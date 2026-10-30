"""Mariano's Azure collector CLI. Live Kroger API is diagnostic; fully indexed provider required for publish."""
from __future__ import annotations
import argparse
import hashlib
import json
import logging
import os
import sys
from pathlib import Path

from .catalog_v2 import CatalogV2Client,CatalogV2Source
from .catalog_v2 import Credentials as CatalogV2Credentials
from .config import categories_from_csv,stores_from_json
from .kroger import Credentials,KrogerClient,KrogerError,location_candidates,trial
from .runner import Collector
from .sources import FixtureSource,AuthorizedProviderSource
from .storage import LocalStorage,AzureBlobStorage,read_json

ROOT=Path(__file__).resolve().parent.parent

class Formatter(logging.Formatter):
    def format(self,r):
        return json.dumps({'level':r.levelname,'event':getattr(r,'event',r.getMessage()),
                           'store':getattr(r,'store_id',''),'category':getattr(r,'category',''),
                           'message':r.getMessage()})

def parser_():
    p=argparse.ArgumentParser(description='Mariano\'s validated collection and Kroger API diagnostics')
    p.add_argument('command',choices=['list','run','status','export','clear-checkpoints','kroger-locations','kroger-trial'])
    p.add_argument('--stores',type=Path,default=ROOT/'config/stores.json')
    p.add_argument('--categories',type=Path,default=ROOT/'config/categories.csv')
    p.add_argument('--store',default='DEMO-LAKESHORE-60601')
    p.add_argument('--source',choices=['fixture','provider','catalog_v2'],default='fixture')
    p.add_argument('--fixtures',type=Path,default=ROOT/'fixtures')
    p.add_argument('--backend',choices=['local','azure'],default='local')
    p.add_argument('--output',type=Path,default=ROOT/'.collector-output')
    p.add_argument('--container',default=os.environ.get('AZURE_BLOB_CONTAINER','marianos-collection'))
    p.add_argument('--minimum-products',type=int,default=None)
    p.add_argument('--authorized-source',action='store_true')
    p.add_argument('--only-categories',default='')
    p.add_argument('--export-file',type=Path)
    p.add_argument('--confirm-reset',action='store_true')
    p.add_argument('--zipcode',default='60601')
    p.add_argument('--address-contains',default='')
    p.add_argument('--location-id',default='')
    p.add_argument('--terms',default='milk,bread')
    return p

def main(argv=None):
    p=parser_(); a=p.parse_args(argv)
    h=logging.StreamHandler(sys.stderr); h.setFormatter(Formatter()); log=logging.getLogger('collector')
    if not log.handlers: log.addHandler(h)
    log.setLevel(logging.INFO)
    try:
        if a.command in ('kroger-locations','kroger-trial'):
            if a.command=='kroger-locations':
                creds=Credentials.from_environment(); cli=KrogerClient(creds)
                response=location_candidates(cli,a.zipcode,a.address_contains)
                print(json.dumps({'zipcode':a.zipcode,'locations':response,
                    'instruction':'Verify the exact address and locationId before using an authorized catalog provider.'},indent=2));return 0
            if not a.location_id or a.location_id.upper().startswith(('DEMO','REPLACE')):
                p.error('kroger-trial requires --location-id from a verified Kroger Locations response')
            cli=KrogerClient(Credentials.from_environment())
            terms=[x.strip() for x in a.terms.split(',') if x.strip()]
            result=trial(cli,a.location_id,terms)
            print(json.dumps(result,indent=2));return 0
        categories=categories_from_csv(a.categories)
        stores=stores_from_json(a.stores)
        if a.command=='list':
            print(json.dumps({'stores':[s.__dict__ for s in stores],
              'categories':[c.__dict__ for c in categories], 'category_count':len(categories)},indent=2));return 0
        subset = bool(a.only_categories)
        if a.only_categories:
            wanted={x.strip() for x in a.only_categories.split(',') if x.strip()}
            if len(wanted)<2 or not wanted.issubset({x.name for x in categories}):
                p.error('Trial category subset must contain at least two exact configured category names')
            categories=[c for c in categories if c.name in wanted]
            print('TRIAL ONLY: this subset cannot demonstrate complete catalog coverage.',file=sys.stderr)
        category_signature=hashlib.sha256(json.dumps([(c.name,c.url) for c in categories]).encode()).hexdigest()[:12]
        namespace=f'trials/{category_signature}' if subset else 'published'
        checkpoint_root=f'checkpoints-trials/{category_signature}' if subset else 'checkpoints'
        store=next((s for s in stores if s.store_id==a.store),None)
        if store is None:p.error('Unknown store_id: '+a.store)
        if a.backend=='azure':
            cs=os.environ.get('AZURE_STORAGE_CONNECTION_STRING','')
            if not cs:p.error('Missing Azure storage connection string')
            storage=AzureBlobStorage(cs,a.container)
        else:storage=LocalStorage(a.output)
        if a.command=='status':
            ptr=read_json(storage,f'{namespace}/{store.store_id}/latest.json')
            print(json.dumps({'store_id':store.store_id,'latest':ptr},indent=2));return 0
        if a.command=='export':
            ptr=read_json(storage,f'{namespace}/{store.store_id}/latest.json')
            if not ptr or not a.export_file:p.error('No successful run or missing --export-file')
            manifest=read_json(storage,ptr['manifest_key'])
            body=storage.read(manifest['data_key'])
            if body is None:raise RuntimeError('Published data missing')
            a.export_file.parent.mkdir(parents=True,exist_ok=True)
            a.export_file.write_bytes(body)
            print(json.dumps({'file':str(a.export_file),'records':manifest['records'],'source_mode':manifest['source_mode']}));return 0
        if a.command=='clear-checkpoints':
            if not a.confirm_reset:p.error('Use --confirm-reset to discard partial progress')
            with storage.locked(store.store_id):
                for cat in categories:storage.delete(f'{checkpoint_root}/{store.store_id}/{cat.slug}.json')
            print('Partial checkpoints reset; published releases untouched');return 0
        if a.minimum_products is not None and a.minimum_products<1:p.error('minimum must be >=1')
        if a.source=='catalog_v2':
            # Partner tier. The public Products API is NOT an alternative here:
            # Kroger's acceptable use policy for public APIs prohibits gathering
            # response data into a database and prohibits cross-retailer price
            # comparison, which is what this collector does.
            if not a.authorized_source or os.environ.get('MARIANOS_DATA_AUTHORIZED')!='yes':
                p.error('Catalog V2 mode requires --authorized-source and MARIANOS_DATA_AUTHORIZED=yes')
            if store.store_id.upper().startswith(('DEMO','REPLACE','UNRESOLVED')):
                p.error('Catalog V2 mode requires a verified real store ID, not a demo placeholder')
            location_id=a.location_id or store.store_id
            client=CatalogV2Client(CatalogV2Credentials.from_environment())
            src=CatalogV2Source(client,location_id)
            minp=a.minimum_products or 500
        elif a.source=='provider':
            if not a.authorized_source or os.environ.get('MARIANOS_DATA_AUTHORIZED')!='yes':
                p.error('Provider mode requires --authorized-source and MARIANOS_DATA_AUTHORIZED=yes')
            if store.store_id.upper().startswith(('DEMO','REPLACE','UNRESOLVED')):
                p.error('Provider mode requires a verified real store ID, not a demo placeholder')
            src=AuthorizedProviderSource(os.environ.get('PROVIDER_BASE_URL',''),os.environ.get('PROVIDER_API_TOKEN',''))
            minp=a.minimum_products or 500
        else:
            src=FixtureSource(a.fixtures)
            minp=a.minimum_products or 1
            print('SYNTHETIC DEMO: does not contain real Mariano\'s data.',file=sys.stderr)
        output=Collector(storage,src,categories,min_products=minp,trial=subset).run(store)
        print(json.dumps(output,indent=2));return 0
    except (Exception,KeyboardInterrupt) as exc:
        log.error('run_failed')
        print(f'ERROR: {exc}',file=sys.stderr);return 1

if __name__=='__main__':raise SystemExit(main())
