
# File: dental-portal/routes/patients.py
# Patient management routes

from flask import Blueprint, render_template, request, jsonify, session, redirect, url_for, flash
from bson.objectid import ObjectId
from datetime import datetime
from functools import wraps

from app_factory import mongo

patients_bp = Blueprint('patients', __name__, url_prefix='/patients')

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function

@patients_bp.route('/')
@login_required
def list_patients():
    """List patients with search and filtering"""
    clinic_id = request.args.get('clinic_id')
    search_query = request.args.get('search', '')
    page = int(request.args.get('page', 1))
    per_page = 20
    
    # Build query
    query = {}
    
    # Get user's clinics
    user_clinics = list(mongo.db.clinics.find({
        'owner_id': session['user_id'],
        'is_active': True
    }))
    clinic_ids = [clinic['_id'] for clinic in user_clinics]
    
    if clinic_id:
        query['clinic_id'] = ObjectId(clinic_id)
    else:
        query['clinic_id'] = {'$in': clinic_ids}
    
    query['is_active'] = True
    
    # Add search
    if search_query:
        query['$or'] = [
            {'personal_info.first_name': {'$regex': search_query, '$options': 'i'}},
            {'personal_info.last_name': {'$regex': search_query, '$options': 'i'}},
            {'personal_info.nickname': {'$regex': search_query, '$options': 'i'}},
            {'contact_info.cell_phone': {'$regex': search_query, '$options': 'i'}}
        ]
    
    # Get patients with pagination
    skip = (page - 1) * per_page
    patients = list(mongo.db.patients.find(query)
                   .sort('created_at', -1)
                   .skip(skip)
                   .limit(per_page))
    
    total_patients = mongo.db.patients.count_documents(query)
    total_pages = (total_patients + per_page - 1) // per_page
    
    return render_template('patients/list.html',
                         patients=patients,
                         clinics=user_clinics,
                         current_page=page,
                         total_pages=total_pages,
                         selected_clinic=clinic_id,
                         search_query=search_query)

@patients_bp.route('/<patient_id>')
@login_required
def detail(patient_id):
    """View patient details"""
    patient = mongo.db.patients.find_one({'_id': ObjectId(patient_id)})
    
    if not patient:
        flash('Patient not found', 'error')
        return redirect(url_for('patients.list_patients'))
    
    # Verify clinic ownership
    clinic = mongo.db.clinics.find_one({
        '_id': patient['clinic_id'],
        'owner_id': session['user_id']
    })
    
    if not clinic:
        flash('Access denied', 'error')
        return redirect(url_for('patients.list_patients'))
    
    return render_template('patients/detail.html', patient=patient, clinic=clinic)


