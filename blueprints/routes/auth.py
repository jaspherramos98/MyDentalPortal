# File: MyDentalPortal/app/routes/auth.py
# Authentication routes — login, register, logout

from flask import (
    Blueprint, request, jsonify, session,
    render_template, redirect, url_for, flash,
)
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import re

from extensions import limiter
from blueprints.repositories import users as user_repo
from blueprints.repositories import audit_log as audit_repo

auth_bp = Blueprint('auth', __name__)


def _audit_auth(action, user=None):
    """Best-effort auth audit entry. Stores the acted-on account id + role, never
    the raw email/password. Never raises — auth must not break on a log failure."""
    try:
        uid = str(user['_id']) if user else None
        audit_repo.record(
            action, 'auth', entity_id=uid,
            actor_user_id=uid, actor_role=(user or {}).get('role'),
        )
    except Exception as e:  # noqa: BLE001
        print(f"[ERROR] auth audit failed: {e}")

# Pre-computed hash so failed logins stay roughly constant-time: we always run a
# password check even when the email doesn't exist, so a missing account can't be
# detected by a faster response (user-enumeration defense).
_DUMMY_PASSWORD_HASH = generate_password_hash('unused-constant-time-placeholder')


# ── helpers ──────────────────────────────────────────────────────────────
def _valid_email(email):
    return bool(re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email))


def account_block_reason(user):
    """Return (flash_category, message) if `user` may NOT log in, else None.

    Lifecycle gate, enforced after the password check. Legacy accounts created
    before these fields existed have no `status`/`is_active` and are grandfathered
    in as active+approved. Anything not explicitly approved is denied by default.
    """
    if user.get('is_active') is False:
        return ('error', 'Your account has been deactivated. Please contact the clinic.')
    status = user.get('status', 'approved')
    if status == 'pending':
        return ('warning', 'Your account is awaiting administrator approval.')
    if status == 'rejected':
        return ('error', 'Your registration was not approved. Please contact the clinic.')
    if status != 'approved':
        # Any other lifecycle state (e.g. suspended) is blocked by default.
        return ('error', 'Your account is not active. Please contact the clinic.')
    return None


# ── routes ───────────────────────────────────────────────────────────────
@auth_bp.route('/login', methods=['GET', 'POST'])
@limiter.limit(
    '10 per minute; 50 per hour',
    methods=['POST'],
    error_message='Too many login attempts. Please wait a minute and try again.',
)
def login():
    if request.method == 'POST':
        data = request.get_json() if request.is_json else request.form
        email = (data.get('email') or '').strip().lower()
        password = data.get('password') or ''

        if not email or not password:
            flash('Email and password are required', 'error')
            return render_template('auth/login.html')

        try:
            user = user_repo.get_by_email(email)
            # Always hash-check (against a dummy hash if no such user) for constant time.
            stored_hash = user['password'] if user else _DUMMY_PASSWORD_HASH
            if check_password_hash(stored_hash, password) and user:
                # Account lifecycle gate (approval + active/deactivated).
                block = account_block_reason(user)
                if block:
                    _audit_auth('login_failed', user)  # correct password, blocked account
                    flash(block[1], block[0])
                    return render_template('auth/login.html')

                session['user_id'] = str(user['_id'])
                session['user_email'] = user['email']
                session['user_name'] = user['name']
                session['user_role'] = user.get('role', 'dentist')
                session.permanent = True

                _audit_auth('login', user)
                if request.is_json:
                    return jsonify({'success': True, 'redirect': url_for('main.dashboard')})
                flash('Login successful!', 'success')
                return redirect(url_for('main.dashboard'))

            _audit_auth('login_failed', user)  # user is None for an unknown email
            flash('Invalid email or password', 'error')
        except Exception as e:
            print(f"Login error: {e}")
            flash('Login failed. Please try again.', 'error')

        return render_template('auth/login.html')

    # GET
    if 'user_id' in session:
        return redirect(url_for('main.dashboard'))
    return render_template('auth/login.html')


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        data = request.get_json() if request.is_json else request.form

        name = (data.get('name') or '').strip()
        email = (data.get('email') or '').strip().lower()
        password = data.get('password') or ''
        confirm_password = data.get('confirm_password') or ''
        license_number = (data.get('license_number') or '').strip()
        specialty = (data.get('specialty') or '').strip()

        # Validation
        if not all([name, email, password, license_number]):
            flash('Please fill in all required fields', 'error')
            return render_template('auth/register.html')
        if password != confirm_password:
            flash('Passwords do not match', 'error')
            return render_template('auth/register.html')
        if len(password) < 8:
            flash('Password must be at least 8 characters long', 'error')
            return render_template('auth/register.html')
        if not _valid_email(email):
            flash('Invalid email address', 'error')
            return render_template('auth/register.html')

        try:
            if user_repo.get_by_email(email):
                flash('Email already registered', 'error')
                return render_template('auth/register.html')

            user_data = {
                'name': name,
                'email': email,
                'password': generate_password_hash(password),
                'license_number': license_number,
                'specialty': specialty,
                'role': 'dentist',           # future: admin, staff
                'status': 'pending',         # must be approved by an admin
                'created_at': datetime.utcnow(),
                'updated_at': datetime.utcnow(),
                'is_active': True,
            }
            user_repo.create(user_data)

            if request.is_json:
                return jsonify({'success': True, 'pending': True})
            flash('Registration submitted. An administrator must approve your '
                  'account before you can log in.', 'success')
            return redirect(url_for('auth.login'))

        except Exception as e:
            print(f"Registration error: {e}")
            flash('Registration failed. Please try again.', 'error')
            return render_template('auth/register.html')

    # GET
    if 'user_id' in session:
        return redirect(url_for('main.dashboard'))
    return render_template('auth/register.html')


@auth_bp.route('/logout', methods=['POST'])
def logout():
    # POST + CSRF token so a malicious page can't force-logout a user.
    uid = session.get('user_id')
    if uid:
        try:
            audit_repo.record('logout', 'auth', entity_id=uid, actor_user_id=uid,
                              actor_role=session.get('user_role'))
        except Exception as e:  # noqa: BLE001
            print(f"[ERROR] auth audit failed: {e}")
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('auth.login'))
