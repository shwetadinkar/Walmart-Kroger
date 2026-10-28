# Browser runtime source gate — 25 October 2026

## Exact current blocker

The bounded unsigned Windows Chromium attempt `unattended-source-gate-20261025-b` failed on its first navigation at 09:56:16–09:56:18 UTC (15:26 IST), before an HTTP response, store selection or listing traversal. Its recorded code is `net::ERR_HTTP2_PROTOCOL_ERROR`. It consumed one browser action and one page-navigation action. No products or source coverage were published. This error establishes a transport failure, not its underlying cause or a successful parser/store test.

Earlier diagnostics captured only a truncated error prefix. The application now whitelists complete Chromium codes including numeric subtypes and omits raw exception messages that could contain sensitive URLs or headers. No proxy, stealth, CAPTCHA solving, certificate exception or protocol-disabling retry was used.

## Implemented runtime preparation

The Dockerfile installs pinned Playwright 1.63.0, Chromium and OS dependencies on Python 3.12 Bookworm. It runs as nonroot user 10001. The image build launches Chromium against `about:blank` and literal local HTML, aborting page routes. This smoke test proves startup only and makes no retailer/API/Azure requests. See [official Playwright Docker guidance](https://playwright.dev/python/docs/docker).

The entrypoint has an explicit `MARIANOS_MODE=discovery` path. It reads only a basename within the shipped configuration directory, validates configuration, requires its store/ZIP to match the job environment and requires Azure execution metadata. Discovery uses stable execution identity and the existing Blob adapter. No product latest pointer is touched. Existing API trial behavior and safe list default remain tested.

Local offline preflight passed 141 tests. A fresh reviewer independently passed 14 targeted checks and reported no important findings. The local smoke used the host's installed Playwright 1.55.0; the image build must separately establish the pinned Linux runtime. No cloud deployment/run is implied.

## Proposed next source test — approval required

Prepare the exact built image/digest before requesting approval for one manual discovery execution on the existing Mariano’s job. Proposed limits: existing 0.5 CPU/1 GiB, 600-second outer timeout, zero retries, one replica, and the smoke configuration's three navigation/load-more actions, 24 browser actions and 90-second action-start budget. In-flight operations also have browser timeouts; 600 seconds is the hard cloud execution bound.

Use the existing private Blob container and isolated `discovery-review/53100508/<execution-id>/` output. Discovery uses no Kroger API credentials or provider jobs. No new resource, permission, billing plan or schedule is requested. At existing allocation, the outer bound is 300 vCPU-seconds and 600 GiB-seconds for one replica. This is not a dollar charge or a guarantee that shared free grants remain; storage/log operations add usage.

This small source/store/pagination feasibility probe cannot exhaust Batteries and is not category acceptance. Record normal source/store success or the exact blocker. Restore the approved API image/mode afterward and preserve the 650 baseline. Verify live pre-test image/mode/settings and rollback values read-only before the final approval packet. No test is authorized by this document.

If ordinary Azure source access also fails, stop rather than try bypasses or repeated samples. Reassess a licensed store/category/offer-complete source under separate commercial approval. Full nested/variant/product/promotion traversal, live interruption/resume, fresh category repeat and approved scheduling remain open. submission_ready=false.
