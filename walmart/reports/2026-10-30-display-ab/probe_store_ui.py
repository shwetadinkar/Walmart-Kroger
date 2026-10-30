"""Fresh session. Reach store 100 the way a visitor would: its own public store
page, then the product. No parameters, no account, no forms, no cart."""
import json, re
from playwright.sync_api import sync_playwright

STEPS = [
    ("1_store_page",   "https://www.walmart.com/store/100"),
    ("2_product_after","https://www.walmart.com/ip/938273658"),
]

def snap(pg, label):
    pg.wait_for_timeout(3500)
    body = pg.inner_text("body") or ""
    return {
        "label": label, "url": pg.url[:120],
        "blocked": "/blocked" in pg.url,
        "title": (pg.title() or "")[:90],
        "prices": re.findall(r"\$\d+\.\d{2}", body)[:5],
        "ppm": re.findall(r"\d+\.?\d*\s*[¢c]/\s*(?:oz|fl oz|lb|ct|ea)", body, re.I)[:3],
        "store_mentions": sorted(set(re.findall(
            r"(?:Bentonville|Sacramento|Supercenter)", body, re.I)))[:5],
        "zips": sorted(set(re.findall(r"\b7271\d\b|\b958\d\d\b", body)))[:5],
        "product_links": pg.evaluate("() => document.querySelectorAll('a[href*=\"/ip/\"]').length"),
    }

out = []
with sync_playwright() as p:
    b = p.chromium.launch(headless=False)
    pg = b.new_context().new_page()          # fresh, unpoisoned session
    for label, url in STEPS:
        try:
            pg.goto(url, timeout=45000, wait_until="domcontentloaded")
            out.append(snap(pg, label))
        except Exception as e:
            out.append({"label": label, "error": f"{type(e).__name__}: {e}"[:150]})
    b.close()
print(json.dumps(out, indent=2))
