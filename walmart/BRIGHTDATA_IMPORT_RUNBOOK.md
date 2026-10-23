# Bright Data snapshot importer — Walmart evidence-trial v0.6.0

This **offline importer** processes Walmart ZIP-code scraper JSON exports already obtained by the operator. It **never calls Walmart, Bright Data, or Azure**, and is **not proof of complete live coverage**. Do not put raw snapshots, generated exports, API tokens, or evidence packages in the public GitHub repository. Use only data you have rights to collect, retain, and share.

## Run on saved JSON snapshot files

Requires Python 3.11+, standard library only. From this repository's `walmart/` folder:

```bash
python tools/import_brightdata.py \
  /private/brightdata/snapshot1.json /private/brightdata/snapshot2.json \
  --store-id 100 --zipcode 72712 --output /private/walmart-evidence
```

Outputs an **immutable** `trials/100/<timestamp>_<id>/` directory with:

- `data_22_fields.json`: exact 22 ordered string fields; blank `gupc`/`unit_price`; retains verified store-assortment candidates including pickup-unavailable products
- `history.json`: a history of source-observed records; feed it to the **next run** with `--history /private/.../history.json`. Missing products are retained without claiming they are newly out of stock
- `evidence.json`: field provenance, source response file/row hash, source observation timestamp, online-price candidates, carried-field dates, provider PPM candidates, unavailable status
- `rejected.json`: failures with source filename and zero-based record number; no fabricated success records
- `manifest.json`: full counts, error classifications, SHA-256 hashes of inputs and explicit acceptance limitations

**Do not import this trial export as a complete production release.** It does not update the original collector's `published/100/latest.json`. Incomplete sample collection must never replace a validated full crawl.

For the next set of snapshots:

```bash
python tools/import_brightdata.py /private/brightdata/new*.json \
  --history /private/walmart-evidence/trials/100/<prior_run>/history.json \
  --output /private/walmart-evidence
```

All historical store assortment products are retained regardless of whether the current partial trial re-observed them. A currently out-of-stock product has its current pickup-availability status recorded in `evidence.json`. The original `crawl_date` is always the date of the original source response, **not a later fabricated crawl date**. Prior confirmed field values are copied forward only if present in an explicit prior history; their original observation timestamps remain in the evidence sidecar. Missing source timestamps mean blank `crawl_date`.

### Mapping and strictness

- Requires `store_id`, `pickup_store_id`, `retailer_store_id`, `zip_code`, `pickup_zipcode` to match the configured store and ZIP, plus Walmart.com seller, category membership in the supplied 11 roots, pickup location and a recognized pickup in-stock/out-of-stock status. Other records go to `rejected.json`.
- A source-record matching Store #100 is an **assortment candidate**, not a verified store-price or fulfillment proof; store-specific price spot-checks remain required.
- UPC is copied verbatim if present. Packaging/net-content statement is preferred to dimension fields. Reject approximate-weight wording. Do not invent price per measure, sizes, UPC or offer terms.
- Provider `final_price` usually means **price when purchased online**, not a documented pickup-store price. It stays in `evidence.json` rather than falsely populating `regular_price` or `sale_price`.
- Provider numeric `unit_price` is **not automatically directly displayed PPM**; it stays in `evidence.json` and `ppm` is blank until independently verified.
- Provider generic `promotion_fulltext` such as *Price when purchased online* does not prove a complete volume or digital offer; deal fields remain blank pending original terms.
- Product identity uses the Walmart item ID plus its matching product URL. Existing history should be kept privately and never deleted.

### Observed initial snapshot results (eight uploaded files)

| Metric | Value |
|---|---:|
| All raw response rows | 214 |
| Source errors | 39 (20 CAPTCHA blocks, 18 dead pages, 1 parse error) |
| Other-store product rows | 86 |
| Outside the 11 requested category roots | 2 |
| Walmart Store #100 assortment candidates | **87** |
| Candidates indicating pickup in stock | 71 |
| Candidates indicating pickup unavailable | 16 |
| Confirmed *pickup-specific* local prices in these raw responses | **0** |
| Directly observed PPM and complete coupon terms confirmed | **0** |

These are **offline normalization observations**, not the client's 500-product or full-category acceptance demonstration. There has been no live interruption/resume or Azure run. Any original data rights or provider billing questions remain separate.