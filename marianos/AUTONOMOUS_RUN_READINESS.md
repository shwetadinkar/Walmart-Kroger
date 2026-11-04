# Readiness for an unattended run, and what one actually produces

4 November 2026. Written so that nothing about the first Azure execution is a
surprise.

## The one thing to know before deploying

**An unattended release carries `ppm`, `volume_deals_description` and
`digital_deals_description` empty, on every run, by design.**

Those three exist only on the rendered retailer page. The Kroger public
Products API carries no displayed rate at any tier, only
`regularPerUnitEstimate`, which is an estimate and must never be written into
`ppm`. The populated figures the client has seen, 727 and 146 and 48, came from
attended page reads merged in afterwards with `tools/merge_page_enrichment.py`.

A scheduled job cannot do that, and it must not fake it: the composition
layer's freshness window is 7 days and refuses an older page read rather than
relabelling an older observed price or offer as newly observed. So the choice
is an empty column or a false one, and the empty column is correct.

Until 4 November the columns arrived empty with **nothing saying why**, because
the job runs `--source sweep` and the `unavailable_crawl` explanation is
registered only on the composite path. `provenance_report()` now carries
`fields_this_source_cannot_supply` and
`page_only_fields_are_empty_unless` on the sweep path too, so the release
explains its own gap. An unexplained empty column reads as a collection
failure; this one is a property of the contract.

## What a run produces, observed rather than described

Rehearsed on 4 November through `tools/observe_schedule.py --keep-releases`:
the real `Collector`, the real `KrogerSweepSource`, the real schema, retention
reconciliation and storage, with only the Kroger HTTP client replayed.

| | |
|---|---|
| fields | 22, fixed order, **every value a string**, no nulls |
| `gupc`, `unit_price` | empty, as required |
| store columns | 100 percent populated |
| `ppm`, volume, digital deal wording | empty, with the reason in the report |
| `coverage_scope` | `subset_trial` |
| `source_coverage_attested` | `false` |
| `submission_ready` | `false` |

The last three are the gates doing their job. A term-filtered search cannot
attest complete category discovery, so the output stays in the trial namespace
and says so. **A release from an unattended run is not a submission.**

## The collector now stops itself before Azure kills it

**It did not.** This entrypoint passed no time budget, so the CLI default of
7200 seconds applied, and `deploy_jobs.sh` deployed `--replica-timeout 7200`.
The two were equal by coincidence, and the consequence is not a late finish: an
Azure replica timeout is a **SIGKILL**, which is not an exception, so
`refusal_recorded` never runs. An overrunning unattended run would have left
**no release and no refusal record at all** - precisely the trace the refusal
machinery exists to leave - defeated by a configuration coincidence rather than
by any code, and only on the runs where it matters most.

The budget is now derived from the replica timeout the job is actually deployed
with, minus 900 seconds of headroom for the collector to finish its term,
reconcile retention, publish and write its report. `deploy_jobs.sh` resolves
`REPLICA_TIMEOUT` once, deploys that figure and forwards the same figure into
the container, so the two cannot drift apart, and it refuses to deploy a
timeout that leaves no headroom. At the default that is a 6300 second sweep
inside a 7200 second replica.

## The Walmart job, now fixed and one thing corrected

**The Walmart run had no time budget at all.** Only Azure's
`--replica-timeout 14400` bounded it, and `walmart/azure/AZURE_DEPLOYMENT.md`
says plainly that "the jobs are not guaranteed to finish in four hours". A
replica timeout is a SIGKILL, so an overrunning run left no release and no
refusal record. Same defect as the Mariano's one in a different shape: there
the budget equalled the timeout, here it was absent.

`Collector` now takes `max_seconds` and checks it between categories. Exceeding
it **refuses the release and records the attempt** rather than publishing what
was collected: a partial Walmart release would read as complete, and this
collector already refuses a release whose coverage cannot be attested. The
check sits between categories rather than per page, because it has to leave
room for the category in hand plus publication, and a per-page stop would leave
the same partial release. The entrypoint derives the budget from the deployed
replica timeout minus 1200 seconds, the deploy script resolves `REPLICA_TIMEOUT`
once and forwards the same figure it deploys, and refuses a timeout with no
headroom. 13200 seconds inside 14400 at the default. `list` is not a run and
takes no budget.

