# Developer handover, 4 November 2026

For picking this repository up in Claude Code. `CLAUDE.md` is the governing
file and is loaded automatically; this one is the map. Where the two disagree,
`CLAUDE.md` wins.

This is **not** `marianos/HANDOVER.md`, which is a client-facing acceptance
guide written at the prototype stage and partly superseded.

## Before anything else

**This repository is public** (`github.com/shwetadinkar/Walmart-Kroger`,
`private: false`). No credential is in it and `marianos/.env.kroger` has never
been committed, checked on 4 November. But provider ticket numbers, a Bright
Data snapshot id, the assigned store id and the client's quoted words are all
in tracked files. Nothing new of that kind should be added, and the client
correspondence log is deliberately kept out of the repository for this reason.

Read in this order:

1. `CLAUDE.md` — the rules, and the defect history behind each one
2. `REVIEW_ACTIONS_2026-10-31.md` — the client's 31 October review, PART 0 first
3. This file
4. The correspondence log (local only, see the last section)

## State

| | |
|---|---|
| working branch | `marianos-api-sweep-2026-10-31` |
| HEAD | `763d14b`, pushed, working tree clean |
| authoritative Mariano's release commit | `74a55c5e6fb2d938df1d06ff6717561420130cd9` |
| frozen, never commit to | `walmart-client-corrections-2026-10-31` (`86245e1`) |
| test counts | Walmart 331, Mariano's 1057 — direct and pytest must agree |
| delivery date | 5 November 2026, 00:00 GMT |

Commits are authored `Shweta Dinkar
<310295881+shwetadinkar@users.noreply.github.com>` with **no** co-author,
tooling or session trailers. History is not rewritten.

```bash
cd marianos && python3 -m pytest tests -q      # expect 1057
cd walmart  && python3 -m pytest tests -q      # expect 331
```

## Mariano's

### Delivered

Release `20261103T175940Z_426c12e8`, **28,549 records** across the 23 populated
roots, the first produced through the runner at the assigned store (Vernon
Hills `53100502`, 1720 N Milwaukee Ave, IL 60061, PICKUP). Store columns 100
percent, `coverage_scope: subset_trial`, `source_coverage_attested: false`,
`submission_ready: false`.

Enrichment merged 4 November, one pass over both page reads: **`ppm` 727,
`volume_deals_description` 146, `digital_deals_description` 48**, all
attributed to `crawl`, none to the API, zero conflicts, zero cross-read
disagreements.

### Paths

| path | what it is | status |
|---|---|---|
| `marianos_collector/runner.py` | `Collector`, the publication gate, `record_refused_attempt` | done |
| `marianos_collector/schema.py` | 22 fields, `make_record`, `check_deal_columns` | done |
| `marianos_collector/sweep_core.py` | the sweep as importable code, `STATE_VERSION 6`, `MAX_TERM_ATTEMPTS 3` | done |
| `marianos_collector/kroger_sweep_source.py` | the Source; out-of-scope retention, coverage reporting | done |
| `marianos_collector/composition.py` | `CompositeSource`, per-field provenance, 7-day freshness | done |
| `marianos_collector/api_trial.py` | `normalize`, `observe`, `to_raw_product` — the stricter implementations | done |
| `marianos_collector/retention.py` | retention reconciliation, `pickup_context` | done |
| `marianos_collector/cron.py` | cron maths, `shortest_gap_seconds` | **new 4 Nov** |
| `marianos_collector/oxylabs.py` | Web API client with `REFUSED_HOSTS` | done, route refused |
| `azure/retry_supervisor.py` | 8 retries at 900s, then notify | **new 4 Nov** |
| `azure/container_entrypoint.py` | per-attempt budget, no `os.execv` | done |
| `azure/deploy_jobs.sh` | refuses a retry plan that cannot fit | done |
| `Dockerfile` | refuses to build without a verified `stores_live.json` | done |
| `tools/kroger_full_sweep.py` | thin wrapper over `sweep_core` | done |
| `tools/merge_page_enrichment.py` | the one-pass multi-read merge | done |
| `tools/parse_page_harvest.py` | `classify_card_line`, the offer grammar | done |
| `tools/out_of_scope_reconciliation.py` | the 166 unmapped identities | done; **artefact not in repo** |
| `tools/delivery_manifest.py` | revision/hash manifest + change-to-test map | done, not yet run for delivery |
| `tools/build_submission.py` | assembles the submission from a release | done |
| `tools/observe_schedule.py` | the schedule, as two separate claims | done |
| `tools/resolve_sitemap_gap.py` | carriage, as a range never a number | done |
| `reports/2026-11-01-vernon-hills-page-harvest/` | first page read, 592 rated | kept |
| `reports/2026-11-04-vernon-hills-page-harvest/` | second read + merge proof | kept |
| `ACCEPTABLE_USE_POSITION.md` | the question that is the client's, not ours | awaiting client |
| `ACQUISITION_AND_SCHEDULED_USE_PROPOSAL.md` | written for owner review | awaiting client |
| `AUTONOMOUS_RUN_READINESS.md` | what an unattended run produces, and the retry arithmetic | done |
| `out/sweep-2026-10-31/` | first sweep, blank store columns | **must not be published** |

## Walmart

### Delivered

615-record trial submission for store 100, ZIP 72712, at
`walmart/submission/2026-10-24/`. All five client corrections done.
`walmart/RELEASE.md` carries the ancestry table and the eight feature checks.

