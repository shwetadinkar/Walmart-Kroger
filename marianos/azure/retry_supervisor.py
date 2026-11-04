"""Retry a refused unattended run, then report the failure by email.

The instruction this implements, in the account holder's words on 4 November:
*"If it fails then keep trying every 15 minutes for 8 times, and still not
successful then send email regarding failure. But next run should remain on
time due."*

Three design decisions are load-bearing, and each exists because the
alternative is wrong rather than merely different.

**Why the retry happens inside one replica rather than through Azure.**
Container Apps jobs have `--replica-retry-limit`, and `deploy_jobs.sh` sets it
to 0. Raising it would retry a failed replica, but the interval between the
platform's retries is not configurable, so "every 15 minutes" cannot be
expressed that way. Supervising inside the replica is the only way to honour
the interval that was asked for. The cost is that the whole plan lives inside
one replica timeout, and an Azure replica timeout is a SIGKILL, so the plan has
to fit. That is what the window arithmetic below is for, and what
`deploy_jobs.sh` refuses a deployment over.

**Why the first attempt gets the whole window and retries get the remainder.**
The obvious scheme reserves eight intervals up front, so the first attempt gets
`window - 8 x interval`. That is backwards: it starves the run that *succeeds*
in order to pay for retries it never needs, and at the default 7200s timeout it
reserves more than the window holds and leaves a negative budget. So each
attempt is given whatever is actually left when it starts.

This has a consequence worth stating, because it removes a special case: **a
run that consumed its whole budget and failed is not retried**, because there
is nothing left to retry it with. Budget exhaustion is the one failure where
retrying is pure waste - it will be given less time, not more - and it falls
out of the clock rather than needing the collector to classify its own
failures. The supervisor owns the clock, so it does not need a new exit-code
contract to know this.

**Why almost everything else is retried, including an expired credential.**
`CLAUDE.md` records credential expiry as the likeliest unattended failure for a
twice-weekly job, and a classifier cannot tell an expired key from a transient
token blip. Retrying costs only time here: a credential failure makes no
retailer requests at all, so eight retries of it spend nothing. The one
exception is a usage error - argparse exits 2 - which will be wrong in exactly
the same way eight more times. That is consistent with the existing decision in
`cli.py` to let an argparse refusal fail loudly the first time a job is
deployed.

**A bot challenge is also not retried.** `AccessChallenge` means the retailer
said no, and the standing position in `CLAUDE.md` is that such a route is
unavailable and that is reported rather than worked around. Retrying a refusal
on a schedule is working around it, so the supervisor stops and reports. This
is the one place classification is worth the coupling, and it is done by
reading the collector's own stderr marker rather than by inventing an exit
code, so the collector's contract is unchanged.
"""

import os
import shlex
import signal
import subprocess
import sys
import time
from dataclasses import dataclass, field


# Time the supervisor leaves between its own last action and the replica
# timeout, so it can write its report and exit rather than being killed
# mid-sentence. Separate from the collector's own publish headroom, which is
# inside each attempt's budget.
SUPERVISOR_EXIT_HEADROOM_SECONDS = 120

# An attempt shorter than this cannot reach the retailer, resolve a store and
# publish, so starting one would burn an attempt to no purpose. When the window
# cannot fit this much, the supervisor stops early and says so.
MIN_ATTEMPT_SECONDS = 300

DEFAULT_RETRY_ATTEMPTS = 8
DEFAULT_RETRY_INTERVAL_SECONDS = 900

# Printed on the final-failure path whether or not email is configured, so an
# Azure Monitor log alert can match it without any credential being baked into
# the image. Named in azure/README.md.
ALERT_MARKER = 'MARIANOS_RUN_FAILED_AFTER_RETRIES'

# Usage error. argparse exits 2 and so does the entrypoint's own validation;
# both will fail identically on every retry.
USAGE_EXIT_CODE = 2

