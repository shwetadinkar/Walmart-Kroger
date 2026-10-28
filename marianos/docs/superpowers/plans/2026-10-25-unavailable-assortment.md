# Preserve unavailable assortment during temporal enrichment

Client feedback requires unavailable genuine products throughout. Replace availability-only exclusion with exact 22-field identity retention and blank current pricing/offer fields. A companion availability audit preserves the original API record and matched source/time/store evidence. Existing price/identity conflicts stay under their separate conservative rules. Do not change the historical exports.

Steps: RED retention/missing-price/stale-context tests; implement availability branch after identity/store/time checks but before price checks; run tests and full offline suite; fresh final review; deliver source and a separate reprocessed dated sample with manifest. No live requests, Azure deployment, subscriptions or billing changes.

Boundary: this improves supplied-input retention, not exhaustive discovery of API-omitted products or full catalogue acceptance.

Completed: retention tests RED then GREEN; fresh review identified unknown availability could blank prices; explicit product/store/unavailable proof regression RED then GREEN. Full offline suite 166 passed, including intercepted Chromium tests. Dated real sample reprocessing retained 55 identities, five unavailable with blank pickup pricing, 50 observed PPM values; no fresh collection. Source-level API omission remains an explicit separate dependency.
