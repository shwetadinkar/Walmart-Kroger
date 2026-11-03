# GAP_RESOLUTION.json is superseded

This file is the **first run** of `tools/resolve_sitemap_gap.py` and its
verdicts are wrong. It is kept unchanged on purpose: it is the evidence that
the defect was real, and a corrected file cannot evidence that.

**Do not read a number out of it.** The corrected figures are in
`GAP_RESOLUTION_RECLASSIFIED.json`, recomputed from this file with no new
requests.

## What was wrong

It returned a carriage verdict for any product the endpoint returned. Kroger's
product-details endpoint returns the catalogue record whether or not the
queried location carries the product, so the response arriving evidences
nothing about the store. A price or an explicit stock level **at that
location** does. It also treated a 404 as a lookup failure rather than as an
answer.

So it reported 324 carried and 0 confirmed absences out of 326, which is a
property of the classifier and not a finding about the store: a classifier that
cannot say no carries no information when it says yes.

## What replaces it

- `priced_at_this_store`: **186**
- `stocked_at_this_store`: **0** (see the note below before reading this one)
- `in_catalogue_no_store_evidence`: **138** (evidence neither way)
- `absent_from_catalogue`: **2**

Products missed by the sweep: at least **186**, at most **324**. A range,
because that is what the measurement supports. Neither end estimates total
catalogue coverage.

A zero against `stocked_at_this_store` is **not** a finding that nothing is
stocked. The first run recorded only whether a price existed and not stock
levels, so no product in it can be classified on stock at all, and every
product without a price falls to `in_catalogue_no_store_evidence` whatever its
stock. A fresh run retains stock levels and would move some of those either
way. That is why the upper bound is kept rather than dropped.

## The keys in this file not to rely on

- `counts`
- `_carried_and_missed_means`
- `_not_carried_means`

`_carried_and_missed_means` is the one to watch. It describes its count as a
hard lower bound on the coverage gap, and that count is the uncorrected 324.
The lower bound is the `priced_at_this_store` figure above.
