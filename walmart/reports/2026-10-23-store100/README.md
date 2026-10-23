# Walmart Store #100 — filtering audit, 23 October 2026

**Source:** 28 distinct Bright Data Walmart JSON snapshots, locally imported and audited. **Target:** Store 100, ZIP 72712.

- **899 total responses**: 381 distinct assortment candidates, 38 duplicate product occurrences, 380 product rejections and 100 upstream source errors.
- **480 exclusion/error decisions** are in [filtered_review_public.csv](filtered_review_public.csv). This is a **sanitized ledger** (source filename, zero-based row, reason, product ID, retailer page URL when available, seller, root category, observed store/ZIP and source-row hash), not a raw dataset.
- Exclusion reasons: 157 unverified Walmart seller; 133 outside required category root; 86 store mismatch/missing; 4 mismatched/malformed product ID/URL; 48 dead page, 47 CAPTCHA, 3 selector timeouts, 1 parse error, 1 unspecified source error.
- Failed requests are **collection failures, not evidence of out-of-stock inventory**. No records rejected due to pickup-unavailable status alone.
- No raw Bright Data payloads, API tokens, verified local prices, PPM, or offer text are stored in this public repository.

**Interpretation:** '381 candidates' is **not** 381 client-accepted products; source-specific pickup prices, directly displayed PPM, promotions, complete category coverage, and Azure execution are still unverified.

For each decision, find the original private source file using `source_file` and `source_row_zero_based`, and verify its SHA-256 digest; the matching raw responses and rejection audit belong in authorized private storage, not public GitHub.

**Next run:** use the importer and the audit exporter to regenerate this ledger from newly downloaded authorized private snapshots; preserve historical records and audit metadata separately.
