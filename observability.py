# File: MyDentalPortal/observability.py
# Error tracking (Sentry) — prod-only, PHI-safe.
#
# This app stores patient health data (PHI). Sentry is configured to capture
# unhandled exceptions for off-box debugging WITHOUT ever shipping patient data
# to a third party. The hard safety choices:
#   * No DSN set  -> Sentry is completely disabled (local/dev/showcase stay
#     silent; only the Render prod host sets SENTRY_DSN). Opt-in by env var.
#   * include_local_variables=False -> stack-frame locals (which routinely hold
#     a `patient` dict full of medical history) are NEVER captured.
#   * max_request_body_size='never' + send_default_pii=False -> request bodies,
#     cookies, and client IP are never sent.
#   * before_send strips anything PHI-bearing that could still ride along
#     (query strings can contain patient-name searches; cookies carry the
#     session). The URL *path* is kept (ObjectId ids aid debugging, not PHI).

import os


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
    # Never attach a user identity (we don't set one, but be defensive).
    event.pop('user', None)
    return event


def init_sentry():
    """Initialise Sentry iff SENTRY_DSN is set. Returns True if enabled.

    Safe to call unconditionally at startup: with no DSN it is a no-op, so
    dev/local/showcase need no Sentry dependency wiring beyond the package.
    """
    dsn = (os.environ.get('SENTRY_DSN') or '').strip()
    if not dsn:
        return False

    # Imported lazily so the package is only needed where Sentry is actually
    # enabled (and import errors don't take the app down on hosts without it).
    import sentry_sdk

    sentry_sdk.init(
        dsn=dsn,
        environment=os.environ.get('FLASK_ENV', 'production'),
        # --- PHI safety (see module docstring) ---
        send_default_pii=False,
        include_local_variables=False,
        max_request_body_size='never',
        before_send=_scrub_phi,
        # Errors only — no performance tracing (keeps us in the free tier and
        # avoids per-request overhead). Raise later if perf insight is needed.
        traces_sample_rate=0.0,
    )
    return True
