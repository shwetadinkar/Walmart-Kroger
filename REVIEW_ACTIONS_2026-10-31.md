# Client review of 31 October: what to fix, and how to know it is fixed

Written for whoever picks this up next. Read `CLAUDE.md` first; every rule there
applies. Nothing here needs a retailer, a credential, or a decision from the
client, with one exception noted under BLOCKED.

The review was an offline acceptance pass, not a skim. The reviewer replayed
the test suites, rebuilt the Walmart ledger from the supplied snapshots,
replayed the 34 Mariano's records through this repository's own `make_record`,
and wrote his own fixtures to probe edge cases. Treat every finding as
reproducible, because each one was reproduced before it was reported.

## Confirmed working. Do not redo these.

Walmart: all 160 tests pass offline. A two-category fixture retained all four
products including an unavailable one and an available-but-unpriced one. The
unattested OPD source is refused full publication. Both malformed-manifest
cases exit 2. Approximate-weight examples are excluded and a fixed-size family
pack is retained. All seven branches listed as ancestors in `RELEASE.md` are
ancestors under full history. The reissued evidence archive verifies: 57
declared, 57 verified, and a rebuild reproduces 654 identities and all 615
submitted identities including 144 pickup-unavailable. Verified local-price and
direct-PPM counts remain zero, as stated.

Mariano's: all 63 root manifest entries match. The export has 34 distinct UPCs,
the 22 ordered string fields, and empty `gupc` and `unit_price`. All 34 titles,
UPCs, regular prices and literal PPM strings, and all 7 populated sale prices,
occur in their saved product observations. Every non-empty line of all 17
coupon descriptions appears in the matching expanded coupon observation,
including quantity, household, expiry and clipping terms. Each observation
shows Pickup at the West Loop store.

## The assigned store: Vernon Hills 53100502

Confirmed by the client on 31 October.

| | |
|---|---|
| Store | Mariano's Vernon Hills |
| Address | 1720 N Milwaukee Ave, Vernon Hills, IL 60061 |
| Division / store | 531 / 00502, combined `53100502` |
| Fulfillment | PICKUP |

It is **not** West Loop. Every artefact in this repository so far targets West
Loop `53100508`, two characters away from the assigned id. Check the id on
every command.

Three instructions came with it:

- **Verification must come from the returned source responses**, not from
  configuration. His words: a configured ID or output label alone is not
  verification. The store, the address and the fulfillment context governing
  the collected prices and offers must all be evidenced in what the API
  actually returned. `resolve_store` already refuses a response whose
  locationId or zipCode contradicts the request; extend it to assert the
  street address too, and record the pickup context per record rather than
  only at run level. The 22 fields are fixed, so "per record" means a sidecar
  keyed by identity (`pickup_context.json`), not a column.
- **Do not relabel the West Loop work.** The 34-product sample and its
  observations stay labelled West Loop. They are a separate store and a
  separate date.
- **The demonstration minimum is 500 genuine distinct products in total**,
  drawn from the required scope. It is not 500 per category. Full production
  must still cover every required category, applicable subcategory and
  pagination with no demonstration cap.

He also set the order of work explicitly: reconcile the authoritative Mariano's
release with the accepted coupon and unavailable-retention fixes first, then
identify the corrected version and the next dated milestone. That is PART 0 and
PART A below, before any collection.

Resolve and confirm the store before the first sweep. This fetches no products:

```bash
python3 tools/kroger_full_sweep.py --zipcode 60061 --address-contains Milwaukee
```

Everything else below is independent of the store.


---

# PART 0. The retention principle. Read this before touching anything else.

Stated by the client on 27 October for Mariano's and again on 31 October for
Walmart. It overrides any instruction elsewhere in this document that conflicts
with it, including the pickup-offer test described under PART A.

**A product is never removed from the delivered dataset because a field is
missing or a status is unfavourable.** Not for being unavailable, not for
having no price, not for having no qualifying pickup offer, not for a missing
source UPC. Those are facts about the observation, recorded as such. They are
not grounds for deletion.

What must change, in every place it was violated. This list was corrected
against the code on 31 October; the first version named the wrong locations and
stopped at four.

- `api_trial.normalize` raises `NO_QUALIFYING_LOCAL_PICKUP_OFFER` and the sweep
  quarantines the row out of the dataset. The qualifying-offer check must
  become a classifier, not a filter: the product stays in the 22-field export
  with empty strings for the values that were not observed, and the reason is
  recorded beside it.
