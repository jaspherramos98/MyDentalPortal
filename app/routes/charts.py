# File: dental-portal/routes/charts.py
# Dental chart routes

from flask import Blueprint, render_template, request, jsonify, session, redirect, url_for, flash
from bson.objectid import ObjectId
from datetime import datetime
from functools import wraps

from app_factory import mongo
from models import DatabaseUtils

charts_bp = Blueprint('charts', __name__, url_prefix='/charts')

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function

@charts_bp.route('/patient/<patient_id>')
@login_required
def view_chart(patient_id):
    """View dental chart for a patient"""
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
    
    # Get or create dental chart
    dental_chart = mongo.db.dental_charts.find_one({'patient_id': ObjectId(patient_id)})
    
    if not dental_chart:
        # Create default chart
        chart_data = DatabaseUtils.create_default_dental_chart(patient_id)
        chart_data['created_by'] = session['user_id']
        result = mongo.db.dental_charts.insert_one(chart_data)
        dental_chart = mongo.db.dental_charts.find_one({'_id': result.inserted_id})
    
    # Get tooth legend
    legend = DatabaseUtils.get_tooth_legend()
    
    return render_template('charts/view.html', 
                         patient=patient, 
                         dental_chart=dental_chart,
                         legend=legend,
                         clinic=clinic)

@charts_bp.route('/update/<patient_id>', methods=['POST'])
@login_required
def update_chart(patient_id):
    """Update dental chart data"""
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
    tooth_id = data.get('tooth_id')
    updates = data.get('updates', {})
    
    if not tooth_id:
        return jsonify({'success': False, 'error': 'Tooth ID required'}), 400
    
    try:
        # Update the specific tooth data
        update_path = f"teeth_status.{tooth_id}"
        mongo.db.dental_charts.update_one(
            {'patient_id': ObjectId(patient_id)},
            {
                '$set': {
                    f"{update_path}.status": updates.get('status', 'present'),
                    f"{update_path}.restorations": updates.get('restorations', []),
                    f"{update_path}.conditions": updates.get('conditions', []),
                    f"{update_path}.notes": updates.get('notes', ''),
                    'updated_at': datetime.utcnow()
                }
            }
        )
        
        return jsonify({'success': True, 'message': 'Chart updated successfully'})
        
    except Exception as e:
        return jsonify({'success': False, 'error': 'Failed to update chart'}), 500

