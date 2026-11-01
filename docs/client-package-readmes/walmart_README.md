# Walmart, store 100 — update of 1 November 2026

Store 100, 406 S Walton Blvd, Bentonville, AR 72712.

This package carries one change to the trial submission you reviewed on
24 October, and the evidence behind it. The file you reviewed is included
unchanged beside the new one so the two can be compared directly.

## What changed

Two columns that were blank on all 615 records are now populated.

| Column | 24 October file | This file | Source |
|---|---:|---:|---|
| `regular_price` | 0 | **614** | the provider's `final_price` |
| `ppm` | 0 | **540** | the provider's `unit_price` joined to its `unit` |
| `sale_price` | 0 | 0 | — |
| `unit_price` | 0 | 0 | stays blank for your pipeline |
| `gupc` | 0 | 0 | stays blank |

Nothing else changed. Record count, titles, weights, UPCs, URLs, categories and
dates are identical.

`FIELD_PROVENANCE.json` carries an entry for every one of the 615 records. For
each value it names the source field, the snapshot file it came from, the row
index within that snapshot, that row's SHA-256, the observation timestamp, and
the provider's written statement it rests on.

## Why these were blank, and what unblocked them

You said on 31 October that keeping an unverified rate out of `ppm` was
appropriate pending direct provenance. I went back to the data provider on
ticket #754118 and asked two questions. Their written answers are reproduced
verbatim in `evidence/2026-10-31-provider-ticket-754118.md`:

- `unit_price` and `unit` are **taken from the text on the Walmart page**, not
  calculated by the provider.
- There is **no separate store-specific pickup price** anywhere in their output.

The first answer is the provenance you asked for, so `ppm` is now filled. The
second is why `regular_price` needs the caveat below rather than a clean bill.

## Three things this does not establish

**1. `ppm` is composed, not captured as displayed.** The provider holds the rate
split across a number and a unit. Joining them is formatting, not calculation,
and the number is never rounded. But Walmart renders the rate in cents and the
join produces dollars. For the first record in the file, Walmart's page shows
`5.7 ¢/fl oz` and this file carries `$0.057/fl oz`. Same number, different
notation. No rate is ever derived from price divided by size.

**2. `regular_price` is the online price, not a confirmed store price.** The
provider states no separate pickup price exists in their output. 143 of the 614
populated prices sit on products that were not available for pickup at their
last observation. One cross-check is worth your attention: the same product
showed `$5.78` on a live Walmart page in a Sacramento store context, equal to
the provider's figure for the 72712 run. One product is a data point, not proof,
but it is consistent with this being a national online price.

**3. Nothing here was observed in store 100's own context.** Every live page
observation available to this work resolves to a Sacramento store. Walmart
refuses to change the browsing location to 72712, with its own "technical
issues" message, and it refuses it the same way when a person does it by hand
rather than any automation. `reports/2026-11-01-store100-notation-probe.md`
records the attempts and what they do and do not show. The provider has been
asked whether it can supply the rendered string from its own store 100 context;
that question is open.

## Contents

| Path | What it is |
|---|---|
| `submission/` | The 615-record file with the two columns populated, plus provenance, a note on the columns, a summary, and the value disagreements |
| `submission/2026-10-24_as_reviewed/` | The file you reviewed on 24 October, byte for byte unchanged |
| `evidence/2026-10-31-provider-ticket-754118.md` | The provider's answers, quoted as received |
| `reports/2026-11-01-store100-notation-probe.md` | The attempt to observe store 100 directly, and why it did not succeed |

## Verifying

```bash
python3 verify.py
```

Needs Python and this folder. It rechecks every file against
`MANIFEST_SHA256.json` and fails if anything has changed or if the folder holds
a file the manifest does not list.
