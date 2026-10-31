# Coupon source and manifests

`coupon_source/` holds the 25 files its 28 October manifest declares, plus that
manifest. All hashes match. Its two screenshots, `EXACT_UPC_COUPON_DRAWER.png`
and `EXPANDED_COUPON.png`, passed the identity scan and were also inspected by
eye: both show the public site, signed out, at West Loop.

All three nested manifests now resolve. The only entries in them with no file
are the portal screenshots declared withheld in `MANIFEST_SHA256.json`.

## What the folder is

Browser-assisted observations on 28 October at West Loop, 40 S Halsted St, in an
anonymous session. No coupon was clipped, nothing was added to a cart, and no
account signed in. It is not evidence of an unattended Azure run.

`EXACT_UPC_TWO_PRODUCT_SAMPLE.json` has 2 records:

| UPC | Join | Observed (UTC) |
|---|---|---|
| `0003980000675` | Coupon drawer opened from that product's own Savings control | 14:16:14 |
| `0003980014532` | Coupon drawer opened from that product's own Savings control | 15:13:31 |

`digital_deals_price` is blank on both, because the discount is not a displayed
final price. The Nov. 22 expiry is as displayed, with no year. The cash-back
drawer on `0003980000675` was captured separately and was not combined with the
coupon or subtracted from the price. Its own no-cash-back wording remains a source
inconsistency, not resolved here.

## Overlap with the Batteries set

`0003980014532` is in both sets. `0003980014532` differs in
`digital_deals_description`, beyond whitespace. The terms read the same, but the
coupon sample's copy has encoding faults (`EnergizerÃ‚Â®` for `Energizer®`, and the
same on `¢` and `’`) and ends with the page's `Show Less` control label, which is
not coupon wording. The Batteries copy has neither. Both are preserved as
captured, and nothing here resolves them. For this product, read the Batteries
copy.

`0003980000675` has no Batteries copy to compare against, and its description in
the sample has the same faults and the same label. Its drawer capture is in
`EXACT_UPC_COUPON_DRAWER_AX.txt`.

## Not current

`EXACT_UPC_22_FIELD_SAMPLE.json` is the earlier one-record sample, and
`LOCAL_NORMALIZER_FIX.patch` and `VALIDATION.json` describe a local fix made that
day. The fix reached the release in `16a6f03`. The 197 tests in `VALIDATION.json`
are that day's figure and describe no current commit.
