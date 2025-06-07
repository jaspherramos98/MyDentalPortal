# File: dental-portal/routes/clinics.py
# Clinic management routes

from flask import Blueprint, render_template, request, jsonify, session, redirect, url_for, flash
from bson.objectid import ObjectId
from datetime import datetime
from functools import wraps

from app_factory import mongo

clinics_bp = Blueprint('clinics', __name__, url_prefix='/clinics')

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function

@clinics_bp.route('/')
@login_required
def list_clinics():
    """List all clinics for the current user"""
    clinics = list(mongo.db.clinics.find({
        'owner_id': session['user_id'],
        'is_active': True
    }).sort('name', 1))
    
    return render_template('clinics/list.html', clinics=clinics)

@clinics_bp.route('/create', methods=['GET', 'POST'])
@login_required
def create():
    """Create a new clinic"""
    if request.method == 'POST':
        data = request.get_json() if request.is_json else request.form
        
        clinic_data = {
            'name': data.get('name', '').strip(),
            'address': data.get('address', '').strip(),
            'phone': data.get('phone', '').strip(),
            'email': data.get('email', '').strip(),
            'owner_id': session['user_id'],
            'staff_ids': [session['user_id']],
            'operating_hours': {
                'monday': {'open': data.get('mon_open', '09:00'), 'close': data.get('mon_close', '17:00'), 'closed': data.get('mon_closed') == 'on'},
                'tuesday': {'open': data.get('tue_open', '09:00'), 'close': data.get('tue_close', '17:00'), 'closed': data.get('tue_closed') == 'on'},
                'wednesday': {'open': data.get('wed_open', '09:00'), 'close': data.get('wed_close', '17:00'), 'closed': data.get('wed_closed') == 'on'},
                'thursday': {'open': data.get('thu_open', '09:00'), 'close': data.get('thu_close', '17:00'), 'closed': data.get('thu_closed') == 'on'},
                'friday': {'open': data.get('fri_open', '09:00'), 'close': data.get('fri_close', '17:00'), 'closed': data.get('fri_closed') == 'on'},
                'saturday': {'open': data.get('sat_open', '09:00'), 'close': data.get('sat_close', '15:00'), 'closed': data.get('sat_closed') == 'on'},
                'sunday': {'open': data.get('sun_open', '00:00'), 'close': data.get('sun_close', '00:00'), 'closed': True}
            },
            'created_at': datetime.utcnow(),
            'updated_at': datetime.utcnow(),
            'is_active': True
        }
        
        if not clinic_data['name']:
            error = 'Clinic name is required'
            if request.is_json:
                return jsonify({'success': False, 'error': error}), 400
            flash(error, 'error')
            return render_template('clinics/create.html')
        
        try:
            result = mongo.db.clinics.insert_one(clinic_data)
            
            if request.is_json:
                return jsonify({'success': True, 'clinic_id': str(result.inserted_id)})
            flash('Clinic created successfully!', 'success')
            return redirect(url_for('clinics.detail', clinic_id=str(result.inserted_id)))
            
        except Exception as e:
            error = 'Failed to create clinic'
            if request.is_json:
                return jsonify({'success': False, 'error': error}), 500
            flash(error, 'error')
            return render_template('clinics/create.html')
    
    return render_template('clinics/create.html')

@clinics_bp.route('/<clinic_id>')
@login_required
def detail(clinic_id):
    """View clinic details"""
    clinic = mongo.db.clinics.find_one({
        '_id': ObjectId(clinic_id),
        'owner_id': session['user_id']
    })
    
    if not clinic:
        flash('Clinic not found', 'error')
        return redirect(url_for('clinics.list_clinics'))
    
    # Get patients for this clinic
    patients = list(mongo.db.patients.find({
        'clinic_id': ObjectId(clinic_id),
        'is_active': True
    }).sort('created_at', -1))
    
    return render_template('clinics/detail.html', clinic=clinic, patients=patients)


