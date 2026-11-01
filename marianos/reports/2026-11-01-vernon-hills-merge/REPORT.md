# Merging the page read into the API set, 1 November 2026

Store: Mariano's Vernon Hills, `53100502`, 1720 N Milwaukee Ave, IL 60061,
PICKUP.

The API sweep enumerates the assortment and supplies category, price, size, UPC
and the product URL. It supplies no displayed price per measure and no deal
wording, because the Kroger public Products API carries neither. The page read
of 1 November supplies exactly those three. This merges them.

It is done through `marianos_collector/composition.py`, not by hand. The API set
is the spine, the page read is an enrichment declaring only three fields, every
contribution is bound to the product, store, fulfilment and time it was observed
at, and the per-field precedence policy and provenance are the module's.

## Read this first: the spine is not the file the rerun package describes

| | Records |
|---|---:|
| `reports/2026-10-31-vernon-hills-package-rerun/README.md` states | 26,166 |
| The file this merge actually used | **24,683** |

The file used is `marianos/out/vernon-hills-enrichment-2026-10-31/data_22_fields.json`
from the operator's machine, SHA-256
`7f94979cd9bb0e2463264fd67a3805471fb684ce90a7526e96b239f23b94e8b6`,
20,020,742 bytes. It carries `Marianos - Marianos Vernon Hills` on all 24,683
rows and 24,505 of them have a category.

**The 1,483-record difference is not explained.** The folder name says
enrichment, not sweep, so this is most likely a later stage of the same run
rather than the rerun's own output, but that has not been established. Until it
is, the rerun package's figure of 26,166 and this merge's 24,683 are two
different numbers for what should be the same collection, and neither should be
quoted as the other. The rerun package's own data has not been located.

## Result

| Measure | Value |
|---|---:|
| Spine records in | 24,683 |
| Spine records out | 24,683 |
| Page cards offered | 656, over 649 distinct UPCs |
| Page UPCs matched in the spine | 611 |
| Page UPCs not present in the spine | 38 |
| `ppm` populated after the merge | 572 |
| `volume_deals_description` populated | 170 |
| `digital_deals_description` populated | 43 |
| Records carrying at least one page value | 572 |
| Client category roots those 572 span | 21 |
| Field conflicts between the two sources | 0 |
| Contributions refused as unbound | 0 |

Every one of those `ppm` values is attributed to `crawl` in `data/provenance.json`,
and every other field to `kroger_public`. No field was taken from both.

The 38 page UPCs with no spine record contributed nothing to any product. They
are not errors on the page's side; they are products the term-filtered sweep did
not reach. They are counted, named in `data/merge_report.json`, and left out.

## Rules this merge keeps

**No row is dropped.** 24,683 in, 24,683 out. A product the page read never
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

- **Coverage.** 572 of 24,683 records carry a displayed rate. The other 24,111
  do not, and the page route stopped before it could reach them.
- **Category completeness.** The spine is a term-filtered sweep. It cannot
  attest complete category discovery and this merge does not change that.
- **Price agreement between the sources.** Price is not taken from the page at
  all, so the two were never compared. A disagreement would have been recorded
  rather than resolved; none was looked for.
- **That 21 roots is 21 roots of coverage.** It means the 572 enriched products
  fall into 21 of the client's roots, not that those roots are covered.

## Reproducing it

```bash
python3 marianos/tools/merge_page_enrichment.py \
  --api <the 24,683-record data_22_fields.json> \
  --page marianos/reports/2026-11-01-vernon-hills-page-harvest/data/parsed_full.json \
  --out <output directory>
```

`data/enriched_subset.json` here holds the 572 records the page read touched,
which is the whole of what this step changed. The full 24,683-record output is
20MB and is not committed; it is regenerated exactly by the command above from
the two named inputs.

Verification: 14 tests direct and 485 under pytest, which agree. Two mutations
were run and both were caught: removing the foreign-store guard failed the store
test, and matching a page record by position instead of by UPC failed two of the
identity tests.
