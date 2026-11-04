# Every route to a complete entry, and what autonomy actually needs

2 November 2026. This supersedes the "What is feasible without new
entitlement" section of `PRODUCTION_ROUTE.md`, which is narrower and older.

Read the first two sections before the table. The table is a list of options;
the two sections are the reason the list looks the way it does.

## The one thing that blocks both contests

Five of the twenty-two fields are store-bound facts the retailer renders on
its own pages and nowhere else:

| Field | Where it exists |
|---|---|
| `ppm` | the rendered product or search card. Walmart renders it in cents |
| `volume_deals_description` | the rendered offer text, verbatim |
| `volume_deals_price` | the rendered offer price |
| `digital_deals_description` | the clipped-coupon surface, behind an account |
| `digital_deals_price` | the same |

`sub_category` is a sixth, partly. It is populated, from the Kroger API's own
category label, so it is an observed value and not a gap. But the label is not
the listing page: the retailer's taxonomy has 184 subcategories and 238 leaves
that the API labels never name, so the field says less than the client's
"Category + ALL subcategories" scope asks for. Only a listing page gives true
membership.

Everything else — title, weight, regular price, sale price, UPC, brand, image,
URL, category root — a documented API gives us, store-bound, unattended,
today. That is why 28,549 Mariano's records exist and are store-verified, release 20261103T175940Z_426c12e8 of 3 November, superseding the 26,166 produced outside the runner.

The six above are the whole problem, and no amount of engineering moves them.
The Kroger public API does not carry a rate or a coupon term, and an
independent client library that claims to wrap every public endpoint lists
Authorization, Products, Locations, Cart and Identity, with no coupon
endpoint anywhere. Walmart's provider holds the rate as two split fields and
refused in writing on 1 November to render the string.

So a route is only interesting if it answers one question: **does it reach a
rendered retailer page, lawfully, unattended?**

## Why the obvious answer is unavailable here

The rendered pages are not forbidden. Mariano's `robots.txt`, captured 1
November, disallows checkout, accounts, clickstream, the recipes API, PDFs,
in-store pages and the store locator. It does **not** disallow `/pl/` listing
pages, `/p/` product pages or `/search`, and it advertises the sitemap we
read on 2 November.

What refuses us is not the rules, it is the egress. Measured, not assumed:

- 30 October, two Azure regions and a second cloud provider: Mariano's closed
  the connection with `ERR_HTTP2_PROTOCOL_ERROR` before any HTTP exchange;
  Walmart returned a PerimeterX challenge. A neutral control returned HTTP 200
  in 336 ms from the same container in the same run, so this is a retailer
  refusal and not a network fault.
- 2 November, a `curl` of `sitemap.xml` through a datacenter: the same
  pre-HTTP refusal.
- 2 November, the same URL in a browser on an ordinary residential
  connection: HTTP 200, five sitemap files read.

The standing position in `CLAUDE.md` is that no identity rotation, no
residential proxy routing and no bot-challenge defeat is built here, by any
name. That is not a reading of the brief and it does not change. It rules out
the three things that would otherwise make a datacenter reach those pages.

What it does **not** rule out is running the collector somewhere the retailer
does not refuse. That is option 4 below, and it is the only route in this
document that reaches all six fields unattended.

## The routes

| # | Route | Reaches the six fields? | Needs | Status |
|---|---|---|---|---|
| 1 | Kroger public Products API sweep, inside the collector | No | nothing new | **Running.** 28,549 records at the assigned store, release 20261103T175940Z_426c12e8, produced through the runner in the trial namespace |
| 2 | Kroger Catalog V2, partner tier | Unknown; it has a `unit` field nobody here has seen populated | a partner request, which is **not authorized** | Blocked by the client's instruction |
| 3 | Bright Data, the account already held | Walmart: the rate, as two split fields. **Mariano's: the provider states in writing that displayed price per measure and digital coupon fields are returned when publicly shown for the product and selected store** | a test against the *assigned* store, which has never been run | Walmart yes, 615 records. Mariano's **not blocked on the provider**: the single test used ZIP 60601, the DEMO-LAKESHORE placeholder, a week before Vernon Hills 60061 was assigned |
| 4 | The collector on a machine the retailer serves | **Yes, all six** | the client's decision, and a machine | Not built. See below |
| 5 | Another commercial provider, unspecified | Possibly | a new paid entitlement | Not pursued; superseded by row 8, which is a provider he already pays for |
| 8 | Oxylabs `marianos_product` / `marianos_search`, the account already held | **Undetermined, and this is the open question.** Takes `store_id`, `delivery_zip` and `fulfillment_type: pickup`, so the store context is a parameter. No documented unit-price or promotion field | 5 requests to find out, plus confirmation that his plan includes the dedicated banner targets | Not pursued until 3 November, because this document and the Oxylabs assessment both wrongly stated no dedicated Mariano's target existed |
| 6 | Deliver the fields the lawful routes carry, blank the rest, report the gap | No | nothing | **This is the current delivery** |
| 7 | Publish Kroger's `regularPerUnitEstimate` in a separate labelled column | Partly, and honestly | the client's say-so | Not built. See below |

