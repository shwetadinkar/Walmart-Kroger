"""Strict, credential-free configuration for the unattended discovery stage."""
import copy,re
from .category_coverage import category_url

def validate_discovery_config(document):
    if not isinstance(document,dict) or set(document)!={'version','store','roots','limits','output_prefix','schedule'}:
        raise ValueError('DISCOVERY_CONFIG_FIELDS')
    c=copy.deepcopy(document)
    if type(c['version']) is not int or c['version']!=1:raise ValueError('DISCOVERY_CONFIG_VERSION')
    s=c['store']
    if not isinstance(s,dict) or set(s)!={'id','zipcode','name','street'}:raise ValueError('DISCOVERY_STORE_FIELDS')
    if not re.fullmatch(r'\d{8}',str(s['id'])) or not isinstance(s['id'],str):raise ValueError('DISCOVERY_STORE_ID')
    if not isinstance(s['zipcode'],str) or not re.fullmatch(r'\d{5}',s['zipcode']):raise ValueError('DISCOVERY_STORE_ZIP')
    if any(not isinstance(s[k],str) or not s[k].strip() or len(s[k])>200 for k in ('name','street')):raise ValueError('DISCOVERY_STORE_CONTEXT')
    if not isinstance(c['roots'],list) or not 1<=len(c['roots'])<=28:raise ValueError('DISCOVERY_ROOTS')
    for r in c['roots']:
        if not isinstance(r,dict) or set(r)!={'name','url'} or not isinstance(r['name'],str) or not r['name'].strip():raise ValueError('DISCOVERY_ROOT_FIELDS')
        r['url']=category_url(r['url'])
    if len({r['url'] for r in c['roots']})!=len(c['roots']):raise ValueError('DISCOVERY_DUPLICATE_ROOT')
    limits=c['limits'];ceilings={'categories':1000,'pages_per_category':500,'total_pages':5000,'browser_actions':20000,'wall_seconds':3600}
    if not isinstance(limits,dict) or set(limits)!=set(ceilings):raise ValueError('DISCOVERY_LIMIT_FIELDS')
    if any(type(limits[k]) is not int or not 1<=limits[k]<=n for k,n in ceilings.items()):raise ValueError('DISCOVERY_LIMIT_RANGE')
    if not isinstance(c['output_prefix'],str) or not re.fullmatch(r'discovery[a-z0-9-]{0,50}',c['output_prefix']):raise ValueError('DISCOVERY_ISOLATED_PREFIX_REQUIRED')
    schedule=c['schedule']
    if not isinstance(schedule,dict) or set(schedule)!={'enabled','cron_utc'} or schedule['enabled'] is not False:raise ValueError('DISCOVERY_SCHEDULE_MUST_REMAIN_DISABLED')
    if not isinstance(schedule['cron_utc'],str) or not re.fullmatch(r'[0-9*/,-]+(?: [0-9*/,-]+){4}',schedule['cron_utc']):raise ValueError('DISCOVERY_SCHEDULE_FORMAT')
    return c
