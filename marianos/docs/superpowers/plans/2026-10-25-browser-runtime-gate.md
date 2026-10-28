# Browser runtime source gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Diagnose the exact ordinary-browser failure and prepare a concrete reviewed browser-enabled image for one separately approved Azure discovery probe.

**Architecture:** Reuse discovery_job and the existing job/Blob environment. Add an explicit discovery entrypoint mode that validates the shipped configuration against store environment settings. Package the standard browser and its OS dependencies without changing website access controls, user sessions or network protocols.

**Tech Stack:** Python 3.12, pinned Playwright browser package, existing Azure storage and manual GitHub image build.

**Spec:** User's production automation direction and continuation request, 25 October 2026.

## Constraints and review focus
- Preserve Walmart, protected 650 baseline and current Azure runtime; no deployment/run/schedule/billing/role mutation without explicit approval.
- Never use stealth, proxy rotation, CAPTCHA solving, certificate exceptions or protocol-disabling flags.
- Require exact configured store, isolated output prefix, disabled schedule and Azure execution identity before launching discovery.
- Browser image build/smoke test must use about:blank only, with no retailer/API/Azure calls.
- Failed source access is a blocker, not category proof. No product or promotion completeness claim.

## Tasks
- [x] RED→GREEN: preserve complete numeric Chromium error subtype while excluding raw sensitive exception text.
- [x] One bounded ordinary local source-gate attempt: failed before HTTP response with net::ERR_HTTP2_PROTOCOL_ERROR; no store/category coverage.
- [ ] RED→GREEN: explicit discovery entrypoint, mismatched store/ZIP, unsafe config path, missing Azure execution identity and safe default behavior.
- [ ] Browser-enabled Docker packaging plus network-free runtime smoke script; retain existing API mode.
- [ ] Regression suite, offline preflight and fresh review; publish only Mariano’s source and build the existing manual image workflow.
- [ ] Record exact image/test resource/output limits, cost bounds and rollback steps in a concrete approval packet. Do not execute the Azure probe without approval.

## Execution ledger
Base: 738eb03ae0caf2217008b811b60f16f182e67876. Existing isolated PR #2 checkout retained.
Ruling: do not keep retrying the failing Windows source path — exact transport failure is now recorded. Prepare the same ordinary collector for an approved alternate execution environment, with no new service/provider or security bypass. Azure approval is the final gate after the image and rollback plan are reviewable.
