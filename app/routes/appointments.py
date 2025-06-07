from flask import Blueprint, request, jsonify, session, render_template, redirect, url_for, flash, current_app
from bson.objectid import ObjectId
from datetime import datetime, timedelta
from functools import wraps

# Create blueprint
appointments_bp = Blueprint('appointments', __name__)

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def get_mongo():
    """Get MongoDB instance from current app"""
    from flask_pymongo import PyMongo
    return current_app.extensions['pymongo']['MONGO'][0]

@appointments_bp.route('/')
@login_required
def appointments():
    """Appointments calendar page"""
    try:
        mongo = get_mongo()
        
        # Get user's clinics
        user_clinics = list(mongo.db.clinics.find({
            'owner_id': session['user_id'],
            'is_active': True
        }))
        
        if not user_clinics:
            flash('You need to create a clinic first before managing appointments.', 'warning')
            return redirect(url_for('create_clinic_fallback'))
        
        # Get patients for the sidebar
        clinic_ids = [clinic['_id'] for clinic in user_clinics]
        patients = list(mongo.db.patients.find({
            'clinic_id': {'$in': clinic_ids},
            'is_active': True
        }).sort('personal_info.first_name', 1))
        
        # Format patients for the template
        formatted_patients = []
        for patient in patients:
            personal_info = patient.get('personal_info', {})
            contact_info = patient.get('contact_info', {})
            
            full_name = f"{personal_info.get('first_name', '')} {personal_info.get('last_name', '')}"
            formatted_patients.append({
                'id': str(patient['_id']),
                'name': full_name.strip(),
                'phone': contact_info.get('cell_phone', contact_info.get('home_phone', '')),
                'last_visit': 'New patient'
            })
        
        return render_template('appointments.html', 
                             clinics=user_clinics, 
                             patients=formatted_patients)
    except Exception as e:
        print(f"Appointments error: {e}")
        flash('Error loading appointments page', 'error')
        return redirect(url_for('dashboard'))