# The collector logs this when the retailer served a bot challenge. Retrying a
# refusal on a schedule is working around it, which this repository does not do
# by any name.
CHALLENGE_MARKERS = ('AccessChallenge', 'AccessBlocked')


@dataclass
class RetryPlan:
    """How many times to retry and how long to wait, with the arithmetic.

    `attempts` counts retries *after* the first run, matching how the
    instruction was phrased: one run plus eight retries is nine attempts.
    """

    attempts: int = DEFAULT_RETRY_ATTEMPTS
    interval_seconds: int = DEFAULT_RETRY_INTERVAL_SECONDS
    collector_headroom_seconds: int = 900
    min_attempt_seconds: int = MIN_ATTEMPT_SECONDS

    def __post_init__(self):
        if self.attempts < 0:
            raise ValueError('retry attempts cannot be negative')
        if self.attempts and self.interval_seconds <= 0:
            raise ValueError('retry interval must be positive')

    @property
    def total_runs(self) -> int:
        return self.attempts + 1

    def waiting_seconds(self) -> int:
        """Time spent waiting, if every retry is used."""
        return self.attempts * self.interval_seconds

    def minimum_timeout_for_full_plan(self) -> int:
        """The smallest replica timeout that can still reach the last retry.

        Every attempt gets at least `min_attempt_seconds`, so this is the
        timeout below which the plan is guaranteed to stop early. It is the
        figure `deploy_jobs.sh` refuses a deployment against.
        """
        return (self.waiting_seconds()
                + self.total_runs * self.min_attempt_seconds
                + self.collector_headroom_seconds
                + SUPERVISOR_EXIT_HEADROOM_SECONDS)

    def timeout_for_full_budget_plan(self, collector_budget: int) -> int:
        """The timeout needed for every attempt to get a full-length run.

        Reported rather than enforced. Guaranteeing nine full sweeps plus two
        hours of waiting needs a replica timeout in the tens of thousands of
        seconds, and Microsoft's own jobs reference states no maximum for
        `replicaTimeout` - only that it is a required int - so this repository
        does not assert a ceiling it cannot evidence. The operator sees the
        figure and decides.
        """
        return (self.waiting_seconds()
                + self.total_runs * collector_budget
                + SUPERVISOR_EXIT_HEADROOM_SECONDS)


@dataclass
class Attempt:
    number: int
    budget_seconds: int
    exit_code: int = None
    elapsed_seconds: float = 0.0
    note: str = ''


@dataclass
class Outcome:
    succeeded: bool
    attempts: list = field(default_factory=list)
    stopped_early: str = ''
    notified: str = ''

    @property
    def exit_code(self) -> int:
        return 0 if self.succeeded else 1

    def summary(self) -> dict:
        return {
            'succeeded': self.succeeded,
            'runs': len(self.attempts),
            'stopped_early': self.stopped_early,
            'notified': self.notified,
            'attempts': [
                {'number': a.number, 'budget_seconds': a.budget_seconds,
                 'exit_code': a.exit_code,
                 'elapsed_seconds': round(a.elapsed_seconds, 1),
                 'note': a.note}
                for a in self.attempts
            ],
        }


def plan_from_environment(collector_headroom_seconds: int = 900) -> RetryPlan:
    """The plan the operator deployed, read from the environment.

    `deploy_jobs.sh` resolves these once, validates the plan against the
    replica timeout it is about to deploy, and forwards the same figures it
    validated, so the plan checked at deploy time is the plan that runs.
    """
    def number(name, default):
        raw = os.getenv(name, '').strip()
        if not raw:
            return default
        try:
            return int(float(raw))
        except ValueError:
            raise ValueError(f'{name} must be a number, not {raw!r}')

    return RetryPlan(
        attempts=number('RETRY_ATTEMPTS', DEFAULT_RETRY_ATTEMPTS),
        interval_seconds=number('RETRY_INTERVAL_SECONDS',
                                DEFAULT_RETRY_INTERVAL_SECONDS),
        collector_headroom_seconds=collector_headroom_seconds,
    )


