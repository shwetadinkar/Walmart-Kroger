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

  **The client rejected the composed value on 4 November**, in his words: "the
  separate composed-PPM export does not satisfy directly captured PPM." So the
  attended browser route that had just worked at Mariano's was tried against
  Walmart store 100, because a directly captured rate in the rendered cents form
  would answer him outright. **It is not obtainable.** The search page serves the
  displayed rate in cents with no challenge at all, but it served **store 3081,
  Sacramento CA 95829**, because Walmart geolocated the request (`isoLoc=IN_DL_t3`)
  and defaulted; those rates are another store's and are recorded nowhere.
  Reaching store 100 context means the store-selection path, and that path
  serves a press-and-hold bot challenge. Defeating it is not done here by any
  name, including by having a person press the button so automated reading can
  continue, which is defeating the protection by proxy. The route is therefore
  unavailable and that is reported. See
  `walmart/evidence/2026-11-04-attended-browser-store-100-attempt.md`.

  The composed value stays the only available form of this column, which was
  already the position; what changed is that it now rests on a test at the right
  store on the current site rather than an inherited claim. The first keyword
  check flagged a challenge on a pattern that could have matched a toy robot in
  a store directory, and the matched text was read before anything was
  concluded — a route declared closed on an unchecked match is the failure this
  file records twice already.
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
  counts: Walmart 331, Mariano's 1066.
- **"Tested in both collectors" is two claims.** The refused-run record was in
  both runners and tested in one: searching the whole Walmart suite for the
  failures tree returned nothing, so on that side a documented property rested
  on no command anyone could run. When a property is claimed for both modules,
  check both suites for it rather than the code.
- **Clear `__pycache__` before a mutation revert.** A restored file once still
  read as red because the mutated bytecode was loaded, which cost a false
  diagnosis. The same staleness in the other direction is the dangerous one: a
  reverted fix reading as green is a mutation test that lies in favour of the
  author.
- **Assert on something that changes.** A test that asserts an identity-keyed
  value will pass whether or not the behaviour works. Two such tests were found
  by review on 3 November and rewritten. One asserted a published row's store
  columns matched the `Store` object it had just been handed, which holds
  whatever that object says; checking it properly showed the blank-store-column
  defect could recur through the collector, and a gate now refuses a store
  whose `store_id`, `zipcode`, `store_name` or `store_location` is blank. The
  other passed `raw["sub_category"]` as the argument it then compared against,
  and bypassed the runner it claimed to test.
- **Claims in client-facing files are checked, not written from memory.** A
  release note once stated a test count and a property that were both false and
  falsifiable in one command.
- **A claim about an outside party's documentation is checked by reading that
  documentation, every time it is relied on.** `OXYLABS_ASSESSMENT.md` declined
  a route on two such claims, that no dedicated Kroger or grocery target exists
  and that the Walmart sources document no store id, and **both were false**:
  `marianos_product`, `marianos_search` and roughly fifteen other Kroger
  banners exist with `store_id`, `delivery_zip` and `fulfillment_type`, and all
  three Walmart endpoints take `store_id`. Each was one page away. A refusal
  built on an unchecked fact is worse than no assessment, because it closes the
  question. It surfaced only because the account holder asked why we were not
  using a tool the client pays for, which is not a reliable way to find this.
  The corrected file shows the original claims rather than replacing them.
  **A standing position must rest on what a route actually does, never on a
  guess about what a vendor offers**, or the position becomes a way of avoiding
  the work of finding out.
- Prefer an independent review that is given the code and the requirements but
  not the author's reasoning, and told to assume the author is wrong.

## Current state

**Walmart.** 615-record trial submission for store 100, ZIP 72712, rebuildable
from snapshots via `walmart/tools/rebuild_evidence.py` and verifiable against
`MANIFEST_SHA256.json`. Five client corrections are done: retention of
unavailable and unpriced offers, a coverage-attestation gate, approximate-weight
exclusion in titles as well as the weight field, manifest entries that fail the
verifier instead of being filtered out, and a bounded first-test probe.

**Mariano's.** Release `20261103T175940Z_426c12e8`, 28,549 records across the
23 populated roots, is the first produced through the runner at the assigned
store: store columns 100 percent, `coverage_scope: subset_trial`,
`source_coverage_attested: false`, `submission_ready: false`. It supersedes the
25,876-record release of the same day and the 26,166 produced outside the
runner.

**That release left the page-read enrichment behind, and nearly shipped
without it.** A fresh sweep carries no `ppm` and no deal wording, because the
API has neither, so the 3 November release had those three columns at zero
while the superseded 26,166 set had 592 of them. A submission was built and a
client letter written saying those fields were blank through four closed
routes, when 592 observed values at the assigned store were sitting in
`reports/2026-11-01-vernon-hills-page-harvest/`, tracked, in the repository.
The account holder asked whether there was progress, which is what surfaced
it. **A new spine does not inherit an enrichment. Re-merge after every sweep,
and check the three page-only columns before calling a release deliverable.**

Merged on 4 November through `tools/merge_page_enrichment.py`. The first merge
put `ppm` on 589, `volume_deals_description` on 181 and
`digital_deals_description` on 51 from the 1 November read alone, 628 of 649
page UPCs bound. **Both of those numbers are superseded**: 181 included the
badge defect below, and the read was then only one of two.

**The delivered figures are the one-pass merge of both reads**, run against the
28,549 release: `ppm` **727**, `volume_deals_description` **146**,
`digital_deals_description` **48**, every one of the three attributed to
`crawl` and none to the API, zero conflicts, zero cross-read disagreements,
nothing refused as unbindable. 730 of 742 page UPCs with a value bound; the 12
that are not in the API set contributed nothing rather than being attached to
anything. 540 products carry values observed on 1 November and 202 observed on
3 November, each stamped with its own read's time.

