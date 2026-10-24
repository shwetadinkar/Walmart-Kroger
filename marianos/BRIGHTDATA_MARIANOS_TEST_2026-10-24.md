# Mariano's single-URL compatibility test — 24 October 2026

## Result: failed; do not scale
Dataset `gd_mhlod8vh2kwgoi9yw3` was tested through the authenticated dashboard with exactly one input:
- URL: https://www.marianos.com/p/green-onions/0000000004068?fulfillment=PICKUP
- zip_code: 60601
- Snapshot: `sd_mvlszutt1sfyjzr6jr`
- Response timestamp: 2026-10-24T02:52:36.905Z (08:22:36 India)
- Dashboard: Ready, 2 seconds, 0% success, one input, 423 B reported size.
- Actual downloaded JSON error: **No Kroger pickup store found for zip code 60601**
- error_code: `bad_input`
- Original downloaded JSON SHA-256: `43CF3A48B1DD8AFDDCD347C308525F1896671D10390CEC375112CA5CE591DD1E`

The URL reached a provider response, but this does not prove supported Mariano's collection. No product, price, UPC, store, PPM or promotion was returned. ZIP 60601 alone did not establish the intended Lakeshore East store. The test does not prove every Mariano's ZIP or provider product is unsupported; it proves this exact configuration failed.

**No five-product batch, category discovery, 500-product collection, Azure execution or contest submission was launched.**

## Earlier pending snapshot now resolved
`sd_mvlk2zd6caphp8rda` became Ready, 0% success, 7min53s, approximately 440 B reported size. Its actual JSON was downloaded:
- input: Kroger green-onions URL, blank ZIP (as previously audited)
- timestamp: 2026-10-23T22:50:56.879Z
- error_code: `detect_block`
- error: Block was detected: "Access Denied" matches the pattern "Access Denied"
- Original JSON SHA-256: `A0491881041614FA210D883B109EDDC897398E7C367E7AAD2FDD5E0A038E491E`

This supersedes the earlier audit's time-specific observation that the snapshot was still running.

## Request and spending accounting
Two single-input requests were launched during this continuation:
1. `sd_mvlsyzo026bmwduvua`: an unintended repeat of the existing Kroger URL/blank ZIP. The agent clicked Run manually before the configuration form finished loading. It was observed Running with one input; its terminal outcome was not verified in this audit. This was disclosed to the user. Do not count it as a Mariano's record.
2. `sd_mvlszutt1sfyjzr6jr`: the intended Mariano's compatibility test above, failed.

Dashboard displayed 3,561 / 5,000 free credits before and after the test and rate $1.50 / 1k records. No purchase, top-up or plan change was performed. A delayed credit adjustment or exact billable usage was not independently reconciled; unchanged displayed credits must not be claimed as proof of zero charge.

## Evidence and scope
Raw JSON responses and the Mariano's input CSV were saved locally. No API keys, account email/IP, account identifier or customer review text is included in this document. Changes in this continuation are confined to this document under `marianos/`; Walmart and workflows remain untouched.

## Next actionable step
Ask Bright Data support for the supported way to select **Mariano's Lakeshore East, 333 E Benton Pl, Chicago, IL 60601**, using this dataset. Supply the exact Mariano's URL, ZIP and `bad_input` text; share private snapshot identifiers only through the account's authorized support channel. Ask whether the endpoint is Kroger-banner-only, and whether Mariano's requires a distinct scraper or store/location input. No support message has been sent.

Resume only with a supported, verified Mariano's configuration. Then perform one successful record, independently check retailer/store/ZIP/price/UPC and source-displayed PPM/promotions, and only then run the bounded five-product trial. Missing PPM/promotions remain missing; do not derive or invent them.
