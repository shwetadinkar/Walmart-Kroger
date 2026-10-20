"""Documented Kroger Public API client. Diagnostic search, NOT full category crawler.

Only talks to https://api.kroger.com/v1 documented OAuth, Locations and Products APIs.
Never assumes a search term enumerates a Mariano's category or its subcategories.
"""
from __future__ import annotations

import base64
import json
import os
import time
from dataclasses import dataclass
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

ROOT = "https://api.kroger.com/v1"

class KrogerError(RuntimeError):
    pass

@dataclass
class Credentials:
    client_id: str
    client_secret: str

    @classmethod
    def from_environment(cls):
        instance = cls(os.getenv("KROGER_CLIENT_ID", ""), os.getenv("KROGER_CLIENT_SECRET", ""))
        if not instance.client_id or not instance.client_secret:
            raise KrogerError("KROGER_CLIENT_ID and KROGER_CLIENT_SECRET are required. Credentials must not be sent to third parties.")
        return instance

class KrogerClient:
    def __init__(self, creds: Credentials, opener=None, pause=0.2):
        self.creds = creds
        self.opener = opener or urlopen
        self.pause = pause
        self._token = ""
        self._expires = 0.0

    def _read(self, request):
        for attempt in range(3):
            try:
                if self.pause: time.sleep(self.pause)
                with self.opener(request, timeout=30) as response:
                    if getattr(response, 'status',200) != 200:
                        raise KrogerError('Unexpected Kroger API response')
                    payload = response.read(8_000_001)
                    if len(payload)>8_000_000:
                        raise KrogerError('API response too large')
                parsed=json.loads(payload)
                if not isinstance(parsed,dict): raise KrogerError('Unexpected Kroger JSON shape')
                return parsed
            except HTTPError as exc:
                if exc.code in (401,403):
                    raise KrogerError(f'Kroger API HTTP {exc.code}: credentials/scope/access denied') from exc
                if exc.code not in (429,500,502,503,504) or attempt == 2:
                    raise KrogerError(f'Kroger API HTTP {exc.code}') from exc
            except (TimeoutError,URLError,OSError) as exc:
                if attempt == 2: raise KrogerError('Kroger API unavailable or timed out') from exc
            time.sleep(2 ** attempt)
        raise KrogerError('Kroger API retry exhausted')

    def token(self):
        if self._token and time.monotonic() < self._expires - 90: return self._token
        basic=base64.b64encode(f'{self.creds.client_id}:{self.creds.client_secret}'.encode()).decode()
        body=urlencode({'grant_type':'client_credentials','scope':'product.compact'}).encode()
        req=Request(ROOT+'/connect/oauth2/token',data=body,headers={
            'Authorization':f'Basic {basic}', 'Content-Type':'application/x-www-form-urlencoded',
            'Accept':'application/json'},method='POST')
        result=self._read(req)
        token=result.get('access_token')
        if not isinstance(token,str) or not token: raise KrogerError('Missing OAuth token')
        self._token=token
        self._expires=time.monotonic()+int(result.get('expires_in', 1800))
        return token

    def get(self,path, params=None):
        if path not in ('/locations','/products') and not path.startswith('/locations/'):
            raise KrogerError('Only approved documented Kroger endpoints are supported')
        url=ROOT+path+(('?'+urlencode(params)) if params else '')
        req=Request(url,headers={'Authorization':f'Bearer {self.token()}','Accept':'application/json'})
        try: return self._read(req)
        except KrogerError as exc:
            if '401' in str(exc):
                self._token=''
                req=Request(url,headers={'Authorization':f'Bearer {self.token()}','Accept':'application/json'})
                return self._read(req)
            raise

    def locations(self, zipcode, limit=200):
        if not (isinstance(zipcode,str) and len(zipcode)==5 and zipcode.isdecimal()):
            raise KrogerError('A five-digit ZIP code is required')
        result=self.get('/locations',{'filter.zipCode.near':zipcode,'filter.limit':limit})
        data=result.get('data')
        if not isinstance(data,list): raise KrogerError('Malformed locations response')
        return data

    def products(self, location_id, term, offset=0, limit=50):
        if not location_id or not term or not (0<=offset<=100000) or not (1<=limit<=50):
            raise KrogerError('Invalid product search parameters')
        result=self.get('/products',{
            'filter.locationId':location_id, 'filter.term':term, 'filter.start':offset,
            'filter.limit':limit, 'filter.fulfillment':'ais,csp'
        })
        data=result.get('data')
        if not isinstance(data,list): raise KrogerError('Malformed product list response')
        return result