**A deal column filled by elimination published badges as offers.** The parser
took the title, then the next line as the size, then called *everything left
over* a deal line, and the merge called every deal line not prefixed `Coupon:`
a volume deal. So on the 1 November page read `volume_deals_description` was
`Low Stock` on 47 records and `View 2 Offers` on 12 more: **82** of 183 volume
values were wholly or partly a stock status, a payment eligibility or a
navigation link. This said 77, written from memory; the sub-counts were exact
and only the summary was wrong, and it understated the defect. The 22 fields have no column for any of those, so they are
retained on the page record under `stock_label` and `non_deal_labels` and
published nowhere. Corrected, the same read gives volume on 120 and digital on
54, and 88 rows' deal columns change.

The same elimination lost real values in the other direction. A sold-by-weight
card carries no size, so the line after the title was taken as one whatever it
said: two digital coupons (`Coupon: $1.79 lb Honeycrisp Apples` and the Bartlett
pear equivalent) and a number of `Buy 1, Get 1 Free` offers were swallowed into
`size`, where nothing publishes them. `size` is never taken from the page, so
none of that reached a published row as a wrong size, but the offers were lost.

**A deal is now identified by what the retailer wrote, not by being left over**,
and the unrecognised case falls to the size slot rather than into a deal column,
because that is the safe direction. `classify_card_line` is the one
implementation of the judgement and the merge imports it, re-classifying every
`deal_lines` entry rather than trusting the parse.

**That does NOT make the two parses interchangeable, and this file claimed it
did.** The sentence here used to read that "a `parsed.json` produced before the
distinction existed re-merges to the same result as one produced after".
Measured on the 1 November read, that is **false**. Re-classification removes a
badge wrongly admitted as a deal, so it fixes that direction. It cannot recover
an offer the old parser put in `size`, because such a line never reaches
`deal_lines` at all. The two files differ on **87 UPCs**, and re-merged the old
one yields **169** deal values against the corrected one's **174**: the five
lost are the two `Coupon: $1.79 lb` produce offers and `Buy 1, Get 1 Free`
lines on sold-by-weight cards.

**So the merge takes `parsed_full_corrected.json`, never `parsed_full.json`.**
Both are in `reports/2026-11-01-vernon-hills-page-harvest/data/`, the old one
distinguishable by having no `stock_label` and no `non_deal_labels` keys. The
4 November read's parsed records are `page_reads.json`, not a `parsed_full*`
file. `tests/test_parse_inputs_not_interchangeable.py` fails if anyone
re-asserts the interchangeability. **`Cash Back:` reaches neither deal column.** It was briefly routed to the digital one, on the reasoning that it sits on the same clipped-offer surface as `Coupon:` and is certainly not a multi-buy offer. `schema.make_record` has refused exactly that since before the merge tool existed, as `CASHBACK_MISCLASSIFIED_AS_DIGITAL`, and the schema is right: there is no cashback column among the 22 fields. The reasoning was the author's and an existing deliberate rule contradicted it. One Vernon Hills record is affected, a Pabst cashback offer, now named in the merge report's `offers_withheld_no_column_for_them` and published nowhere. Digital deals are therefore **48**, not 49.

**The merge wrote the deal columns without the schema's rules.** It bypasses `make_record`, so a value the schema refuses could reach a published row by coming through the merge, and all 54 page-read digital values failed the schema's gate while being published anyway: two write paths with contradictory rules for one column, and the unreachable one was the stricter. `schema.check_deal_columns` is now the one implementation and both call it. The gate's clipping-language requirement was itself too strict - it rejected every value read from the retailer's own pages - so the retailer's leading `Coupon:` marker is admissible evidence, because that prefix is how the retailer labels that surface, in exactly the way a bare promotional sentence is not.

This surfaced on 4 November from **comparing the two page reads of the same
store three days apart** - a record whose `size` read a coupon line on 1
November read `SNAP EBT` on 4 November, which is not a change in the data. That
comparison is worth keeping as a check: of 64 UPCs rated on both dates, the
displayed rate was **identical on all 64** and `sale_price` moved on one, which
is the only reproducibility evidence this enrichment route has.

**Chaining two merges falsified the provenance, and every count stayed right.**
Two page reads were merged by running the tool twice, the second onto the first
one's output. Against the real 28,549 release that produced `ppm` 727 and
`volume_deals_description` 146 - correct totals - with
`values_by_field_and_source` reading `ppm: {crawl: 201, kroger_public: 526}`
and `digital_deals_description: {kroger_public: 53}`. **The Kroger public
Products API carries neither field at any tier**, so 526 rates and all 53
coupon descriptions were recorded as having come from a source that cannot
produce them. The second pass cannot tell the first pass's contributions from
the spine's own values. No conflict was reported and nothing failed, because
nothing was wrong except the labels; it was caught by reading the report rather
than by any gate.

`--page` and `--observed-at` are now repeatable in pairs and **every read is
applied in one pass**. Per product the freshest read that supplies anything
wins and all three fields come from that one read, so the single observation
time on a contribution is true of every value in it; taking each field from
whichever read happened to have it would stamp values with a time they were not
observed at. Argument order does not decide anything, the observation time does.
A mismatched count of `--page` and `--observed-at` is refused rather than
reusing one stamp. Disagreements between reads are recorded in
`cross_read_disagreements`, and `page_reads` names each file with the time it
was applied under.

One pass over the two reads gives `ppm`, `volume_deals_description` and
`digital_deals_description` **all attributed to `crawl`, none to the API**, with
zero conflicts and zero cross-read disagreements. Digital deals come out at 49
before the cashback withholding below takes them to the delivered 48, rather
than the 53 the chained run reported: five coupons present on 1 November
were gone when those same products were re-read on 3 November, and one of the
five is not in the API set. **An offer the later observation did not see is not
evidence of an offer now**, so it is not carried forward. The 1 November read is
kept, so the historical observation is not lost; it is simply not published as
current.

The merge refused twice before it ran, both times correctly. It will not merge
a page read onto rows whose store columns differ, so passing a tidied
`Marianos - Vernon Hills` was rejected against the observed
`Marianos - Marianos Vernon Hills` that Kroger's `/locations` returns. That
gate exists because of the West Loop relabelling defect and it caught a store
name typed from memory instead of read from the data.

