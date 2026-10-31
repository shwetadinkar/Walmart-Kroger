"""The stop rules of the bounded page probe, against a page with no network."""
import json
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from marianos_collector import page_probe
from marianos_collector.browser_session import (AccessBlocked, assert_accessible,
                                                refusal_sign, safe_browser_error_code,
                                                verify_rendered_store)
from marianos_collector.page_probe import (Capture, MAXIMUM_PAGES, Measurements,
                                           run_probe, select_products)

STORE = {'id': '53100502', 'name': 'Marianos Vernon Hills',
         'street': '1720 N Milwaukee Ave', 'zipcode': '60061'}
PROOF = {'observed_at': '2026-10-31T15:00:00+00:00', 'url': 'u', 'dialogs': []}
GOOD = 'Pickup at Marianos Vernon Hills | 1720 N Milwaukee Ave\nUPC: {}\n$1.00'


class Response:
    def __init__(self, status, url=''):
        self.status, self.url = status, url

    def body(self):
        return b'<html>served</html>'


class Locator:
    def __init__(self, page):
        self.page = page

    def inner_text(self, timeout=None):
        return self.page.text

    def aria_snapshot(self):
        return '- generic'


class Page:
    """Serves `script`, one entry per navigation: (status, text) or an exception."""

    def __init__(self, script):
        self.script = list(script)
        self.visits, self.text, self.url, self.listener = [], '', '', None
        self.after_visit = None

    def on(self, event, listener):
        self.listener = listener

    def goto(self, url, wait_until=None):
        self.visits.append(url)
        step = self.script.pop(0)
        if isinstance(step, Exception):
            raise step
        status, self.text = step
        self.url = url
        if self.after_visit:
            self.after_visit(self)
        return Response(status)

    def wait_for_function(self, *args, **kwargs):
        pass

    def locator(self, selector):
        return Locator(self)

    def content(self):
        return '<html>rendered</html>'

    def screenshot(self, full_page=False):
        return b'png'


def targets(count):
    return [{'upc': f'{i:013d}', 'category': 'Grocery', 'url': f'https://www.marianos.com/p/x/{i:013d}',
             'page_url': f'https://www.marianos.com/p/x/{i:013d}?fulfillment=PICKUP', 'title': 't'}
            for i in range(count)]


def served(items):
    return [(200, GOOD.format(t['upc'])) for t in items]


