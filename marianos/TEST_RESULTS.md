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
