# Oxylabs Web Scraper API: the four things asked for

3 November 2026. The client wrote:

> Our existing paid interface is Oxylabs Classic Web Scraper API; that is not a
> guarantee it will supply the required retailer fields or context. If you
> propose using it, first identify the exact adapter, source/response shape,
> missing evidence it would resolve and a bounded request/cost estimate. Do not
> assume additional access or an approved run.

Nothing has been run. No account was used, no request was made, and no access
is assumed. Everything below comes from Oxylabs' public developer
documentation, read on 3 November, with the pages named at the end.

## Correction to the first version of this file

The first version of this assessment, written earlier the same day, declined
the route for Mariano's and judged it useless for Walmart. Both conclusions
rested on two factual claims about Oxylabs' documentation, **and both claims
were wrong.** They are recorded here rather than quietly replaced, because the
reasoning built on them was the substance of the document.

| What it claimed | What the documentation says |
|---|---|
| "Mariano's and Kroger: no dedicated source exists. Neither Kroger, Mariano's, nor any US grocery retailer is a named target." | `marianos_search` and `marianos_product` are named targets with a dedicated parser, as are `kroger_*` and roughly fifteen other Kroger banners including Pick 'n Save, Metro Market, Harris Teeter, Fred Meyer, King Soopers, Ralphs and QFC. |
| "The Oxylabs Walmart documentation does not document a store id, a ZIP code or store-specific pricing on any of its three Walmart sources." | All three Walmart endpoints take `store_id`, and two take `fulfillment_type`. |

Those were checkable in one reading of the target list. This repository's own
rule is that claims in client-facing files are checked rather than written from
memory, and this file broke it. The conclusions below are different from the
first version's because the facts are.

**The short answer now: there is a documented Mariano's interface that accepts
our store and pickup context, and the remaining question is a narrow one about
two output fields that a bounded probe settles.**

## 1. The exact adapter

One class implementing the existing `fetch(store, category, url, cursor) ->
Page` contract, alongside `FixtureSource`, `AuthorizedProviderSource`,
`CatalogV2Source` and `KrogerSweepSource`, so the runner, schema, retention
and storage layers are untouched:

    marianos/marianos_collector/oxylabs_source.py
        class OxylabsMarianosSource:
            source_mode = "oxylabs_web_scraper_api_marianos_product"
            coverage_attested = False

    walmart/walmart_collector/oxylabs_source.py
        class OxylabsWalmartSource:
            source_mode = "oxylabs_web_scraper_api_walmart_product"
            coverage_attested = False

Credentials by environment only, `OXYLABS_USERNAME` and `OXYLABS_PASSWORD`,
never on a command line, same rule as the Kroger keys.

`coverage_attested = False` on both. `marianos_search` takes a `query`, so it
is term-filtered search exactly like the Kroger sweep and enumerates no
category; the runner would confine its output to the trial namespace and the
report would say `source_coverage_attested: false`. A dedicated parser does not
change that, and nothing here is a route to complete category coverage.

## 2. Source and response shape

**Transport.** `POST https://realtime.oxylabs.io/v1/queries`, HTTP Basic auth,
`Content-Type: application/json`. Realtime returns only the default output;
other output types need the Push-Pull method.

**Response.** One top-level key, `results`, an array whose items carry
`content`, `created_at`, `updated_at`, `id`, `page`, `url`, `job_id` and
`status_code`.

**Mariano's.** A dedicated target, and these are the parameters that matter:

| Source | Takes | Location parameters |
|---|---|---|
| `marianos_product` | `query` | `store_id`, `delivery_zip`, `fulfillment_type` |
| `marianos_search` | `query`, plus `brand` and `price_range` | `store_id`, `delivery_zip`, `fulfillment_type` |
| `marianos` (url variant) | any Mariano's URL | `store_id`, `delivery_zip`, `fulfillment_type` |

`fulfillment_type` documents `pickup`, `delivery` and `in_store` as values. So
the assigned context for this engagement, store `53100502`, ZIP `60061`,
PICKUP, is expressible as request parameters rather than inferred.

**Walmart.** Also a dedicated target with `store_id`:

| Source | Takes | Location parameters |
|---|---|---|
| `walmart_product` | `query`, `domain` | `store_id`, `fulfillment_type` |
| `walmart_search` | `query`, `domain`, `sort_by`, price bounds, `start_page`, `fulfillment_speed` | `store_id`, `fulfillment_type` |
| `walmart` (url variant) | any Walmart URL | `store_id`, `fulfillment_type` |

No `delivery_zip` on the Walmart side; that is the one real difference from the
Kroger banners.

**What is NOT documented, for either retailer.** I could not reach a parsed
output schema for the Kroger-banner targets. The Oxylabs Kroger product page
names pricing, availability and fulfillment options. The Walmart product
sample output shows price, currency, title, rating, review count, seller, SKU
and GTIN, warranty, breadcrumbs, description and specifications. **Neither
mentions a unit price, a price per measure, or any promotion, deal or coupon
text field.** That is now the whole of the open question, and it is undetermined
rather than answered either way.

## 3. The acceptable-use position, restated

The first version refused the Mariano's route on the ground that it meant
pointing a general proxy network at a retailer that refuses our datacenter
egress. That ground was the false claim: there is a dedicated, parsed,
retailer-specific interface, not a `universal` fetch of an arbitrary URL.

