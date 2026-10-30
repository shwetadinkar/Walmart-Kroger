"""Does a headed browser under a virtual display change what Azure receives?

WHY THIS EXISTS
---------------
The 30 October measurement tested headless Chromium from Azure and recorded
that Walmart answers with a PerimeterX challenge page and Mariano's closes the
connection before any HTTP exchange. That document stated one explicit limit:

    "This tested headless Chromium. Headed Chrome under a virtual display from
     Azure was not tested."

This probe closes that gap. It is the only remaining untested variable in the
access finding, and leaving it open while telling the client the route is
refused would be asserting more than was measured.

WHAT IT DOES AND DOES NOT DO
----------------------------
Two arms in one run, from one container, against the same URLs:

  * headless Chromium
  * headed Chromium under Xvfb, a virtual X display

Each arm requests a neutral control first, so an arm that fails everything can
be told apart from a retailer refusal.

One navigation per URL. No retries. No proxy. No header, TLS or fingerprint
manipulation. No challenge solving. A refusal is the result and is recorded as
such; nothing is attempted to get around one.

This probe is deliberately narrow. It answers "does the window change the
answer", not "can we get the data". If the headed arm also returns a challenge,
that is a finding to report, not a prompt to try something stronger.

MERGE NOTE
----------
`egress_region_probe.py` on the walmart-source-qualification-probe branch
already dispatches by method and refuses cross-method comparison. When that
branch lands, this probe's two arms belong there as a third method rather than
as a separate tool. It is standalone here only so the measurement is not
blocked on that merge.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone

# Markers published in the 30 October finding. Presence is recorded; absence is
# not treated as success, because a page can be refused without saying so.
CHALLENGE_MARKERS = (
    "robot or human",
    "px-captcha",
    "perimeterx",
    "are you a human",
    "access denied",
    "unusual traffic",
    "verify you are",
)

DEFAULT_TARGETS = [
    {"name": "neutral_control", "url": "https://example.com/", "role": "control"},
    {"name": "walmart_category", "url": "https://www.walmart.com/cp/food/976759", "role": "target"},
    {"name": "walmart_product", "url": "https://www.walmart.com/ip/938273658", "role": "target"},
    {"name": "marianos_category", "url": "https://www.marianos.com/c/dairy", "role": "target"},
]


class ProbeError(RuntimeError):
    pass


def egress_address(timeout: int = 10) -> dict:
    """Record the address the retailer actually sees, not the one we assume."""
    try:
        from urllib.request import urlopen

        with urlopen("https://api.ipify.org?format=json", timeout=timeout) as response:
            return {"observed": json.loads(response.read(4096)).get("ip", ""), "error": ""}
    except Exception as exc:  # noqa: BLE001 - the address is context, never the result
        return {"observed": "", "error": f"{type(exc).__name__}: {exc}"}


def _classify(title: str, body: str) -> list:
    haystack = f"{title}\n{body}".lower()
    return [marker for marker in CHALLENGE_MARKERS if marker in haystack]


def visit(page, target: dict, nav_timeout_ms: int) -> dict:
    """One navigation. No retry. The outcome is the result, whatever it is."""
    record = {
        "name": target["name"],
        "url": target["url"],
        "role": target["role"],
        "status": None,
        "title": "",
        "challenge_markers": [],
        "error": "",
        "elapsed_ms": None,
    }
    started = time.monotonic()
    try:
        response = page.goto(target["url"], timeout=nav_timeout_ms, wait_until="domcontentloaded")
        record["status"] = response.status if response else None
        record["title"] = (page.title() or "")[:300]
        body = ""
        try:
            body = (page.inner_text("body") or "")[:4000]
        except Exception:  # noqa: BLE001 - a body we cannot read is still a result
            body = ""
        record["challenge_markers"] = _classify(record["title"], body)
    except Exception as exc:  # noqa: BLE001
        record["error"] = f"{type(exc).__name__}: {exc}"[:400]
    record["elapsed_ms"] = round((time.monotonic() - started) * 1000, 1)
    return record


def run_arm(headless: bool, targets: list, nav_timeout_ms: int) -> dict:
    from playwright.sync_api import sync_playwright

    arm = {
        "arm": "headless" if headless else "headed_xvfb",
        "headless": headless,
        "display": os.environ.get("DISPLAY", ""),
        "browser_version": "",
        "results": [],
        "arm_error": "",
    }
    if not headless and not arm["display"]:
        arm["arm_error"] = (
            "Headed arm requires a virtual display. Start Xvfb and export DISPLAY, "
            "or use the accompanying Dockerfile.headed."
        )
        return arm

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=headless)
            arm["browser_version"] = browser.version
            context = browser.new_context()
            page = context.new_page()
            for target in targets:
                arm["results"].append(visit(page, target, nav_timeout_ms))
            browser.close()
    except Exception as exc:  # noqa: BLE001
        arm["arm_error"] = f"{type(exc).__name__}: {exc}"[:400]
    return arm


def compare(arms: list) -> dict:
    """State plainly whether the window changed the answer.

    Only compares arms that actually ran, and only for targets both arms
    reached, because a comparison against an arm that failed to start is not a
    comparison.
    """
    by_arm = {arm["arm"]: arm for arm in arms if not arm["arm_error"]}
    if len(by_arm) < 2:
        return {
            "comparable": False,
            "reason": "Both arms must run before their results can be compared",
            "arms_that_ran": sorted(by_arm),
        }

    headless = {r["name"]: r for r in by_arm["headless"]["results"]}
    headed = {r["name"]: r for r in by_arm["headed_xvfb"]["results"]}

    control_ok = {
        arm: any(
            r["role"] == "control" and r["status"] == 200
            for r in by_arm[arm]["results"]
        )
        for arm in by_arm
    }

    differences = []
    for name in sorted(set(headless) & set(headed)):
        a, b = headless[name], headed[name]
        if a["role"] != "target":
            continue
        changed = (
            a["status"] != b["status"]
            or bool(a["challenge_markers"]) != bool(b["challenge_markers"])
            or bool(a["error"]) != bool(b["error"])
        )
        if changed:
            differences.append(
                {
                    "target": name,
                    "headless": {
                        "status": a["status"],
                        "markers": a["challenge_markers"],
                        "error": a["error"],
                    },
                    "headed_xvfb": {
                        "status": b["status"],
                        "markers": b["challenge_markers"],
                        "error": b["error"],
                    },
                }
            )

    return {
        "comparable": True,
        "controls_returned_200": control_ok,
        "targets_compared": len([n for n in set(headless) & set(headed) if headless[n]["role"] == "target"]),
        "targets_that_differ": len(differences),
        "differences": differences,
        "headed_display_changes_the_answer": bool(differences),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Compare headless against headed-under-Xvfb from this environment"
    )
    parser.add_argument("--targets", type=str, default="", help="JSON file overriding the target list")
    parser.add_argument("--nav-timeout-ms", type=int, default=30000)
    parser.add_argument("--out", type=str, default="", help="Write the record to this path as well as stdout")
    parser.add_argument(
        "--arm",
        choices=["both", "headless", "headed"],
        default="both",
        help="Run a single arm. 'both' is required for a comparison.",
    )
    args = parser.parse_args(argv)

    targets = DEFAULT_TARGETS
    if args.targets:
        with open(args.targets, encoding="utf-8") as handle:
            targets = json.load(handle)
        if not isinstance(targets, list) or not targets:
            raise ProbeError("Target file must be a non-empty JSON array")

    if not any(t.get("role") == "control" for t in targets):
        raise ProbeError(
            "A neutral control is required, so that an arm which fails everything "
            "can be distinguished from a retailer refusal"
        )

    arms = []
    if args.arm in ("both", "headless"):
        arms.append(run_arm(True, targets, args.nav_timeout_ms))
    if args.arm in ("both", "headed"):
        arms.append(run_arm(False, targets, args.nav_timeout_ms))

    record = {
        "probe": "headed_display_probe",
        "question": "Does a headed browser under a virtual display change what this environment receives?",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "egress": egress_address(),
        "xvfb_available": bool(shutil.which("Xvfb")),
        "method": {
            "navigations_per_url": 1,
            "retries": 0,
            "proxy": "none",
            "header_tls_or_fingerprint_manipulation": "none",
            "challenge_solving": "none",
            "bypass_attempted": False,
        },
        "arms": arms,
        "comparison": compare(arms),
        "caution": (
            "A refusal here is the measurement, not a failure to work around. "
            "If the headed arm is also refused, that is the finding."
        ),
    }

    text = json.dumps(record, indent=2)
    print(text)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as handle:
            handle.write(text + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