The assigned store for the demonstration is **Vernon Hills,
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

`CompositeSource` forwards every public attribute it does not define itself to
the spine, read live, and one the spine lacks stays absent. Forwarding names
one at a time lost three in turn: `unresolved_offers`, `reset_unresolved`, and
then `coverage_attested`, which made the composite publish path **unrunnable**
because the CLI decided scope from the spine's attestation while the runner
read the composite's and found nothing. The same omission silently skipped the
uncovered-roots staleness gate, since `populated_roots` never reached the spine
either. The generic forwarding is ported from the Walmart module, which had
already been fixed this way; neither module may go back to hand-written
forwards, and neither may forward a neutral default, because
`unresolved_offers` returning `[]` made a spine that keeps no such record read
as a count of zero.

Two properties of the adapter are load-bearing and must not be traded away:

- **The source serves raw products, not records.** `api_trial.to_raw_product`
  is the single mapping from a Kroger product to the raw dict; `observe` makes
  the record from it and so does the runner, through the same
  `make_retained_record`. A rule added to one path therefore cannot miss the
  other. A test asserts the two produce an identical record for the same
  product.
- **The index is read back from the persisted API responses, not from the
  sweep's return value.** The checkpoint holds *finished records*, so a resumed
  sweep would have nothing to hand the runner for terms already done. Reading
  the responses is the re-filter-rather-than-re-fetch property defect 4 above
  asked for, used rather than claimed.

  This was first written as "a resumed sweep serves exactly what a fresh one
  served". **That was false** and the test for it compared a run's output
  against itself over the same raw directory, so it asserted nothing. A term
  that failed on page 0 was marked done and checkpointed, so a resumed sweep
  skipped it for ever while a fresh one collected it, and the only trace was an
  entry in `page_failures` that nothing compared against `done_terms`.

  **Fixed on 4 November.** A term whose pages did not all complete is not added
  to `done_terms`, so a resume retries it. Retrying is bounded at
  `MAX_TERM_ATTEMPTS` of 3, because a term that fails the same way every time
  would otherwise be retried for ever across resumes and no run would finish;
  after the cap it is marked done and named in `terms_abandoned`. Both reach
  the release report as `terms_abandoned_after_retries` and
  `terms_incomplete_pending_retry`, because a term we stopped trying to collect
  is a coverage fact and a run that left work for a resume has not produced
  what its configured terms would yield. `STATE_VERSION` is 6; the version gate
  refuses an older checkpoint rather than misreading it. A failure mid-sequence
  counts as incomplete too, not only one on page 0.

- **`terms_hit_start_cap` is decided after a term's pages, from the term.** It
  used to be appended only inside the `start > max_start` branch, which the
  collector never reaches because `PAGES_PER_TERM` stops at start 250 exactly.
  So the sweep's main quantitative coverage limit was structurally always
  empty on this path and a release reported zero terms truncated when the truth
  was that we could not know. A reported total now settles it, more than the
  ceiling being truncated and exactly the ceiling complete; without a total,
  reaching the ceiling is recorded because not knowing what is behind it is
  itself the disclosure.

- **`pickup_context` travels from the source into `retention.json`.**
  `RETENTION_POLICY.md` requires it per identity: fulfillment flags, `soldBy`,
  stock level, offer classification, observation time. The sweep tool supplied
  it and the runner did not, and `retention.observation` had no parameter for
  it, so every release produced through the collector carried
  `pickup_context: {}` and the policy's instruction to read `sold_by` before
  `regular_price` was unsatisfiable on that path.

- **Every raw response is checked against the location it was collected at,
  and a page cursor is only honoured against the contents it was issued for.**
  Both were defects found by an independent review on 3 November, both
  reproduced, both fixed, and both now have tests in
  `tests/test_sweep_source_defects.py` that fail when the fix is reverted.
  `to_raw_product` stamps the store columns and `store_context_verified: True`
  from whatever `Store` it is handed, so indexing another store's responses
  relabelled them: a work directory shared between two stores served three
  West Loop products as verified Vernon Hills observations, silently. And the
  cursor was an integer offset into a list rebuilt from disk per process, so
  across two processes 14 observed products became 10 published with
  `status: validated` and no gate fired. Neither may be traded away.

Two things the runner route delivers differently from the tool, both honest and
both reported rather than smoothed over:

