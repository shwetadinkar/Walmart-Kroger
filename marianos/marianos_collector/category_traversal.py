"""Resumable evidence traversal. Never publishes a product dataset or latest pointer.

The driver must visit public rendered pages and return literal observations. Browser
request totals differ from page totals; neither is misreported as API request usage.
Call under the storage backend's per-store lock.
"""
import hashlib
import json
from .category_coverage import CoverageLedger, category_url


def encoded(value):
    return json.dumps(value,sort_keys=True,ensure_ascii=False).encode('utf-8')


class CategoryAccessBlocked(RuntimeError):
    """Stop this run permanently after an access restriction; no automatic retry."""


class CategoryTraversal:
    def __init__(self,storage,driver,roots,store_id,zipcode,run_id,*,max_categories=500,maximum_pages=100):
        if not (1<=max_categories<=1000 and 1<=maximum_pages<=500):
            raise ValueError('Category traversal bounds exceeded')
        self.storage,self.driver=storage,driver
        self.roots=[{'name':r['name'],'url':category_url(r['url'])} for r in roots]
        self.store_id,self.zipcode,self.run_id=store_id,zipcode,run_id
        self.max_categories,self.maximum_pages=max_categories,maximum_pages
        # Storage's key validation rejects unsafe run/store identifiers.
        self.prefix=f'category-runs/{store_id}/{run_id}'
        self.key=self.prefix+'/checkpoint.json'

    def run(self):
        configuration={'roots':self.roots,'store_id':self.store_id,'zipcode':self.zipcode,
                       'source_kind':self.driver.source_kind,'maximum_pages':self.maximum_pages}
        fingerprint=hashlib.sha256(encoded(configuration)).hexdigest()
        raw=self.storage.read(self.key)
        state=json.loads(raw) if raw else {'configuration_sha256':fingerprint,
               'pending':[r['url'] for r in self.roots],'observations':[],'pages_observed':0,'attempts':0}
        if state['configuration_sha256']!=fingerprint:raise ValueError('CATEGORY_CONFIGURATION_CHANGED')
        if state.get('access_blocked'):raise CategoryAccessBlocked('CATEGORY_ACCESS_BLOCKED_STOP')
        ledger=CoverageLedger(self.roots,self.store_id,self.zipcode)
        for e in state['observations']:
            for key,digest in ((e['snapshot_key'],e['snapshot_sha256']),
                               (e['discovery_key'],e['discovery_evidence_sha256'])):
                data=self.storage.read(key)
                if data is None or hashlib.sha256(data).hexdigest()!=digest:
                    raise ValueError('CATEGORY_EVIDENCE_CORRUPT')
            ledger.observe(e)
        visited={e['url'] for e in state['observations']}
        while state['pending'] and len(visited)<self.max_categories:
            url=state['pending'][0]
            state['attempts']+=1
            self.storage.write(self.key,encoded(state)) # persist before external activity
            try:
                e=dict(self.driver.visit(url,self.maximum_pages))
            except CategoryAccessBlocked:
                state.update(access_blocked=True,blocked_url=url)
                self.storage.write(self.key,encoded(state))
                raise
            if category_url(e['url'])!=url:raise ValueError('CATEGORY_UNEXPECTED_REDIRECT')
            token=hashlib.sha256(url.encode()).hexdigest()
            for field,key_field,hash_field in (
                ('snapshot_text','snapshot_key','snapshot_sha256'),
                ('discovery_text','discovery_key','discovery_evidence_sha256')):
                data=e.pop(field).encode('utf-8')
                digest=hashlib.sha256(data).hexdigest()
                key=f'{self.prefix}/evidence/{token}-{digest}.txt'
                self.storage.write(key,data)
                e[key_field],e[hash_field]=key,digest
            e['source_kind']=self.driver.source_kind
            ledger.observe(e)
            state['observations'].append(e);visited.add(url)
            state['pending'].pop(0)
            for child in e.get('children',[]):
                child=category_url(child)
                if child not in visited and child not in state['pending']:state['pending'].append(child)
            state['pages_observed']+=e.get('pages',0)
            self.storage.write(self.key,encoded(state))
            if e.get('status')=='blocked':
                state.update(access_blocked=True,blocked_url=url)
                self.storage.write(self.key,encoded(state))
                break
        report={**ledger.report(),'pending_nodes':len(state['pending']),
                'pages_observed':state['pages_observed'],'category_attempts':state['attempts'],
                'run_id':self.run_id,'source_kind':self.driver.source_kind,
                'page_counts_are_network_request_counts':False}
        self.storage.write(self.prefix+'/coverage.json',encoded(report))
        return report
