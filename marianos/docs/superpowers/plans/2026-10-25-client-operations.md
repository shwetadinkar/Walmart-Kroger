# Client Operations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Finish the source-independent configuration, reporting, recovery verification and operator handover work authorized by the user.

**Architecture:** Reuse the strict discovery configuration and existing receipt/checkpoint/publication implementations. Add a standard-library-only operations module for local configuration checking and safe report projections, automatically saved alongside discovery and API execution receipts. Preserve all source and cloud limits.

**Tech Stack:** Existing Python 3.11+ package, unittest, local filesystem fixtures.

**Spec:** User-approved remaining-work note, 25 October 2026; production automation direction. User requested execution of the proposed balance work, with existing scope/architecture retained.

## Global Constraints
- Changes only under marianos/; preserve protected baseline and Walmart.
- No network collection, Azure mutation, credentials, providers, deployment or scheduling.
- submission_ready=false; offline recovery is not live acceptance.
- Retain unknown counters as null rather than claiming zero; omit raw source/exception/credential fields from operational reports.
- Keep existing data and receipt schemas backwards compatible; operational JSON is separate from the 22-field product schema.

## Review Focus
- Missing/negative/bool counts cannot look like successful zero-record observations.
- A completed discovery is not product extraction or contest readiness.
- Report generation must not leak arbitrary error strings, URLs, secrets or account metadata.
- Local check/report commands must not instantiate network clients or overwrite input evidence.
- Recovery verification must distinguish same-execution resume, independent fresh observations, low yield and publication failure.

## Tasks
- [x] RED→GREEN: operations.check_configuration(document, expected_store=None, expected_zip=None), using existing validation plus bounded numeric cron semantics; add CLI check with JSON/Markdown output and meaningful exit status. Reject invalid configurations without echoing raw values.
- [x] RED→GREEN: operations.build_report(mode, receipt, configuration=None, validation=None, coverage=None) whitelist projection across discovery, api-trial and collection reports; preserve unknowns, distinguish synthetic and completeness, reject cross-store evidence and unsafe/malformed states. Add CLI report for local artifacts only.
- [x] RED→GREEN: write separate operational reports automatically alongside discovery and API execution receipts, including failed executions, without changing publication or retry semantics.
- [x] Exercise existing recovery/publication and synthetic acceptance paths through the actual packaged interface; add only missing behavioral tests and save dated results.
- [x] Write a single current operator guide, fix stale README status, document scope, secrets, configuration, reports, recovery, source limits, schedule/deploy gates and exact walkthrough. Build a private source/evidence/handover ZIP with hashes and verify from a clean extracted copy.
- [ ] Run full suite/preflight; fresh review; resolve important findings. Publish source to existing draft PR, preserve old evidence package and deployed image.

## Execution ledger
Base: 7616ffd9e0c4e2da72e817f92a41cba0aea92a6d. Reuse existing isolated branch. Native execution follows user's request to do the balance work; no further design questionnaire is needed for the accepted scope. No image build/deployment is needed to demonstrate these local additions.

Task 1: complete — 15 operator behavior tests now cover valid/invalid locality and cron, safe CLI failures, report privacy, coherent identity/counts/synthetic evidence, publication-pending state and automatic report failure handling.
Task 2: complete — automatic supplementary reports for discovery/API executions; existing collection reports have a unified local view. No collection/publication control flow changed.
Task 3: complete — clean-package preflight and both existing 560-record synthetic recovery simulations passed; these are not live acceptance.
Review: fresh independent reviewer passed all 153 then-current tests and found two important report-coherence issues. Both were reproduced RED and repaired GREEN, alongside a publication-pending classification regression. Full suite then passed156 tests.
Ruling: supplementary report persistence is best-effort with a fixed warning — authoritative receipt failures and last-good publication semantics must not be masked by an additional reporting failure.
Ruling: keep the existing draft PR and no deployment/image build; user authorized continuation of that source branch, not merge or Azure changes.
