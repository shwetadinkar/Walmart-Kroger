> **Update v0.4.0:** An official Walmart OPD snapshot-to-collector adapter is now included. See [`OPD_CLIENT_RUNBOOK.md`](OPD_CLIENT_RUNBOOK.md) for runnable client commands and unresolved acceptance limitations.

# Requirements coverage and gaps

Mapped from the uploaded five-page `Shared_Scraper_Technical_Requirements.docx` and `Walmart_Category_URLs.csv`. This page reports implementation status, not contest certification.

**Written 20 October 2026 and partly superseded.** Rows marked *(updated 1 Nov)*
were rechecked against the repository on 1 November; the rest still describe the
20 October state and may understate what now exists. The row on real records said
"synthetic fixtures only" for eight days after 615 real provider records for store
100 were already in `submission/2026-10-24/`. That was wrong and is corrected
below.

| Source requirement | Implementation status | Evidence or remaining work |
|---|---|---|
| Existing Azure environment, twice weekly per location | **Deployment template only** | `azure/deploy_jobs.sh`; must run/observe in client's Azure |
| Configurable stores, no code copies | Implemented | `config/stores.json`, CLI `--store` / `WALMART_STORE_ID` |
| Secrets outside source; logs; no overlap | Implemented (Azure integration untested) | secrets via environment; logs; Azure 60-s renewable lease |
| All 11 categories, all subcategories, pagination, lazy/dynamic content | Enumeration logic implemented; **live completeness unproven** | `config/categories.csv` + provider `children`, `next_cursor`, `subcategories_complete`; approved provider must actually enumerate lazy/dynamic products |
| Exclude Food Shop All Foods/Recipes, Pets Farm Animals | Implemented | `config.py`, tests |
| Correct location and pickup/store fulfillment | Validated against provider metadata; **physical accuracy unproven** | Page + row location checks; eligible fulfillment filters; screenshot/evidence URL demanded |
| 22 fields in exact order; all strings; blank GUPC and unit_price | Implemented | `schema.py`, schema tests |
| Original UPC, image/product URLs; no inferred PPM *(updated 1 Nov)* | Implemented; `ppm` now populated on 540 of 615 | No rate is derived from price and size. The provider confirmed in writing that its `unit_price` and `unit` are read from the page text; the two are joined, labelled composed rather than captured, and the cent-versus-dollar notation difference is disclosed. See `submission/2026-10-31-provider-fields/NOTE.md` |
| Private labels, no approximate-weight products, no duplicates | Implemented, some real-world matching limitations | Configured known private brands; approx wording filter; product_id/UPC/URL dedup |
| Regular, sale, volume and digital deals separately | Implemented as classification/validation of provider inputs; **real correctness unproven** | `schema.py` never computes offer prices; provider must supply complete offer conditions and clipping evidence |
| Walmart Cash should not become instant coupon | Basic misclassification guard | `schema.py` blocks cashback descriptions in digital coupon fields; other nuanced real cases need tests |
| Detect access challenges, HTTP errors, malformed pages and low yields | Implemented in provider/data validator | retries transient 429/5xx; fail closed on 401/403; errors/zero counts; prior yield floor |
| Real durable resume, preserve latest good release | Implemented | page staging + remote checkpoint, pointer commit last; interruption tests |
| >=500 REAL records *(updated 1 Nov)* | **Met for the count** | 615 real records from the authorized provider for store 100, ZIP 72712, in `submission/2026-10-24/` and `submission/2026-10-31-provider-fields/`. Not synthetic |
| Fresh observed run in store 100's own context *(updated 1 Nov)* | **Not completed** | No page has been observed in store 100's context. Walmart refuses the location change to 72712 from this location, by automation and by hand; see `reports/2026-11-01-store100-notation-probe/REPORT.md` |
| Full source, operating docs and walkthrough | Source and docs included; walkthrough remains | user should record real Azure demonstration after acceptance |

## Product data caveats

The installed pipeline is purposely fail-closed. A source claiming incomplete category discovery, mismatched store context or missing independent evidence will not publish live data. The code cannot independently prove a third-party feed is honest. The 500-record count is a necessary but insufficient requirement: actual random record and coverage audits remain essential.
