# Mariano's Catalog V2 route: runbook

For the client, or anyone reviewing the collector. Nothing in this document has
been run against Kroger. No credential exists in this repository.

## Why this route and not the public API

Kroger publishes two tiers. The public Products API is self-service; Catalog V2
is partner-gated and requires a contractual agreement.

The public tier carries the fields this brief needs, including
`regularPerUnitEstimate` and `promoPerUnitEstimate` in its published OpenAPI
1.3.0 price model. It is still not usable here. Kroger's *Acceptable Use of
Public APIs* prohibits systematically gathering response data to create a
database, and separately prohibits comparing products and prices among other
retailers. This collector accumulates a retained dataset on a twice-weekly
schedule and runs beside a Walmart collector on the same schema, so both
prohibitions apply.

So the partner agreement is not an administrative step in front of data that
could otherwise be taken. It is what grants the rights. `kroger.py` stays
diagnostic-only for this reason and its output is marked
`publication_eligible: false`.

## What the adapter does

Catalog V2 has no category filter. Its three endpoints are driven by store
location, optionally narrowed by a UPC list or an `updatedAt` range, and paged
with `page.offset` / `page.size`.

So `CatalogV2Source` sweeps the whole location once, groups products by the
category each product reports about itself, and serves the collector's existing
per-category page interface from that result. The runner, normalizer, 22-field
schema, storage and retention logic are unchanged.

A paged sweep is a stronger coverage claim than a category crawl. A crawl
reaches only what it discovers by following links; a sweep is exhaustive by
construction once the API reports `hasMore: false`. If the sweep stops early,
`subcategories_complete` is false and the runner refuses to publish.

## Field mapping

| Brief field | Catalog V2 source | Notes |
|---|---|---|
| `regular_price` | `prices[].regular.defaultDescription` | Displayed string, e.g. `$4.99` |
| `sale_price` | `prices[].promo.defaultDescription` or `.promoDescription` | |
| `volume_deals_description` | composed from `promo.nFor.quantity` and `.price` | **Composed, not verbatim.** See below |
| `volume_deals_price` | `promo.nFor.price` | `USD 18.00` reduced to `18.00` |
| `digital_deals_description` | — | Always blank. See below |
| `digital_deals_price` | — | Always blank |
| `weight` | `metadata.size` | e.g. `1 lb` |
| `upc` | `upc` | String in the contract, so leading zeros survive |
| `url` | `productPageURL` | Rejected if the host is not a marianos.com host |
| `image_url` | `images[]` | |
| `category` / `sub_category` | `categories[].parent.name` / `.name` | |
| `store_brand` | `brand.name` against the private-brand list | |
| `ppm` | `prices[].regular.unit` | **Not written by default.** See below |

## Three things this route does not settle

**Volume offer wording is composed.** The brief requires retailer wording to be
preserved rather than rebuilt. Catalog V2 supplies the offer as structured data
(`nFor.quantity`, `nFor.price`), not as the shelf sentence, so a string like
`4 for $18.00` is built by the adapter. Every run records
`volume_wording: composed_from_nFor_not_verbatim_retailer_text` in its
provenance so this is never mistaken for scraped text.

**Price per measure is unproven.** The price model has a field named `unit`,
documented only as `string, example "USD 5.00"`. That may be the displayed
price per measure, or it may be the price for the unit of sale. The contract
does not say. The adapter therefore carries it into the audit record on every
product but does **not** write it to `ppm` unless an operator sets
`CATALOG_V2_UNIT_IS_PPM=yes` having checked a live response. A field name and a
plausible example are not a result.

**Digital coupon terms are not available at all.** No Kroger API on the
published list, public or partner, exposes clipping state, household limits or
digital offer eligibility. `digital_deals_description` and
`digital_deals_price` are blank because the data does not exist on this route,
not because it was not mapped.

## Two parameters that need a live answer

Both are required by the contract but have no published values, so both are
configurable and both are recorded in the run provenance as unverified.

| Setting | Env var | Default | What settles it |
|---|---|---|---|
| Fulfillment filter | `CATALOG_V2_FULFILLMENT` | `curbside` | The contract marks `filter.locations.fulfillment.eq` required but publishes no enum |
| OAuth scope | `CATALOG_V2_SCOPE` | `product.compact` | The partner agreement states the issued scope |

## Running it

Credentials stay with whoever owns them. They are read from the environment and
are never written to disk, logged, or sent anywhere but `api.kroger.com`.

```bash
export KROGER_CLIENT_ID=...
export KROGER_CLIENT_SECRET=...
export MARIANOS_DATA_AUTHORIZED=yes
export CATALOG_V2_FULFILLMENT=curbside      # confirm against the agreement
# export CATALOG_V2_SCOPE=...               # if the agreement issues another
# export CATALOG_V2_UNIT_IS_PPM=yes         # only after checking a live response

python -m marianos_collector run \
  --store <real-store-id> \
  --location-id <kroger locationId> \
  --source catalog_v2 \
  --authorized-source \
  --backend local
```

Find the `locationId` first, and confirm the address by eye rather than
guessing:

```bash
python -m marianos_collector kroger-locations --zipcode 60661 --address-contains "Des Plaines"
```

## Bounded first test

To run once, after entitlement exists, before anything scaled.

| Parameter | Bound |
|---|---|
| Store | one, confirmed by address |
| Page size | 5 |
| Pages | 1 |
| Output | isolated, not merged into any delivered dataset |
| Azure | no deployment, no scheduling |

What to check on the returned records: that `locations[].id` equals the
requested store on every row, that `productPageURL` is a marianos.com host,
that `upc` keeps its leading zeros, whether `unit` is a per-measure rate or a
unit-of-sale price, and whether any `nFor` block appears at all.

Record absent fields as absent. Derive nothing.

## What is already proved without credentials

27 tests cover this adapter specifically, inside a Mariano's suite of 60. They
exercise the contract's two money spellings, `nFor` composition, store binding
against a multi-location response, refusal of a foreign-banner product URL,
pagination and the empty-page loop guard, the demo-store and page-size guards,
entitlement refusal as a non-retried challenge, and the provenance record.

None of that is evidence that an entitlement exists. It is evidence that the
day one is granted, the mapping is already written and tested.
