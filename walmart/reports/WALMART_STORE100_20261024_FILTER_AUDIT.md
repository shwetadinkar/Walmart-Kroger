# Walmart #63 — Store #100 filter audit (24 October 2026)

**Store / ZIP:** Walmart Supercenter #100, Bentonville, 72712  
**Status:** Offline import trial only. **NOT an acceptance-certified 500-record dataset.**  
**Data policy:** This public repository contains no original provider responses, product-level data export, API keys, or private evidence. Client access to originals requires private authorized storage.

## Source and normalization summary

- 45 distinct Bright Data JSON snapshot files inspected (22–23 October 2026 source observations).
- 1,268 source response rows.
- 171 source error rows, including store chooser failures, timeouts, CAPTCHA or unavailable pages.
- 445 product response rows rejected under strict store / category / seller / item identity rules.
- 39 repeated eligible product observations deduplicated.
- **613 unique Walmart Store #100 assortment candidates** remain (471 pickup-available and 142 pickup-unavailable at last observation).
- Earlier 422/422 products preserved; 191 additional unique candidates after category filter correction.
- The 22-field output is structurally verified and contains 613 unique product URLs.
- Locally run automated test suite: **60 tests passed**.

## Rejection reasons (product response rows)

| Reason | Count |
|---|---:|
| Walmart seller / retailer cannot be verified | 240 |
| Outside the 11 approved category paths | 115 |
| Store identity missing or inconsistent | 86 |
| Walmart item URL/product ID mismatch | 4 |
| **Total** | **445** |

Provider errors (171) are tracked separately, not misclassified as ineligible products.

## Coverage across client's eleven approved roots

| Category | Unique candidates |
|---|---:|
| Pets | 99 |
| Food | 81 |
| Beauty | 74 |
| Health & Wellness | 66 |
| Household Essentials | 60 |
| Office Supplies | 58 |
| Feeding | 58 |
| Personal Care | 44 |
| Diapering | 39 |
| Art Supplies | 20 |
| Balloons | 14 |
| **Total** | **613** |

## Important importer correction

The original importer used `root_category_url`, which incorrectly excluded genuine Feeding, Diapering, Art Supplies and Balloons products because their broad parent category is Baby, Arts & Crafts or Party & Occasions.

The corrected importer verifies the **primary product `category_ids` ancestry** against the approved paths, ignores unrelated `related_pages`, supports a strict top-level fallback for the provider's `-1` sentinel, and preserves the specifically excluded Recipes, Shop All Foods and Farm Animals scopes. It retains previously sourced descriptive fields with provenance if later partial responses omit them.

## Acceptance blockers still open

The provider's generic `final_price` is not verified as the specific selected store pickup price; `unit_price` is not independently established as directly displayed PPM; complete digital and quantity promotion terms were not observed. In the current 613-row trial export, **regular_price, sale_price, PPM and promotion fields remain blank** rather than inferred. Full-category traversal/pagination and live Azure twice-weekly operation also require independent verification.

**Private evidence package** includes original 45 snapshots, per-row reasons, observation history and JSON/CSV exports; it is intentionally **not checked into public GitHub**.

No additional billable Bright Data requests or Azure cloud deployments were performed during this offline import.
