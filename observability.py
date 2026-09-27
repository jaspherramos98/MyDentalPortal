# File: MyDentalPortal/observability.py
# Logging + error tracking (Sentry) — PHI-safe by construction.
#
# ONE rule for everything that leaves the request: exception TYPES and stack
# frames are fine, exception MESSAGES are not. Messages routinely carry data —
# a DuplicateKeyError names the duplicate email, a ValueError can echo a form
# value — so both the log formatter and the Sentry scrubber redact them.
# Log calls themselves use constant messages; interpolate ids only, never
# names, contact details, notes or form values.
#
# This app stores patient health data (PHI). Sentry is configured to capture
# unhandled exceptions for off-box debugging WITHOUT ever shipping patient data
# to a third party. The hard safety choices:
#   * No DSN set  -> Sentry is completely disabled (local/dev stay
#     silent; only the Render prod host sets SENTRY_DSN). Opt-in by env var.
#   * include_local_variables=False -> stack-frame locals (which routinely hold
#     a `patient` dict full of medical history) are NEVER captured.
#   * max_request_body_size='never' + send_default_pii=False -> request bodies,
#     cookies, and client IP are never sent.
#   * before_send strips anything PHI-bearing that could still ride along
#     (query strings can contain patient-name searches; cookies carry the
#     session). The URL *path* is kept (ObjectId ids aid debugging, not PHI).

import logging
import os
import sys
import traceback

REDACTED = '[message redacted]'


# ── Logging ──────────────────────────────────────────────────────────────────

def _exception_chain(exc):
    """The exception and its causes/contexts, oldest first (like a traceback)."""
    chain, seen = [], set()
    while exc is not None and id(exc) not in seen:
        seen.add(id(exc))
        chain.append(exc)
        exc = exc.__cause__ or (None if exc.__suppress_context__ else exc.__context__)
    return list(reversed(chain))


def redacted_traceback(exc):
    """A full traceback (files, lines, code) with every exception message removed."""
    parts = []
    chain = _exception_chain(exc)
    for i, e in enumerate(chain):
        if i:
            parts.append(
                '\nThe above exception was the direct cause of the following exception:\n\n'
                if e.__cause__ is chain[i - 1] else
                '\nDuring handling of the above exception, another exception occurred:\n\n'
            )
        parts.append('Traceback (most recent call last):\n')
        parts.extend(traceback.format_tb(e.__traceback__))
        parts.append(f'{type(e).__module__}.{type(e).__qualname__}: {REDACTED}\n')
    return ''.join(parts).rstrip('\n')


class PhiSafeFormatter(logging.Formatter):
    """Formatter that keeps tracebacks but never prints exception messages."""

    def format(self, record):
        # logging caches the formatted traceback on the record (exc_text). If any
        # other handler formatted it first, that cached text is UNREDACTED — so
        # always re-render through formatException, then restore the cache.
        cached = record.exc_text
        record.exc_text = None
        try:
            return super().format(record)
        finally:
            record.exc_text = cached

    def formatException(self, ei):
        return redacted_traceback(ei[1]) if ei and ei[1] is not None else ''


class _StdoutHandler(logging.StreamHandler):
    """StreamHandler bound to the *current* sys.stdout (Render reads stdout;
    resolving it per record also keeps pytest's output capture working)."""

    def emit(self, record):
        self.stream = sys.stdout
        super().emit(record)


_LOG_FORMAT = '%(asctime)s %(levelname)s %(name)s: %(message)s'


def configure_logging(level=logging.INFO):
    """Route the app's logs to stdout through the PHI-safe formatter. Idempotent."""
    root = logging.getLogger()
    if not any(isinstance(h, _StdoutHandler) for h in root.handlers):
        handler = _StdoutHandler()
        handler.setFormatter(PhiSafeFormatter(_LOG_FORMAT))
        root.addHandler(handler)
    root.setLevel(level)


# ── Sentry ───────────────────────────────────────────────────────────────────


# Keys whose values could carry PHI or auth material — scrubbed from every event.
# Header handling is allowlist, not blocklist: only these survive, everything
# else is dropped. This is deliberate — a blocklist misses things. It removes
# cookies + auth AND every client-IP header variant (X-Forwarded-For,
# Cf-Connecting-Ip, True-Client-IP, X-Real-IP, Forwarded, …) which are personal
# data under RA 10173. Kept headers are debugging-useful and carry no PII.
_SAFE_HEADERS = {
    'accept', 'accept-encoding', 'accept-language', 'content-type', 'user-agent',
}

# Request-environment keys that can hold the client IP — scrubbed too.
_SENSITIVE_ENV = {'REMOTE_ADDR'}


def _scrub_phi(event, hint):
    """before_send hook: drop request fields that could carry PHI/secrets."""
    request = event.get('request')
    if request:
        # Request body + query string can hold patient data (search terms,
        # form fields). Remove both outright.
        request.pop('data', None)
        request.pop('query_string', None)
        request.pop('cookies', None)
        # Allowlist headers — drop cookies, auth, and any client-IP header.
        headers = request.get('headers')
        if isinstance(headers, dict):
            for key in list(headers):
                if key.lower() not in _SAFE_HEADERS:
                    headers.pop(key, None)
        # Drop client IP from the WSGI environ if present.
        env = request.get('env')
        if isinstance(env, dict):
            for key in _SENSITIVE_ENV:
                env.pop(key, None)
    # Exception messages can carry PHI (see module header) — keep type + frames.
    for exc in (event.get('exception') or {}).get('values') or []:
        if exc.get('value'):
            exc['value'] = REDACTED
    # Never attach a user identity (we don't set one, but be defensive).
    event.pop('user', None)
    return event


def init_sentry():
    """Initialise Sentry iff SENTRY_DSN is set. Returns True if enabled.

    Safe to call unconditionally at startup: with no DSN it is a no-op, so
    dev/local need no Sentry dependency wiring beyond the package.
    """
    dsn = (os.environ.get('SENTRY_DSN') or '').strip()
    if not dsn:
        return False

    # Imported lazily so the package is only needed where Sentry is actually
    # enabled (and import errors don't take the app down on hosts without it).
    import sentry_sdk
    from sentry_sdk.integrations.logging import LoggingIntegration

    sentry_sdk.init(
        dsn=dsn,
        environment=os.environ.get('FLASK_ENV', 'production'),
        # --- PHI safety (see module docstring) ---
        send_default_pii=False,
        include_local_variables=False,
        max_request_body_size='never',
        before_send=_scrub_phi,
        # Logged (handled) errors stay on-box: log records become breadcrumbs
        # only, never Sentry events — only unhandled exceptions are reported.
        integrations=[LoggingIntegration(level=logging.INFO, event_level=None)],
        # Errors only — no performance tracing (keeps us in the free tier and
        # avoids per-request overhead). Raise later if perf insight is needed.
        traces_sample_rate=0.0,
    )
    return True
