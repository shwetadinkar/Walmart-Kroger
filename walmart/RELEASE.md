# The authoritative release

Prepared by Shweta, 31 October 2026.

Your review asked for one authoritative release, because `main` still resolved
to `ad67fd3` and the regeneration instructions named an older branch. A
reviewer following them would have used the defective importer and the
defective verifier. This file is the answer, and the regeneration instructions
now point here.

## Use this

**Branch:** `walmart-client-corrections-2026-10-31`

Every Walmart branch in the repository is an ancestor of this one:

| Branch | Ancestor of this release |
|---|---|
| `main` | yes |
| `walmart-evidence-regeneration` | yes |
| `walmart-import-history-regression-fix` | yes |
| `walmart-timestamp-precision-and-verifier` | yes |
| `walmart-source-qualification-probe` | yes |
| `walmart-probe-display-arms` | yes |
| `marianos-catalog-v2-adapter` | yes (it also carried Walmart files) |

Check it rather than taking my word:

```bash
for b in main walmart-evidence-regeneration walmart-import-history-regression-fix \
         walmart-timestamp-precision-and-verifier walmart-source-qualification-probe \
         walmart-probe-display-arms marianos-catalog-v2-adapter; do
  git merge-base --is-ancestor "origin/$b" HEAD && echo "ancestor: $b" || echo "NOT ancestor: $b"
done
```

A note on an earlier version of this file, because it was wrong and you may
have read it. It claimed `walmart-evidence-regeneration` and
`walmart-import-history-regression-fix` were squash merged and therefore not
ancestors. They are ancestors. The claim came from running the check in a
shallow clone, where the grafted history made unrelated-looking results. The
table above was produced with full history.

Two branches are **not** ancestors, and both are Mariano's work rather than
Walmart:

| Branch | Why it is excluded |
|---|---|
| `marianos-fresh-runs-category-evidence` | 17 commits of Mariano's runbooks, retention policy and Azure pilot configuration |
| `marianos-live-api-west-loop` | 2 commits of Mariano's West Loop API trial evidence |

Neither contains Walmart code. They belong to the Mariano's submission and are
deliberately not folded into a Walmart corrections release.

One file was deliberately **removed** rather than carried forward:
`tools/headed_display_probe.py`. Its headless-and-headed comparison was folded
into `tools/egress_region_probe.py --display-ab`, which does the same work with
the stronger classification. Keeping both would have left two probes answering
one question differently.

## Feature checks

```bash
test -f walmart/tools/rebuild_evidence.py                              # evidence regeneration
grep -q _freshness walmart/walmart_collector/brightdata_import.py      # import history fix
grep -q _conflicting_fields walmart/walmart_collector/brightdata_import.py
grep -q _instant walmart/walmart_collector/brightdata_import.py        # timestamp precision fix
grep -q redacted_sha256 walmart/tools/verify_snapshot_manifest.py      # verifier fix
test -f walmart/tools/egress_region_probe.py                           # egress and display probe
test -f walmart/tools/opd_bounded_probe.py                             # bounded OPD probe
test -f walmart/walmart_collector/composition.py                       # field-level composition
```

All eight should succeed. If any fails you are not on the release.

## What changed since the branch you reviewed

You reviewed `c37dd03` on `walmart-timestamp-precision-and-verifier`. That
commit is an ancestor, and the five corrections sit on top of it:

1. Unavailable and unpriced products are retained rather than dropped. Catalog
   offers with no store price row, and offers with no usable product URL, are
   recorded in `unresolved_offers` and reported in the run report rather than
   disappearing.
2. A source that cannot attest coverage is refused a full publication, checked
   both at construction and again immediately before the release pointer is
   written.
3. Approximate-weight wording is excluded from titles as well as the weight
   field, on both retailers.
4. Malformed manifest entries fail the verifier instead of being filtered out,
   and declared is reported against examined.
5. `tools/opd_bounded_probe.py` is the bounded first test, with one cumulative
   budget and no retries.

Tests: 152 on Walmart, 91 on Mariano's.

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

Both were run against the package delivered on 30 October before this file was
written. The verifier reported 57 declared, 57 verified, 0 altered, 0 missing.
The rebuild reproduced:

| Check | Expected | Observed |
|---|---|---|
| Submitted identities reproduced | 615 of 615 | 615, none missing |
| Submitted set, pickup available | 471 | 471 |
| Submitted set, pickup unavailable | 144 | 144 |
| Full ledger identities | 654 | 654 |
| Products with a confirmed pickup price | 0 | 0 |

A field-by-field comparison of the regenerated records against the delivered
615 shows exactly two differences, both already known to you: `store_logo` on
all 615, which is the configuration change you confirmed, and `sub_category` on
one product. The retention correction introduces no others, which was checked
rather than assumed.
