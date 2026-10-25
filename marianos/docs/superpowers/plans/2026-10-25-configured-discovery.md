# Configured unattended discovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make client configuration drive a bounded unattended category-discovery command with persisted evidence, safe resume, fresh execution identities and visible incomplete/failure reports.

**Architecture:** Reuse RenderedCategoryDriver, CategoryTraversal, CoverageLedger and LocalStorage/AzureBlobStorage. Add strict configuration and an ordinary browser-session setup adapter; never attach to or export the user's signed-in browser. Discovery is a usable first stage, not a claim of finished product/offer extraction.

**Tech Stack:** Python standard library, optional Playwright sync API, existing storage interfaces.

**Spec:** User's Priority Work Order and Important Additional Direction supplied 25 October 2026. Private evidence A–D is completed first; unattended production extraction remains the primary next objective.

## Global Constraints
- Only marianos/; preserve Walmart and 650 baseline.
- No new provider charge, Azure mutation, permission change, deployment or schedule activation.
- No CAPTCHA solving, stealth, proxy rotation or restriction bypass.
- Keep submission_ready false; do not treat listing traversal as variant/product completeness.
- Small selected categories do not inherit a mandatory 500-product minimum.

## Review Focus
- Resume may not silently use changed store/categories/limits or corrupt evidence.
- Separate execution IDs must not reuse a prior queue; same-execution resume must not replay completed nodes.
- Absolute aggregate page/action/time limits must survive interruption and resume.
- Store setup must verify exact street/name/ZIP and listing grid identity, not nearest ZIP alone.
- A blocked/error run must write an inspectable receipt without changing any successful product pointer.

## Task 1 — Configuration and discovery command
Files: production_config.py, discovery_job.py, config/discovery.westloop.example.json, tests/test_discovery_job.py.
- [x] RED: client config validation, selected-scope minimum, safe prefix/ID, resume mismatch, aggregate limits, durable error receipt and fresh execution tests.
- [x] GREEN: connect config to existing traversal/storage, persist config and receipts before work, capture failures without credentials or raw exception text.
- [x] Run targeted and full tests.

## Task 2 — Ordinary unattended browser setup and bounded live attempt
Files: browser_session.py, discovery_job.py, tests/test_browser_session.py, docs/UNATTENDED_DISCOVERY.md.
- [x] RED: exact store verification, wrong store and challenge response tests. Normal ZIP selection requires live acceptance and remains unproved.
- [x] GREEN: new isolated browser context, observed semantic controls, no credential state/proxy tricks; launch only the configured source roots.
- [x] Run one bounded ordinary local website discovery attempt with no API/provider calls; save actual success or concrete blocker. Do not retry an access restriction.
- [x] Record exact live boundary and remaining product/variant/offer integration work.

## Task 3 — Review and handover
- [x] Fresh review of new source, tests and reports; fix important findings.
- [x] Full regression/offline checks. Final source scan and outside-marianos check accompany publication.
- [ ] Publish reviewable PR continuation/source without private retailer evidence; do not deploy.

## Execution ledger

Base: 22017e1de92c9038b6cb2ff60e3e90dd4b650f21. Existing isolated feature checkout retained.
Ruling: first connect and live-test the discovery stage before broad product extraction — its existing driver currently requires manually prepared browser state — costs no new cloud infrastructure and exposes a critical source blocker early if present.

Review: two important findings fixed RED→GREEN: navigation budgets now charge before failed/bootstrap/child/return/load-more actions, and post-bootstrap failures capture source evidence. Fresh reviewer independently passed 13 targeted tests and found no remaining important issues. Full suite/preflight passed 136 tests locally.

Live result: initial ordinary unsigned Chromium navigation failed before store setup; one additional normal diagnostic captured only the net::ERR_HTTP prefix. No further live attempts or bypass. No category/product/variant coverage proved by this run. Explicitly blocked source compatibility is recorded in UNATTENDED_DISCOVERY.md; product/offer integration and Azure browser packaging remain future acceptance work.
