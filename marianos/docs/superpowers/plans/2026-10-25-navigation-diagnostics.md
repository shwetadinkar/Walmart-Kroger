# Bounded navigation diagnostics

Scope: offline instrumentation only; no retailer calls, Azure changes, new spend, or protocol/security changes.

1. RED tests for ordered main-frame request/response/failure, URL and error redaction, caps and snapshot isolation.
2. Implement a 32-event recorder with numeric browser version, relative time and status only. Attach before first navigation; detach after setup.
3. Include snapshot in setup failure evidence and successful driver. Never retain headers, bodies, cookies, query, fragment or arbitrary path.
4. Run complete offline suite and independent final review. Deliver source and verification, preserving earlier packages.

Acceptance: failure is still a failure, submission_ready remains false; this is instrumentation, not a transport fix.

Completed: 163 offline tests pass, including 3 optional Chromium checks with all requests intercepted. RED missing recorder and rendered-text privacy regression observed before GREEN. Independent final review: no important findings. No Azure/retailer requests or deployment. All changes confined to marianos/.