### Option 8, in detail, because this document was wrong about it

Until 3 November this table had no Oxylabs row and `OXYLABS_ASSESSMENT.md`
stated that no dedicated Kroger or grocery target existed, so the only way to
use that account would have been `universal` fetching of `marianos.com`, which
the standing position refuses. **That was false.** `marianos_search` and
`marianos_product` are named targets with a dedicated parser, as are roughly
fifteen other Kroger banners, and they accept `store_id`, `delivery_zip` and
`fulfillment_type` with `pickup` among the documented values.

So the route was ruled out on a fact that was not true, and row 4 was being
called "the only complete one" without this having been checked. Row 4 may
still be the only complete one. It is no longer established.

What is actually undetermined is narrow. No output schema I could reach for
these targets mentions a unit price, a price per measure, or any promotion,
deal or coupon text. Those two fields are the whole of the enrichment gap. If
`marianos_product` returns them, then the statement repeated in every report
here - that no unattended route to displayed price per measure and retailer
deal wording exists - stops being true, and it closes with the store context
requested rather than assumed. Five requests settle it; the probe is specified
in `OXYLABS_ASSESSMENT.md`.

Two things not to overstate. It attests nothing about category coverage:
`marianos_search` takes a `query`, so it is term-filtered exactly like the
Kroger sweep and its output belongs in the trial namespace with
`coverage_attested = False`. And a dedicated target is still a vendor fetching
a page our own egress cannot reach; that is a narrower thing than arbitrary
proxy fetching and it is the same distinction already drawn for Bright Data and
for `walmart_product`, but it is not a bright line, and the wider judgement is
the client's.

Also unconfirmed: whether his plan covers the dedicated banner targets at all.
He named Classic Web Scraper API. If the targets sit outside that entitlement
the answer reverts to no, for reasons of access rather than capability.

### Option 4, in detail, because it is the only complete one

Run the collector on a machine the retailer serves — a small always-on box on
an ordinary connection, or the client's own hardware. Azure keeps the storage,
the checkpointing and the schedule; only the fetching moves.

This uses no evasion. No proxy, no rotated identity, no challenge answered.
It is one ordinary client on one ordinary connection, at a request rate well
under a human browsing, reading pages `robots.txt` permits.

What it would deliver that nothing else does: displayed `ppm` and verbatim
deal wording at scale, and true subcategory membership from the listing pages,
for both retailers.

Three things to be straight about before anyone calls it the answer:

- **It is still automated access.** The retailer refuses datacenters, which is
  reasonable evidence it would rather not be crawled at all, whatever
  `robots.txt` permits. That is a judgement for the client and his own
  counsel, not for us, and it should be made deliberately rather than arrived
  at because it was the only box left.
- **It is not what the brief says.** The brief says Azure. The honest reply is
  that Azure egress is refused by both retailers, measured from two regions and
  two providers, so "unattended in Azure" and "displayed price per measure" are
  in direct conflict and the client has to choose which he wants.
- **Digital coupon terms need a signed-in account.** Even on a served machine,
  the clipped-coupon surface is behind a login. That means the client's own
  account and his explicit instruction, and credentials stay with their owner:
  we would produce the command, he would run it. The 17 coupon terms collected
  on 24 October came from a signed-in session on his side.

### Option 7, in detail, because it is cheap and nobody has asked for it

Kroger's public API carries `regularPerUnitEstimate`. `CLAUDE.md` forbids it
in `ppm`, and that stays: `ppm` is the *displayed* rate, and an estimate is
not one.

But the rule governs what may go in `ppm`, not whether an observed API field
may be delivered under its own name. A separate column, named
`ppm_api_estimate`, carrying Kroger's own figure, labelled as an estimate from
the API and not a displayed rate, breaks nothing: the value is observed, it is
not reconstructed, and it is not presented as something it is not.

That would put a per-unit figure on most of the 28,549 records instead of 592
of them, with the displayed-versus-estimate distinction on the face of the
data. It is the client's call because it is his schema and his downstream
pipeline. It is the single largest improvement available for no new access.

Not done, and not to be done, until he says so.

## Autonomy: what is now true, and what is left

### Done

**The sweep runs inside the collector.** `--source sweep`, or `--spine sweep`
under `--source composite`. The route that produces the data now carries the
publication gate, retention reconciliation, trial and published namespace
separation, and resume. That was the client's fourth point on 2 November and
it needed nothing from outside.

**A scheduled run can complete.** Five of the 28 roots return nothing from
this API for a permanent vocabulary reason, so the zero-products gate would
have failed every run forever. `config/sweep_coverage.json` declares them with
the retailer's own taxonomy as the reason, they drop out of the configured
set, the release names them, and the run fails if one of them ever starts
returning products.

**The Azure job can select it.** `MARIANOS_SOURCE=sweep` resolves the store
from Kroger's own `/locations` response with the ZIP and street asserted,
passes the declaration, and deliberately does not pass `--authorized-source`,
because the public tier has no authorization to assert.

**The store columns cannot be invented.** They come from the Locations
response, never from a config file. The first sweep run shipped 18,351 records
with a blank `store_name`; that cannot recur.