class RunProbe(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.waits = []
        patch = mock.patch.object(page_probe, 'prepare_store', return_value=PROOF)
        self.prepare = patch.start()
        self.addCleanup(patch.stop)

    def run_on(self, page, items):
        self.capture = Capture(pathlib.Path(self.dir.name) / 'run')
        return run_probe(page, items, STORE, 'https://www.marianos.com/', self.capture,
                         pace_seconds=30, sleep=self.waits.append)

    def test_every_page_read_once_paced_and_in_importer_form(self):
        items = targets(4)
        page = Page(served(items))
        result = self.run_on(page, items)
        self.assertEqual(page.visits, [t['page_url'] for t in items])
        self.assertEqual(self.waits, [30, 30, 30])
        self.assertEqual((result['pages_served'], result['stopped']), (4, None))
        saved = json.loads((self.capture.root / f"PDP_{items[2]['upc']}.json").read_text())
        self.assertEqual(saved['url'], items[2]['page_url'])
        self.assertIn('UPC: ' + items[2]['upc'], saved['text'])
        self.assertEqual(json.loads((self.capture.root / 'CURRENT_STORE.json').read_text()), PROOF)

    def assert_stopped_at_second(self, step, sign):
        items = targets(5)
        page = Page(served(items[:1]) + [step] + served(items[2:]))
        result = self.run_on(page, items)
        self.assertEqual(page.visits, [t['page_url'] for t in items[:2]])
        self.assertEqual(result['stopped']['sign'], sign)
        self.assertEqual(result['stopped']['ordinal'], 2)
        self.assertEqual(result['stopped']['after_pages_served'], 1)
        self.assertEqual(result['pages_requested'], 2)
        self.assertEqual(result['outcomes'], {'served': 1, 'refused': 1})
        self.assertFalse((self.capture.root / f"PDP_{items[1]['upc']}.json").exists())

    def test_http_refusals_stop_without_retry(self):
        for status in (401, 403, 429, 503):
            with self.subTest(status=status):
                self.setUp()
                self.assert_stopped_at_second((status, 'Forbidden'), f'HTTP_{status}')

    def test_refusal_served_with_200_stops(self):
        self.assert_stopped_at_second((200, 'Access Denied\nReference #18'), 'TEXT:access denied')

    def test_transport_failure_stops_without_retry(self):
        self.assert_stopped_at_second(RuntimeError('net::ERR_HTTP2_PROTOCOL_ERROR at x'),
                                      'net::ERR_HTTP2_PROTOCOL_ERROR')

    def test_lost_store_context_stops(self):
        self.assert_stopped_at_second((200, 'UPC: 1\nPickup at Marianos West Loop'),
                                      'STORE_CONTEXT_LOST')

    def test_refused_page_keeps_its_bytes(self):
        items = targets(2)
        result = self.run_on(Page(served(items[:1]) + [(403, 'Access Denied')]), items)
        refused = result['observations'][1]
        self.assertEqual((refused['status'], refused['refusal']), (403, 'HTTP_403'))
        self.assertEqual((self.capture.root / refused['text_file']).read_bytes(), b'Access Denied')
        self.assertTrue((self.capture.root / refused['files']['rendered.html']).exists())

    def test_first_party_subresource_refusal_stops(self):
        items = targets(3)
        page = Page(served(items))

        def refuse_second(p):
            if len(p.visits) == 2:
                p.listener(Response(429, 'https://www.marianos.com/atlas/v1/x'))
        page.after_visit = refuse_second
        result = self.run_on(page, items)
        self.assertEqual(result['stopped']['sign'], 'SUBRESOURCE_429')
        self.assertEqual(len(page.visits), 2)

    def test_leaving_the_site_stops(self):
        items = targets(3)
        page = Page(served(items))

        def redirect(p):
            if len(p.visits) == 2:
                p.url = 'https://challenge.example/x'
        page.after_visit = redirect
        self.assertEqual(self.run_on(page, items)['stopped']['sign'], 'LEFT_SITE')

    def test_missing_page_is_a_gap_not_a_refusal(self):
        items = targets(3)
        page = Page(served(items[:1]) + [(404, 'Not found')] + served(items[2:]))
        result = self.run_on(page, items)
        self.assertEqual(result['outcomes'], {'served': 2, 'not_found': 1})
        self.assertIsNone(result['stopped'])

    def test_refused_store_selection_reads_no_product(self):
        self.prepare.side_effect = AccessBlocked('HTTP_403')
        page = Page([])
        result = self.run_on(page, targets(3))
        self.assertEqual(page.visits, [])
        self.assertFalse(result['store_selected'])
        self.assertEqual(result['stopped']['kind'], 'refused')
        self.assertEqual(result['stopped']['sign'], 'HTTP_403')
        self.assertEqual(result['pages_requested'], 0)

    def test_transport_failure_at_store_selection_is_not_called_a_refusal(self):
        self.prepare.side_effect = RuntimeError('net::ERR_HTTP2_PROTOCOL_ERROR at https://x')
        page = Page([])
        result = self.run_on(page, targets(3))
        self.assertEqual(page.visits, [])
        self.assertEqual(result['stopped']['kind'], 'transport_failure_unattributed')
        self.assertEqual(result['stopped']['sign'], 'net::ERR_HTTP2_PROTOCOL_ERROR')

    def test_unproved_store_reads_no_product(self):
        self.prepare.side_effect = ValueError('BROWSER_EXACT_STORE_SELECTION_UNVERIFIED')
        page = Page([])
        result = self.run_on(page, targets(3))
        self.assertEqual((page.visits, result['stopped']['kind']), ([], 'failed'))

    def test_subresource_refused_during_store_selection_reads_no_product(self):
        page = Page([])

        def prepared(p, store, url):
            p.listener(Response(403, 'https://www.marianos.com/atlas/v1/x'))
            return PROOF
        self.prepare.side_effect = prepared
        result = self.run_on(page, targets(3))
        self.assertEqual((page.visits, result['stopped']['sign']), ([], 'SUBRESOURCE_403'))

    def test_bounds(self):
        with self.assertRaises(ValueError):
            self.run_on(Page([]), targets(MAXIMUM_PAGES + 1))
        self.dir.cleanup()
        self.dir = tempfile.TemporaryDirectory()
        with self.assertRaises(ValueError):
            self.run_on(Page([]), targets(2) + targets(1))

    def test_output_directory_must_be_new(self):
        root = pathlib.Path(self.dir.name) / 'taken'
        Capture(root)
        with self.assertRaises(FileExistsError):
            Capture(root)


class Signs(unittest.TestCase):
    def test_refusal_sign(self):
        self.assertEqual(refusal_sign(Response(200), 'Normal store products'), '')
        self.assertEqual(refusal_sign(None, 'Please verify you are human'),
                         'TEXT:verify you are human')
        self.assertEqual(refusal_sign(Response(404), 'gone'), '')
        with self.assertRaises(AccessBlocked):
            assert_accessible(Response(403), 'x')
        assert_accessible(Response(200), 'x')

    def test_error_code_never_carries_raw_text(self):
        self.assertEqual(safe_browser_error_code(RuntimeError('net::ERR_FAILED at https://x?t=1')),
                         'net::ERR_FAILED')
        self.assertEqual(safe_browser_error_code(RuntimeError('secret')), 'BROWSER_OPERATION_FAILED')

    def test_store_must_match(self):
        verify_rendered_store(STORE, 'Marianos Vernon Hills | 1720 N Milwaukee Ave')
        with self.assertRaises(ValueError):
            verify_rendered_store(STORE, 'Marianos West Loop | 40 S Halsted St')

    def test_only_first_party_refusals_count(self):
        seen = Measurements()
        seen.on_response(Response(403, 'https://ads.example/pixel'))
        seen.on_response(Response(200, 'https://www.marianos.com/ok'))
        self.assertEqual(seen.take(), [])
        seen.on_response(Response(403, 'https://www.marianos.com/x?q=1'))
        self.assertEqual(seen.take(), [{'status': 403, 'path': '/x'}])
        self.assertEqual(seen.take(), [])


def row(upc, category, sale='', weight='12 oz', price='1.00'):
    return {'upc': upc, 'category': category, 'url': f'https://www.marianos.com/p/x/{upc}',
            'product_title': 't', 'sale_price': sale, 'weight': weight, 'regular_price': price}


class Selection(unittest.TestCase):
    def test_every_root_before_a_second_from_any(self):
        rows = [row(f'A{i}', 'Big') for i in range(5)] + [row('B', 'Small'), row('C', 'Tiny')]
        context = {r['upc']: {'offer_status': 'qualifying_pickup_offer'} for r in rows}
        picked = select_products(rows, context, target=4)
        self.assertEqual([p['category'] for p in picked], ['Big', 'Small', 'Tiny', 'Big'])

    def test_prefers_sale_then_measure(self):
        rows = [row('1', 'X', weight='each'), row('2', 'X'), row('3', 'X', sale='0.50', weight='each')]
        context = {r['upc']: {'offer_status': 'qualifying_pickup_offer'} for r in rows}
        self.assertEqual([p['upc'] for p in select_products(rows, context, target=3)],
                         ['3', '2', '1'])

    def test_needs_a_comparable_offer_and_a_root(self):
        rows = [row('1', 'X'), row('2', ''), row('3', 'X', price=''), row('4', 'X')]
        context = {r['upc']: {'offer_status': 'qualifying_pickup_offer'} for r in rows[:3]}
        context['4'] = {'offer_status': 'no_qualifying_pickup_offer'}
        self.assertEqual([p['upc'] for p in select_products(rows, context)], ['1'])

    def test_selection_is_stable_and_bounded(self):
        rows = [row(str(i), 'X') for i in range(40)]
        context = {r['upc']: {'offer_status': 'qualifying_pickup_offer'} for r in rows}
        self.assertEqual(select_products(rows, context), select_products(rows[::-1], context))
        with self.assertRaises(ValueError):
            select_products(rows, context, target=MAXIMUM_PAGES + 1)


if __name__ == '__main__':
    unittest.main()
