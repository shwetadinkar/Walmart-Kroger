# Brief's proof items

From section 10 of the shared requirements. "Met" means the bytes in this package
show it, not that the item is accepted.

| Item | Result |
|---|---|
| 500 valid records from an assigned location | Met: 26,166 records at store 53100502 |
| Multiple required categories | Met: 23 of 28 roots populated, 5 empty; see `DOES_NOT_ESTABLISH.md` |
| Structured JSON | Met: `data/data_22_fields.json`, 22 string fields in order, no nulls |
| Runtime | Met: 1643.1 seconds, 998 requests, 2026-10-31T20:56:16 to 2026-10-31T21:23:32 UTC |
| Total and category counts | Met: below |
| Duplicate count | Met: 0 duplicate UPCs, 0 duplicate URLs. 17,089 repeat placements across terms were collapsed from 43,255 returned |
| Field-completeness results | Met: all 22 fields, below |
| PPM examples | **Not met.** No row has a `ppm`. The API carries only an estimate, which the brief forbids, and the page probe at this store read no page |
| Deal examples | **Not met.** No volume or digital wording exists in this data. 7,469 rows carry a `sale_price`, which is the API's promo price and not a deal description |
| Location proof | Met for the API: `data/store_verification.json` is Kroger's response for this store, and every row's store columns match it |
| Architecture | `R8_ARCHITECTURE_AND_SERVICES.md` |
| Operating costs | `R9_OPERATING_COST.md`; an estimate, with unpriced items stated |
| Evidence the scraper generated the data | `R10_EVIDENCE_OF_GENERATION.md` |

Not shown by this package, and needed for acceptance under section 10: a fresh observed
run, interruption recovery and repeat-run testing on this store, and Azure deployment of
this collection.

## Field completeness

| Field | Non-empty | Share |
|---|---:|---:|
| `zipcode` | 26,166 | 100.0% |
| `store_name` | 26,166 | 100.0% |
| `store_location` | 26,166 | 100.0% |
| `store_logo` | 0 | 0.0% |
| `store_brand` | 26,166 | 100.0% |
| `category` | 25,979 | 99.3% |
| `sub_category` | 26,166 | 100.0% |
| `product_title` | 26,166 | 100.0% |
| `weight` | 26,166 | 100.0% |
| `regular_price` | 26,020 | 99.4% |
| `sale_price` | 7,469 | 28.5% |
| `volume_deals_description` | 0 | 0.0% |
| `volume_deals_price` | 0 | 0.0% |
| `digital_deals_description` | 0 | 0.0% |
| `digital_deals_price` | 0 | 0.0% |
| `image_url` | 26,160 | 100.0% |
| `url` | 26,166 | 100.0% |
| `upc` | 26,166 | 100.0% |
| `gupc` | 0 | 0.0% |
| `ppm` | 0 | 0.0% |
| `unit_price` | 0 | 0.0% |
| `crawl_date` | 26,166 | 100.0% |

`gupc` and `unit_price` are blank by the brief. `store_logo` is blank because neither
Kroger API supplies one and none was supplied to the run.

## Category counts

| Root | Records |
|---|---:|
| Grocery | 5,000 |
| Beverages | 2,572 |
| Frozen | 1,999 |
| Personal Care | 1,773 |
| Beer Wine Liquor | 1,752 |
| Household | 1,470 |
| Beauty | 1,361 |
| Health | 1,344 |
| Dairy | 1,164 |
| Natural Organic | 1,130 |
| Meat | 987 |
| Candy | 883 |
| Breakfast | 802 |
| Pet Supplies | 709 |
| Produce | 636 |
| Bakery | 604 |
| Baby | 564 |
| Kitchen Dining | 496 |
| Deli | 468 |
| (no root) | 187 |
| School Office | 101 |
| Candles Home Fragrances | 66 |
| Floral | 49 |
| Hardware Home Improvement | 49 |
| Batteries, Coffee, Coupons, Light Bulbs, Seafood | 0 each |

Records with no root carry a Kroger label that has no entry in the map, and are kept
with `category` blank.
