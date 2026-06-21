# File: MyDentalPortal/blueprints/routes/staff.py
# Staff management for a dentist: generate single-use access codes and view/revoke
# them, and see the staff currently linked to this dentist. Dentist/admin only.
#
# The staff *registration* side (consuming a code) lives in auth.py (it's a public
# flow). This blueprint is the dentist's side of onboarding.

from flask import (
    Blueprint, render_template, request, session, redirect, url_for, flash,
)

from blueprints.utils import role_required, ROLE_DENTIST, audit
from blueprints.repositories import access_codes as code_repo
from blueprints.repositories import memberships as membership_repo
from blueprints.repositories import users as user_repo

staff_bp = Blueprint('staff', __name__)


@staff_bp.route('/staff')
@role_required(ROLE_DENTIST)
def list_staff():
    dentist_id = session['user_id']
    # Resolve each membership to a (name/email) for display.
    staff = []
    for m in membership_repo.list_for_dentist(dentist_id):
        u = user_repo.get(m['user_id'])
        if u:
            staff.append({
                'name': u.get('name', ''),
                'email': u.get('email', ''),
                'role': m.get('role', 'staff'),
                'user_id': m['user_id'],
            })
    codes = code_repo.list_for_dentist(dentist_id)
    return render_template('staff/list.html', staff=staff, codes=codes)


@staff_bp.route('/staff/codes/generate', methods=['POST'])
@role_required(ROLE_DENTIST)
def generate_code():
    dentist_id = session['user_id']
    code = code_repo.generate(dentist_id, created_by=dentist_id)
    audit('generate', 'access_code', dentist_id=dentist_id)
    # Shown ONCE — it's only stored hashed and can't be retrieved again.
    flash(f'Staff access code (copy it now, it won\'t be shown again): {code}', 'success')
    return redirect(url_for('staff.list_staff'))


@staff_bp.route('/staff/codes/<code_id>/revoke', methods=['POST'])
@role_required(ROLE_DENTIST)
def revoke_code(code_id):
    dentist_id = session['user_id']
    result = code_repo.revoke(code_id, dentist_id)
    if result and result.modified_count:
        audit('revoke', 'access_code', code_id, dentist_id=dentist_id)
        flash('Access code revoked.', 'success')
    else:
        flash('Code not found, already used, or already revoked.', 'error')
    return redirect(url_for('staff.list_staff'))