**Simultaneous firing is the design, not an oversight.** An earlier version of
this file called the two jobs starting together a gap worth staggering. That
was wrong, and reading `walmart/azure/AZURE_DEPLOYMENT.md` corrected it: the
Walmart deployment **deliberately** runs two scheduled jobs, one per store, on
the same expression, and "a Blob lease prevents two overlapping executions of
the same store". The real hazard already has a real guard. Staggering would
also change a time stated to the client in that document, Monday and Thursday
06:00 UTC, for no correctness gain, so the schedule is unchanged.

## A failed run retries itself, then emails

Eight retries at fifteen minute intervals, then a failure notice, with the next
scheduled run untouched. `azure/retry_supervisor.py` does it, on both sides.

**The arithmetic has to be seen before deploying, because it changed the
timeouts.** Eight retries at 900 seconds is two hours of waiting *alone*, and
the whole plan has to fit inside one replica timeout, because a replica timeout
is a SIGKILL and would cut the plan off part-way. So:

| | Mariano's | Walmart |
|---|---:|---:|
| retries, interval | 8 at 900s | 8 at 900s |
| waiting alone | 7200s | 7200s |
| **minimum timeout for all 9 attempts** | **10920s** | **11220s** |
| was deployed with | 7200s | 14400s |
| **now defaults to** | **14400s** | **21600s** |
| first attempt's budget at that default | 13500s | 20400s |
| gap to the next firing | 259200s | 259200s |

Every figure above is computed by `retry_supervisor.RetryPlan`, not worked out
by hand. Nine attempts each getting a *full-length* run would need 128820s and
190920s respectively, which is why the plan degrades the number of attempts
rather than reserving time up front.

The deployment **refuses** a timeout that cannot reach every configured
attempt, and quotes the figure to set. It is refused rather than quietly
shortened: a plan that silently stops at attempt three is not the plan that was
configured. Lowering `RETRY_ATTEMPTS` or `RETRY_INTERVAL_SECONDS` is the other
way to make it fit.

**No Azure maximum is claimed here.** Microsoft's jobs reference lists
`replicaTimeout` as a required int with no stated maximum, minimum or default.
The last row above is therefore reported, not enforced; whether Azure accepts
it is found out at deploy time.

**The first attempt gets the whole window, retries get what it leaves.** So a
successful run is never starved to pay for retries it does not need, and a run
that used its whole budget and failed is not retried, because there is nothing
left to retry it with. That is the one failure where retrying is waste.

**What is not retried:** a usage error, which will be wrong the same way eight
more times, and a bot challenge, because the retailer said no and retrying a
refusal on a schedule is working around it. Everything else is, including an
expired credential - the likeliest unattended failure, and one that costs no
retailer requests to retry.

**The next run is unaffected, and that is checked rather than assumed.** Azure's
cron fires independently of how long an execution takes, so an overrunning
execution does not delay the next firing - it runs beside it and meets the Blob
lease, which refuses it. The deployment therefore also refuses a replica timeout
that is not shorter than the gap between firings, computed from the deployed
expression. At 72 hours there is room.

**Email is optional and needs no credential in the image.** A final failure
always prints `MARIANOS_RUN_FAILED_AFTER_RETRIES`, which an Azure Monitor log
alert matches with nothing deployed alongside it. For email instead, set
`ALERT_EMAIL_TO` and `SMTP_HOST`, plus `SMTP_USERNAME` and `SMTP_PASSWORD` if
the relay needs them; the password reaches the job as an Azure secret and is in
no file here. A `--dry-run` says which route is configured.

```bash
# What the configured plan needs, before deploying anything.
REPLICA_TIMEOUT=14400 bash azure/deploy_jobs.sh --dry-run

# To be emailed instead of alerting on the log line:
ALERT_EMAIL_TO=you@example.com SMTP_HOST=smtp.example.com \
  bash azure/deploy_jobs.sh --dry-run
```

## The image refuses to build without a verified store

`config/stores_live.json` is gitignored by design, because it holds the
location id verified against Kroger's Locations API, and `azure/README.md` says
to copy it from `stores_live.template.json` before building. **Nothing checked
that it had been done.** A build that skipped the step produced a perfectly
good image whose first act, at 06:00 UTC with nobody watching, was to fail on a
missing file.

