# Mariano's contest #58 — Bright Data snapshot evidence
Date: 24 October 2026 (India). Source: authenticated Bright Data dashboard and downloaded files. Dataset: `gd_mhlod8vh2kwgoi9yw3` (Kroger.com — collect by URL).

## Decision
**Mariano's compatibility is NOT demonstrated. Do not scale to 500+ products.** Neither named snapshot input is a marianos.com URL. No new collection, rerun, cancellation, paid purchase, Azure execution or contest submission was performed in this audit.

## Actual observations
- Dashboard showed **3,561 / 5,000 free credits** and **$1.50 / 1k records**. These are observed dashboard values, not a promise of billing treatment or a verified monetary balance.
- Latest `sd_mvlk2zd6caphp8rda`: **Running**, one input, output record count/file size unavailable. Output download was disabled. Its input CSV was downloaded successfully. Latest JSON could not be downloaded because it was unavailable; no output is fabricated.
- Prior `sd_mvljzomw2fryebfuro`: **Ready**, one input, one output, 100% dashboard success, 8 seconds, approximately 7.45 KB. Actual JSON and input CSV downloaded.
- **Both input CSVs are byte-identical**: URL `https://www.kroger.com/p/green-onions/0000000004068?fulfillment=PICKUP`, empty `zip_code`. The latest snapshot is therefore not evidence of a Mariano's URL test.

## Prior JSON field evidence
| Question | Observed source values | Assessment |
| --- | --- | --- |
| Retailer | rootdomain=kroger.com; store_name=KROGER; seller_name=Kroger; title ends Kroger | Kroger, not verified Mariano's |
| Store / ZIP | store_id=03400017; input.zip_code empty; no verified store address/ZIP | Not tied to either intended Mariano's store |
| Product | Green Onions, 1 each | Genuine provider result; not a Mariano's acceptance record |
| Local price | price=0.69; list_price=0.69; currency=USD | Returned price, not independently verified at a target Mariano's store |
| UPC | upc=0000000004068; sku and gtin same | Preserve leading zeros; retailer UPC cross-check pending |
| Displayed PPM | price_by_unit=null; price_per_unit=null | Missing; do not calculate or invent |
| Promotion | is_promo=false; sale_price=null; skus_coupons fields null | No populated promotion in this record; does not establish general coupon coverage |

A 100% scraper success rate means the provider returned a record, not that Mariano's/store/price/contest requirements passed.

## Evidence integrity and privacy
Original files retained locally; raw JSON includes customer review text and is deliberately not committed. Account logs containing account identifiers, email and IP are not committed. No API key was needed or published.

SHA-256:
- Prior raw JSON: `4C96C82E3E62BEDABB937B4B68CC9489A69A4CB57B3CDED4643217D12BE83C69`
- Prior input CSV: `8705A65BB6A649BE16905BC4F33610B8A85F41CA3BCFD4D8802511ED44F197D4`
- Latest input CSV: `8705A65BB6A649BE16905BC4F33610B8A85F41CA3BCFD4D8802511ED44F197D4`

Repository baseline inspected: `a7968e3c81f8424a93bd94da0bedd4228f8aeb24`. Only this evidence document is added under marianos/. Walmart baseline tree: `b694f59ba4bfb08cd5e39d60f06b96d394fd9df9`.

## Actionable next steps and bounded collection plan
1. Obtain an actual marianos.com PDP compatibility result from this provider, with a specified target ZIP and returned proof of the exact Mariano's banner/store/address. URL acceptance alone is insufficient: reject silent normalization to generic Kroger or an unrelated default store.
2. Verify Lakeshore East (333 E Benton Pl, 60601) or West Loop (40 S Halsted St, 60661) against authoritative store evidence; website chain/store codes must not be assumed to be API location IDs.
3. Only after that compatibility gate passes, run **one batch of 5 distinct PDP URLs**, one output per input, no discovery/category jobs, automatic retries, reruns or scheduled calls. Maximum 5 new product records in that batch; no expansion to 10 without inspecting results. Confirm the dashboard still applies existing credits before launching; stop if it requests purchase/top-up or changes charging terms.
4. Preserve input, raw response, snapshot ID, timestamp and credit observations privately. Compare each result with the selected-store retailer page: product/UPC, store/ZIP, pickup price, displayed PPM and all shown promotion conditions. Missing evidence stays null/unverified.
5. If marianos.com is rejected, rewritten to Kroger or lacks store context, stop and request explicit Mariano's support or use an authorized source that proves it. Do not spend credits repeatedly probing the same mismatch.
6. A later 500+ submission remains gated on genuine qualifying products, category/subcategory/pagination coverage, verified target stores, 22-field validation and observed operational evidence. Existing synthetic tests are not live acceptance proof.

The requested 5–10-record collection was **not launched**, because the user's prerequisite (“if source is valid”) was not met. This audit establishes neither support nor non-support for marianos.com; it establishes that the two supplied snapshots do not test that question.