The test this file already applied to Walmart was that `walmart_product` with
its dedicated parser is a documented product interface rather than proxy
fetching a page on our behalf, and that it was the one part worth proposing.
`marianos_product` is the same shape. Applying a stricter rule to Mariano's
than to Walmart when both are dedicated targets would be incoherent, so it is
not applied.

What the standing position in `CLAUDE.md` still rules out, unchanged:

- `source: universal` against `marianos.com`, or any arbitrary-URL fetching of
  a retailer that has refused us.
- Anything whose purpose is to defeat a bot challenge, under any name.
- Identity rotation or residential routing arranged by us or at our direction
  for that purpose.

And the honest qualification, stated rather than glossed: **a dedicated target
is still a vendor fetching a page our own egress cannot reach.** The
distinction between a maintained, parsed, retailer-specific product interface
and proxy-fetching an arbitrary URL is a real one, and it is the distinction
already drawn for Walmart and for Bright Data. It is not a bright line. The
broader commercial and legal judgment about collecting a retailer's data
through a third party belongs to the client and his own counsel, which is where
`marianos/ACCEPTABLE_USE_POSITION.md` leaves it. Nothing here changes that
file.

The measured refusal of our own egress stands as recorded: two Azure regions
and a second cloud provider on 30 October, and a datacenter `curl` of
`sitemap.xml` on 2 November, all refused before any HTTP exchange, against the
same URL a browser on an ordinary residential connection served normally.

## 4. What it could resolve, if the output carries the fields

**Mariano's, the enrichment gap.** Displayed price per measure and the
retailer's own deal wording exist only on the rendered page. The Kroger public
Products API carries neither, our page route stopped after 28 page loads on
1 November, and every report says no unattended route to those fields exists.
If `marianos_product` returns them, that statement stops being true and the
gap closes unattended, with the store and pickup context requested rather than
assumed. If it does not, the statement stands and is better evidenced than
before.

**Walmart, the store context question.** The open question is whether the
Bright Data provider's store switch applied to the 22 and 23 October
snapshots, and therefore whether 143 records sit on products genuinely
unavailable for pickup at Store 100. `walmart_product` with `store_id` 100 and
`fulfillment_type` gives an independent second observation of that claim from a
different provider, which is worth more than the provider restating its own
mechanism. It does not retroactively verify the October snapshots; it tests
whether their pickup claim reproduces.

Neither of these is a coverage route. `marianos_search` is term-filtered and
attests nothing about category completeness.

## 5. A bounded probe

Not a collection. It would produce no delivered records.

| Step | Requests | What it settles |
|---|---:|---|
| `marianos_product` on 5 UPCs already in the delivered set, with `store_id` 53100502, `delivery_zip` 60061, `fulfillment_type` pickup | 5 | Whether the parsed output carries a unit price or price-per-measure field, and any promotion or deal text at all. **This is the one that matters.** |
| The same 5 with no `store_id` | 5 | Whether the store context changes the price, which is the only way to know the parameter does anything |
| `marianos_search` on 2 terms whose Kroger-API results we already hold | 2 | Whether its result set differs from the API's for the same term, and whether it carries the two fields |
| `walmart_product` on 5 Store 100 product IDs we already hold, with `store_id` 100 and `fulfillment_type` | 5 | Whether the pickup claim on those records reproduces from an independent provider, and whether a unit price appears |
| **Total** | **17** | |

Seventeen requests. I am deliberately not quoting a unit price: the rate card
depends on the plan on his account, and guessing it would be the same error as
guessing a retailer field. Seventeen results is a rounding error against any
commitment tier, so cost is not the constraint.

**The first five requests are the whole value of this.** If the parsed output
has no unit price and no deal text, everything else here is a store-context
cross-check and nothing more.

## 6. The question that has to go back to him

He named **Classic Web Scraper API** specifically. The dedicated e-commerce
scrapers may or may not sit inside that entitlement; Oxylabs has reorganised
these products and the naming across its documentation is not consistent. If
the banner targets are a separate product or tier, then every parameter in
section 2 is documentation he cannot use, and the answer reverts to something
close to the first version of this file for reasons of access rather than of
capability.

That is his to answer and not ours to assume, which is why it is a question
here rather than a premise.

## What this assessment does not establish

- **That `marianos_product` returns a price per measure or deal wording.** It
  establishes that the documentation reachable on 3 November does not say so,
  and does not say otherwise. Undetermined. Section 5 exists for that.
- **That the account can call these targets.** Section 6.
- **Anything about cost.** No rate card was read. Request counts are bounded
  above; the price per result is on his account and not visible here.
- **Any category coverage claim.** `marianos_search` is term-filtered search.
  It cannot enumerate a category and `coverage_attested` is `False`.
- **That the October Walmart snapshots are verified.** A probe tests whether
  their pickup claim reproduces now. It cannot observe the past.
- **That the partner question is affected.** It is not. The partner request
  stays unsubmitted, as agreed.
- **That the acceptable-use position has moved.** The standing refusals in
  section 3 are unchanged. What changed is that this route is not one of them.

## Sources

Read 3 November 2026:

- Oxylabs developer documentation, e-commerce targets list (the page naming
  `marianos_search`, `marianos_product`, `kroger_search`, `kroger_product`,
  `walmart_search`, `walmart_product` and the other banners)
- Oxylabs developer documentation, dedicated scrapers quick reference (the
  endpoint parameter lists quoted in section 2)
- Oxylabs Kroger Scraper API product page
- Oxylabs Walmart Product Data API product page