def _looks_like_challenge(text: str) -> bool:
    return any(marker in (text or '') for marker in CHALLENGE_MARKERS)


def supervise(build_argv, plan: RetryPlan, window_seconds: int,
              run=None, sleep=time.sleep, clock=time.monotonic,
              notify=None, log=print) -> Outcome:
    """Run the collector, retrying a failure on the plan, within the window.

    `build_argv(budget_seconds)` returns the argv for one attempt, so each
    attempt is given the time actually left rather than a figure fixed at
    startup. Everything with a side effect is injectable, so the tests drive
    nine attempts and two hours of waiting without a subprocess or a clock.

    `window_seconds` is the replica timeout minus the supervisor's own exit
    headroom: the time the supervisor may consume in total.
    """
    run = run or _run_subprocess
    notify = notify or send_failure_notice
    started = clock()
    outcome = Outcome(succeeded=False)

    for number in range(1, plan.total_runs + 1):
        remaining = window_seconds - (clock() - started)
        budget = int(remaining - plan.collector_headroom_seconds)
        if budget < plan.min_attempt_seconds:
            outcome.stopped_early = (
                f'window exhausted before attempt {number}: {int(remaining)}s '
                f'left, which is under the {plan.min_attempt_seconds}s an '
                f'attempt needs plus {plan.collector_headroom_seconds}s to '
                f'publish')
            log(f'retry_supervisor stopping early: {outcome.stopped_early}')
            break

        attempt = Attempt(number=number, budget_seconds=budget)
        log(f'retry_supervisor attempt {number} of {plan.total_runs}, '
            f'collector budget {budget}s')
        at = clock()
        code, captured = run(build_argv(budget))
        attempt.exit_code = code
        attempt.elapsed_seconds = clock() - at
        outcome.attempts.append(attempt)

        if code == 0:
            attempt.note = 'published'
            outcome.succeeded = True
            log(f'retry_supervisor attempt {number} succeeded')
            return outcome

        if code == USAGE_EXIT_CODE:
            attempt.note = 'usage error, not retried'
            outcome.stopped_early = (
                'usage error: the arguments or environment are wrong, so every '
                'retry would fail identically')
            log(f'retry_supervisor not retrying: {outcome.stopped_early}')
            break

        if _looks_like_challenge(captured):
            attempt.note = 'retailer served a bot challenge, not retried'
            outcome.stopped_early = (
                'the retailer served a bot challenge. The standing position is '
                'that such a route is unavailable and that is reported rather '
                'than worked around, and retrying a refusal on a schedule is '
                'working around it')
            log(f'retry_supervisor not retrying: {outcome.stopped_early}')
            break

        attempt.note = f'failed with exit {code}'
        if number == plan.total_runs:
            log('retry_supervisor exhausted every configured attempt')
            break

        remaining = window_seconds - (clock() - started)
        if remaining - plan.interval_seconds < (
                plan.min_attempt_seconds + plan.collector_headroom_seconds):
            outcome.stopped_early = (
                f'no room for another attempt after waiting '
                f'{plan.interval_seconds}s: {int(remaining)}s left in the '
                f'replica window')
            log(f'retry_supervisor stopping early: {outcome.stopped_early}')
            break

        log(f'retry_supervisor waiting {plan.interval_seconds}s before '
            f'attempt {number + 1}')
        sleep(plan.interval_seconds)

    outcome.notified = notify(outcome, log=log)
    return outcome


def _run_subprocess(argv):
    """Run one attempt, streaming its output and keeping a copy to classify.

    The child's output goes to the job's own log as it happens, because an
    unattended run that buffers its output for an hour tells the operator
    nothing while it is going wrong. A copy is kept so the bot-challenge marker
    can be read without parsing the log after the fact.
    """
    captured = []
    with subprocess.Popen(argv, stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, text=True,
                          bufsize=1) as child:
        _forward_signals_to(child)
        for line in child.stdout:
            sys.stdout.write(line)
            sys.stdout.flush()
            captured.append(line)
        code = child.wait()
    return code, ''.join(captured[-200:])


