# What this data does not establish

All figures here are recomputed from `raw_index.json` and `data/` by the builder.

## Complete category discovery

Term-filtered search cannot attest complete category discovery. The public Products API
has no category enumeration: `/products` requires a search term. A product no term
matched is absent, and nothing here measures how many such products exist. 301 terms
were run. The counts are what those terms returned, not what the store stocks.

## Products per term

**69 terms reached Kroger's limit.** `filter.start` is a skip count that Kroger refuses above
250, so a term yields at most 300 products. These terms report more than that, so their
results are truncated by Kroger's API, and no request can reach the rest. 15 terms across the
run report exactly 1,000, which looks like a ceiling on the figure rather than a count.

`Bakery||bread`, `Bakery||cake`, `Bakery||pie`, `Beauty||face cream`, `Beauty||makeup`, `Beer Wine Liquor||beer`, `Beer Wine Liquor||red wine`, `Beer Wine Liquor||white wine`, `Beer Wine Liquor||wine`, `Beverages||drink mix`, `Beverages||juice`, `Beverages||seltzer`, `Beverages||soda`, `Breakfast||cereal`, `Breakfast||granola`, `Candy||candy`, `Candy||caramel`, `Candy||chocolate`, `Candy||gum`, `Candy||gummy`, `Candy||mints`, `Coffee||coffee`, `Dairy||butter`, `Dairy||cheese`, `Dairy||eggs`, `Dairy||milk`, `Dairy||yogurt`, `Frozen||frozen chicken`, `Frozen||frozen dinner`, `Frozen||frozen vegetables`, `Frozen||ice cream`, `Grocery||beans`, `Grocery||broth`, `Grocery||canned soup`, `Grocery||crackers`, `Grocery||jelly`, `Grocery||pasta`, `Grocery||pasta sauce`, `Grocery||peanut butter`, `Grocery||rice`, `Grocery||salsa`, `Grocery||spices`, `Grocery||sugar`, `Hardware Home Improvement||tool`, `Health||supplements`, `Health||vitamins`, `Household||bleach`, `Kitchen Dining||baking pan`, `Kitchen Dining||food storage`, `Meat||ham`, `Meat||roast`, `Meat||sausage`, `Meat||steak`, `Natural Organic||gluten free`, `Natural Organic||organic eggs`, `Natural Organic||organic snacks`, `Natural Organic||plant based`, `Personal Care||shampoo`, `Produce||apple`, `Produce||broccoli`, `Produce||lemon`, `Produce||lime`, `Produce||orange`, `Produce||pepper`, `Produce||potato`, `Produce||strawberry`, `Produce||tomato`, `School Office||markers`, `Seafood||clams`

**A further 6 terms received fewer products than Kroger reported, below the limit.**
The sweep continues past a short page until it has covered the total or a page comes
back empty, so these are not stopped early. Kroger's total and what it serves disagree, and
nothing here says which is right. Of the 221 terms with results below the limit, 215 of 221 received at
least the reported total.

| Term | Reported total | Received |
|---|---:|---:|
| `Natural Organic||organic produce` | 154 | 152 |
| `Personal Care||shaving cream` | 62 | 61 |
| `Produce||banana` | 152 | 151 |
| `Produce||cucumber` | 41 | 40 |
| `Produce||lettuce` | 115 | 114 |
| `Produce||melon` | 21 | 20 |

**An earlier run skipped each term's first result.** `data/kroger-start-semantics-2026-10-31.json`
records eight live requests: no parameter and 0 return the same first page, 1 drops the
first product, 2 the first two, 250 works and 251 is refused. This run starts at 0.

Kroger's documentation also says the order of term results can change between requests,
so pages of one term are not guaranteed a stable partition of its results.

## The five empty roots

| Root | Why it is empty |
|---|---|
| Seafood | Kroger files it under the single label `Meat & Seafood`, which maps to Meat. Seafood: 266 products were found by its terms, assigned to Meat 136, Grocery 89, Deli 18, Pet Supplies 7. It cannot be separated from the 987 records carrying that label |
| Coupons | Not a product category. Coupons: 4 products were found by its terms, all of which are ordinary groceries |
| Coffee | No Kroger label reads Coffee. Coffee: 799 products were found by its terms, assigned to Beverages 665, Dairy 58, Natural Organic 57, Kitchen Dining 8 |
| Batteries | No Kroger label exists for it. Batteries: 64 products were found by its terms, assigned to Household 55, Hardware Home Improvement 8, Personal Care 1 |
| Light Bulbs | No Kroger label exists for it. Light Bulbs: 129 products were found by its terms, assigned to Household 100, (no root) 12, Hardware Home Improvement 10, Candy 3 |

The 42 labels Kroger returned are the whole of what the map can use, and a
search term is not evidence of a category. So these roots being empty does not mean
the store lacks these products: they are in the data under other roots, and a zero here
measures the label, not the shelf. Equally, a count on a populated root measures Kroger's
label and is not the retailer's site category.

## Records not seen in this run

0 records are carried forward. The run was given the earlier run at this store as its
previous run, and every product in that run was returned again, so 26,166 rows were observed in this run.
Compared with that run, 1,483 records are added and none lost, and no shared record differs in any of the
22 fields, including price. The two runs were about seven hours apart on one day, so this is not evidence
of price stability. 630 shared products differ in the raw fulfilment or inventory fields, which the 22 fields do not carry.
The comparison cannot separate the paging correction from assortment change at the store.

## Products sharing a UPC

0 UPCs are shared by more than one product in this run. If one were, both rows would stay and
`data/run_report.json` would list it.

## Records with no root

187 records have a blank `category`, because their labels have no map entry.
The run report's `records_with_unmapped_category` reads 255: that counts
placements, and a product found by two terms is counted twice. Both figures are correct.

## Displayed values

`ppm`, `volume_deals_description`, `volume_deals_price`, `digital_deals_description` and
`digital_deals_price` are blank on all 26,166 rows, because the public tier carries none of
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
- 608 of the rows have no qualifying pickup offer. They stay in the data, and
  `data/pickup_context.json` records why.
- `store_brand` is rule-based and its open brand classifications have not been reviewed.
- This is one run. It does not show repeatability, price stability or change over time.
- The store was verified once, before collection. Requests name the location throughout,
  but it was not re-verified during the run.
