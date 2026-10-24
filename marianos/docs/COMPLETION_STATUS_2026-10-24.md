# Verified continuation and remaining acceptance work

The protected Azure export contains 650 unique products, 244 sale prices and exactly
22 ordered string fields. It remains an API keyword trial, not a category-complete
submission. `submission_ready` remains false. Walmart code and resources are outside
this change.

## Fresh execution implementation

`run_context` derives a stable run ID from Azure's documented execution name. A retry
of that execution resumes its checkpoints; a different execution gets a fresh ID.
Missing Azure execution metadata fails closed. Legacy fixed IDs cannot override
Azure execution identity. Execution receipts persist attempted HTTP requests before
network activity, survive retries, and verify immutable object hashes before skipping
completed work. Existing per-store locks and renewable Blob leases remain in use.
An older completed retry cannot replace a newer successful pointer.

Two actual local API executions selected five records each. Each made three HTTP
requests and one product query; observations had different timestamps. Replaying the
first completed execution made zero requests and preserved the second pointer. These
are **local live tests**, not evidence of two new Azure executions. API search pages
contained up to 50 source products; five is the selected export size.

`azure/freshness_rollout_plan.json` proposes two manual Azure pilots with a separate
`freshness-checks/` output namespace. It is not a deployment template and has not
been applied. The existing 650-product `trials/53100508/` namespace is protected.
The new immutable image digest must be filled only after CI builds it. No permission,
identity, environment, storage account or Walmart job change is proposed.

## Category source and traversal

All 28 original root URLs were checked in the selected West Loop browser context.
Their main content exposed 333 distinct category URL strings (331 after normalization); this is discovery evidence,
not complete traversal. `/d/dairy` and `/d/breakfast` returned missing pages.
Retailer breadcrumbs led to `/pl/dairy-eggs/02` and `/pl/breakfast/03` respectively.
The original CSV is preserved; route resolutions are recorded separately.

A live AA Batteries leaf listing displayed 19 results and 19 unique product links,
without a Load More control; its Departments dialog exposed no descendant radios.
This establishes one bounded leaf-listing pilot, not complete Batteries or all roots.
Sponsored flags are retained: sponsored products can be part of the stated result
count. The older Fresh Fruit terminal listing still has a count discrepancy and
must not be marked complete.

`category_traversal` persists its queue and content-addressed evidence, verifies
hashes on resume, and separates discovery from observation. `rendered_categories`
implements normal public DOM navigation, Load More growth checks and Departments
radio discovery. It stops on access restrictions, wrong store, unexpected category
redirect, changing result counts and budgets. It uses no hidden retailer endpoint,
proxy service or challenge bypass. Unit tests use synthetic drivers and do not prove
live DOM-driver operation or completeness. The Python browser driver still needs an
end-to-end live run, a browser-session/bootstrap wrapper, exhaustive landing-page
discovery and production packaging before unattended deployment. Landing pages and
coupons remain explicit unresolved paths. No synthetic fixture is submission proof.

The user confirmed that written collection permission exists. The Bright Data Kroger
dataset's Mariano's compatibility is not established; no new provider job was run.

## Evidence enrichment

`temporal_enrichment` requires exact product path, store, local ZIP/address, timezone
and a maximum one-hour observation gap; then checks source prices and pickup.
Comparable price conflicts quarantine the record with both sources. Stale website
observations are rejected without discarding a valid newer API record. PPM is copied
literally, never calculated. Digital fields require complete observed terms; unknown
fields remain empty. A separate review export never overwrites its inputs.

The old 204-page website sample predates the Azure observation by several hours.
Of those observations, 203 match current UPCs but are too old; one UPC is outside the
650-product baseline. Applying the conservative review retained 650 API records,
quarantined zero and added no stale PPM or promotions. Fresh paired observations and
full coupon-detail capture remain acceptance work.

A fresh Energizer offers dialog exposed separate $1 Cash Back and $1 digital coupon
offers, expiry text and Sign In To Clip. It did not expose complete eligibility,
limits or terms in that dialog. Cash Back is not treated as an immediate sale price;
the incomplete coupon is retained as pending evidence, not populated final fields.

## Additional stores, recovery and monitoring

`config/stores_verified.json` contains the one live-verified store. Additional stores
can be configured, but must pass the official Locations API ID/ZIP/address/chain
verification and independent pickup/context/canary tests before being enabled. Demo
stores in existing fixture configs do not establish real multi-store acceptance.

