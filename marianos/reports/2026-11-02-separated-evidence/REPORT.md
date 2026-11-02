# Five claims, kept apart, 2 November 2026

The client asked that offline checks, fresh collection, interruption and
recovery, failed-run publication protection, and twice-weekly Azure operation
be kept as **separate** evidence. They had not been. The material existed but
was spread across `R6`, `R7`, `R8`, several READMEs and the evidence package,
where a strong claim could carry a weak one by association.

So each is stated on its own below, with what it rests on, what it covers, and
what it does not. Read them separately. None of them implies another.

---

## 1. Offline checks

**Claim.** The code behaves as described without touching a network.

**Evidence.** `tools/preflight.py` runs clean with no credentials. The test
suites are **549 for Mariano's and 251 for Walmart**, direct and pytest counts
agreeing. Every fix made for the client's 2 November review carries a mutation
test: the fix was reverted, the suite was confirmed red, and the fix restored.

**Covers.** Logic, schema, gates, retention rules, parsing, namespace layout,
binding rules.

**Does not establish.** Anything about live retailer data, this store, or any
figure in the delivered dataset. A green suite has twice in this project
reported sound work that was not, which is why mutation testing is required
here rather than optional.

---

## 2. Fresh collection

**Claim.** A real collection ran against the assigned store and produced the
delivered records.

**Evidence.** 31 October 2026, 20:56:16 to 21:23:32 UTC, 1,643.1 seconds, 998
requests, 301 terms. 26,166 products, 26,166 distinct UPCs, no duplicates, 0
page failures. The store is resolved against Kroger's Locations API and the
response is committed at
`reports/2026-11-01-vernon-hills-merge/data/store_verification.json`:
`locationId 53100502`, 1720 N Milwaukee Ave, Vernon Hills, IL 60061.

**Covers.** That the collection happened, at that store, at that time, at that
cost in requests.

**Does not establish.** Category completeness: 69 of 301 terms hit the
300-result ceiling. Displayed price per measure or deal wording: the public
tier carries neither, and the 592 rates came from a separate attended page
read. That it ran on Azure: it did not. That it ran through the collector: it
did not, which is the gap `PRODUCTION_ROUTE.md` describes.

---

## 3. Interruption and recovery

This is the claim most at risk of being over-read, so it is stated narrowly.

**Claim.** A checkpoint survives a deliberate failure and a later execution
resumes from it rather than re-fetching.

**Evidence, part one: an observed Azure trial.** Three executions of
`marianos-westloop-api-pilot` on 28 October, recorded in
`reports/2026-10-31-evidence-package/RESULTS.md`:

| Execution | Stage | Result | HTTP attempts | New queries |
|---|---|---|---|---:|
| `muij8ay` | interrupt | failed, deliberately | 3 | not recorded |
| `9vca720` | resume | succeeded | 2 | **0** |
| `1pxbwhh` | fresh | succeeded | 3 | 1 |

The checkpoint survived the deliberate failure with its SHA-256 unchanged, and
the resume made no new queries.

**Evidence, part two: tests.** `test_cloud_recovery.py` 9 tests and
`test_execution_state.py` 10 cover the runner's recovery. The sweep that
actually produced the delivered data has its own checkpointing, covered inside
`test_kroger_sweep.py` (85 tests), including that a current checkpoint resumes
without re-fetching and that a checkpoint written under older rules is refused
rather than mixed with new records.

**Does not establish.** The Azure trial was at **West Loop, not Vernon Hills**,
and was a five-product selection on the single term `milk`. It is not evidence
of recovery at 26,166-record scale, at the assigned store, or for the full
301-term sweep. The sweep's resume is covered by tests, not by an observed
interrupted production run. Those are two different standards of evidence and
this report does not merge them.

---

## 4. Failed-run publication protection

**Claim.** A failed or degraded run cannot replace a good published release.

**Evidence.** In the runner: a minimum-product floor, a previous-yield ratio
check, canary products, a `PUBLISHED_IDENTITY_LOST` check, store-context
validation, and the latest pointer committed last so a partial write never
becomes the current release. Trials and full releases never share a namespace,
and as of 2 November a source that cannot attest coverage cannot produce a full
release at all. Covered by `test_runner_retention.py` (8 tests) and parts of
`test_vernon_hills_package.py`, with the namespace separation covered by
`test_trial_namespace.py` (6) and the attestation gate by
`test_coverage_attestation_gate.py` (9).

**Does not establish.** That this has been exercised by a real failed
production run at the assigned store. The protection is implemented and tested;
it has not been observed saving a real release.

---

## 5. Twice-weekly Azure operation

**Claim, and it is the weakest of the five.** The collector is intended to run
unattended on Azure, twice weekly, per store.

**Evidence.** `azure/deploy_jobs.sh` creates one Azure Container Apps scheduled
job per verified store, with the schedule defaulting to `0 6 * * 1,4`, which is
Mondays and Thursdays at 06:00 UTC. `azure/container_entrypoint.py` is the
entrypoint. Azure execution itself is not hypothetical: the 28 October trial
above ran three executions on Azure Container Apps with output in private Blob
storage.

**Does not establish**, and this is the important part:

- **Twice-weekly scheduled operation has never been observed.** The 28 October
  executions were a manually driven pilot, not the cron schedule running by
  itself across a week.
- **Nothing has run in the client's Azure environment.** The brief asks for
  that, and it needs his environment.
- **The delivered 26,166 did not come from Azure at all.** They came from a
  local run of a tool outside the collector.

So: deployment template written and a pilot executed, against a requirement for
observed twice-weekly operation in the client's environment. Those are far
apart and the gap is not narrowed by the other four claims being in good shape.

---

## Summary, kept deliberately blunt

| Claim | Strength |
|---|---|
| 1. Offline checks | Strong. Tested and mutation-tested |
| 2. Fresh collection | Strong for what it is. Real, store-verified, bounded coverage |
| 3. Interruption and recovery | Mixed. Observed on Azure, but at another store on five products; tested at scale |
| 4. Failed-run protection | Implemented and tested. Never observed saving a real release |
| 5. Twice-weekly Azure | Weakest. Template plus a pilot. Never observed as a schedule, never in the client's environment |
