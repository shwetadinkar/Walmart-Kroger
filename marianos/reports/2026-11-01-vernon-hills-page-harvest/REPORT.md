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
| Cards captured | 432 recovered, 656 harvested |
| Distinct UPCs in the recovered set | 426 |
| Cards with a displayed `ppm` | 389 of 432 |
| Cards with retailer deal wording | 142 of 432 |
| Cards with a sale price | 136 of 432 |
| Cards sold by weight | 32 of 432 |
| Cross-term value disagreements | 0 |
| Displayed rate units | `oz` 188, `fl oz` 111, `lb` 50, `each` 40 |

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

**224 harvested records were not recovered.** Nine further terms, `makeup`,
`diapers`, `paper towels`, `aluminum foil`, `dog food`, `candle`,
`aa batteries`, `light bulb` and `notebook`, were harvested successfully and
counted, taking the run to 656 records. They were held in the page's own storage
pending the next checkpoint and the computer became unreachable first. They are
not lost: that storage persists in the browser profile and can be read back if a
page on that origin loads again. Until it does, only the 432 are in hand.

**It is signed out.** Digital coupon prices that require an account were not
visible, so this run says nothing about `digital_deals_description` coverage for
a signed-in shopper. No account was used and none will be without instruction.

**Nothing is joined yet.** The 426 UPCs have not been matched against the 26,166
API records, which are on the operator's machine. Overlap, and therefore how many
API rows this would actually enrich, is unknown.

**Prices are as the site reported them for this store context.** They were not
checked against the shelf, and no page was observed in-store.

## Terms of use

This route reads the retailer's public website, not the Kroger public API, so the
Acceptable Use of Public APIs question recorded in `../../ACCEPTABLE_USE_POSITION.md`
does not reach it. That is a change of question, not an answer to it: the website
carries its own terms, which have not been read here, and no claim is made that
this route is unencumbered. It is recorded so the two questions are not confused.

## Files

| Path | What it is |
|---|---|
| `data/harvest_checkpoint_1.tsv` | The 432 cards as captured, one row per card, lines in rendered order |
| `data/parsed.json` | The same cards parsed into fields |
| `data/parse_report.json` | Counts, units, and the cross-term conflict check |
| `../../tools/parse_page_harvest.py` | The parser. Reads shapes; reports what it does not recognise |
| `../../tests/test_parse_page_harvest.py` | 14 tests, including two that fail if a value is invented |

Parser verification: 14 tests direct and 471 under pytest, which agree with the
suite total. Two mutations were run and both were caught: writing the
approximate each-price into `regular_price` failed two tests, and deriving a rate
from price and size when none was displayed failed one.
