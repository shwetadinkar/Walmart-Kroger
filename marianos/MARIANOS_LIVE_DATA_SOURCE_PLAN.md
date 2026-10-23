# Mariano's contest #58 — actual live-data source and acceptance plan

**Prepared:** 24 October 2026  
**State:** sourcing research only; **zero genuine Mariano's contest rows collected**, zero Azure live executions. Do not represent the current 560-row synthetic test as live product data.

## What store we must scrape

Mariano's is a Kroger grocery banner, but a generic `kroger.com` result or a result for another Kroger banner/store is **not** sufficient. Use the contest's assigned Mariano's address and official Kroger `locationId` obtained through the Kroger Locations API. Confirm ZIP, full address, brand and pickup/aisle fulfillment. The current repo's `DEMO-...` location IDs are **synthetic and must never be used live**.

## Candidate source A: Kroger's documented API (preferred location/price cross-check)

- Official public Products API supports authenticated product searches filtered by `filter.locationId`, plus paging with `filter.start` and `filter.limit`, and product detail lookups by ID/UPC.
- With an approved Kroger API application and an actual verified Mariano's location ID, use `marianos_collector/kroger.py` to check representative store-level products, UPC, regular/promo pricing and availability.
- **Not established:** exhaustive listing of the client's 28 specific `marianos.com` category roots/subcategories, valid product URL mapping, site-displayed PPM, and every clipped coupon, limit and volume-deal condition. The official Public Products API alone therefore does not satisfy the full collector's category-completeness contract.
- Kroger API docs: https://www.postman.com/kroger/the-kroger-co-s-public-workspace/documentation/ki6utqb/kroger-public-apis

## Candidate source B: Bright Data's Kroger Scraper API (requires a Mariano's feasibility test)

- Provider: https://brightdata.com/products/web-scraper/kroger — describes bulk product URL collection, JSON/CSV output and API-driven snapshots.
- **Critical unknown:** the advertised Kroger scraper is **not** proof it accepts `marianos.com` product/category URLs, resolves the selected Mariano's location, supplies pickup-specific prices, supports category discovery or provides clip/coupon and displayed-PPM evidence. Test this explicitly before spending money.
- Check the Bright Data account's *actual* dataset ID, supported input schema, permissions and remaining free allocation in the control panel. A sample `kroger.com` result with no location is only a product-reference source.
- If a private Bright Data Marriott/Mariano's-specific scraper or a licensed store/category feed is available, validate it against the 28-root contract and provider data-use rights before relying on it.

## Safe live feasibility gate before 500+ collection

1. Confirm the assigned Mariano's store(s) and live Kroger `locationId` using official location evidence; do not infer from ZIP alone.
2. Obtain authorized API/store-feed access, with secrets confined to the user's environment. Do not upload API tokens to public GitHub or chat.
3. Sample **one genuine item** from each of two distinct required category roots, and verify: exact store/ZIP, retailer identity, pickup fulfillment, canonical product URL, 22-field transformation, source timestamp, regular/sale price, displayed PPM when present, seller type and source detail for coupons/volume discounts. Preserve absence as blank.
4. Prove the provider can enumerate *all children and pages* of at least one root reliably. A product-page scraper alone cannot discover the whole category and coupon catalog.
5. Once source capability, usage rights and potential spend are approved, run a bounded 50-record trial. Merge with history, record exclusions and duplicates, confirm category map and validate evidence.
6. Scale to 500+ distinct **genuine Mariano's observations across all 28 roots** only after the small trial meets criteria; independent audit of store prices and coupons remains required.
7. Deploy in the client's **Azure Container Apps Jobs** environment with private Blob Storage, secrets, a manual fresh-run verification, interruption/resume tests and an approved twice-weekly schedule. No live Azure execution has been performed yet.

## What's already implemented

See [README.md](README.md), [SUBMISSION_STATUS.md](SUBMISSION_STATUS.md), [ORGANIZER_ACCESS_REQUEST.md](ORGANIZER_ACCESS_REQUEST.md), [CLIENT_LIVE_TEST_STEPS.md](CLIENT_LIVE_TEST_STEPS.md) and [azure/README.md](azure/README.md) for the existing offline-tested Python collector, provider interface, no-promotion-without-evidence acceptance gate, 28 category roots and dry-run Azure setup.

## Explicit unresolved dependencies

- Contest-specific Mariano's physical store(s), live Kroger `locationId` and location proof.
- Authorized Mariano's-compatible full-category data feed including pricing/promotion evidence and usage rights.
- Client's Azure subscription/resources and budget authorization.
- Genuine 500+ record proof, full category coverage, interruption recovery and live Azure logs.

**Do not change the Walmart #63 dataset, importer or submission while building Mariano's #58.**
