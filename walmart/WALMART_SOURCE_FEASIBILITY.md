# Walmart — source feasibility and operating-cost gate (22 October 2026)

**Status:** Candidate services researched. We have **no** Bright Data/Walmart account or key, have executed **zero paid or authenticated live source requests**, and have not obtained genuine 500-record evidence. The independent Mariano's project remains untouched.

## Recommended first trial: Bright Data Walmart Scraper API (candidate, not yet selected)

- Provider: https://brightdata.com/products/web-scraper/walmart
- Advertised free tier: **5,000 records/month**, no credit card required, subject to provider eligibility. Pay-as-you-go advertisement: **USD $1.50 per 1,000 successfully delivered records**.
- Walmart-specific products, category discovery and ZIP/store-ID collection are offered. Reference: https://brightdata.com/blog/how-tos/guide-to-scraping-walmart
- Published dataset IDs are only starting points: products `gd_l95fol7l1ru6rlo116`; ZIP-product example `gd_m693oc1r1gebnayxq`. Confirm exact input and response schemas in the account; do not invent mappings.
- **Critical rights check:** https://www.walmart.com/help/article/walmart-com-terms-of-use/3b75080af40340d6bbd596f116fae5a0/ restricts automated collection without Walmart's express written consent. A data-provider product or advertised free tier does not itself establish that the buyer has the data rights required for their intended use. Obtain written clarity on collection/storage/transfer rights before operating.
- Alternative: https://oxylabs.io/products/scraper-api/ecommerce/walmarts advertises a free trial of up to 2,000 results. Its store and promotion field coverage is likewise unverified.

## What we have versus need

| Dependency | Existing access | Minimum first test requirement | Production requirement |
| --- | --- | --- | --- |
| Python code, configuration and 45 offline tests | Yes, in this repository | No subscription | Same |
| Bright Data token / qualifying trial | **No** | Eligible trial plus confirmed permitted use, with auto-recharge off | An approved billed plan if data exceed the free quota |
| Source original response and cost logs | **No** | 10–20 real product responses, local store identity and source timestamps | All 11 roots, all permitted subcategories/pages, 2x weekly per store |
| Walmart OPD partner credentials | **No** | Not mandatory | Optional alternative only if granted and approved for this use |
| Client Azure access | **No** | Not needed for source field qualification | Container job, Blob Storage, Key Vault and logs, billed to client's own account |

## Step-by-step trial; no purchase without a separate decision

1. Confirm provider terms and right to collect/retain/transfer Walmart data. If a free account is not genuinely available with **$0 incremental billing**, stop and request the client's approval of a **specific capped paid pilot**.
2. Trial Walmart Supercenter #100 / ZIP 72712 on a small, representative permitted product set. A ZIP alone does not prove the selected pickup store: source responses must identify store **100**.
3. Preserve original dated source responses in **private storage, never public GitHub**. Inspect original product identity/pack size, UPC (not guessed GTIN), displayed PPM (not calculated), seller, pickup/in-store fulfillment, local price, unavailable assortment, volume-deal wording, and coupon clip requirements. Record raw response URLs or equivalent evidence IDs and acquisition timestamps.
4. Map provider-specific fields explicitly. Use `tools/source_feasibility_audit.py` with a real response and `config/source_mapping.template.json`; report the missing or mismatched source fields without inventing values.
5. Record actual **charged result count, request count, page/category count, elapsed time, retries, and vendor billable usage**. One API call may return many chargeable product records. Do not conflate requests and delivered records.
6. A 500-product live pilot should proceed only after store-specific provenance, pricing, field coverage and the data rights pass manual spot checks. A 500-record sample cannot by itself prove the complete 11-category production traversal.

### Audit a saved raw provider response; no network requests

```powershell
cd walmart
python tools/source_feasibility_audit.py --input private-source/walmart-raw.json --mapping private-source/mapping.json --source brightdata-walmart-zipcodes --store-id 100 --zipcode 72712 --output private-source/report.json
```

Copy the blank mapping template to `private-source/mapping.json` and fill paths only after inspecting the provider's response. Use `--requests-observed N` only for an **actually counted** number of API calls. Store raw data and reports outside the public repository.

## Costs: published price, not measured workload

Let `N` = **chargeable provider records for a complete store run, as measured**, `S` = number of stores, `R` = complete runs per month (typically 8–9 for twice weekly). An **uncapped PAYG estimate before any eligible free allowance** is:

`provider_cost_usd = N × S × R × 1.50 / 1000`

Illustrative scenario with **one store and eight runs/month**, not measured real Walmart usage:

| Chargeable records per full run | Per month | Published PAYG estimate |
| ---: | ---: | ---: |
| 500 | 4,000 | $6 |
| 5,000 | 40,000 | $60 |
| 20,000 | 160,000 | $240 |
| 100,000 | 800,000 | $1,200 |

Provider free allowance may reduce costs if the account is eligible; additional vendor calls for detail/verification could increase billable records. Real category/subcategory/page totals and Azure costs **cannot yet be quoted**. Do not promise costs for all required products before a complete live count.

**Initial test spend ceiling: USD $0** on a permitted free sample / eligible free trial with no auto-recharge. **No paid service is currently approved or purchased.** Any paid pilot requires a separately proposed budget, exact plan/permissions, and express buyer approval.

## Remaining acceptance gates

No genuine 500-product test; no original local price/fulfillment/coupon/PPM evidence; no verified category completeness or unavailable-product carry-forward/freshness history; no actual interruption recovery against live source; no observed Azure run. Current synthetic offline tests remain useful software tests, **not proof of live source coverage**.
