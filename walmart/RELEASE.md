# The authoritative release

Prepared by Shweta, 31 October 2026.

Your review of 31 October asked for one authoritative release, because `main`
still resolved to `ad67fd3` and the regeneration instructions pointed at an
older branch. A reviewer following them would have used the defective importer
and the defective verifier. This file is the answer to that, and the
regeneration instructions now point here.

## Use this

**Branch:** `walmart-client-corrections-2026-10-31`

Nothing else in this repository is current. Every other Walmart branch is an
ancestor of this one, so there is no second place to look and nothing is
stranded:

| Branch | Carried here |
|---|---|
| `main` | yes, entirely |
| `walmart-timestamp-precision-and-verifier` | yes, entirely |
| `walmart-source-qualification-probe` | yes, entirely |
| `walmart-probe-display-arms` | yes, entirely |
| `walmart-evidence-regeneration` | content present; merged into `main` as PR #4 |
| `walmart-import-history-regression-fix` | content present; merged into `main` |

The last two were squash merged, so their commit identifiers are not ancestors
even though their code is here. Rather than ask you to take that on trust, the
features are checkable directly:

```bash
test -f walmart/tools/rebuild_evidence.py                              # evidence regeneration
grep -q _freshness walmart/walmart_collector/brightdata_import.py      # import history fix
grep -q _conflicting_fields walmart/walmart_collector/brightdata_import.py
grep -q _instant walmart/walmart_collector/brightdata_import.py        # timestamp precision fix
grep -q redacted_sha256 walmart/tools/verify_snapshot_manifest.py      # verifier fix
test -f walmart/tools/egress_region_probe.py                           # egress probe
test -f walmart/tools/opd_bounded_probe.py                             # bounded OPD probe
```

All seven should succeed. If any fails you are not on the release.

## What changed since the branch you reviewed

You reviewed `c37dd03` on `walmart-timestamp-precision-and-verifier`. That
commit is an ancestor of this release, and the five corrections sit on top of
it:

1. Unavailable and unpriced products are retained rather than dropped. Catalog
   offers with no store price row are recorded as unresolved rather than
   published with an unevidenced store context.
2. A source that cannot attest coverage is refused a full publication in the
   Collector itself, not only in the CLI.
3. Approximate-weight wording is excluded from titles as well as the weight
   field, on both retailers.
4. Malformed manifest entries fail the verifier instead of being filtered out,
   and declared is reported against checked.
5. `tools/opd_bounded_probe.py` is the bounded first test, with one cumulative
   budget and no retries.

Tests: 109 on Walmart, 37 on Mariano's.

## Regenerating the ledger

Identical to the earlier instructions except for the branch. Verify the
snapshots first; the verifier now refuses a manifest it cannot fully check
rather than reporting a clean pass over part of one.

```bash
git checkout walmart-client-corrections-2026-10-31
cd walmart

python tools/verify_snapshot_manifest.py \
  --snapshots /path/to/package/snapshots \
  --manifest  /path/to/package/MANIFEST_SHA256.json

python tools/rebuild_evidence.py \
  --snapshots /path/to/package/snapshots \
  --store-id 100 --zipcode 72712 \
  --submission submission/2026-10-24/Walmart_Store100_615_Trial_22Field.json \
  --output /path/to/a/private/output/folder
```

Expected, unchanged from the package you verified:

| Check | Expected |
|---|---|
| Submitted identities reproduced | 615 of 615, none missing |
| Submitted set, pickup available | 471 |
| Submitted set, pickup unavailable | 144 |
| Full ledger identities | 654 |
| Products with a confirmed pickup price | 0 |

The last row is unchanged and still correct. See the source analysis for why
the provider's store-aware feed returns an online price rather than a store
pickup price.

## One caveat about rebuilding with the corrected importer

The retention correction changes which products the OPD path keeps. It does not
change the delivered 615 or the 654-row ledger, because those came from the
provider snapshots and not from OPD, and the rebuild above reproduces them
exactly. If that ever stops being true, treat it as a defect and tell me.
