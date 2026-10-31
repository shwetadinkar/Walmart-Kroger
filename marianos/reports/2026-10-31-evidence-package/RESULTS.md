# Azure recovery evidence, corrected 31 October 2026

Replaces `azure_recovery/RESULTS.md`, which is kept unchanged and marked
superseded. That file promised original files and screenshots generically. This
one says what each file is. `MANIFEST_SHA256.json` lists every file in the
package with its hash.

All of this evidence is West Loop, store `53100508`. None of it is Vernon Hills.

## What the trial established

Three executions of `marianos-westloop-api-pilot` on 28 October, for a
five-product selection on the term milk.

| Execution | Stage | Platform result | Harness window (UTC) | HTTP attempts | New queries |
|---|---|---|---|---|---|
| `muij8ay` | interrupt | Failed, deliberately | from 09:20:45 | 3 | not recorded |
| `9vca720` | resume | Succeeded, 10:30:00 to 10:31:17 | 10:31:06 to 10:31:09 | 2 | 0 |
| `1pxbwhh` | fresh | Succeeded, 12:06:35 to 12:07:47 | 12:07:33 to 12:07:39 | 3 | 1 |

Eight attempts in total. The checkpoint survived the deliberate failure with its
SHA-256 unchanged.

## What is actually included

**Original files, downloaded from private Blob storage:**

- `RESUMED_PAGE_ORIGINAL.json`: the checkpoint, 699,424 bytes, SHA-256
  `b33c05fd8802b2ccc217df9c318e4663f4d94fafc1b35babf61259bb5f77e78a`, equal to
  the hash in `STATUS.json`. Despite the name, this is the page the interrupt
  stage saved at 09:20:49. The resume stage made no new query, and the file time
  of 10:38 is the download.
- `FRESH_PAGE_ORIGINAL.json`: the page the fresh stage observed at 12:07:39.
- `FRESH_RECEIPT_ORIGINAL.json`: the fresh stage's receipt.
- `VERIFIED_STORE_ORIGINAL.json` and `FRESH_STORE_ORIGINAL.json`: the store
  responses.

**Reserialized from the Azure portal, not original files:**
`INTERRUPT_RECEIPT_UI.json`, `RESUME_RECEIPT_UI.json` and
`DURABLE_CHECKPOINT_UI.json`.

**Text copied from the portal:** `EXECUTION_HISTORY_UI.txt`,
`RESTORED_CONTAINER_UI.txt` and `RESTORED_OVERVIEW_UI.txt`.

**Portal screenshots: none.** The three portal screenshots are withheld because
they show account-identifying details. UI transcriptions are supplied instead:
`RESTORED_CONTAINER_UI.txt` and `RESTORED_OVERVIEW_UI.txt` transcribe the restored
container and overview pages. They are accessibility-tree text, not images. The
third screenshot, of the temporary configuration before rollback, has no
transcription. `MANIFEST_SHA256.json` records the size and hash of all three, and
the 28 October manifest in `azure_recovery/` still lists them.

**Written during the trial:** `SCOPE.json`, `START_EVENT.json`, `STATUS.json`,
`REPEAT_COMPARISON.json`, `BASELINE_PRESERVATION.json` and
`ROLLBACK_REQUIRED.md`.

**Not included:** Azure diagnostic log exports, and any independent reading of
the digest of the image that actually ran.

## The two page files

Both are 699,424 bytes. They are not copies. They differ in content and in
`observed_at`: 09:20:49.774598 and 12:07:39.195016 UTC.

The equal size has a cause. Both hold the same 50 products in a different order,
and every value that changed kept its width: 17 `effectiveDate` values, the
pagination total (943, then 940) and `observed_at` itself. Reordering and
same-width changes cannot alter the length.

## The two selected files

`EARLIER_SELECTED_5.json` and `FRESH_SELECTED_5.json` are byte-identical, because
the selection produced identical records. They share a file time of 12:09:59
because both were serialized at the end of the trial, with `STATUS.json` and this
folder's manifest, not at the time of each observation. They are a derived
artifact. **The independent evidence is the two page files.**

Replaying the selection at `7c49e25` over each page file on 31 October gave five
identical records from both, for the same five UPCs and with the same values in
those files, with one exception: `product_title`. The selected files carry an
encoding fault on four of the five titles (`Â®` for `®`). The page files are
correct. The records also carry the `cid` parameter on `url`, as the pages do.

This is a same-day repeat on five products. It is not evidence of stability over
time.

## Source and image

| Item | Value |
|---|---|
| Trial source | `7c49e25dc5d315dcb3ff5cd9e0a46ae8595e432c` |
| Built image digest | `sha256:3fd2d63f77de79daeb879b69514b6ba9b322609f6b6591a663cf16538d6088ed`, from build evidence; the digest at runtime was not read |
| Image restored afterwards | `8a375326b9334b38d01e5159d553377099442937` |
| Reconciled release | `74a55c5e6fb2d938df1d06ff6717561420130cd9` |

`7c49e25` is not an ancestor of the release. They diverge at `58ff5fb`, and
`cloud_recovery.py` was carried over and has changed since. The release has not
been run in Azure, so this trial is evidence about `7c49e25` only.

## Batteries reference

The seven sizes recovered from a listing cite `LISTING_03.txt`, included at
111,454 bytes with SHA-256
`7df3e2da492c0b80175aff6382577bb311583431a95796500df51c2775989e60`. The file holds
no timestamp of its own. Its file time is 15:25:02 UTC on 28 October. It precedes
each product page, and the sizes remain listing observations, not product-page
observations. `PRODUCTS_34_PARTIAL_V2.json` and its V2 companions are current;
the earlier versions are kept and marked superseded. The chronology is in
`C4_BLOCKED_SOURCE_CHRONOLOGY.md`.

## Coupon source

`coupon_source/` is the full 28 October folder, with its manifest. See
`C2_COUPON_SOURCE.md`.

## What this does not establish

Publication protection after a failed cloud run, twice-weekly scheduling,
coverage of the 28 category roots, subcategory or pagination completeness,
unavailable-assortment completeness, full volume and digital terms, full-run
cost, or anything about Vernon Hills. `C5_RESULT_SEPARATION.md` keeps the results
apart.
