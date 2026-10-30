"""Controlled A/B probe: does the egress region change what the retailer returns?

THE QUESTION
    Earlier attempts ran from Azure South India and from a machine in India, and
    were refused. A contestant on the public clarification board stated that the
    retailer edge blocks non-US traffic. That is a hypothesis about *where the
    request comes from*, not about what the source can supply, and it has never
    been tested.

    This probe holds everything constant except the egress region: same target,
    one navigation, no retries. Run it once from the existing region and once
    from a US region, then compare.

WHAT IT IS NOT
    Not a collector and not a workaround. It makes exactly ONE request to the
    retailer, records what came back, and stops. It does not retry, rotate,
    pace around a refusal, alter TLS or headers, or attempt any form of
    challenge solving. A refusal is the result, not an obstacle.

    It imports nothing from walmart_collector and writes nothing the collector
    reads.

WHY IT RECORDS THE EGRESS ADDRESS
    The experiment is meaningless without evidence of where the request
    originated. The probe resolves its own public address and country from a
    neutral service first, so the comparison rests on observed geography rather
    than on the region name someone typed.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import socket
import ssl
import sys
import time
import urllib.error
import urllib.request
from uuid import uuid4

NEUTRAL_CONTROL = "https://example.com/"
EGRESS_LOOKUP = "https://ipinfo.io/json"

# Two tiers, because conflating them produced a wrong verdict in both
# directions on 30 October.
#
# REFUSAL_MARKERS are phrases that appear on an actual refusal page. If one of
# these is present the visitor was shown a wall.
REFUSAL_MARKERS = (
    "robot or human", "access denied", "are you a human", "verify you are",
    "/_sec/cp_challenge", "errors.edgesuite.net", "request unsuccessful",
    "incapsula", "cf-browser-verification",
)
# ANTIBOT_MARKERS are bot-protection machinery that these retailers ship on
# ordinary pages too. Finding "captcha" inside a script reference says the
# protection exists, NOT that this request was challenged. A Walmart category
# page served with 61 product links also matched "captcha"; treating that as a
# refusal would have been plainly wrong.
ANTIBOT_MARKERS = ("captcha", "px-captcha", "perimeterx", "datadome", "akamai-bm")

# Kept as the union for any caller that wants "anything bot-related".
CHALLENGE_MARKERS = REFUSAL_MARKERS + ANTIBOT_MARKERS
# Markers that indicate a real shopping page actually rendered.
SHOPPING_MARKERS = ("add to cart", "pickup", "in stock", "price", "aisle")


def _utc():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _get(url, timeout, ua=None):
    """One plain HTTPS GET. Redirects followed; nothing else is special."""
    req = urllib.request.Request(url, headers={"User-Agent": ua} if ua else {})
    started = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read(400_000)
            return {"status": resp.status, "elapsed_ms": int((time.time() - started) * 1000),
                    "bytes": len(body), "body": body, "error": None}
    except urllib.error.HTTPError as exc:
        body = exc.read(400_000)
        return {"status": exc.code, "elapsed_ms": int((time.time() - started) * 1000),
                "bytes": len(body), "body": body, "error": f"HTTPError {exc.code}"}
    except (urllib.error.URLError, socket.timeout, ssl.SSLError, OSError) as exc:
        return {"status": None, "elapsed_ms": int((time.time() - started) * 1000),
                "bytes": 0, "body": b"", "error": f"{type(exc).__name__}: {exc}"}


def _get_browser(url, timeout, headless=True):
    """One navigation in a real browser, when Playwright is available.

    A plain client and a browser are treated very differently by edge
    protection: in our own measurements a plain GET was dropped from every
    location, while a real browser reached the edge and was answered. Results
    from the two methods are therefore NOT comparable, and the method used is
    recorded in every artifact.

    Headless and headed are likewise not interchangeable, and that is not a
    theoretical caution. Measured 30 October 2026 across three consecutive runs
    with identical results in every cell, from one datacenter address:

        Walmart category    headless: challenged   headed: no challenge
        Walmart product     headless: challenged   headed: challenged
        Marianos category   headless: no response  headed: HTTP 200

    So the window is a real variable, and an earlier prediction that it would
    not matter "because the refusal is keyed to the address and not the window"
    was wrong. Headed needs a virtual display; see --method headed.
    """
    from playwright.sync_api import sync_playwright
    started = time.time()
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=headless)
        try:
            page = browser.new_context().new_page()
            try:
                resp = page.goto(url, timeout=timeout * 1000, wait_until="domcontentloaded")
                body = (page.content() or "").encode("utf-8", "replace")
                # Count links that actually point at product detail pages.
                #
                # Text markers alone are not enough, and that is measured, not
                # cautious: on 30 October a Marianos category page returned 200
                # with "pickup" and "price" present and was classified SERVED,
                # while the page itself was a consent notice plus navigation
                # with ZERO products on it. "Pickup & Delivery" is a nav link.
                # A page that serves products carries links to products.
                try:
                    products = page.evaluate(
                        "() => document.querySelectorAll("
                        "'a[href*=\"/ip/\"], a[href*=\"/p/\"]').length"
                    )
                except Exception:
                    products = None
                return {"status": resp.status if resp else None,
                        "elapsed_ms": int((time.time() - started) * 1000),
                        "bytes": len(body), "body": body, "error": None,
                        "product_links": products,
                        "final_url": page.url,
                        "browser_version": browser.version}
            except Exception as exc:
                return {"status": None, "elapsed_ms": int((time.time() - started) * 1000),
                        "bytes": 0, "body": b"",
                        "error": f"{type(exc).__name__}: {str(exc)[:200]}",
                        "browser_version": browser.version}
        finally:
            browser.close()


def fetch(url, timeout, method, ua=None):
    """Dispatch to a browser or a plain client, reporting which was used.

    The method name travels in the result because comparisons across methods
    are not controlled, and the comparison code refuses them on that basis.
    """
    if method in ("browser", "headed"):
        headless = method == "browser"
        if not headless and not os.environ.get("DISPLAY"):
            # Fail loudly rather than silently falling back to headless, which
            # would produce a result labelled "headed" that was nothing of the
            # kind and would quietly corrupt the A/B.
            return {"status": None, "elapsed_ms": 0, "bytes": 0, "body": b"",
                    "error": "headed requested but no DISPLAY is set; run under "
                             "xvfb-run or use azure/Dockerfile.headed",
                    "method": "headed_unavailable_no_display"}
        try:
            r = _get_browser(url, timeout, headless=headless)
            r["method"] = method
            r["headless"] = headless
            return r
        except ImportError:
            r = _get(url, timeout, ua)
            r["method"] = "plain_http_playwright_unavailable"
            return r
    r = _get(url, timeout, ua)
    r["method"] = "plain_http"
    return r


def classify(result):
    text = result["body"][:400_000].decode("utf-8", "replace").lower()
    refusal = sorted({m for m in REFUSAL_MARKERS if m in text})
    antibot = sorted({m for m in ANTIBOT_MARKERS if m in text})
    hits = sorted(set(refusal) | set(antibot))
    shopping = sorted({m for m in SHOPPING_MARKERS if m in text})
    products = result.get("product_links")
    # Only a browser can count product links. For a plain GET the question does
    # not arise, so absence of a count is not evidence of absence of products.
    counted = isinstance(products, int)

    if result["error"] and result["status"] is None:
        verdict = "TRANSPORT_FAILURE"
    elif counted and products > 0 and refusal:
        # Products AND a refusal phrase. Genuinely ambiguous, and the verdict
        # says so instead of picking a side.
        verdict = "AMBIGUOUS_PRODUCTS_AND_REFUSAL_TEXT"
    elif counted and products > 0 and antibot:
        # Content arrived; the site merely ships bot protection, as these
        # retailers do on ordinary pages. Not a refusal.
        verdict = "SERVED_ANTIBOT_PRESENT"
    elif refusal or result["status"] in (403, 401, 429):
        verdict = "REFUSED_OR_CHALLENGED"
    elif result["status"] == 200 and counted and products == 0 and antibot:
        verdict = "SHELL_WITHOUT_PRODUCTS"
    elif result["status"] == 200 and counted and products == 0:
        # The decisive case. A page arrived, it is not a challenge, and it
        # carries no products. Calling this SERVED would overstate it by a
        # wide margin: it is the shell, which is what a consent interstitial
        # or an unhydrated single-page app looks like.
        verdict = "SHELL_WITHOUT_PRODUCTS"
    elif result["status"] == 200 and counted and products > 0:
        verdict = "SERVED"
    elif result["status"] == 200 and shopping:
        # Text markers only, no link count available. Weaker evidence, and the
        # verdict says so rather than borrowing SERVED's authority.
        verdict = "SERVED_TEXT_MARKERS_ONLY"
    elif result["status"] == 200:
        verdict = "SERVED_BUT_UNRECOGNISED"
    else:
        verdict = "OTHER"
    return {"verdict": verdict, "method": result.get("method", "plain_http"),
            "browser_version": result.get("browser_version"),
            "http_status": result["status"],
            "elapsed_ms": result["elapsed_ms"], "response_bytes": result["bytes"],
            "transport_error": result["error"],
            "product_links": products if counted else None,
            "final_url": result.get("final_url"),
            "refusal_markers_found": refusal,
            "antibot_markers_found": antibot,
            "challenge_markers_found": hits, "shopping_markers_found": shopping}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--target", required=True, help="One retailer URL to request once")
    p.add_argument("--region-label", required=True,
                   help="Where you believe this is running, e.g. 'azure-southindia'. "
                        "Recorded alongside the OBSERVED egress country, which is authoritative.")
    p.add_argument("--timeout", type=int, default=45)
    p.add_argument("--method", default="browser", choices=["browser", "plain", "headed"],
                   help="browser (default) drives real headless Chromium via Playwright and is "
                        "the method comparable with earlier browser evidence. headed drives the "
                        "same Chromium with a window, which requires a virtual display and is "
                        "NOT comparable with headless for an egress-region question, because it "
                        "changes two variables at once. plain sends a bare HTTPS GET, which edge "
                        "protection drops from every location tested, so a plain result cannot "
                        "settle a question about egress region.")
    p.add_argument("--display-ab", action="store_true",
                   help="Run headless AND headed against the same target in the same run, from "
                        "the same address, to test whether the browser window changes the "
                        "answer. This is the controlled form of that question: comparing two "
                        "separate runs risks confounding the window with time or address.")
    p.add_argument("--user-agent", default=None,
                   help="Optional UA string. Left unset by default: this probe measures the "
                        "default response and does not disguise the client.")
    p.add_argument("--output", type=Path, required=True, help="PRIVATE output root, outside git")
    p.add_argument("--compare", type=Path,
                   help="A previous RECEIPT.json to produce an A/B comparison against")
    args = p.parse_args(argv)

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid4().hex[:8]
    outdir = args.output / "egress_probe" / run_id
    outdir.mkdir(parents=True)

    started = _utc()

    # 1. Where is this actually running? Observed, not asserted.
    egress = {"lookup": EGRESS_LOOKUP}
    r = _get(EGRESS_LOOKUP, args.timeout)
    try:
        info = json.loads(r["body"].decode("utf-8"))
        egress.update({"ip": info.get("ip"), "country": info.get("country"),
                       "region": info.get("region"), "city": info.get("city"),
                       "org": info.get("org"), "resolved": True})
    except Exception:
        egress.update({"resolved": False, "error": r["error"] or "unparseable"})

    # 2. Neutral control: proves general connectivity independent of the retailer.
    control = classify(fetch(NEUTRAL_CONTROL, args.timeout, args.method))

    # 3. One retailer request per arm. No retry under any outcome.
    #    --display-ab runs two arms against the same target from the same
    #    address in the same run, which is the controlled way to ask whether
    #    the browser window changes the answer. Comparing two separate runs
    #    would confound the window with time and with address.
    display_ab = None
    if args.display_ab:
        arms, raw = {}, {}
        for arm_method in ("browser", "headed"):
            arm_result = fetch(args.target, args.timeout, arm_method, args.user_agent)
            raw[arm_method] = arm_result
            arms[arm_method] = classify(arm_result)
            (outdir / f"TARGET_RESPONSE_{arm_method}.bin").write_bytes(arm_result["body"])

        # The single-target receipt below describes whichever arm the operator
        # asked for; headless is the sensible default when they asked for
        # neither (--method plain with --display-ab).
        primary = args.method if args.method in arms else "browser"
        target_result, target = raw[primary], arms[primary]

        # An arm that could not start is not an arm. Only a run where BOTH
        # browsers actually drove counts as a controlled display comparison.
        both_ran = all(arms[m].get("method") == m for m in ("browser", "headed"))
        changed = arms["browser"]["verdict"] != arms["headed"]["verdict"]
        display_ab = {
            "controlled": both_ran,
            "reason": "" if both_ran else
                      "Both arms must actually run before the window can be held "
                      "responsible for a difference",
            "primary_arm_in_receipt": primary,
            "headless": arms["browser"],
            "headed": arms["headed"],
            "verdict_changed": changed if both_ran else None,
            "window_changes_the_answer": both_ran and changed,
            "note": "Same target, same address, same run. The only deliberate "
                    "difference is the browser window.",
        }
    else:
        target_result = fetch(args.target, args.timeout, args.method, args.user_agent)
        target = classify(target_result)
        (outdir / "TARGET_RESPONSE.bin").write_bytes(target_result["body"])

    receipt = {
        "run_id": run_id,
        "purpose": "egress_region_ab_probe",
        "started_utc": started, "ended_utc": _utc(),
        "claimed_region_label": args.region_label,
        "client_method": args.method,
        "method_note": ("A plain client and a real browser are treated differently by "
                        "edge protection. Only runs using the same method are comparable."),
        "observed_egress": egress,
        "target_url": args.target,
        "retailer_requests_made": 1, "retries": 0,
        "user_agent_overridden": bool(args.user_agent),
        "tls_or_header_manipulation": False,
        "proxy_used": False,
        "challenge_solving_attempted": False,
        "neutral_control": control,
        "target": target,
        "display_ab": display_ab,
        "target_response_sha256": sha256(target_result["body"]).hexdigest(),
        "source_mode": "diagnostic_probe_not_production",
        "production_ready": False,
        "touches_collector_state": False,
    }
    (outdir / "RECEIPT.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")

    lines = [f"# Egress region probe, {started[:10]}\n",
             "One request to one retailer URL, to test whether the egress region changes what "
             "the edge returns. No retry, no proxy, no header or TLS manipulation, no challenge "
             "solving. A refusal is recorded as the result.\n",
             "## Where this ran\n",
             f"- Claimed region label: `{args.region_label}`",
             f"- Client method: **{target.get('method')}**"
             + (f" ({target['browser_version']})" if target.get("browser_version") else ""),
             f"- Observed egress IP: {egress.get('ip') or 'not resolved'}",
             f"- Observed country: **{egress.get('country') or 'unknown'}**"
             f"  (region {egress.get('region') or '?'}, org {egress.get('org') or '?'})\n",
             "The observed country is what the comparison rests on. The region label is only "
             "what the operator believed.\n",
             "## Result\n",
             "| | Neutral control | Retailer target |", "|---|---|---|",
             f"| URL | {NEUTRAL_CONTROL} | {args.target} |",
             f"| HTTP status | {control['http_status']} | {target['http_status']} |",
             f"| Verdict | {control['verdict']} | **{target['verdict']}** |",
             f"| Elapsed ms | {control['elapsed_ms']} | {target['elapsed_ms']} |",
             f"| Response bytes | {control['response_bytes']} | {target['response_bytes']} |",
             f"| Challenge markers | {', '.join(control['challenge_markers_found']) or 'none'} "
             f"| {', '.join(target['challenge_markers_found']) or 'none'} |",
             f"| Transport error | {control['transport_error'] or 'none'} "
             f"| {target['transport_error'] or 'none'} |\n",
             "A control that succeeds while the target is refused shows the refusal is specific "
             "to the retailer rather than a general network fault.\n"]

    if display_ab:
        hl, hd = display_ab["headless"], display_ab["headed"]
        lines += ["## Headless against headed, same target and same address\n",
                  "| | Headless | Headed |", "|---|---|---|",
                  f"| Method actually used | {hl.get('method')} | {hd.get('method')} |",
                  f"| HTTP status | {hl['http_status']} | {hd['http_status']} |",
                  f"| Verdict | **{hl['verdict']}** | **{hd['verdict']}** |",
                  f"| Challenge markers | {', '.join(hl['challenge_markers_found']) or 'none'} "
                  f"| {', '.join(hd['challenge_markers_found']) or 'none'} |",
                  f"| Shopping markers | {', '.join(hl['shopping_markers_found']) or 'none'} "
                  f"| {', '.join(hd['shopping_markers_found']) or 'none'} |",
                  f"| Transport error | {hl['transport_error'] or 'none'} "
                  f"| {hd['transport_error'] or 'none'} |\n"]
        if not display_ab["controlled"]:
            lines.append(f"**Not a controlled comparison: {display_ab['reason']}.**\n")
        elif display_ab["window_changes_the_answer"]:
            lines.append(
                "Both arms ran against the same target from the same address in the same run, "
                "so the browser window is the only deliberate difference, and the outcome "
                "changed. The window is a real variable.\n\n"
                "A changed verdict is not the same as usable data. Read the shopping markers "
                "row: a `SERVED_BUT_UNRECOGNISED` verdict means a page came back without the "
                "markers a real shopping page carries, which is a shell rather than products.\n")
        else:
            lines.append(
                "Both arms ran against the same target from the same address in the same run "
                "and the outcome did not change, so the browser window does not explain this "
                "refusal.\n")

    if args.compare and args.compare.is_file():
        prev = json.loads(args.compare.read_text(encoding="utf-8"))
        pe, pt = prev.get("observed_egress", {}), prev.get("target", {})
        lines += ["## A/B comparison\n",
                  "| | Previous run | This run |", "|---|---|---|",
                  f"| Region label | {prev.get('claimed_region_label')} | {args.region_label} |",
                  f"| Observed country | **{pe.get('country')}** | **{egress.get('country')}** |",
                  f"| Target | {prev.get('target_url')} | {args.target} |",
                  f"| HTTP status | {pt.get('http_status')} | {target['http_status']} |",
                  f"| Verdict | {pt.get('verdict')} | {target['verdict']} |\n"]
        same_target = prev.get("target_url") == args.target
        same_method = prev.get("client_method") == args.method
        lines.append(f"| Client method | {prev.get('client_method')} | {args.method} |\n")
        if not same_method:
            lines.append("**These runs used different client methods, so this is not a controlled "
                         "comparison of egress region.**\n")
        changed = pt.get("verdict") != target["verdict"]
        controlled = same_target and same_method
        lines.append(
            ("The only deliberate difference between these runs is the egress region. "
             if controlled else
             "**These runs used different target URLs, so this is not a controlled comparison.** ") +
            ("The outcome changed, which supports egress geography as the cause.\n" if changed and controlled
             else "The outcome did not change, so egress geography alone does not explain the refusal.\n"
             if controlled else "\n"))

    lines += ["## What this does and does not establish\n",
              "A served response shows the edge serves this request from this location. It does "
              "not establish category coverage, unattended operation at volume, or that a "
              "datacenter address will keep being served.\n",
              "A refusal from both locations rules out geography and points at address "
              "reputation or client fingerprinting instead.\n",
              "Shweta\n"]
    (outdir / "FINDINGS.md").write_text("\n".join(lines), encoding="utf-8")

    print(json.dumps({"output_directory": str(outdir),
                      "observed_country": egress.get("country"),
                      "observed_ip": egress.get("ip"),
                      "control_verdict": control["verdict"],
                      "target_verdict": target["verdict"],
                      "target_http_status": target["http_status"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
