# Product identity, observation freshness and retention

The delivered JSON remains exactly 22 ordered string fields. Identity is the selected store plus a verified retailer product ID from its product URL. Source UPC is optional; it is never derived or fabricated from URL digits. Blank UPCs do not deduplicate unrelated products. A conflicting nonempty UPC across distinct identities fails closed.

API normalization accepts verified store-assortment evidence independently of pickup availability and positive price. Missing/unusable prices are blank; raw source responses retain the original values. Store-scoped responses, category/provider store context, seller and approximate-weight rules remain separate eligibility checks. A fulfillment capability flag alone does not prove stock availability; explicit API inventory or dated website evidence is required for the availability sidecar.

Each versioned export adds retention.json keyed by stable identity: first_seen_at, last_observed_at, current/carried_forward status, last_successful_collection_at, availability and evidence time, per-field price/source observation dates, field freshness, source references/hashes, historical quotes and carry reason. Rows absent from a successful later collection keep their original crawl_date and historical values. A current directly observed row with no current price has a blank delivered price; previous quotes stay in sidecar history. Stale observations cannot refresh prior values.

Price conflicts retain identity with disputed price/offer fields blank and both source values in a separate conflict audit. Quarantine is an evidence review state, not an availability filter. Never interpret audit-only preservation as delivered-data retention.

Fresh minimum/yield, source/store, completeness and publication checks run before accumulation; carried records cannot disguise a failed/empty/abnormally thin source run. Previous successful output stays unchanged if a run fails. Retry checkpoints retain their original observation dates.

API collect/import, direct enrichment, temporal merge and generic category collector use this policy. Temporal CLI supports --previous-products and --previous-retention together; an explicit --collection-at is required for an empty current observation set. Existing historical baseline output is immutable: reprocess only into a new versioned location. An old generic-provider manifest without retention metadata fails with PREVIOUS_RETENTION_METADATA_REQUIRED rather than guessing observation dates.

One configured category is allowed without a two-category/global500 threshold; acceptance uses that configured scope. This does not establish any live category as complete. The current rendered source still fails during initial navigation and has not passed unattended product/variant/offer extraction.

Historical replays and controlled regression examples must state their source dates and changes. They are not fresh collection or live interruption/recovery evidence. No deployment/scheduling/billing change follows from passing tests.
