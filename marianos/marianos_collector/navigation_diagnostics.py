"""Small allowlisted navigation evidence; never collect payloads or headers."""
from copy import deepcopy
import re
import time
from urllib.parse import urlsplit

class NavigationDiagnostics:
    MAX_EVENTS = 32

    def __init__(self, page, version, clock=time.monotonic):
        self.page = page
        self.version = version if isinstance(version, str) and re.fullmatch(r"[0-9]{1,4}(?:\.[0-9]{1,4}){1,3}", version) else "unknown"
        self.clock = clock
        self.started = clock()
        self.events = []
        self.dropped = 0
        self.handlers = {"request": self.request, "response": self.response, "requestfailed": self.failed}

    @staticmethod
    def target(url):
        try:
            parsed = urlsplit(url)
            if parsed.scheme == "https" and parsed.hostname in ("marianos.com", "www.marianos.com"):
                return "https://" + parsed.hostname + "/[path-redacted]"
        except (ValueError, TypeError):
            pass
        return "[external-or-invalid]"

    def _record(self, event, request, **fields):
        # Observability must never interrupt collection or replace its original failure.
        try:
            if not request.is_navigation_request() or request.frame != self.page.main_frame:
                return
            if len(self.events) >= self.MAX_EVENTS:
                self.dropped = min(self.dropped + 1, 2147483647)
                return
            elapsed = min(86400000, max(0, int((self.clock() - self.started) * 1000)))
            self.events.append(dict(event=event, elapsed_ms=elapsed, target=self.target(request.url), **fields))
        except Exception:
            return

    def request(self, request):
        self._record("request", request)

    def response(self, response):
        try:
            status = response.status
            if type(status) is int and 100 <= status <= 599:
                self._record("response", response.request, status=status)
        except Exception:
            return

    def failed(self, request):
        try:
            failure = request.failure
            match = re.search(r"\bnet::ERR_[A-Z0-9_]{1,80}\b", failure or "")
            self._record("requestfailed", request, error_code=match.group() if match else "REQUEST_FAILED")
        except Exception:
            return

    def attach(self):
        for name, handler in self.handlers.items():
            self.page.on(name, handler)

    def detach(self):
        for name, handler in self.handlers.items():
            try:
                self.page.remove_listener(name, handler)
            except Exception:
                pass

    def snapshot(self):
        return {"browser_version": self.version, "events": deepcopy(self.events), "dropped_events": self.dropped,
                "scope": "main_frame_during_browser_setup", "max_events": self.MAX_EVENTS}
