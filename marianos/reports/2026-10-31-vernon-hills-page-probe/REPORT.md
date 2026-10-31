# Vernon Hills page probe, 31 October 2026

Store: Mariano's Vernon Hills, `53100502`, 1720 N Milwaukee Ave, IL 60061, PICKUP.
Evidence: `out/vernon-hills-page-probe-2026-10-31/` (`probe_run.json`,
`neutral_control.json`, `selection.json`). Merged output:
`out/vernon-hills-enrichment-2026-10-31/`.

## Result

**No page was read.** The first request to the site failed before any response,
so the run stopped there, as instructed. Nothing was retried.

| Measure | Value |
|---|---|
| Pages planned | 25, across 23 roots |
| Requests to the retailer | 1 (homepage, the store-selection step) |
| Product pages requested | 0 |
| Pages served before the failure | 0 |
| Store selected | No |
| What the failure looked like | `net::ERR_HTTP2_PROTOCOL_ERROR`; no response, no HTTP status, no body |
| When | 2026-10-31T14:46:17 UTC, 0.24 s after the run started |
| Batch duration | 0.365 s; the 30-second pace was never reached |
| `ppm` present | Not measurable: 0 pages read |
| `volume_deals_description` present | Not measurable: 0 pages read |
| `digital_deals_description` present | Not measurable: 0 pages read |

These are zero pages, not zero percent. The presence rates are unknown.

## Conditions

Chromium headless shell 153.0.8010.12 under Playwright 1.63.0, in a fresh isolated
context with no saved session and no proxy. Pacing was one page every 30 seconds.

## Neutral control

Run once after the stop, in the same browser build, with no retailer request.

| Target | Status | Protocol | Seconds |
|---|---|---|---|
| `https://example.com/` | 200 | h2 | 0.138 |
| `https://www.cloudflare.com/` | 200 | h2 | 1.279 |

So this browser and network complete HTTP/2 requests to other sites.
`neutral_control.json` was written after the run, so it is not listed in the
probe's `MANIFEST_SHA256.json`.

## Reading it against earlier evidence

The error matches the 26 October browser comparison, where isolated Chromium and
installed Chrome both failed with it on a retailer category page. On 28 October,
headed Chrome in a fresh context received HTTP 403 with a visible challenge on the
same kind of page. The closest thing to a page-count measure is also from 28
October: an agent-driven visible browser session at West Loop captured 34 product
pages between 15:25:53 and 15:30:50 UTC, and the next page was Access Denied at
15:31:21, with no HTTP status captured. That is a different condition and a
different store, so it is not a Vernon Hills threshold; see
`reports/2026-10-31-evidence-package/C4_BLOCKED_SOURCE_CHRONOLOGY.md`.

Taken together, this fits the site refusing fresh isolated browsers before store
selection, but this run does not prove it (see below).

## Deliberately not tried

Each of these would be a variation after a stop, so none was attempted: a second
request to the site, headed mode, another browser or channel, turning HTTP/2 off,
a copied session, or a different network route.

## What was merged

`composition.py` ran over all 24,683 spine products with the page source registered
as unavailable and its reason stated.

- 24,683 products out; no value differs from the spine.
- `field_provenance.json` names the source of each populated field, per product. All
  are `kroger_public_api`. There are no page bindings and no conflicts, because there
  was no page value to bind or to disagree.
- `ppm`, `volume_deals_description` and `digital_deals_description` stay blank on
  every product.
- The spine's file hashes are unchanged from before the run.

The output is the spine plus provenance. It adds no observed field.

## What this does not establish

- That the failure was bot protection. It carries no status and no challenge page,
  so the mechanism is unattributed. The stored `probe_run.json` says `kind: failed`,
  written before the classifier was corrected; the tool now writes
  `transport_failure_unattributed` for this case.
- That the site refuses at a page count. No page was served, so this measures no
  refusal threshold, and the requested threshold remains unknown.
- That every browser or network is refused. One browser configuration, one request.
- Anything about PPM or coupon presence at Vernon Hills. West Loop rates must not
  be carried over.
- That the product-page parser works on Vernon Hills pages. It has only been run
  against West Loop captures and synthetic fixtures.
- How retailer Savings wording would be read. `merge_page_probe.py` takes `ppm`
  and compares `regular_price`; offer text stays unresolved until real Vernon Hills
  pages exist to check a reading against.
- Representative coverage. The 25 selected products were all on sale in the API with
  a measured size, chosen to find these fields, so even a completed run would not
  have given a rate for the catalogue.
- The freshness rule in `temporal_enrichment.merge_export`, which limits the gap
  between website and API observations to 3600 seconds. It was not exercised.
- Whether the same request succeeds at another time.

## Terms

`marianos/README.md` records that Kroger's website terms restrict automated
extraction, and that Playwright automation requires authorization for the exact
collection use. This run was made on the account holder's explicit instruction.
That instruction does not settle what the terms permit.
