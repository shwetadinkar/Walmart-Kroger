# Mariano's, Vernon Hills — update of 1 November 2026

Store 53100502, 1720 N Milwaukee Ave, Vernon Hills, IL 60061, pickup. The store
is confirmed in `data/store_verification.json`, which resolves the location id
to that address against Kroger's own locations service.

Three fields that were blank on every record are now populated for part of the
set, read from the retailer's own pages at your store.

## What is here

| Measure | Value |
|---|---:|
| Records at Vernon Hills | 26,166 |
| Distinct UPCs | 26,166 |
| Records with a category | 25,979 |
| Records with a **displayed** price per measure | **592** |
| Records with the retailer's **own volume deal wording** | **181** |
| Records with the retailer's **own digital coupon wording** | **51** |
| Client category roots the enriched records span | 22 |
| Disagreements between the two sources | 0 |

## How the three fields were obtained

The Kroger product API carries no displayed price per measure and no deal
wording at all, so those columns stayed blank rather than being calculated.
Every earlier attempt to read the retailer's pages failed: two browsers with a
protocol error on 26 October, a challenge on 28 October, and a probe on
31 October that was refused on its first request and read nothing.

On 1 November the pages served. The useful finding is where the values sit: the
**search results page** renders the price, the size, the price per measure, the
retailer's own deal wording and a link whose path ends in the UPC. So a separate
page per product is unnecessary. 28 page loads produced 656 cards over 649
distinct products, of which 635 matched a product already in the collection.

Every rate written is the string the retailer rendered, for example
`$0.03/fl oz`. None is composed, rounded, or worked out from price divided by
size. Deal text is the rendered line, split only by the retailer's own `Coupon:`
label. The merge runs through the project's composition layer, which binds every
contributed value to the product, store, fulfilment and time it was observed at,
and records which source supplied each field in `data/provenance.json`.

A by-product worth flagging: on items sold by weight the retailer displays a per
pound rate, for example `$0.69/lb`, beside a price it marks approximate, such as
`about $1.45 each`. The rate is kept, the approximate price is recorded under
its own name, and `regular_price` is left empty, because an approximate price is
not a fixed shelf price.

## What this does not establish

**Coverage.** 592 of 26,166 records carry a displayed rate. The other 25,574 do
not. The page route stopped before it could reach them, and the stop was not
diagnosed: the site returned a page with no products, the next request was
refused, and the machine's own connection failed at the same moment. Both
causes fit and this run did not separate them.

**Category completeness.** The collection is built from term-filtered search,
because the Kroger product API has no category enumeration. Term-filtered search
cannot attest complete category discovery, and nothing here should be read as
doing so. Where a root shows zero, that reflects Kroger's label vocabulary
rather than the shelf: Kroger publishes no label for Coffee, Batteries or Light
Bulbs, files Seafood inside a single `Meat & Seafood` label, and those products
are present in the data under the labels Kroger does use.

**22 roots is not 22 roots of coverage.** It means the 592 enriched records fall
into 22 of your roots.

**Not yet run unattended on Azure.** The durable checkpoint was proved by a
three-execution stop-and-resume trial on 28 October, but this collection was
produced locally and not through the scheduled path.

## One decision this package needs from you

Kroger's *Acceptable Use of Public APIs*, as I read it, prohibits systematically
gathering responses to build a database and prohibits comparing prices across
retailers. This collection comes from that public tier, and the collector has
carried a note since the start saying public tier output is not publishable for
that reason. I am not willing to quietly reverse my own note.

`ACCEPTABLE_USE_POSITION.md` sets out the position in full, including the limit
of my reading: I could not re-read the policy page, which needs a signed-in
developer account, so the two prohibitions above are my paraphrase and not
quoted text. It gives three options and they are all yours. Until one is chosen,
the data here is marked as a demonstration that the collector works at your
store, and is not marked publication eligible.

## Contents

| Path | What it is |
|---|---|
| `data/data_22_fields_enriched.json` | All 26,166 records, 22 fields, after the merge |
| `data/enriched_subset.json` | The 592 records the page read touched |
| `data/merge_report.json` | Counts, match rates, and what the merge does not establish |
| `data/provenance.json` | Which source supplied each field, and how many values |
| `data/store_verification.json` | The store resolved against Kroger's locations service |
| `page-read/` | The page-read report, the 656 cards as captured, and the parse |
| `merge/REPORT.md` | How the two sources were joined and the rules that governed it |
| `ACCEPTABLE_USE_POSITION.md` | The policy question and the three options |
| `evidence/` | The provider's reply on the Mariano's ZIP issue, and the site's robots.txt as read |

## Verifying

```bash
python3 verify.py
```

Needs Python and this folder. It rechecks every file against
`MANIFEST_SHA256.json` and fails if anything has changed or if the folder holds
a file the manifest does not list.
