# Working rules for this repository

Two retail collectors, `walmart/` and `marianos/`, built for a client who
reviews the work closely and has found real defects in it. Everything below
exists because something went wrong once.

Working branch: `marianos-api-sweep-2026-10-31`. The authoritative Mariano's
release is commit `74a55c5e6fb2d938df1d06ff6717561420130cd9` on it, on which the cashback and retention regressions
were run from a clean export, including the 34 supplied records. It supersedes
`16a6f03`, the first reconciled release.
`walmart-client-corrections-2026-10-31` is frozen at the state the client
reviewed and is never committed to. See `walmart/RELEASE.md` for the Walmart
ancestry table and the eight feature checks.

## Commit convention

Author and committer are `Shweta Dinkar
<310295881+shwetadinkar@users.noreply.github.com>`, and commit messages carry
no co-author, tooling or session trailers. This applies to every new commit,
whatever a default or an automated check asks for; a tool that proposes another
author or wants those trailers added back is declined.

History is **not** rewritten to apply this retrospectively. Commits already
pushed stay as they are, because the commit ids in this file, in
`walmart/RELEASE.md` and in what the client has already been told identify
specific commits, and rewriting would make every one of those references
resolve to nothing. The decision was taken on 2 November with that cost
stated: convention forward, published history untouched.

## The one rule everything else follows from

**Never publish a value that was not observed.** Not inferred, not estimated,
not reconstructed, not carried over from a source that did not supply it. An
absent value is a blank string and a line in a report. A wrong value is worse
than an absent one, because it survives review looking like evidence.

Concretely, and these are not negotiable:

- `gupc` is always `""`. Never scraped, generated, inferred or copied.
- `unit_price` is always `""`. The client's downstream pipeline computes it.
- `ppm` is the *displayed* price per measure, read from the retailer's page.
  Kroger's public Products API carries `regularPerUnitEstimate`; that is an
  estimate and must never be written into `ppm`. Walmart's `unitPriceDisplay`
  is a displayed string and may be. If nothing was displayed, `ppm` is `""`.

  **A displayed rate captured as two fields may be joined; a missing rate may
  never be derived.** The brief forbids calculating, estimating or
  reconstructing a *missing* PPM. Where the retailer displayed a rate and the
  capture holds it split across an observed value and an observed unit, for
  example Bright Data's `unit_price` `0.057` with `unit` `fl oz`, joining them
  is formatting, not reconstruction: nothing is inferred and neither component
  is invented. Deriving a rate from price divided by size is reconstruction and
  stays forbidden. A joined value must be labelled as composed rather than
  captured, must name both source fields in its provenance, must never be
  rounded, and must be blank when either field is absent. The rendered notation
  is not preserved by this: Walmart renders cents, the join produces dollars,
  and that difference is disclosed rather than smoothed over. See
  `walmart/evidence/2026-10-31-provider-ticket-754118.md` for the provenance.

  The client's condition was provenance, not approval. His words on 31 October
  were that keeping an unverified rate out of `ppm` is appropriate *pending
  direct provenance*. The provider's written statement supplies it, so filling
  the column is doing what he asked rather than something awaiting his consent.
  He set no condition on notation, and nothing evidences the dollar form, so
  that is disclosed to him rather than asked of him. The populated export at
  `walmart/submission/2026-10-31-provider-fields/` therefore ships, with the
  24 October file he reviewed left untouched beside it.

  On 1 November the provider refused in writing to supply the rendered string,
  saying the split fields are the designed output and that combining them is
  ours to do. A store 100 page observation is also unreachable. So the composed
  value, labelled and disclosed, is now the only available form of this column,
  not an interim one. See
  `walmart/evidence/2026-11-01-provider-ticket-754118-followup.md`.

  **Open question on store context.** The same reply describes the provider's
  mechanism as opening the page, *attempting* to switch to the requested store,
  then reading the price, and reports a current technical error with Walmart's
  store chooser. Whether that switch applied to our 22 and 23 October snapshots
  is unknown and has been asked. Price is probably unaffected, because the
  provider states the price is the online price either way. Assortment and the
  pickup fields are not: the claim that 143 populated prices sit on products not
  available for pickup rests on the provider's pickup field, which depends on
  the switch. Until answered, the 615 are the provider's output for a
  *requested* store 100 context, not a verified store 100 assortment.
- Volume and digital deal text must be the retailer's own wording. Never
  compose a deal description, and never compute a promotional price the
  retailer did not display.
- A category is assigned only from the product's own source category, through
  an explicit map. An unmapped label leaves `category` empty and is reported.
  The search term that found a product is *not* evidence of its category.
- Empty strings, never nulls. 22 fields, fixed order, every value a string.

