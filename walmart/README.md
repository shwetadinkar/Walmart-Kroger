**Source-feasibility pilot (22 Oct 2026):** See [WALMART_SOURCE_FEASIBILITY.md](WALMART_SOURCE_FEASIBILITY.md) for provider candidates, advertised price examples, $0 trial rule, exact access gaps, and the new raw-response quality audit. No live Walmart source records have been obtained.\n\n# Walmart Azure Collector — v0.5.0 integrity update

**Run the Walmart offline checks directly on GitHub:** [Walmart offline verification](https://github.com/shwetadinkar/Walmart-Kroger/actions/workflows/walmart-offline.yml) (select **Run workflow**). [Successful initial workflow run](https://github.com/shwetadinkar/Walmart-Kroger/actions/runs/39544351675). The workflow uses synthetic fixtures only; it does not make authenticated Walmart requests.\n\n**Current stage:** offline-tested software; live 500-record acceptance and deployment have **not** been completed. Read [WALMART_ACCEPTANCE_STATUS.md](WALMART_ACCEPTANCE_STATUS.md) before submitting anything.

From the GitHub folder `Walmart-Kroger/walmart` run:

```bash
python tools/preflight.py
python -m unittest discover -v tests
```

**New safeguards:** partial-category and OPD tests are isolated under `trials/`, separate from the full `published/` pointer. Category pagination checks source revision across resumptions, and `tools/submission_gate.py` rejects unproven live-data claims. `tools/opd_category_audit.py` compares category roots against an authorized OPD taxonomy file but cannot independently verify completeness.

The authorized provider remains necessary for fully audited pickup-specific offers, site hierarchy and digital/volume promotions. No API key is committed; the OPD bulk source is provisional. See the acceptance ledger for the exact outstanding requirements.

---

> **v0.4.1 client preflight:** To verify everything locally with no Walmart API key, run `python tools/preflight.py` after extracting this package. See [PRE_CLIENT_TEST.md](PRE_CLIENT_TEST.md). This is a testing prototype, not proof of real Walmart records or an observed Azure deployment.

> **Update v0.4.0:** An official Walmart OPD snapshot-to-collector adapter is now included. See [`OPD_CLIENT_RUNBOOK.md`](OPD_CLIENT_RUNBOOK.md) for runnable client commands and unresolved acceptance limitations.

# Walmart Azure Collector — source project (v0.3.0)

A fail-closed Python collection and validation system based on the attached **Shared Scraper Technical Requirements** and **Walmart Category URLs**. Configured for Walmart Supercenter **#100 / ZIP 72712** and **#5959 / ZIP 77007**.

> **CURRENT STATUS — pipeline built and local fixture-tested, NOT a finished live Walmart scraper.** The buyer has not supplied an approved method of collecting live store-level Walmart product prices. The operational live collector therefore consumes an **authorized data provider's page feed** described below. There is no direct Walmart anti-bot workaround, reverse-engineered retailer API, or proven 500-record real-world dataset in this package. The source/provider interface must be connected to an approved data source, tested on real records and verified in Azure before the entry meets the contest conditions. Do not submit synthetic fixtures as product evidence.

## Implemented

- Uses all 11 category URLs **unchanged** from `config/categories.csv`. Explicitly ignores **Food → Shop All Foods / Recipes**, **Pets → Farm Animals** during nested category discovery.
- Supports multiple store IDs in `config/stores.json` without code duplication.
- Recursive subcategory discovery (complete provider-declared child list), multi-page pagination, cursor-loop detection, safety cap and checkpoint continuation.
- Each page and individual product must match store ID + ZIP and affirm store selection. Only `pickup` / `in_store` Walmart-seller offers pass.
- Produces **exactly 22 ordered fields**, all strings, no `remarks`/`gupc14`; `gupc` and `unit_price` are always `""`; PPM, UPC, URLs and deal terms are never invented or calculated.
- Separates explicitly supplied regular, sale, volume and digital deals. Filters non-clipped cashback misclassification, shipping-only / marketplace offers and approximate-weight items.
- Product deduplication across categories and pagination. Category-level counts, examples, field completeness, runtime and exclusions reported.
- Publisher writes new versioned data and report first, and updates `latest.json` **only after** all category and store validation passes.
- Azure Blob durable pages/checkpoints and renewable 60-second Blob lease for same-store exclusion; local filesystem implementation for tests.
- 2 weekly Azure scheduled-job examples; structured logs; no hardcoded production credentials.
- 27 automated tests including interrupted run recovery and retaining the previous good output.

**NEW: See [CLIENT_TESTING.md](CLIENT_TESTING.md) for three independently labeled acceptance test modes (offline, official OPD connectivity, authorized provider collection). A Walmart I/O API key is NOT automatically compatible with the collector’s normalized feed interface.**

## Fast start (no Azure account necessary)

```bash
cd walmart_azure_collector
python -m walmart_collector list
python -m unittest discover -v tests
python -m walmart_collector run --store 100 --source fixture
python -m walmart_collector run --store 5959 --source fixture
python -m walmart_collector status --store 100
python -m walmart_collector export --store 100 --export-file demo_bentonville.json
```

Fixture runs need no nonstandard Python packages (Python 3.11+). They generate **13 synthetic valid records per store**, spanning 11 categories. Sample fixtures also exercise a subcategory, pagination, a skipped Food recipe category, approximate-weight exclusion and shipping-only exclusion. These example records **do not exist on Walmart**. Do not claim the sample data is real or use it to satisfy a 500-record contest target.

You may optionally use an isolated virtual environment:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[test]'
```

## Official Walmart I/O OPD smoke test (optional)

A new **read-only** probe in `tools/walmart_opd_smoke_test.py` checks the *documented* Walmart I/O OPD OAuth and pickup store-locator endpoints, if you already have OPD API approval and credentials. It does **not** collect product prices or replace the authorized feed integration. See [WALMART_OFFICIAL_API_TEST.md](WALMART_OFFICIAL_API_TEST.md).

```bash
python tools/walmart_opd_smoke_test.py --store both --dry-run
# After OPD access is explicitly granted and environment secrets are configured:
python tools/walmart_opd_smoke_test.py --store both
```

## Connect a licensed / authorized live provider

The program makes a GET request to `PROVIDER_BASE_URL` with query arguments `store_id`, `zipcode`, `category`, `category_url`, and `cursor`. Its response **must** follow the documented structure in `examples/approved_provider_page_contract.json`:

- `store_id`, `zipcode` — **strings** reflecting the actual store used for that page.
- `store_context_verified` — boolean `true` only if the provider has actually checked the store context.
- `source_url` — Walmart HTTPS category/subcategory URL being processed.
- `location_evidence_url` — URL of independently inspectable evidence for the store context; **mandatory for live provider mode**.
- `children` — exhaustive list of immediate subcategory `{name, url}` objects. Provider recursively reports children for every discovered subcategory.
- `subcategories_complete` — `true` only if immediate subcategory discovery completed successfully; false fails the run.
- `next_cursor` — string continuation token (`""` means last page); **all products** must be enumerated, not just sponsored/first page items.
- `products` — array of observed products containing `store_id`, `zipcode`, `store_context_verified`, `seller_type` (`walmart`), `fulfillment` (`pickup` or `in_store`), `product_id` (strongly recommended), `product_title`, `weight`, `brand`, prices, observed promotions, source URLs, UPC and displayed PPM. See example JSON.

**This contract is an integration boundary, not an assertion that an authorized provider has been found.** Client must confirm access rights, costs, coverage, SKU identity, data completeness, fidelity of pickup/store context, and evidence links. Provider assertions do not replace spot checking against the retailer.

Set secrets privately (never add `.env` to git). Example commands:

```bash
export PROVIDER_BASE_URL='https://YOUR-APPROVED-PROVIDER.example/api/catalog'
export PROVIDER_API_TOKEN='YOUR-TOKEN-SET-SECURELY'
export WALMART_DATA_AUTHORIZED=yes
python -m walmart_collector run --source provider --authorized-source --store 100 --minimum-products 500
```

It will **refuse** a provider endpoint hosted directly on `walmart.com`, or without explicit authorization affirmation. It does not defeat CAPTCHA, challenge pages, or site rate limits. For a legitimate provider, adapt its actual contract into the `Page` contract in `sources.py` rather than claiming that the example endpoint exists.

For Azure, install `pip install -e '.[azure]'` or build the included Dockerfile, and configure Azure secrets. See [Azure Deployment](azure/AZURE_DEPLOYMENT.md).

## Files

```text
walmart_azure_collector/
├── README.md
├── CLIENT_TESTING.md                # offline / OPD / provider acceptance tests
├── pyproject.toml
├── Dockerfile
├── config/
│   ├── categories.csv                # user-provided 11-category file
│   └── stores.json                   # test stores #100 and #5959
├── walmart_collector/
│   ├── cli.py                        # run, list, status, export, clear-checkpoints
│   ├── config.py                     # category exclusions and store config
│   ├── schema.py                     # exact 22-field validation
│   ├── sources.py                    # fixture and approved-provider adapter
│   ├── runner.py                     # BFS, resume, QA, publishing
│   └── storage.py                    # local / Azure Blob, lock
├── fixtures/                        # all SYNTHETIC, both stores
├── tests/test_collector.py           # integration/regression tests
├── tests/test_provider_http_adapter.py  # offline mocked HTTP adapter tests
├── tools/client_acceptance.py       # unified handover test CLI
├── examples/
│   ├── approved_provider_page_contract.json
│   └── build_demo_fixtures.py
└── azure/
    ├── AZURE_DEPLOYMENT.md
    └── deploy_jobs.sh
```

## Status, snapshots and reset

`run` reports a manifest and validation metrics. Output is stored under `.collector-output` (local mode) or in the configured Azure container. `status` returns the pointer to the latest successfully published snapshot. `export` writes that exact JSON to a user-chosen file.

On any error, **the published pointer is not updated**. The run can restart from saved category queues/cursors/pages in the same storage backend. To abandon partial checkpoints, review the failure then run:

```bash
python -m walmart_collector clear-checkpoints --store 100 --confirm-reset
```

This does not delete already published validated data. Checkpoints older than seven days intentionally require review and explicit reset to avoid silently publishing a week-old mix of data. Staging snapshots are retained for debugging and must be lifecycle-managed separately (never remove active pages).

## Real-contest acceptance still to be proven

1. Client authorization/licensed feed and assigned testing store.
2. **At least 500 real distinct eligible products** across multiple client-required categories, and full catalog over all 11 roots and subcategories.
3. Actual spot checks of local prices, pickup/in-store identity, offers, PPM and UPC against real Walmart pages/source evidence.
4. Observed fresh run plus interrupted-recovery and repeat-run demonstrations in the customer's Azure subscription.
5. Deploy with production IAM, Key Vault secret references, schedule, alerts, cost controls, data retention, and an acceptance walkthrough.

All five items require a real approved data source and/or the customer's access. See [Requirements Coverage](REQUIREMENTS_COVERAGE.md) and [Azure Deployment](azure/AZURE_DEPLOYMENT.md).
