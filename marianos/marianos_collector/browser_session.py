"""Ordinary isolated browser setup; no saved user session, proxy or restriction bypass.

Ported from `marianos-fresh-runs-category-evidence`. Only what a bounded page
read needs came across; the category traversal it was written for did not.
"""
import re
from datetime import datetime, timezone

REFUSAL_TEXT = re.compile(
    r'access denied|verify you are human|captcha|unusual traffic'
    r'|are you a robot|errors\.edgesuite\.net|request (?:was )?blocked',
    re.I)
REFUSAL_STATUS = (401, 403, 429)


class AccessBlocked(RuntimeError):
    """The retailer refused. Stop. This is never caught in order to retry."""


def safe_browser_error_code(error):
    """Whitelist diagnostic codes; never persist exception URLs, headers or credentials."""
    text = str(error)
    code = re.search(r'\bnet::ERR_[A-Z0-9_]+\b', text)
    if code:
        return code.group()
    if "Executable doesn't exist" in text:
        return 'BROWSER_EXECUTABLE_MISSING'
    if 'Timeout' in type(error).__name__:
        return 'BROWSER_OPERATION_TIMEOUT'
    return 'BROWSER_OPERATION_FAILED'


def refusal_sign(response, text):
    """What about this response looks like a refusal, or ""."""
    if response is not None and response.status in REFUSAL_STATUS:
        return f'HTTP_{response.status}'
    if response is not None and response.status >= 500:
        return f'HTTP_{response.status}'
    found = REFUSAL_TEXT.search(text or '')
    return f'TEXT:{found.group().lower()}' if found else ''


def assert_accessible(response, text):
    sign = refusal_sign(response, text)
    if sign:
        raise AccessBlocked(sign)


def verify_rendered_store(store, shopping):
    if store['name'] not in shopping or store['street'] not in shopping:
        raise ValueError('BROWSER_STORE_CONTEXT_UNVERIFIED')


def store_proof(dialog, url):
    """The selection as the page showed it, in the form rendered_product reads."""
    radios = dialog.locator('input[type="radio"]')
    return {'observed_at': datetime.now(timezone.utc).isoformat(), 'url': url,
            'dialogs': [{
                'text': dialog.inner_text(),
                'radios': [{'checked': radios.nth(i).is_checked(),
                            'label': radios.nth(i).get_attribute('aria-label'),
                            'value': radios.nth(i).get_attribute('value')}
                           for i in range(radios.count())]}]}


def prepare_store(page, store, start_url):
    """Select the store through the site's own shopping-trip dialog.

    Returns the store proof captured with the radio checked. Any refusal raises
    AccessBlocked; any unmet step raises and nothing further is read, because a
    price read without a proved store is not evidence about that store.
    """
    response = page.goto(start_url, wait_until='domcontentloaded')
    assert_accessible(response, page.locator('body').inner_text())
    opener = re.compile('open modal to change how you are shopping')
    page.get_by_role('button', name=opener).wait_for(state='visible')
    page.get_by_role('button', name=opener).click()
    dialog = page.get_by_role('dialog', name='Start Your Shopping Trip', exact=True)
    dialog.wait_for(state='visible')
    dialog.get_by_role('tab', name='Pickup', exact=True).click()
    dialog.get_by_role('searchbox', name='Search by Postal Code', exact=True).fill(store['zipcode'])
    dialog.get_by_role('button', name='Search', exact=True).click()
    radio = dialog.get_by_role('radio', name=re.compile(
        re.escape(store['name']) + r'.*' + re.escape(store['street'])
        + r'.*' + re.escape(store['zipcode']), re.S))
    radio.wait_for(state='visible')
    if radio.count() != 1:
        raise ValueError('BROWSER_EXACT_STORE_SELECTION_UNVERIFIED')
    radio.check()
    proof = store_proof(dialog, page.url)
    dialog.get_by_role('button', name='Start Shopping', exact=True).click()
    dialog.wait_for(state='hidden')
    page.wait_for_function(
        "s => {const e=document.querySelector('[aria-label=\"Currently Shopping\"]');"
        "return e && e.innerText.includes(s.name) && e.innerText.includes(s.street)}",
        arg=store)
    verify_rendered_store(store, page.get_by_label('Currently Shopping', exact=True).inner_text())
    return proof