- **187 of 26,166 products have no configured root**, because the retailer's own
  label is not in the explicit map. The tool kept them with an empty
  `category`. The runner is category-driven, so they cannot be served under any
  root; they are counted and named in `provenance_report()` and never guessed
  into one. That method was called `provenance()` until 3 November, which
  nothing but tests ever called, because the runner looks for
  `provenance_report()` — so none of this reached a single release, and this
  file claimed otherwise.

  **This has now happened in three sources, and is fixed in all three on
  4 November.** `CatalogV2Source.provenance()` had the identical stale name,
  called only by a test. `AuthorizedProviderSource` had **no report method
  under either name**, and because the runner reads it through `hasattr`, a
  release produced through that source carried no provenance block at all and
  nothing failed. That is the worst placement for the gap: that source sets
  `coverage_attested = True`, so unlike the sweep it may publish outside the
  trial namespace, and the source permitted the strongest claim disclosed the
  least. It now reports its host, path, attestation with the explicit note that
  the attestation is the provider's claim carried forward rather than our
  verification, its page and retry counters, and what it does not establish.
  The token appears nowhere, with a test asserting that.

  **A rename fixes one occurrence, so the guard is structural.**
  `tests/test_source_report_surface.py` parses `runner.py` for the attribute
  names it reads off a source, asserts it looks for `provenance_report` and not
  `provenance`, discovers every `*Source` class in the package, and requires
  the method on each one that is not a test fixture - with a sharper assertion
  for any source that attests coverage. It also fails if any source carries the
  stale `provenance` name again, even beside the right one, because that is
  where the divergence starts. Two of its own assertions check that the
  derivation and the discovery actually found something, so the rest cannot
  pass vacuously.
  This is **not** a map with ten entries missing. They are seasonal and
  non-grocery departments outside the client's 28 roots, so mapping them would
  be assigning a category from the one the product is not in. What to do with
  out-of-scope products is a scope question for the client, not a defect to fix
  here; see `ROUTES_AND_AUTONOMY.md`.

  **The delivered release has 166, not 187**, and the counters reconcile
  exactly: 28,549 served plus 46,073 duplicates plus 166 out of scope equals
  the 74,788 products seen, over 1,833 indexed responses. On the client's
  instruction of 4 November they are now retained as identities with the
  retailer label verbatim and the raw response file each came from, written by
  `tools/out_of_scope_reconciliation.py`, which re-indexes the persisted raw
  responses and so needs no collection and no credential.

  **The artefact is not in this repository**, and this line previously read as
  if it were, citing `reports/2026-11-04-out-of-scope-reconciliation/` as
  though that path existed here. It does not. The tool was run on the account
  holder's machine, where the raw responses and the release live, and its output
  ships in the client package. The counts it produced are the ones above and
  they reconcile exactly, but **a claim that identities "are now retained"
  needs the artefact to exist wherever the claim is read**. Found by an
  independent review on 4 November, which looked for the directory.

  **The label set is seasonal and turns over between runs.** Measured at the
  same store three days apart:

  | label | 31 Oct sweep | 3 Nov sweep |
  |---|---:|---:|
  | `Party` | 117 | 116 |
  | `Halloween` | 38 | **3** |
  | `Christmas` | 0 | **11** |
  | `Entertainment` | 10 | 11 |
  | `Thanksgiving` | 10 | 10 |
  | `Automotive` | 4 | 5 |
  | `Other` | 3 | 3 |
  | `Apparel` | 2 | 2 |
  | `Holiday & Seasonal Goods` | 1 | 2 |
  | `Sporting Goods` | 1 | 1 |
  | `Furniture` | 1 | 1 |
  | `Travel & Luggage` | 0 | **1** |
  | total | 187 | 166 |

  `Christmas` and `Travel & Luggage` are labels the 31 October sweep never saw,
  and `Halloween` fell by 35 in three days. So this is not a fixed list of
  labels waiting to be mapped: **a static map of the seasonal departments would
  be stale within days and would need maintenance for ever**, which is a reason
  to keep reconciling them separately rather than an argument for mapping them.
  It also means the 187 figure above describes the superseded 26,166 set and
  cannot be quoted for any later release.
- **Five of the 28 roots came back empty** in the 31 October sweep: Coupons,
  Seafood, Coffee, Batteries, Light Bulbs. The runner refuses a release with an
  empty configured root, which is correct, so a sweep run names the 23 roots it
  can populate and the zero-products failure now states which roots the source
  did reach. Earlier this said `missing_roots()` reported that; nothing called
  it, and a reviewer met the bare validation failure.

  **`Seafood` on that list does not mean no seafood was collected.** Kroger
  files meat and seafood under the single label `Meat & Seafood`; the client's
  CSV splits them; a product cannot be assigned to one from the label alone, so
  `config/category_map.json` maps the label to `Meat` and keeps it in
  `sub_category`. Seafood is in the delivered data, inside the 987 Meat
  records, and is read by filtering `sub_category`. The reason text in
  `config/sweep_coverage.json` said the cause was Kroger's labels and the
  retailer's sitemap; the actual cause is this repository's own mapping
  decision, and a client reading only the root name would have concluded the
  opposite. `Coffee` was wrong too: the map does contain `Coffee -> Coffee`;
  no product the sweep reached carried that label.

  **Three of the five are now measured against the delivered data rather than
  inferred from the sitemap.** Binding the 3 November page read by UPC shows 24
  ground coffee products in the dataset labelled `Beverages`, 24 light bulbs
  labelled `Household` / `Cleaning Products`, and 24 batteries, 19 under the
  same label and 5 under `Hardware Home Improvement`. So those products **are
  in the delivered data**, under the retailer's own broader label, exactly as
  seafood sits inside Meat. The gap is a taxonomy mismatch between the client's
  28 roots and what the retailer publishes, not a collection failure, and
  assigning a root would be assigning a category the product's own source does
  not carry. None of it makes those roots covered: no product is served under
  them and each stays declared.

The store columns come from Kroger's own `/locations` response via
`sweep_core.store_from_locations` **when `--resolve-store` is passed**, and
`--resolve-store` requires `--expect-zipcode` and `--expect-street` because the
assigned id differs from West Loop's by two characters. The Azure job always
passes it. Without it the columns come from `stores.json` and **nothing checks
that `--store` and `--location-id` describe the same store**, so
`--source sweep --store <any configured id> --location-id 53100508` publishes
West Loop data under whatever name the config holds. This file previously
stated the observed-columns property unconditionally, which was false for the
CLI. **Fixed on 3 November:** without `--resolve-store`, `--source sweep` now
requires `--store` to equal `--location-id`, so the store columns describe the
store queried.

## A refused run leaves a record

Unattended, the only trace of a failure was the exception and a log line: a
budget-stopped or partially collected run looked identical to one that never
started. Both runners now write the refused attempt to
`failures/<namespace>/<store>/<timestamp>_<id>.json`, carrying the reason
verbatim, the scope, the configured roots, the release that was left untouched,
and whatever the source can say about how far it got through
`provenance_report()` and `durable_evidence()`.

The release is still refused; none of that protection is relaxed. Three things
about the record are deliberate and tested: it is written **outside** the
publishing namespace, so the assertion that nothing may be written there stays
strong; the original error is always re-raised, and a failure to write the
record never replaces the error it was recording; and the store-usability gate
is inside the recorder, because a misconfigured job is the failure most likely
to recur unattended.

