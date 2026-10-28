"""Network-free image smoke: launch installed Chromium and render literal local HTML."""
import json
from importlib.metadata import version
from playwright.sync_api import sync_playwright

def main():
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True)
        try:
            page=browser.new_page()
            page.route('**/*',lambda route:route.abort())
            page.goto('about:blank')
            page.set_content('<main><h1>Marianos browser runtime smoke</h1></main>')
            assert page.get_by_role('heading',name='Marianos browser runtime smoke',exact=True).inner_text()=='Marianos browser runtime smoke'
            assert page.url=='about:blank'
        finally:browser.close()
    print(json.dumps({'browser_runtime_smoke_passed':True,'playwright_version':version('playwright'),
                      'retailer_requests':0,'azure_requests':0,'api_credentials_used':False,'live_source_acceptance':False}))

if __name__=='__main__':main()
