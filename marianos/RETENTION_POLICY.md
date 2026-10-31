# Product identity, observation freshness and retention

Internal policy for this repository. Supersedes the version on
`marianos-fresh-runs-category-evidence`. The rule is the client's, stated on
27 October for Mariano's and on 31 October for Walmart.

**A product is never removed from the delivered dataset because a field is
missing or a status is unfavourable.** "Never publish a value that was not
observed" governs values. An unobserved value is an empty string. It is not a
reason to delete the product it belongs to.

## What keeps a row, and what does not

| Case | Row | Value | Recorded in |
|---|---|---|---|
| No qualifying pickup offer | kept | whatever the closest item carried | `offer_status`, `offer_gaps` |
| No price, or a zero price | kept | empty | `offer_gaps` |
| Unavailable | kept | observed values stay | `availability_state`, `availability_audit` |
| No valid UPC | kept | empty | `record_gaps`, `identity_basis` |
| No valid product URI | kept under its UPC | empty | `record_gaps`, `identity_basis` |
| Refused deal text, foreign URL, malformed price | kept | that field empty | `value_refusals` |
| Website and API disagree on a price | kept | disputed fields empty | conflict audit, both values |
| Approximate-weight wording in the weight or title | excluded | | quarantine, with reason |
| Store mismatch, or an unverified store | run stops | | |
| Neither a URL nor a UPC | held | | quarantine, with reason |

Approximate weight is excluded because the brief excludes it. It is the only
content exclusion. The last row is a limit of the format, not a judgement about
the product: the 22 fields have no other place to hold an identity, so such a
product cannot be carried from run to run.

A price conflict is the one case where observed values are emptied, because two
sources disagree about one value and publishing either would resolve that
silently. Both values stay in the audit.

## Identity

Identity is the store plus the retailer product id from the product URL. The UPC
is optional and is never derived from URL digits. Without a URL the UPC is used.
Which applied is recorded per record as `identity_basis`. Blank UPCs do not merge
unrelated products. One UPC on two identities fails closed.

## Context beside the record

The delivered JSON stays exactly 22 ordered string fields, so context cannot be
a column. The sweep writes `pickup_context.json`, keyed by identity: the
fulfillment flags, `soldBy`, stock level, offer classification, observation time
and the hash of the response each value came from. `retention.json` repeats it
per identity with first and last observation dates, current or carried-forward
status, per-field observation dates, historical prices and the carry reason.

Sold-by-weight items keep the price Kroger returned, and `sold_by` says so. The
figure may be per pound rather than for the stated size. That is unresolved, so
read `sold_by` before reading `regular_price`.

## Carrying products forward

A product absent from a later successful run is carried with its original
`crawl_date` and last observed values, marked `carried_forward`. A current
observation with no price has an empty delivered price, and the earlier quote
stays in `historical_prices`. Stale observations cannot refresh newer values.
Carried rows never disguise a failed run: the yield and completeness gates apply
to what was freshly observed. A prior run from another store is refused, so West
Loop and Vernon Hills can never merge.

## Worked examples

Each runs through the real importer in `tests/test_retention_worked_examples.py`:
two dated collections of one store, 24 and 25 October, with a $2.98 product.

| Example | Delivered row after the second run | `retention.json` |
|---|---|---|
| Available becomes unavailable, price observed at $3.49 | `3.49`, dated 25 Oct | `unavailable`, `current`, history `2.98` |
| Price missing on the next run | empty price, dated 25 Oct | `current`, gap `NO_POSITIVE_REGULAR_PRICE`, history `2.98` |
| Absent from the next run | `2.98`, dated 24 Oct | `carried_forward`, `NOT_RETURNED_IN_CURRENT_COLLECTION` |
