# Walmart & Mariano's — Azure Collector Projects

Two separate Python prototypes for the Walmart and Mariano's Freelancer contests, with retailer-specific code, tests, configuration, and Azure deployment files.

- [Walmart program](walmart/README.md)
- [Mariano's program](marianos/README.md)

Each program should be tested independently. Use `python tools/preflight.py` inside its folder for offline validation. Product fixtures are synthetic. Live retailer access, 500 genuine records, and observed Azure deployment are not yet verified.

**Security:** This repository is public. Never commit credentials, tokens, or client secrets. A sealed Freelancer entry does not hide public GitHub source files.