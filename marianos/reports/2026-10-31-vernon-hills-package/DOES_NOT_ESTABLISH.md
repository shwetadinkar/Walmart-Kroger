> **SUPERSEDED — added 1 November 2026.** This package describes the run made
> **before** the paging correction in commit `78f57dc`, and it is missing the
> 1,483 records that correction recovered. Its figure of 24,683 records is
> superseded by the 26,166 in `../2026-10-31-vernon-hills-package-rerun/`, which
> is the authoritative collection for this store and date. Nothing in this
> folder should be quoted. It is kept because the earlier run is part of the
> record, not because it is current.

# What this data does not establish

All figures here are recomputed from `raw_index.json` and `data/` by the builder.

## Complete category discovery

Term-filtered search cannot attest complete category discovery. The public Products API
has no category enumeration: `/products` requires a search term. A product no term
matched is absent, and nothing here measures how many such products exist. 301 terms
were run. The counts are what those terms returned, not what the store stocks.

## Products per term

**79 terms stopped at this run's limit**, each with 250 products returned. The limit
is this run's own: requests stopped at `filter.start=201`. Kroger refused
`filter.start=251` on an earlier run, and its OpenAPI gives the parameter a maximum of
250. Starts from 202 to 250 were not requested, so these terms are truncated by at
least what those starts would have returned. Kroger's reported total exceeds 250 on
all of them, and 15 terms across the run report exactly 1,000, which looks like a ceiling on the
figure rather than a count.

`Baby||baby food`, `Bakery||bread`, `Bakery||cake`, `Bakery||dinner rolls`, `Bakery||pie`, `Bakery||tortilla`, `Beauty||face cream`, `Beauty||makeup`, `Beer Wine Liquor||beer`, `Beer Wine Liquor||red wine`, `Beer Wine Liquor||white wine`, `Beer Wine Liquor||wine`, `Beverages||bottled water`, `Beverages||drink mix`, `Beverages||juice`, `Beverages||seltzer`, `Beverages||soda`, `Breakfast||cereal`, `Breakfast||granola`, `Candy||candy`, `Candy||caramel`, `Candy||chocolate`, `Candy||gum`, `Candy||gummy`, `Candy||mints`, `Coffee||coffee`, `Dairy||butter`, `Dairy||cheese`, `Dairy||eggs`, `Dairy||milk`, `Dairy||yogurt`, `Frozen||frozen chicken`, `Frozen||frozen dinner`, `Frozen||frozen pizza`, `Frozen||frozen vegetables`, `Frozen||ice cream`, `Grocery||beans`, `Grocery||broth`, `Grocery||canned soup`, `Grocery||crackers`, `Grocery||honey`, `Grocery||jelly`, `Grocery||pasta`, `Grocery||pasta sauce`, `Grocery||peanut butter`, `Grocery||rice`, `Grocery||salsa`, `Grocery||spices`, `Hardware Home Improvement||tool`, `Health||supplements`, `Health||vitamins`, `Household||bleach`, `Household||fabric softener`, `Kitchen Dining||baking pan`, `Kitchen Dining||food storage`, `Kitchen Dining||water bottle`, `Meat||ground beef`, `Meat||ham`, `Meat||roast`, `Meat||sausage`, `Meat||steak`, `Natural Organic||gluten free`, `Natural Organic||organic eggs`, `Natural Organic||organic snacks`, `Natural Organic||plant based`, `Personal Care||body wash`, `Personal Care||conditioner`, `Personal Care||deodorant`, `Personal Care||shampoo`, `Personal Care||soap`, `Produce||broccoli`, `Produce||lemon`, `Produce||lime`, `Produce||onion`, `Produce||orange`, `Produce||pepper`, `School Office||markers`, `Seafood||clams`, `Seafood||tuna`

**A further 11 terms ended short of Kroger's reported total without reaching the limit.**
The sweep ends a term on a page under 50, and these pages ran short with products
remaining. The run's own report did not list them; the sweep now does.

| Term | Reported total | Received |
|---|---:|---:|
| `Grocery||sugar` | 1,000 | 49 |
| `Natural Organic||organic produce` | 154 | 148 |
| `Personal Care||shaving cream` | 62 | 60 |
| `Produce||apple` | 309 | 47 |
| `Produce||banana` | 152 | 49 |
| `Produce||cucumber` | 41 | 39 |
| `Produce||lettuce` | 115 | 49 |
| `Produce||melon` | 21 | 19 |
| `Produce||potato` | 522 | 48 |
| `Produce||strawberry` | 697 | 49 |
| `Produce||tomato` | 391 | 49 |

**One product per term may be missing.** Kroger defines `filter.start` as the number of
products to skip, minimum 1. The sweep's first request sends 1. Of the
205 terms with results below the limit, 194 of 205 returned exactly one product fewer than the
reported total. That fits the first-ranked result of each term being skipped, though
another term may have returned it. No live request has tested this.

Kroger's documentation also says the order of term results can change between requests,
so pages of one term are not guaranteed a stable partition of its results.

## The five empty roots

| Root | Why it is empty |
|---|---|
| Seafood | Kroger files it under the single label `Meat & Seafood`, which maps to Meat. Seafood: 289 products were found by its terms, assigned to Meat 134, Grocery 90, Deli 39, Frozen 10. It cannot be separated from the 967 records carrying that label |
| Coupons | Not a product category. Coupons: 3 products were found by its terms, all of which are ordinary groceries |
| Coffee | No Kroger label reads Coffee. Coffee: 810 products were found by its terms, assigned to Beverages 675, Dairy 59, Natural Organic 57, Kitchen Dining 8 |
| Batteries | No Kroger label exists for it. Batteries: 61 products were found by its terms, assigned to Household 52, Hardware Home Improvement 7, Personal Care 1, (no root) 1 |
| Light Bulbs | No Kroger label exists for it. Light Bulbs: 129 products were found by its terms, assigned to Household 101, (no root) 11, Hardware Home Improvement 10, Candy 3 |

The 42 labels Kroger returned are the whole of what the map can use, and a
search term is not evidence of a category. So these roots being empty does not mean
the store lacks these products: they are in the data under other roots, and a zero here
measures the label, not the shelf. Equally, a count on a populated root measures Kroger's
label and is not the retailer's site category.

## Records with no root

178 records have a blank `category`, because their labels have no map entry.
The run report's `records_with_unmapped_category` reads 241: that counts
placements, and a product found by two terms is counted twice. Both figures are correct.

## Displayed values

`ppm`, `volume_deals_description`, `volume_deals_price`, `digital_deals_description` and
`digital_deals_price` are blank on all 24,683 rows, because the public tier carries none of
them. `regularPerUnitEstimate` is an estimate and was not used. The page read that would
supply them stopped on its first request on 31 October, with no page served, so how often
Vernon Hills displays any of them is unknown.

`sale_price` is the API's promo price. It is not evidence of how a deal is worded or
whether it needs a digital coupon.

## Prices and products

- Prices are what the API returned at the time of each capture, and were not compared
  with the website or the shelf.
- Requests carry `filter.fulfillment=ais,csp`, so a product Kroger holds for neither
  in-store nor curbside at this location was never returned.
- 587 of the rows have no qualifying pickup offer. They stay in the data, and
  `data/pickup_context.json` records why.
- `store_brand` is rule-based and its open brand classifications have not been reviewed.
- This is one run. It does not show repeatability, price stability or change over time.
- The store was verified once, before collection. Requests name the location throughout,
  but it was not re-verified during the run.
