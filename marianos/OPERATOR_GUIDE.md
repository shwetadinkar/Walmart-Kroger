# Mariano's operator guide — current engineering handover

## What this package can and cannot do

The software has configuration validation, exact product normalization, checkpoint/retry safeguards, isolated review outputs and last-good publication protection. The historical 650-product West Loop API export is real. The website examples and promotion observations are separately dated evidence. The production source gate is still open: neither Windows nor Azure unattended browser navigation has passed, the public app lacks partner catalog scope, and full category/PPM/coupon acceptance has not been demonstrated.

No production deployment or scheduling is authorized by this guide. Do not treat a valid configuration, passing offline test or completed listing report as submission readiness. `submission_ready` remains false. The latest source package has not been deployed to Azure.

## 1. Start locally without keys or cloud access

Extract the package. Open a terminal **inside its `marianos` directory**, where pyproject.toml, config/ and tools/ are visible. Python 3.11 or later is required. The offline workflow uses the standard library; no installation, API key, shell-policy change or subscription is needed.

```powershell
python --version
python tools/preflight.py
```

Expected: `offline_passed: true`. The generated report is `client-test-output/preflight.json`. It includes tests plus two clearly labelled 560-record SYNTHETIC recovery simulations. Those records are deliberately invented and must never be submitted as retailer data. The tests simulate access failures; such expected errors in captured test output are not real network observations.

## 2. Validate client configuration before collection

Start from config/discovery.westloop.example.json. This contains store 53100508, ZIP 60661, one Batteries root, isolated discovery-review output and disabled scheduling. The all-roots example preserves all 28 requested roots but has not passed live traversal. Do not run either browser job merely because configuration passes.

```powershell
python -m marianos_collector.operations check --config config/discovery.westloop.example.json --store-id 53100508 --zipcode 60661 --output .operator-output/config-check
```

Expected: exit 0, `status: valid`, `live_store_verified: false`, `submission_ready: false`. Review the generated operational-report.json and operational-report.md. Wrong store/ZIP, unsafe namespace, credential fields, malformed limits, enabled schedule or out-of-range cron fail with exit 2 and a safe error code. The checker makes no network request.

Edit a copy of the JSON for another store: id, zipcode, name and street must all describe that exact store. A syntactically valid configuration does not verify a real address or store entitlement. Verify through an authorized source before a live run. Select roots from the supplied CSV; do not invent a category crosswalk. Category/page/action/time limits can deliberately end discovery incomplete. Do not impose a 500-product requirement on a smaller selected category.

The output_prefix is deliberately restricted to a discovery namespace. It cannot redirect discovery into the protected trials or published product namespaces. Runtime Azure container/blob settings are separate from this application prefix and remain unchanged unless explicitly approved.

## 3. Read one consistent operational report

New source writes automatically create these supplementary JSON reports:

- Discovery: `<discovery-prefix>/<store>/<execution>/operational-report.json`, alongside receipt.json.
- API execution: `executions/<store>/<execution>.operations.json`, alongside the authoritative execution receipt.

The authoritative receipt/checkpoint remains the recovery source. A supplementary report storage failure is logged as `operational_report_unavailable`; it does not replace or hide the original source error. Older images/runs do not gain reports retroactively.

You can generate local JSON and Markdown from downloaded evidence without launching collection:

```powershell
python -m marianos_collector.operations report --mode discovery --receipt RECEIPT.json --config CONFIGURATION.json --coverage COVERAGE.json --output .operator-output/run-review
```

Replace the capitalized filenames with your local files. **Omit --coverage when the run failed before coverage existed.** The client package includes an exact failed-cloud example and ready-made reports. For API execution receipts use --mode api-trial, optionally --validation VALIDATION.json. For an existing provider/fixture Collector report.json use --mode collection --receipt REPORT.json. The original collection report remains available; this command is its unified local view.

Exit 0 means the input described valid configuration or a completed/validated software stage. Exit 2 means invalid local input, or a failed/blocked/incomplete run; in the latter case the review report is still written. Every report keeps submission_ready false. Null counts mean not recorded, **not zero**. Browser actions, navigation actions, pages, HTTP attempts and accepted records are distinct quantities. Do not add them together.

An API candidate whose receipt state is validated but whose publication is unfinished is reported as `publication_pending` with exit 2. It is not a completed run. Resolve the original publication failure and resume the same execution; do not discard the last valid pointer.

Reports copy only selected identities, dates, counters and safe failure codes; they do not copy source bodies, arbitrary exception messages or credentials. Cross-store/ZIP/execution evidence is rejected. Input hashes establish exactly which local files were used, not independent retailer authenticity. Report generation refuses to overwrite an input file.

## 4. Understand recovery and freshness

- Resume only the same genuine execution identity with identical configuration. Persisted budgets still apply; restarting does not reset its allowance.
- A separate real execution must obtain a distinct execution identity. Do not set a permanent MARIANOS_RUN_ID for scheduled runs.
- Completed execution retries are idempotent. An older validated candidate cannot roll back a later successful pointer.
- Candidate objects are versioned before latest is changed. Failed validation, abnormal low yield, locality mismatch, damaged staged data or publication failure must preserve the last valid release.
- A discovery access block is durable; do not repeatedly restart that execution to evade it. Incomplete bounded discovery is not a complete category. Changing configuration requires a separate reviewed execution, not editing checkpoints.
- Keep quarantined/unavailable evidence separate from accepted output. Do not join historical prices/offers into a new observation without exact store, identity, timing and price validation.

