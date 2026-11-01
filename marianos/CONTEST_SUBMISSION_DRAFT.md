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

# Mariano's Azure Scraper — Technical Prototype Submission

Hello,

I have developed a Python-based Mariano's collection framework based on the shared specifications and all 28 category roots in the provided CSV. It includes location checks, exact 22-field JSON generation, duplicate and approximate-weight filtering, deal-field validation, checkpoint recovery, fail-closed publication, and Azure Container Apps deployment configuration.

The offline code passes automated tests and a repeatable 560-record **synthetic** integration simulation across all 28 category roots. The simulated records are clearly labeled and are not represented as actual Mariano's products.

To complete the contest's required live 500-product demonstration, the collector must be connected to an approved category-complete data source and verified against an assigned Mariano's location. The public Kroger product search is available for authenticated location and sample price diagnostics, but it does not by itself establish full category or digital-coupon coverage.

The attached source package contains a one-command preflight, a live acceptance gate, a conditional Azure deployment script, a provider contract, and detailed instructions for observed testing. Credentials stay in the client's environment.

Please confirm the approved production data source and assigned location so the live acceptance test can be completed and independently verified.
