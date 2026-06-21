# File: MyDentalPortal/app/routes/treatments.py
# Treatment record routes — scalable design for future additions

from flask import (
    Blueprint, render_template, request, jsonify,
    session, redirect, url_for, flash,
)
from bson.objectid import ObjectId
from datetime import datetime
import traceback

from blueprints.utils import (
    login_required, verify_patient_access as _verify_patient_access,
    role_required, ROLE_DENTIST, ROLE_STAFF, is_admin,
    user_clinic_ids as _user_clinic_ids, audit,
)
from blueprints.repositories import treatments as treatment_repo
from blueprints.repositories import patients as patient_repo

treatments_bp = Blueprint('treatments', __name__)


def _is_price_confirmer():
    """Dentist/admin may set a confirmed price; staff can only propose one."""
    return is_admin() or session.get('user_role') != ROLE_STAFF


# ── ADD TREATMENT ────────────────────────────────────────────────────────
@treatments_bp.route('/patients/<patient_id>/treatments/add', methods=['GET', 'POST'])
@login_required
def add_treatment(patient_id):
    patient, clinic = _verify_patient_access(patient_id)
    if not clinic:
        flash('Access denied or patient not found', 'error')
        return redirect(url_for('patients.list_patients'))

    if request.method == 'POST':
        f = request.form
        try:
            treatment = {
                'patient_id': ObjectId(patient_id),
                'clinic_id': clinic['_id'],
                'date': f.get('date') or datetime.utcnow().strftime('%Y-%m-%d'),
                'tooth_numbers': [
                    t.strip() for t in (f.get('tooth_numbers') or '').split(',')
                    if t.strip()
                ],
                'procedure': (f.get('procedure') or '').strip(),
                'description': (f.get('description') or '').strip(),
                'dentist': (f.get('dentist') or session.get('user_name', '')).strip(),
                'amount_charged': float(f.get('amount_charged') or 0),
                'amount_paid': float(f.get('amount_paid') or 0),
                'balance': (
                    float(f.get('amount_charged') or 0)
                    - float(f.get('amount_paid') or 0)
                ),
                'currency': clinic.get('currency', 'PHP'),
                'status': f.get('status', 'completed'),
                'notes': (f.get('notes') or '').strip(),
                'next_appointment': f.get('next_appointment', ''),
                'created_by': session['user_id'],
                'created_at': datetime.utcnow(),
                'updated_at': datetime.utcnow(),
            }

            # Price-confirmation: a dentist/admin's price is confirmed immediately;
            # a staff member's price is PENDING until a dentist confirms it.
            confirmer = _is_price_confirmer()
            treatment['price_set_by'] = session['user_id']
            treatment['price_confirmed'] = confirmer
            treatment['price_confirmed_by'] = session['user_id'] if confirmer else None
            treatment['price_confirmed_at'] = datetime.utcnow() if confirmer else None

            tid = treatment_repo.insert(treatment)
            audit('create', 'treatment', tid, clinic=clinic)
            if not confirmer:
                audit('price_proposed', 'treatment', tid, clinic=clinic)
            flash('Treatment record added successfully!', 'success')
            return redirect(url_for('patients.patient_detail', patient_id=patient_id))

        except Exception as e:
            print(f"[ERROR] Add treatment: {e}")
            traceback.print_exc()
            flash('Error adding treatment record', 'error')

    return render_template(
        'treatments/add.html',
        patient=patient,
        clinic=clinic,
    )


