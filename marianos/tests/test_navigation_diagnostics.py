import json
import os
import unittest
from types import SimpleNamespace
from marianos_collector.navigation_diagnostics import NavigationDiagnostics

class NavigationDiagnosticsTests(unittest.TestCase):
    def recorder(self):
        page=SimpleNamespace(main_frame=object())
        return page,NavigationDiagnostics(page,"123.4.5.6",clock=lambda:1)
    def request(self,page,url,**kwargs):
        return SimpleNamespace(url=url,frame=kwargs.get('frame',page.main_frame),is_navigation_request=lambda:True,failure='net::ERR_HTTP2_PROTOCOL_ERROR at https://secret/?token=secret')
    def test_order_redirect_response_then_failure_and_privacy(self):
        page,d=self.recorder()
        a=self.request(page,'https://user:secret@www.marianos.com/pl/milk/02001?token=secret#secret')
        b=self.request(page,'https://private.example/customer/secret')
        d.request(a);d.response(SimpleNamespace(request=a,status=302));d.request(b);d.failed(b)
        result=d.snapshot()
        self.assertEqual([e['event'] for e in result['events']],['request','response','request','requestfailed'])
        self.assertEqual(result['events'][1]['status'],302)
        self.assertEqual(result['events'][0]['target'],'https://www.marianos.com/[path-redacted]')
        self.assertNotIn('secret',json.dumps(result))
        self.assertEqual(result['events'][-1]['error_code'],'net::ERR_HTTP2_PROTOCOL_ERROR')
    def test_failure_without_response_and_subframes_ignored(self):
        page,d=self.recorder();r=self.request(page,'https://www.marianos.com/')
        d.request(self.request(page,r.url,frame=object()));d.failed(r)
        self.assertEqual([e['event'] for e in d.snapshot()['events']],['requestfailed'])
    def test_cap_and_snapshot_isolation(self):
        page,d=self.recorder();r=self.request(page,'https://www.marianos.com/')
        for _ in range(100):d.request(r)
        result=d.snapshot()
        self.assertEqual(len(result['events']),32)
        self.assertEqual(result['dropped_events'],68)
        self.assertLess(len(json.dumps(result)),8192)
        result['events'].clear()
        self.assertEqual(len(d.snapshot()['events']),32)
    def test_invalid_version_and_failure_text_not_retained(self):
        page,d=self.recorder();d.version='invalid'
        r=self.request(page,'https://marianos.com.evil/secret');r.failure='secret'
        d.failed(r)
        self.assertEqual(d.snapshot()['events'][0]['target'],'[external-or-invalid]')
        self.assertNotIn('secret',json.dumps(d.snapshot()))

@unittest.skipUnless(os.environ.get("MARIANOS_OFFLINE_BROWSER_TESTS") == "1", "Opt-in requires local Playwright and Chromium; all requests intercepted")
class BrowserDiagnosticIntegrationTests(unittest.TestCase):
    def test_real_chromium_events_with_intercepted_response_no_network(self):
        from playwright.sync_api import sync_playwright
        with sync_playwright() as runtime:
            browser=runtime.chromium.launch(headless=True)
            try:
                page=browser.new_page()
                page.route("**/*", lambda route: route.fulfill(status=200,content_type="text/html",body="<html>offline fixture</html>"))
                diagnostics=NavigationDiagnostics(page,browser.version)
                diagnostics.attach()
                page.goto("https://www.marianos.com/?token=secret",wait_until="domcontentloaded")
                diagnostics.detach()
                result=diagnostics.snapshot()
                self.assertEqual([e['event'] for e in result['events']],['request','response'])
                self.assertEqual(result['events'][1]['status'],200)
                self.assertNotIn('secret',json.dumps(result))
            finally:
                browser.close()

    def test_factory_attaches_before_setup_and_preserves_failure(self):
        from unittest.mock import patch
        from marianos_collector.browser_session import create_discovery_driver
        def setup(page,config,guard):
            page.route("**/*",lambda route: route.abort("failed"))
            page.goto("https://www.marianos.com/?token=secret",wait_until="domcontentloaded")
        with patch('marianos_collector.browser_session.prepare_store',side_effect=setup):
            with self.assertRaises(Exception) as caught:
                create_discovery_driver({},lambda *a:None,5)
        evidence=caught.exception.discovery_evidence
        result=evidence['navigation_diagnostics']
        self.assertEqual([e['event'] for e in result['events']],['request','requestfailed'])
        self.assertEqual(result['events'][-1]['error_code'],'net::ERR_FAILED')
        self.assertNotIn('secret',json.dumps(result))

    def test_setup_evidence_does_not_store_rendered_customer_text(self):
        from unittest.mock import patch
        from marianos_collector.browser_session import create_discovery_driver
        def setup(page,config,guard):
            page.set_content('<html><body>Customer secret@example.com</body></html>')
            raise RuntimeError('net::ERR_FAILED')
        with patch('marianos_collector.browser_session.prepare_store',side_effect=setup):
            with self.assertRaises(Exception) as caught:
                create_discovery_driver({},lambda *a:None,5)
        self.assertNotIn('secret@example.com',json.dumps(caught.exception.discovery_evidence))
