# File: MyDentalPortal/blueprints/utils/__init__.py
# Shared cross-cutting helpers for auth and access control.
#
# These used to be copy-pasted into every blueprint. Centralising them gives a
# single source of truth — important for security, since access-control logic
# must behave identically everywhere.

from functools import wraps

from flask import session, redirect, url_for, current_app, abort

from blueprints.repositories import patients as _patient_repo
from blueprints.repositories import clinics as _clinic_repo


def login_required(f):
    """Redirect to login if there is no authenticated session."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated


def user_clinic_ids():
    """ObjectIds of the active clinics owned by the current user."""
    return _clinic_repo.owned_ids(session['user_id'])


def verify_patient_access(patient_id):
    """Return (patient, clinic) only if the current user owns the patient's clinic.

    Returns (None, None) for a missing/invalid id; (patient, None) for a patient
    in someone else's clinic — the caller must treat a None clinic as access
    denied. Delegates to the patients repository (the multi-staff access seam).
    """
    return _patient_repo.get_for_owner(patient_id, session['user_id'])


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
