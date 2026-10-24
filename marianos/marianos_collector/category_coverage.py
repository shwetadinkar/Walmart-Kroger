"""Evidence ledger: navigation discovery and live category completion stay distinct."""
from datetime import datetime
import re
from urllib.parse import parse_qsl,urlencode,urljoin,urlsplit,urlunsplit


def category_url(value):
    parsed=urlsplit(urljoin('https://www.marianos.com',value))
    if (parsed.scheme!='https' or parsed.hostname not in ('marianos.com','www.marianos.com')
            or parsed.username or parsed.password or parsed.port not in (None,443)):
        raise ValueError('Invalid retailer category origin')
    if not (parsed.path.startswith(('/d/','/pl/')) or parsed.path.rstrip('/')=='/savings/cl/coupons'):
        raise ValueError('Not a configured category path')
    query=sorted((k,v) for k,v in parse_qsl(parsed.query) if k not in ('pzn','page') and not k.startswith('utm_'))
    return urlunsplit(('https','www.marianos.com',parsed.path.rstrip('/'),urlencode(query),''))


class CoverageLedger:
    def __init__(self,roots,store_id,zipcode):
        self.roots=[{'name':r['name'],'url':category_url(r['url'])} for r in roots]
        self.store_id,self.zipcode=store_id,zipcode
        self.nodes={r['url']:{'children':[],'observations':[]} for r in self.roots}

    def discover(self,parent,children):
        parent=category_url(parent)
        node=self.nodes.setdefault(parent,{'children':[],'observations':[]})
        for child in children:
            url=category_url(child)
            self.nodes.setdefault(url,{'children':[],'observations':[]})
            if url not in node['children']:node['children'].append(url)

    def observe(self,observation):
        e=dict(observation)
        if (e.get('store_id')!=self.store_id or e.get('zipcode')!=self.zipcode
                or e.get('store_context_verified') is not True):
            raise ValueError('CATEGORY_STORE_MISMATCH')
        if not re.fullmatch(r'[a-f0-9]{64}',e.get('snapshot_sha256','')):
            raise ValueError('CATEGORY_EVIDENCE_HASH_REQUIRED')
        stamp=datetime.fromisoformat(e['observed_at'])
        if stamp.tzinfo is None:raise ValueError('CATEGORY_EVIDENCE_TIMEZONE_REQUIRED')
        e['url']=category_url(e['url'])
        self.discover(e['url'],e.get('children',[]))
        self.nodes[e['url']]['observations'].append(e)

    def _evidence_valid(self,node):
        if not node['observations']:return False
        e=node['observations'][-1]
        expected,observed=e.get('expected_products'),e.get('observed_listing_cards',e.get('observed_organic_cards'))
        if 'hierarchy_expected_products' in e and e['hierarchy_expected_products'] is not None:
            if type(e['hierarchy_expected_products']) is not int or e['hierarchy_expected_products']!=expected:
                return False
        # A ledger belongs to one collection run. Changing terminal membership is
        # not reconciled by a later observation merely having the same total.
        current=set(e.get('unique_product_urls',[]))
        if any(previous.get('status')=='ok' and previous.get('terminal') is True
               and set(previous.get('unique_product_urls',[]))!=current
               for previous in node['observations'][:-1]):return False
        return (e.get('status')=='ok' and e.get('source_kind') in ('rendered-retailer','licensed-retailer-feed')
                and e.get('listing_present') is True and e.get('terminal') is True
                and e.get('discovery_complete') is True
                and bool(re.fullmatch(r'[a-f0-9]{64}',e.get('discovery_evidence_sha256','')))
                and type(expected) is int and type(observed) is int and expected>=0 and observed>=0
                and (expected>0 or e.get('explicit_empty') is True)
                and isinstance(e.get('unique_product_urls'),list)
                and all(isinstance(u,str) and u for u in e['unique_product_urls'])
                and len(set(e['unique_product_urls']))<=observed)

    def _own_complete(self,node):
        return (self._evidence_valid(node)
                and len(set(node['observations'][-1]['unique_product_urls']))==node['observations'][-1]['expected_products'])

    def _descendant_products(self,url,seen):
        if url in seen:return set()
        node=self.nodes[url];latest=node['observations'][-1] if node['observations'] else {}
        found=set(latest.get('unique_product_urls',[]))
        for child in node['children']:found.update(self._descendant_products(child,seen|{url}))
        return found

    def _basis(self,url,visiting):
        node=self.nodes[url]
        if url in visiting or not self._evidence_valid(node):return None
        if not all(self._basis(c,visiting|{url}) for c in node['children']):return None
        if self._own_complete(node):
            parent=set(node['observations'][-1]['unique_product_urls'])
            if any(not self._descendant_products(child,{url}).issubset(parent) for child in node['children']):
                return None
            return 'direct-listing'
        if not node['children']:return None
        latest=node['observations'][-1]
        union=set()
        for child in node['children']:union.update(self._descendant_products(child,{url}))
        if (len(union)==latest['expected_products']
                and set(latest['unique_product_urls']).issubset(union)):
            return 'exhaustive-descendant-union'
        return None

    def _complete(self,url,visiting):
        return self._basis(url,visiting) is not None

    def report(self):
        roots=[]
        for root in self.roots:
            node=self.nodes[root['url']]
            done=self._complete(root['url'],set())
            last=node['observations'][-1] if node['observations'] else {}
            roots.append({**root,'status':'complete' if done else (last.get('status') if last.get('status') not in (None,'ok') else 'incomplete'),
                          'complete':done,'observations':len(node['observations']),
                          'completion_basis':self._basis(root['url'],set()),
                          'discovered_children':len(node['children']),
                          'unique_product_urls':len(set(last.get('unique_product_urls',[])))})
        return {'store_id':self.store_id,'zipcode':self.zipcode,'configured_roots':len(roots),
                'complete_roots':sum(r['complete'] for r in roots),'all_roots_complete':bool(roots) and all(r['complete'] for r in roots),
                'discovered_nodes':len(self.nodes),'visited_nodes':sum(bool(n['observations']) for n in self.nodes.values()),
                'roots':roots,'nodes':self.nodes,'submission_ready':False}