- `api_trial.import_snapshot` on `marianos-live-api-west-loop` excludes
  unavailable records, under the reason `WEBSITE_PICKUP_UNAVAILABLE_OR_UNVERIFIED`.
  It must not.
- `temporal_enrichment.py` on `marianos-fresh-runs-category-evidence` already
  keeps the row but blanks its observed values on unavailable products. It must
  keep the values too.
- Walmart `_to_raw` blanks `currentPrice` and `unitPriceDisplay` on unavailable
  rows, destroying values that were observed. See B3.
- `make_record` refuses a whole product for one bad value: unverified or
  cashback deal text, a deal price with no description, a malformed price, a
  blank title, a URL on another site. A refusal must cost that value, not the
  product. `make_retained_record` decides that; `make_record` stays the judge
  of what is valid.

Also required by the same instruction:

- Previously observed products are retained indefinitely, with their original
  observation dates, and must remain distinguishable from fresh observations.
  A product absent from a later run does not disappear; it is carried with its
  earlier date.
- A missing source UPC must not remove the product, so identity cannot depend
  on UPC alone. Identity is the retailer product id from the product URL, with
  the UPC when no URL was observed, and `identity_basis` records which. A
  product with neither cannot be carried, because the 22 fields have no other
  place to hold an identity; it is held in quarantine with its reason.
- The acceptance status that currently marks audit preservation as PASS while
  the accepted output excludes unavailable products is wrong and must be
  corrected.
- Supply worked examples: available becoming unavailable, a missing price, and
  a product absent on the next run.

Retention can only reach what was returned. The Products API requests carry
`filter.fulfillment=ais,csp`, so a product Kroger holds for neither in-store nor
curbside at the location never arrives, and every run report says so.

The distinction that matters: the one rule in `CLAUDE.md` is never publish a
value that was not observed. That governs *values*. It has been misapplied to
*rows*. An unobserved value is an empty string; it is not a reason to delete
the product it belongs to.

## The next milestone, in the client's own words

He named it on 27 October, and it is smaller and more achievable than 500
records across 28 roots: **one representative category collected unattended
through every applicable subcategory, page and variant, with coverage
reconciliation and correctly retained unavailable products.** Then extend
across the remaining roots. A bounded keyword API run and manual category
observations do not establish uncapped production, and the ledger correctly
reports zero roots accepted for unattended full extraction.

---

# PART A. Mariano's release reconciliation

**This is the most serious item.** The release named to the client excludes
`marianos-fresh-runs-category-evidence`, which carries accepted fixes. Two
regressions follow, both reproduced by the reviewer.

## A1. The cashback fix is missing

On the named release, `schema.py` searches the whole digital description:

```python
if re.search(r"\b(?:cashback|cash back)\b", dig_desc, re.I):
    raise RecordRejected("CASHBACK_MISCLASSIFIED_AS_DIGITAL")
```

Commit `5b991c7` on `marianos-fresh-runs-category-evidence` narrowed this to a
dedicated benefit field (`cash_benefit_text`) precisely so that a coupon whose
genuine terms say "No cash back" is kept, while an actual cashback offer is
still rejected. The rule exists because the shared requirements say Walmart
Cash, cashback and manufacturer offers must not be treated as immediate digital
price reductions. "No cash back" is a restriction, not an offer.

Consequence: replaying the 34 supplied records through this release rejects all
17 coupon-bearing records.

Port `5b991c7` and its test. Then add a regression that pins both directions:
a description containing "No cash back" in its terms is **kept**, and a real
cashback benefit is still **refused as a digital deal**. Under PART 0 that
refusal costs the field, not the product: `make_record` raises, the digital
fields are emptied, the product stays, and the reason is recorded in
`value_refusals`.

## A2. Retention reconciliation is not called

In a two-category synthetic repeat through the real `Collector`, the first run
published four identities and the second published three, dropping a product
absent from the second observation, and the second report was still marked
validated. The earlier retention reconciliation is not invoked on this release.

Restore it. Eligible products previously observed must be preserved
indefinitely with their original observation dates, and must remain
distinguishable from fresh observations. A run that silently loses a
previously published identity must not validate.

## A3. Produce one authoritative Mariano's release

