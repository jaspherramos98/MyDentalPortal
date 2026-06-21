# File: MyDentalPortal/blueprints/routes/admin.py
# Admin-only screens. Currently: review + approve/reject new registrations.

from flask import (
    Blueprint, render_template, redirect, url_for,
    session, flash, abort, request,
)
from werkzeug.security import generate_password_hash
from bson.objectid import ObjectId
from bson.errors import InvalidId
from datetime import datetime

from blueprints.utils import admin_required, ROLE_DENTIST, ROLE_STAFF, ROLE_ADMIN
from blueprints.repositories import users as user_repo
from blueprints.repositories import memberships as membership_repo
from blueprints.repositories import audit_log as audit_repo

admin_bp = Blueprint('admin', __name__)


def _audit_admin(action, entity_type, entity_id):
    """Best-effort audit of an admin action (never breaks the request)."""
    try:
        audit_repo.record(action, entity_type, entity_id,
                          actor_user_id=session.get('user_id'), actor_role='admin')
    except Exception as e:  # noqa: BLE001
        print(f"[ERROR] admin audit failed: {e}")


@admin_bp.route('/admin/registrations')
@admin_required
def registrations():
    pending = user_repo.list_by_status('pending')
    return render_template('admin/registrations.html', pending=pending)


@admin_bp.route('/admin/registrations/<user_id>/approve', methods=['POST'])
@admin_required
def approve(user_id):
    try:
        oid = ObjectId(user_id)
    except (InvalidId, TypeError):
        abort(404)
    user_repo.set_status_if_pending(
        oid, 'approved',
        {'updated_at': datetime.utcnow(), 'approved_by': session['user_id']},
    )
    flash('Account approved — the user can now log in.', 'success')
    return redirect(url_for('admin.registrations'))


@admin_bp.route('/admin/registrations/<user_id>/reject', methods=['POST'])
@admin_required
def reject(user_id):
    try:
        oid = ObjectId(user_id)
    except (InvalidId, TypeError):
        abort(404)
    user_repo.set_status_if_pending(
        oid, 'rejected',
        {'updated_at': datetime.utcnow(), 'rejected_by': session['user_id']},
    )
    flash('Registration rejected.', 'warning')
    return redirect(url_for('admin.registrations'))


# ── USER MANAGEMENT ──────────────────────────────────────────────────────
@admin_bp.route('/admin/users')
@admin_required
def users():
    """List all accounts (admin handles password resets manually — no email flow)."""
    all_users = user_repo.list_all_no_password()
    return render_template('admin/users.html', users=all_users)


@admin_bp.route('/admin/users/<user_id>/reset-password', methods=['POST'])
@admin_required
def reset_password(user_id):
    try:
        oid = ObjectId(user_id)
    except (InvalidId, TypeError):
        abort(404)

    new_password = request.form.get('new_password') or ''
    if len(new_password) < 8:
        flash('New password must be at least 8 characters long.', 'error')
        return redirect(url_for('admin.users'))

    result = user_repo.update_set(oid, {
        'password': generate_password_hash(new_password),
        'updated_at': datetime.utcnow(),
        'password_reset_by': session['user_id'],
    })
    if result.matched_count:
        flash('Password reset. Share the new password with the user securely.', 'success')
    else:
        flash('User not found.', 'error')
    return redirect(url_for('admin.users'))


# ── ADMIN PANEL: dentists -> their linked staff + role/lifecycle mgmt ─────────
@admin_bp.route('/admin/panel')
@admin_required
def panel():
    """Every dentist (and admin) with the staff linked to them, plus role +
    lifecycle controls. The app-admin's superset view."""
    all_users = user_repo.list_all_no_password()
    by_id = {str(u['_id']): u for u in all_users}
    rows = []
    for d in all_users:
        if d.get('role') not in (ROLE_DENTIST, ROLE_ADMIN):
            continue
        staff = []
        for m in membership_repo.list_for_dentist(str(d['_id'])):
            su = by_id.get(m['user_id'])
            if su:
                staff.append({'user': su, 'membership_id': str(m['_id'])})
        rows.append({'dentist': d, 'staff': staff})
    return render_template('admin/panel.html', rows=rows)


@admin_bp.route('/admin/users/<user_id>/active', methods=['POST'])
@admin_required
def set_active(user_id):
    """Activate / deactivate an account (lifecycle)."""
    if user_id == session['user_id']:
        flash("You can't change your own account's active state.", 'error')
        return redirect(url_for('admin.panel'))
    active = request.form.get('active') == '1'
    result = user_repo.update_set(user_id, {
        'is_active': active, 'updated_at': datetime.utcnow(),
    })
    if result.matched_count:
        _audit_admin('activate' if active else 'deactivate', 'user', user_id)
        flash('Account ' + ('activated.' if active else 'deactivated.'), 'success')
    else:
        flash('User not found.', 'error')
    return redirect(url_for('admin.panel'))


@admin_bp.route('/admin/users/<user_id>/role', methods=['POST'])
@admin_required
def set_role(user_id):
    """Change a user's role (promote to dentist, grant/revoke admin, etc.)."""
    new_role = request.form.get('role')
    if new_role not in (ROLE_DENTIST, ROLE_STAFF, ROLE_ADMIN):
        flash('Invalid role.', 'error')
        return redirect(url_for('admin.panel'))
    # Don't let an admin strip their own admin rights (avoids self-lockout).
    if user_id == session['user_id'] and new_role != ROLE_ADMIN:
        flash("You can't change your own admin role.", 'error')
        return redirect(url_for('admin.panel'))
    result = user_repo.update_set(user_id, {
        'role': new_role, 'updated_at': datetime.utcnow(),
    })
    if result.matched_count:
        _audit_admin('set_role', 'user', user_id)
        flash(f'Role updated to {new_role}.', 'success')
    else:
        flash('User not found.', 'error')
    return redirect(url_for('admin.panel'))


@admin_bp.route('/admin/memberships/<membership_id>/revoke', methods=['POST'])
@admin_required
def revoke_membership(membership_id):
    """Unlink a staff member from a dentist."""
    result = membership_repo.revoke_by_id(membership_id)
    if result and result.modified_count:
        _audit_admin('revoke_membership', 'membership', membership_id)
        flash('Staff unlinked from the dentist.', 'success')
    else:
        flash('Membership not found or already revoked.', 'error')
    return redirect(url_for('admin.panel'))
