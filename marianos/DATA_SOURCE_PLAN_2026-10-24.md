# Mariano's scraper contest — source acquisition and live test plan

**Prepared:** 24 October 2026. **Status:** no genuine Mariano's 500-product source collection or production Azure run yet. Existing `marianos/` v0.2.1 code is an offline-tested framework; **33 local preflight tests passed** on 24 October, including **synthetic** crash/restart and two-store simulations. Do not submit those mock records.

## Proposed source strategy — not the Walmart scraper

### A. Primary location / price diagnostic: official Kroger Public API

Mariano's is in the Kroger banner family. The documented Kroger Public API supports:
- Store/location lookup under `/v1/locations`. Verify the banner, street address and returned **actual locationId**, rather than using placeholder IDs.
- Product queries under `/v1/products` with `filter.locationId`, which can return **store-specific price and availability where available**.
- Product-detail queries by actual UPC/product ID with `filter.locationId`.
- OAuth client credentials supplied securely by an authorized account.

**Two client-targeted stores (official store directory):**
1. **Mariano's Lakeshore East**, 333 E Benton Pl, Chicago, IL 60601 (store webpage path `/531/00503`; the webpage's chain/store code is **NOT independently verified as the Kroger API locationId**).
2. **Mariano's West Loop**, 40 S Halsted St, Chicago, IL 60661 (webpage path `/531/00508`; likewise verify actual API locationId before use).

**Official sources**: https://www.postman.com/kroger/the-kroger-co-s-public-workspace/documentation/ki6utqb/kroger-public-apis and https://www.marianos.com/stores/grocery/il/chicago

Run existing diagnostic from `marianos/` with an authorized application:

```bash
# Do not place real values in source control
export KROGER_CLIENT_ID='(secure private environment)'
export KROGER_CLIENT_SECRET='(secure private environment)'
python -m marianos_collector kroger-locations --zipcode 60601 --address-contains Benton
python -m marianos_collector kroger-locations --zipcode 60661 --address-contains Halsted
python -m marianos_collector kroger-trial --location-id VERIFIED_KROGER_LOCATION_ID --terms milk,bread
```

Use the exact store IDs returned by the official API. Confirm actual product URLs, prices, availability and prices across both locations.

**Major gap:** keyword search in the Public API **does not prove enumeration of the client's full 28 category roots, every descendant page, coupons or retailer-displayed PPM**. A Kroger Product API `promo` field is not proof of a clipped digital coupon.

### B. Category discovery / extra retailer pages: licensed provider with verified Mariano's location

Bright Data currently advertises a **Kroger Scraper API** (`https://brightdata.com/products/web-scraper/kroger`), on-demand API/no-code collection and a free-tier advertisement. **It is not yet demonstrated** that its generic Kroger scraper can collect the full Mariano's `marianos.com` category trees for both selected locations, correctly bind their pickup selection and capture coupon/quantity terms. Do not substitute generic `kroger.com` output for verified Mariano's records.

Bright Data separately advertises a Kroger dataset (`https://brightdata.com/products/datasets/kroger`), whose listed minimum order starts at $250. **Do not order that dataset without specific budget approval**; the existing project has no authorized paid purchase.

Other retailer-data providers may claim to support Mariano's, but none has been integrated or authenticated. A vendor must demonstrate: category pagination to exhaustion, proof of exact selected store, individual product UPC and direct source URL, store-pickup price, displayed PPM, authentic clipped/volume promotions and timestamped raw evidence.

### C. First real live acceptance experiment (small/no-charge before scale)

1. Obtain permission and client-owned OAuth credentials for Kroger Public API. Confirm the 2 real `locationId` values from `/locations` and match exact addresses.
2. Query 5–10 products at both stores; cross-check against the retailers' selected-store PDP/site display. **Do not store credentials or large raw data publicly.**
3. Check Bright Data dashboard access, current free quota and whether its **Kroger** scraper actually accepts `marianos.com` URLs and a store context. If not, **do not** bulk-run it.
4. Choose category-complete source; demonstrate 1 category plus descendants and all pages from the client's 28-root CSV, with only source-observed coupon/PPM fields populated.
5. Test a small 20–50 product trial per verified store. Preserve source responses, failures, timestamps and seller/fulfillment identity.
6. Extend to >500 genuine distinct qualifying products **per store if required by the client's exact brief** (read the original requirement, do not infer from Walmart's single-store threshold). Validate all 28 roots, full path mapping and both stores separately.
7. Observe a real interrupted/restarted data job, then deploy Azure Container Apps + Azure Blob in a client-approved subscription, record actual job execution logs, and only then enable schedule.

**Budget guard:** no new vendor or Azure spend without explicit approval. Do not infer the account's current free quota from public pricing pages.

## Code already available

- `marianos_collector/kroger.py`: official API OAuth, locations, and product diagnostics.
- `marianos_collector/runner.py`: checkpointed authorized-provider category-paging architecture.
- `marianos_collector/schema.py`: 22-field output, fail-closed price/PPM/deal rules.
- `tools/live_access_preflight.py`: safeguards for live source access.
- `tools/submission_gate.py`: blocks acceptance claims without live evidence.
- `azure/`: offline-prepared Azure job setup, not live deployed.
- `CLIENT_LIVE_TEST_STEPS.md`, `ORGANIZER_ACCESS_REQUEST.md`, and `SUBMISSION_STATUS.md` describe prerequisites and gaps.

**Current bottom line:** Use official **Kroger API** for verified Mariano's store IDs and reliable store-local product diagnostics first; use an **authorized full-category data source** only after it is proven to support those exact stores. The project is **not a Mariano's live-data submission**.
