"""Normal rendered-UI driver; no hidden endpoints, CAPTCHA solving or proxy bypass.

Requires an already selected, verified pickup store. The caller owns the browser
session and may use Playwright's synchronous Page. This module imports no browser
library and never attaches to the user's browser or reads saved credentials.
"""
from datetime import datetime,timezone
import re
import time
from .category_coverage import category_url
from .category_traversal import CategoryAccessBlocked


LISTING_DOM = r'''() => {
 const body=document.body.innerText;
 if(/access denied|verify you are human|captcha|unusual traffic/i.test(body))return {body,missing_main:true};
 const main=document.querySelector('main');
 if(!main)return {missing_main:true,body:document.body.innerText.slice(0,2000)};
 const heading=Array.from(main.querySelectorAll('h2')).find(x=>/^\d[\d,]* results?$/.test(x.textContent.trim()));
 // Only the primary results grid: recommendation carousels are outside it.
 const grid=main.querySelector('[data-testid="auto-grid"]');
 const cards=grid?Array.from(grid.querySelectorAll('.ProductCard')).map(c=>({
   url:c.querySelector('a[href^="/p/"]')?.getAttribute('href'),
   text:c.innerText,sponsored:/\bSponsored\b/.test(c.innerText)})):[];
 return {url:location.href,title:main.querySelector('h1')?.textContent,
   expected_products:heading?Number(heading.textContent.replace(/[^0-9]/g,'')):null,
   store_grid:grid?.getAttribute('data-qa'),cards,
   shopping:document.querySelector('[aria-label="Currently Shopping"]')?.innerText||'',
   main_text:main.innerText,
   category_links:Array.from(main.querySelectorAll('a[href]')).map(a=>({name:a.textContent,url:a.getAttribute('href')}))
    .filter(a=>/^\/(?:d|pl)\//.test(a.url)),
   load_more:Array.from(main.querySelectorAll('button')).some(b=>b.textContent.trim()==='Load More Results'),
   loading:Array.from(main.querySelectorAll('[role="status"]')).some(s=>/loading/i.test(s.innerText))};
}'''

DEPARTMENT_DOM = r'''d => {
 const checked=d.querySelector('input[type="radio"]:checked');
 if(!checked)return {known:false,children:[]};
 const branch=checked.closest('label').parentElement;
 return {known:true,current:checked.getAttribute('aria-label'),children:
 Array.from(branch.querySelectorAll('input[type="radio"]')).filter(r=>r!==checked)
 .map(r=>({name:r.getAttribute('aria-label'),value:r.value})),text:d.innerText};
}'''