The build now refuses: on the file being absent, on it being invalid JSON, on
it being empty, and on it still containing `DEMO`, `REPLACE`, `UNRESOLVED` or
`EXAMPLE`. The placeholder case matters as much as the missing one, because a
copied template would otherwise deploy and this repository has published one
store's data under another store's name once already. A test asserts the check
sits before `ENTRYPOINT`, since a check after it would still build a broken
image, and that the Dockerfile and the entrypoint name the same path.

## Before the first Azure execution

```bash
# 1. Offline self-test. No retailer and no Azure connection.
python3 tools/preflight.py

# 2. Credentials and store resolution, against the real Kroger API.
#    This is the check that matters most: keys are rotated and a
#    twice-weekly job fails at 06:00 UTC with nobody watching.
python3 tools/live_access_preflight.py --help

# 3. The schedule, as two separate claims.
python3 tools/observe_schedule.py --out reports/schedule-check --keep-releases

# 4. Inspect what the rehearsal published, rather than trusting it.
find reports/schedule-check/releases -name report.json | head -1 | xargs cat
```

Environment the sweep route requires, and refuses to start without:
`KROGER_CLIENT_ID`, `KROGER_CLIENT_SECRET`, `KROGER_LOCATION_ID`,
`MARIANOS_EXPECT_ZIPCODE`, `MARIANOS_EXPECT_STREET`,
`AZURE_STORAGE_CONNECTION_STRING`. The entrypoint rejects a `KROGER_LOCATION_ID`
beginning `DEMO`, `REPLACE` or `UNRESOLVED`, and requires the ZIP and street,
because the assigned store id differs from West Loop's by two characters and
one sweep already shipped 18,351 records with blank store columns.

`CATALOG_V2_UNIT_IS_PPM` is **ignored** by the collector and no longer
forwarded by the deploy script. It used to promote a field of unknown meaning
into `ppm` on an unattended job.

## What to check after the first execution

1. `report.json`: `coverage_scope`, `source_coverage_attested`,
   `submission_ready`, and that `fields_this_source_cannot_supply` is present.
2. The store columns in `data.json`, against the assigned store. A gate refuses
   a store whose `store_id`, `zipcode`, `store_name` or `store_location` is
   blank, but check the values are the right store's.
3. `provenance.terms_completed` against `terms_configured`, and
   `terms_abandoned_after_retries`. An abandoned term collected nothing across
   three attempts and is named rather than counted as complete.
4. `failures/<namespace>/<store>/` — empty on a clean run. A refused attempt
   leaves a record there carrying the reason verbatim, including a refusal that
   happens before the runner exists, such as an expired credential.
5. The job log, for `retry_supervisor attempt N of 9` lines and a closing
   `retry_supervisor summary:`. A clean run shows attempt 1 and nothing else.
   On a failure the summary gives each attempt's exit code, the budget it was
   given and how long it took, and `stopped_early` says so when the plan ended
   before its ninth attempt and why. **One failed run writes one refusal record
   per attempt and one notice**, not one notice per attempt.

## What an Azure execution will establish, and what it will not

**Will establish:** that the job runs in the client's own environment, against
his storage account, with his secrets and his network; that the cron fires
there; that the gates behave on real infrastructure.

**Will not establish:**

- **Any of the three page-only columns.** See the top of this file.
- **Category coverage.** One search term reaches at most 300 products because
  `filter.start` is refused past 250, and 114 configured terms hit that
  ceiling. Splitting them into 421 narrower terms raised the number hitting it
  to 114 from 68, so the ceiling is structural.
- **Resume across executions**, unless `MARIANOS_SWEEP_WORK_DIR` points at a
  mounted volume. It defaults to container-local `/tmp`, which is discarded
  with the execution, so a stopped run resumes from nothing. The *release*
  checkpoint is in Blob storage and does survive. No observed run has
  exercised a mounted volume.
- **That the public tier permits this.** That is the acceptable-use question,
  which is the client's with his own counsel. See
  `ACCEPTABLE_USE_POSITION.md` and
  `ACQUISITION_AND_SCHEDULED_USE_PROPOSAL.md`. Deploying a schedule is the
  act that question is about, so it is worth settling before rather than
  after.
