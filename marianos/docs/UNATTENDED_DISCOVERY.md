# Configured unattended discovery stage

This stage connects client configuration to the existing rendered category driver and coverage ledger. It is not the complete product/variant/promotion application, and it never publishes a product latest pointer.

## Configuration and execution

Install the existing package with its optional browser extra and install Chromium using the official Playwright tooling. The local development host already had both available. The current Azure Dockerfile has not been changed to include a browser, and no browser-enabled Azure image has been deployed.

```text
python -m pip install ".[browser]"
python -m playwright install chromium
python -m marianos_collector.discovery_job --config config/discovery.westloop.example.json --output ./discovery-output
```

The example is intentionally bounded: one configured root, three total navigation/load-more actions, 24 total browser actions and a 90-second action-start deadline. It is a smoke-test configuration and cannot prove all nine Batteries child branches. `discovery.all-roots.example.json` contains the 28 configured roots, but has not been executed or accepted; inspect its larger limits before any future authorized run.

Configure the exact store ID, ZIP, retailer display name and street; roots may be a selected subset or all 28. Configure category/page/action/time ceilings, an isolated `discovery...` output prefix and a disabled proposed UTC schedule. Unknown fields, credentials in configuration, unsafe prefixes, malformed identities/limits and enabled schedules are rejected. There is no 500-product minimum in this discovery-only stage; a selected small category must be judged against its actual scope.

The browser uses a new unsigned context with ordinary controls. It selects Pickup, enters the configured ZIP, chooses the exact store-name/street/ZIP radio and verifies the rendered store context and listing grid where available. It does not copy the user's profile, attach to a signed-in browser, use stealth/proxies or solve access challenges. The actual store-setup sequence remains unverified live because initial navigation failed.

## Resume, freshness and bounds

Local runs get a new execution ID by default. To resume a known execution, pass its original `--run-id` with identical configuration and the same output directory. Changing store, roots or limits rejects that checkpoint. Azure backend mode uses the existing execution-context identity by default, stable for replicas/retries and different for separate executions. Azure mode requires the existing storage extras and authentication configuration; it has not been live-tested for this new stage. No deployment or role change is implied.

Before external actions, the application persists budget use. Bootstrap, navigation, child probes/returns and load-more operations consume the total page-action budget, including failed attempts. Completed listing observations are reported separately; neither count is an HTTP request count because a browser can issue many asset requests. The wall budget is checked before actions, and an in-flight browser operation is also subject to its browser timeout; it is not an operating-system hard process kill.

An interrupted completed node is not replayed on resume; a partially completed node may need to be visited again within the remaining persisted budget. Completed/incomplete terminal receipts are returned on same-execution retry without launching a new browser. An access block is durable and cannot be resumed into more requests. A separate execution intentionally creates fresh state.

Output paths under the isolated prefix include configuration.json, budget.json, receipt.json, checkpoint.json, coverage.json when traversal returns, immutable hashed listing/discovery evidence, and failure-source.json where capture is available. Receipts omit raw exception strings, credentials and headers. Access failures and incomplete coverage return a nonzero exit status. Accepted product exports and protected baseline pointers are untouched.

## Actual live attempt — 25 October 2026

One normal isolated Chromium discovery execution failed during its first navigation, before selecting a store or traversing a category. It consumed one browser action under the implementation at that time, saved an error-page URL and empty body, and published no products. A single additional ordinary navigation diagnostic also failed before an HTTP response. Its diagnostic parser retained only `net::ERR_HTTP`; the exact longer subtype was not captured and is not inferred. No CAPTCHA, proxy, user-agent spoofing, certificate exception or protocol-disabling retry was attempted.

The existing in-app session can display retailer pages; that does not establish the independent collector's source compatibility. The immediate technical blocker is normal isolated browser navigation on this host, not a product parser result. Full store bootstrap, representative nested/paginated traversal and forced-stop/resume live acceptance remain unproved. Private receipts/diagnostics are delivered separately, not published to GitHub.

## Acceptance boundary and next work

Offline tests cover strict client configuration, safe output isolation, changed-config rejection, same-run resume, fresh separate state, persisted action/page budgets, challenge stops and failure evidence. The reviewed regression suite and preflight passed locally; synthetic tests are not retailer acceptance.

The next source gate is successful ordinary unattended navigation and exact store selection in an approved environment. Then demonstrate one representative nested/paginated category, all variant families and matched product/PPM/offer extraction, deliberate live interruption/resume and a fresh separate execution. Only after that expand all 28 roots. The production product pipeline, automatic coupon/variant completeness, browser-enabled Azure packaging, production monitoring and approved scheduled occurrences remain required. No new image deployment, scheduling or paid source is authorized by this document. submission_ready=false.