# ── EDIT TREATMENT ───────────────────────────────────────────────────────
@treatments_bp.route('/treatments/<treatment_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_treatment(treatment_id):
    try:
        treatment = treatment_repo.get(treatment_id)
        if not treatment:
            flash('Treatment not found', 'error')
            return redirect(url_for('patients.list_patients'))

        patient, clinic = _verify_patient_access(str(treatment['patient_id']))
        if not clinic:
            flash('Access denied', 'error')
            return redirect(url_for('patients.list_patients'))

        if request.method == 'POST':
            f = request.form
            update = {
                'date': f.get('date', treatment['date']),
                'tooth_numbers': [
                    t.strip() for t in (f.get('tooth_numbers') or '').split(',')
                    if t.strip()
                ],
                'procedure': (f.get('procedure') or '').strip(),
                'description': (f.get('description') or '').strip(),
                'dentist': (f.get('dentist') or '').strip(),
                'amount_charged': float(f.get('amount_charged') or 0),
                'amount_paid': float(f.get('amount_paid') or 0),
                'balance': (
                    float(f.get('amount_charged') or 0)
                    - float(f.get('amount_paid') or 0)
                ),
                'status': f.get('status', 'completed'),
                'notes': (f.get('notes') or '').strip(),
                'next_appointment': f.get('next_appointment', ''),
                'updated_at': datetime.utcnow(),
            }

            # Price-confirmation on edit: a dentist/admin save confirms the price;
            # a staff edit that CHANGES the amount re-opens it as pending (a staff
            # edit that leaves the amount alone doesn't touch confirmation state).
            confirmer = _is_price_confirmer()
            price_proposed = False
            if confirmer:
                update['price_confirmed'] = True
                update['price_confirmed_by'] = session['user_id']
                update['price_confirmed_at'] = datetime.utcnow()
            elif update['amount_charged'] != float(treatment.get('amount_charged') or 0):
                update['price_confirmed'] = False
                update['price_set_by'] = session['user_id']
                update['price_confirmed_by'] = None
                update['price_confirmed_at'] = None
                price_proposed = True

            treatment_repo.update_set(treatment_id, update)
            audit('update', 'treatment', treatment_id, clinic=clinic)
            if price_proposed:
                audit('price_proposed', 'treatment', treatment_id, clinic=clinic)
            flash('Treatment updated successfully!', 'success')
            return redirect(url_for('patients.patient_detail',
                                    patient_id=str(treatment['patient_id'])))

        return render_template(
            'treatments/edit.html',
            treatment=treatment, patient=patient, clinic=clinic,
        )
    except Exception as e:
        print(f"[ERROR] Edit treatment: {e}")
        traceback.print_exc()
        flash('Error editing treatment', 'error')
        return redirect(url_for('patients.list_patients'))


# ── MARK FULLY PAID ──────────────────────────────────────────────────────
@treatments_bp.route('/treatments/<treatment_id>/mark-paid', methods=['POST'])
@login_required
def mark_paid(treatment_id):
    """Clear a treatment's outstanding balance by setting amount_paid = charged."""
    try:
        treatment = treatment_repo.get(treatment_id)
        if treatment:
            patient, clinic = _verify_patient_access(str(treatment['patient_id']))
            if clinic:
                charged = float(treatment.get('amount_charged') or 0)
                treatment_repo.update_set(treatment_id, {
                    'amount_paid': charged,
                    'balance': 0.0,
                    'updated_at': datetime.utcnow(),
                })
                audit('mark_paid', 'treatment', treatment_id, clinic=clinic)
                flash('Treatment marked as fully paid.', 'success')
                return redirect(url_for('patients.patient_detail',
                                        patient_id=str(treatment['patient_id'])))
        flash('Access denied or treatment not found', 'error')
    except Exception as e:
        print(f"[ERROR] Mark paid: {e}")
        traceback.print_exc()
        flash('Error updating payment', 'error')
    return redirect(url_for('patients.list_patients'))


# ── DELETE TREATMENT ─────────────────────────────────────────────────────
@treatments_bp.route('/treatments/<treatment_id>/delete', methods=['POST'])
@role_required(ROLE_DENTIST)  # deleting a treatment record is dentist/admin only
def delete_treatment(treatment_id):
    try:
        treatment = treatment_repo.get(treatment_id)
        if treatment:
            patient, clinic = _verify_patient_access(str(treatment['patient_id']))
            if clinic:
                treatment_repo.delete(treatment_id)
                audit('delete', 'treatment', treatment_id, clinic=clinic)
                flash('Treatment record deleted', 'success')
                return redirect(url_for('patients.patient_detail',
                                        patient_id=str(treatment['patient_id'])))
        flash('Access denied or treatment not found', 'error')
    except Exception as e:
        print(f"Delete treatment error: {e}")
        flash('Error deleting treatment', 'error')
    return redirect(url_for('patients.list_patients'))


# ── PRICING: confirm a staff-proposed price ──────────────────────────────────
@treatments_bp.route('/treatments/<treatment_id>/confirm-price', methods=['POST'])
@role_required(ROLE_DENTIST)
def confirm_price(treatment_id):
    """Dentist/admin confirms a pending (staff-proposed) treatment price."""
    treatment = treatment_repo.get(treatment_id)
    if treatment:
        patient, clinic = _verify_patient_access(str(treatment['patient_id']))
        if clinic:
            treatment_repo.update_set(treatment_id, {
                'price_confirmed': True,
                'price_confirmed_by': session['user_id'],
                'price_confirmed_at': datetime.utcnow(),
            })
            audit('price_confirmed', 'treatment', treatment_id, clinic=clinic)
            flash('Price confirmed.', 'success')
            if request.form.get('from') == 'queue':
                return redirect(url_for('treatments.pending_prices'))
            return redirect(url_for('patients.patient_detail',
                                    patient_id=str(treatment['patient_id'])))
    flash('Access denied or treatment not found', 'error')
    return redirect(url_for('patients.list_patients'))


# ── PRICING: dentist/admin review queue of pending prices ─────────────────────
@treatments_bp.route('/treatments/pending-prices')
@role_required(ROLE_DENTIST)
def pending_prices():
    """Treatments awaiting price confirmation: dentist sees their clinics, admin
    sees all."""
    clinic_ids = None if is_admin() else _user_clinic_ids()
    rows = treatment_repo.find_pending_prices(clinic_ids)
    for r in rows:
        p = patient_repo.get(str(r.get('patient_id')))
        pi = (p or {}).get('personal_info', {})
        r['patient_name'] = f"{pi.get('first_name', '')} {pi.get('last_name', '')}".strip() or '—'
    return render_template('treatments/pending_prices.html', treatments=rows)


# ── JSON API (for AJAX calls from patient detail page) ───────────────────
@treatments_bp.route('/api/patients/<patient_id>/treatments')
@login_required
def get_treatments_api(patient_id):
    """Return treatments as JSON for dynamic loading."""
    patient, clinic = _verify_patient_access(patient_id)
    if not clinic:
        return jsonify({'error': 'Access denied'}), 403

    treatments = treatment_repo.list_for_patient(patient_id)
    for t in treatments:
        t['_id'] = str(t['_id'])
        t['patient_id'] = str(t['patient_id'])
        t['clinic_id'] = str(t['clinic_id'])
        for k in ('created_at', 'updated_at'):
            if k in t and hasattr(t[k], 'isoformat'):
                t[k] = t[k].isoformat()

    return jsonify({'treatments': treatments})
