> **SUPERSEDED — added 1 November 2026.** This package describes the run made
> **before** the paging correction in commit `78f57dc`, and it is missing the
> 1,483 records that correction recovered. Its figure of 24,683 records is
> superseded by the 26,166 in `../2026-10-31-vernon-hills-package-rerun/`, which
> is the authoritative collection for this store and date. Nothing in this
> folder should be quoted. It is kept because the earlier run is part of the
> record, not because it is current.

# Requirement 7: keeping a failed run from replacing good data

As with requirement 6, the protection below belongs to the publication path. It was
**not applied to this dataset**, which was never published through it.

## The publication path: `marianos_collector/runner.py`

1. A per-store lock stops overlapping runs (`storage.locked`).
2. Pages are staged, then the checkpoint advances. A crash leaves at most an orphan staged page.
   A checkpoint is refused if it is over seven days old or was made under another configuration.
3. All validation in requirement 6 happens before any publication write. A failure raises,
   so nothing below it runs.
4. `reconcile` merges the prior release, so a product absent from this run carries forward
   with its original date. A prior release at another store is refused.
5. A release that would lose a published product fails with `PUBLISHED_IDENTITY_LOST`.
6. Data, report, retention and manifest are written under a new versioned prefix.
7. The `latest` pointer is written last, after confirming the lock is still held.

So a failed run leaves the `latest` pointer naming the previous release. Tests covering this
include `test_previous_good_pointer_unchanged_on_failed_rerun`.

## The path that made this data: `tools/kroger_full_sweep.py`

The sweep has no gate and no `latest` pointer, so it cannot replace anything, and equally it
cannot certify anything.

- Output goes to a folder named on the command line. If that folder holds a checkpoint, the
  run refuses to start unless `--resume` is given, and a checkpoint from older record rules
  cannot be resumed.
- The checkpoint is written after each term, and each file is written to a temporary name
  and then moved into place.
- `--previous-run` carries forward absent products through `reconcile`, and refuses another
  store's run. This run used none, so 24,683 records are current and none carried.
- **A run stopped by its budget or by an API error still writes its full output**, with the
  reason in `stopped_reason`. Nothing marks that folder unusable, so the reader has to check that
  field. In this run it is empty.

Promoting a sweep folder to a deliverable is a manual step. Nothing in the code validates it.
This package's builder does check a folder before packaging it, and refuses on a stated failure,
but it does not perform the requirement 6 gates.
