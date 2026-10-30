# Can a headed browser collect store-specific Walmart prices from a datacenter?

Measured 30 October 2026, from a datacenter address, headed Chromium under a
virtual display. Read-only throughout: no account, no sign-in, no cart, no
form submission, no purchase. No proxy, no retries, no challenge solving.

The short answer is no, and the reason is more specific and more useful than
the one this project has been giving.

## What a headed browser does get

One Walmart product page, from a fresh session, is served in full. Not a
shell: real product data.

- Product: Ol' Roy Complete Nutrition Chicken & Rice Dry Dog Food, 4 lb
- Price: **$3.47**
- Displayed price per measure: **86.8 ¢/lb**
- 68 links to product detail pages on the page
- "Add to cart" present

So the earlier statement that Walmart is refused from a datacenter address is
not accurate as written. Headless is refused. Headed is served.

## Why that does not make it a route

Three measurements, each reproducible.

**1. The price is not the store's price.** The default session resolves to a
Sacramento Supercenter, not store 100. The brief requires store 100's pickup
price at ZIP 72712. $3.47 and 86.8 ¢/lb belong to whatever store the session
defaulted to, and using them as store 100's figures would be wrong.

**2. Selecting a store by URL parameter is blocked immediately.** Each of
`athStoreId`, `storeId` and `assortmentStoreId` redirected to
`walmart.com/blocked?url=...`. Not a challenge page to solve; a block.

**3. The second navigation in a session is blocked.** This is the decisive
one. Fresh session, three ordinary product URLs in sequence, nothing else:

| Navigation | Result |
|---|---|
| 1st product page | Served. $3.47, 68 product links |
| 2nd product page | **"Robot or human?"**, 0 links |
| 3rd product page | **"Robot or human?"**, 0 links |

The store's own public page at `/store/100` loads fine and confirms
Bentonville, AR, serving 72712. Navigating from it to a product page is
blocked in the same way.

## What that means for collection

A collector needs thousands of sequential page loads. This address gets one
per fresh session. The page is not the obstacle; the sequence is.

Clearing that means a new identity for every page, which in practice means
rotating residential addresses. That is the thing this project has declined to
build, and the decision is unchanged. What has changed is the evidence for it:
the refusal is no longer asserted from a headless measurement, it is the
observed behaviour of the protection under exactly the access pattern a
collector would produce.

## What is still untested

This ran from a cloud container, not from Azure. Azure's address reputation
may be better or worse, and `tools/egress_region_probe.py --display-ab` will
answer that from inside Azure without any change.

Whether the site's own store-picker UI can pin a session to store 100 was not
tested, because the second navigation is blocked before a store could be
chosen and used. Pursuing it past that point would be working around the
protection rather than reading the site.

## Reproducing it

`probe_seq.py` is the decisive one: fresh session, three product pages, no
parameters. `probe_store_ctx.py` covers the URL-parameter attempts and
`probe_store_ui.py` the store-page route. All three are read-only.

Shweta
