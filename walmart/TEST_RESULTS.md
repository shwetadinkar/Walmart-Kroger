# Local Verification Report — walmart_azure_collector

**Verification type:** Synthetic offline fixture integration tests only. This is **not** verified Walmart live-data evidence or proof of deployment to Azure.

| Check | Result |
|---|---|
| Python unit/integration tests | **27 passed** (`python -m unittest discover -v tests`) |
| Category roots from supplied CSV | **11** |
| Bentonville ZIP / store ID | **72712 / #100** |
| Houston ZIP / store ID | **77007 / #5959** |
| Bentonville valid unique records | **13 synthetic** |
| Houston valid unique records | **13 synthetic** |
| Categories with eligible records | **11** per store |
| Synthetic excluded approximate-weight products | **1** per store |
| Synthetic excluded shipping-only products | **1** per store |
| Simulated interrupted run / checkpoint resume | **Passed** |
| Prior successful snapshot preserved after failure | **Passed** |
| Per-store lock tested locally | **Passed** |
| Live authorized Walmart records / 500 record acceptance | **NOT TESTED** |
| Azure job deployment / live scheduling / Blob lease | **NOT TESTED** |

The 22 ordered output fields are validated as all strings, with `gupc` and `unit_price` blank and `crawl_date` last. The code also rejects unauthorized/Walmart-hosted provider endpoints, store mismatches, unsupported fulfillment, invalid coupons, missing canaries, suspicious yield drops and missing location evidence in provider mode.

See `examples/synthetic_bentonville_output.json` and `examples/synthetic_houston_output.json` for non-real examples. Do not submit these to the contest as genuine scraped data.


## v0.3.0 addendum — independently reproduced on 2026-10-20

- 27 automated tests PASS (including four mock HTTP provider-adapter tests).
- `python tools/client_acceptance.py offline --store both` PASS.
- 13 **synthetic** eligible records for store #100 and 13 for store #5959, spread over 11 configured root categories per store.
- Missing Walmart OPD credentials correctly fail (exit status 2); no authenticated Walmart OPD calls executed.
- Approved live provider feed, live 500 product records, local prices, actual coupons, full category completeness, and Azure deployment remain **unverified**.
- All mock response evidence and synthetic product URLs are generated solely for test execution and must not be presented as client contest evidence.

See `CLIENT_TESTING.md` and `tools/client_acceptance.py`.
