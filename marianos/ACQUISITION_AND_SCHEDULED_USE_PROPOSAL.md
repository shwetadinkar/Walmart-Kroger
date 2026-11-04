# Acquisition and scheduled-use proposal, for owner review

Prepared at the client's request of 4 November. **This is a description of what
is proposed, for the owner and his own counsel to measure against the
applicable terms. It is not a legal opinion, not a clearance, and not an
agreement.** Nothing here has been agreed with Kroger or any other party on
anyone's behalf, no partner request has been submitted, and none will be
without written instruction.

## The applicable policy text

The governing terms for the public tier are published at
**https://developer.kroger.com/terms**, and the per-API pages under
`https://developer.kroger.com/api-products/` carry the per-product conditions.

**I have not reproduced the text here, because I could not retrieve it.** That
host disallows automated retrieval in full, and I will not substitute a
third-party copy of a terms page for the terms themselves on a question that
goes to counsel: a mirror can be stale or partial, and the one being relied on
would not be the one quoted. The owner or his counsel should open the page
directly. If it is wanted as a dated extract for the file, say so and it can be
captured from the page itself rather than reconstructed.

This matters more than it looks. A refusal and a permission have each already
been built in this engagement on an unchecked claim about a vendor's
documentation, and both were wrong. The rule that came out of it is that the
fact carrying the decision gets checked, whichever way the decision goes.

## What is acquired

| | |
|---|---|
| Route | Kroger public developer tier, `GET /v1/products` |
| Authentication | OAuth2 `client_credentials`, scope `product.compact` |
| Credential holder | The client. Stored in `marianos/.env.kroger`, gitignored, never transmitted to us or committed |
| Store context | One store, Vernon Hills `53100502`, ZIP 60061, pickup |
| Fields taken | Product title, brand, size/weight, regular and sale price, UPC, product page URI, image URL, the retailer's own category label, fulfilment flags and stock level |
| Fields **not** taken | No customer data, no order data, no cart, no identity, no loyalty data. The `product.compact` scope reaches none of it |
| Derived values | None. `gupc` and `unit_price` ship empty by instruction, and `ppm` is only ever the rate the retailer displayed |

Access is read-only. No endpoint that writes, orders, or acts on an account is
called, and the Cart and Identity APIs are not used.

## Rate and volume

| | |
|---|---|
| Per-run ceiling, as configured | 1,500 requests and 7,200 seconds, enforced in code |
| Pages per search term | 6 (`filter.start` 0 to 250; Kroger refuses past 250) |
| Terms configured | 286 base terms plus 474 narrower splits |
| Observed, 3 November | about 2,200 requests across the base sweep and the split run, producing 28,549 distinct records |
| Proposed cadence | twice weekly |

The 3 November figure exceeded the single-run ceiling because it was the base
sweep plus a separate split run, not one run. A steady-state scheduled run
re-sweeps the configured terms within the per-run ceiling above.

## The schedule proposed

`0 6 * * 1,4` — Mondays and Thursdays at 06:00 UTC, giving 72 and 96 hour
gaps. Computed from the default read out of `azure/deploy_jobs.sh`, not
retyped.

**Nothing has run on this schedule.** No Azure cron has fired, nothing has run
in the client's environment, and the twice-weekly operation is a deployment
template plus a manually driven three-execution pilot. That is the honest state
and the proposal is for an operation that does not yet exist.

## Retention and use

Collected data is written to the client's own storage, under a trial namespace
while coverage cannot be attested. Raw API responses are persisted per term so
a later rule change re-filters rather than re-fetches, which reduces repeat
querying rather than increasing it. Each record keeps its own observation time
and per-field provenance. Previously observed products are retained with their
original dates.

The intended use is the client's own retail price-comparison deliverable. Two
aspects are the ones most likely to need the owner's judgement, and they are
named here rather than buried:

1. **Systematic accumulation over time.** Twice-weekly collection builds a
   price history rather than answering a query. This is the part most likely to
   sit outside a public read tier's expectations.
2. **Cross-retailer comparison.** The output is placed beside Walmart data for
   comparison. Whether a public tier's terms contemplate competitive
   benchmarking is a question about the terms, not about the code.

Neither is a technical limitation and neither is for me to resolve.

## What is not done, and will not be

- No identity rotation, no residential or other proxy routing, and no CAPTCHA
  or bot-challenge defeat, by any name. Where a route needs any of that, the
  route is reported unavailable rather than worked around.
- No partner-tier submission, registration, or agreement. The client's
  instruction that none is authorized stands.
- No acceptance of terms on the client's or the owner's behalf.
- No third-party vendor is pointed at the retailer's pages. A paid provider's
  dedicated endpoint for this retailer was checked on 3 November and refused,
  because it returns the retailer's own page fetched by the vendor, which is
  the same act under a different name.

## The attended page read is a separate question

Displayed price per measure and retailer deal wording exist only on the
rendered page; the public API carries neither at any tier. The values delivered
for those columns came from **attended sessions in a person's own browser** on
1 and 3 November, 935 product cards across the two, with the store confirmed
from the page itself before collection. That is a person looking at pages, at
human pace, not a scheduled or automated collection, and it is not part of what
is proposed above.

If those columns are wanted on a schedule rather than attended, that is a
different acquisition and needs its own decision. It has not been proposed
here and nothing has been built for it.

## What this document does not establish

- It does not establish that any of this is permitted. That is the question it
  exists to put to the owner.
- It does not establish that the schedule works, because nothing has run on it.
- It does not quote the governing terms, for the reason given above.
- It does not establish category coverage. One search term reaches at most 300
  products and 114 configured terms hit that ceiling, so the route cannot
  attest complete category discovery and the output stays in the trial
  namespace with `source_coverage_attested: false`.
