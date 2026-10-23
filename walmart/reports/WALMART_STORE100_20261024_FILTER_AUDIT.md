# Walmart contest #63 — Store #100 full offline source audit (24 October 2026)

**Store / ZIP:** Walmart Supercenter #100 · 406 S Walton Blvd, Bentonville, AR 72712  
**Release:** [Client review — 615-product trial JSON](../submission/2026-10-24/README.md)  
**Status:** **615 real-source assortment candidates, NOT acceptance-certified local-price data.**

## Original provider inputs and filter outcomes

**46 distinct Bright Data JSON files** (observed 22–23 October 2026); **1,294 response rows**.

| Outcome | Count |
|---|---:|
| Provider/source errors | 177 |
| Ineligible/uncorroborated product responses | 463 |
| Eligible but duplicate observations | 39 |
| **Unique eligible products in final store dataset** | **615** |
| **Total response rows** | **1,294** |

### Source errors

| Category | Count |
|---|---:|
| Dead page / store unavailability | 68 |
| CAPTCHA / block | 55 |
| Provider errors without normalized code (including store chooser issues) | 41 |
| Wait-element timeout | 12 |
| Parsing error | 1 |
| **Total** | **177** |

### Product rejection reasons

| Reason | Count |
|---|---:|
| Walmart seller or retailer unverified, including third-party marketplace sellers | 258 |
| Outside the approved 11 category paths | 115 |
| Store ID missing/mismatched | 86 |
| Walmart URL and product ID inconsistent | 4 |
| **Total** | **463** |

**The latest snapshot** `sd_mvlb7aru15q1lwe5t2.json` supplied **26** responses: six source errors, eighteen third-party seller rejections, and two valid Walmart product candidates (both pickup-unavailable) added to the previously reconciled 613.

## Category counts

| Approved root | Products |
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

Latest observed fulfillment: **471 pickup-available; 144 pickup-unavailable**. Import history preserves unavailable products rather than removing them. This is a snapshot observation, **not** proof of all local prices.

## Validation and limitations

- **615** distinct Walmart product URLs; exact **22-field** JSON schema; source observation dates preserved.
- Input source is **real Bright Data exported responses**, not synthetic fixture data.
- The old category-root bug was repaired: validate the **primary `category_ids` ancestry**, not only a broad department URL; the revised importer also handles documented `-1` sentinel cases under strict fallback.
- The correction includes Feeding, Diapering, Balloons and Art Supplies and protects Recipes, Shop All Foods and Farm Animals exclusions.
- **All 615 prices / displayed PPM remain unverified**: all `regular_price`, `sale_price`, `ppm` and `unit_price` are blank. Digital and volume offers are also blank, not invented.
- **Eleven categories represented** does *not* prove every subcategory or page was traversed.
- **Azure implementation update (24 October 2026):** Actual Walmart Docker program executed in South India Azure Container Apps Job, and its Managed Identity successfully read the manually uploaded 615-row JSON and wrote [a verification report](../submission/2026-10-24/azure_blob_verification_20261023T215838Z.json) to private Blob Storage. **No live Bright Data collection, automatic raw-history migration, scheduled ingestion or interruption/resume test has been demonstrated.**
- **60 importer/collector automated tests passed locally**; these are offline tests.
- Detailed original source row hashes, input file SHA-256 digests, per-record seller/store/fulfillment evidence and historical observations remain in a **private evidence package** for permissioned review. They are not interchangeable with store-specific pricing proof.

**Data-use note:** The public repo includes the user-requested 615-row demonstration, but it does not include original full provider snapshots, personal customer reviews, API keys or other nonessential raw material. Confirm the relevant redistribution rights. An authorization-controlled evidence handoff should be arranged before client acceptance.

No Bright Data paid collection, scheduled production ingestion, or end-to-end retailer-price verification is claimed. **Do not label 615 records a fully compliant client submission.**
