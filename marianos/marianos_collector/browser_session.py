"""Ordinary isolated browser setup; no saved user session, proxy or restriction bypass."""
import re
from datetime import datetime,timezone
from .category_traversal import CategoryAccessBlocked
from .rendered_categories import RenderedCategoryDriver

def assert_accessible(response,text):
    if (response is not None and response.status in (401,403,429)) or re.search(r'access denied|verify you are human|captcha|unusual traffic',text,re.I):
        raise CategoryAccessBlocked('CATEGORY_ACCESS_BLOCKED_STOP')

def verify_rendered_store(store,shopping,grid):
    if store['name'] not in shopping or store['street'] not in shopping:
        raise ValueError('BROWSER_STORE_CONTEXT_UNVERIFIED')
    if grid is not None and grid!=store['id'][-5:]:raise ValueError('BROWSER_STORE_GRID_MISMATCH')

def prepare_store(page,config,guard):
    store=config['store'];guard('page')
    response=page.goto(config['roots'][0]['url'],wait_until='domcontentloaded')
    assert_accessible(response,page.locator('body').inner_text())
    page.get_by_role('button',name=re.compile('open modal to change how you are shopping')).wait_for(state='visible')
    guard();page.get_by_role('button',name=re.compile('open modal to change how you are shopping')).click()
    dialog=page.get_by_role('dialog',name='Start Your Shopping Trip',exact=True)
    dialog.wait_for(state='visible');guard();dialog.get_by_role('tab',name='Pickup',exact=True).click()
    guard();dialog.get_by_role('searchbox',name='Search by Postal Code',exact=True).fill(store['zipcode'])
    guard();dialog.get_by_role('button',name='Search',exact=True).click()
    radio=dialog.get_by_role('radio',name=re.compile(re.escape(store['name'])+r'.*'+re.escape(store['street'])+r'.*'+re.escape(store['zipcode']),re.S))
    radio.wait_for(state='visible')
    if radio.count()!=1:raise ValueError('BROWSER_EXACT_STORE_SELECTION_UNVERIFIED')
    guard();radio.check();guard();dialog.get_by_role('button',name='Start Shopping',exact=True).click()
    dialog.wait_for(state='hidden')
    page.wait_for_function("s => {const e=document.querySelector('[aria-label=\"Currently Shopping\"]');return e && e.innerText.includes(s.name) && e.innerText.includes(s.street)}",arg=store)
    shopping=page.get_by_label('Currently Shopping',exact=True).inner_text()
    grid=page.locator('main [data-testid="auto-grid"]')
    verify_rendered_store(store,shopping,grid.get_attribute('data-qa') if grid.count() else None)

def create_discovery_driver(config,guard,remaining_seconds):
    try:from playwright.sync_api import sync_playwright
    except ImportError as exc:raise RuntimeError('Install optional browser dependency and Chromium before unattended discovery') from exc
    runtime=sync_playwright().start();browser=None;page=None
    try:
        # A fresh context is intentional: do not attach to the user's browser or copy cookies/tokens.
        browser=runtime.chromium.launch(headless=True)
        context=browser.new_context(locale='en-US')
        page=context.new_page();page.set_default_timeout(min(15000,max(1,int(remaining_seconds*1000))))
        prepare_store(page,config,guard)
        s=config['store'];driver=RenderedCategoryDriver(page,s['id'],s['zipcode'],s['name'],s['street'],
            maximum_actions=config['limits']['browser_actions'],timeout_seconds=remaining_seconds,action_guard=guard)
        def close():
            try:browser.close()
            finally:runtime.stop()
        driver.close=close
        return driver
    except Exception as exc:
        if page is not None:
            try:
                text=page.locator('body').inner_text(timeout=2000)
                assert_accessible(None,text)
            except CategoryAccessBlocked as blocked:
                exc=blocked
            except Exception: text='Body unavailable'
            exc.discovery_evidence={'observed_at':datetime.now(timezone.utc).isoformat(),'url':page.url,
                                    'body_text':text[:12000],'isolated_unsigned_browser':True}
        if browser is not None:browser.close()
        runtime.stop()
        raise exc
