# ppm and regular_price on the 615, 31 October 2026

## What these columns were

`ppm` and `regular_price` were blank on all 615 records by decision, not because nothing
was available. The provider's numbers existed and were kept in the evidence sidecar.
`ppm` was held blank because no displayed string had been captured. `regular_price` was
held blank because `final_price` is an online price and not a store pickup price.

## What changed

Both decisions are reversed for this file. The basis is `walmart/evidence/2026-10-31-provider-ticket-754118.md`, the provider's
answer on ticket #754118. It states that `unit_price` and `unit` are taken from text on
the Walmart page and not calculated by the provider, and that the page price for the
store and ZIP context is the only price available, with no separate pickup price.

| Column | Populated | Blank | Source |
|---|---:|---:|---|
| `ppm` | 540 | 75 | `$<unit_price>/<unit>`, from the raw number, never rounded |
| `regular_price` | 614 | 1 | `final_price`, zeros added to two decimals, never rounded |

The brief's own `unit_price` column stays blank, and no other field changed. The
24 October file is unchanged. `FIELD_PROVENANCE.json` names, per value, the source field,
the snapshot row and the provider statement.

## What is still unevidenced

- **`ppm` is composed, not captured.** The brief asks for PPM exactly as displayed. These
  strings are assembled from two fields and are in dollars. The two page observations
  render cents: `86.8 ¢/lb`, captured at a Sacramento store, and `5.7 c/fl oz`, which
  appears in the provider-ticket note with no capture behind it in this repository.
- **The displayed form of the other units has not been observed.** Units here: `oz` 222, `fl oz` 184, `count` 51, `lb` 50, `ea` 29, `qt` 2, `pt` 1, `yd` 1.
- **Nothing is shown at store 100.** No page has been observed in store 100's context.
  The provider's account is of its own pipeline, and was not independently checked.
- **`regular_price` is the online price.** The brief asks for the store's pickup or in-store
  price. 143 populated prices are on products not available for pickup at their last observation.
- **2 products had differing values across snapshots.** The row the submission already
  named was used, and `VALUE_DISAGREEMENTS.json` lists each.
- **Values date from 22 and 23 October.** They have not been refreshed.
- **Client acceptance.** The provider-ticket note says `ppm` stays blank until the provider
  supplies the rendered string, a store 100 page shows the form, or the client accepts a value
  labelled as composed. The first two are unmet, and no acceptance is recorded in this repository.
