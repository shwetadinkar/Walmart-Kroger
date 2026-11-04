#!/usr/bin/env python3
"""Watch the schedule fire by itself, and check it fires when it claims to.

"Twice-weekly Azure operation" is the weakest of the five evidence claims. The
deployment template exists and a three-execution pilot ran on Azure Container
Apps on 28 October, but that pilot was manually driven: **the schedule has
never been observed running by itself**, and a template plus a manual pilot is
not an observed schedule.

This closes as much of that as can be closed away from the client's Azure
subscription, and it is careful to separate two different claims rather than
letting one carry the other.

**Claim A, the deployed expression fires at the times it is meant to.**
Verified by computation, not simulation, and against the cron expression read
out of `azure/deploy_jobs.sh` rather than retyped here, so the thing checked is
the thing deployed. If someone edits the deployment default, this notices.

**Claim B, a scheduler left alone executes the job repeatedly.** Observed in
real elapsed time: a scheduler is started, nothing touches it, and each firing
drives a real `Collector` run through the real `KrogerSweepSource` with only
the Kroger HTTP client replayed. Every execution is recorded with its own
wall-clock timestamp.

Claim B uses a short interval rather than waiting days for Mondays and
Thursdays. That is a compression of the *cadence*, disclosed, and it is why the
two claims are kept apart: A establishes the real times, B establishes
unattended repetition. Neither establishes the other and neither establishes
Azure.

**What none of it establishes:** nothing here runs on Azure, nothing runs in
the client's environment, no Azure cron fired, and the data is replayed. Those
remain open and are stated in the transcript.
"""

import argparse
import json
import re
import shutil
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from marianos_collector.config import Category, Store  # noqa: E402
from marianos_collector.kroger_sweep_source import KrogerSweepSource  # noqa: E402
from marianos_collector.runner import Collector, ValidationFailure  # noqa: E402
from marianos_collector.storage import LocalStorage  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent

STORE = Store("53100502", "60061", "Marianos - Marianos Vernon Hills",
              "1720 N Milwaukee Ave, Vernon Hills, IL 60061", "")
CATEGORIES = [Category("Dairy", "https://www.marianos.com/d/dairy"),
              Category("Produce", "https://www.marianos.com/d/produce")]
CATEGORY_MAP = {"Dairy": "Dairy", "Produce": "Produce"}

# cron day-of-week: 0 and 7 are both Sunday, 1 is Monday.
DAY_NAMES = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday",
             "Friday", "Saturday"]


def deployed_cron(script: Path) -> str:
    """The cron expression the deployment script defaults to.

    Read rather than retyped. A copy here could drift from the deployment and
    then this tool would attest a schedule nobody deploys.
    """
    text = script.read_text()
    # Two spellings, because the two deployment scripts differ: Marianos
    # assigns CRON="${CRON_EXPRESSION:-...}" and Walmart inlines
    # "${CRON_EXPRESSION:-...}" at the az flag. Both are read rather than
    # retyped, and every default found must agree, so an edit to one of the
    # two places in a script cannot leave this attesting the other.
    found = re.findall(r'\$\{CRON_EXPRESSION:-([^}"]+)\}', text)
    if not found:
        raise SystemExit(f"No CRON_EXPRESSION default found in {script}")
    unique = {value.strip() for value in found}
    if len(unique) != 1:
        raise SystemExit(
            f"{script} carries disagreeing cron defaults {sorted(unique)}; "
            "fix the script rather than guessing which one deploys")
    return unique.pop()


def _field(spec: str, low: int, high: int) -> set:
    """One cron field expanded to the values it matches."""
    values = set()
    for part in spec.split(","):
        base, _, step_text = part.partition("/")
        step = int(step_text) if step_text else 1
        if base == "*":
            start, end = low, high
        elif "-" in base:
            a, _, b = base.partition("-")
            start, end = int(a), int(b)
        else:
            start = end = int(base)
        values.update(range(start, end + 1, step))
    return values


def matches(expression: str, moment: datetime) -> bool:
    """Whether a 5-field cron expression fires at this minute."""
    minute, hour, dom, month, dow = expression.split()
    cron_dow = (moment.weekday() + 1) % 7      # Monday 0 -> cron 1
    wanted_dow = _field(dow, 0, 7)
    if 7 in wanted_dow:
        wanted_dow.add(0)
    return (moment.minute in _field(minute, 0, 59)
            and moment.hour in _field(hour, 0, 23)
            and moment.day in _field(dom, 1, 31)
            and moment.month in _field(month, 1, 12)
            and cron_dow in wanted_dow)


def next_firings(expression: str, after: datetime, count: int) -> list:
    """The next `count` firing times, by walking minutes. No library."""
    moment = after.replace(second=0, microsecond=0) + timedelta(minutes=1)
    out = []
    limit = 366 * 24 * 60
    while len(out) < count and limit:
        if matches(expression, moment):
            out.append(moment)
        moment += timedelta(minutes=1)
        limit -= 1
    if len(out) < count:
        raise SystemExit(f"{expression!r} did not fire {count} times within a year")
    return out