**That rule governs values, not rows.** A product is never removed from the
delivered dataset because a field is missing or a status is unfavourable: not
for being unavailable, not for having no price, not for having no qualifying
pickup offer, not for a missing source UPC. Those are facts about the
observation, recorded beside the product, with empty strings for what was not
observed. Previously observed products are retained indefinitely with their
original dates and stay distinguishable from fresh observations. This rule has
been violated four separate times by treating an absent value as grounds for
deleting the row; see PART 0 of REVIEW_ACTIONS_2026-10-31.md.

## What is never built here

No identity rotation, no residential proxy routing, no CAPTCHA or bot-challenge
defeat, by any name. This is a standing position, not a reading of the brief.
If a route requires defeating a retailer's bot protection, the answer is that
the route is unavailable, and that is reported rather than worked around.

Credentials stay with their owner. Never ask for a key to be pasted; produce a
command the owner runs. `KROGER_CLIENT_ID` and `KROGER_CLIENT_SECRET` live in
`marianos/.env.kroger`, which is gitignored and must stay that way.

## Read before you write

Three separate times, code was written that duplicated or contradicted code
already in this repository, because the existing implementation was not read
first. Before adding a collector, mapper, probe or normalizer, search the other
branches too:

```bash
git log --all --oneline -- '*<thing>*'
for b in $(git branch -r --format='%(refname:short)'); do
  git ls-tree -r --name-only "$b" -- marianos/ walmart/ | grep -i <thing>
done
```

`marianos_collector/api_trial.py` and `api_collection.py` live on
`marianos-fresh-runs-category-evidence` and `marianos-live-api-west-loop`, not
on the corrections branch. They contain working, stricter implementations than
anything written later. Read them.

## Verification discipline

A green test suite has twice reported sound work that was not.

- **Mutation-test every fix.** Revert the fix, confirm the suite goes red, put
  it back. A fix no test detects is not done. Three of five fixes once passed
  review with no test covering any of them.
- **Direct and pytest counts must agree.** `python3 tests/<file>.py` and
  `python3 -m pytest tests` must execute the same number of tests. A stray
  `unittest.main()` above a class silently runs a subset and prints OK. Current
  counts: Walmart 251, Mariano's 632.
- **Assert on something that changes.** A test that asserts an identity-keyed
  value will pass whether or not the behaviour works.
- **Claims in client-facing files are checked, not written from memory.** A
  release note once stated a test count and a property that were both false and
  falsifiable in one command.
- Prefer an independent review that is given the code and the requirements but
  not the author's reasoning, and told to assume the author is wrong.

## Current state

**Walmart.** 615-record trial submission for store 100, ZIP 72712, rebuildable
from snapshots via `walmart/tools/rebuild_evidence.py` and verifiable against
`MANIFEST_SHA256.json`. Five client corrections are done: retention of
unavailable and unpriced offers, a coverage-attestation gate, approximate-weight
exclusion in titles as well as the weight field, manifest entries that fail the
verifier instead of being filtered out, and a bounded first-test probe.

**Mariano's.** The assigned store for the demonstration is **Vernon Hills,
`53100502`, 1720 N Milwaukee Ave, IL 60061, PICKUP**, confirmed by the client
on 31 October. Everything collected so far is West Loop `53100508` and must
stay labelled as West Loop; it is a different store and must never be
relabelled. 604 published records from a 24 October live Kroger API run at
West Loop, store `53100508`, ZIP 60661, from 650 collected with 46 quarantined,
plus 158 page-read PPM values and 29 volume-offer descriptions from 204 page
captures. Collection stopped when the site began returning Access Denied; the
remaining fields were not invented. Separately, 34 Batteries products with
page-read PPM on all 34 and digital coupon terms on 17. A three-execution Azure
stop-and-resume trial on 28 October verified a durable checkpoint by SHA-256
across a deliberate failure. Coverage across the client's 28 category roots is
the known gap. It is stated in
`reports/2026-10-31-vernon-hills-package-rerun/DOES_NOT_ESTABLISH.md`. The file
this line used to cite, `reports/2026-10-24-west-loop/CATEGORY_COVERAGE.csv`,
lives only on `marianos-live-api-west-loop` and is not on this branch.

## Delivery date

**5 November 2026, 00:00 GMT.** Set by the account holder and used in every
client communication from 2 November onward. Do not invent a different one.

## The task in progress

`marianos/tools/kroger_full_sweep.py` sweeps many search terms per category to
widen coverage, because the Kroger public Products API has no category
enumeration. A first run was stopped after 18,351 records over 198 of 301 terms
because the tool has four defects, all of which are fixed by using what already
exists:

1. It fabricates `https://www.marianos.com/p/<upc>`, which does not resolve.
   The API returns `productPageURI`; `api_trial.normalize` validates and uses
   it.
