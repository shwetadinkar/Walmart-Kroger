# Merging the page read into the API set, 1 November 2026

Store: Mariano's Vernon Hills, `53100502`, 1720 N Milwaukee Ave, IL 60061,
PICKUP. The store is confirmed in `data/store_verification.json`, which resolves
`locationId` `53100502` to that address at 2026-10-31T20:56:15Z.

The API sweep enumerates the assortment and supplies category, price, size, UPC
and the product URL. It supplies no displayed price per measure and no deal
wording, because the Kroger public Products API carries neither. The page read
of 1 November supplies exactly those three. This merges them.

It is done through `../../marianos_collector/composition.py`, not by hand. The API set
is the spine, the page read is an enrichment declaring only three fields, every
contribution is bound to the product, store, fulfilment and time it was observed
at, and the per-field precedence policy and provenance are the module's.

## Which spine, and why it had to be corrected

`marianos/out/` on the operator's machine holds several runs at this store:

| Folder | Records |
|---|---:|
| `vernon-hills-2026-10-31-rerun/` | **26,166** |
| `vernon-hills-enrichment-2026-10-31/` | 24,683 |
| `vernon-hills-2026-10-31/` | 24,683 |
| `probe-vh/` | 1,603 |
| `probe-v2/` | 1,571 |

The first version of this merge used the 24,683-record file, which is the run
from **before** the paging correction in commit `78f57dc`. That was wrong: those
1,483 records are the ones the paging fix recovered, and they were never offered
to the merge. This report describes the corrected merge against the 26,166-record
rerun, SHA-256
`842c2dbee1b7d897568abec90adcdb80131a606b9e71212b923f7b5025eb0b6a`,
21,257,021 bytes, 26,166 distinct UPCs with no duplicates and 25,979 carrying a
category.

**On the enrichment folder in that table.** An earlier version of this report
said `vernon-hills-enrichment-2026-10-31/` held enrichment built on the
superseded set, and that it needed rebuilding. That overstated it. Checked: its
24,683 records carry **no page-read values at all** — `ppm`,
`volume_deals_description`, `digital_deals_description`,
`volume_deals_price` and `digital_deals_price` are empty on every row. That
matches the 31 October page probe, which read zero pages before the site refused
(`reports/2026-10-31-vernon-hills-page-probe/REPORT.md`). So the folder is the
pre-correction run with nothing added, not stale enrichment. There is nothing in
it to rebuild, and this merge supersedes it entirely.

## Result

| Measure | Value |
|---|---:|
| Spine records in | 26,166 |
| Spine records out | 26,166 |
| Page cards offered | 656, over 649 distinct UPCs |
| Page UPCs matched in the spine | 635 |
| Page UPCs not present in the spine | 14 |
| `ppm` populated after the merge | 592 |
| `volume_deals_description` populated | 181 |
| `digital_deals_description` populated | 51 |
| Records carrying at least one page value | 592 |
| Client category roots those 592 span | 22 |
| Field conflicts between the two sources | 0 |
| Contributions refused as unbound | 0 |

Every `ppm`, `volume_deals_description` and `digital_deals_description` value is
attributed to `crawl` in `data/provenance.json`. Every other field is attributed
to `kroger_public`. No field was taken from both.

Spread of the 592 across the client's roots: Household 90, Meat 53, Beverages
50, Beauty 40, Dairy 33, Frozen 32, Grocery 28, Candy 26, Bakery 25, Baby 25,
Health 24, Pet Supplies 24, Breakfast 24, Beer Wine Liquor 24, Candles and Home
Fragrances 23, Natural Organic 19, School Office 15, Deli 13, Personal Care 11,
Produce 6, Hardware and Home Improvement 3, Kitchen and Dining 1. Three of the
592 carry no category, because their Kroger label is not in the map, and they
are kept with the field empty rather than guessed.

The 14 page UPCs with no spine record contributed nothing to any product. They
are counted and named in `data/merge_report.json` and left out. Against the
superseded spine this number was 38, so the paging correction accounted for 24
of them.

## Rules this merge keeps

**No row is dropped.** 26,166 in, 26,166 out. A product the page read never
reached keeps empty strings in those three fields and stays in the set, which is
the retention rule in PART 0.

**No value is composed.** The rate written is the string the retailer rendered.
Deal text is the rendered line, split only by the retailer's own `Coupon:`
label: a line it prefixes that way becomes `digital_deals_description`, anything
else becomes `volume_deals_description`. No promotional price is derived from
deal wording, and `volume_deals_price` stays empty throughout.

**No page value reaches another store.** The tool refuses the whole merge if the
spine carries any store name other than the one given, which is what stops a
West Loop row being enriched by a Vernon Hills page read. There is a test that
fails if that guard is removed.

**`gupc` and `unit_price` stay empty**, as everywhere else.

## What this does not establish

- **Coverage.** 592 of 26,166 records carry a displayed rate. The other 25,574
  do not, and the page route stopped before it could reach them. 22 roots
  appearing here means the 592 fall into 22 of the client's roots, not that
  those roots are covered.
- **Category completeness.** The spine is a term-filtered sweep. It cannot
  attest complete category discovery and this merge does not change that.
- **Price agreement between the sources.** Price is not taken from the page at
  all, so the two were never systematically compared. A disagreement would have
  been recorded rather than resolved; none was looked for.
- **Anything about the acceptable-use question.** The spine is Kroger public
  API data and sits under `../../ACCEPTABLE_USE_POSITION.md` exactly as before.
  Merging page-read fields onto it does not change that, and
  `publication_eligible` is untouched.

## Reproducing it

```bash
python3 marianos/tools/merge_page_enrichment.py \
  --api <vernon-hills-2026-10-31-rerun/data_22_fields.json> \
  --page marianos/reports/2026-11-01-vernon-hills-page-harvest/data/parsed_full.json \
  --out <output directory>
```

`data/enriched_subset.json` holds the 592 records the page read touched, which
is the whole of what this step changed. The full 26,166-record output is 21MB
and is not committed; it regenerates exactly from the two named inputs.

Verification: 14 tests direct and 485 under pytest, which agree. Two mutations
were run and both were caught: removing the foreign-store guard failed the store
test, and matching a page record by position instead of by UPC failed two of the
identity tests.
