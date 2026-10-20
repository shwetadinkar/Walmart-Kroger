> **Update v0.4.0:** An official Walmart OPD snapshot-to-collector adapter is now included. See [`OPD_CLIENT_RUNBOOK.md`](OPD_CLIENT_RUNBOOK.md) for runnable client commands and unresolved acceptance limitations.

# Walmart official OPD API: smoke-test procedure

This project includes an **optional, read-only Walmart I/O OPD API probe**. It does not impersonate a browser, bypass access restrictions, modify Walmart data, or prove that the existing contest feed requirements can be fulfilled by Walmart's APIs.

## 1. Prerequisites

- Walmart I/O OPD partnership/API subscription approved for **this intended data use** (having a Walmart.com login is not sufficient).
- A Walmart I/O OPD `client_id` and `client_secret` for OAuth. Keep them in environment variables, outside GitHub; do not paste them in the chat or logs.
- Python 3.11+. The probe uses only the standard library.

Official documentation:

- [OPD introduction](https://www.walmart.io/docs/opd/stores/grocery-introduction) — private access/approval.
- [Store locator](https://walmart.io/docs/opd/quick-start-guide/catalog-store-service-locator) — OAuth and ZIP/store lookup.
- [Product catalog snapshot](https://www.walmart.io/docs/opd/recipe-register/catalog-product-snapshot) — feed metadata and catalog fields.
- [Walmart I/O API terms](https://walmart.io/termsandcondition) — permitted-use limitations.

The **Marketplace Sandbox** (`sandbox.walmartapis.com`) is intended for Marketplace seller integrations. Its simulated products do **not** validate actual local pickup prices or any of the 500 live records the contest requires.

## 2. Local non-network test (no credentials)

```bash
cd walmart_azure_collector
python tools/walmart_opd_smoke_test.py --store both --dry-run
```

Dry-run lists planned API endpoints and ZIP codes. It **does not contact Walmart or obtain product data**.

## 3. Authenticated store lookup (only after approval)

Set secrets in a secure terminal/session or managed secret store:

```bash
export WALMART_OPD_CLIENT_ID='YOUR_APPROVED_CLIENT_ID'
export WALMART_OPD_CLIENT_SECRET='YOUR_APPROVED_CLIENT_SECRET'
python tools/walmart_opd_smoke_test.py --store both
```

The probe:
1. Obtains an OAuth access token (not printed).
2. Sends a `POST` read-only store-locator request for ZIP `72712` and ZIP `77007` with `INSTORE_PICKUP` filter.
3. Checks whether expected store IDs `100` and `5959` occur as `fulfillmentStoreId` among the returned access points.
4. Prints counts and status, **not tokens**. If the service returns a nearby store but not the expected store, it returns `STORE_NOT_CONFIRMED`, not false success.

Optional (requests catalog **metadata** only, not actual catalog files):

```bash
python tools/walmart_opd_smoke_test.py --store both --catalog
```

This includes a GET to `/affil/catalog-api/v2/product/feeds/items`. The response may contain temporary signed URLs; the probe **does not print or download them**.

## 4. How to interpret outcomes

| Outcome | Meaning |
| --- | --- |
| `DRY_RUN` | Code and request plan only; no API connectivity verified. |
| OAuth returns 401/403 | Missing/invalid credentials, restricted subscription, or access issue. |
| OAuth success | Authentication works; no claim about rights or store prices. |
| `STORE_CONFIRMED` | The requested pickup store is listed for the supplied ZIP. |
| `STORE_NOT_CONFIRMED` | Store was not found in returned accesspoints; investigate before trusting any local prices. |
| Catalog metadata success | Feed-list permission works; does not prove per-store pricing. |

## 5. What is still required

Even a successful OPD store-locator test is not enough to fulfill the contest. Confirm that API access permits the intended data aggregation/use, that price-and-availability endpoints return **correct prices for store 100 and 5959**, and that category traversal, displayed PPM, UPC, volume deals, digital coupons, actual seller and pickup fulfillment can be verified. Feed snapshots are generic catalog data; do not treat snapshot prices as store-specific prices.

Do **not** submit dry-run, sandbox, or fabricated fixtures as real Walmart records.
