> **Update v0.4.0:** An official Walmart OPD snapshot-to-collector adapter is now included. See [`OPD_CLIENT_RUNBOOK.md`](OPD_CLIENT_RUNBOOK.md) for runnable client commands and unresolved acceptance limitations.

# Requirements coverage and gaps

Mapped from the uploaded five-page `Shared_Scraper_Technical_Requirements.docx` and `Walmart_Category_URLs.csv`. This page reports implementation status, not contest certification.

| Source requirement | Implementation status | Evidence or remaining work |
|---|---|---|
| Existing Azure environment, twice weekly per location | **Deployment template only** | `azure/deploy_jobs.sh`; must run/observe in client's Azure |
| Configurable stores, no code copies | Implemented | `config/stores.json`, CLI `--store` / `WALMART_STORE_ID` |
| Secrets outside source; logs; no overlap | Implemented (Azure integration untested) | secrets via environment; logs; Azure 60-s renewable lease |
| All 11 categories, all subcategories, pagination, lazy/dynamic content | Enumeration logic implemented; **live completeness unproven** | `config/categories.csv` + provider `children`, `next_cursor`, `subcategories_complete`; approved provider must actually enumerate lazy/dynamic products |
| Exclude Food Shop All Foods/Recipes, Pets Farm Animals | Implemented | `config.py`, tests |
| Correct location and pickup/store fulfillment | Validated against provider metadata; **physical accuracy unproven** | Page + row location checks; eligible fulfillment filters; screenshot/evidence URL demanded |
| 22 fields in exact order; all strings; blank GUPC and unit_price | Implemented | `schema.py`, schema tests |
| Original UPC, image/product URLs; no inferred PPM | Implemented as data-preservation rule | Values passed from authorized feed unchanged; sample fixtures only |
| Private labels, no approximate-weight products, no duplicates | Implemented, some real-world matching limitations | Configured known private brands; approx wording filter; product_id/UPC/URL dedup |
| Regular, sale, volume and digital deals separately | Implemented as classification/validation of provider inputs; **real correctness unproven** | `schema.py` never computes offer prices; provider must supply complete offer conditions and clipping evidence |
| Walmart Cash should not become instant coupon | Basic misclassification guard | `schema.py` blocks cashback descriptions in digital coupon fields; other nuanced real cases need tests |
| Detect access challenges, HTTP errors, malformed pages and low yields | Implemented in provider/data validator | retries transient 429/5xx; fail closed on 401/403; errors/zero counts; prior yield floor |
| Real durable resume, preserve latest good release | Implemented | page staging + remote checkpoint, pointer commit last; interruption tests |
| >=500 REAL records and fresh observed run | **Not completed** | synthetic fixtures only; must connect authorized feed, run, audit |
| Full source, operating docs and walkthrough | Source and docs included; walkthrough remains | user should record real Azure demonstration after acceptance |

## Product data caveats

The installed pipeline is purposely fail-closed. A source claiming incomplete category discovery, mismatched store context or missing independent evidence will not publish live data. The code cannot independently prove a third-party feed is honest. The 500-record count is a necessary but insufficient requirement: actual random record and coverage audits remain essential.
