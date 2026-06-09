# File: MyDentalPortal/blueprints/routes/patients.py
# Patient management routes — matches PDA paper form fields exactly

from flask import (
    Blueprint, render_template, request, session,
    redirect, url_for, flash, jsonify,
)
from bson.objectid import ObjectId
from datetime import datetime
import traceback

from extensions import mongo
from blueprints.utils import login_required, user_clinic_ids as _get_user_clinic_ids

patients_bp = Blueprint('patients', __name__)


def _ensure_nested(patient):
    """Ensure all nested dicts exist so templates don't crash on missing keys."""
    # Every nested dict the detail/list templates may access — keep this in
    # sync with templates so a patient missing any section never 500s.
    top_level = (
        'personal_info', 'contact_info', 'emergency_contact', 'dental_history',
        'medical_history', 'referral_info', 'guardian_info', 'minor_info',
        'insurance_info',
    )
    for key in top_level:
        if key not in patient or not isinstance(patient[key], dict):
            patient[key] = {}

    # medical_history sub-dicts used by the template.
    mh = patient['medical_history']
    for sub in ('allergies', 'women_health', 'medical_conditions',
                'general_health', 'physician_info', 'vital_signs'):
        if sub not in mh or not isinstance(mh.get(sub), dict):
            mh[sub] = {}
    return patient