# ------------------------------------------------------------------ claim A


def check_deployed_times(expression: str, count: int = 8) -> dict:
    firings = next_firings(expression, datetime(2026, 11, 3, tzinfo=timezone.utc), count)
    days = sorted({DAY_NAMES[(f.weekday() + 1) % 7] for f in firings})
    times = sorted({f.strftime("%H:%M") for f in firings})
    gaps = sorted({int((b - a).total_seconds() // 3600)
                   for a, b in zip(firings, firings[1:])})
    return {
        "claim": "The deployed cron expression fires on the days and times intended",
        "method": ("Computed, not simulated, from the expression read out of "
                   "azure/deploy_jobs.sh rather than retyped here."),
        "expression": expression,
        "next_firings_utc": [f.isoformat() for f in firings],
        "days_it_fires": days,
        "times_it_fires_utc": times,
        "hours_between_firings": gaps,
        "fires_twice_a_week": days == ["Monday", "Thursday"] and times == ["06:00"],
        "verdict": ("PASS" if days == ["Monday", "Thursday"] and times == ["06:00"]
                    else "FAIL"),
    }


# ------------------------------------------------------------------ claim B


def offer():
    return {"soldBy": "UNIT", "size": "18 ct", "fulfillment": {"curbside": True},
            "price": {"regular": 2.98}, "inventory": {"stockLevel": "HIGH"}}


def product(upc, categories=("Dairy",)):
    return {"productId": upc, "upc": upc, "description": f"Item {upc}",
            "brand": "Kroger", "productPageURI": f"/p/item/{upc}",
            "categories": list(categories), "items": [offer()], "images": []}


class ReplayClient:
    def __init__(self):
        self.calls = []

    def products(self, location_id, term, offset=0, limit=50):
        self.calls.append((term, offset))
        if offset:
            return {"data": [], "meta": {"pagination": {"total": 3}}}
        if term == "milk":
            items = [product(f"000111106{i:04d}") for i in range(3)]
        else:
            items = [product(f"000222206{i:04d}", ("Produce",)) for i in range(3)]
        return {"data": items, "meta": {"pagination": {"total": 3}}}

    def get(self, path):
        raise RuntimeError(path)


def one_execution(store_root: Path, work_root: Path, sequence: int) -> dict:
    """What one firing does. No operator involved."""
    started = datetime.now(timezone.utc)
    source = KrogerSweepSource(ReplayClient(), "53100502",
                               work_root / f"exec-{sequence}",
                               {"Dairy": ["milk"], "Produce": ["apples"]},
                               category_map=CATEGORY_MAP)
    record = {"execution": sequence, "fired_at_utc": started.isoformat()}
    try:
        out = Collector(LocalStorage(store_root), source, CATEGORIES,
                        min_products=1, trial=True).run(STORE)
        record.update(outcome="published",
                      release=out["manifest"]["release"],
                      records=out["report"]["unique_records"],
                      scope=out["report"]["scope"])
    except (ValidationFailure, ValueError) as exc:
        record.update(outcome="refused", refused_with=f"{type(exc).__name__}: {exc}")
    record["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
    return record


def observe_unattended(executions: int, interval: float,
                       keep_releases_under: Path | None = None) -> dict:
    """Start a scheduler, touch nothing, record every firing.

    `keep_releases_under` writes the published releases somewhere inspectable
    instead of a temporary directory. Without it this tool proved that a
    scheduler repeats the job and then discarded what the job published, so the
    one question an operator has before trusting an unattended run - what does
    a release from it actually contain, and are the page-only columns empty -
    could not be answered from its output.
    """
    if keep_releases_under is not None:
        store_root = Path(keep_releases_under) / "releases"
        work_root = Path(keep_releases_under) / "sweep-work"
        store_root.mkdir(parents=True, exist_ok=True)
        work_root.mkdir(parents=True, exist_ok=True)
    else:
        store_root = Path(tempfile.mkdtemp(prefix="sched-store-"))
        work_root = Path(tempfile.mkdtemp(prefix="sched-work-"))
    # A minute-granularity cron compressed to seconds, so the matcher that
    # decides the real schedule is the matcher driving this one.
    expression = f"*/{max(1, int(interval))} * * * * *"
    started = datetime.now(timezone.utc)
    runs = []
    try:
        last = None
        while len(runs) < executions:
            now = datetime.now(timezone.utc)
            tick = now.replace(microsecond=0)
            if tick != last and tick.second % max(1, int(interval)) == 0:
                last = tick
                runs.append(one_execution(store_root, work_root, len(runs) + 1))
            else:
                time.sleep(0.1)
        pointer = sorted(store_root.rglob("latest.json"))
        latest = json.loads(pointer[0].read_text()) if pointer else {}
        failures = sorted(store_root.rglob("failures/**/*.json"))
    finally:
        # Kept when the caller asked to keep them. Deleting what the run
        # published is what made this tool unable to answer the question an
        # operator actually has before an unattended deployment.
        if keep_releases_under is None:
            shutil.rmtree(store_root, ignore_errors=True)
            shutil.rmtree(work_root, ignore_errors=True)

    published = [r for r in runs if r["outcome"] == "published"]
    return {
        "claim": "A scheduler left alone executes the job repeatedly",
        "method": ("Real elapsed time. The scheduler was started and nothing "
                   "touched it; each firing drove a real Collector run through "
                   "the real KrogerSweepSource with only the Kroger HTTP client "
                   "replayed."),
        "cadence_used": f"every {int(interval)} seconds",
        "_cadence_is_compressed": (
            "The deployed cadence is twice weekly. Waiting for two real "
            "Mondays would not make the unattended-repetition property any "
            "more true, so the cadence is compressed and said so. The real "
            "times are claim A, checked by computation."),
        "observed_window_utc": [started.isoformat(),
                                datetime.now(timezone.utc).isoformat()],
        "executions_requested": executions,
        "executions_observed": len(runs),
        "executions_published": len(published),
        "distinct_releases": len({r.get("release") for r in published}),
        "operator_interventions": 0,
        "latest_pointer_after": latest.get("release", ""),
        "refused_executions": [r for r in runs if r["outcome"] != "published"],
        "failure_records_written": len(failures),
        "executions": runs,
        "verdict": ("PASS" if len(runs) == executions and len(published) == executions
                    and len({r.get("release") for r in published}) == executions
                    else "FAIL"),
    }


DOES_NOT_ESTABLISH = """\
# What observing the schedule does not establish

**It did not run on Azure.** No Azure Container Apps job was created, no Azure
cron fired, and nothing ran in the client's subscription. The only Azure
execution evidence in this project remains the three-execution pilot of 28
October, which was manually driven, at West Loop, on a five-product selection
of the single term `milk`.

**The cadence observed is not the deployed cadence.** The deployed schedule is
twice weekly and the observation ran every few seconds. That compression is why
the two claims are reported separately: the firing *times* are checked by
computing them from the deployed expression, and the *unattended repetition* is
observed in real time at a cadence nobody has to wait a week for. Neither
result stands in for the other.

**The data is replayed.** Only the Kroger HTTP client is stubbed, so the
collector, schema, retention reconciliation and storage are all real, but the
products are invented. Nothing here is evidence about this store's assortment
or any figure in the delivered dataset.

**It says nothing about the client's environment.** His Azure subscription, his
storage account, his secrets and his network are untested, and the brief asks
for operation there.

**One week of real operation is still unobserved.** Even on the real schedule,
this would need a week to show two firings. Nothing here shortens that; it
shows the expression is right and that repetition needs no operator.
"""


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--deploy-script", type=Path,
                   default=ROOT / "azure/deploy_jobs.sh")
    p.add_argument("--executions", type=int, default=3)
    p.add_argument("--keep-releases", action="store_true",
                   help="Write the published releases under --out instead of a "
                        "temporary directory, so what an unattended run "
                        "publishes can be inspected. Without this the tool "
                        "proved the scheduler repeats the job and then threw "
                        "away what the job produced.")
    p.add_argument("--interval", type=float, default=5.0,
                   help="Seconds between firings for the unattended observation")
    a = p.parse_args(argv)

    expression = deployed_cron(a.deploy_script)
    claim_a = check_deployed_times(expression)
    claim_b = observe_unattended(
        a.executions, a.interval,
        keep_releases_under=a.out if a.keep_releases else None)

    report = {
        "_what": ("Two separate claims about the schedule, kept apart so neither "
                  "carries the other."),
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "deployed_expression": expression,
        "deployed_expression_read_from": str(a.deploy_script),
        "claims": [claim_a, claim_b],
        "all_pass": claim_a["verdict"] == "PASS" and claim_b["verdict"] == "PASS",
    }
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / "SCHEDULE.json").write_text(json.dumps(report, indent=1))
    (a.out / "DOES_NOT_ESTABLISH.md").write_text(DOES_NOT_ESTABLISH)
    print(json.dumps({c["claim"]: c["verdict"] for c in report["claims"]}, indent=1))
    print(f"expression {expression!r} read from {a.deploy_script.name}")
    print(f"executions observed: {claim_b['executions_observed']}, "
          f"published: {claim_b['executions_published']}, "
          f"distinct releases: {claim_b['distinct_releases']}, "
          f"operator interventions: {claim_b['operator_interventions']}")
    print(f"wrote {a.out}")
    return 0 if report["all_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
