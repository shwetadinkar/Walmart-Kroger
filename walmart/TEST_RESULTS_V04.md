# v0.4.0 observed test results (local, 2026-10-20)

- **35/35 automated tests passed** (`python -m unittest discover -q tests`).
- `python tools/client_acceptance.py offline --store both`: exit 0; each store produced 13 **synthetic** fixtures across the 11 configured categories.
- A simulated official OPD source joined catalog+store-price by `offerId` for Bentonville #100 and Houston #5959, and preserved directly displayed PPM. It excluded marketplace and other-store price rows. Both store runs published 2 synthetic records across two categories.
- A simulated compressed feed interruption did not change the previous published pointer; the next run completed.
- Streaming parser tested against newline JSON and JSON array inputs; no third-party parser dependency.
- Real OPD run attempted without credentials and exited 1, clearly reporting missing credentials, without contacting the API.
- **Not tested:** authenticated Walmart API calls, real store offers or promotions, 500 real records, full category taxonomy completeness, Azure observed job, load/cost benchmarks.

See OPD_CLIENT_RUNBOOK.md for live client tests and material limitations.
