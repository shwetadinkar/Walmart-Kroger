# Verified West Loop API trial implementation plan

Goal: deliver the actual 650-product official-API collection in the exact schema, with evidence and a repeatable bounded collector. Preserve full-coverage acceptance gates.

Architecture: API collection and imports live in a separate trial module/CLI; the existing provider publication path is unchanged. Source category labels are preserved in provenance. Website evidence may enrich only matching store/UPC records; displayed PPM and full coupon conditions are never calculated.

Spec: SHARED_REQUIREMENTS.docx; config/categories.csv; user authorization for a different verified Mariano's store and completion of the task.

Constraints: marianos/ changes only; no credentials or customer data in public files; gupc/unit_price empty; 22 ordered strings; no approximate-weight records; raw source and timestamps retained; API keyword search is not category exhaustion proof.

Tasks:
- [ ] Add tests for source verification, field normalization, deduplication, website evidence store/UPC matching and promotion separation, and failed-run preservation.
- [ ] Implement API trial import/export with a separate trial namespace and source manifest. Map source labels conservatively; do not invent subcategories.
- [ ] Integrate bounded official API collection/checkpoints with explicit request/record ceilings and verified store identity.
- [ ] Generate and validate the 650 real records. Verify selected West Loop website prices/PPM/coupon details and preserve evidence.
- [ ] Run full test suite, preflight, recovery and repeat-import checks. Inspect secret exposure and Walmart diff. Obtain independent final review.
- [ ] Deliver source, JSON, provenance, validation, coverage limitations and deployment instructions. Report Azure execution and full category gaps truthfully.

Baseline: commit 58ff5fb799c780c8a8788270e3538481dab54ff7; 33 tests passed. Isolated shallow clone and branch marianos-live-api-west-loop.

Ruling: retain the existing final submission gate. The collected 650 products satisfy a real-data count milestone, not complete 28-root coverage or observed Azure execution. No Azure CLI/Docker is available on PATH in this session.
