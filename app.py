from flask import Flask, request, jsonify, session, render_template, redirect, url_for, flash
from flask_pymongo import PyMongo
from werkzeug.security import generate_password_hash, check_password_hash
from bson.objectid import ObjectId
from datetime import datetime, timedelta, timezone
import os
from functools import wraps
from dotenv import load_dotenv
from config import get_config

# Load environment variables
load_dotenv()

app = Flask(__name__)

# Configuration
# Configuration
config_class = get_config()
app.config.from_object(config_class)
config_class.init_app(app)
# Initialize MongoDB
mongo = PyMongo(app)

# Import and register blueprints with corrected paths
def register_blueprints():
    """Register all blueprints with proper error handling"""
    blueprints = [
        ('app.routes.appointments', 'appointments_bp', '/appointments'),
        ('app.routes.auth', 'auth_bp', '/auth'),
        ('app.routes.clinics', 'clinics_bp', '/clinics'),
        ('app.routes.patients', 'patients_bp', '/patients'),
        ('app.routes.treatments', 'treatments_bp', '/treatments'),
        ('app.routes.charts', 'charts_bp', '/charts'),
        ('app.routes.main', 'main_bp', None)
    ]
    
    for module_path, blueprint_name, url_prefix in blueprints:
        try:
            module = __import__(module_path, fromlist=[blueprint_name])
            blueprint = getattr(module, blueprint_name)
            if url_prefix:
                app.register_blueprint(blueprint, url_prefix=url_prefix)
            else:
                app.register_blueprint(blueprint)
            print(f"✓ {blueprint_name} registered successfully")
        except ImportError as e:
            print(f"✗ Could not import {blueprint_name}: {e}")
        except AttributeError as e:
            print(f"✗ Blueprint {blueprint_name} not found in module: {e}")
        except Exception as e:
            print(f"✗ Error registering {blueprint_name}: {e}")

# Register blueprints
register_blueprints()

