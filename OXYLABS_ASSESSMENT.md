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

**The short answer, now that it has been run rather than argued about: the
dedicated Mariano's target exists, it works, and it is refused. Not on
capability. On what it turns out to be.**

A trial account was taken on 3 November so the question could be settled
without touching the client's entitlement or his budget. Sixteen requests,
about four cents. What they established is in section 5, and it is the
opposite of what section 3 of the first version assumed in both directions.

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

## 3. The acceptable-use position, after testing rather than before

The first version refused the Mariano's route on the ground that no dedicated
target existed, so the only route would be `universal` fetching of
`marianos.com`. That ground was false. The second version then accepted the
dedicated target on the ground that it is a *maintained, parsed,
retailer-specific interface* rather than arbitrary page fetching.

**That ground is false too, and `OPTIONS` on the endpoint is what settled it.**
Its output enum is `html`, `markdown`, `screenshot`, `json`, where `json` is
parsed by an LLM against a `json.schema` or `json.prompt` the caller supplies.
There is no vendor-maintained product parser for this retailer. The target
resolves a query, accepts store context, and returns the page.

So the dedicated target delivers the same bytes as the generic route, and the
distinction cannot carry the weight that was put on it. The standing position
in `CLAUDE.md` covers both, and both are refused in code: `REFUSED_HOSTS` for
the URL route, `REFUSED_TARGETS` for the dedicated one, each with a test
asserting no request is sent.

The measured refusal of our own egress stands as recorded: two Azure regions
and a second cloud provider on 30 October, and a datacenter `curl` of
`sitemap.xml` on 2 November, all refused before any HTTP exchange, against the
same URL a browser on an ordinary residential connection served normally.

**A second and independent reason.** The `json` output is LLM extraction. A
value a model produced by reading a page is not an observed value, and `ppm`
is required to be the *displayed* rate. That reason would stand even if the
first did not.

**What is not being claimed.** Not that this is unlawful, and not that the
client may not do it. The capability is real and the obstacle was never
technical. Whether to collect this retailer through a third party is a
commercial and legal judgement for the client with his own counsel, which is
where `marianos/ACCEPTABLE_USE_POSITION.md` leaves it and where it stays. What
is decided here is only what this repository will build.

## 4. What it would have resolved

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

## 5. The probe, and what it returned

Run on 3 November against a trial account, not the client's. Sixteen requests.

| Step | Result |
|---|---|
| `POST /v1/scrape/marianos/product`, 5 UPCs, with `store_id` 53100502, `delivery_zip` 60061, `fulfillment_type` pickup | **400** `UNSUPPORTED_BODY_PROPERTY`, pointer `#/parse` |
| The same 5 without `parse` | **200**, `state: done`, each carrying `results[0].html` |
| `OPTIONS /v1/scrape/marianos/product` | The typed parameters, including the output enum |

Three things follow, in order of how much they matter.

**The 400 was the most informative response of the set.** A missing target or
a rejected key fails before the body is read, so a complaint about one body
property established that the endpoint exists and that the key reaches it.
`parse` belongs to the Classic Realtime API; the dedicated endpoints do not
take it.

**The 200s returned the retailer's product page**, not a product record. The
five UPCs were chosen because each already carries a price per measure read
off that retailer's own rendered page, so a returned rate could have been
checked against an observed one rather than trusted. There was no rate to
check, because there was no parsed object.

**`OPTIONS` then explained why**, and is the reason section 3 now reads as it
does: `html`, `markdown`, `screenshot`, and an LLM-parsed `json`. No vendor
parser exists.

The probe cost about four cents and changed the answer twice. It is the whole
argument for running a bounded probe instead of reasoning from documentation,
which is what the first version of this file did, twice, wrongly.

## 6. What is now known about entitlement

He named **Classic Web Scraper API**. The trial account used here was a **Web
API** product instance, and on that instance the dedicated banner targets are
callable: the 400 and then the 200s prove it for `marianos_product`.

That answers the question for a Web API instance. It does not answer it for
his Classic entitlement, which may be a different product with a different
target list. Since the route is refused on other grounds, the entitlement
question no longer blocks anything, and it is recorded here rather than put to
him as a decision he needs to make.

## What this assessment does not establish

- **That the page markup does not contain the rate.** It almost certainly
  does: these are the rendered product pages. What is established is that the
  endpoint returns no parsed rate field, and that extracting one would mean
  parsing a page a vendor fetched on our behalf, which is the act refused in
  section 3, or accepting an LLM's reading of it, which is not an observation.
- **That the client's Classic entitlement includes these targets.** Only that
  a Web API trial instance does. Section 6.
- **Anything about cost.** No rate card was read. Request counts are bounded
  above; the price per result is on his account and not visible here.
- **Any category coverage claim.** `marianos_search` is term-filtered search.
  It cannot enumerate a category and `coverage_attested` is `False`.
- **That the October Walmart snapshots are verified.** A probe tests whether
  their pickup claim reproduces now. It cannot observe the past.
- **That the partner question is affected.** It is not. The partner request
  stays unsubmitted, as agreed.
- **That this route is unlawful, or that the client may not use it.** It
  establishes only what this repository will build. The capability is real and
  the obstacle was never technical.
- **Anything about Bright Data.** That route is assessed separately and is a
  different shape: a dataset the provider collects under its own arrangements,
  rather than per-URL fetches we direct. On 1 November the provider confirmed
  in writing that displayed price per measure and digital coupon fields are
  returned when publicly shown for the product and the selected store. It
  cannot currently resolve the assigned store: ZIP 60061 returns `bad_input`,
  retested 3 November, open with their R&D.

## Sources

Read 3 November 2026:

- Oxylabs developer documentation, e-commerce targets list (the page naming
  `marianos_search`, `marianos_product`, `kroger_search`, `kroger_product`,
  `walmart_search`, `walmart_product` and the other banners)
- Oxylabs developer documentation, dedicated scrapers quick reference (the
  endpoint parameter lists quoted in section 2)
- Oxylabs Kroger Scraper API product page
- Oxylabs Walmart Product Data API product page
