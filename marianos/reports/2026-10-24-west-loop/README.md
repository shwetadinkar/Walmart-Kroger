# Mariano's West Loop — verified API trial package

## What you have
- **604 unique real product records** in the exact 22-field string schema, ZIP 60661.
- Original 650-record API review file, with 46 conflicting/unavailable records separated into quarantine.
- Official API store proof: location 53100508, Mariano's West Loop, 40 S Halsted St, Chicago, IL 60661.
- 204 matched website page captures; retained dataset includes 158 source-displayed PPM values and 29 volume-offer descriptions.
- Original source responses, hashes, per-record provenance and category/field validation.
- Working source and tests, bounded request limits, checkpoints, overlap protection and an Azure job template.

## Start here
Use `Marianos_WestLoop_604_Trial_22Field.json` as the conservative trial export. `Marianos_WestLoop_650_API_Review.json` is the broader API review set; it includes records later quarantined. Neither file is final accepted full-category production output.

`VALIDATION.json` records count, uniqueness, field completeness, exact source hashes, website/API conflicts and live recovery evidence. `QUARANTINE_46.json` gives the excluded rows and reasons. Category values preserve known aliases or original API labels; they are not a claim that all CSV roots were traversed.

## Work still required for final acceptance
The site began returning Access Denied after the 204 successful checks; requests were stopped. Remaining website PPM/coupon fields were not invented. All 28 category roots and descendants are not yet proven exhausted. Digital-coupon terms, buyer-observed acceptance, Azure deployment/scheduled execution and the recorded walkthrough remain unverified.

The source package contains no credentials. Your encrypted credentials remain outside it. No Azure resources or recurring charges were created, no support message or contest entry was sent, and Walmart was unchanged.

API response timestamp window: 20.01 seconds, excluding startup/OAuth. This is not total-job runtime. The second live collector returned 650 records; 650 UPCs are shared with the original review set.

See `OPERATING_GUIDE.md` for reproduction and deployment prerequisites. The existing final submission gate remains blocked rather than claiming incomplete coverage passed.
