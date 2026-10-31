# Composed source: what can actually run

Internal engineering note, checked against `walmart_collector/` at the commit
that added it. Not written for delivery.

`--source composite` is not deployable as a route to the offer fields. It runs,
and the fields it cannot reach stay blank with the reason recorded.

## Executable sources

| Source | Role | Implementation | Runs today |
|---|---|---|---|
| OPD snapshot | spine | `opd.WalmartOPDSnapshotSource` | Code exists; needs an entitlement this project does not hold. `coverage_attested = False`, so a full release is refused and only a trial runs |
| Authorized provider | spine | `sources.AuthorizedProviderSource` | Adapter exists; no provider is contracted. It attests coverage on the provider's own claim, which an auditor must verify |
| Fixture | spine | `sources.FixtureSource` | Runs; synthetic, and reported as synthetic through a composite too |
| Website crawl | enrichment | `composition.unavailable_crawl` | **Not a collector.** A placeholder with an empty lookup and a blocked status |

Delivered Bright Data snapshots go through `brightdata_import.py`, a separate
offline import, not a source the composite can wrap.

There is no working offer enrichment. `sale_price` and the four volume and
digital fields have no executable source, and every composite run report lists
them under `provenance.fields_without_executable_source`. An entitlement would
not change that: OPD documents no offer fields, and the crawl is refused from
datacenter egress by a bot challenge, which this project does not defeat. Nor
would an entitlement validate production coverage. `coverage_attested` stays
false on OPD until something reconciles the feed against the configured
categories.

## Binding of every contributed field

The spine's fields are bound by the checks that admit a product at all.
Enrichment values are bound per value: a lookup returns `_binding` with
`identity`, `store_id`, `fulfillment` and `observed_at`, and `composition.py`
refuses a value that does not match, counting the reason under
`provenance.contributions_refused_as_unbound`.

| Field | Source by precedence | Product | Store | Fulfilment | Time |
|---|---|---|---|---|---|
| `product_title`, `weight`, `url`, `image_url`, `upc`, `store_brand`, `regular_price` | OPD, provider, crawl | OPD offer or provider product id | OPD `storeCode` for price; catalog fields are national | `make_record` admits `pickup` and `in_store`; OPD asserts `pickup` from the locator, not per row | Run `crawl_date`; no per-value time |
| `ppm` | OPD, crawl, provider | as above | OPD `storeCode` | as above | as above |
| `sale_price`, `volume_deals_*`, `digital_deals_*` | crawl, provider | `_binding.identity` | `_binding.store_id` | `_binding.fulfillment` | `_binding.observed_at` |

`upc`, `brand` and the rest of the catalog are one national row, so store binding
applies to the price feed only. A spine value has no observation time finer than
the run date. That is a limit of the 22-field record, and it holds for any value
a spine supplies. `offer_context.json` beside the record holds the availability
each price was observed with.
