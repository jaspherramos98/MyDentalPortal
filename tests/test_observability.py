"""PHI-safe logging + Sentry scrubbing (observability.py).

The rule under test: exception TYPES and stack frames may leave the request;
exception MESSAGES (which routinely carry emails, names, form values) may not.
"""
import logging

from observability import (
    REDACTED, PhiSafeFormatter, _scrub_phi, configure_logging, redacted_traceback,
)

PHI = "Alicemarker jane.doe@example.com 0917-555-0000"
# Kept out of the raise lines: tracebacks print source lines (code), and the
# test must only see what the formatter itself emits.
DUP_KEY_MSG = "E11000 duplicate key { email: \"jane.doe@example.com\" } " + PHI


def _raise_chained():
    try:
        try:
            raise KeyError(PHI)
        except KeyError as inner:
            raise RuntimeError("outer " + PHI) from inner
    except RuntimeError as exc:
        return exc


def test_redacted_traceback_keeps_frames_and_types_but_no_messages():
    text = redacted_traceback(_raise_chained())
    assert PHI not in text and "jane.doe" not in text
    assert "builtins.KeyError: " + REDACTED in text
    assert "builtins.RuntimeError: " + REDACTED in text
    assert "direct cause" in text
    assert "test_observability.py" in text          # frames survive for debugging


def test_implicit_context_is_redacted_too():
    try:
        try:
            raise ValueError(PHI)
        except ValueError:
            raise TypeError(PHI)                    # implicit __context__
    except TypeError as exc:
        text = redacted_traceback(exc)
    assert PHI not in text and "During handling" in text


def test_formatter_redacts_log_exception_output():
    record = logging.LogRecord("t", logging.ERROR, __file__, 1, "Create patient failed",
                               None, None)
    exc = _raise_chained()
    record.exc_info = (type(exc), exc, exc.__traceback__)
    out = PhiSafeFormatter("%(levelname)s %(message)s").format(record)
    assert out.startswith("ERROR Create patient failed")
    assert PHI not in out and REDACTED in out


def test_formatter_ignores_unredacted_cache_from_other_handlers():
    """logging caches exc_text on the record; another handler formatting first
    must not make ours print its unredacted copy."""
    exc = _raise_chained()
    record = logging.LogRecord("t", logging.ERROR, __file__, 1, "failed", None,
                               (type(exc), exc, exc.__traceback__))
    logging.Formatter().format(record)                 # plain formatter caches exc_text
    assert PHI in record.exc_text
    assert PHI not in PhiSafeFormatter().format(record)


def test_configure_logging_is_idempotent():
    configure_logging()
    configure_logging()
    root = logging.getLogger()
    assert sum(type(h).__name__ == "_StdoutHandler" for h in root.handlers) == 1


def test_sentry_scrub_redacts_exception_values():
    event = {"exception": {"values": [{"type": "KeyError", "value": PHI}]},
             "request": {"data": "x", "query_string": "search=" + PHI, "cookies": "s",
                         "headers": {"User-Agent": "UA", "X-Forwarded-For": "1.2.3.4"}},
             "user": {"id": "u"}}
    out = _scrub_phi(event, None)
    assert out["exception"]["values"][0] == {"type": "KeyError", "value": REDACTED}
    assert "data" not in out["request"] and "query_string" not in out["request"]
    assert out["request"]["headers"] == {"User-Agent": "UA"}
    assert "user" not in out


def test_route_error_logs_traceback_without_phi(real_client, as_user, world, capsys, monkeypatch):
    """End to end: a route crash whose exception text holds PHI logs the
    failure + traceback, but not the text."""
    from blueprints.repositories import patients as patient_repo

    def boom(*_a, **_k):
        raise RuntimeError(DUP_KEY_MSG)
    monkeypatch.setattr(patient_repo, "search_active_page", boom)
    as_user("dentist")
    real_client.get("/patients")
    out = capsys.readouterr().out
    assert "Patients list failed" in out and "Traceback" in out
    assert "jane.doe@example.com" not in out and "Alicemarker" not in out
