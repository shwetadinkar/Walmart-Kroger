# Mariano's Azure Scraper — Technical Prototype Submission

Hello,

I have developed a Python-based Mariano's collection framework based on the shared specifications and all 28 category roots in the provided CSV. It includes location checks, exact 22-field JSON generation, duplicate and approximate-weight filtering, deal-field validation, checkpoint recovery, fail-closed publication, and Azure Container Apps deployment configuration.

The offline code passes automated tests and a repeatable 560-record **synthetic** integration simulation across all 28 category roots. The simulated records are clearly labeled and are not represented as actual Mariano's products.

To complete the contest's required live 500-product demonstration, the collector must be connected to an approved category-complete data source and verified against an assigned Mariano's location. The public Kroger product search is available for authenticated location and sample price diagnostics, but it does not by itself establish full category or digital-coupon coverage.

The attached source package contains a one-command preflight, a live acceptance gate, a conditional Azure deployment script, a provider contract, and detailed instructions for observed testing. Credentials stay in the client's environment.

Please confirm the approved production data source and assigned location so the live acceptance test can be completed and independently verified.