The names in `getattr(self.source, ...)` there are literals on purpose. The
delegation surface is derived by parsing the runner for what it reads off a
source, and a variable name made that derivation blind.

**It only covered `Collector.run`, which is not where this fails.** Both CLIs
do work before the runner exists: the Mariano's CLI loads the Kroger
credentials twice, resolving the store from `/locations` and building the
source; the Walmart CLI builds its source, reads the OPD mapping and reads the
canaries. So a missing or expired key, or a missing mapping file, produced an
exception, a log line and no artefact at all - the ordinary misconfigured job,
which is the failure most likely to recur unattended, going unrecorded by the
machinery built for exactly it. Credential expiry is the likeliest of all for a
twice-weekly job, because keys are rotated and nobody is watching when they
are. Found on 3 November by running the real CLI with the two variables
removed, after the client reproduced the bare error twice.

`record_refused_attempt` in each runner is now the single place a refusal is
written and named, called by both the runner and the CLI, and it stamps the
timestamp from the same instant it builds the key so the two cannot disagree.
Four properties are tested on both sides and each has been mutation-checked:

- Only `run` records. `status` and `export` are not runs, must not leave
  refusal artefacts, and `status` must not need credentials at all.
- The `Collector` call stays **outside** the guard, because it records its own
  refusals and wrapping it would write two records for one failure. A test
  asserts one failure produces one record.
- A Mariano's startup record never claims a store it did not resolve. The ids
  are labelled `requested_`, `store_resolved` is explicit, and the resolved
  columns appear only when the store was actually read. This repository has
  already published one store's data under another store's name once; a failure
  record that reads like a store observation is the same mistake somewhere
  quieter.
- A refused run may still leave checkpoints - that is what makes it resumable.
  The property is that the *publishing* tree is untouched, not that nothing at
  all was written, and the test asserts the narrower thing. Asserting the wider
  one failed honestly the first time it ran.

Not fixed, deliberately: an argparse refusal still exits without a record,
because `p.error` raises `SystemExit`. A wrong flag fails the first time a job
is deployed rather than silently months later, so it is left.

**A SIGKILL bypasses all of it, and the job was configured to earn one.** The
entrypoint passed no time budget, so the CLI default of 7200 seconds applied,
and `deploy_jobs.sh` deployed `--replica-timeout 7200`. Equal by coincidence,
and an Azure replica timeout is a SIGKILL rather than an exception, so
`refusal_recorded` never runs: an overrunning unattended run would leave **no
release and no refusal record**, exactly the trace this machinery exists to
leave, defeated by configuration rather than by code and only on the runs where
it matters most. The budget is now derived from the deployed replica timeout
minus 900 seconds of headroom; `deploy_jobs.sh` resolves `REPLICA_TIMEOUT`
once, deploys it and forwards the same value into the container so the two
cannot drift, and refuses a timeout with no headroom. Found on 4 November while
checking what a rehearsal does not touch.

**The image refused nothing about its own store mapping.**
`config/stores_live.json` is gitignored by design, holding the verified
location id, and `azure/README.md` says to copy it from the template before
building. Nothing checked. A build that skipped that step produced a good image
whose first act at 06:00 UTC was to fail on a missing file. The Dockerfile now
refuses to build on the file being absent, invalid, empty, or still containing
`DEMO`, `REPLACE`, `UNRESOLVED` or `EXAMPLE` - the placeholder case mattering
as much, because a copied template would otherwise deploy under an unverified
store identity.

**The same defect existed on the Walmart side as an absence.** Its run had no
time budget at all, so only `--replica-timeout 14400` bounded it, and
`walmart/azure/AZURE_DEPLOYMENT.md` says plainly that "the jobs are not
guaranteed to finish in four hours". `Collector` now takes `max_seconds` and
checks it between categories; exceeding it **refuses the release and records
the attempt** rather than publishing a partial set that would read as complete.
Between categories rather than per page, because the check must leave room for
the category in hand plus publication. Its entrypoint and deploy script are
wired exactly like the Mariano's pair, 13200 inside 14400, and `list` takes no
budget because it is not a run. Tested on the Walmart side in
`tests/test_time_budget.py`, four mutation reverts checked, because "tested in
both collectors" is two claims.

**Simultaneous firing is the design and an earlier note here was wrong.** That
note called the two jobs starting together a gap worth staggering.
`walmart/azure/AZURE_DEPLOYMENT.md` says the Walmart deployment deliberately
runs two scheduled jobs, one per store, on the same expression, and that "a
Blob lease prevents two overlapping executions of the same store". The hazard
has a guard, the 06:00 UTC time is stated to the client in that document, and
the schedule is therefore unchanged.

## A refused run is retried, then reported

The account holder's instruction on 4 November: *"If it fails then keep trying
every 15 minutes for 8 times, and still not successful then send email
regarding failure. But next run should remain on time due."*

`azure/retry_supervisor.py`, in both collectors, runs the collector as a
subprocess and retries it. `os.execv` used to run it, which replaces the
process, so nothing was left to observe the exit code and no retry was
possible.

**The retry is inside one replica, and that is forced rather than chosen.**
Azure's own `--replica-retry-limit` would retry a failed replica, but its
interval is not configurable, so "every 15 minutes" cannot be expressed that
way. The cost of supervising inside the replica is that the whole plan has to
fit inside one replica timeout, because a replica timeout is a SIGKILL.

**The first attempt gets the whole window and retries get what it leaves.** The
obvious scheme reserves eight intervals up front, so the first attempt gets
`window - 8 x interval`; that starves the run that *succeeds* to pay for
retries it never needs, and at the old 7200s timeout it reserves more than the
window holds. Each attempt is therefore given the time actually left when it
starts. **This removes a special case rather than adding one:** a run that
consumed its whole budget and failed is not retried, because there is nothing
left to retry it with. Budget exhaustion is the one failure where retrying is
pure waste - the next attempt would get less time, not more - and it falls out
of the clock, so the collector never has to classify its own failures and the
CLI's exit contract is unchanged.