# ── LIST ─────────────────────────────────────────────────────────────────
@patients_bp.route('/patients')
@login_required
def list_patients():
    try:
        user_clinics = list(
            mongo.db.clinics.find({'owner_id': session['user_id'], 'is_active': True})
        )
        clinic_ids = [c['_id'] for c in user_clinics]

        search_query = request.args.get('search', '')
        clinic_filter = request.args.get('clinic_id', '')

        query = {'is_active': True}
        if clinic_filter:
            query['clinic_id'] = ObjectId(clinic_filter)
        else:
            query['clinic_id'] = {'$in': clinic_ids}

        if search_query:
            query['$or'] = [
                {'personal_info.first_name': {'$regex': search_query, '$options': 'i'}},
                {'personal_info.last_name': {'$regex': search_query, '$options': 'i'}},
                {'personal_info.nickname': {'$regex': search_query, '$options': 'i'}},
                {'contact_info.cell_phone': {'$regex': search_query, '$options': 'i'}},
            ]

        page = max(1, request.args.get('page', 1, type=int))
        per_page = 20
        total = mongo.db.patients.count_documents(query)
        total_pages = max(1, (total + per_page - 1) // per_page)

        patients = list(
            mongo.db.patients.find(query)
            .sort('created_at', -1)
            .skip((page - 1) * per_page)
            .limit(per_page)
        )

        # Ensure nested dicts for safe template access
        for p in patients:
            _ensure_nested(p)

        return render_template(
            'patients/list.html',
            patients=patients,
            clinics=user_clinics,
            current_page=page,
            total_pages=total_pages,
            selected_clinic=clinic_filter,
            search_query=search_query,
        )
    except Exception as e:
        print(f"[ERROR] Patients list: {e}")
        traceback.print_exc()
        flash('Error loading patients', 'error')
        return render_template(
            'patients/list.html',
            patients=[], clinics=[],
            current_page=1, total_pages=1,
            selected_clinic=None, search_query='',
        )


# ── CREATE ───────────────────────────────────────────────────────────────
@patients_bp.route('/patients/create', methods=['GET', 'POST'])
@login_required
def create_patient():
    user_clinics = list(
        mongo.db.clinics.find({'owner_id': session['user_id'], 'is_active': True})
    )

    if not user_clinics:
        flash('Please create a clinic first before adding patients.', 'warning')
        return redirect(url_for('clinics.create_clinic'))

    if request.method == 'POST':
        f = request.form
        try:
            patient_data = {
                'clinic_id': ObjectId(f.get('clinic_id')),
                'personal_info': {
                    'first_name': (f.get('first_name') or '').strip(),
                    'last_name': (f.get('last_name') or '').strip(),
                    'middle_name': (f.get('middle_name') or '').strip(),
                    'nickname': (f.get('nickname') or '').strip(),
                    'gender': f.get('gender', ''),
                    'birthday': f.get('birthday', ''),
                    'age': f.get('age', ''),
                    'religion': (f.get('religion') or '').strip(),
                    'nationality': (f.get('nationality') or '').strip(),
                    'occupation': (f.get('occupation') or '').strip(),
                },
                'contact_info': {
                    'home_address': (f.get('home_address') or '').strip(),
                    'landline': (f.get('landline') or '').strip(),
                    'cell_phone': (f.get('cell_phone') or '').strip(),
                    'office_number': (f.get('office_number') or '').strip(),
                    'email': (f.get('patient_email') or '').strip().lower(),
                },
                'insurance_info': {
                    'dental_insurance': (f.get('dental_insurance') or '').strip(),
                },
                'minor_info': {
                    'guardian_name': (f.get('guardian_name') or '').strip(),
                    'guardian_occupation': (f.get('guardian_occupation') or '').strip(),
                },
                'referral_info': {
                    'referred_by': (f.get('referred_by') or '').strip(),
                    'consultation_reason': (f.get('consultation_reason') or '').strip(),
                },
                'dental_history': {
                    'previous_dentist': (f.get('previous_dentist') or '').strip(),
                    'last_visit': (f.get('last_dental_visit') or '').strip(),
                },
                'medical_history': {
                    'physician_name': (f.get('physician_name') or '').strip(),
                    'physician_specialty': (f.get('physician_specialty') or '').strip(),
                    'physician_address': (f.get('physician_address') or '').strip(),
                    'q1_good_health': f.get('q1_good_health', 'no'),
                    'q2_under_treatment': f.get('q2_under_treatment', 'no'),
                    'q2_condition': (f.get('q2_condition') or '').strip(),
                    'q3_serious_illness': f.get('q3_serious_illness', 'no'),
                    'q3_illness_detail': (f.get('q3_illness_detail') or '').strip(),
                    'q4_hospitalized': f.get('q4_hospitalized', 'no'),
                    'q4_hospitalized_detail': (f.get('q4_hospitalized_detail') or '').strip(),
                    'q5_medications': f.get('q5_medications', 'no'),
                    'q5_medications_detail': (f.get('q5_medications_detail') or '').strip(),
                    'q6_tobacco': f.get('q6_tobacco', 'no'),
                    'q7_dangerous_drugs': f.get('q7_dangerous_drugs', 'no'),
                    'allergies': {
                        'local_anesthesia': 'allergy_local_anesthesia' in f,
                        'penicillin': 'allergy_penicillin' in f,
                        'antibiotics': 'allergy_antibiotics' in f,
                        'sulfa_drugs': 'allergy_sulfa_drugs' in f,
                        'aspirin': 'allergy_aspirin' in f,
                        'latex': 'allergy_latex' in f,
                        'other': (f.get('allergy_other') or '').strip(),
                    },
                    'women_health': {
                        'pregnant': f.get('q9_pregnant', 'no'),
                        'nursing': f.get('q9_nursing', 'no'),
                        'birth_control': f.get('q9_birth_control', 'no'),
                    },
                    'conditions': {
                        'high_blood_pressure': 'cond_high_bp' in f,
                        'low_blood_pressure': 'cond_low_bp' in f,
                        'epilepsy_convulsions': 'cond_epilepsy' in f,
                        'aids_hiv': 'cond_aids_hiv' in f,
                        'std': 'cond_std' in f,
                        'stomach_troubles_ulcer': 'cond_stomach' in f,
                        'fainting_seizures': 'cond_fainting' in f,
                        'rapid_weight_loss': 'cond_weight_loss' in f,
                        'radiation_therapy': 'cond_radiation' in f,
                        'joint_replacement': 'cond_joint_replacement' in f,
                        'heart_surgery': 'cond_heart_surgery' in f,
                        'heart_attack': 'cond_heart_attack' in f,
                        'thyroid_problem': 'cond_thyroid' in f,
                        'heart_disease': 'cond_heart_disease' in f,
                        'heart_murmur': 'cond_heart_murmur' in f,
                        'hepatitis_liver': 'cond_hepatitis_liver' in f,
                        'rheumatic_fever': 'cond_rheumatic_fever' in f,
                        'allergies': 'cond_allergies' in f,
                        'respiratory_disease': 'cond_respiratory' in f,
                        'hepatitis_jaundice': 'cond_hepatitis_jaundice' in f,
                        'tuberculosis': 'cond_tuberculosis' in f,
                        'swollen_ankles': 'cond_swollen_ankles' in f,
                        'kidney_disease': 'cond_kidney' in f,
                        'diabetes': 'cond_diabetes' in f,
                        'chest_pain': 'cond_chest_pain' in f,
                        'stroke': 'cond_stroke' in f,
                        'cancer_tumors': 'cond_cancer' in f,
                        'anemia': 'cond_anemia' in f,
                        'angina': 'cond_angina' in f,
                        'asthma': 'cond_asthma' in f,
                        'emphysema': 'cond_emphysema' in f,
                        'bleeding_problems': 'cond_bleeding' in f,
                        'blood_disease': 'cond_blood_disease' in f,
                        'head_injuries': 'cond_head_injuries' in f,
                        'arthritis_rheumatism': 'cond_arthritis' in f,
                        'other': (f.get('cond_other') or '').strip(),
                    },
                    'blood_pressure': (f.get('blood_pressure') or '').strip(),
                    'current_medications': (f.get('current_medications') or '').strip(),
                },
                'created_by': session['user_id'],
                'created_at': datetime.utcnow(),
                'updated_at': datetime.utcnow(),
                'is_active': True,
            }

            if not patient_data['personal_info']['first_name']:
                flash('First name is required', 'error')
                return render_template('patients/create.html',
                                       clinics=user_clinics, form_data=f)
            if not patient_data['personal_info']['last_name']:
                flash('Last name is required', 'error')
                return render_template('patients/create.html',
                                       clinics=user_clinics, form_data=f)

            result = mongo.db.patients.insert_one(patient_data)
            flash('Patient created successfully!', 'success')
            return redirect(url_for('patients.patient_detail',
                                    patient_id=str(result.inserted_id)))

        except Exception as e:
            print(f"[ERROR] Create patient: {e}")
            traceback.print_exc()
            flash(f'Error creating patient record: {e}', 'error')
            return render_template('patients/create.html',
                                   clinics=user_clinics, form_data=f)

    return render_template('patients/create.html',
                           clinics=user_clinics, form_data={})


# ── DETAIL ───────────────────────────────────────────────────────────────
@patients_bp.route('/patients/<patient_id>')
@login_required
def patient_detail(patient_id):
    try:
        print(f"[DEBUG] Loading patient: {patient_id}")

        patient = mongo.db.patients.find_one({'_id': ObjectId(patient_id)})
        if not patient:
            print(f"[ERROR] Patient not found: {patient_id}")
            flash('Patient not found', 'error')
            return redirect(url_for('patients.list_patients'))

        print(f"[DEBUG] Patient found: {patient.get('personal_info', {}).get('first_name', '?')}")
        print(f"[DEBUG] Patient clinic_id: {patient.get('clinic_id')} (type: {type(patient.get('clinic_id'))})")

        # Look up clinic — try owner_id match first, fall back to just _id
        clinic = mongo.db.clinics.find_one({
            '_id': patient['clinic_id'],
            'owner_id': session['user_id'],
        })
        if not clinic:
            # Maybe clinic_id is stored as string in old data
            clinic = mongo.db.clinics.find_one({'_id': patient['clinic_id']})
            if not clinic:
                print(f"[ERROR] Clinic not found for patient. clinic_id={patient.get('clinic_id')}")
                flash('Clinic not found for this patient', 'error')
                return redirect(url_for('patients.list_patients'))
            print(f"[DEBUG] Clinic found (owner mismatch, allowing): {clinic['name']}")

        # Ensure nested dicts
        _ensure_nested(patient)

        dental_chart = mongo.db.dental_charts.find_one(
            {'patient_id': ObjectId(patient_id)}
        )
        treatment_records = list(
            mongo.db.treatment_records.find({'patient_id': ObjectId(patient_id)})
            .sort('date', -1).limit(20)
        )
        patient_appointments = list(
            mongo.db.appointments.find({
                'patient_id': ObjectId(patient_id),
                'is_active': True,
            }).sort([('date', -1), ('time', -1)]).limit(10)
        )
        prescriptions = list(
            mongo.db.prescriptions.find({'patient_id': ObjectId(patient_id)})
            .sort('created_at', -1)
        )
        patient_files = list(
            mongo.db.patient_files.find({'patient_id': ObjectId(patient_id)})
            .sort('created_at', -1)
        )

        print(f"[DEBUG] Rendering patient detail OK")
        return render_template(
            'patients/detail.html',
            patient=patient,
            clinic=clinic,
            dental_chart=dental_chart,
            treatment_records=treatment_records,
            appointments=patient_appointments,
            prescriptions=prescriptions,
            patient_files=patient_files,
        )
    except Exception as e:
        print(f"[ERROR] Patient detail failed: {e}")
        traceback.print_exc()
        flash(f'Error loading patient details: {e}', 'error')
        return redirect(url_for('patients.list_patients'))


# ── EDIT ─────────────────────────────────────────────────────────────────
@patients_bp.route('/patients/<patient_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_patient(patient_id):
    try:
        patient = mongo.db.patients.find_one({'_id': ObjectId(patient_id)})
        if not patient:
            flash('Patient not found', 'error')
            return redirect(url_for('patients.list_patients'))

        _ensure_nested(patient)

        clinic = mongo.db.clinics.find_one({'_id': patient['clinic_id']})
        if not clinic:
            flash('Clinic not found', 'error')
            return redirect(url_for('patients.list_patients'))

        user_clinics = list(
            mongo.db.clinics.find({'owner_id': session['user_id'], 'is_active': True})
        )

        if request.method == 'POST':
            f = request.form
            update_data = {
                'personal_info.first_name': (f.get('first_name') or '').strip(),
                'personal_info.last_name': (f.get('last_name') or '').strip(),
                'personal_info.middle_name': (f.get('middle_name') or '').strip(),
                'personal_info.nickname': (f.get('nickname') or '').strip(),
                'personal_info.gender': f.get('gender', ''),
                'personal_info.birthday': f.get('birthday', ''),
                'personal_info.age': f.get('age', ''),
                'personal_info.religion': (f.get('religion') or '').strip(),
                'personal_info.nationality': (f.get('nationality') or '').strip(),
                'personal_info.occupation': (f.get('occupation') or '').strip(),
                'contact_info.home_address': (f.get('home_address') or '').strip(),
                'contact_info.landline': (f.get('landline') or '').strip(),
                'contact_info.cell_phone': (f.get('cell_phone') or '').strip(),
                'contact_info.office_number': (f.get('office_number') or '').strip(),
                'contact_info.email': (f.get('patient_email') or '').strip().lower(),
                'emergency_contact.name': (f.get('emergency_name') or '').strip(),
                'emergency_contact.relationship': (f.get('emergency_relationship') or '').strip(),
                'emergency_contact.phone': (f.get('emergency_phone') or '').strip(),
                'insurance_info.dental_insurance': (f.get('dental_insurance') or '').strip(),
                'updated_at': datetime.utcnow(),
            }
            mongo.db.patients.update_one(
                {'_id': ObjectId(patient_id)},
                {'$set': update_data},
            )
            flash('Patient updated successfully!', 'success')
            return redirect(url_for('patients.patient_detail', patient_id=patient_id))

        return render_template('patients/edit.html',
                               patient=patient, clinics=user_clinics, clinic=clinic)
    except Exception as e:
        print(f"[ERROR] Edit patient: {e}")
        traceback.print_exc()
        flash(f'Error editing patient: {e}', 'error')
        return redirect(url_for('patients.list_patients'))


# ── DELETE (soft) ────────────────────────────────────────────────────────
@patients_bp.route('/patients/<patient_id>/delete', methods=['POST'])
@login_required
def delete_patient(patient_id):
    try:
        patient = mongo.db.patients.find_one({'_id': ObjectId(patient_id)})
        if patient:
            mongo.db.patients.update_one(
                {'_id': ObjectId(patient_id)},
                {'$set': {'is_active': False, 'updated_at': datetime.utcnow()}},
            )
            flash('Patient record deleted', 'success')
        else:
            flash('Patient not found', 'error')
    except Exception as e:
        print(f"[ERROR] Delete patient: {e}")
        traceback.print_exc()
        flash(f'Error deleting patient: {e}', 'error')
    return redirect(url_for('patients.list_patients'))