Offline preflight covers controlled recovery, multi-store fixtures, deduplication and trial/publication isolation. The execution-state tests cover budget persistence, publication interruption, corrupt output, same-execution idempotence and separate source calls. These are controlled tests, not genuine cloud forced-stop/resume or live fresh-repeat acceptance.

## 5. Existing Azure setup and secret handling

The existing separate Mariano's job is marianos-westloop-api-pilot. Its restored approved runtime is image tag 8a375326b9334b38d01e5159d553377099442937, mode api-trial, store 53100508 / 60661, manual trigger, 0.5 CPU / 1 GiB, 600-second timeout, zero retries, parallelism/completion 1. API limits were target/minimum 5, max queries 1, max attempts 6, output freshness-checks. Recheck live configuration before any approved mutation; these are handover observations, not a promise settings never change.

Preserve the 650-product baseline at trials/53100508 and the Walmart collector/resources. Source/report changes in this package are **not deployed**. The browser image tag 7616ffd was tested once and failed; the original API image/mode were restored. No additional execution is authorized.

Keep secrets in the existing Azure secret references/identity arrangement or the owner's approved local secure credential store. Never put keys in configuration JSON, command arguments, GitHub, the client package or screenshots. Do not refresh credentials or change scopes just to follow this guide. Offline checks require no secrets. The public API credential does not grant partner catalog access.

## 6. Deployment, monitoring and scheduling gates

Before requesting deployment, identify the exact reviewed source/image, measured limits, expected output prefix, previous image/environment rollback values and cost ceiling. Build success alone does not authorize deployment. No Pay As You Go upgrade, new resources, roles, providers or production schedule may be enabled without approval.

After compatible source access is demonstrated, accept one complete representative category, then all configured roots, real interruption/recovery, independent fresh observations and product/PPM/offer evidence. Only then request production scheduling. The example cron is Monday/Thursday 06:00 UTC; a configured cron string is not an enabled Azure schedule.

Monitor authoritative execution status plus receipt/report availability, observation age, yield, coverage and quarantines. Investigate `operational_report_unavailable` or a failed/blocked/incomplete run. Missing telemetry is not success. This package adds local/report observability; it does not create a live alerting service. Actual monthly cost requires measured cloud/billing evidence; earlier planning ranges are not measured production expenditure.

## 7. Walkthrough script

1. Show the current limitations and identify the real historical 650 export separately from synthetic demos.
2. Run preflight from the extracted source; show its report and zero live records generated by the simulation.
3. Run the configuration check; demonstrate a copied wrong-ZIP configuration fails before any source call.
4. Generate/read the saved cloud failure report; point out one navigation action and unknown product/request counters, not fabricated zero observations.
5. Show controlled recovery results and explain what remains untested live.
6. Show current source/image references, package hashes, recovery rules and the manual/approval boundary.

This is an exact demonstration script, not a recorded video. Recording remains outstanding. The client receives source and instructions, with no hidden remote shutdown, paid service or weekly manual page-inspection dependency represented as solved automation.


## 8. Browser setup diagnostics (offline verified, not deployed)

Setup failure evidence now includes `navigation_diagnostics`: up to 32 ordered main-frame request/response/failure events, relative elapsed milliseconds, HTTP status where received, a whitelisted error code and numeric browser version. Listeners attach before the first navigation and detach when setup finishes or fails. Success retains a snapshot on the driver; this is not a continuous network log.

All paths, queries, fragments, user information and external destinations are redacted. No headers, cookies, payloads or rendered body text are stored by browser setup evidence. This does not change other existing collection evidence contracts. Events dropped at the cap are counted; an empty list is not proof no traffic occurred (for example, an unavailable frame cannot be attributed safely).

Default tests require no browser. To run optional offline Chromium integration checks, install the pinned browser extra and Chromium, set `MARIANOS_OFFLINE_BROWSER_TESTS=1`, then run the test suite. These tests intercept all requests before navigation; they never contact the retailer.

The earlier HTTP/2 failure remains unresolved. A future live test requires a concrete reviewed image, separate bounded approval and protected rollback; this source change does not authorize execution or scheduling.


## 9. Unavailable assortment retention

Temporal enrichment retains a genuine matched product when fresh, store-specific evidence reports pickup unavailable. Its 22-field identity record remains in products.json; current pickup prices, PPM and deal fields are blanked because availability does not validate those quotes. availability_audit.json preserves the dated observation, original API record and evidence hash. Availability alone is no longer a quarantine reason.

Stale observations, wrong stores, unresolved variant identities and mismatched URLs cannot authorize this change. Ordinary available-product price conflicts retain the existing separate quarantine behavior. This change does not discover products omitted by an upstream source; complete unavailable assortment coverage remains a live source acceptance requirement. Historical deliverables are unchanged; reprocessed samples must keep their original observation dates and be labelled separately.