def location_candidates(client, zipcode, address_contains=''):
    """Require a human to confirm the exact brand/address and locationId; don't guess."""
    results=[]
    for loc in client.locations(zipcode):
        addr=loc.get('address') or {}
        if not isinstance(addr,dict): continue
        street=str(addr.get('addressLine1') or '')
        name=str(loc.get('name') or '')
        chain=loc.get('chain') or {}
        chain_name=str(chain.get('name') or '') if isinstance(chain,dict) else str(chain)
        if 'mariano' not in (' '.join([name,chain_name])).lower():
            continue
        if address_contains and address_contains.lower() not in street.lower(): continue
        results.append({'locationId':str(loc.get('locationId') or ''),'name':name,
             'chain':chain_name,'address':street,'zipcode':str(addr.get('zipCode') or ''),
             'city':str(addr.get('city') or '')})
    return results


def _price_string(x):
    if isinstance(x,(int,float)) and x>=0:
        return f'{x:.2f}'
    return ''

def diagnostic_product(product):
    """Normalized preview only. Neither synthetic nor publication-ready category proof."""
    if not isinstance(product,dict): raise KrogerError('Invalid product record')
    items=product.get('items') or []
    if not isinstance(items,list): raise KrogerError('Invalid product items')
    first=next((i for i in items if isinstance(i,dict) and isinstance(i.get('price'),dict)),{})
    price=first.get('price') or {}
    ims=product.get('images') or []
    image=''
    for im in ims:
        if isinstance(im,dict):
            sizes=im.get('sizes') or []
            if isinstance(sizes,list):
                image=next((str(s.get('url')) for s in sizes if isinstance(s,dict) and s.get('url')), '')
            if image:break
    return {
      'productId':str(product.get('productId') or ''),
      'upc':str(product.get('upc') or ''),
      'title':str(product.get('description') or ''),
      'brand':str(product.get('brand') or ''),
      'size':str(first.get('size') or ''),
      'regular_price':_price_string(price.get('regular')),
      'sale_price':_price_string(price.get('promo')),
      'image_url':image,
      'ppm':'',  # Public products API does not document retailer-displayed PPM.
      'digital_deals_description':'',
      'volume_deals_description':'',
      'category_coverage_verified':False,
      'publication_eligible':False,
    }


def trial(client, location_id, terms, limit_per_term=15, max_pages=2):
    """Query local prices, verify response shape, and report diagnostic samples only.

    Filtering with filter.term cannot attest complete category/subcategory discovery.
    """
    if len(terms)>10: raise KrogerError('Limit trial to ten terms')
    seen=set()
    samples=[]
    per_term={}
    for term in terms:
        term=str(term).strip()
        if not term: continue
        count=0
        for page_no in range(max_pages):
            result=client.products(location_id,term,offset=page_no*limit_per_term,limit=limit_per_term)
            for raw in result['data']:
                record=diagnostic_product(raw)
                if not record['productId']: continue
                count+=1
                if record['productId'] not in seen:
                    seen.add(record['productId'])
                    samples.append(record)
            if len(result['data'])<limit_per_term:break
        per_term[term]=count
    return {'mode':'KROGER_PUBLIC_API_DIAGNOSTIC_ONLY',
            'locationId':location_id,'terms':terms,'matches_by_term':per_term,
            'unique_preview_records':len(samples),'category_coverage_verified':False,
            'coupon_terms_verified':False,'retailer_displayed_ppm_verified':False,
            'suitable_as_contest_proof':False,'samples':samples[:50]}
