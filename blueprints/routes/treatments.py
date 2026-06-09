# File: MyDentalPortal/app/routes/treatments.py
# Treatment record routes — scalable design for future additions

from flask import (
    Blueprint, render_template, request, jsonify,
    session, redirect, url_for, flash,
)
from bson.objectid import ObjectId
from datetime import datetime
import traceback

from extensions import mongo
from blueprints.utils import login_required, verify_patient_access as _verify_patient_access

treatments_bp = Blueprint('treatments', __name__)


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

            mongo.db.treatment_records.insert_one(treatment)
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
        treatment = mongo.db.treatment_records.find_one({'_id': ObjectId(treatment_id)})
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
            mongo.db.treatment_records.update_one(
                {'_id': ObjectId(treatment_id)},
                {'$set': update},
            )
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


# ── DELETE TREATMENT ─────────────────────────────────────────────────────
@treatments_bp.route('/treatments/<treatment_id>/delete', methods=['POST'])
@login_required
def delete_treatment(treatment_id):
    try:
        treatment = mongo.db.treatment_records.find_one({'_id': ObjectId(treatment_id)})
        if treatment:
            patient, clinic = _verify_patient_access(str(treatment['patient_id']))
            if clinic:
                mongo.db.treatment_records.delete_one({'_id': ObjectId(treatment_id)})
                flash('Treatment record deleted', 'success')
                return redirect(url_for('patients.patient_detail',
                                        patient_id=str(treatment['patient_id'])))
        flash('Access denied or treatment not found', 'error')
    except Exception as e:
        print(f"Delete treatment error: {e}")
        flash('Error deleting treatment', 'error')
    return redirect(url_for('patients.list_patients'))


# ── JSON API (for AJAX calls from patient detail page) ───────────────────
@treatments_bp.route('/api/patients/<patient_id>/treatments')
@login_required
def get_treatments_api(patient_id):
    """Return treatments as JSON for dynamic loading."""
    patient, clinic = _verify_patient_access(patient_id)
    if not clinic:
        return jsonify({'error': 'Access denied'}), 403

    treatments = list(
        mongo.db.treatment_records.find({'patient_id': ObjectId(patient_id)})
        .sort('date', -1)
    )
    for t in treatments:
        t['_id'] = str(t['_id'])
        t['patient_id'] = str(t['patient_id'])
        t['clinic_id'] = str(t['clinic_id'])
        for k in ('created_at', 'updated_at'):
            if k in t and hasattr(t[k], 'isoformat'):
                t[k] = t[k].isoformat()

    return jsonify({'treatments': treatments})
