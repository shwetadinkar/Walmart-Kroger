> **SUPERSEDED — added 1 November 2026.** This package describes the run made
> **before** the paging correction in commit `78f57dc`, and it is missing the
> 1,483 records that correction recovered. Its figure of 24,683 records is
> superseded by the 26,166 in `../2026-10-31-vernon-hills-package-rerun/`, which
> is the authoritative collection for this store and date. Nothing in this
> folder should be quoted. It is kept because the earlier run is part of the
> record, not because it is current.

# Brief's proof items

From section 10 of the shared requirements. "Met" means the bytes in this package
show it, not that the item is accepted.

| Item | Result |
|---|---|
| 500 valid records from an assigned location | Met: 24,683 records at store 53100502 |
| Multiple required categories | Met: 23 of 28 roots populated, 5 empty; see `DOES_NOT_ESTABLISH.md` |
| Structured JSON | Met: `data/data_22_fields.json`, 22 string fields in order, no nulls |
| Runtime | Met: 1445.9 seconds, 888 requests, 2026-10-31T14:05:49 to 2026-10-31T14:29:51 UTC |
| Total and category counts | Met: below |
| Duplicate count | Met: 0 duplicate UPCs, 0 duplicate URLs. 13,479 repeat placements across terms were collapsed from 38,162 returned |
| Field-completeness results | Met: all 22 fields, below |
| PPM examples | **Not met.** No row has a `ppm`. The API carries only an estimate, which the brief forbids, and the page probe at this store read no page |
| Deal examples | **Not met.** No volume or digital wording exists in this data. 6,981 rows carry a `sale_price`, which is the API's promo price and not a deal description |
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
| `zipcode` | 24,683 | 100.0% |
| `store_name` | 24,683 | 100.0% |
| `store_location` | 24,683 | 100.0% |
| `store_logo` | 0 | 0.0% |
| `store_brand` | 24,683 | 100.0% |
| `category` | 24,505 | 99.3% |
| `sub_category` | 24,683 | 100.0% |
| `product_title` | 24,683 | 100.0% |
| `weight` | 24,683 | 100.0% |
| `regular_price` | 24,542 | 99.4% |
| `sale_price` | 6,981 | 28.3% |
| `volume_deals_description` | 0 | 0.0% |
| `volume_deals_price` | 0 | 0.0% |
| `digital_deals_description` | 0 | 0.0% |
| `digital_deals_price` | 0 | 0.0% |
| `image_url` | 24,678 | 100.0% |
| `url` | 24,683 | 100.0% |
| `upc` | 24,683 | 100.0% |
| `gupc` | 0 | 0.0% |
| `ppm` | 0 | 0.0% |
| `unit_price` | 0 | 0.0% |
| `crawl_date` | 24,683 | 100.0% |

`gupc` and `unit_price` are blank by the brief. `store_logo` is blank because neither
Kroger API supplies one and none was supplied to the run.

## Category counts

| Root | Records |
|---|---:|
| Grocery | 4,471 |
| Beverages | 2,495 |
| Frozen | 1,869 |
| Personal Care | 1,726 |
| Beer Wine Liquor | 1,633 |
| Household | 1,425 |
| Beauty | 1,290 |
| Health | 1,240 |
| Natural Organic | 1,101 |
| Dairy | 1,097 |
| Meat | 967 |
| Candy | 818 |
| Breakfast | 780 |
| Pet Supplies | 703 |
| Bakery | 586 |
| Produce | 569 |
| Baby | 557 |
| Kitchen Dining | 472 |
| Deli | 457 |
| (no root) | 178 |
| School Office | 93 |
| Candles Home Fragrances | 65 |
| Floral | 46 |
| Hardware Home Improvement | 45 |
| Batteries, Coffee, Coupons, Light Bulbs, Seafood | 0 each |

Records with no root carry a Kroger label that has no entry in the map, and are kept
with `category` blank.