### Left, in the order it matters

1. **Nobody has watched the schedule fire.** The deployment template exists
   and Azure execution is not hypothetical — three executions ran there on 28
   October — but the cron has never been observed running by itself across a
   week, and nothing has run in the client's environment. This is the weakest
   of the five evidence claims and it is weak for a reason that is about
   observation, not code.
2. **The sweep cannot resume across Azure executions.** Its checkpoint and raw
   responses live under `MARIANOS_SWEEP_WORK_DIR`, container-local by default,
   and each Container Apps execution gets a fresh container. The runner's own
   checkpoint is in Blob storage and does survive. Mounting a volume fixes it;
   `deploy_jobs.sh` does not mount one and no run has exercised the mounted
   case.
3. **A stopped run should still report.** A budget-exhausted or API-stopped
   sweep currently raises. For a twice-weekly job the right behaviour is a
   release that says what it reached and what it did not, which is a change to
   how `Budget.Exhausted` surfaces, not to any gate.
4. **187 products have no root to be delivered under, and this turns out not
   to be a mapping omission.** An earlier draft of this document said each was
   a one-line addition to `config/category_map.json` once someone looked at
   the labels. Someone looked. The labels are:

   | Records | Retailer label |
   |---:|---|
   | 117 | `Party` |
   | 38 | `Halloween` |
   | 10 | `Entertainment` |
   | 10 | `Thanksgiving` |
   | 4 | `Automotive` |
   | 3 | `Other` |
   | 2 | `Apparel` |
   | 1 | `Furniture` |
   | 1 | `Holiday & Seasonal Goods` |
   | 1 | `Sporting Goods` |

   Not one of those is any of the client's 28 roots. They are seasonal and
   non-grocery departments he did not ask for, plus three products the
   retailer itself labels `Other`. So the map is not missing ten entries;
   these are products outside the requested scope, and mapping them anywhere
   would be inventing a category assignment from the category the product is
   *not* in.

   What is genuinely open is what should happen to them, and it is the
   client's call because it is a scope question rather than a defect. The tool
   kept them with an empty `category`, which honours the rule that a product
   is never dropped for a missing value. The runner is category-driven, so
   under that route they are reported and not delivered. Those are two
   defensible readings of the same rule and we should not pick between them on
   his behalf.

   **Answered on 4 November.** He chose a third thing, narrower than either:
   retain their original retailer labels and identities in a separate
   unmapped/out-of-scope reconciliation with source paths and counts; invent no
   root assignment; discard no historical observation; and any eventual mapping
   must be supported by the retailer taxonomy. That is implemented in
   `tools/out_of_scope_reconciliation.py`, which re-indexes the persisted raw
   responses, so it reconciles a published release without collecting anything
   and without reading a credential, and refuses if its own counter and the
   retained rows disagree.

   **The table above describes the superseded 26,166 set and must not be quoted
   for the delivered one.** The delivered release has **166**, and the counters
   reconcile exactly: 28,549 served plus 46,073 duplicate identities plus 166
   out of scope equals the 74,788 products seen, over 1,833 indexed responses.

   **The label set is seasonal and turns over between runs**, which bears
   directly on his condition about the retailer taxonomy. Measured at the same
   store three days apart, `Halloween` fell from 38 products to 3, `Christmas`
   went from absent to 11, and `Travel & Luggage` appeared with 1 — two labels
   the 31 October sweep never saw at all. So this is not a fixed list waiting to
   be mapped. A static map of the seasonal departments would be stale within
   days and would need maintaining indefinitely, which supports keeping them in
   a separate reconciliation rather than mapping them.
5. **The 326-product question is open and answerable today.** 326 of the 890
   products in the retailer's own SEO sitemap are absent from our data.
   `tools/resolve_sitemap_gap.py` decides, per id against this store, whether
   each is a coverage gap or simply not carried. It needs the Kroger
   credentials, so it is a command for their owner to run:

   ```bash
   cd marianos
   set -a; . ./.env.kroger; set +a
   python3 tools/resolve_sitemap_gap.py --location-id 53100502 --probe-only
   ```

   One request. If it reports `probe: worked`, rerun without `--probe-only`
   and `--out reports/2026-11-02-sitemap-gap` for all 326. The
   `carried_and_missed` count is the first hard lower bound this project has
   on what the term sweep misses. It is a lower bound and not an estimate: the
   890 are an SEO subset the retailer chose, not a random sample.

## What this document does not establish

- That option 4 is acceptable. It is lawful as described and uses no evasion,
  and it is still automated access to a site that refuses datacenters. That is
  the client's decision and his counsel's, not a technical finding.
- That option 7 is acceptable. It is compatible with the no-unobserved-value
  rule as argued above. It changes his schema, so it is his call.
- That any of this resolves the acceptable-use question in
  `ACCEPTABLE_USE_POSITION.md`. It does not. `publication_eligible` is still
  false and that decision is still open.
- That bringing the sweep inside the collector produced PPM or deal wording.
  It did not, and it was never going to. It fixed how the assortment is
  produced, not what the public tier carries.
- Any dated milestone. Dates are set by the account holder.
