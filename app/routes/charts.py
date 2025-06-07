# File: dental-portal/app/routes/charts.py
# Updated dental chart routes

from flask import Blueprint, render_template, request, jsonify, session, redirect, url_for, flash
from bson.objectid import ObjectId
from datetime import datetime
from functools import wraps

from app_factory import mongo

charts_bp = Blueprint('charts', __name__, url_prefix='/charts')

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def create_default_dental_chart(patient_id):
    """Create a default dental chart structure for a new patient"""
    teeth_status = {}
    
    # Adult teeth (permanent teeth using FDI numbering)
    permanent_teeth = [
        # Upper right: 18-11
        18, 17, 16, 15, 14, 13, 12, 11,
        # Upper left: 21-28  
        21, 22, 23, 24, 25, 26, 27, 28,
        # Lower left: 38-31
        38, 37, 36, 35, 34, 33, 32, 31,
        # Lower right: 41-48
        41, 42, 43, 44, 45, 46, 47, 48
    ]
    
    for tooth_num in permanent_teeth:
        teeth_status[str(tooth_num)] = {
            "notes": "",
            "colors": {}
        }
    
    # Temporary teeth
    temporary_teeth = [55, 54, 53, 52, 51, 61, 62, 63, 64, 65, 85, 84, 83, 82, 81, 71, 72, 73, 74, 75]
    for tooth_num in temporary_teeth:
        teeth_status[f"temp_{tooth_num}"] = {
            "notes": "",
            "colors": {}
        }
    
    return {
        "patient_id": ObjectId(patient_id),
        "chart_date": datetime.utcnow(),
        "teeth_status": teeth_status,
        "periodontal_screening": {
            "gingivitis": False,
            "early_periodontitis": False,
            "moderate_periodontitis": False,
            "advanced_periodontitis": False
        },
        "occlusion": {
            "class_molar": "",
            "overjet": "",
            "overbite": "",
            "midline_deviation": "",
            "crossbite": False
        },
        "appliances": {
            "orthodontic": False,
            "stayplate": False,
            "others": ""
        },
        "tmd_assessment": {
            "clenching": False,
            "clicking": False,
            "trismus": False,
            "muscle_spasm": False
        },
        "xray_taken": {
            "periapical": {"taken": False, "tooth_number": "", "date": ""},
            "panoramic": {"taken": False, "date": ""},
            "cephalometric": {"taken": False, "date": ""},
            "occlusal": {"taken": False, "upper_lower": "", "date": ""},
            "others": {"taken": False, "type": "", "date": ""}
        },
        "created_by": session['user_id'],
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow()
    }

@charts_bp.route('/patient/<patient_id>')
@login_required
def view_chart(patient_id):
    """View dental chart for a patient"""
    try:
        # Verify patient access
        patient = mongo.db.patients.find_one({'_id': ObjectId(patient_id)})
        if not patient:
            flash('Patient not found', 'error')
            return redirect(url_for('patients_fallback'))
        
        clinic = mongo.db.clinics.find_one({
            '_id': patient['clinic_id'],
            'owner_id': session['user_id']
        })
        
        if not clinic:
            flash('Access denied', 'error')
            return redirect(url_for('patients_fallback'))
        
        # Get or create dental chart
        dental_chart = mongo.db.dental_charts.find_one({'patient_id': ObjectId(patient_id)})
        
        if not dental_chart:
            # Create default chart
            chart_data = create_default_dental_chart(patient_id)
            result = mongo.db.dental_charts.insert_one(chart_data)
            dental_chart = mongo.db.dental_charts.find_one({'_id': result.inserted_id})
        
        # Prepare chart data for template
        chart_data_json = {}
        if dental_chart:
            # Convert ObjectId to string for JSON serialization
            chart_data_copy = dental_chart.copy()
            if '_id' in chart_data_copy:
                chart_data_copy['_id'] = str(chart_data_copy['_id'])
            if 'patient_id' in chart_data_copy:
                chart_data_copy['patient_id'] = str(chart_data_copy['patient_id'])
            chart_data_json = chart_data_copy
        
        return render_template('charts/dental_chart.html', 
                             patient=patient, 
                             dental_chart=dental_chart,
                             chart_data=chart_data_json,
                             clinic=clinic)
                             
    except Exception as e:
        print(f"Dental chart error: {e}")
        flash('Error loading dental chart', 'error')
        return redirect(url_for('patients_fallback'))

@charts_bp.route('/update/<patient_id>', methods=['POST'])
@login_required
def update_chart(patient_id):
    """Update dental chart data"""
    try:
        # Verify patient access
        patient = mongo.db.patients.find_one({'_id': ObjectId(patient_id)})
        if not patient:
            return jsonify({'success': False, 'error': 'Patient not found'}), 404
        
        clinic = mongo.db.clinics.find_one({
            '_id': patient['clinic_id'],
            'owner_id': session['user_id']
        })
        
        if not clinic:
            return jsonify({'success': False, 'error': 'Access denied'}), 403
        
        data = request.get_json()
        
        # Update the entire chart data
        mongo.db.dental_charts.update_one(
            {'patient_id': ObjectId(patient_id)},
            {
                '$set': {
                    **data,
                    'updated_at': datetime.utcnow(),
                    'updated_by': session['user_id']
                }
            },
            upsert=True
        )
        
        return jsonify({'success': True, 'message': 'Chart updated successfully'})
        
    except Exception as e:
        print(f"Chart update error: {e}")
        return jsonify({'success': False, 'error': 'Failed to update chart'}), 500