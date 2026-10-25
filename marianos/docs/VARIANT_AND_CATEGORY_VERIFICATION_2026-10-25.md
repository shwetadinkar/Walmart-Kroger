# Variant selection and 55-product category verification

## Concrete source behavior

Light Bulbs initially displayed 52 results while its hierarchy reported 55. Three omitted catalog identities were subsequently observed through ordinary price filters and variant controls: 0004667756535, 0004667756539 and 0004667756541. Together the observed root, child and price-filter links contain 55 distinct product identities.

A selected option does not always establish a selected product. When a size is unchosen, Mariano's can retain the prior UPC and price and show "This selection is unavailable. Please choose another option." Completing the option-and-size combination changes the product URL, UPC and price. Some fully selected combinations are genuinely unavailable. These two cases must remain distinct.

The collector now discards unfinished-selection evidence before price comparison, preserving the good API record. Fully resolved matching-SKU evidence explicitly showing pickup unavailable reaches availability quarantine. Direct enrichment refuses unavailable pickup. Supplied selection flags must be literal booleans, and a supplied primary-product text must contain exactly the expected UPC; a matching recommendation cannot substitute for the current product.

## Actual bounded collection

On 25 October 2026, 55 source-discovered product IDs were requested through the official Kroger product-details route, with locationId 53100508 on every product request. The run used 57 HTTP attempts against a ceiling of 60, including authentication and store verification. No provider credits or Azure job were used.

All 55 product pages were then read in the normal retailer browser, verifying each UPC and West Loop context. Observation interval: 05:56:36–05:59:54 UTC (11:26:36–11:29:54 IST). The maximum API/page time gap was under five minutes.

- 50 retained records: exact 22 ordered string fields, unique UPCs, ZIP 60661, verified pickup availability, matching regular/sale prices, and literal displayed PPM.
- 8 retained sale prices.
- 5 products quarantined because their pages said Pickup Out of Stock despite API pickup capability. Current stock and fulfillment capability are different facts.
- No source-derived price disagreements in this cohort.
- gupc and unit_price remain empty. No PPM or final offer price was calculated.
- Subcategories, store logo and unobserved promotion fields remain empty rather than inferred.

The exported URLs use the actual public pickup product-page URLs without API attribution strings. Original API responses, page captures, timestamps and hashes remain in the private evidence package.

## Acceptance boundary

The 55 observed identities now reconcile the displayed hierarchy total, but exhaustive traversal of every variant family has not been established. Earlier child-list discovery includes 24 October evidence; all 55 product/API pairs above were freshly observed on 25 October. This is a verified bounded category review export, not proof that all 28 roots were completely traversed or that an unattended browser collector is production-ready. `category_complete` and `submission_ready` remain false.

## Validation and preserved scope

126 tests and offline preflight passed locally. A fresh reviewer independently passed the 19 temporal-enrichment tests and found no remaining important issues in the changes. Synthetic tests are separate from live evidence. Walmart and all other root tree entries are unchanged. The 650-product baseline was not overwritten. Azure configuration, scheduled triggers, permissions and billing were not changed. The new code is for review; no additional Azure deployment or production scheduling is implied.
