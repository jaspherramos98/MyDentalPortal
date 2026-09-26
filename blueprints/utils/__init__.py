# File: MyDentalPortal/blueprints/utils/__init__.py
# Shared cross-cutting helpers for auth and access control.
#
# These used to be copy-pasted into every blueprint. Centralising them gives a
# single source of truth — important for security, since access-control logic
# must behave identically everywhere.

import time
from functools import wraps

from flask import (
    session, redirect, url_for, current_app, abort, request, jsonify, flash,
)

from blueprints.repositories import patients as _patient_repo
from blueprints.repositories import clinics as _clinic_repo
from blueprints.repositories import audit_log as _audit_repo


# Role vocabulary. App Admin is a global superset; Dentist owns clinics; Staff
# (assistant/receptionist) is the constrained role multi-staff will introduce.
ROLE_ADMIN = 'admin'
ROLE_DENTIST = 'dentist'
ROLE_STAFF = 'staff'


# Header sent by static/js/resilient-submit.js. It asks for JSON outcomes
# instead of redirects: with fetch(), "the response was a redirect" can't tell
# a successful save apart from a bounce to /login (idle timeout) or back to the
# form (expired CSRF). Treating every redirect as success loses the typed form.
RESILIENT_SUBMIT_HEADER = 'X-Resilient-Submit'


def wants_json_submit():
    """True when the request came from the resilient-submit client."""
    return request.headers.get(RESILIENT_SUBMIT_HEADER) == '1'


def session_expired_response():
    """401 JSON for a resilient-submit request that has no live session."""
    return jsonify({'ok': False, 'error': 'session_expired'}), 401


def enforce_idle_timeout():
    """before_request hook: log a user out after IDLE_TIMEOUT_SECONDS of inactivity.

    Each request refreshes the activity stamp; once the gap exceeds the timeout
    the session is cleared and the user is bounced to login. PHI shouldn't stay
    open on an unattended machine. Static assets don't reset the timer. A
    resilient-submit request gets a 401 JSON instead of the redirect, so the
    open form keeps what was typed.
    """
    timeout = current_app.config.get('IDLE_TIMEOUT_SECONDS') or 0
    if 'user_id' not in session or timeout <= 0:
        return None
    if request.endpoint == 'static':
        return None
    now = int(time.time())
    last = session.get('last_activity')
    if last is not None and now - last > timeout:
        session.clear()
        if wants_json_submit():
            return session_expired_response()
        flash('You were signed out due to inactivity.', 'info')
        return redirect(url_for('auth.login'))
    session.permanent = True
    session['last_activity'] = now
    return None


def login_required(f):
    """Redirect to login if there is no authenticated session."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            if wants_json_submit():
                return session_expired_response()
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated


def user_clinic_ids():
    """ObjectIds of the active clinics the current user may work in.

    Owned clinics (dentist) PLUS clinics owned by any dentist the user is a staff
    member of. The multi-staff listing seam.
    """
    return _clinic_repo.accessible_ids(session['user_id'])


def verify_patient_access(patient_id):
    """Return (patient, clinic) only if the current user may access the patient.

    Access = the patient's clinic is owned by the user (dentist) or by a dentist
    the user is a staff member of. Returns (None, None) for a missing/invalid id;
    (patient, None) for a patient the user may not access — the caller must treat
    a None clinic as access denied. Delegates to the patients repository (the
    multi-staff access seam).
    """
    return _patient_repo.get_for_accessor(patient_id, session['user_id'])


def is_admin():
    """True if the logged-in user is an administrator."""
    email = (session.get('user_email') or '').lower()
    return (
        email in current_app.config.get('ADMIN_EMAILS', [])
        or session.get('user_role') == 'admin'
    )


def admin_required(f):
    """Require an authenticated administrator; 403 otherwise."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('auth.login'))
        if not is_admin():
            abort(403)
        return f(*args, **kwargs)
    return decorated


def current_role():
    """The logged-in user's role (defaults to dentist for legacy sessions)."""
    return session.get('user_role', ROLE_DENTIST)


def role_required(*roles):
    """Require an authenticated user whose role is in `roles`; 403 otherwise.

    Admins implicitly satisfy any role requirement (they are a global superset).
    This is the multi-staff foundation: future staff-restricted routes declare
    e.g. @role_required(ROLE_DENTIST) and staff get a 403.
    """
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if 'user_id' not in session:
                return redirect(url_for('auth.login'))
            if is_admin() or current_role() in roles:
                return f(*args, **kwargs)
            abort(403)
        return decorated
    return decorator


def audit(action, entity_type, entity_id=None, clinic=None, dentist_id=None):
    """Best-effort audit-log write, attributed to the current session user.

    Pass the ``clinic`` dict (as returned by ``verify_patient_access``) and the
    owning dentist + clinic_id are derived from it for the nested viewer. NEVER
    pass PHI — only the action + identifiers are stored (see audit_log repo).

    Deliberately swallows errors: an audit-log failure must not break the user's
    actual action. A failure is printed (and so reaches Sentry-adjacent logs).
    """
    try:
        clinic_id = None
        if clinic is not None:
            clinic_id = clinic.get('_id')
            dentist_id = dentist_id or clinic.get('owner_id')
        _audit_repo.record(
            action, entity_type, entity_id,
            actor_user_id=session.get('user_id'),
            actor_role=session.get('user_role', ROLE_DENTIST),
            clinic_id=clinic_id, dentist_id=dentist_id,
        )
    except Exception as e:  # noqa: BLE001 - audit must never break the request
        print(f"[ERROR] audit log write failed: {e}")
