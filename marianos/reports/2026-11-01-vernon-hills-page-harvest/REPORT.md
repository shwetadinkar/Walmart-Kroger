# Vernon Hills page harvest, 1 November 2026

Store: Mariano's Vernon Hills, `53100502`, 1720 N Milwaukee Ave, IL 60061,
PICKUP, selected in the browser itself and confirmed in the page header as
"Pickup at Marianos Vernon Hills".

Route: the Claude desktop app's built-in browser pane, running on the operator's
own computer with its ordinary persistent profile, signed out. Not a headless
browser, not an isolated context, no proxy, no identity rotation and no
challenge was presented or answered.

## Why this run happened

Three earlier attempts at retailer pages failed in three different ways:

| Date | Condition | Result |
|---|---|---|
| 26 October | Isolated Chromium and installed Chrome, category page | `ERR_HTTP2_PROTOCOL_ERROR` |
| 28 October | Headed Chrome, fresh context | HTTP 403 with a visible challenge |
| 31 October | Headless Chromium under Playwright, Vernon Hills | `ERR_HTTP2_PROTOCOL_ERROR` on request 1, no page read |

`ppm`, `volume_deals_description` and `digital_deals_description` were therefore
blank on all 26,166 records of the 31 October API collection, and were left
blank rather than calculated.

## What this run establishes

**The pane serves the pages.** The homepage, the store selector and 26 search
result pages were served normally at Vernon Hills.

**The search results page carries all three missing fields at once.** Opening a
product detail page per product turns out to be unnecessary. Each result card
renders the price, the size, the displayed price per measure, the retailer's own
deal wording, and a product link whose path ends in the UPC, which is the join
key back to the API records.

| Measure | Value |
|---|---|
| Terms requested | 27 |
| Terms that returned cards | 26 |
| Page loads to the retailer | 28, including the homepage |
| Cards captured | 656, all recovered |
| Distinct UPCs | 649 |
| Cards with a displayed `ppm` | 608 of 656 |
| Cards with retailer deal wording | 217 of 656 |
| Cards with a sale price | 181 of 656 |
| Cards sold by weight | 32 of 656 |
| Cross-term value disagreements | 0 |
| Displayed rate units | `oz` 206, `each` 170, `fl oz` 115, `lb` 74, `sq ft` 43 |

Every rate above is the string the retailer rendered. None was composed from
parts, none was rounded, and none was derived from price divided by size. A card
that displayed no rate has an empty `ppm`, and `../../tests/test_parse_page_harvest.py`
holds a test that fails if a rate is ever computed from a price and a size.

**Sold-by-weight items answer a question that was parked for the client.** The
retailer displays a per-pound rate on them, for example `$0.69/lb`, beside a
price it labels as approximate, for example "about $1.45 each". The parser keeps
the rate, records the approximate price under its own name, and leaves
`regular_price` empty, because an approximate price is not the fixed price that
column means. 32 cards are in this shape.

## What this run does not establish

**It is not category completeness.** Term-filtered search cannot attest complete
category discovery, and nothing here should be read as doing so. 26 terms were
chosen to spread across the client's roots, not to exhaust them.

**The cause of the stop is not isolated.** The 27th term, `extension cord`,
returned a page with zero product cards and a title that fell back to the raw
URL. The next navigation was refused. At the same moment the link to the
operator's computer began failing intermittently, and shortly after it
disconnected entirely. A retailer refusal and a dropped desktop link are both
consistent with what was seen, and this run did not separate them. The earlier
pattern, 34 pages at West Loop on 28 October followed by Access Denied, is
consistent with a retailer refusal, but consistency is not proof and 28 page
loads is not a measured threshold.

Later the same day the computer reconnected and `www.marianos.com` served
immediately, with no challenge and no refusal. That is evidence against a
standing retailer block and toward the dropped desktop link, but it is not
proof either: hours had passed, and a refusal that expires on its own would
look exactly the same. The honest statement remains that this run did not
separate the two causes. For contrast, Walmart on the same day did issue an
explicit bot challenge, titled "Robot or human?", and that is what a retailer
refusal looks like when it is unambiguous; see
`walmart/reports/2026-11-01-store100-notation-probe/REPORT.md`. Nothing of that
kind was ever shown by this retailer during this run.

**The 224 records held over from the interrupted session were recovered.** The
run was checkpointed at 432 when the operator's computer became unreachable, and
the remaining nine terms stayed in the browser profile's own storage. On 1
November the origin was reloaded and all 656 read back intact across all 26
terms, so nothing from this run was lost. The 432-record checkpoint is kept
beside the full set rather than replaced.

**It is signed out.** Digital coupon prices that require an account were not
visible, so this run says nothing about `digital_deals_description` coverage for
a signed-in shopper. No account was used and none will be without instruction.

**The join is done, and it is reported elsewhere.** An earlier version of this
section said nothing was joined yet and gave a UPC count of 426, which appears
nowhere else in this report and contradicts its own table of 656 cards over 649
distinct UPCs. Both were wrong. The 649 were matched against the 26,166-record
collection the same day: 635 matched, 14 did not. See
`../2026-11-01-vernon-hills-merge/REPORT.md`.

**Prices are as the site reported them for this store context.** They were not
checked against the shelf, and no page was observed in-store.

## Terms of use

This route reads the retailer's public website, not the Kroger public API, so the
Acceptable Use of Public APIs question recorded in `../../ACCEPTABLE_USE_POSITION.md`
does not reach it. That is a change of question, not an answer to it: the website
carries its own terms, which have not been read here, and no claim is made that
this route is unencumbered. It is recorded so the two questions are not confused.

One part of it is checkable and was checked. `www.marianos.com/robots.txt` was
read on 1 November and is kept verbatim at
`../../evidence/2026-11-01-marianos-robots.txt`, SHA-256
`ede59005502216460d9eab5d79cbd36a033c8dca5f52426b183ad2c187eecdd3`. It carries a
single `User-agent: *` group disallowing accounts, checkout, scheduling,
clickstream, the order-ahead kiosk, the recipes API, PDFs, `/in-stores/` and
`/locations*`, and it publishes a sitemap. The paths this run read, `/search`
and `/p/`, are not disallowed, and no crawl-delay is set. That covers robots.txt
and nothing else: the site's terms of use are a separate document and have not
been read.

## Files

| Path | What it is |
|---|---|
| `data/harvest_full.tsv` | All 656 cards as captured, one row per card, lines in rendered order |
| `data/parsed_full.json` | All 656 parsed into fields |
| `data/parse_report_full.json` | Counts, units, and the cross-term conflict check for all 656 |
| `data/harvest_checkpoint_1.tsv` | The first 432, kept as the interrupted run's checkpoint |
| `data/parsed.json` | The same cards parsed into fields |
| `data/parse_report.json` | Counts, units, and the cross-term conflict check |
| `../../tools/parse_page_harvest.py` | The parser. Reads shapes; reports what it does not recognise |
| `../../tests/test_parse_page_harvest.py` | 14 tests, including two that fail if a value is invented |

All 656 cards parse with no unrecognised shapes and no cross-term
disagreements.

Parser verification: `tests/test_parse_page_harvest.py` runs 14 tests directly
and contributes the same 14 to the Mariano's suite, which stands at 485. Two mutations were run and both were caught: writing the
approximate each-price into `regular_price` failed two tests, and deriving a rate
from price and size when none was displayed failed one.
