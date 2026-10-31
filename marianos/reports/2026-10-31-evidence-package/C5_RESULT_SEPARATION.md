# Commits and results, kept apart

## Commit order

    8a37532  24 Oct  deployed baseline; the image restored after the trial
       | 4 commits
    738eb03  25 Oct  later implementation
       | 8 commits
    7c49e25  28 Oct  source of the Azure trial

    74a55c5  31 Oct  reconciled release, on a separate line from 58ff5fb

Each commit in the chain is an ancestor of the next: `738eb03` is an ancestor of
`7c49e25`. So `738eb03` is later than the deployed baseline and earlier than the
trial source. It is not the deployed baseline and must not be presented as one.
The chain left the release's line at `58ff5fb` on 24 October, so none of the three
is an ancestor of the release.

## Five separate results

| Result | Status | Evidence |
|---|---|---|
| Offline tests | Passed | Measured 31 October: 190 passed and 5 skipped under pytest at `7c49e25`; 345 passed at `74a55c5` |
| Two fresh five-product cloud runs | Passed, West Loop | `RESUMED_PAGE_ORIGINAL.json` and `FRESH_PAGE_ORIGINAL.json` |
| Forced interruption and resume | Passed | Execution `muij8ay` then `9vca720`; the checkpoint hash is unchanged |
| Failed-run publication protection | **Not established in the cloud** | The trial lists it as unproven; this evidence holds no such test |
| Twice-weekly scheduled execution | **Not established** | The job is manual; no schedule was enabled |

None of these implies another. The cloud results are on a five-product sample at
`7c49e25` and say nothing about full deployment, the 34-product Batteries sample,
or the reconciled release.