**Two artefacts the repository does not hold, both by design.** The submission
is rebuildable from snapshots via `tools/rebuild_evidence.py`, whose `--output`
is documented as a "PRIVATE output folder, never inside git", and that is where
`MANIFEST_SHA256.json` and `PROVENANCE_615.json` are written. So the
verification manifest exists where the rebuild ran, not here. The only
`MANIFEST_SHA256.json` in the repository is the Mariano's one at
`marianos/reports/2026-10-31-evidence-package/`. Do not write that the Walmart
submission is "verifiable against `MANIFEST_SHA256.json`" without saying where
that file is: a claim needs its artefact to exist wherever the claim is read,
which is a defect this engagement has already shipped once.

### Paths

| path | what it is | status |
|---|---|---|
| `walmart_collector/runner.py` | `Collector` with `max_seconds`, refusal records | done |
| `walmart_collector/composition.py` | generic attribute forwarding (ported from here to Mariano's) | done |
| `walmart_collector/cron.py` | cron maths | **new 4 Nov** |
| `azure/retry_supervisor.py` | checked port of the Mariano's one | **new 4 Nov** |
| `submission/2026-10-24/` | the file the client reviewed | **untouched, keep** |
| `submission/2026-10-31-provider-fields/` | composed-PPM export | **client rejected 4 Nov** |
| `evidence/2026-11-04-attended-browser-store-100-attempt.md` | why directly captured PPM is not obtainable | done |

## What remains

### 1. Blocked on you — the delivery package

The release and the raw responses live on your machine, not here. Nothing below
can run until the release is where the tools can read it.

```bash
# After the release is in place:
python3 tools/merge_page_enrichment.py \
  --api <release data.json> \
  --page reports/2026-11-01-vernon-hills-page-harvest/data/parsed_full.json \
  --observed-at 2026-11-01T22:00:00+00:00 \
  --page reports/2026-11-04-vernon-hills-page-harvest/data/parsed_full.json \
  --observed-at 2026-11-03T<...>+00:00 \
  --store-id 53100502 --zipcode 60061 \
  --store-name "Marianos - Marianos Vernon Hills" \
  --store-location "1720 N Milwaukee Ave, Vernon Hills, IL 60061" \
  --out out/<new-dir>
```

`--page` and `--observed-at` are repeatable and **must be passed as pairs in
one invocation**. Never chain two merges: doing so labelled 526 rates and 53
coupon descriptions as having come from the Kroger public API, which carries
neither field at any tier. Every count stayed correct; only the provenance was
false.

Then, in order: `tools/out_of_scope_reconciliation.py` (needs `--work-dir` with
the persisted raw responses), `tools/build_submission.py`,
`tools/delivery_manifest.py --since <revision the client last reviewed>`,
checksum verification, zip.

Expected figures to check against: `ppm` 727, volume 146, digital 48, and
28,549 + 46,073 duplicates + 166 out of scope = 74,788 seen over 1,833 indexed
responses.

### 2. The drafted client message is not sent

It states digital deals at 48 and must not go out until the package matches.
Held locally, not in this repository.

### 3. Open with third parties

- **Bright Data #754403** — Mariano's. Reran at the assigned ZIP 60061 on
  4 November and it failed the same way: `"No Kroger pickup store found for zip
  code 60061"`, `error_code: bad_input`, so provider store resolution and not a
  bot challenge. Escalated to their R&D, no answer. Two things worth asking
  that have not been: whether the dataset accepts a `store_id` such as
  `53100502` instead of a ZIP, and whether its Kroger store lookup covers the
  Mariano's banner at all.
- **Bright Data #754118** — Walmart. Whether the store switch applied to the
  22 and 23 October snapshots is unknown and asked. Until answered the 615 are
  the provider's output for a *requested* store 100 context, not a verified
  store 100 assortment.
- **The client's acceptable-use decision.** His 4 November instruction stands:
  no partner request, registration, agreement or production schedule is
  authorized, and the partner request stays unsubmitted. He also asked for the
  exact applicable policy text and link. **That text is already drafted**, in
  the 30 October correspondence, quoting Kroger's prohibition on
  "systematically scraping or gathering response data to create a database" and
  on comparing prices across retailers. Re-read the live policy page before
  sending it: a claim about an outside party's documentation is checked by
  reading that documentation every time it is relied on, and this engagement
  has twice had a position rest on an unchecked claim about a vendor.

### 4. Not done, deliberately

- An argparse refusal leaves no refusal record. `p.error` raises `SystemExit`,
  and a wrong flag should fail the first time a job is deployed rather than
  silently months later.
- **No resume across Azure executions** unless `MARIANOS_SWEEP_WORK_DIR` points
  at a mounted volume. It defaults to container-local `/tmp`, discarded with
  the execution. The release checkpoint is in Blob storage and does survive. No
  observed run has exercised a mounted volume.
- The out-of-scope artefact is not in this repository. The tool ran on your
  machine where the raw responses are, and its output ships in the client
  package.

### 5. Available, not required

About **80 extra page reads** would put a rate in every one of the 28 roots (9
roots short of 10 rated products each). Four of the six roots at zero are the
ones the API cannot reach at all, and page reading closes the empty-root gap
and the rate gap in one pass. Scope for anything expensive is **500 products
across the categories, not 28,549** — price any proposal against 80 to 200
products.

### 6. Never established by anything here

No Azure execution has run in the client's environment. `observe_schedule.py`
separates two claims — that the deployed expression fires when it should
(computed) and that a scheduler left alone repeats the job (observed in real
time) — and **neither establishes Azure**: nothing ran there, no Azure cron
fired, and the data is replayed.

## Client correspondence

Not in this repository, because it is public. The log and the eight drafted
messages were delivered to you as files on 4 November; keep them somewhere
private and alongside this repo. The log covers 24 October to 4 November: what
was sent, what the client instructed, and where each resulting artefact lives.

The client's 4 November review exists in no file in this repository. It is
transcribed in that log, and its five instructions are the live constraints on
the delivery package above.