**Almost everything else is retried, including an expired credential.** That is
the likeliest unattended failure for a twice-weekly job, a classifier cannot
tell an expired key from a token blip, and retrying one costs no retailer
requests at all. Two exceptions: a usage error, which exits 2 and will be wrong
the same way eight more times, consistent with the existing decision to let an
argparse refusal fail loudly the first time a job is deployed; and a bot
challenge, because the retailer said no, the standing position is that such a
route is unavailable and that is reported rather than worked around, and
retrying a refusal on a schedule is working around it. The challenge marker is
matched on the exception name rather than loose prose, because a route declared
closed on an unchecked match is the failure this file records twice.

**The deployment refuses a plan it cannot deliver.** Eight retries at 900s is
7200s of waiting *alone*, so the configured plan needs at least 10,920s on the
Mariano's side and 11,220s on the Walmart side even if every attempt fails
instantly. The deployed timeouts were 7200 and 14400. `deploy_jobs.sh` now
resolves the plan once, checks it with the same code the container runs - read
from `retry_supervisor.py`, not retyped - and **refuses rather than quietly
shortening it**, because a plan that silently stops at attempt three is not the
plan that was configured. The refusal quotes the figure to set. Defaults are
now 14400 and 21600.

It also refuses a replica timeout that is not shorter than the gap between cron
firings, computed from the deployed expression. That is what answers "next run
should remain on time due": Azure's cron fires independently of how long an
execution takes, so an overrun is not a late next run, it is a *second*
execution running beside the first, which then meets the Blob lease and is
refused. A retry plan that overruns turns one transient failure into a refused
next run. `0 6 * * 1,4` gives 72 hours, so there is room.

**No maximum replica timeout is asserted anywhere here.** Microsoft's jobs
reference lists `replicaTimeout` as a required int with no stated maximum,
minimum or default, and the only discussion of a practical ceiling is a
community thread. So the timeout needed for every attempt to get a *full-length*
run is reported to the operator rather than enforced, and whether Azure accepts
it is discovered at deploy time on their screen. A standing position must rest
on what a route actually does, never on a guess about what a vendor offers.

**The failure notice needs no credential by default.** The supervisor always
prints `MARIANOS_RUN_FAILED_AFTER_RETRIES` or `WALMART_RUN_FAILED_AFTER_RETRIES`,
which an Azure Monitor log alert matches with nothing in the image. Email is
sent when, and only when, the operator sets `ALERT_EMAIL_TO` and `SMTP_HOST`;
the SMTP password is theirs, reaches the job as an Azure secret, and appears in
no file here. A failed email never replaces the failure it reports and never
decides the exit code, the same rule the refusal recorder follows, and a test
asserts no password reaches the body or the marker line.

`list` is not a run: it executes once, is never retried and leaves no notice,
the separation `cli.py` already makes.

**The alert query was written from memory and was wrong.** The first draft of
the Azure Monitor query in both deployment docs narrowed on
`ContainerName_s startswith "marianos-"`. Checked against
`learn.microsoft.com/azure/container-apps/log-monitoring`, that page documents
the table for container *apps*, does not mention jobs at all and documents no
job-name column; `ContainerName_s` is the container's name, not the job's. So
the filter would most likely have matched nothing and **the alert would have
stayed silent through exactly the failure it exists to report** - worse than no
alert, because it reads as one. Both docs now filter on the marker alone, which
carries the store and source itself, and say to confirm the job-name column in
the operator's own workspace before narrowing. Caught before shipping only
because the query is an instruction someone else would paste, which is the test
for when a recalled fact has to be read instead.

**The cron maths moved into both packages** as `cron.py`, because the container
ships the package and not `tools/`. `tools/observe_schedule.py` imports it, and
a test fails if a second copy of the day-of-week conversion appears anywhere -
cron Monday is 1 where Python's `weekday()` makes it 0, and two copies of that
would disagree silently. `shortest_gap_seconds` takes the *tightest* gap over
several firings, not the first or the widest: `0 6 * * 1,4` alternates 72 and 96
hours and 96 would permit an overlap.

**The supervisor is one implementation kept in two places, and checked.** The
two images build from separate contexts, so neither Dockerfile can copy a
module above its own directory, and this repository already ports between the
modules for that reason. A copy nobody checks is how two implementations of one
rule drift apart, so `PortedBetweenCollectors` derives the Walmart copy from the
Mariano's one by substitution and compares them line by line: a change made to
one side only fails by name, and the fix is to port it rather than to edit the
substitution list. Its own substitution list is checked for dead entries, which
immediately found one looking in too narrow a place.

Both Dockerfiles now `COPY azure/retry_supervisor.py`; without it the image
builds and fails at 06:00 UTC, the same defect class as the missing store
mapping.

Tested on both sides in `tests/test_retry_supervisor.py`, 55 tests each, with
**24 mutation reverts checked on each**, because "tested in both collectors" is
two claims. Two of those reverts found tests of mine that detected nothing: the
pre-attempt window check was covered only by the post-wait check that catches
the same cases later, and the success path asserted attempt counts while a
docstring claimed it asserted that no email is sent. Both are now asserted.

## The schedule, as two separate claims

"Twice-weekly Azure operation" was a template plus a manually driven
three-execution pilot, with the schedule never observed running by itself.
`tools/observe_schedule.py` closes what can be closed away from the client's
subscription, and keeps two claims apart so neither carries the other.

**The deployed expression fires when it should.** Computed, not simulated, from
the cron default read out of `azure/deploy_jobs.sh` rather than retyped, and
both deployment scripts are read. `0 6 * * 1,4` gives Mondays and Thursdays at
06:00 UTC with 72 and 96 hour gaps. If a script carries disagreeing defaults,
this refuses rather than attesting whichever it found first. Each script now
resolves `CRON` once and uses that variable everywhere, so the expression
validated against the retry plan is the expression deployed; the Walmart script
previously spelled the default inline in three places.