For an interrupted API execution, retain the same execution identity and budget.
For a genuinely fresh observation use a new execution identity. Never delete a good
pointer to repair a failed run. A corrupted receipt/object, changed configuration or
material yield drop requires investigation rather than publication. Category access
blocks persist a durable stop; do not resume that run automatically.

Monitoring must include failed/timed-out Azure executions, missing expected UTC runs,
source request counts, records, yield versus last success, store/canary failures,
remaining coverage paths, incomplete coupons and observation age. Existing execution
history/logs are available; alert rules and notification destinations have not been
created. Enabling a billable alert or expanding permissions requires approval.

## Costs and schedule limits

Two runs per week average 8.70 runs per month. At the observed 55-second Azure trial
duration, 0.5 vCPU and 1 GiB, that is approximately 239 vCPU-seconds and 478 GiB-seconds
monthly for the API trial only. At the 600-second timeout ceiling it would be about
2,609 vCPU-seconds and 5,218 GiB-seconds. Full browser/category collection runtime has
not been measured; these numbers cannot be presented as its cost forecast.

[Microsoft pricing](https://azure.microsoft.com/en-us/pricing/details/container-apps/)
bills jobs at active compute rates only while running, and the stated consumption
free grants are shared per subscription. Request charges do not apply to jobs.
The shared Walmart workload may consume grants. Monthly cost is billable vCPU-seconds
times the actual South India CPU rate plus billable GiB-seconds times its memory rate,
then [Blob capacity/transactions](https://azure.microsoft.com/en-us/pricing/details/storage/blobs/),
logs, retention and any separately approved services. The public pricing page did not
render numeric regional rates in this inspection, so no fixed dollar quote is claimed.
No additional paid provider use or chargeable service was started in this continuation.

The proposed schedule is Monday/Thursday 06:00 UTC (`0 6 * * 1,4`), currently disabled.
It must remain disabled until distinct Azure executions demonstrate fresh source
observations, the production scope is approved and monitoring/budgets are verified.

## Exact demonstration script (recording outstanding)

1. Show the preserved 650-product JSON and audit: unique UPCs, exact field order,
   store ZIP 60661, empty gupc/unit_price, 244 observed sale prices and enrichment gaps.
2. Show baseline Azure execution `marianos-westloop-api-pilot-yrmb6iq` succeeded in
   55 seconds, and export run `b70ded437414abb646e0`; explain the two IDs differ.
3. Show local freshness evidence: different run IDs/timestamps, three requests each,
   and a completed retry with zero requests and no pointer rollback.
4. Show category-root report, original missing routes and retailer breadcrumb
   resolutions. Show the 19-result AA Batteries leaf and its empty descendant list.
   Explicitly state all 28 roots are not complete.
5. Show stale-enrichment rejection, price-conflict quarantine tests and last-good
   preservation tests. Synthetic tests are labeled as tests.
6. After separate approval and new image build, run the two bounded Azure pilots,
   inspect receipts/output hashes and source observation times, then review schedule
   activation separately. Do not show secret values.

No recording has been created. Final category-complete data, fresh enrichment,
coupon completeness, multi-store live acceptance, new Azure execution evidence and
scheduled-run evidence remain outstanding.

Sources: [Azure execution variables](https://learn.microsoft.com/en-us/azure/container-apps/environment-variables),
[Azure jobs and UTC schedules](https://learn.microsoft.com/en-us/azure/container-apps/jobs),
[official Kroger product filters](https://www.postman.com/kroger/the-kroger-co-s-public-workspace/request/cx3ttq9/product-list).

## Later live category validation

Batteries root pagination ended at 97 card placements and 72 unique product links against 95 stated results. All nine displayed child categories were then traversed to terminal listings and their empty descendant branches verified. Their deduplicated union contains exactly 95 product links. The ledger can reconcile an exhaustive descendant union only when every child passes, the union matches the parent result count, and every parent-observed product is included. This proves listing enumeration for one of 28 roots; UPC and product export acceptance are separate.

Five category-discovered products were independently requested through the official product-details route, with filter.locationId on every request (seven HTTP attempts total including OAuth and store verification). The public API documentation says batch filter.productId ignores other filters; it is not used for store-local prices. Five fresh product pages displayed matching UPC, West Loop context, pickup availability and literal PPM. Four records retained PPM after conservative merging. One was quarantined because the API regular price was 17.99 and the displayed website regular price was 17.98. An incomplete volume-offer teaser remains pending. The protected 650-product baseline is unchanged.

The expanded local suite passes 112 tests. The previously built image from commit 8fe3492 passed 105 CI tests and contains the already-reviewed fresh-execution API fix; later category/product-detail refinements require a subsequent image build before deploying those refinements.
