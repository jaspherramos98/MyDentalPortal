# File: dental-portal/routes/treatments.py
# Treatment record routes

from flask import Blueprint, render_template, request, jsonify, session, redirect, url_for, flash
from bson.objectid import ObjectId
from datetime import datetime
from functools import wraps

from app_factory import mongo

treatments_bp = Blueprint('treatments', __name__, url_prefix='/treatments')

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function

@treatments_bp.route('/patient/<patient_id>')
@login_required
def patient_treatments(patient_id):
    """List all treatments for a specific patient"""
    # Verify patient access
    patient = mongo.db.patients.find_one({'_id': ObjectId(patient_id)})
    if not patient:
        flash('Patient not found', 'error')
        return redirect(url_for('patients.list_patients'))
    
    clinic = mongo.db.clinics.find_one({
        '_id': patient['clinic_id'],
        'owner_id': session['user_id']
    })
    
    if not clinic:
        flash('Access denied', 'error')
        return redirect(url_for('patients.list_patients'))
    
    # Get treatments
    treatments = list(mongo.db.treatment_records.find({
        'patient_id': ObjectId(patient_id)
    }).sort('date', -1))
    
    return render_template('treatments/list.html', 
                         patient=patient, 
                         treatments=treatments,
                         clinic=clinic)

@treatments_bp.route('/add/<patient_id>', methods=['GET', 'POST'])
@login_required
def add_treatment(patient_id):
    """Add a new treatment record"""
    # Verify patient access
    patient = mongo.db.patients.find_one({'_id': ObjectId(patient_id)})
    if not patient:
        flash('Patient not found', 'error')
        return redirect(url_for('patients.list_patients'))
    
    clinic = mongo.db.clinics.find_one({
        '_id': patient['clinic_id'],
        'owner_id': session['user_id']
    })
    
    if not clinic:
        flash('Access denied', 'error')
        return redirect(url_for('patients.list_patients'))
    
    if request.method == 'POST':
        data = request.get_json() if request.is_json else request.form
        
        # Parse tooth numbers
        tooth_numbers = []
        if data.get('tooth_numbers'):
            tooth_numbers = [t.strip() for t in data.get('tooth_numbers').split(',') if t.strip()]
        
        treatment_data = {
            'patient_id': ObjectId(patient_id),
            'date': datetime.strptime(data.get('date'), '%Y-%m-%d') if data.get('date') else datetime.utcnow(),
            'tooth_numbers': tooth_numbers,
            'procedure': data.get('procedure', '').strip(),
            'dentist': data.get('dentist', session.get('user_name', '')),
            'amount_charged': float(data.get('amount_charged', 0)),
            'amount_paid': float(data.get('amount_paid', 0)),
            'balance': float(data.get('amount_charged', 0)) - float(data.get('amount_paid', 0)),
            'notes': data.get('notes', '').strip(),
            'treatment_category': data.get('treatment_category', 'General'),
            'created_by': session['user_id'],
            'created_at': datetime.utcnow(),
            'updated_at': datetime.utcnow()
        }
        
        # Add next appointment if provided
        if data.get('next_appointment'):
            treatment_data['next_appointment'] = datetime.strptime(
                data.get('next_appointment'), '%Y-%m-%d'
            )
        
        try:
            result = mongo.db.treatment_records.insert_one(treatment_data)
            
            if request.is_json:
                return jsonify({'success': True, 'treatment_id': str(result.inserted_id)})
            flash('Treatment record added successfully!', 'success')
            return redirect(url_for('treatments.patient_treatments', patient_id=patient_id))
            
        except Exception as e:
            error = 'Failed to add treatment record'
            if request.is_json:
                return jsonify({'success': False, 'error': error}), 500
            flash(error, 'error')
    
    return render_template('treatments/add.html', patient=patient, clinic=clinic)

