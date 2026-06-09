# File: MyDentalPortal/app/routes/charts.py
# Dental chart routes — FDI numbering, cross layout
# *** THIS MODULE IS CRITICAL — DO NOT MODIFY CHART LOGIC ***

from flask import (
    Blueprint, render_template, request, jsonify,
    session, redirect, url_for, flash,
)
from bson.objectid import ObjectId
from datetime import datetime
import traceback

from extensions import mongo
from blueprints.utils import login_required

charts_bp = Blueprint('charts', __name__)


def create_default_dental_chart(patient_id):
    """Create a default dental chart structure for a new patient.
    Uses FDI (ISO 3950) numbering — standard in the Philippines.
    """
    teeth_status = {}

    # Permanent teeth
    permanent_teeth = [
        18, 17, 16, 15, 14, 13, 12, 11,   # Upper right
        21, 22, 23, 24, 25, 26, 27, 28,   # Upper left
        38, 37, 36, 35, 34, 33, 32, 31,   # Lower left
        41, 42, 43, 44, 45, 46, 47, 48,   # Lower right
    ]
    for t in permanent_teeth:
        teeth_status[str(t)] = {"notes": "", "colors": {}}

    # Temporary (deciduous) teeth
    temporary_teeth = [
        55, 54, 53, 52, 51,   # Upper right
        61, 62, 63, 64, 65,   # Upper left
        85, 84, 83, 82, 81,   # Lower right
        71, 72, 73, 74, 75,   # Lower left
    ]
    for t in temporary_teeth:
        teeth_status[f"temp_{t}"] = {"notes": "", "colors": {}}

    return {
        "patient_id": ObjectId(patient_id),
        "chart_date": datetime.utcnow(),
        "teeth_status": teeth_status,
        "periodontal_screening": {
            "gingivitis": False,
            "early_periodontitis": False,
            "moderate_periodontitis": False,
            "advanced_periodontitis": False,
        },
        "occlusion": {
            "class_molar": "",
            "overjet": "",
            "overbite": "",
            "midline_deviation": "",
            "crossbite": False,
        },
        "appliances": {
            "orthodontic": False,
            "stayplate": False,
            "others": "",
        },
        "tmd_assessment": {
            "clenching": False,
            "clicking": False,
            "trismus": False,
            "muscle_spasm": False,
        },
        "xray_taken": {
            "periapical": {"taken": False, "tooth_number": "", "date": ""},
            "panoramic": {"taken": False, "date": ""},
            "cephalometric": {"taken": False, "date": ""},
            "occlusal": {"taken": False, "upper_lower": "", "date": ""},
            "others": {"taken": False, "type": "", "date": ""},
        },
        "created_by": session['user_id'],
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }


@charts_bp.route('/chart/patient/<patient_id>')
@login_required
def view_chart(patient_id):
    """View dental chart for a patient."""
    try:
        patient = mongo.db.patients.find_one({'_id': ObjectId(patient_id)})
        if not patient:
            flash('Patient not found', 'error')
            return redirect(url_for('patients.list_patients'))

        clinic = mongo.db.clinics.find_one({
            '_id': patient['clinic_id'],
            'owner_id': session['user_id'],
        })
        if not clinic:
            flash('Access denied', 'error')
            return redirect(url_for('patients.list_patients'))

        # Get or create dental chart
        dental_chart = mongo.db.dental_charts.find_one(
            {'patient_id': ObjectId(patient_id)}
        )
        if not dental_chart:
            chart_data = create_default_dental_chart(patient_id)
            result = mongo.db.dental_charts.insert_one(chart_data)
            dental_chart = mongo.db.dental_charts.find_one({'_id': result.inserted_id})

        # Prepare JSON-serialisable copy for template
        chart_data_json = {}
        if dental_chart:
            chart_data_json = dental_chart.copy()
            chart_data_json['_id'] = str(chart_data_json['_id'])
            chart_data_json['patient_id'] = str(chart_data_json['patient_id'])
            # Convert datetime objects for JSON
            for key in ('chart_date', 'created_at', 'updated_at'):
                if key in chart_data_json and hasattr(chart_data_json[key], 'isoformat'):
                    chart_data_json[key] = chart_data_json[key].isoformat()

        return render_template(
            'charts/dental_chart.html',
            patient=patient,
            dental_chart=dental_chart,
            chart_data=chart_data_json,
            clinic=clinic,
        )
    except Exception as e:
        print(f"[ERROR] Dental chart: {e}")
        traceback.print_exc()
        flash('Error loading dental chart', 'error')
        return redirect(url_for('patients.list_patients'))


@charts_bp.route('/charts/update/<patient_id>', methods=['POST'])
@charts_bp.route('/chart/update/<patient_id>', methods=['POST'])
@login_required
def update_chart(patient_id):
    """Update dental chart data (called by JS fetch)."""
    try:
        patient = mongo.db.patients.find_one({'_id': ObjectId(patient_id)})
        if not patient:
            return jsonify({'success': False, 'error': 'Patient not found'}), 404

        clinic = mongo.db.clinics.find_one({
            '_id': patient['clinic_id'],
            'owner_id': session['user_id'],
        })
        if not clinic:
            return jsonify({'success': False, 'error': 'Access denied'}), 403

        data = request.get_json()

        # Remove read-only fields that would conflict with MongoDB
        for key in ('_id', 'patient_id', 'created_by', 'created_at'):
            data.pop(key, None)

        mongo.db.dental_charts.update_one(
            {'patient_id': ObjectId(patient_id)},
            {'$set': {
                **data,
                'updated_at': datetime.utcnow(),
                'updated_by': session['user_id'],
            }},
            upsert=True,
        )
        return jsonify({'success': True, 'message': 'Chart updated successfully'})

    except Exception as e:
        print(f"[ERROR] Chart update: {e}")
        traceback.print_exc()
        return jsonify({'success': False, 'error': 'Failed to update chart'}), 500
