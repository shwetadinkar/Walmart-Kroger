# Walmart & Mariano's — Azure Collector Projects

Two separate Python prototypes for the Walmart and Mariano's Freelancer contests, with retailer-specific code, tests, configuration, and Azure deployment files.

- [Walmart program](walmart/README.md)
- [Mariano's program](marianos/README.md)

Each program should be tested independently. Use `python tools/preflight.py` inside its folder for offline validation.

**Status, 1 November 2026.** Real data exists for both. Walmart: 615 provider
records for store 100, ZIP 72712. Mariano's: 26,166 Kroger API records for
Vernon Hills, store `53100502`, of which 592 carry a price per measure read from
the retailer's own pages, 181 carry volume deal wording and 51 carry digital
coupon wording. Some offline fixtures remain synthetic and are labelled as such
where they are used. What is still not done: observed twice-weekly deployment in
the client's own Azure environment, a client-observed fresh run, any page
observation in Walmart store 100's own context, complete category enumeration,
and the Kroger acceptable-use decision in `marianos/ACCEPTABLE_USE_POSITION.md`.

**Security:** This repository is public. Never commit credentials, tokens, or client secrets. A sealed Freelancer entry does not hide public GitHub source files.