# Requirement 6: category completeness and silent blocking

There are two code paths, and they differ. This dataset came from the second, so the
gates in the first were **not applied to this dataset**.

## The publication path: `marianos_collector/runner.py`

`Collector` runs one category at a time and raises `ValidationFailure`, which ends the run
before anything is published, on any of these:

| Condition | Check |
|---|---|
| A page's store, ZIP or verified flag differs | `Location context mismatch` |
| A product's store context differs or is unknown | `Product-level store context mismatch or unknown` |
| The source cannot attest subcategories | `Provider cannot attest complete subcategory discovery` |
| A page or cursor repeats | `Repeated page/cursor discovered`, `Pagination cursor loop` |
| A category yields nothing | `Zero eligible products`, treating failed as not empty |
| A category falls below half its prior count | `Suspicious yield collapse` |
| A configured canary product is missing | `Missing canary product` |
| Fewer than 500 valid products | `Only N valid unique products` |

Completeness here is an attestation by the source, not a measurement: the gate requires
`subcategories_complete`, and it cannot detect a source that claims it wrongly.

This path would refuse this dataset, because five roots are empty and search cannot
attest subcategories.

## The path that made this data: `tools/kroger_full_sweep.py`

- **Errors.** `kroger.py` raises at once on HTTP 401 or 403, retries 429 and 5xx up to three
  attempts, and rejects a response of the wrong shape. A failure on one term is recorded in
  `page_failures` and the sweep moves on. This run recorded none, and its `stopped_reason` is empty.
- **Store.** The store is resolved from Kroger's `/locations` response and checked for banner,
  ZIP and street before collection. It is not re-checked during the run.
- **Empty roots.** They are listed in `categories_with_zero_products` and do not stop the run.
- **Truncation.** Terms reaching the limit are named. Terms ending short of Kroger's total
  were not named by this run; the report now has `short_of_reported_total`, and recomputing
  it here finds 11 terms.

The sweep has **no** canary check, no comparison with a prior run, no minimum yield and no
latency check. Abnormal latency, listed in the brief, is not detected on either path.

## What silent blocking would look like here

An API that returned HTTP 200 with an empty list would not be detected as blocking. It looks
the same as a term with no products: 17 of 301 terms returned nothing, and nothing here
distinguishes those from a refusal. All 301 terms completed and the run's later terms still
returned products, which is consistent with no blocking, but it is not proof of none.

The website route is separate. `marianos_collector/page_probe.py` stops on 401, 403, 429, 5xx,
refusal wording, a redirect off the site, a refused first-party subresource or a lost store
context. It did not contribute to this data.
