# File: MyDentalPortal/app/routes/appointments.py
# Appointment management routes — calendar + CRUD API

from flask import (
    Blueprint, render_template, request, jsonify,
    session, redirect, url_for, flash,
)
from bson.objectid import ObjectId
from datetime import datetime, timedelta

from extensions import mongo
from blueprints.utils import login_required, user_clinic_ids as _user_clinic_ids

appointments_bp = Blueprint('appointments', __name__)

# Server-side allowlists — never trust client-supplied enums.
ALLOWED_TYPES = {
    'checkup', 'cleaning', 'filling', 'extraction',
    'emergency', 'follow-up', 'surgery',
}
ALLOWED_STATUSES = {'scheduled', 'cancelled', 'completed', 'no-show'}
ALLOWED_PRIORITIES = {'normal', 'high', 'urgent'}


def _today_str():
    """Today's date as 'YYYY-MM-DD' in the clinic's timezone (for date bounds)."""
    try:
        from zoneinfo import ZoneInfo
        from flask import current_app
        tz = ZoneInfo(current_app.config.get('TIMEZONE', 'Asia/Manila'))
        return datetime.now(tz).strftime('%Y-%m-%d')
    except Exception:
        return datetime.now().strftime('%Y-%m-%d')


def _to_minutes(time_str):
    """'HH:MM' -> minutes since midnight, or None if unparseable."""
    try:
        h, m = str(time_str).split(':')
        return int(h) * 60 + int(m)
    except (ValueError, AttributeError):
        return None


def _has_time_conflict(clinic_id, date, time_str, duration, exclude_id=None):
    """True if [time, time+duration) overlaps any active, non-cancelled
    appointment in the same clinic on the same day."""
    start = _to_minutes(time_str)
    if start is None:
        return False
    end = start + int(duration or 30)

    query = {
        'clinic_id': clinic_id if isinstance(clinic_id, ObjectId) else ObjectId(clinic_id),
        'date': date,
        'is_active': True,
        'status': {'$ne': 'cancelled'},
    }
    if exclude_id:
        query['_id'] = {'$ne': ObjectId(exclude_id)}

    for other in mongo.db.appointments.find(query):
        o_start = _to_minutes(other.get('time'))
        if o_start is None:
            continue
        o_end = o_start + int(other.get('duration', 30) or 30)
        # Half-open interval overlap: A starts before B ends, and B starts before A ends.
        if start < o_end and o_start < end:
            return True
    return False


# ── PAGE ─────────────────────────────────────────────────────────────────
@appointments_bp.route('/appointments')
@login_required
def appointments():
    try:
        user_clinics = list(
            mongo.db.clinics.find({'owner_id': session['user_id'], 'is_active': True})
            .sort('name', 1)
        )
        if not user_clinics:
            flash('Create a clinic first before managing appointments.', 'warning')
            return redirect(url_for('clinics.create_clinic'))

        clinic_ids = [c['_id'] for c in user_clinics]
        patients = list(
            mongo.db.patients.find({'clinic_id': {'$in': clinic_ids}, 'is_active': True})
            .sort('personal_info.first_name', 1)
        )

        formatted = []
        for p in patients:
            pi = p.get('personal_info', {})
            ci = p.get('contact_info', {})
            formatted.append({
                'id': str(p['_id']),
                'name': f"{pi.get('first_name', '')} {pi.get('last_name', '')}".strip(),
                'phone': ci.get('cell_phone', ''),
                'clinic_id': str(p['clinic_id']),
            })

        return render_template(
            'appointments.html',
            clinics=user_clinics,
            patients=formatted,
        )
    except Exception as e:
        print(f"Appointments page error: {e}")
        flash('Error loading appointments page', 'error')
        return redirect(url_for('main.dashboard'))


