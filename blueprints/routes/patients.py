# File: MyDentalPortal/blueprints/routes/patients.py
# Patient management routes — matches PDA paper form fields exactly

from flask import (
    Blueprint, render_template, request, session,
    redirect, url_for, flash, jsonify, send_file,
)
from bson.objectid import ObjectId
from datetime import datetime
import re
import traceback

from extensions import mongo
from blueprints.utils import (
    login_required, user_clinic_ids as _get_user_clinic_ids, verify_patient_access,
    role_required, ROLE_DENTIST, audit,
)
from blueprints.repositories import patients as patient_repo
from blueprints.repositories import clinics as clinic_repo
from werkzeug.utils import secure_filename

patients_bp = Blueprint('patients', __name__)

# _ensure_nested moved to the patients repository (blueprints/repositories/patients.py).
# Kept as a module-level alias for backward compatibility with existing call sites.
_ensure_nested = patient_repo.ensure_nested


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
            # Escape so the user's text is matched literally — never interpreted
            # as a regex (prevents ReDoS / regex injection against the DB).
            safe_q = re.escape(search_query)
            query['$or'] = [
                {'personal_info.first_name': {'$regex': safe_q, '$options': 'i'}},
                {'personal_info.last_name': {'$regex': safe_q, '$options': 'i'}},
                {'personal_info.nickname': {'$regex': safe_q, '$options': 'i'}},
                {'contact_info.cell_phone': {'$regex': safe_q, '$options': 'i'}},
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
    user_clinics = clinic_repo.accessible_active(session['user_id'])

    if not user_clinics:
        flash('Please create a clinic first before adding patients.', 'warning')
        return redirect(url_for('clinics.create_clinic'))

    if request.method == 'POST':
        f = request.form
        try:
            # NOTE: keys here are read from the create form's actual field names
            # (left side of f.get) and written to the canonical schema the detail
            # page reads (dict keys). Keep both sides in sync with create.html.
            patient_data = {
                'clinic_id': ObjectId(f.get('clinic_id')),
                'personal_info': {
                    'first_name': (f.get('first_name') or '').strip(),
                    'last_name': (f.get('last_name') or '').strip(),
                    'middle_name': (f.get('middle_name') or '').strip(),
                    'nickname': (f.get('nickname') or '').strip(),
                    'gender': f.get('gender', ''),
                    'birthday': f.get('birthdate', ''),
                    'age': f.get('age', ''),
                    'religion': (f.get('religion') or '').strip(),
                    'nationality': (f.get('nationality') or '').strip(),
                    'occupation': (f.get('occupation') or '').strip(),
                },
                'contact_info': {
                    'home_address': (f.get('home_address') or '').strip(),
                    'landline': (f.get('home_phone') or '').strip(),
                    'cell_phone': (f.get('cell_phone') or '').strip(),
                    'office_number': (f.get('office_phone') or '').strip(),
                    'email': (f.get('email') or '').strip().lower(),
                },
                'emergency_contact': {
                    'name': (f.get('emergency_name') or '').strip(),
                    'relationship': (f.get('emergency_relationship') or '').strip(),
                    'phone': (f.get('emergency_phone') or '').strip(),
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
                    'physician_address': (f.get('physician_phone') or '').strip(),
                    'q1_good_health': f.get('good_health', 'no'),
                    'q2_under_treatment': f.get('under_treatment', 'no'),
                    'q2_condition': (f.get('treatment_condition') or '').strip(),
                    'q6_tobacco': f.get('tobacco', 'no'),
                    'q7_dangerous_drugs': f.get('dangerous_drugs', 'no'),
                    'current_medications': (f.get('current_medications') or '').strip(),
                    'blood_type': (f.get('blood_type') or '').strip(),
                    'blood_pressure': (f.get('blood_pressure') or '').strip(),
                    'bleeding_time': (f.get('bleeding_time') or '').strip(),
                    'allergies': {
                        'local_anesthesia': 'allergy_anesthetic' in f,
                        'penicillin': 'allergy_penicillin' in f,
                        'sulfa_drugs': 'allergy_sulfa' in f,
                        'aspirin': 'allergy_aspirin' in f,
                        'latex': 'allergy_latex' in f,
                        'other': (f.get('allergy_others') or '').strip(),
                    },
                    'women_health': {
                        'pregnant': f.get('pregnant', 'no'),
                        'nursing': f.get('nursing', 'no'),
                        'birth_control': f.get('birth_control', 'no'),
                    },
                    'conditions': {
                        'high_blood_pressure': 'condition_high_blood_pressure' in f,
                        'heart_disease': 'condition_heart_disease' in f,
                        'diabetes': 'condition_diabetes' in f,
                        'asthma': 'condition_asthma' in f,
                        'cancer_tumors': 'condition_cancer_tumors' in f,
                        'heart_murmur': 'condition_heart_murmur' in f,
                        'epilepsy_convulsions': 'condition_epilepsy' in f,
                        'hepatitis_liver': 'condition_hepatitis_liver' in f,
                        'kidney_disease': 'condition_kidney_disease' in f,
                        'arthritis_rheumatism': 'condition_arthritis' in f,
                        'thyroid_problem': 'condition_thyroid_problem' in f,
                        'bleeding_problems': 'condition_bleeding_problems' in f,
                        'other': (f.get('condition_other') or '').strip(),
                    },
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

            # Access check: the posted clinic must be one the user may work in
            # (owned or via membership) — prevents creating a patient in another
            # dentist's clinic by tampering with the form's clinic_id.
            sel_clinic = clinic_repo.get_accessible(
                patient_data['clinic_id'], session['user_id']
            )
            if not sel_clinic:
                flash('You cannot add a patient to that clinic.', 'error')
                return render_template('patients/create.html',
                                       clinics=user_clinics, form_data=f)

            inserted_id = patient_repo.create(patient_data)
            audit('create', 'patient', inserted_id, clinic=sel_clinic)
            flash('Patient created successfully!', 'success')
            return redirect(url_for('patients.patient_detail',
                                    patient_id=str(inserted_id)))

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
            # Owner mismatch or missing clinic — deny access (don't leak existence).
            print(f"[ERROR] Access denied for patient {patient_id} (not owner)")
            flash('Patient not found', 'error')
            return redirect(url_for('patients.list_patients'))

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


# ── PDF EXPORT ───────────────────────────────────────────────────────────
@patients_bp.route('/patients/<patient_id>/pdf')
@login_required
def patient_pdf(patient_id):
    patient, clinic = verify_patient_access(patient_id)
    if not clinic:
        flash('Patient not found', 'error')
        return redirect(url_for('patients.list_patients'))
    try:
        _ensure_nested(patient)
        from blueprints.utils.pdf import build_patient_pdf
        # Pull the patient photo (if any) so it can be embedded in the PDF.
        photo_bytes = None
        if patient.get('photo_file_id'):
            try:
                from gridfs import GridFS
                photo_bytes = GridFS(mongo.db).get(patient['photo_file_id']).read()
            except Exception:
                photo_bytes = None
        buf = build_patient_pdf(patient, clinic, photo_bytes=photo_bytes)
        pi = patient.get('personal_info', {})
        fname = secure_filename(
            'patient_%s_%s' % (pi.get('first_name', ''), pi.get('last_name', ''))
        ) or 'patient_record'
        resp = send_file(buf, mimetype='application/pdf',
                         as_attachment=True, download_name=fname + '.pdf')
        resp.headers['X-Content-Type-Options'] = 'nosniff'
        return resp
    except Exception as e:
        print(f"[ERROR] Patient PDF: {e}")
        traceback.print_exc()
        flash('Could not generate the PDF.', 'error')
        return redirect(url_for('patients.patient_detail', patient_id=patient_id))


# ── EDIT ─────────────────────────────────────────────────────────────────
@patients_bp.route('/patients/<patient_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_patient(patient_id):
    try:
        # Access via the membership seam: clinic owner OR linked staff may edit.
        patient, clinic = verify_patient_access(patient_id)
        if not patient or not clinic:
            flash('Patient not found', 'error')
            return redirect(url_for('patients.list_patients'))

        _ensure_nested(patient)
        user_clinics = clinic_repo.accessible_active(session['user_id'])

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
                'minor_info.guardian_name': (f.get('guardian_name') or '').strip(),
                'minor_info.guardian_occupation': (f.get('guardian_occupation') or '').strip(),
                'referral_info.referred_by': (f.get('referred_by') or '').strip(),
                'referral_info.consultation_reason': (f.get('consultation_reason') or '').strip(),
                'dental_history.previous_dentist': (f.get('previous_dentist') or '').strip(),
                'dental_history.last_visit': (f.get('last_dental_visit') or '').strip(),
                'medical_history.physician_name': (f.get('physician_name') or '').strip(),
                'medical_history.physician_specialty': (f.get('physician_specialty') or '').strip(),
                'medical_history.physician_address': (f.get('physician_address') or '').strip(),
                'medical_history.q1_good_health': f.get('good_health', 'no'),
                'medical_history.q2_under_treatment': f.get('under_treatment', 'no'),
                'medical_history.q2_condition': (f.get('treatment_condition') or '').strip(),
                'medical_history.q6_tobacco': f.get('tobacco', 'no'),
                'medical_history.q7_dangerous_drugs': f.get('dangerous_drugs', 'no'),
                'medical_history.current_medications': (f.get('current_medications') or '').strip(),
                'medical_history.blood_type': (f.get('blood_type') or '').strip(),
                'medical_history.blood_pressure': (f.get('blood_pressure') or '').strip(),
                'medical_history.bleeding_time': (f.get('bleeding_time') or '').strip(),
                'medical_history.allergies.local_anesthesia': 'allergy_anesthetic' in f,
                'medical_history.allergies.penicillin': 'allergy_penicillin' in f,
                'medical_history.allergies.sulfa_drugs': 'allergy_sulfa' in f,
                'medical_history.allergies.aspirin': 'allergy_aspirin' in f,
                'medical_history.allergies.latex': 'allergy_latex' in f,
                'medical_history.allergies.other': (f.get('allergy_others') or '').strip(),
                'medical_history.women_health.pregnant': f.get('pregnant', 'no'),
                'medical_history.women_health.nursing': f.get('nursing', 'no'),
                'medical_history.women_health.birth_control': f.get('birth_control', 'no'),
                'medical_history.conditions.high_blood_pressure': 'condition_high_blood_pressure' in f,
                'medical_history.conditions.heart_disease': 'condition_heart_disease' in f,
                'medical_history.conditions.diabetes': 'condition_diabetes' in f,
                'medical_history.conditions.asthma': 'condition_asthma' in f,
                'medical_history.conditions.cancer_tumors': 'condition_cancer_tumors' in f,
                'medical_history.conditions.heart_murmur': 'condition_heart_murmur' in f,
                'medical_history.conditions.epilepsy_convulsions': 'condition_epilepsy' in f,
                'medical_history.conditions.hepatitis_liver': 'condition_hepatitis_liver' in f,
                'medical_history.conditions.kidney_disease': 'condition_kidney_disease' in f,
                'medical_history.conditions.arthritis_rheumatism': 'condition_arthritis' in f,
                'medical_history.conditions.thyroid_problem': 'condition_thyroid_problem' in f,
                'medical_history.conditions.bleeding_problems': 'condition_bleeding_problems' in f,
                'medical_history.conditions.other': (f.get('condition_other') or '').strip(),
                'updated_at': datetime.utcnow(),
            }
            patient_repo.update_set(patient_id, update_data)
            audit('update', 'patient', patient_id, clinic=clinic)
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
@role_required(ROLE_DENTIST)  # deleting a patient record is dentist/admin only
def delete_patient(patient_id):
    try:
        patient = mongo.db.patients.find_one({'_id': ObjectId(patient_id)})
        # Only the owner of the patient's clinic may delete the record.
        clinic = None
        if patient:
            clinic = mongo.db.clinics.find_one({
                '_id': patient['clinic_id'],
                'owner_id': session['user_id'],
            })
        if patient and clinic:
            mongo.db.patients.update_one(
                {'_id': ObjectId(patient_id)},
                {'$set': {'is_active': False, 'updated_at': datetime.utcnow()}},
            )
            audit('delete', 'patient', patient_id, clinic=clinic)
            flash('Patient record deleted', 'success')
        else:
            flash('Patient not found', 'error')
    except Exception as e:
        print(f"[ERROR] Delete patient: {e}")
        traceback.print_exc()
        flash(f'Error deleting patient: {e}', 'error')
    return redirect(url_for('patients.list_patients'))
