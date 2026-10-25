# Variant source guard and bounded category review

Spec: existing handover A/B/D and safeguards; actual option/size behavior observed through normal Mariano's UI.

- [x] Investigate missing identities using displayed price filters and variant choices, preserving raw observations.
- [x] Collect exactly 55 source-discovered IDs through store-pinned official API calls, capped at 60 attempts.
- [x] Read all 55 actual product pages and preserve matching UPC/store/time evidence.
- [x] Add RED-to-GREEN tests separating unfinished selection from matching-SKU pickup unavailability; reject malformed selection flags and unrelated primary UPCs.
- [x] Implement guards in existing API enrichment and temporal merge, before price comparison.
- [x] Run full tests/preflight and fresh review; audit the separate review export.
- [ ] Publish to the existing draft PR and package the exact source/evidence checkpoint.

Ruling: a matching resolved SKU that is out of stock must be quarantined, while an unfinished option/size state is discarded as unusable website evidence. Otherwise the pipeline either retains a known unavailable product or falsely quarantines a valid unrelated API record.

Ruling: reconciling 55 observed identities does not prove all variant families or all 28 roots have been traversed. Coverage flags stay false. No Azure changes, new permissions, paid providers or billing upgrades.
