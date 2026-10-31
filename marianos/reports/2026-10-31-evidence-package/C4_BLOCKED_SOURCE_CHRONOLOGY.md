# Chronology of the Batteries collection

`batteries_reference/BLOCKED_SOURCE.json` is preserved unchanged. It records 3
successful products and 92 remaining. The final set is 34 products and 61 pending.
Both pairs total the 95 discovered URLs, so they describe the same run at
different counts. The record's count of 3 does not match the 34 captures that
precede it, and nothing in the evidence says why. It is left as written.

All times are UTC on 28 October.

| Time | Event | Source |
|---|---|---|
| 15:24:28 to 15:25:02 | Four listing captures | `LISTING_00.txt` to `LISTING_03.txt`, file times |
| 15:25:11 | 95 unique URLs, matching the displayed total of 95 | `DISCOVERED_URLS.json` |
| 15:25:53 | First product page observed, `0003980014519` | `products/` |
| 15:26:51 | Third product page observed, `0003980014532` | `products/` |
| 15:30:50 | Thirty-fourth and last, `0003980011099` | `products/` |
| 15:31:21 | Access Denied on `0003980014517`; collection stopped with no retry | `BLOCKED_SOURCE.json`, `ACCESS_DENIED.png` |

The blocked product is among the 61 in `PENDING_61_URLS.json`. The 34 captures
match the identifiers in `PROGRESS.json`.

The refusal is a saved rendered Access Denied page with an edge reference. **No
HTTP status was independently captured.** The record says so, and it should not be
read as an observed 403.

This was agent-driven collection in a visible browser session, not an unattended
Azure run. Sixty-one URLs have no product-page capture.
