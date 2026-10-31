# Requirement 10: evidence the collector generated this data

## What ships

- `data/data_22_fields.json` and the run's own records, byte for byte.
- `data/vernon-hills-2026-10-31.log`, the run's console log, one line per term.
- `data/store_verification.json`, Kroger's `/locations` response.
- `raw_index.json`: all 888 captures, one per request, with path, size, SHA-256, term, start,
  time, products returned and Kroger's reported total.
- `raw_sample/`: a sample of those captures.
- `source/`: the code and configuration that ran.

## How the sample is chosen

By rule, seeded with the SHA-256 of the data file, so nobody picked the pages and anyone can
recompute the choice from `raw_index.json`. `--verify` does.

1. For each root with results, the first page of one term.
2. Every page of 3 terms stopped at the limit, from different roots.
3. Every page of the 11 terms ending short of their reported total.
4. Every page of the 17 terms with no result.
5. 30 further pages, the lowest-ranked by seeded hash.

The manifest gives the reason for each page.

## What was checked

Every one of the 3,633 products on the sampled pages is in the data file with the same URL path. For
the 2,428 that were first observed on a sampled page, the row's `regular_price` is a price on that page.
The index's request count equals the run's 888 requests, and its 38,162 returned placements, less
the 13,479 repeats, equal the 24,683 rows.

## What was left out, and why

- The other raw captures. All 888 captures are 336,572,613 bytes, too large to ship whole. Each one
  stays hashed in `raw_index.json`, so it can be supplied later and checked against that hash.
- `retention.json` and `checkpoint.json`, about 157 MB between them. Both are the run's working records;
  their hashes and sizes are in the manifest.

## The mask

Raw pages carry a Kroger `cid` tracking parameter in `productPageURI`. The value in these captures
differs from the older application's value already cleared for shipping, so that clearance
does not cover it. In `raw_sample/` each value is replaced by `cid=MASKED`. Nothing else in a page changes.

As a result a sampled page's hash differs from the original. The manifest gives both, but
the original hash can only be checked against the unmasked page, which stays with the operator.

## What this does not show

The sample, index and log were produced by the same operator's run. They show the data is consistent
with the captures and that the captures have the form of Kroger API responses. They do not prove a
third party watched the run. A fresh observed run is the test of that, and has not been held.