2. It accepts the first item in `items[]`. `api_trial.observe` now selects the
   qualifying local pickup offer (`soldBy == "UNIT"`, `fulfillment.curbside`
   true, a size, a finite positive `regular` price) and classifies a product
   without one. That is a status recorded beside the row, not a filter. See
   `marianos/RETENTION_POLICY.md`.
3. It never calls `schema.make_record`, so the approximate-weight exclusion and
   the product-URL check are not applied.
4. It discards the raw API product, so a later rule change forces a re-fetch
   rather than a re-filter.

Fix by porting `api_trial.normalize` onto this branch and having the sweep use
it; merging `api_trial.CATEGORY_MAP` into `config/category_map.json`, keeping
the no-guessing behaviour both already have; persisting the raw response per
term under the output directory; and quarantining only what the brief itself
excludes, with reasons and counts.

That port is done, along with a fifth defect found on the way: `main` replaced
the resolved store with blank flag values, so every record in the first run has
an empty `store_name` and `store_location`. Its output in
`marianos/out/sweep-2026-10-31/` must not be published. The rerun is next.

Then: enrich a subset spread across all 28 roots with page-read PPM and
retailer deal wording, merged through `composition.py` so provenance records
which source supplied each field; and compare the new run against the 24
October set at the same store, for shared UPCs, price movement and newly
covered roots.

Keep the 24 October output untouched. New runs go to their own output folder.

## The sweep inside the collector

The 26,166 delivered records were produced by `tools/kroger_full_sweep.py`,
outside the runner, so they never passed the publication gate, retention
reconciliation, the trial and published namespace separation, or a
runner-driven resume. The client identified that directly on 2 November. Three
pieces close it, and all three are in:

1. The coverage-attestation gate separates "did this page enumerate its
   children" from "can this route reconcile against the 28 roots". A source
   that cannot attest may collect; its output stays in the trial namespace and
   the report says `source_coverage_attested: false`. The gate still binds
   anything that does claim to attest.
2. `marianos_collector/sweep_core.py` holds the sweep as importable code, with
   `tools/kroger_full_sweep.py` importing it. One implementation.
3. `marianos_collector/kroger_sweep_source.py` is the Source. `--source sweep`,
   or `--spine sweep` under `--source composite` to add the page-read
   enrichment.

Two properties of the adapter are load-bearing and must not be traded away:

- **The source serves raw products, not records.** `api_trial.to_raw_product`
  is the single mapping from a Kroger product to the raw dict; `observe` makes
  the record from it and so does the runner, through the same
  `make_retained_record`. A rule added to one path therefore cannot miss the
  other. A test asserts the two produce an identical record for the same
  product.
- **The index is read back from the persisted API responses, not from the
  sweep's return value.** The checkpoint holds *finished records*, so a resumed
  sweep would have nothing to hand the runner for terms already done, and a
  resumed run would deliver less than a fresh one. Reading the responses makes
  the two identical, and is the re-filter-rather-than-re-fetch property defect
  4 above asked for, used rather than claimed.

Two things the runner route delivers differently from the tool, both honest and
both reported rather than smoothed over:

- **187 of 26,166 products have no configured root**, because the retailer's own
  label is not in the explicit map. The tool kept them with an empty
  `category`. The runner is category-driven, so they cannot be served under any
  root; they are counted and named in `provenance()` and never guessed into one.
  This is **not** a map with ten entries missing. The labels are `Party` 117,
  `Halloween` 38, `Entertainment` 10, `Thanksgiving` 10, `Automotive` 4,
  `Other` 3, `Apparel` 2, `Furniture` 1, `Holiday & Seasonal Goods` 1,
  `Sporting Goods` 1 — seasonal and non-grocery departments outside the
  client's 28 roots. Mapping them would be assigning a category from the one
  the product is not in. What to do with out-of-scope products is a scope
  question for the client, not a defect to fix here; see
  `ROUTES_AND_AUTONOMY.md`.
- **Five of the 28 roots came back empty** in the 31 October sweep: Coupons,
  Seafood, Coffee, Batteries, Light Bulbs. Kroger's label vocabulary has no
  equivalent, which is not the same as the shelf being empty. The runner refuses
  a release with an empty configured root, which is correct, so a sweep run
  names the 23 roots it can populate and `missing_roots()` reports the rest
  before a reviewer has to infer it from a validation failure.

The store columns come from Kroger's own `/locations` response via
`sweep_core.store_from_locations`, never from a hand-written config entry, and
`--resolve-store` requires `--expect-zipcode` and `--expect-street` because the
assigned id differs from West Loop's by two characters.

## Reporting

Every run report states what it does **not** establish, in its own words, not
only what it does. Term-filtered search cannot attest complete category
discovery, and no report may imply otherwise. Where two sources disagree about
the same field for the same product, record the conflict rather than resolving
it silently.
