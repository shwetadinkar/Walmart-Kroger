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

# v0.2.1 verified handoff test

Date: 2026-10-20 (development environment)

- 33 Python `unittest` checks passed, including five new live-diagnostic logic tests.
- `python tools/preflight.py`: `offline_passed: true` with both demo stores, 28 fixture categories per store and two 560-record **synthetic** acceptance simulations.
- `python tools/live_access_preflight.py --mode kroger` with **no** credentials: exit code 1; writes sanitized `CONNECTION_FAILED` report and no credentials.
- Authentic Kroger API requests were **not** executed. No real store IDs, production discounts or price-per-measure were verified.
- Azure jobs were **not** deployed.
- Live 500 genuine records and observed acceptance remain blocked pending buyer-supplied approved access.