def _forward_signals_to(child):
    """Pass a graceful stop on to the collector rather than orphaning it.

    An Azure replica timeout is a SIGKILL and nothing can be done about that,
    which is the whole reason the budget exists. But a SIGTERM - a manual stop,
    or a platform drain - is catchable, and the collector should be allowed to
    refuse its run and write its own record rather than being abandoned by a
    parent that exited first.
    """
    def handler(signum, _frame):
        try:
            child.send_signal(signum)
        except ProcessLookupError:
            pass

    for signum in (signal.SIGTERM, signal.SIGINT):
        try:
            signal.signal(signum, handler)
        except (ValueError, OSError):
            pass        # not the main thread, as in the tests


def send_failure_notice(outcome: Outcome, log=print, smtp=None) -> str:
    """Report a final failure, by email when the operator configured one.

    **The credential stays with its owner.** `CLAUDE.md`'s standing rule is
    that credentials are never baked in and never pasted here; these come from
    the environment, which `deploy_jobs.sh` fills from Azure secrets the
    operator sets. Nothing in this repository holds an SMTP password.

    When email is not configured the marker line is still printed, because the
    credential-free way to get an alert out of a Container Apps job is an Azure
    Monitor log alert matching a string in the job's log. That is the default,
    and it is documented rather than silently substituted: the return value
    says which happened, and it reaches the run summary.
    """
    body = _notice_body(outcome)
    log(f'{ALERT_MARKER} {_one_line(outcome)}')

    host = os.getenv('SMTP_HOST', '').strip()
    to = [a.strip() for a in os.getenv('ALERT_EMAIL_TO', '').split(',') if a.strip()]
    if not host or not to:
        missing = ' and '.join(
            n for n, v in (('SMTP_HOST', host), ('ALERT_EMAIL_TO', to)) if not v)
        log(f'retry_supervisor: no email sent, {missing} not set. The marker '
            f'line above is what an Azure Monitor log alert matches.')
        return f'log_marker_only ({missing} not set)'

    try:
        _send_email(host, to, body, smtp=smtp)
    except Exception as exc:                        # noqa: BLE001
        # A failed notification must never replace the failure it reports, and
        # must never be the thing that decides the exit code. Same rule the
        # refusal recorder follows.
        log(f'retry_supervisor: email to {", ".join(to)} failed: '
            f'{type(exc).__name__}: {exc}. The marker line above stands.')
        return f'email_failed ({type(exc).__name__})'
    log(f'retry_supervisor: failure email sent to {", ".join(to)}')
    return f'email_sent to {", ".join(to)}'


def _one_line(outcome: Outcome) -> str:
    runs = len(outcome.attempts)
    codes = ','.join(str(a.exit_code) for a in outcome.attempts)
    tail = f' stopped_early={outcome.stopped_early!r}' if outcome.stopped_early else ''
    return (f'store={os.getenv("MARIANOS_STORE_ID", "") or "unset"} '
            f'source={os.getenv("MARIANOS_SOURCE", "") or "unset"} '
            f'runs={runs} exit_codes={codes}{tail}')


def _notice_body(outcome: Outcome) -> str:
    lines = [
        "A scheduled Mariano's collection run failed and was not recovered by "
        'its retries.',
        '',
        f'Store:      {os.getenv("MARIANOS_STORE_ID", "") or "unset"}',
        f'Source:     {os.getenv("MARIANOS_SOURCE", "") or "unset"}',
        f'Attempts:   {len(outcome.attempts)}',
    ]
    if outcome.stopped_early:
        lines += ['', f'Stopped before the full plan: {outcome.stopped_early}']
    lines += ['', 'Per attempt:']
    for a in outcome.attempts:
        lines.append(f'  {a.number}. exit {a.exit_code} after '
                     f'{a.elapsed_seconds:.0f}s of a {a.budget_seconds}s '
                     f'budget - {a.note}')
    lines += [
        '',
        'Nothing was published and the latest pointer is unchanged. The refused',
        'attempt is recorded under failures/<namespace>/<store>/ with the reason',
        'verbatim; read that rather than this summary for the cause.',
        '',
        'The next scheduled run is unaffected. Azure fires the cron expression',
        'independently of how long an execution takes, and the retry plan is',
        'bounded to finish inside one replica timeout, which the deployment',
        'refuses unless it is shorter than the gap between firings.',
    ]
    return '\n'.join(lines)


