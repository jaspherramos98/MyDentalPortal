# File: MyDentalPortal/blueprints/routes/clinics.py
# Clinic management routes. Clinic management is OWNER-only (clinic_repo.*_owned);
# linked staff work in a dentist's clinics but never manage them.

from flask import (
    Blueprint, render_template, request, session,
    redirect, url_for, flash,
)
from datetime import datetime
import traceback

from blueprints.utils import login_required, role_required, ROLE_DENTIST, audit
from blueprints.repositories import clinics as clinic_repo
from blueprints.repositories import patients as patient_repo

clinics_bp = Blueprint('clinics', __name__)

# The currencies the clinic forms offer. Anything else falls back to the default.
CURRENCIES = ('PHP', 'USD')
DEFAULT_CURRENCY = 'PHP'


def _clinic_fields(form):
    """The editable clinic fields from a submitted form, trimmed + validated."""
    currency = form.get('currency', DEFAULT_CURRENCY)
    return {
        'name': (form.get('name') or '').strip(),
        'address': (form.get('address') or '').strip(),
        'phone': (form.get('phone') or '').strip(),
        'email': (form.get('email') or '').strip().lower(),
        'operating_hours': (form.get('operating_hours') or '').strip(),
        'currency': currency if currency in CURRENCIES else DEFAULT_CURRENCY,
    }


@clinics_bp.route('/clinics')
@login_required
def list_clinics():
    search_query = request.args.get('search', '')
    try:
        clinics = clinic_repo.search_owned(session['user_id'], search_query)
        counts = patient_repo.active_counts_by_clinic([c['_id'] for c in clinics])
        for clinic in clinics:
            clinic['patient_count'] = counts.get(clinic['_id'], 0)
        return render_template('clinics/list.html', clinics=clinics,
                               search_query=search_query)
    except Exception as e:
        print(f"[ERROR] Clinics list: {e}")
        traceback.print_exc()
        flash('Error loading clinics', 'error')
        return render_template('clinics/list.html', clinics=[], search_query='')


@clinics_bp.route('/clinics/create', methods=['GET', 'POST'])
@role_required(ROLE_DENTIST)  # clinic management is dentist/admin only (staff can't)
def create_clinic():
    if request.method == 'POST':
        fields = _clinic_fields(request.form)
        if not fields['name']:
            flash('Clinic name is required', 'error')
            return render_template('clinics/create.html')
        try:
            now = datetime.utcnow()
            clinic_id = clinic_repo.insert(dict(
                fields, owner_id=session['user_id'], is_active=True,
                created_at=now, updated_at=now,
            ))
            audit('create', 'clinic', clinic_id, dentist_id=session['user_id'])
            flash(f'Clinic "{fields["name"]}" created successfully!', 'success')
            return redirect(url_for('clinics.list_clinics'))
        except Exception as e:
            print(f"[ERROR] Create clinic: {e}")
            traceback.print_exc()
            flash('Error creating clinic', 'error')

    return render_template('clinics/create.html')


@clinics_bp.route('/clinics/<clinic_id>/edit', methods=['GET', 'POST'])
@role_required(ROLE_DENTIST)  # clinic settings = dentist/admin only
def edit_clinic(clinic_id):
    try:
        clinic = clinic_repo.get_owned(clinic_id, session['user_id'])
        if not clinic:
            flash('Clinic not found', 'error')
            return redirect(url_for('clinics.list_clinics'))

        if request.method == 'POST':
            fields = _clinic_fields(request.form)
            if not fields['name']:
                flash('Clinic name is required', 'error')
                return render_template('clinics/edit.html', clinic=clinic)
            clinic_repo.update_owned(clinic['_id'], session['user_id'], fields)
            audit('update', 'clinic', clinic['_id'], clinic=clinic)
            flash('Clinic updated successfully!', 'success')
            return redirect(url_for('clinics.list_clinics'))

        return render_template('clinics/edit.html', clinic=clinic)
    except Exception as e:
        print(f"[ERROR] Edit clinic: {e}")
        traceback.print_exc()
        flash('Error editing clinic', 'error')
        return redirect(url_for('clinics.list_clinics'))


@clinics_bp.route('/clinics/<clinic_id>/delete', methods=['POST'])
@role_required(ROLE_DENTIST)  # clinic management is dentist/admin only
def delete_clinic(clinic_id):
    try:
        # Audit + success only when the caller really owned (and removed) it —
        # a rejected attempt must not show up as a delete in the owner's log.
        if clinic_repo.deactivate_owned(clinic_id, session['user_id']):
            audit('delete', 'clinic', clinic_id, dentist_id=session['user_id'])
            flash('Clinic deleted successfully', 'success')
        else:
            flash('Clinic not found', 'error')
    except Exception as e:
        print(f"[ERROR] Delete clinic: {e}")
        traceback.print_exc()
        flash('Error deleting clinic', 'error')
    return redirect(url_for('clinics.list_clinics'))
