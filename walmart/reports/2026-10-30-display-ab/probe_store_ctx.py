"""Can a headed session be pinned to a specific Walmart store, and does the
price change when it is? Read-only: no account, no cart, no purchase."""
import json, re
from playwright.sync_api import sync_playwright

PRODUCT = "https://www.walmart.com/ip/938273658"
STORE_ID = "100"            # Bentonville AR, ZIP 72712 per the brief
ZIP = "72712"

def snap(pg, label):
    pg.wait_for_timeout(3500)
    body = pg.inner_text("body") or ""
    return {
        "label": label,
        "url": pg.url,
        "prices": re.findall(r"\$\d+\.\d{2}", body)[:6],
        "ppm": re.findall(r"\d+\.?\d*\s*[¢c]/\s*(?:oz|fl oz|lb|ct|ea)", body, re.I)[:4],
        # Anything that names a store or a fulfilment location
        "store_mentions": sorted(set(re.findall(
            r"(?:Bentonville|Supercenter|Sacramento|store\s*#?\s*\d{3,5}|Pickup at [^\n]{0,40})",
            body, re.I)))[:6],
        "zip_mentions": sorted(set(re.findall(r"\b\d{5}\b", body)))[:8],
        "has_pickup": "pickup" in body.lower(),
    }

out = []
with sync_playwright() as p:
    b = p.chromium.launch(headless=False)
    ctx = b.new_context()
    pg = ctx.new_page()

    pg.goto(PRODUCT, timeout=45000, wait_until="domcontentloaded")
    out.append(snap(pg, "1_default_no_store_set"))

    # Walmart has historically accepted a store hint on the URL. Try it and see
    # whether the page actually honours it, rather than assuming it does.
    for param in ("athStoreId", "storeId", "assortmentStoreId"):
        try:
            pg.goto(f"{PRODUCT}?{param}={STORE_ID}", timeout=45000, wait_until="domcontentloaded")
            out.append(snap(pg, f"2_param_{param}={STORE_ID}"))
        except Exception as e:
            out.append({"label": f"2_param_{param}", "error": f"{type(e).__name__}: {e}"[:160]})

    b.close()

print(json.dumps(out, indent=2))
