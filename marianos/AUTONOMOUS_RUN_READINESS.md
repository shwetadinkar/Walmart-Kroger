# Readiness for an unattended run, and what one actually produces

4 November 2026. Written so that nothing about the first Azure execution is a
surprise.

## The one thing to know before deploying

**An unattended release carries `ppm`, `volume_deals_description` and
`digital_deals_description` empty, on every run, by design.**

Those three exist only on the rendered retailer page. The Kroger public
Products API carries no displayed rate at any tier, only
`regularPerUnitEstimate`, which is an estimate and must never be written into
`ppm`. The populated figures the client has seen, 727 and 146 and 49, came from
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

## Two things about the Walmart job, not fixed here

**Both jobs are scheduled for the same instant.** `walmart/azure/deploy_jobs.sh`
also deploys `--trigger-type Schedule` with `0 6 * * 1,4`, so Mariano's and
Walmart start together twice a week. Staggering them is a one-line change and it
is deliberately **not** made here: Monday and Thursday at 06:00 UTC is the
schedule the client has been told, and changing what he has been told is his
call rather than ours.

**The Walmart CLI has no time budget to tune.** It takes no `--max-seconds`, so
only the 14400 second replica timeout bounds it, and that bound is the SIGKILL
described above. With 615 products from provider snapshots, four hours is large
headroom and the case is unlikely; but unlikely is not the same as recorded, so
it is recorded. Giving that CLI a budget is the same fix as above and has not
been done.

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
