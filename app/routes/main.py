# File: dental-portal/routes/main.py
# Main application routes - dashboard, home, etc.

from flask import Blueprint, render_template, session, redirect, url_for, jsonify, request
from bson.objectid import ObjectId
from datetime import datetime, timedelta
from functools import wraps

# Import your mongo instance
from app_factory import mongo

main_bp = Blueprint('main', __name__)

def login_required(f):
    """Decorator to require login for routes"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function

@main_bp.route('/')
def index():
    """Home page - redirect to dashboard if logged in, otherwise to login"""
    if 'user_id' in session:
        return redirect(url_for('main.dashboard'))
    return redirect(url_for('auth.login'))

@main_bp.route('/dashboard')
@login_required
def dashboard():
    """Main dashboard page"""
    try:
        user_id = session['user_id']
        
        # Get user's clinics
        user_clinics = list(mongo.db.clinics.find({
            'owner_id': user_id,
            'is_active': True
        }).sort('name', 1))
        
        # Get clinic IDs for querying patients
        clinic_ids = [clinic['_id'] for clinic in user_clinics]
        
        # Get recent patients (last 10)
        recent_patients = list(mongo.db.patients.find({
            'clinic_id': {'$in': clinic_ids},
            'is_active': True
        }).sort('created_at', -1).limit(10))
        
        # Get upcoming appointments (next 7 days)
        today = datetime.utcnow()
        week_from_now = today + timedelta(days=7)
        
        upcoming_appointments = list(mongo.db.treatment_records.find({
            'patient_id': {'$in': [ObjectId(p['_id']) for p in recent_patients]},
            'next_appointment': {
                '$gte': today,
                '$lte': week_from_now
            }
        }).sort('next_appointment', 1).limit(5))
        
        # Get some statistics
        stats = {
            'total_clinics': len(user_clinics),
            'total_patients': mongo.db.patients.count_documents({
                'clinic_id': {'$in': clinic_ids},
                'is_active': True
            }),
            'patients_this_month': mongo.db.patients.count_documents({
                'clinic_id': {'$in': clinic_ids},
                'is_active': True,
                'created_at': {'$gte': datetime(today.year, today.month, 1)}
            }),
            'appointments_this_week': len(upcoming_appointments)
        }
        
        # Add patient names to appointments
        for appointment in upcoming_appointments:
            patient = mongo.db.patients.find_one({'_id': appointment['patient_id']})
            if patient:
                appointment['patient_name'] = f"{patient['personal_info']['first_name']} {patient['personal_info']['last_name']}"
        
        return render_template('dashboard/index.html',
                             clinics=user_clinics,
                             recent_patients=recent_patients,
                             upcoming_appointments=upcoming_appointments,
                             stats=stats)
                             
    except Exception as e:
        print(f"Dashboard error: {e}")
        return render_template('dashboard/index.html',
                             clinics=[],
                             recent_patients=[],
                             upcoming_appointments=[],
                             stats={'total_clinics': 0, 'total_patients': 0, 
                                   'patients_this_month': 0, 'appointments_this_week': 0})

@main_bp.route('/search')
@login_required
def search():
    """Global search functionality"""
    query = request.args.get('q', '').strip()
    search_type = request.args.get('type', 'patients')  # patients, clinics, treatments
    
    if not query:
        return jsonify({'results': []})
    
    user_id = session['user_id']
    results = []
    
    try:
        if search_type == 'patients':
            # Get user's clinic IDs
            user_clinics = mongo.db.clinics.find({'owner_id': user_id}, {'_id': 1})
            clinic_ids = [clinic['_id'] for clinic in user_clinics]
            
            # Search patients
            patients = mongo.db.patients.find({
                'clinic_id': {'$in': clinic_ids},
                'is_active': True,
                '$or': [
                    {'personal_info.first_name': {'$regex': query, '$options': 'i'}},
                    {'personal_info.last_name': {'$regex': query, '$options': 'i'}},
                    {'personal_info.nickname': {'$regex': query, '$options': 'i'}},
                    {'contact_info.cell_phone': {'$regex': query, '$options': 'i'}},
                    {'contact_info.email': {'$regex': query, '$options': 'i'}}
                ]
            }).limit(20)
            
            for patient in patients:
                results.append({
                    'id': str(patient['_id']),
                    'type': 'patient',
                    'title': f"{patient['personal_info']['first_name']} {patient['personal_info']['last_name']}",
                    'subtitle': patient['personal_info'].get('nickname', ''),
                    'description': patient['contact_info'].get('cell_phone', ''),
                    'url': url_for('patients.detail', patient_id=str(patient['_id']))
                })
        
        elif search_type == 'clinics':
            clinics = mongo.db.clinics.find({
                'owner_id': user_id,
                'is_active': True,
                'name': {'$regex': query, '$options': 'i'}
            }).limit(10)
            
            for clinic in clinics:
                results.append({
                    'id': str(clinic['_id']),
                    'type': 'clinic',
                    'title': clinic['name'],
                    'subtitle': clinic.get('address', ''),
                    'description': clinic.get('phone', ''),
                    'url': url_for('clinics.detail', clinic_id=str(clinic['_id']))
                })
        
        return jsonify({'results': results})
        
    except Exception as e:
        print(f"Search error: {e}")
        return jsonify({'results': [], 'error': 'Search failed'})

@main_bp.route('/api/stats')
@login_required
def api_stats():
    """API endpoint for dashboard statistics"""
    try:
        user_id = session['user_id']
        
        # Get user's clinics
        user_clinics = list(mongo.db.clinics.find({
            'owner_id': user_id,
            'is_active': True
        }, {'_id': 1}))
        
        clinic_ids = [clinic['_id'] for clinic in user_clinics]
        today = datetime.utcnow()
        
        # Calculate various statistics
        stats = {
            'clinics': {
                'total': len(user_clinics),
                'active': len(user_clinics)  # All found clinics are active due to filter
            },
            'patients': {
                'total': mongo.db.patients.count_documents({
                    'clinic_id': {'$in': clinic_ids},
                    'is_active': True
                }),
                'this_month': mongo.db.patients.count_documents({
                    'clinic_id': {'$in': clinic_ids},
                    'is_active': True,
                    'created_at': {'$gte': datetime(today.year, today.month, 1)}
                }),
                'this_week': mongo.db.patients.count_documents({
                    'clinic_id': {'$in': clinic_ids},
                    'is_active': True,
                    'created_at': {'$gte': today - timedelta(days=7)}
                })
            },
            'treatments': {
                'total': mongo.db.treatment_records.count_documents({
                    'patient_id': {'$in': [
                        p['_id'] for p in mongo.db.patients.find(
                            {'clinic_id': {'$in': clinic_ids}}, {'_id': 1}
                        )
                    ]}
                }),
                'this_month': mongo.db.treatment_records.count_documents({
                    'created_at': {'$gte': datetime(today.year, today.month, 1)}
                })
            }
        }
        
        return jsonify(stats)
        
    except Exception as e:
        print(f"Stats API error: {e}")
        return jsonify({'error': 'Failed to load statistics'}), 500

@main_bp.route('/settings')
@login_required
def settings():
    """Application settings page"""
    user = mongo.db.users.find_one({'_id': ObjectId(session['user_id'])})
    return render_template('settings.html', user=user)

@main_bp.route('/help')
def help_page():
    """Help and documentation page"""
    return render_template('help.html')

@main_bp.route('/about')
def about():
    """About page"""
    return render_template('about.html')

# Error handlers
@main_bp.errorhandler(404)
def not_found(error):
    return render_template('errors/404.html'), 404

@main_bp.errorhandler(500)
def internal_error(error):
    return render_template('errors/500.html'), 500