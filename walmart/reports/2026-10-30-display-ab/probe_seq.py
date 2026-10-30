"""Is it the SECOND navigation that blocks, or the store page specifically?
Fresh session, three ordinary product pages in sequence. Nothing else."""
import json, re
from playwright.sync_api import sync_playwright
PRODUCTS = ["https://www.walmart.com/ip/938273658",
            "https://www.walmart.com/ip/10450114",
            "https://www.walmart.com/ip/10315615"]
out=[]
with sync_playwright() as p:
    b=p.chromium.launch(headless=False); pg=b.new_context().new_page()
    for i,u in enumerate(PRODUCTS,1):
        try:
            pg.goto(u, timeout=45000, wait_until="domcontentloaded"); pg.wait_for_timeout(3000)
            body=pg.inner_text("body") or ""
            out.append({"nav":i,"blocked":"/blocked" in pg.url,
                        "title":(pg.title() or "")[:70],
                        "prices":re.findall(r"\$\d+\.\d{2}",body)[:3],
                        "links":pg.evaluate("() => document.querySelectorAll('a[href*=\"/ip/\"]').length")})
        except Exception as e:
            out.append({"nav":i,"error":f"{type(e).__name__}: {e}"[:110]})
    b.close()
print(json.dumps(out,indent=2))
