# Walmart contest acceptance ledger — v0.5.0

This is a working software prototype **not a completed contest entry**. This file is the truth source for status claims. Offline fixtures and mocked OPD responses are **synthetic**.

## Implemented and verified locally

- Exact 11 configured category roots from the supplied Walmart CSV (including Food and Pets exclusions).
- Product + page store ID and ZIP checks in the provider contract; only Walmart-seller local pickup/in-store offers admitted.
- Exact 22-column JSON string schema; `gupc` and `unit_price` blank; observed PPM preserved.
- Filter approximate-weight, marketplace and shipping-only items; avoid duplicate placements.
- Recursive category queue, pagination, interruption recovery, per-store locks, previous successful release protection, threshold/canary checks, logs and category counts.
- Trials (a subset of categories or OPD snapshots) use separate paths from full validated releases.
- Source revisions in consecutive pages are checked to prevent mixing updated feeds during recovery.
- Official OPD **documented** OAuth, store lookup, catalog snapshot and price snapshot integration. OPD results go to a **trial namespace**, not the complete source-of-truth dataset.
- No-credential `python tools/preflight.py`, category taxonomy diagnostic, and an explicit final submission evidence gate.

## Not yet proven (requires real access and observation)

1. Authorized live Walmart access with the intended rights to bulk collect, retain and transfer data.
2. Assigned store and real-time verification of pickup eligibility **for every included product**. A store-ID price snapshot alone is not proof of pickup eligibility.
3. Mapping every specified website category/subcategory to the OPD feed taxonomy; excluded paths also need verification. The mapping JSON is provisional.
4. Accurate distinction of retail regular vs sale prices, and full volume/digital coupon terms including clip requirements; OPD snapshot does not document all these fields.
5. At least **500 genuine unique records** for one assigned store, complete category counts, spot-checked products and PPM/promotion examples.
6. Fresh repeat run and interruption recovery *against real data* and observed twice-weekly jobs in the buyer's Azure environment.
7. Running cost under production rates, provider terms and actual volume.

## Test locally (no credentials)

From `walmart/` in the GitHub repository:

```bash
python -m unittest discover -v tests
python tools/preflight.py
python tools/walmart_opd_smoke_test.py --store both --dry-run
```

The resulting synthetic data is **not** contest evidence.

## Approved OPD trial (credentials stay with authorized owner)

```bash
export WALMART_OPD_CLIENT_ID='...'
export WALMART_OPD_CLIENT_SECRET='...'
export WALMART_DATA_AUTHORIZED=yes
python -m walmart_collector run --source opd --store 100 --authorized-source \
  --only-categories Food,Beauty --minimum-products 1 --opd-cache /persistent/opd-cache
```

**Important:** This invokes genuine Walmart feeds only if the credentials have explicit permission; outcomes are stored in `trials/`, not in the full-release pointer. The strict collector can fail if provisional mappings omit products. The retail pickup and promotions audits remain necessary.

To review a downloaded authorized taxonomy JSON:

```bash
python tools/opd_category_audit.py --taxonomy-file taxonomy.json
```

## Source-complete provider option

With a licensed provider returning the strict page contract (see `examples/approved_provider_page_contract.json`), the full collector may be run with `--source provider --authorized-source`. No provider credentials or approved endpoint are included in this repository. **An adapter alone is not the data source.**

## Submission gate

After generating real `data.json`, matching `report.json`, and a human `review.json` recording the evidence references and byte hash:

```bash
python tools/submission_gate.py --data data.json --report report.json --review review.json
```

It blocks when real records, complete category evidence, proof references, reviewed pickup eligibility, authorized access or Azure execution are missing. Even a successful gate is not a substitute for the contest holder's observed run.

**Do not describe this as a finished scraper or submit synthetic records as proof.**
