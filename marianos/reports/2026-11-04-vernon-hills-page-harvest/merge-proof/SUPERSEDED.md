# This merge-proof folder is superseded. Do not follow its instructions.

Both files here are kept because they are the evidence that the chained-merge
defect was real, and a corrected file cannot evidence that. Neither is edited.

## Do not rely on these

- **`merge_report_1nov_plus_4nov.json`, the key
  `values_by_field_and_source`.** It reads `ppm: {kroger_public: 529,
  crawl: 200}` and `volume_deals_description: {kroger_public: ..., crawl: 27}`.
  **The Kroger public Products API carries neither field at any tier.** Those
  are page-read values mislabelled as API values, because the second merge
  could not tell the first merge's contributions from the spine's own. The
  counts in the same file are correct; only the source labels are wrong, which
  is what made it survive a reading.

- **`README.md`'s instruction.** It says "the two page reads were merged onto
  it **in order**" and closes with "The same two commands against the 28,549
  spine produce that release's figures". That is the chained form, which this
  repository now declares incorrect, so the file instructs a reader to do the
  one thing they must not.

- **Its 729 / 147 / 53 totals.** They were measured against the superseded
  26,166 spine, not the delivered release, and the digital figure is wrong for
  a second reason: the chained run carried forward five coupons that were gone
  when those products were re-read, so 53 should be 49, and the cashback withholding then takes it to 48.

## What replaces it

One pass over both reads, `--page` and `--observed-at` repeated in pairs. Run
against the delivered 28,549 release that gives `ppm` 727,
`volume_deals_description` 146, `digital_deals_description` 48, **all three
attributed to `crawl` and none to the API**, zero conflicts, zero cross-read
disagreements, nothing refused. The correct invocation is in
`AUTONOMOUS_RUN_READINESS.md` and in the repository's working rules.

Neither file here predates the current tool by accident: they carry no
`page_reads` and no `cross_read_disagreements` keys, because the tool did not
have them yet. Their absence is a quick way to recognise a chained report.

## Why this marker exists rather than a deletion

The same reason `GAP_RESOLUTION.json` is kept beside its own `SUPERSEDED.md`.
A defect that is quietly deleted leaves nothing to show it was found, and the
next person has no reason to believe the gate that now prevents it was ever
needed. Found by an independent review on 4 November, which read the provenance
block rather than the totals.
