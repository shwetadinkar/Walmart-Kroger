# Oxylabs Classic Web Scraper API: the four things asked for

3 November 2026. The client wrote:

> Our existing paid interface is Oxylabs Classic Web Scraper API; that is not a
> guarantee it will supply the required retailer fields or context. If you
> propose using it, first identify the exact adapter, source/response shape,
> missing evidence it would resolve and a bounded request/cost estimate. Do not
> assume additional access or an approved run.

Nothing has been run. No account was used, no request was made, and no access
is assumed. Everything below comes from Oxylabs' public developer
documentation, read on 3 November, with the pages named at the end.

**The short answer, before the detail: I am not proposing it for Mariano's,
and for Walmart it does not resolve the thing that is actually unresolved.**
The reasons are in sections 3 and 4, and one of them is a line this repository
does not cross rather than a technical limit.

## 1. The exact adapter

One class implementing the existing `fetch(store, category, url, cursor) ->
Page` contract, alongside `FixtureSource`, `AuthorizedProviderSource`,
`CatalogV2Source` and `KrogerSweepSource`, so the runner, schema, retention
and storage layers are untouched:

    marianos/marianos_collector/oxylabs_source.py
        class OxylabsSource:
            source_mode = "oxylabs_web_scraper_api_universal"
            coverage_attested = False

    walmart/walmart_collector/oxylabs_source.py
        class OxylabsWalmartSource:
            source_mode = "oxylabs_web_scraper_api_walmart_product"
            coverage_attested = False

Credentials by environment only, `OXYLABS_USERNAME` and `OXYLABS_PASSWORD`,
never on a command line, same rule as the Kroger keys.

`coverage_attested = False` on both, for the same reason as the sweep: neither
enumerates a category, so the runner would confine the output to the trial
namespace.

## 2. Source and response shape

**Transport.** `POST https://realtime.oxylabs.io/v1/queries`, HTTP Basic auth,
`Content-Type: application/json`.

**Response.** One top-level key, `results`, an array whose items carry
`content`, `created_at`, `updated_at`, `id`, `page`, `url`, `job_id` and
`status_code`. Realtime returns only the default output; other output types
need the Push-Pull method.

**Walmart.** Three documented sources:

| Source | Takes | Parser |
|---|---|---|
| `walmart_product` | a product ID | dedicated |
| `walmart_search` | a `query` | dedicated |
| `walmart` | any Walmart URL, search and product pages only | none |

**Mariano's and Kroger: no dedicated source exists.** Neither Kroger,
Mariano's, nor any US grocery retailer is a named target. That leaves
`source: universal` with `url`, `geo_location`, `render: html` and
`parsing_instructions`, the last of which does support custom extraction logic
over the returned HTML.

## 3. Why I am not proposing it for Mariano's

Using `universal` against `marianos.com` means pointing Oxylabs' proxy network
at a retailer that refuses our datacenter egress, in order to obtain the page
our datacenter cannot get. Measured three times: two Azure regions and a
second cloud provider on 30 October, and a datacenter `curl` of
`sitemap.xml` on 2 November, all refused before any HTTP exchange, against the
same URL a browser on an ordinary residential connection served normally.

The standing position in `CLAUDE.md` is that no identity rotation, no
residential proxy routing and no bot-challenge defeat is built here, **by any
name**. Paying a vendor to perform it at our direction is the same act with an
invoice attached. That the interface already exists and is already paid for
changes who holds the proxy pool, not what the request does.

This is not the same shape as the Bright Data route already in use for
Walmart. There we consume a dataset the provider collected under its own
arrangements and we state its provenance and its limits. Here we would be
issuing per-URL fetch instructions against a specific retailer and relying on
the vendor's network to get past a refusal aimed at us. If the client reads
that distinction differently it is his call to make explicitly, with his own
counsel, and not a thing to arrive at because it was the only option left.

If Oxylabs offers a **pre-collected grocery dataset**, as opposed to
`universal` fetching on demand, that is the Bright Data shape and I would
assess it on the same terms. Their public target list does not show one.

## 4. Why it does not resolve the Walmart gap either

The unresolved Walmart question is store context: whether the provider's store
switch applied to the 22 and 23 October snapshots, and therefore whether 143
records sit on products genuinely unavailable for pickup at Store 100.

The Oxylabs Walmart documentation **does not document a store id, a ZIP code or
store-specific pricing on any of its three Walmart sources**, and does not
document a unit price, price-per-measure or promotion-text field in the parsed
output. So on the published documentation it supplies neither of the two things
we need: not the store-bound context, and not the displayed rate.

It might do more than it documents. That would have to be established by a
bounded probe, section 5, and it would be a probe of whether the capability
exists at all, not a collection run.

## 5. A bounded probe, if he wants one anyway

This is the smallest thing that answers the capability question. It is not a
collection and it would produce no delivered records.

| Step | Requests | What it settles |
|---|---:|---|
| `walmart_product` with `parse: true` on 5 known Store 100 product IDs | 5 | Whether the parsed output carries any unit-price or promotion field at all |
| The same 5 with any store or location parameter the account exposes | 5 | Whether a store context can be requested, and whether the price moves when it changes |
| `walmart` on 2 full product URLs carrying a store parameter | 2 | Whether the returned HTML contains the rendered price-per-measure string |
| **Total** | **12** | |

Twelve requests. Whatever Oxylabs charges per result, twelve results is a
rounding error against any commitment tier, so the cost question is not the
constraint and I am deliberately not quoting a unit price I cannot see: the
rate card depends on the plan on his account, and guessing it would be the
same error as guessing a retailer field.

**What the probe would not establish**, and this is why I would rather he
decided section 3 first: twelve successful fetches would not make the route
compliant with the standing position, nor make `universal` fetching of
`marianos.com` acceptable. It settles capability only.

## 6. What I would rather do instead

The `walmart_product` source with its dedicated parser, used on product IDs we
already hold, is worth 12 requests to find out whether it carries a unit price,
because that is a documented product interface rather than proxy-fetching a
page on our behalf. That is the one part of this I would propose.

For Mariano's, the honest position is unchanged from
`marianos/ROUTES_AND_AUTONOMY.md`: no unattended route to displayed price per
measure and deal wording exists that does not cross the line in section 3. The
routes that remain are the ones already named there, and the decision among
them is his.

## What this assessment does not establish

- **That Oxylabs cannot do these things.** It establishes that its public
  documentation does not say it can. Vendor documentation is often behind the
  product; the probe in section 5 exists for exactly that reason.
- **Anything about cost.** No rate card was read. Request counts are bounded
  above; the price per result is on his account and not visible here.
- **That the partner question is affected.** It is not. The partner request
  stays unsubmitted, as agreed.
- **That any of this changes the acceptable-use question** in
  `marianos/ACCEPTABLE_USE_POSITION.md`. It does not.

## Sources

- [Realtime integration](https://developers.oxylabs.io/products/web-scraper-api/integration-methods/realtime) — endpoint, auth, payload fields, response keys
- [Any Domain / API targets](https://developers.oxylabs.io/api-targets) — `universal`, `parsing_instructions`, `geo_location`, and the absence of any grocery target
- [Walmart targets](https://developers.oxylabs.io/scraper-apis/web-scraper-api/walmart) — `walmart_product`, `walmart_search`, `walmart`, and the absence of documented store context or unit-price fields