Combine, on one branch: the new sweep and composition work, `5b991c7`, the
retention reconciliation, the current observation importer, and the recovery
harness. Do not switch wholesale to either existing branch; both are
incomplete. `marianos-fresh-runs-category-evidence`'s runner deletes the
unresolved-offer and provenance reporting, and its `kroger.py` deletes the
acceptable-use comment. Its acceptance of blank prices and in-store-only offers
is not a defect: under PART 0 those products stay, classified.

Demonstrate both regressions above passing **on that exact commit**, and record
the commit id.

Done: release commit `16a6f03838a22a822a118977004086976d1a1de0` on
`marianos-api-sweep-2026-10-31`.

---

# OPEN. Two value questions for the client

Neither is ours to decide. Both are flagged in `marianos/RETENTION_POLICY.md`,
and the code holds its current behaviour until the client answers.

1. **Website and API disagree on a price.** The disputed fields are emptied and
   both values stay in the audit, because publishing either would settle the
   conflict silently. B3's rule points the other way: record uncertainty in a
   separate field rather than emptying the value.
2. **Sold-by-weight prices.** These rows keep the price Kroger returned, with
   `sold_by` beside them, but it may be per pound rather than for the stated
   size. One probe row reads `14.99` for `7.5 oz`.

---

# PART B. Walmart

## B1. The bounded probe is not bounded

`tools/opd_bounded_probe.py` advertises a cumulative deadline and byte budget
and enforces neither through completion.

- A six-request run finished at 601 seconds against a 600-second ceiling and
  returned exit 0 with `stopped_on_failure=false`. The clock is only consulted
  when dispatching another request.
- `opener.open` uses a fixed 60-second timeout unrelated to the run deadline.
- Bytes are not counted as received. An 11-byte response refused against a
  10-byte limit recorded zero bytes. A mocked HTTP 503 body of 100 bytes also
  recorded zero.
- `gzip.decompress` expands the whole body before row limits apply, so the
  decompressed size is unbounded.

Enforce a whole-run deadline across reads, decompression, parsing, evidence
writing and cleanup, with bounded finalization rather than an abrupt exit.
Count bytes as they arrive, including on refusal and on error responses, and
keep the failure receipt accurate. Bound decompressed bytes, not only
compressed ones.

## B2. Transport success is being reported as a result

With a matching pickup-store locator response but every returned price row
belonging to store 999, the probe returned exit 0, zero matched store-price
records, and `every_price_row_matches_requested_store=true`.

That flag is vacuously true over an empty set. This is the same defect class as
the earlier `all([]) == true`; fixing it in one place did not fix the pattern.
Any "all rows satisfy X" flag must be false, or absent, when no rows were
examined.

Require the intended matched sample before reporting success, or mark the
result explicitly incomplete. Do not treat the first five catalog rows and
first 100 price rows as evidence that a missing match is absent from the whole
feed. Preserve sanitized original locator, catalog and price evidence including
snapshot identity and capture times; the current receipt holds mostly selected
values and field counts. Store availability in the locator does not establish
the fulfillment or the regular/sale meaning of every price row.

## B3. Observed values are being destroyed on unavailable products

`_to_raw` blanks `currentPrice` and `unitPriceDisplay` whenever availability is
not AVAILABLE. In the reviewer's fixture an unavailable source row carrying
9.99 and a literal `83.25 c/oz` produced two empty fields.

This was a judgement call made when the retention fix landed, and it was wrong.
The rule is never publish a value that was not observed; it is not suppress a
value that was observed. Unavailability does not establish that a present
source value is fabricated or stale.

Preserve observed values with their observation context. Where the meaning is
uncertain, record that uncertainty in a separate field rather than by emptying
the value. Historical values must stay distinguishable from fresh observations.
Still never calculate PPM.

## B4. Approximate-weight exclusion is too broad

The title pattern on both retailers rejects `Rice 16 oz, approximately 8
servings`. An approximate serving count is not an approximate product weight,
and the shared requirements scope the exclusion to weight wording.

Narrow the pattern so it recognises approximate *weight* rather than
approximation in general. Add a regression holding fixed-size products with
approximate serving counts alongside the existing positive exclusions, real
family packs and multipacks.

## B5. The composed source is not deployable

- The default CLI constructs an unavailable crawl placeholder. There is no
  working offer enrichment implementation behind it.
- `CompositeSource` does not forward `coverage_attested`, so wrapping an
  otherwise attested source causes the full-publication gate to reject it.

