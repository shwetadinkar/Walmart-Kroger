> **SUPERSEDED IN PART — rechecked 1 November 2026.** This document was written
> during the prototype stage, before any real data existed, and its "not yet
> done" statements were never revisited. The corrections below are authoritative
> where they conflict with the text that follows.
>
> **Now true:** 615 real provider records for Walmart store 100, ZIP 72712
> (`walmart/submission/`). 26,166 real Kroger API records for Mariano's Vernon
> Hills, store `53100502`, with the store resolved through Kroger's Locations
> API and the response committed. 592 of those carry a price per measure read
> from the retailer's own pages, 181 carry volume deal wording and 51 carry
> digital coupon wording. Kroger location IDs `53100502` and `53100508` are
> real, not illustrative. An Azure stop-and-resume trial ran three executions on
> 28 October and verified a durable checkpoint by SHA-256.
>
> **Still not done:** observed twice-weekly deployment in the client's own Azure
> environment; a fresh run observed by the client; any page observation in
> Walmart store 100's own context; complete category enumeration, which
> term-filtered search cannot attest; and the Kroger acceptable-use decision
> recorded in `marianos/ACCEPTABLE_USE_POSITION.md`.

# Mariano's Azure Collector v0.2.0 — verification results

Environment: Python 3.11+ compatible code; executed locally in a Python 3 runtime using only standard library (Azure SDK not required for offline tests). Date: 2026-10-20. No credentials were used. No network calls were made to Kroger, Mariano's, Freelancer or Azure.

## Verified

- `python -m unittest discover -q tests`: **28 tests passed**.
- `python tools/preflight.py`: **offline_passed: true**.
- Demo Lakeshore East 60601: 28 synthetic fixture records, one per configured root, all 22 fields in exact order.
- Demo West Loop 60661: 28 synthetic fixture records, one per configured root, all 22 fields in exact order.
- Full-scale simulation per store: **560 unique synthetic products across 28 roots**, 56 duplicate placements excluded; 85 page-fetch calls including a simulated interruption and successful checkpoint recovery.
- Full-scale simulation checked displayed PPM preservation, promotion descriptions, cross-placement deduplication, run status and trial/full publication separation.
- Fewer than 500 fixture records: correct rejection, no successful publication.
- `tools/submission_gate.py`: refuses synthetic fixtures and missing human attestation.
- `bash -n azure/deploy_jobs.sh`: syntax passed; `--dry-run` exercised using *illustrative* store ID 12345678, no Azure changes.

## Not verified

- 500 **real** records from Mariano's: **0 collected**.
- Approved data rights and production credentials.
- Live Kroger API connectivity and real location identification.
- Complete live category/subcategory enumeration, displayed PPM, and full digital/volume promotions.
- Docker image build/push and actual Azure job creation/execution.
- Buyer-observed fresh run, random price comparisons, repeated execution and walkthrough recording.

**This is not a final contest acceptance record.** All product counts in this report refer to explicitly labeled synthetic test data.