def _send_email(host, to, body, smtp=None):
    """Send over SMTP. Separated so a test can inject a transport."""
    import smtplib
    from email.message import EmailMessage

    port = int(os.getenv('SMTP_PORT', '587'))
    user = os.getenv('SMTP_USERNAME', '').strip()
    password = os.getenv('SMTP_PASSWORD', '')
    sender = os.getenv('ALERT_EMAIL_FROM', '').strip() or user or 'noreply@localhost'

    message = EmailMessage()
    message['Subject'] = (
        f'[Marianos] scheduled run failed after retries '
        f'(store {os.getenv("MARIANOS_STORE_ID", "") or "unset"})')
    message['From'] = sender
    message['To'] = ', '.join(to)
    message.set_content(body)

    if smtp is not None:
        smtp(message, host=host, port=port, user=user, password=password)
        return
    with smtplib.SMTP(host, port, timeout=60) as server:
        server.starttls()
        if user:
            server.login(user, password)
        server.send_message(message)


def describe(plan: RetryPlan, replica_timeout: int, collector_budget: int,
             shortest_gap_seconds: int = None) -> dict:
    """What this plan does with this timeout. Used by the deploy check."""
    minimum = plan.minimum_timeout_for_full_plan()
    out = {
        'retry_attempts': plan.attempts,
        'retry_interval_seconds': plan.interval_seconds,
        'total_runs': plan.total_runs,
        'waiting_seconds_if_all_used': plan.waiting_seconds(),
        'replica_timeout': replica_timeout,
        'minimum_timeout_for_all_attempts': minimum,
        'all_attempts_reachable': replica_timeout >= minimum,
        'timeout_for_full_length_attempts':
            plan.timeout_for_full_budget_plan(collector_budget),
        '_first_attempt_budget': (
            'The first attempt gets the whole window. Retries get what it '
            'leaves, so a run that exhausts its budget is not retried.'),
    }
    if shortest_gap_seconds is not None:
        out['shortest_gap_between_firings_seconds'] = shortest_gap_seconds
        out['finishes_before_the_next_firing'] = replica_timeout < shortest_gap_seconds
    return out


def main(build_argv, replica_timeout: int, collector_headroom_seconds: int,
         argv_for_non_run=None) -> int:
    """Entry point used by the container entrypoint.

    `argv_for_non_run`, when given, is run once with no retry plan at all. The
    `list` command is not a run: it must not retry and must not leave a failure
    notice, the same separation `cli.py` already makes between `run` and the
    commands that are not runs.
    """
    if argv_for_non_run is not None:
        print(f'retry_supervisor: not a run, executing once: '
              f'{shlex.join(argv_for_non_run)}')
        code, _ = _run_subprocess(argv_for_non_run)
        return code

    plan = plan_from_environment(collector_headroom_seconds)
    window = replica_timeout - SUPERVISOR_EXIT_HEADROOM_SECONDS
    if window <= collector_headroom_seconds:
        raise ValueError(
            f'replica timeout {replica_timeout}s leaves no room for a single '
            f'attempt: {SUPERVISOR_EXIT_HEADROOM_SECONDS}s of supervisor '
            f'headroom plus {collector_headroom_seconds}s for the collector to '
            f'publish already exceeds it')

    outcome = supervise(build_argv, plan, window)
    print('retry_supervisor summary:', outcome.summary())
    return outcome.exit_code