@appointments_bp.route('/api', methods=['GET'])
@login_required
def get_appointments():
    """Get appointments for calendar view"""
    try:
        mongo = get_mongo()
        
        clinic_id = request.args.get('clinic_id')
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        
        # Get user's clinics
        user_clinics = list(mongo.db.clinics.find({
            'owner_id': session['user_id'],
            'is_active': True
        }))
        clinic_ids = [str(clinic['_id']) for clinic in user_clinics]
        
        # Build query
        query = {'is_active': True}
        
        if clinic_id and clinic_id in clinic_ids:
            query['clinic_id'] = ObjectId(clinic_id)
        else:
            query['clinic_id'] = {'$in': [ObjectId(cid) for cid in clinic_ids]}
        
        if start_date and end_date:
            query['date'] = {'$gte': start_date, '$lte': end_date}
        
        appointments = list(mongo.db.appointments.find(query).sort([('date', 1), ('time', 1)]))
        
        # Convert ObjectIds to strings for JSON serialization
        for appointment in appointments:
            appointment['_id'] = str(appointment['_id'])
            appointment['clinic_id'] = str(appointment['clinic_id'])
            if 'patient_id' in appointment:
                appointment['patient_id'] = str(appointment['patient_id'])
        
        return jsonify({'success': True, 'appointments': appointments})
        
    except Exception as e:
        print(f"Get appointments error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@appointments_bp.route('/api', methods=['POST'])
@login_required
def create_appointment():
    """Create a new appointment"""
    try:
        mongo = get_mongo()
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['patient_name', 'date', 'time']
        for field in required_fields:
            if not data.get(field):
                return jsonify({'success': False, 'error': f'{field} is required'}), 400
        
        # Get clinic_id
        clinic_id = data.get('clinic_id')
        if not clinic_id:
            user_clinic = mongo.db.clinics.find_one({
                'owner_id': session['user_id'],
                'is_active': True
            })
            if not user_clinic:
                return jsonify({'success': False, 'error': 'No clinic found'}), 403
            clinic_id = str(user_clinic['_id'])
        
        # Verify clinic ownership
        clinic = mongo.db.clinics.find_one({
            '_id': ObjectId(clinic_id),
            'owner_id': session['user_id']
        })
        
        if not clinic:
            return jsonify({'success': False, 'error': 'Invalid clinic'}), 403
        
        # Check for time conflicts
        existing_appointment = mongo.db.appointments.find_one({
            'clinic_id': ObjectId(clinic_id),
            'date': data['date'],
            'time': data['time'],
            'is_active': True
        })
        
        if existing_appointment:
            return jsonify({'success': False, 'error': 'Time slot already booked'}), 409
        
        # Create appointment
        appointment_data = {
            'clinic_id': ObjectId(clinic_id),
            'patient_name': data['patient_name'].strip(),
            'date': data['date'],
            'time': data['time'],
            'duration': int(data.get('duration', 30)),
            'type': data.get('type', 'checkup'),
            'priority': data.get('priority', 'normal'),
            'notes': data.get('notes', '').strip(),
            'status': 'scheduled',
            'created_by': session['user_id'],
            'created_at': datetime.utcnow(),
            'updated_at': datetime.utcnow(),
            'is_active': True
        }
        
        # Add patient_id if provided
        if data.get('patient_id'):
            appointment_data['patient_id'] = ObjectId(data['patient_id'])
        
        result = mongo.db.appointments.insert_one(appointment_data)
        
        return jsonify({
            'success': True, 
            'appointment_id': str(result.inserted_id),
            'message': 'Appointment created successfully'
        })
        
    except Exception as e:
        print(f"Create appointment error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@appointments_bp.route('/api/<appointment_id>', methods=['PUT'])
@login_required
def update_appointment(appointment_id):
    """Update an existing appointment"""
    try:
        mongo = get_mongo()
        data = request.get_json()
        
        # Find appointment and verify ownership
        appointment = mongo.db.appointments.find_one({'_id': ObjectId(appointment_id)})
        if not appointment:
            return jsonify({'success': False, 'error': 'Appointment not found'}), 404
        
        # Verify clinic ownership
        clinic = mongo.db.clinics.find_one({
            '_id': appointment['clinic_id'],
            'owner_id': session['user_id']
        })
        
        if not clinic:
            return jsonify({'success': False, 'error': 'Access denied'}), 403
        
        # Check for time conflicts (excluding current appointment)
        if data.get('date') and data.get('time'):
            existing_appointment = mongo.db.appointments.find_one({
                '_id': {'$ne': ObjectId(appointment_id)},
                'clinic_id': appointment['clinic_id'],
                'date': data['date'],
                'time': data['time'],
                'is_active': True
            })
            
            if existing_appointment:
                return jsonify({'success': False, 'error': 'Time slot already booked'}), 409
        
        # Build update data
        update_data = {
            'updated_at': datetime.utcnow()
        }
        
        # Update fields if provided
        updatable_fields = ['patient_name', 'date', 'time', 'duration', 'type', 'priority', 'notes', 'status']
        for field in updatable_fields:
            if field in data:
                if field == 'duration':
                    update_data[field] = int(data[field])
                else:
                    update_data[field] = data[field]
        
        # Handle patient_id separately
        if 'patient_id' in data:
            if data['patient_id']:
                update_data['patient_id'] = ObjectId(data['patient_id'])
            else:
                update_data['$unset'] = {'patient_id': ''}
        
        # Update appointment
        result = mongo.db.appointments.update_one(
            {'_id': ObjectId(appointment_id)},
            {'$set': update_data}
        )
        
        if result.modified_count:
            return jsonify({
                'success': True,
                'message': 'Appointment updated successfully'
            })
        else:
            return jsonify({
                'success': False,
                'error': 'No changes made'
            }), 400
        
    except Exception as e:
        print(f"Update appointment error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@appointments_bp.route('/api/<appointment_id>', methods=['DELETE'])
@login_required
def delete_appointment(appointment_id):
    """Delete (deactivate) an appointment"""
    try:
        mongo = get_mongo()
        
        # Find appointment and verify ownership
        appointment = mongo.db.appointments.find_one({'_id': ObjectId(appointment_id)})
        if not appointment:
            return jsonify({'success': False, 'error': 'Appointment not found'}), 404
        
        # Verify clinic ownership
        clinic = mongo.db.clinics.find_one({
            '_id': appointment['clinic_id'],
            'owner_id': session['user_id']
        })
        
        if not clinic:
            return jsonify({'success': False, 'error': 'Access denied'}), 403
        
        # Soft delete (deactivate)
        result = mongo.db.appointments.update_one(
            {'_id': ObjectId(appointment_id)},
            {
                '$set': {
                    'is_active': False,
                    'deleted_at': datetime.utcnow(),
                    'deleted_by': session['user_id']
                }
            }
        )
        
        if result.modified_count:
            return jsonify({
                'success': True,
                'message': 'Appointment deleted successfully'
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Failed to delete appointment'
            }), 400
        
    except Exception as e:
        print(f"Delete appointment error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500