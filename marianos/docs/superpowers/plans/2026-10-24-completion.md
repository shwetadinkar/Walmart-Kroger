# Fresh executions and category evidence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preserve the working Azure trial while fixing fresh execution identity and establishing evidence-backed category/source and enrichment gates.

**Architecture:** Extend the current bounded collector rather than replace it. Use Azure's documented execution name as the stable checkpoint identity for replicas/retries, with fresh identity for different executions. Keep category completeness and source authorization independent of the keyword API trial; accept only demonstrated source evidence.

**Tech Stack:** Python standard library, existing Azure Blob/Managed Identity adapters, existing Container Apps Job and Docker image workflow.

**Spec:** User handover dated 24 October 2026; `SHARED_REQUIREMENTS.docx`, `config/categories.csv`, and the live public contest specification.

## Global Constraints
- Preserve Azure export b70ded437414abb646e0 and Docker digest 09000c6068c96d934660b92a796e3cf7db5a3f6df4a32b12c628aeb9ee81fc6b.
- All code changes stay under marianos/. Walmart resources, data and permissions stay untouched.
- Work on marianos-fresh-runs-category-evidence; create a separate pull request.
- Obtain user approval before Azure mutation, permission expansion, paid services or provider jobs.
- Keep submission_ready false until every mandatory requirement passes.

## Review Focus
- Fixed legacy run IDs must not make separate Azure executions replay old pages.
- Completed execution retries must not move latest backwards or refetch products.
- Wrong store, stale website evidence and price conflicts must never produce silent enrichment.
- Terminal UI state and provider claims alone cannot prove complete category traversal.
- Missing source rights or categories must remain explicit blockers rather than synthetic acceptance.

### Task 1: Baseline and gap matrix
- [x] Verify actual downloaded Azure JSON, field order, uniqueness, timestamps and hashes; preserve immutable private copies.
- [x] Reconcile successful Actions run with branch head; clone isolated checkout and create continuation branch.
- [x] Inspect live Azure job non-secret configuration and execution evidence without mutations.
- [x] Record detailed gap/source capability and authorization matrix.

### Task 2: Fresh-run identity and operational evidence
- [x] Add failing execution identity and duplicate/retry tests.
- [x] Implement run_context.py; prefer documented CONTAINER_APP_JOB_EXECUTION_NAME over legacy fixed ID; allow explicit local resume.
- [x] Add immutable execution receipts and timing/request/cache counters to api_collection.py; preserve last successful pointer.
- [x] Test two executions make independent source calls, same-execution retry resumes, duplicate completion makes no calls, store locks and failures preserve good output.
- [x] Prepare disabled schedule configuration and per-store config; no Azure changes.

### Task 3: Category-source feasibility and completeness evidence
- [x] Verify official source capability/conditions. Do not spend Bright Data credits or bypass blocks.
- [ ] Implement a persisted coverage ledger that validates traversal/page/terminal evidence, rejects repeated pages/count contradictions, and reports all 28 roots and unresolved paths.
- [x] Exercise preserved genuine navigation/listing evidence; distinguish discovered links from traversed/complete categories.
- [ ] Implement live source traversal only if authorization and source completeness capability are established.

### Task 4: Conservative evidence enrichment
- [x] Add explicit product/store/timestamp matching and strict price-conflict quarantine for the Azure baseline.
- [x] Preserve original 650 export; write a separately named review export with per-field provenance and unresolved temporal gaps.
- [ ] Verify displayed PPM and promotion conditions; never infer digital terms or calculated prices.

### Task 5: Review and delivery
- [ ] Run regression suite, independent review, credential scan, offline preflight and original/Walmart hash comparisons.
- [ ] Publish source branch and a clear draft PR with actual tests and limitations.
- [x] Prepare operating-cost assumptions, setup/recovery instructions, acceptance checklist and exact demonstration script.
- [ ] Present concrete Azure update/schedule plan for approval only when code is built and verified; retain manual baseline until approved.

## Current verification boundary
105 automated tests and offline preflight passed. Live local 5+5 API observations and one 19-result leaf category were observed. Full category traversal, paired fresh website enrichment, complete coupon terms, multi-store live acceptance, a new Azure image/execution and scheduled occurrences remain unverified. The Python browser driver has not run end to end. Approval is still required before Azure changes.