**A scheduler left alone repeats the job.** Observed in real elapsed time:
three executions, three distinct releases, zero operator interventions, each
with its own wall-clock timestamp, each a real `Collector` run through the real
`KrogerSweepSource` with only the Kroger HTTP client replayed.

The cadence is compressed to seconds and says so. The real times are the first
claim, checked by computation; the unattended repetition is the second,
observed in real time. Neither establishes the other, and **neither establishes
Azure**: nothing ran there, nothing ran in the client's environment, no Azure
cron fired, and the data is replayed. The cron day-of-week conversion is the
load-bearing detail - cron Monday is 1 where Python's `weekday()` makes it 0,
and getting it wrong shifts every reported firing by a day.

## Presence in a catalogue is not carriage

`tools/resolve_sitemap_gap.py` resolves the 326 sitemap products missing from
the delivered data against the store. Its first version returned a carriage
verdict for **any** product the endpoint returned, and treated a 404 as a
lookup failure. On the real run it reported 324 carried and **zero** confirmed
absences, which is not a finding about the store but a classifier that never
says no. Its own docstring stated the correct rule - at least one item the
store prices or stocks - and the code did not implement it. It was caught in
review here, before the number was used anywhere and before it was sent to the
client, by reading the run's own output rather than by any test: zero absences
out of 326 is a classifier, not a store.

Kroger's product-details endpoint returns the catalogue record whether or not
the location carries the product. So a price or an explicit stock level **at
that location** is carriage evidence; presence in the response is not. Absence
of both is undetermined and says so. A 404 is an answer, not a failure.

**The output is a range, never a single number.** On the 3 November run: 186
priced at the store, 138 undetermined, 2 absent from the catalogue. So the
sweep missed at least 186 of those products and at most 324. Neither end
estimates the whole catalogue, because the 890 sitemap products are an SEO
subset the retailer chose rather than a random sample.

Two further things this cost. The first run recorded only whether a price
existed, not stock levels, so its undetermined bucket cannot be narrowed
without re-running; stock levels are retained now. And the probe item itself
had no price at the location, so the very first call was already showing the
defect - a probe is to be read, not just passed.

**The superseded run is kept byte-identical and marked.** `GAP_RESOLUTION.json`
is the evidence that the defect was real, and a corrected file cannot evidence
that, so it is never edited. But kept unchanged it also keeps its own wrong
`counts` and, worse, its own wrong prose: `_carried_and_missed_means` calls its
324 a hard lower bound on the coverage gap. So `--reclassify` writes
`SUPERSEDED.md` beside it, naming the keys not to rely on and carrying the
corrected bounds. The marker is generated by the tool, not written by hand, so
it cannot drift from the reclassification it describes, and it states that a
zero `stocked_at_this_store` is an artefact of the first run keeping no stock
levels rather than a finding about the store.

## Splitting a capped term does not close the ceiling

`filter.start` caps one *term* at 300 products, not a category, so a capped
term can be split into narrower ones that each get their own 300. The account
holder proposed it; it had not been proposed here. On 3 November the 68 capped
terms were split into 421 narrower ones and run into the same work directory,
which the source indexes as a union with the first run.

It works, and it does not solve the problem. 25,876 records became 28,549, up
10.3 percent for 421 terms and about 2,200 requests. But **`terms_hit_start_cap`
went from 68 to 114**: 46 of the narrower terms hit the same ceiling. "whole
milk" has more than 300 products behind it as well. Each split reveals more
depth rather than exhausting it, so the ceiling is structural and no amount of
term splitting reaches past it. That is now measured rather than argued, and it
is the honest form of the coverage limit to report.

Two numbers worth keeping: 62 percent of everything seen was a duplicate
identity, 46,073 of 74,788, and the counters reconcile exactly, 28,549 served
plus 46,073 duplicates plus 166 unmapped. Yield was 6.3 new records per new
term, against 86 per term on the first pass.

**None of this was needed for the deliverable.** `REVIEW_ACTIONS_2026-10-31.md`
records the client's own instruction that the demonstration minimum is 500
genuine distinct products in total, not per category; full coverage is a
production requirement. The first run passed 500 in its first minute. The
remaining shortfall is fields, not products: `ppm` and the four deal columns
sit at 0 percent through every API route.

## The Oxylabs Web API client

`marianos_collector/oxylabs.py`, shaped like `kroger.py`: one error type,
credentials from the environment only, an injectable opener so tests never
touch the network, retry rules in one place. Built to the contract at
`developers.oxylabs.io/products/web-api/for-agents.md`, read on 3 November
rather than recalled. Base `https://webapi.oxylabs.io`, Bearer on every
request, 150 second timeout, retries only on timeouts and 408/429/5xx with
exponential backoff and jitter over three attempts, 400 and 401 surfaced and
never retried, `metadata.request_id` captured per call.

**`REFUSED_HOSTS` is the standing position written into code.** `/v1/scrape`
takes an arbitrary URL, and pointed at `marianos.com` it would very likely
return the displayed price per measure and the deal wording this engagement
keeps reporting as unreachable. That is a vendor fetching the page our egress
cannot reach, which is the route refused by any name, and a new product name
is not a new act. `scrape()` raises on that host before anything is sent, with
a test asserting no request was made. A *dedicated* target reached through
`scrape_target()` is a different interface and is not covered by the refusal.

**The dedicated target is entitled, and it is not what the argument for it
claimed.** On 3 November five requests to `/v1/scrape/marianos/product` with
`store_id`, `delivery_zip` and `fulfillment_type` returned 200, `state: done`,
each carrying `results[0].html`: the retailer's own product page. `OPTIONS` on
the endpoint then gave its typed parameters, and they are decisive. The output
enum is `html`, `markdown`, `screenshot`, `json` - and `json` is parsed by an
LLM against a `json.schema` or `json.prompt` **we** supply. Oxylabs maintains
no structured product schema for this retailer.

