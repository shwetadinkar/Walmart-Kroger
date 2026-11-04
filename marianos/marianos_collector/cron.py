"""Cron expression maths, with no third-party dependency.

This lived in `tools/observe_schedule.py`, which is the only thing that needed
it until the retry supervisor did. Two reasons it moved here rather than being
copied:

- **One implementation.** The day-of-week conversion is the load-bearing
  detail: cron Monday is 1 where Python's `weekday()` makes it 0, and getting
  it wrong shifts every computed firing by a day. A second copy of that is a
  second chance to get it wrong, and the two would disagree silently.
- **The image ships `marianos_collector`, not `tools/`.** See the Dockerfile.
  The supervisor runs inside the container and has to know the gap between
  scheduled firings, so the maths has to be somewhere the container has.

Nothing here reads the schedule from Azure. It computes from an expression the
caller supplies, and the caller is responsible for having read that expression
out of the deployment script rather than retyping it.
"""

from datetime import datetime, timedelta, timezone

# cron day-of-week: 0 and 7 are both Sunday, 1 is Monday.
DAY_NAMES = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday",
             "Friday", "Saturday"]

# A year of minutes. The walk below is bounded by this so a malformed or
# never-firing expression raises rather than spinning.
_WALK_LIMIT_MINUTES = 366 * 24 * 60


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
    limit = _WALK_LIMIT_MINUTES
    while len(out) < count and limit:
        if matches(expression, moment):
            out.append(moment)
        moment += timedelta(minutes=1)
        limit -= 1
    if len(out) < count:
        raise ValueError(f"{expression!r} did not fire {count} times within a year")
    return out


def shortest_gap_seconds(expression: str, samples: int = 16,
                         after: datetime = None) -> int:
    """The smallest interval between two consecutive firings, in seconds.

    This is the ceiling on how long one execution may take before it risks
    overlapping the next one. A retry plan that can run longer than this can
    still be in progress when the scheduler fires again, and the instruction
    the plan exists to satisfy was that the next run stays on time.

    Overlap is not merely untidy. Azure's cron fires independently of how long
    an execution takes, so a long execution does not delay the next firing - it
    runs *beside* it. On the Mariano's side the second execution would then meet
    the Blob lease `storage.locked(store_id)` holds and be refused, so a retry
    plan that overruns converts a transient failure into a refused next run.
    That is the opposite of keeping the next run on time, which is why this is
    checked rather than assumed.

    `samples` firings are taken so an irregular expression is measured at its
    tightest rather than at whichever gap happens to come first. `0 6 * * 1,4`
    alternates 72 and 96 hours, and 72 is the answer that binds.
    """
    if samples < 2:
        raise ValueError("need at least two firings to measure a gap")
    start = after or datetime(2026, 1, 1, tzinfo=timezone.utc)
    firings = next_firings(expression, start, samples)
    gaps = [int((b - a).total_seconds()) for a, b in zip(firings, firings[1:])]
    return min(gaps)
