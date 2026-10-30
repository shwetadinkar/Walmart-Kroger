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

# Rendered markers that indicate a challenge or refusal rather than a page.
CHALLENGE_MARKERS = (
    "robot or human", "access denied", "are you a human", "verify you are",
    "captcha", "px-captcha", "/_sec/cp_challenge", "errors.edgesuite.net",
    "request unsuccessful", "incapsula", "cf-browser-verification",
)
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


def _get_browser(url, timeout):
    """One navigation in a real browser, when Playwright is available.

    A plain client and a browser are treated very differently by edge
    protection: in our own measurements a plain GET was dropped from every
    location, while a real browser reached the edge and was answered. Results
    from the two methods are therefore NOT comparable, and the method used is
    recorded in every artifact.
    """
    from playwright.sync_api import sync_playwright
    started = time.time()
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        try:
            page = browser.new_context().new_page()
            try:
                resp = page.goto(url, timeout=timeout * 1000, wait_until="domcontentloaded")
                body = (page.content() or "").encode("utf-8", "replace")
                return {"status": resp.status if resp else None,
                        "elapsed_ms": int((time.time() - started) * 1000),
                        "bytes": len(body), "body": body, "error": None,
                        "browser_version": browser.version}
            except Exception as exc:
                return {"status": None, "elapsed_ms": int((time.time() - started) * 1000),
                        "bytes": 0, "body": b"",
                        "error": f"{type(exc).__name__}: {str(exc)[:200]}",
                        "browser_version": browser.version}
        finally:
            browser.close()


def fetch(url, timeout, method, ua=None):
    """Dispatch to a browser or a plain client, reporting which was used."""
    if method == "browser":
        try:
            r = _get_browser(url, timeout)
            r["method"] = "browser"
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
    hits = sorted({m for m in CHALLENGE_MARKERS if m in text})
    shopping = sorted({m for m in SHOPPING_MARKERS if m in text})
    if result["error"] and result["status"] is None:
        verdict = "TRANSPORT_FAILURE"
    elif result["status"] == 200 and shopping and not hits:
        verdict = "SERVED"
    elif hits or result["status"] in (403, 401, 429):
        verdict = "REFUSED_OR_CHALLENGED"
    elif result["status"] == 200:
        verdict = "SERVED_BUT_UNRECOGNISED"
    else:
        verdict = "OTHER"
    return {"verdict": verdict, "method": result.get("method", "plain_http"),
            "browser_version": result.get("browser_version"),
            "http_status": result["status"],
            "elapsed_ms": result["elapsed_ms"], "response_bytes": result["bytes"],
            "transport_error": result["error"],
            "challenge_markers_found": hits, "shopping_markers_found": shopping}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--target", required=True, help="One retailer URL to request once")
    p.add_argument("--region-label", required=True,
                   help="Where you believe this is running, e.g. 'azure-southindia'. "
                        "Recorded alongside the OBSERVED egress country, which is authoritative.")
    p.add_argument("--timeout", type=int, default=45)
    p.add_argument("--method", default="browser", choices=["browser", "plain"],
                   help="browser (default) drives real Chromium via Playwright and is the only "
                        "method comparable with earlier browser evidence. plain sends a bare "
                        "HTTPS GET, which edge protection drops from every location tested, so "
                        "a plain result cannot settle a question about egress region.")
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

    # 3. Exactly one retailer request. No retry under any outcome.
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