# Authentication decorator
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# Routes
@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        data = request.get_json() if request.is_json else request.form
        email = data.get('email')
        password = data.get('password')
        
        # Validate input
        if not email or not password:
            flash('Email and password are required', 'error')
            return render_template('auth/login.html')
        
        try:
            user = mongo.db.users.find_one({'email': email.lower().strip()})
            
            if user and check_password_hash(user['password'], password):
                session['user_id'] = str(user['_id'])
                session['user_email'] = user['email']
                session['user_name'] = user['name']
                
                if request.is_json:
                    return jsonify({'success': True, 'redirect': url_for('dashboard')})
                flash('Login successful!', 'success')
                return redirect(url_for('dashboard'))
            
            flash('Invalid email or password', 'error')
        except Exception as e:
            print(f"Login error: {e}")
            flash('Login failed. Please try again.', 'error')
        
        return render_template('auth/login.html')
    
    # GET request
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return render_template('auth/login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        data = request.get_json() if request.is_json else request.form
        
        # Get form data
        name = data.get('name', '').strip()
        email = data.get('email', '').strip().lower()
        password = data.get('password', '')
        confirm_password = data.get('confirm_password', '')
        license_number = data.get('license_number', '').strip()
        specialty = data.get('specialty', '').strip()
        
        # Basic validation
        if not all([name, email, password, license_number]):
            flash('Please fill in all required fields', 'error')
            return render_template('auth/register.html')
        
        if password != confirm_password:
            flash('Passwords do not match', 'error')
            return render_template('auth/register.html')
        
        if len(password) < 8:
            flash('Password must be at least 8 characters long', 'error')
            return render_template('auth/register.html')
        
        try:
            # Check if user already exists
            if mongo.db.users.find_one({'email': email}):
                flash('Email already registered', 'error')
                return render_template('auth/register.html')
            
            # Create new user
            user_data = {
                'name': name,
                'email': email,
                'password': generate_password_hash(password),
                'license_number': license_number,
                'specialty': specialty,
                'created_at': datetime.utcnow(),
                'updated_at': datetime.utcnow(),
                'is_active': True
            }
            
            result = mongo.db.users.insert_one(user_data)
            
            if request.is_json:
                return jsonify({'success': True, 'user_id': str(result.inserted_id)})
            flash('Registration successful! Please login.', 'success')
            return redirect(url_for('login'))
            
        except Exception as e:
            print(f"Registration error: {e}")
            flash('Registration failed. Please try again.', 'error')
            return render_template('auth/register.html')
    
    # GET request
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return render_template('auth/register.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    try:
        user_id = session['user_id']
        
        # Get user's clinics
        user_clinics = list(mongo.db.clinics.find({
            'owner_id': user_id,
            'is_active': True
        }).sort('name', 1))
        
        # Get clinic IDs for querying patients and appointments
        clinic_ids = [clinic['_id'] for clinic in user_clinics]
        
        # Get recent patients (last 10)
        recent_patients = []
        if clinic_ids:
            recent_patients = list(mongo.db.patients.find({
                'clinic_id': {'$in': clinic_ids},
                'is_active': True
            }).sort('created_at', -1).limit(10))
        
        # Get today's appointments
        today = datetime.now().strftime('%Y-%m-%d')
        today_appointments = []
        if clinic_ids:
            today_appointments = list(mongo.db.appointments.find({
                'clinic_id': {'$in': clinic_ids},
                'date': today,
                'is_active': True
            }).sort('time', 1))
        
        # Get upcoming appointments (next 7 days)
        end_date = (datetime.now() + timedelta(days=7)).strftime('%Y-%m-%d')
        upcoming_appointments = []
        if clinic_ids:
            upcoming_appointments = list(mongo.db.appointments.find({
                'clinic_id': {'$in': clinic_ids},
                'date': {'$gte': today, '$lte': end_date},
                'is_active': True
            }).sort([('date', 1), ('time', 1)]).limit(10))
        
        # Get some basic statistics
        stats = {
            'total_clinics': len(user_clinics),
            'total_patients': len(recent_patients),
            'patients_this_month': 0,
            'appointments_this_week': 0,
            'today_appointments': len(today_appointments),
            'upcoming_appointments': len(upcoming_appointments)
        }
        
        # Calculate this month's patients
        if clinic_ids:
            today_dt = datetime.utcnow()
            month_start = datetime(today_dt.year, today_dt.month, 1)
            stats['patients_this_month'] = mongo.db.patients.count_documents({
                'clinic_id': {'$in': clinic_ids},
                'is_active': True,
                'created_at': {'$gte': month_start}
            })
            
            # Calculate this week's appointments
            week_start = today_dt - timedelta(days=today_dt.weekday())
            week_end = week_start + timedelta(days=7)
            stats['appointments_this_week'] = mongo.db.appointments.count_documents({
                'clinic_id': {'$in': clinic_ids},
                'date': {
                    '$gte': week_start.strftime('%Y-%m-%d'),
                    '$lt': week_end.strftime('%Y-%m-%d')
                },
                'is_active': True
            })
        
        return render_template('dashboard/index.html',
                             clinics=user_clinics,
                             recent_patients=recent_patients,
                             today_appointments=today_appointments,
                             upcoming_appointments=upcoming_appointments,
                             stats=stats)
                             
    except Exception as e:
        print(f"Dashboard error: {e}")
        # Return dashboard with empty data if there's an error
        return render_template('dashboard/index.html',
                             clinics=[],
                             recent_patients=[],
                             today_appointments=[],
                             upcoming_appointments=[],
                             stats={'total_clinics': 0, 'total_patients': 0, 
                                   'patients_this_month': 0, 'appointments_this_week': 0,
                                   'today_appointments': 0, 'upcoming_appointments': 0})

# Clinic Management Routes
@app.route('/clinics_fallback')
@login_required
def clinics_fallback():
    """Fallback clinic route if blueprint fails"""
    try:
        clinics = list(mongo.db.clinics.find({
            'owner_id': session['user_id'],
            'is_active': True
        }).sort('name', 1))
        return render_template('clinics/list.html', clinics=clinics)
    except Exception as e:
        print(f"Clinics error: {e}")
        flash('Error loading clinics', 'error')
        return render_template('clinics/list.html', clinics=[])

@app.route('/clinics_fallback/create', methods=['GET', 'POST'])
@login_required
def create_clinic_fallback():
    """Fallback create clinic route if blueprint fails"""
    if request.method == 'POST':
        data = request.get_json() if request.is_json else request.form
        
        clinic_data = {
            'name': data.get('name', '').strip(),
            'address': data.get('address', '').strip(),
            'phone': data.get('phone', '').strip(),
            'email': data.get('email', '').strip(),
            'owner_id': session['user_id'],
            'staff_ids': [session['user_id']],
            'office_hours': {
                'monday': {'start': '09:00', 'end': '17:00', 'closed': False},
                'tuesday': {'start': '09:00', 'end': '17:00', 'closed': False},
                'wednesday': {'start': '09:00', 'end': '17:00', 'closed': False},
                'thursday': {'start': '09:00', 'end': '17:00', 'closed': False},
                'friday': {'start': '09:00', 'end': '17:00', 'closed': False},
                'saturday': {'start': '09:00', 'end': '13:00', 'closed': False},
                'sunday': {'start': '09:00', 'end': '17:00', 'closed': True}
            },
            'appointment_duration': 30,
            'created_at': datetime.utcnow(),
            'updated_at': datetime.utcnow(),
            'is_active': True
        }
        
        if not clinic_data['name']:
            flash('Clinic name is required', 'error')
            return render_template('clinics/create.html')
        
        try:
            result = mongo.db.clinics.insert_one(clinic_data)
            flash('Clinic created successfully!', 'success')
            return redirect(url_for('clinics_fallback'))
        except Exception as e:
            print(f"Create clinic error: {e}")
            flash('Failed to create clinic', 'error')
    
    return render_template('clinics/create.html')

# Appointments Routes (Fallback routes if blueprint fails)
@app.route('/appointments_fallback')
@login_required
def appointments_fallback():
    """Fallback appointments page if blueprint fails"""
    try:
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
            full_name = f"{patient['personal_info']['first_name']} {patient['personal_info']['last_name']}"
            formatted_patients.append({
                'id': str(patient['_id']),
                'name': full_name,
                'phone': patient['contact_info'].get('cell_phone', patient['contact_info'].get('home_phone', '')),
                'last_visit': 'New patient'
            })
        
        return render_template('appointments.html', 
                             clinics=user_clinics, 
                             patients=formatted_patients)
    except Exception as e:
        print(f"Appointments error: {e}")
        flash('Error loading appointments page', 'error')
        return redirect(url_for('dashboard'))

# API Routes for Appointments (Fallback)
@app.route('/api/appointments', methods=['GET'])
@login_required
def get_appointments_api():
    """Get appointments for calendar view"""
    try:
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

@app.route('/api/appointments', methods=['POST'])
@login_required
def create_appointment_api():
    """Create a new appointment"""
    try:
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

# Patient Management Routes (keeping your existing code)
@app.route('/patients_fallback/create', methods=['GET', 'POST'])
@login_required
def create_patient_fallback():
    print(f"DEBUG: create_patient called with method: {request.method}")
    
    if request.method == 'POST':
        print("DEBUG: Processing POST request")
        data = request.get_json() if request.is_json else request.form
        print(f"DEBUG: Form data keys: {list(data.keys())}")
        
        # Validate clinic ownership
        clinic_id = data.get('clinic_id')
        print(f"DEBUG: Selected clinic_id: {clinic_id}")
        
        if not clinic_id:
            print("DEBUG: No clinic selected")
            flash('Please select a clinic', 'error')
            user_clinics = list(mongo.db.clinics.find({'owner_id': session['user_id'], 'is_active': True}))
            return render_template('patients/create.html', clinics=user_clinics, form_data=data)
        
        try:
            clinic = mongo.db.clinics.find_one({
                '_id': ObjectId(clinic_id),
                'owner_id': session['user_id']
            })
            print(f"DEBUG: Found clinic: {clinic['name'] if clinic else 'None'}")
        except Exception as e:
            print(f"DEBUG: Error finding clinic: {e}")
            flash('Invalid clinic selected', 'error')
            user_clinics = list(mongo.db.clinics.find({'owner_id': session['user_id'], 'is_active': True}))
            return render_template('patients/create.html', clinics=user_clinics, form_data=data)
        
        if not clinic:
            print("DEBUG: Clinic not found or not owned by user")
            flash('Invalid clinic selected', 'error')
            user_clinics = list(mongo.db.clinics.find({'owner_id': session['user_id'], 'is_active': True}))
            return render_template('patients/create.html', clinics=user_clinics, form_data=data)
        
        # Enhanced validation with conditional guardian requirements for minors
        required_fields = [
            'first_name', 'last_name', 'gender', 'birthdate', 'age',
            'home_address', 'home_phone', 'emergency_name', 
            'emergency_relationship', 'emergency_phone', 'good_health',
            'under_treatment', 'current_medications', 'clinic_id'
        ]

        missing_fields = []

        # Validate base required fields
        for field in required_fields:
            value = data.get(field, '')
            
            if field in ['good_health', 'under_treatment']:
                if value not in ['yes', 'no']:
                    missing_fields.append(field.replace('_', ' ').title())
            else:
                if not value or not value.strip():
                    missing_fields.append(field.replace('_', ' ').title())

        # Check if patient is a minor
        patient_age = None
        try:
            age_value = data.get('age', '').strip()
            if age_value:
                patient_age = int(age_value)
        except (ValueError, TypeError):
            pass

        # Additional validation for minors
        if patient_age is not None and patient_age < 18:
            if not data.get('guardian_name', '').strip():
                missing_fields.append('Guardian/Parent Name')

        if missing_fields:
            flash(f'Please fill in required fields: {", ".join(missing_fields)}', 'error')
            user_clinics = list(mongo.db.clinics.find({'owner_id': session['user_id'], 'is_active': True}))
            return render_template('patients/create.html', clinics=user_clinics, form_data=data)
        
        try:
            # Create patient document
            patient_data = {
                'clinic_id': ObjectId(clinic_id),
                'personal_info': {
                    'first_name': data.get('first_name', '').strip(),
                    'middle_name': data.get('middle_name', '').strip(),
                    'last_name': data.get('last_name', '').strip(),
                    'nickname': data.get('nickname', '').strip(),
                    'gender': data.get('gender', '').strip(),
                    'birthdate': data.get('birthdate', '').strip(),
                    'age': int(data.get('age', 0)) if data.get('age', '').strip() else None,
                    'religion': data.get('religion', '').strip(),
                    'nationality': data.get('nationality', '').strip(),
                    'home_address': data.get('home_address', '').strip(),
                    'occupation': data.get('occupation', '').strip(),
                    'dental_insurance': data.get('dental_insurance', '').strip()
                },
                'contact_info': {
                    'home_phone': data.get('home_phone', '').strip(),
                    'cell_phone': data.get('cell_phone', '').strip(),
                    'office_phone': data.get('office_phone', '').strip(),
                    'fax': data.get('fax', '').strip(),
                    'email': data.get('email', '').strip()
                },
                'emergency_contact': {
                    'name': data.get('emergency_name', '').strip(),
                    'relationship': data.get('emergency_relationship', '').strip(),
                    'phone': data.get('emergency_phone', '').strip()
                },
                'guardian_info': {
                    'name': data.get('guardian_name', '').strip(),
                    'occupation': data.get('guardian_occupation', '').strip()
                },
                'referral_info': {
                    'referred_by': data.get('referred_by', '').strip(),
                    'consultation_reason': data.get('consultation_reason', '').strip()
                },
                'dental_history': {
                    'previous_dentist': data.get('previous_dentist', '').strip(),
                    'last_visit': data.get('last_dental_visit', '').strip()
                },
                'medical_history': {
                    'physician_info': {
                        'name': data.get('physician_name', '').strip(),
                        'specialty': data.get('physician_specialty', '').strip(),
                        'office_address': data.get('physician_address', '').strip(),
                        'office_number': data.get('physician_phone', '').strip()
                    },
                    'general_health': {
                        'good_health': data.get('good_health') == 'yes',
                        'under_treatment': data.get('under_treatment') == 'yes',
                        'treatment_condition': data.get('treatment_condition', '').strip(),
                        'serious_illness': data.get('serious_illness') == 'yes',
                        'illness_details': data.get('illness_details', '').strip(),
                        'hospitalized': data.get('hospitalized') == 'yes',
                        'hospitalization_details': data.get('hospitalization_details', '').strip(),
                        'current_medications': data.get('current_medications', '').strip(),
                        'tobacco_use': data.get('tobacco_use') == 'yes',
                        'alcohol_drugs': data.get('alcohol_drugs') == 'yes'
                    },
                    'allergies': {
                        'local_anesthetic': data.get('allergy_anesthetic') == 'yes',
                        'penicillin': data.get('allergy_penicillin') == 'yes',
                        'sulfa_drugs': data.get('allergy_sulfa') == 'yes',
                        'aspirin': data.get('allergy_aspirin') == 'yes',
                        'latex': data.get('allergy_latex') == 'yes',
                        'others': data.get('allergy_others', '').strip()
                    },
                    'women_health': {
                        'pregnant': data.get('pregnant') == 'yes',
                        'nursing': data.get('nursing') == 'yes',
                        'birth_control': data.get('birth_control') == 'yes'
                    },
                    'vital_signs': {
                        'blood_type': data.get('blood_type', '').strip(),
                        'blood_pressure': data.get('blood_pressure', '').strip(),
                        'bleeding_time': data.get('bleeding_time', '').strip()
                    },
                    'medical_conditions': create_medical_conditions_from_form(data)
                },
                'created_at': datetime.utcnow(),
                'updated_at': datetime.utcnow(),
                'is_active': True
            }
            
            result = mongo.db.patients.insert_one(patient_data)
            create_default_dental_chart(str(result.inserted_id))
            
            if request.is_json:
                return jsonify({'success': True, 'patient_id': str(result.inserted_id)})
            
            patient_name = f'{patient_data["personal_info"]["first_name"]} {patient_data["personal_info"]["last_name"]}'
            flash(f'Patient {patient_name} added successfully!', 'success')
            return redirect(url_for('patients_fallback'))
            
        except Exception as e:
            print(f"DEBUG: Error creating patient: {e}")
            flash('Failed to create patient. Please try again.', 'error')
            user_clinics = list(mongo.db.clinics.find({'owner_id': session['user_id'], 'is_active': True}))
            return render_template('patients/create.html', clinics=user_clinics, form_data=data)
    
    # GET request - show form
    user_clinics = list(mongo.db.clinics.find({'owner_id': session['user_id'], 'is_active': True}))
    
    if not user_clinics:
        flash('You need to create a clinic first before adding patients.', 'warning')
        return redirect(url_for('create_clinic_fallback'))
    
    return render_template('patients/create.html', clinics=user_clinics, form_data={})

def create_medical_conditions_from_form(data):
    """Extract medical conditions from form data"""
    conditions = [
        'high_blood_pressure', 'heart_disease', 'cancer_tumors',
        'low_blood_pressure', 'heart_murmur', 'anemia',
        'epilepsy', 'hepatitis_liver', 'angina',
        'aids_hiv', 'rheumatic_fever', 'asthma',
        'std', 'allergies_general', 'emphysema',
        'stomach_ulcer', 'respiratory', 'bleeding_problems',
        'fainting_seizures', 'hepatitis_jaundice', 'blood_disease',
        'weight_loss', 'tuberculosis', 'head_injuries',
        'radiation_therapy', 'swollen_ankles', 'arthritis',
        'joint_replacement', 'kidney_disease', 'heart_surgery',
        'diabetes', 'heart_attack', 'chest_pain',
        'thyroid_problem', 'stroke'
    ]
    
    medical_conditions = {}
    for condition in conditions:
        medical_conditions[condition] = data.get(f'condition_{condition}') == 'yes'
    
    medical_conditions['other'] = data.get('condition_other', '').strip()
    return medical_conditions

def create_default_dental_chart(patient_id):
    """Create a default dental chart for a new patient"""
    try:
        teeth_status = {}
        
        # Adult teeth (1-32)
        for i in range(1, 33):
            teeth_status[f"tooth_{i}"] = {
                "status": "present",
                "restorations": [],
                "conditions": [],
                "notes": ""
            }
        
        chart_data = {
            "patient_id": ObjectId(patient_id),
            "chart_date": datetime.utcnow(),
            "teeth_status": teeth_status,
            "created_by": session['user_id'],
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }
        
        mongo.db.dental_charts.insert_one(chart_data)
        
    except Exception as e:
        print(f"Error creating dental chart: {e}")

@app.route('/patients_fallback/<patient_id>')
@login_required
def patient_detail_fallback(patient_id):
    """View patient details - fallback route"""
    try:
        patient = mongo.db.patients.find_one({'_id': ObjectId(patient_id)})
        
        if not patient:
            flash('Patient not found', 'error')
            return redirect(url_for('patients_fallback'))
        
        # Verify clinic ownership
        clinic = mongo.db.clinics.find_one({
            '_id': patient['clinic_id'],
            'owner_id': session['user_id']
        })
        
        if not clinic:
            flash('Access denied', 'error')
            return redirect(url_for('patients_fallback'))
        
        # Get dental chart
        dental_chart = mongo.db.dental_charts.find_one({'patient_id': ObjectId(patient_id)})
        
        # Get treatment records
        treatment_records = list(mongo.db.treatment_records.find({
            'patient_id': ObjectId(patient_id)
        }).sort('date', -1).limit(10))
        
        # Get patient's appointments
        patient_appointments = list(mongo.db.appointments.find({
            'patient_id': ObjectId(patient_id),
            'is_active': True
        }).sort([('date', -1), ('time', -1)]).limit(10))
        
        return render_template('patients/detail.html', 
                             patient=patient, 
                             clinic=clinic,
                             dental_chart=dental_chart,
                             treatment_records=treatment_records,
                             appointments=patient_appointments)
                             
    except Exception as e:
        print(f"Patient detail error: {e}")
        flash('Error loading patient details', 'error')
        return redirect(url_for('patients_fallback'))

# Create route aliases for easier template usage
@app.route('/patients')
@login_required
def patients():
    return patients_fallback()

@app.route('/patients/create', methods=['GET', 'POST'])
@login_required
def create_patient():
    return create_patient_fallback()

@app.route('/patients/<patient_id>')
@login_required
def patient_detail(patient_id):
    return patient_detail_fallback(patient_id)

@app.route('/clinics')
@login_required
def clinics():
    return clinics_fallback()

@app.route('/clinics/create', methods=['GET', 'POST'])
@login_required
def create_clinic():
    return create_clinic_fallback()

@app.route('/appointments')
@login_required
def appointments():
    return appointments_fallback()


@app.route('/patients_fallback')
@login_required
def patients_fallback():
    """Fallback patients list route"""
    try:
        # Get user's clinics
        user_clinics = list(mongo.db.clinics.find({
            'owner_id': session['user_id'],
            'is_active': True
        }))
        clinic_ids = [clinic['_id'] for clinic in user_clinics]
        
        # Get search parameters
        search_query = request.args.get('search', '')
        clinic_id = request.args.get('clinic_id')
        
        # Build query
        query = {'is_active': True}
        if clinic_id:
            query['clinic_id'] = ObjectId(clinic_id)
        else:
            query['clinic_id'] = {'$in': clinic_ids}
        
        # Add search functionality
        if search_query:
            query['$or'] = [
                {'personal_info.first_name': {'$regex': search_query, '$options': 'i'}},
                {'personal_info.last_name': {'$regex': search_query, '$options': 'i'}},
                {'personal_info.nickname': {'$regex': search_query, '$options': 'i'}},
                {'contact_info.cell_phone': {'$regex': search_query, '$options': 'i'}}
            ]
        
        patients = list(mongo.db.patients.find(query).sort('created_at', -1).limit(50))
        
        return render_template('patients/list.html',
                             patients=patients,
                             clinics=user_clinics,
                             current_page=1,
                             total_pages=1,
                             selected_clinic=clinic_id,
                             search_query=search_query)
    except Exception as e:
        print(f"Patients error: {e}")
        flash('Error loading patients', 'error')
        return render_template('patients/list.html',
                             patients=[],
                             clinics=[],
                             current_page=1,
                             total_pages=1,
                             selected_clinic=None,
                             search_query='')

# Error handlers
@app.errorhandler(404)
def not_found(error):
    return render_template('errors/404.html'), 404

@app.errorhandler(500)
def internal_error(error):
    return render_template('errors/500.html'), 500

# Initialize database function
def init_database():
    """Initialize database with indexes and default admin user"""
    try:
        # Create indexes
        mongo.db.users.create_index("email", unique=True)
        mongo.db.users.create_index("license_number")
        mongo.db.clinics.create_index("owner_id")
        mongo.db.patients.create_index("clinic_id")
        mongo.db.appointments.create_index([("clinic_id", 1), ("date", 1), ("time", 1)])
        mongo.db.appointments.create_index("patient_id")
        mongo.db.dental_charts.create_index("patient_id")
        
        # Create default admin user if none exists
        if mongo.db.users.count_documents({}) == 0:
            admin_user = {
                "name": "Admin User",
                "email": "admin@dental.com",
                "password": generate_password_hash("admin123"),
                "license_number": "ADMIN001",
                "specialty": "General Dentistry",
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
                "is_active": True
            }
            
            result = mongo.db.users.insert_one(admin_user)
            print(f"Created admin user with ID: {result.inserted_id}")
            print("Login with: admin@dental.com / admin123")
            
    except Exception as e:
        print(f"Database initialization error: {e}")

# Health check route
@app.route('/health')
def health_check():
    """Health check endpoint"""
    try:
        # Test database connection
        mongo.db.command('ping')
        return jsonify({"status": "healthy", "database": "connected"}), 200
    except Exception as e:
        return jsonify({"status": "unhealthy", "error": str(e)}), 500

@app.context_processor
def inject_route_helpers():
    """Inject helper functions into all templates"""
    
    def safe_url_for(endpoint, **values):
        """Safely generate URLs with fallback routes"""
        try:
            return url_for(endpoint, **values)
        except:
            # Try fallback routes
            fallback_map = {
                'create_clinic': 'create_clinic_fallback',
                'clinics': 'clinics_fallback', 
                'patients': 'patients_fallback',
                'create_patient': 'create_patient_fallback',
                'appointments': 'appointments_fallback',
                'patient_detail': 'patient_detail_fallback'
            }
            
            fallback_endpoint = fallback_map.get(endpoint)
            if fallback_endpoint:
                try:
                    return url_for(fallback_endpoint, **values)
                except:
                    pass
            
            # If all else fails, return a safe default
            return '#'
    
    def check_blueprint_available(blueprint_name):
        """Check if a blueprint is available"""
        return blueprint_name in app.blueprints
    
    return dict(
        safe_url_for=safe_url_for,
        check_blueprint_available=check_blueprint_available
    )

if __name__ == '__main__':
    with app.app_context():
        init_database()
    app.run(debug=True, host='0.0.0.0', port=5000)