Fix the delegation without weakening the gate. This is the third attribute
missed on the same class after `unresolved_offers` and `reset_unresolved`;
audit the whole delegation surface rather than patching one more attribute, and
add a test that fails if a new attribute is added to the spine interface and
not forwarded.

Then show the executable source implementations, and the product, store,
fulfillment and time binding for every contributed field. An entitlement would
not by itself supply the missing offer collector or validate production
coverage.

---

# PART C. Mariano's evidence package

## C1. Missing listing observation

Seven recovered sizes cite `LISTING_03.txt`, which is not in the package.
Supply that original observation with its timestamp and hash, or state plainly
that it cannot be produced. The recovery note alone does not verify the bytes.
Preserve the observed pack and count identities.

## C2. Nested manifests reference absent material

The root manifest describes the reduced package accurately, but nested
manifests still refer to 8 missing Batteries files, 14 missing Azure files and
18 missing coupon files. Label historical or superseded items as such rather
than resending every obsolete file.

Specifically absent and requested: `FRESH_PAGE_ORIGINAL.json`,
`FRESH_RECEIPT_ORIGINAL.json`, `FRESH_STORE_ORIGINAL.json`,
`RESUMED_PAGE_ORIGINAL.json`, `VERIFIED_STORE_ORIGINAL.json`,
`EARLIER_SELECTED_5.json`, `FRESH_SELECTED_5.json`, and the actual
699,424-byte checkpoint. A stated matching hash is not the checkpoint bytes.
Include it or give the exact securely accessible location.

## C3. Azure claims are not independently verifiable

The receipts in the package are reserialized summaries while `RESULTS.md` says
original files and screenshots are included. Either supply the originals or
correct `RESULTS.md`. Map the trial's source commit `7c49e25` and image to the
reconciled release. Keep the five-product API trial, the 34-product
browser-assisted sample, and full deployment acceptance clearly separate.

## C0. The promotion README contradicts its own output

The README says chocolate ice cream `0007457001400` was retained and bars were
withheld, while `enriched-review/products.json` and the terms index retain bars
`0007457001310`. Correct the index and documentation against the raw evidence
rather than against the README. Preserve the observed November 3 / November 4
expiry discrepancy as a discrepancy; do not pick a date without evidence for it.

## C5. Keep the later implementation distinct from the deployed baseline

Commit `738eb03ae0caf2217008b811b60f16f182e67876` is a later implementation and
must not be presented as the deployed baseline. Offline test results, the two
fresh five-product cloud runs, an actual forced interruption and resume,
failed-run publication protection, and twice-weekly scheduled execution are
five separate results and must be reported separately.

## C4. `BLOCKED_SOURCE.json` contradicts the final collection

It records three successful products and 92 remaining; the final set is 34 plus
61 pending. Preserve the original refusal record unchanged and add the
chronology explaining the later observations and how collection stopped. The
saved refusal contains an Access Denied page with no independently captured
HTTP status; keep that distinction explicit.

---

# PART D. Smaller corrections

- The system and sources document cites 189 tests. Current counts are 160
  Walmart and 133 Mariano's. Any client-facing count must be measured at the
  commit being described, not carried forward.
- `image_url` and `store_logo` are empty across all 34 Mariano's records.
  Permitted by the schema, but populate them where the source supplies them.
- Published product URLs must carry no query string. The Kroger
  `productPageURI` includes a `cid` tracking parameter containing our API
  client id. Raw captures keep it by design and must not ship.
- Brand classification still unresolved from a partial sample: `Bakery Fresh`,
  `Bakery`, `Smart Way`, and the apostrophe-less `Roundys`. Settle these from a
  full run rather than by guessing.

---

# How anything here is considered done

Per `CLAUDE.md`, and without exception:

1. Every change has a test, and every test is mutation-checked by reverting the
   change and confirming the suite goes red.
2. Direct and pytest counts agree for both collectors.
3. Tests assert on something that changes. A test that passes with and without
   the fix proves nothing.
4. Client-facing counts and claims are measured at the commit they describe.
5. Where a finding was a judgement call rather than a bug, say so in the commit
   message and say what changed the judgement.

# What must not be done

Do not weaken the publication gate to make the composite pass. Do not calculate
PPM from price and size. Do not fill a field because it looks empty. Do not
widen a pattern to make a test pass. Do not report a flag as true over an empty
set. Do not run a collection sweep before the store is confirmed. Do not
request entitlement or registration; the client's instruction not to register
remains in force.