**So the distinction this repository drew does not exist, and the route is
refused.** The case for the dedicated target over `/v1/scrape` on a retailer
URL was that it is a *maintained, parsed, retailer-specific interface* rather
than a vendor fetching the page our egress cannot reach. Checked, it is the
second thing: query resolution, store-context parameters, and the page. The
bytes are identical to the generic route that `REFUSED_HOSTS` blocks, so
allowing one while blocking the other is incoherent and the standing position
covers both. `scrape_target()` therefore must not be pointed at this retailer
either.

This is the same failure as the one above it, inverted. That entry records a
*refusal* built on an unchecked fact about a vendor. This was nearly a
*permission* built on one, and the only reason it was caught is that `OPTIONS`
was asked before the capability was used. **Check the fact that carries the
decision, whichever way the decision goes.**

A second and independent reason, which would stand even if the first did not:
`json` output is LLM extraction. A value a model produced by reading a page is
not an observed value, and `ppm` is required to be the *displayed* rate. The
one rule at the top of this file covers it.

What this does establish, and it is worth keeping: the capability is real.
Displayed price per measure and retailer deal wording are reachable this way.
The obstacle is not technical and never was, which is exactly how it should be
reported to the client - as a decision that is his to make with his own
counsel, not a limitation to be worked around here. See
`marianos/ACCEPTABLE_USE_POSITION.md`.

Whether this account even has a dedicated Mariano's target is answered by
`scrapers()`, one GET, not inferred from a documentation page. That is the
first call to make, and the probe exposes it as `--list-scrapers`.

The general `/v1/search` and `/v1/scrape` endpoints are a web search and page
reader. They are **not** the dedicated e-commerce scrapers, and a Web API
product instance is not evidence that the banner targets are entitled.

## The Bright Data Mariano's route was never tested at the assigned store

Reported as "blocked on their ticket #754403" since 24 October. That overstates
it, and the overstatement cost the better part of a day chasing a second
vendor.

The single Mariano's compatibility test, snapshot `sd_mvlszutt1sfyjzr6jr` on
24 October, used **ZIP 60601**. That is the `DEMO-LAKESHORE` entry in
`config/stores.json`, 333 E Benton Pl, a placeholder. Vernon Hills is
**60061** and West Loop is **60661**; 60601 is neither. The assigned store was
not confirmed until 31 October, a week after the test, and the test has never
been rerun against it. `BRIGHTDATA_MARIANOS_TEST_2026-10-24.md` was accurate
about its own scope - it says plainly that the test "proves this exact
configuration failed" and nothing wider - but the route table and the client
reporting since then have carried it as a provider defect.

On 1 November the provider answered the question directly on that ticket:
displayed price-per-measure and digital coupon fields **are** returned when
they are publicly shown for the product and the selected store, with no
guarantee of population for every product. That is the answer the enrichment
gap has been waiting for, from the route this repository already accepts -
consuming a dataset the provider collected under its own arrangements, which
is a different act from directing per-URL fetches at a retailer that refuses
our egress.

**Rerun on 4 November at ZIP 60061. It failed the same way:** `"No Kroger
pickup store found for zip code 60061"`, `error_code: bad_input`, on the
bananas URL that carries a page-read `ppm` of `$0.69/lb`.

So the hypothesis above was wrong. The placeholder ZIP was real and worth
finding, but it was not the cause, and the test asked for to settle it settled
it against the guess. What the rerun does buy is a better-founded claim than
the one it replaces: this route is now **tested at the assigned store and
fails there**, where before it had only ever been tested at a ZIP belonging to
nothing. "Blocked on the provider" is accurate now, and evidenced.

The failure is `bad_input`, not `detect_block`, so it is the provider's store
resolution and not a bot challenge. The retailer's own site resolves Vernon
Hills from 60061 without trouble, which is in the 1 November message on the
ticket. So the provider cannot select a store the retailer selects, and the
provider's assurance that price per measure and coupon fields come through
"for the product and selected store" cannot be exercised while no store can be
selected.

Open on ticket #754403 since 1 November, escalated to their R&D, no answer.
Two things are worth asking that have not been: whether the dataset accepts a
`store_id` such as `53100502` instead of a ZIP, and whether its Kroger store
lookup covers the Mariano's banner at all or only Kroger-branded stores.

**Do not report `ppm` as unobtainable on the strength of this.** It is
unobtainable *through every route currently open to us*, which is a different
sentence and the one the client should get.

## Scope for anything expensive: 500 across categories, not 28,549

Set by the account holder on 4 November. Any route that costs real effort per
product - attended page reads, a served machine, a partner tier, a paid
provider - targets **500 distinct products spread across the categories**, not
the whole set. It matches the client's own instruction in
`REVIEW_ACTIONS_2026-10-31.md`: the demonstration minimum is 500 genuine
distinct products in total, not per category, and full coverage is a
production requirement rather than a demonstration one.

**On the numbers, that target is already met and the remainder is small.** The
1 November page read produced 592 rated products spread across 22 of the 28
roots, not clustered. Measured on 4 November against the configured roots:

| Target | Roots short | Extra page reads |
|---|---:|---:|
| 10 rated products in every root | 9 | **80** |
| 20 in every root | 13 | **192** |

So the gap between what exists and a rate in every single root is about 80
page reads. That is one attended session on the route that produced the 592,
and it changes what a negative answer from a provider costs: not much.

**Four of the six roots at zero are the ones the API cannot reach at all** -
Seafood, Coffee, Batteries, Light Bulbs - and the retailer's sitemap publishes
each as a real listing page. Page reading therefore closes the empty-root gap
and the rate gap in one pass, which no API route can do at any price. Coupons
is a savings surface rather than a product category and may yield nothing;
Floral has 45 API products and no rate yet.

Before proposing any scaled route again, price it against 80 to 200 products,
not 28,549. The Oxylabs evening was spent on a capability that would have been
needed for the whole set and is not needed for this one.

## Reporting

Every run report states what it does **not** establish, in its own words, not
only what it does. Term-filtered search cannot attest complete category
discovery, and no report may imply otherwise. Where two sources disagree about
the same field for the same product, record the conflict rather than resolving
it silently.
