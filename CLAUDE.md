# Working rules for this repository

Two retail collectors, `walmart/` and `marianos/`, built for a client who
reviews the work closely and has found real defects in it. Everything below
exists because something went wrong once.

Authoritative branch: `walmart-client-corrections-2026-10-31`. See
`walmart/RELEASE.md` for the ancestry table and the eight feature checks.

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
  counts: Walmart 162, Mariano's 218.
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
the known gap; `reports/2026-10-24-west-loop/CATEGORY_COVERAGE.csv` states it.

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

## Reporting

Every run report states what it does **not** establish, in its own words, not
only what it does. Term-filtered search cannot attest complete category
discovery, and no report may imply otherwise. Where two sources disagree about
the same field for the same product, record the conflict rather than resolving
it silently.