# ── API: list ────────────────────────────────────────────────────────────
@appointments_bp.route('/appointments/api', methods=['GET'])
@login_required
def get_appointments():
    try:
        clinic_ids = _user_clinic_ids()
        if not clinic_ids:
            return jsonify({'success': False, 'error': 'No clinics found'}), 403

        clinic_filter = request.args.get('clinic_id')
        start = request.args.get('start_date')
        end = request.args.get('end_date')

        query = {'is_active': True}
        if clinic_filter:
            query['clinic_id'] = ObjectId(clinic_filter)
        else:
            query['clinic_id'] = {'$in': clinic_ids}

        if start and end:
            query['date'] = {'$gte': start, '$lte': end}
        else:
            today = datetime.now()
            ws = today - timedelta(days=today.weekday())
            we = ws + timedelta(days=6)
            query['date'] = {'$gte': ws.strftime('%Y-%m-%d'), '$lte': we.strftime('%Y-%m-%d')}

        appts = list(mongo.db.appointments.find(query).sort([('date', 1), ('time', 1)]))
        out = []
        for a in appts:
            out.append({
                'id': str(a['_id']),
                'clinic_id': str(a['clinic_id']),
                'patient_id': str(a.get('patient_id', '')),
                'patient_name': a.get('patient_name', ''),
                'date': a['date'],
                'time': a['time'],
                'duration': a.get('duration', 30),
                'type': a.get('type', 'checkup'),
                'priority': a.get('priority', 'normal'),
                'status': a.get('status', 'scheduled'),
                'notes': a.get('notes', ''),
            })
        return jsonify({'success': True, 'appointments': out, 'total': len(out)})
    except Exception as e:
        print(f"Get appointments error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ── API: create ──────────────────────────────────────────────────────────
@appointments_bp.route('/appointments/api', methods=['POST'])
@login_required
def create_appointment():
    try:
        data = request.get_json()
        required = ['patient_name', 'date', 'time', 'clinic_id']
        missing = [f for f in required if not data.get(f)]
        if missing:
            return jsonify({'success': False, 'error': f'Missing: {", ".join(missing)}'}), 400

        # Appointments can't be booked in the past (UI also enforces min=today).
        if str(data['date']) < _today_str():
            return jsonify({'success': False, 'error': 'The appointment date cannot be in the past.'}), 400

        clinic = mongo.db.clinics.find_one({
            '_id': ObjectId(data['clinic_id']),
            'owner_id': session['user_id'],
        })
        if not clinic:
            return jsonify({'success': False, 'error': 'Invalid clinic'}), 403

        # Overlap check honouring duration (cancelled appointments free their slot).
        if _has_time_conflict(data['clinic_id'], data['date'], data['time'],
                              data.get('duration', 30)):
            return jsonify({
                'success': False,
                'error': 'That time overlaps an existing appointment at this clinic.',
            }), 409

        appt_type = data.get('type', 'checkup')
        if appt_type not in ALLOWED_TYPES:
            appt_type = 'checkup'
        priority = data.get('priority', 'normal')
        if priority not in ALLOWED_PRIORITIES:
            priority = 'normal'

        appt = {
            'clinic_id': ObjectId(data['clinic_id']),
            'patient_name': data['patient_name'].strip(),
            'date': data['date'],
            'time': data['time'],
            'duration': int(data.get('duration', 30)),
            'type': appt_type,
            'priority': priority,
            'notes': (data.get('notes') or '').strip(),
            'status': 'scheduled',
            'created_by': session['user_id'],
            'created_at': datetime.utcnow(),
            'updated_at': datetime.utcnow(),
            'is_active': True,
        }
        if data.get('patient_id'):
            try:
                appt['patient_id'] = ObjectId(data['patient_id'])
            except Exception:
                pass

        result = mongo.db.appointments.insert_one(appt)
        return jsonify({
            'success': True,
            'appointment_id': str(result.inserted_id),
            'message': f'Appointment scheduled at {clinic["name"]}',
        })
    except Exception as e:
        print(f"Create appointment error: {e}")
        return jsonify({'success': False, 'error': 'Failed to create appointment'}), 500


# ── API: update ──────────────────────────────────────────────────────────
@appointments_bp.route('/appointments/api/<appt_id>', methods=['PUT'])
@login_required
def update_appointment(appt_id):
    try:
        data = request.get_json()
        appt = mongo.db.appointments.find_one({'_id': ObjectId(appt_id)})
        if not appt:
            return jsonify({'success': False, 'error': 'Not found'}), 404

        clinic = mongo.db.clinics.find_one({
            '_id': appt['clinic_id'], 'owner_id': session['user_id'],
        })
        if not clinic:
            return jsonify({'success': False, 'error': 'Access denied'}), 403

        # Overlap check only when timing actually changes (so a status-only
        # update such as cancel/reactivate is never blocked).
        if any(k in data for k in ('date', 'time', 'duration')):
            new_date = data.get('date', appt['date'])
            new_time = data.get('time', appt['time'])
            new_duration = data.get('duration', appt.get('duration', 30))
            if _has_time_conflict(appt['clinic_id'], new_date, new_time,
                                  new_duration, exclude_id=appt_id):
                return jsonify({
                    'success': False,
                    'error': 'That time overlaps an existing appointment at this clinic.',
                }), 409

        # Validate client-supplied enums before persisting.
        if 'type' in data and data['type'] not in ALLOWED_TYPES:
            return jsonify({'success': False, 'error': 'Invalid appointment type'}), 400
        if 'status' in data and data['status'] not in ALLOWED_STATUSES:
            return jsonify({'success': False, 'error': 'Invalid status'}), 400
        if 'priority' in data and data['priority'] not in ALLOWED_PRIORITIES:
            return jsonify({'success': False, 'error': 'Invalid priority'}), 400

        update = {'updated_at': datetime.utcnow()}
        for field in ['patient_name', 'date', 'time', 'duration', 'type',
                       'priority', 'notes', 'status']:
            if field in data:
                val = data[field]
                if field == 'duration':
                    val = int(val)
                elif field in ('patient_name', 'notes'):
                    val = val.strip()
                update[field] = val

        mongo.db.appointments.update_one({'_id': ObjectId(appt_id)}, {'$set': update})
        return jsonify({'success': True, 'message': 'Updated'})
    except Exception as e:
        print(f"Update appointment error: {e}")
        return jsonify({'success': False, 'error': 'Update failed'}), 500


# ── API: delete ──────────────────────────────────────────────────────────
@appointments_bp.route('/appointments/api/<appt_id>', methods=['DELETE'])
@login_required
def delete_appointment(appt_id):
    try:
        appt = mongo.db.appointments.find_one({'_id': ObjectId(appt_id)})
        if not appt:
            return jsonify({'success': False, 'error': 'Not found'}), 404

        clinic = mongo.db.clinics.find_one({
            '_id': appt['clinic_id'], 'owner_id': session['user_id'],
        })
        if not clinic:
            return jsonify({'success': False, 'error': 'Access denied'}), 403

        mongo.db.appointments.update_one(
            {'_id': ObjectId(appt_id)},
            {'$set': {'is_active': False, 'deleted_at': datetime.utcnow()}},
        )
        return jsonify({'success': True, 'message': 'Deleted'})
    except Exception as e:
        print(f"Delete appointment error: {e}")
        return jsonify({'success': False, 'error': 'Delete failed'}), 500
