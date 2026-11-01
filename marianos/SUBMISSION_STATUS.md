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

# Mariano's contest — compliance matrix and blockers (v0.2.0)

The supplied shared technical requirements (pages 1–5) demand every CSV root/subcategory, location accuracy, 22 ordered JSON fields, twice-weekly Azure runs, restart protection, genuine 500+ products, demonstration and source transfer. The Mariano's CSV contains 28 root URLs.

| Requirement | Implemented / tested | Evidence and remaining issue |
| --- | --- | --- |
| Exact 28 Mariano's category roots | YES, offline | `config/categories.csv`; complete live traversal untested. |
| Discover all subcategories / paginate | YES for generic provider contract and synthetic recursion | Approved provider must actually enumerate live retailer category taxonomy. |
| Product and store accuracy | YES for strict field validation | Actual Kroger location IDs and market offer matches unverified. |
| 22 fields / proper order | YES, automated | UPC unmodified, PPM never calculated, `gupc` and `unit_price` blank, dates last. |
| Regular/sale/volume/digital offer separation | YES, schema enforcement | Actual coupon pages and all promotion conditions not yet retrieved. |
| Reject approximate weights / duplicates | YES, automated | Test fixtures and 560-record synthetic simulation. |
| Checkpoints / retries / no failed overwrite | YES, automated | Synthetic crash-and-resume, versioned publication. |
| Trials isolated from full releases | YES, automated | `trials/<hash>/...` differs from `published/...`. |
| Two weekly Azure jobs | CLI script implemented; not deployed | `azure/deploy_jobs.sh`, verified from shell syntax, no Azure account available. |
| 500+ genuine Mariano's products | **NO** | Only 560 synthetic records simulated; zero real data provided. |
| Complete live category proof | **NO** | Kroger Public Products `filter.term` cannot prove every URL/subcategory. |
| Independent location and price comparisons | **NO** | Requires approved credentials and buyer's assigned store. |
| Recorded walkthrough / buyer observed run | **NO** | Must be performed in the client's environment. |
| Final submission readiness | **BLOCKED** | `tools/submission_gate.py` fail-closed until live artifacts and human sign-off. |

## What to request from the organizer

1. The actual assigned Mariano's store address and Kroger location ID or permission to identify the store using authorized API access.
2. Licensed retail collection provider credentials or partner feed with complete 28-root category coverage, digital coupons, in-store price per measure, and data reuse rights.
3. Azure resource group / environment and secure procedure for credentials (no secrets in public contest files).
4. Opportunity to observe the required fresh run and inspect prices and promotions.

**This program is transferable open Python source, not a representation that these inputs have already been supplied.**

## v0.2.1 client-access preparation (2026-10-20)

- Added `tools/live_access_preflight.py` to let the buyer verify (a) Kroger API + actual store + small product preview or (b) first pages of an approved full-category provider without giving us credentials or publishing data.
- Added `ORGANIZER_ACCESS_REQUEST.md` and `CLIENT_LIVE_TEST_STEPS.md`. The live preflight report is deliberately non-acceptance evidence.
- **Unresolved blockers remain unchanged:** no buyer-assigned verified store or approved complete-category provider credentials, no 500 genuine records, no independently observed Azure execution, and no buyer-reviewed final offers/PPM.
- Do not send this package as proof that these live milestones have been achieved.
