# October 27 client corrections — implementation ledger

User explicitly requests implementation without another design approval cycle. Reuse current Python collector, no Azure mutation, spend, or source bypass. Preserve all historical evidence and Walmart.

1. Add verified retailer-ID/URL stable identity and a shared accumulated-retention reconciler. Sidecars carry direct observation dates, field freshness, first/last seen, availability, collection time, source hashes and carry reasons. Current missing prices stay blank; absent/stale observations retain prior row with prior crawl_date and explicitly historical fields.
2. Correct normalize, collect, import, enrich, temporal merge and generic collector; identity-based dedup, not blank UPC. Reject malformed identities/store contexts and approximate weights. Keep price conflicts as audit without dropping eligible identities. Use current observations to validate fresh yield before carry-forward; never hide source failure with old rows.
3. Independent promotion identity/raw evidence reconciliation and checkpoint audit in parallel, restricted to their own paths.
4. Test RED→GREEN mandatory transitions, import/cloud publication integration and provider collector. Generate new versioned real-evidence replay exports, explicitly label controlled field-suppression scenarios versus actual observations. Correct acceptance ledger.
5. Keep one-category live demo BLOCKED unless compatible source actually works; source navigation evidence already local/Azure failures. No identical retries. Implement/test shared retention in future category collector without pretending fixtures are live.
6. Full suite, independent final review, exact private output package and source commit. No public raw/customer/credential payloads.

## Verification ledger

- RED witnessed: missing retention module; importer dropped unavailable/missing-price record, collapsed blank UPCs, lost absent identity; generic collector rejected configured single category; verified website price lost when API blank; source inventory out-of-stock misclassified. All corrected with targeted GREEN runs.
- Fresh final review found one important issue (website price lost on blank API field); regression failed then passed after fix. No other important findings.
- Full suite 185 tests passed including three intercepted offline Chromium checks. Current bounded local source check on 28 October failed first navigation, ERR_HTTP2_PROTOCOL_ERROR. No live category, recovery or scheduling claim.
- Historical promo correction verified bars1310 retained/chocolate1400 withheld under old policy, preserving actual coupon source and November3/4 contradiction; full evidence stays private. New policy retains conflict identities with price blanks in a separate replay.
- Current source snapshot/preflight verification and exact artifact/source hashes accompany private delivery. No historical baseline or Walmart file changed.