class RenderedCategoryDriver:
    source_kind='rendered-retailer'
    def __init__(self,page,store_id,zipcode,store_name,street,*,maximum_actions=200,timeout_seconds=900):
        if not re.fullmatch(r'\d{8}',store_id) or not re.fullmatch(r'\d{5}',zipcode):
            raise ValueError('Verified store ID and ZIP required')
        self.page,self.store_id,self.zipcode=page,store_id,zipcode
        self.store_name,self.street=store_name,street
        self.maximum_actions,self.actions=maximum_actions,0
        self.deadline=time.monotonic()+timeout_seconds
        self.page.set_default_timeout(15000)

    def _action(self):
        if self.actions>=self.maximum_actions or time.monotonic()>=self.deadline:
            raise RuntimeError('CATEGORY_BROWSER_BUDGET_EXHAUSTED')
        self.actions+=1

    def _read(self):
        e=self.page.evaluate(LISTING_DOM)
        text=e.get('main_text',e.get('body',''))
        if re.search(r'access denied|verify you are human|captcha|unusual traffic',text,re.I):
            raise CategoryAccessBlocked('CATEGORY_ACCESS_BLOCKED_STOP')
        if self.store_name not in e.get('shopping','') or self.street not in e.get('shopping',''):
            raise ValueError('CATEGORY_STORE_CONTEXT_LOST')
        if e.get('store_grid') not in (None,self.store_id[-5:]):
            raise ValueError('CATEGORY_GRID_STORE_MISMATCH')
        e['observed_at']=datetime.now(timezone.utc).isoformat()
        return e

    def _settled(self):
        # A heading can be present before the previous category's results disappear.
        try:
            self.page.wait_for_function(r'''() => {
              if(/access denied|verify you are human|captcha|unusual traffic/i.test(document.body.innerText))return true;
              const m=document.querySelector('main');if(!m)return false;
              const busy=Array.from(m.querySelectorAll('[role="status"]')).some(x=>/^loading$/i.test(x.innerText.trim()));
              return !busy && (m.querySelector('.ProductCard') || /0 results|page doesn.t exist/i.test(m.innerText));
            }''',timeout=20000)
        except Exception:
            self._read() # turn an HTTP-200 challenge into a durable stop, not a retryable timeout
            raise
        return self._read()

    def _goto(self,url):
        self._action();response=self.page.goto(url,wait_until='domcontentloaded')
        if response and response.status in (401,403,429):raise CategoryAccessBlocked('CATEGORY_ACCESS_BLOCKED_STOP')
        e=self._settled()
        if category_url(e['url'])!=category_url(url):raise ValueError('CATEGORY_UNEXPECTED_REDIRECT')
        return e

    def _departments(self):
        button=self.page.get_by_role('button',name=re.compile(r'^Departments.*filter dropdown$'))
        if button.count()!=1:return {'known':False,'children':[],'text':'Department filter unavailable'}
        self._action();button.click()
        dialog=self.page.get_by_role('dialog',name='Departments',exact=True)
        dialog.wait_for(state='visible')
        return dialog.evaluate(DEPARTMENT_DOM)

    def visit(self,url,maximum_pages):
        url=category_url(url);e=self._goto(url);snapshots=[];pages=1
        expected=e.get('expected_products')
        if expected is None:
            # Landing pages and coupons need dedicated traversal; never pretend they are empty listings.
            children=[]
            for link in e.get('category_links',[]):
                child=category_url(link['url'])
                if child!=url and child not in children:children.append(child)
            return self._observation(url,e,children,False,'unresolved_landing_page',pages,'No listing hierarchy proof',False)
        while True:
            snapshots.append(e)
            if not e['load_more']:break
            if pages>=maximum_pages:
                return self._observation(url,e,[],False,'page_budget_exhausted',pages,str(snapshots),False)
            before=len(e['cards']);self._action()
            self.page.get_by_role('button',name='Load More Results',exact=True).click()
            self.page.wait_for_function('(n) => document.querySelectorAll(\'main [data-testid="auto-grid"] .ProductCard\').length > n',arg=before,timeout=20000)
            e=self._settled();pages+=1
            if e['expected_products']!=expected:raise RuntimeError('CATEGORY_RESULT_COUNT_CHANGED')
        hierarchy=self._departments();children=[];proof=[hierarchy]
        # A missing/ambiguous checked branch cannot establish exhaustive discovery.
        for child in hierarchy['children']:
            self._action();self.page.get_by_role('radio',name=child['name'],exact=True).check()
            self._action();self.page.get_by_role('button',name='View results',exact=True).click()
            child_page=self._settled();child_url=category_url(child_page['url'])
            if child_url==url:raise RuntimeError('CATEGORY_CHILD_DID_NOT_NAVIGATE')
            children.append(child_url);proof.append({'selection':child,'url':child_url})
            self._goto(url);self._departments()
        close=self.page.get_by_role('dialog',name='Departments',exact=True).get_by_role('button',name='Close modal dialog',exact=True)
        if close.count():self._action();close.click()
        import json
        result=self._observation(url,e,children,True,'ok',pages,json.dumps(proof,ensure_ascii=False),hierarchy['known'])
        result['snapshot_text']=json.dumps(snapshots,ensure_ascii=False)
        return result

    def _observation(self,url,e,children,terminal,status,pages,proof,discovery_complete):
        import json
        from urllib.parse import urljoin,urlsplit,urlunsplit
        urls=[]
        for card in e.get('cards',[]):
            if not card.get('url'):continue
            p=urlsplit(urljoin(url,card['url']));urls.append(urlunsplit((p.scheme,p.netloc,p.path,'','')))
        return {'url':url,'store_id':self.store_id,'zipcode':self.zipcode,'store_context_verified':True,
                'observed_at':e.get('observed_at',datetime.now(timezone.utc).isoformat()),'status':status,
                'listing_present':e.get('expected_products') is not None,'terminal':terminal,
                'expected_products':e.get('expected_products'),'observed_listing_cards':len(e.get('cards',[])),
                'unique_product_urls':sorted(set(urls)),'children':children,
                'explicit_empty':e.get('expected_products')==0 and '0 results' in e.get('main_text',''),
                'discovery_complete':discovery_complete,'snapshot_text':json.dumps(e,ensure_ascii=False),
                'discovery_text':proof,'pages':pages,'browser_actions':self.actions,
                'sponsored_cards':sum(c.get('sponsored',False) for c in e.get('cards',[]))}
