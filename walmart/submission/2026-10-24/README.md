# Walmart scraper contest #63 — client review package

**Prepared:** 24 October 2026 · **Repository:** [Walmart-Kroger / walmart](../../)  
**Target:** Walmart Supercenter **#100**, 406 S Walton Blvd, Bentonville, AR **72712**  
**Candidate dataset:** **615 distinct genuine-source Walmart product observations** in the client's exactly ordered 22-field format  
**Release classification:** **TRIAL / INCOMPLETE ACCEPTANCE**, not a fully verified live-priced submission

> **Start here, reviewer:** [615-product demonstration JSON](Walmart_Store100_615_Trial_22Field.json) · [offline verification script](validate_submission.py) · [filter audit](../../reports/WALMART_STORE100_20261024_FILTER_AUDIT.md) · [full Walmart program and setup](../../README.md).

## Scope and versioned source code

- **Walmart Python collector:** [`walmart_collector/`](../../walmart_collector/); [source README](../../README.md); [package metadata](../../pyproject.toml). The Bright Data category-hierarchy importer has the **v0.7.1 correction**; the existing API/Azure automation components are v0.7.0 pilot architecture, **not production deployed**.
- **Bright Data importer:** [`walmart_collector/brightdata_import.py`](../../walmart_collector/brightdata_import.py).
- **Bright Data orchestration:** [`walmart_collector/brightdata_automatic.py`](../../walmart_collector/brightdata_automatic.py), [automation notes](../../BRIGHTDATA_AUTO_INTEGRATION.md).
- **Azure Container Apps pilot:** [Azure setup](../../azure/BRIGHTDATA_AZURE_SETUP.md) and [manual-job script](../../azure/create_brightdata_manual_job.sh).
- **Offline regression tests:** [`tests/`](../../tests/); **60 tests passed locally** following the category hierarchy fix. An earlier automated collection module had separate offline tests. These do **not** constitute a production Azure run.

## Demonstration and review

| Measurement | Result | Verification / caveat |
|---|---:|---|
| Original provider JSON snapshot files inspected | 46 | Imported offline; original files retained privately |
| Source response rows | 1,294 | 2026-10-22 and 2026-10-23 source observations |
| Source error rows | 177 | Includes store chooser issues, CAPTCHA, dead pages, timeouts |
| Rejected product responses | 463 | Seller 258, category 115, store 86, product identity 4 |
| Duplicate eligible product observations | 39 | Not counted as additional products |
| **Unique accepted assortment candidates** | **615** | 615 distinct product URLs; no synthetic records |
| Pickup available at last recorded observation | 471 | Store #100 context was checked |
| Pickup unavailable at last recorded observation | 144 | Preserved in history; not confused with shipping availability |
| Approved category groups represented | 11 of 11 | Representation **does not prove exhaustive category traversal** |
| Store-specific pickup prices independently verified | **0** | Online `final_price` is deliberately **not** passed off as selected-store pickup price |
| Directly displayed price-per-measure (PPM) independently verified | **0** | Numeric provider `unit_price` is not enough |
| Digital and volume promotion terms verified | **0** | Missing deal fields left empty |
| Production Azure execution and twice-weekly schedule observed | **No** | Prepared but not deployed |
| Automated interruption recovery validated on Azure | **No** | Designed; only offline/mock behaviors tested |

There are **615 authentic source-product candidates**, but **not 615 verified, price-complete store offers**. Please evaluate the trial data with that limitation.

### Category breakdown

| Approved category | Products |
|---|---:|
| Pets | 99 |
| Food | 81 |
| Beauty | 74 |
| Health & Wellness | 66 |
| Household Essentials | 60 |
| Office Supplies | 58 |
| Feeding | 58 |
| Personal Care | 44 |
| Diapering | 41 |
| Art Supplies | 20 |
| Balloons | 14 |
| **Total** | **615** |

## Quick reviewer verification (no keys)

Clone repository, from its root:

```bash
python walmart/submission/2026-10-24/validate_submission.py
cd walmart
python -m unittest discover -v tests
python tools/preflight.py
```

The first command checks distinct Walmart item URLs, exactly 22 string fields in the required order, ZIP/store, covered categories and crawl dates. It does **not** verify individual live website prices. The regression suite and preflight use offline fixtures and imported source observations; they do not perform a real Bright Data API trigger.

### Reproduce ingestion from authorized original snapshots

Keep raw files **outside the public Git repository**, in a private directory. From `walmart/`:

```bash
python tools/import_brightdata.py /private/walmart-snapshots/sd_*.json --output /private/walmart-output
```

Deduplication uses store and item identity; historical products, old source timestamps, pickup-unavailable products and rejected rows remain traceable. For the **original 46 inputs**, individual filename/SHA-256 checksums, per-record source-row hashes, processing outcomes, original online price candidates and provider PPM candidates are in the **private evidence package**; they are not all reproduced here because the repository is public and redistribution/access rights are not established. Arrange permissioned evidence handover for independent audit. **The demonstration JSON itself is intentionally public at the user's request; confirm redistribution authorization before relying on public hosting.**

The previous rejected-row totals are updated in the [aggregate audit](../../reports/WALMART_STORE100_20261024_FILTER_AUDIT.md). The product-level evidence includes both a filename and row hash so an authorized reviewer can check the original provider output.

## What has been resolved

1. The 500-product numerical threshold has been exceeded using **46 actual Bright Data files** and not mock/synthetic entries.
2. Added strict Store #100/72712, item-ID/URL, Walmart seller and approved-category validation.
3. Fixed the category hierarchy bug, which had wrongly omitted valid **Feeding, Diapering, Balloons and Art Supplies** records beneath broader Baby / Party / Arts departments.
4. Preserved pickup-unavailable records and historical product observations without fabricating availability.
5. Logged separate error, rejected-row and duplicate counts. Local importer/automation tests run offline.
6. Implemented guarded API snapshot retrieval and versioned Azure Blob trial-publication components in source.

## Outstanding client acceptance requirements

1. **Pricing / PPM:** obtain and validate *selected-store pickup* regular/sale prices and *displayed* PPM (not generic online price, inferred unit price or shipping price).
2. **Promotions:** verify coupon eligibility and clip requirements, quantity/volume deals and their full terms from source.
3. **Full-category coverage:** demonstrate exhaustive pagination and descendant enumeration for all eleven approved category roots, rather than merely obtaining products in each.
4. **Interruption recovery:** observe a real interrupted/resumed provider + Azure job with no double billing, partial promotion, or history loss.
5. **Azure production:** provision a client-approved subscription, storage, secure secrets, container job, monitored run and scheduled repeat; document actual execution logs and storage objects.
6. **Original raw evidence access:** give reviewer permissioned access to the 46 original snapshots and row-level provenance under the provider's data-use terms.

**No firm finish date is claimed for the above dependencies.** They require verified source capability/authorization, access to the client's Azure subscription and approval for possible cloud/vendor charges. **Do not mark this dataset client-accepted based only on the offline count.**

## Safety of source and other contest

This submission is scoped only to `walmart/`. **The separate Mariano's collector under `marianos/` has not been altered for this release.** No API credentials have been placed in GitHub. New paid live collection is disabled without explicit approval.
