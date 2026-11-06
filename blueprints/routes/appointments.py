# File: MyDentalPortal/app/routes/appointments.py
# Appointment management routes — calendar + CRUD API

import logging
import re

from flask import (
    Blueprint, render_template, request, jsonify,
    session, redirect, url_for, flash, current_app,
)
from bson.objectid import ObjectId
from datetime import datetime, timedelta

from blueprints.utils import (
    login_required, user_clinic_ids as _user_clinic_ids, scoped_clinic_ids, audit,
    verify_patient_access, submission_id, can_confirm_price,
)
from blueprints.repositories import appointments as appt_repo
from blueprints.repositories import clinics as clinic_repo
from blueprints.repositories import patients as patient_repo
from blueprints.repositories import treatments as treatment_repo
from blueprints.repositories import submissions as submissions_repo
from blueprints.clock import utcnow, clinic_today
from blueprints import treatment_records, visit_links, visits

appointments_bp = Blueprint('appointments', __name__)
log = logging.getLogger(__name__)

# Server-side allowlists — never trust client-supplied enums.
ALLOWED_TYPES = {
    'checkup', 'cleaning', 'filling', 'extraction',
    'emergency', 'follow-up', 'surgery', 'orthodontic', 'others',
}
# Statuses the calendar may set directly. `completed` is only reached through
# "Complete visit" (saving a treatment linked to the appointment), so a visit is
# never marked done without the record of what was done.
SETTABLE_STATUSES = {'scheduled', 'cancelled', 'no-show'}
STATUS_AUDIT_ACTIONS = {'cancelled': 'cancel', 'no-show': 'no_show', 'scheduled': 'reopen'}

HISTORY_PAGE_SIZE = 50
HISTORY_DEFAULT_DAYS = 30
HISTORY_MAX_DAYS = 366       # bounds one list query (filtered/paginated in Python)
HISTORY_STATUS_FILTERS = {
    # filter value -> statuses fetched from the DB (attention is narrowed after)
    '': None,
    'completed': ['completed'],
    'cancelled': ['cancelled'],
    'no-show': ['no-show'],
    'scheduled': ['scheduled'],
    'attention': ['scheduled', 'completed'],
}
ALLOWED_PRIORITIES = {'normal', 'high', 'urgent'}


def _today_str():
    """Today's date as 'YYYY-MM-DD' in the clinic's timezone (for date bounds)."""
    return clinic_today(current_app.config.get('TIMEZONE', 'Asia/Manila'))


def _visit_url(appt):
    """Where a finished visit's banner/row leads: the patient's Treatment tab
    with this visit's records highlighted. None when no patient is linked."""
    if not appt.get('patient_id'):
        return None
    return url_for('patients.patient_detail', patient_id=str(appt['patient_id']),
                   tab='treatment', visit=str(appt['_id']), _anchor='treatment-history')


def _visits_for(appts, today):
    """``{appointment_id_str: Visit}`` for a batch, with one treatment query."""
    linked = treatment_repo.by_appointment([a['_id'] for a in appts])
    return {
        str(a['_id']): visits.summarize(a, linked.get(str(a['_id']), []), today)
        for a in appts
    }


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

    for other in appt_repo.find_active_on_day(clinic_id, date, exclude_id):
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
        user_clinics = clinic_repo.accessible_active(session['user_id'])
        if not user_clinics:
            flash('Create a clinic first before managing appointments.', 'warning')
            return redirect(url_for('clinics.create_clinic'))

        clinic_ids = [c['_id'] for c in user_clinics]
        patients = patient_repo.active_in_clinics(clinic_ids)

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
            clinics_json=[
                {'id': str(c['_id']), 'name': c.get('name', ''), 'address': c.get('address') or ''}
                for c in user_clinics
            ],
        )
    except Exception:
        log.exception("Appointments page failed")
        flash('Error loading appointments page', 'error')
        return redirect(url_for('main.dashboard'))


# ── API: list ────────────────────────────────────────────────────────────
@appointments_bp.route('/appointments/api', methods=['GET'])
@login_required
def get_appointments():
    try:
        if not _user_clinic_ids():
            return jsonify({'success': False, 'error': 'No clinics found'}), 403
        clinic_ids = scoped_clinic_ids(request.args.get('clinic_id'))

        start = request.args.get('start_date')
        end = request.args.get('end_date')

        if not (start and end):
            today = datetime.now()
            ws = today - timedelta(days=today.weekday())
            we = ws + timedelta(days=6)
            start, end = ws.strftime('%Y-%m-%d'), we.strftime('%Y-%m-%d')

        appts = appt_repo.find_in_range(clinic_ids, start, end)
        today = _today_str()
        visit_by_id = _visits_for(appts, today)
        out = []
        for a in appts:
            visit = visit_by_id[str(a['_id'])]
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
                # Visit outcome for the calendar banner. Amounts are deliberately
                # NOT sent: the calendar may face patients (owner decision), so
                # they live in the list view only.
                'visit': {
                    'state': visit.state,
                    'status_label': visit.status_label,
                    'reasons': visit.reasons,
                    'procedures': visit.procedures,
                    'url': _visit_url(a),
                },
                'can_complete': (a.get('status', 'scheduled') in ('scheduled', 'completed')
                                 and a['date'] <= today),
            })
        return jsonify({'success': True, 'appointments': out, 'total': len(out),
                        'today': today})
    except Exception:
        log.exception("Get appointments failed")
        return jsonify({'success': False, 'error': 'Could not load appointments.'}), 500


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

        clinic = clinic_repo.get_accessible(ObjectId(data['clinic_id']), session['user_id'])
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
            'created_at': utcnow(),
            'updated_at': utcnow(),
            'is_active': True,
        }
        if data.get('patient_id'):
            try:
                appt['patient_id'] = ObjectId(data['patient_id'])
            except Exception:
                pass

        appt_id = appt_repo.insert(appt)
        audit('create', 'appointment', appt_id, clinic=clinic)
        return jsonify({
            'success': True,
            'appointment_id': appt_id,
            'message': f'Appointment scheduled at {clinic["name"]}',
        })
    except Exception:
        log.exception("Create appointment failed")
        return jsonify({'success': False, 'error': 'Failed to create appointment'}), 500


# ── API: update ──────────────────────────────────────────────────────────
@appointments_bp.route('/appointments/api/<appt_id>', methods=['PUT'])
@login_required
def update_appointment(appt_id):
    try:
        data = request.get_json()
        appt = appt_repo.get(appt_id)
        if not appt:
            return jsonify({'success': False, 'error': 'Not found'}), 404

        clinic = clinic_repo.get_accessible(appt['clinic_id'], session['user_id'])
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
        new_status = data.get('status')
        status_changes = new_status is not None and new_status != appt.get('status', 'scheduled')
        if status_changes:
            error = _status_change_error(appt, new_status)
            if error:
                return jsonify({'success': False, 'error': error}), 400
        if 'priority' in data and data['priority'] not in ALLOWED_PRIORITIES:
            return jsonify({'success': False, 'error': 'Invalid priority'}), 400

        update = {'updated_at': utcnow()}
        for field in ['patient_name', 'date', 'time', 'duration', 'type',
                       'priority', 'notes', 'status']:
            if field in data:
                val = data[field]
                if field == 'duration':
                    val = int(val)
                elif field in ('patient_name', 'notes'):
                    val = val.strip()
                update[field] = val

        appt_repo.update_set(appt_id, update)
        action = STATUS_AUDIT_ACTIONS.get(new_status, 'update') if status_changes else 'update'
        audit(action, 'appointment', appt_id, clinic=clinic)
        return jsonify({'success': True, 'message': 'Updated'})
    except Exception:
        log.exception("Update appointment failed")
        return jsonify({'success': False, 'error': 'Update failed'}), 500


def _status_change_error(appt, new_status):
    """Why `appt` may not move to `new_status` (None = allowed)."""
    if new_status not in SETTABLE_STATUSES:
        return 'Invalid status'
    if new_status == 'no-show' and appt['date'] > _today_str():
        return "A future appointment can't be a no-show."
    if appt.get('status') == 'completed' and treatment_repo.by_appointment([appt['_id']]):
        return 'This visit has treatment records. Edit those instead.'
    return None


# ── Record visit (the calendar's one-step dialog) ────────────────────────
# Everything needed to finish a past/today visit without leaving the calendar:
# pick the patient (typed-in walk-ins), claim records already entered for it,
# and/or add what was done. Saving marks the visit completed.
def _visit_context(appt_id, patient_id_arg):
    """(appt, visit_clinic, patient, patient_clinic, error) for the visit
    endpoints. `error` is a (message, status) pair; patient is None for a
    walk-in whose patient hasn't been picked yet."""
    appt = appt_repo.get(appt_id)
    vclinic = visit_links.visit_clinic(appt, session['user_id'])
    if not vclinic:
        return None, None, None, None, ('Appointment not found.', 404)
    if appt.get('patient_id') and patient_id_arg and str(patient_id_arg) != str(appt['patient_id']):
        return appt, vclinic, None, None, ('This appointment is booked for a different patient.', 400)
    patient_id = appt.get('patient_id') or patient_id_arg
    if not patient_id:
        return appt, vclinic, None, None, None
    patient, pclinic = verify_patient_access(str(patient_id))
    if not pclinic:
        return appt, vclinic, None, None, ('Patient not found.', 404)
    why = visit_links.refusal(appt, patient, session['user_id'], _today_str())
    if why:
        return appt, vclinic, patient, pclinic, (why, 400)
    return appt, vclinic, patient, pclinic, None


def _patient_name(patient):
    info = patient.get('personal_info') or {}
    return f"{info.get('first_name', '')} {info.get('last_name', '')}".strip()


def _visit_json(visit, appt=None):
    out = {'state': visit.state, 'status_label': visit.status_label,
           'reasons': visit.reasons, 'procedures': visit.procedures}
    if appt is not None:
        out['url'] = _visit_url(appt)
    return out


@appointments_bp.route('/appointments/api/<appt_id>/visit', methods=['GET'])
@login_required
def visit_details(appt_id):
    """What the Record-visit dialog shows. No amounts (calendar screen)."""
    appt, vclinic, patient, pclinic, error = _visit_context(appt_id, request.args.get('patient_id'))
    if error:
        return jsonify({'success': False, 'error': error[0]}), error[1]
    today = _today_str()
    visit = _visits_for([appt], today)[str(appt['_id'])]
    candidates = []
    if patient:
        candidates = [
            {'id': str(t['_id']), 'date': t.get('date', ''), 'procedure': t.get('procedure', '')}
            for t in visit_links.link_candidates(appt, patient['_id'], today)
        ]
    return jsonify({
        'success': True,
        'appointment': {
            'id': str(appt['_id']), 'date': appt['date'], 'time': appt.get('time', ''),
            'status': appt.get('status', 'scheduled'), 'clinic_name': vclinic.get('name', ''),
            'patient_name': appt.get('patient_name', ''),
            'has_patient': bool(appt.get('patient_id')),
        },
        'patient': {'id': str(patient['_id']), 'name': _patient_name(patient)} if patient else None,
        'visit': _visit_json(visit),
        'candidates': candidates,
        'currency': (pclinic or vclinic).get('currency', 'PHP'),
        'price_needs_confirmation': not can_confirm_price(),
        'procedures': list(treatment_records.PROCEDURES),
        'full_form_url': url_for('treatments.add_treatment', patient_id=str(patient['_id']),
                                 appointment_id=str(appt['_id'])) if patient else None,
    })


@appointments_bp.route('/appointments/api/<appt_id>/visit', methods=['POST'])
@login_required
def record_visit(appt_id):
    """Link chosen existing records and/or create one, then complete the visit.

    JSON: {patient_id?, link: [treatment ids], treatment: {procedure,
    tooth_numbers, amount_charged, amount_paid, notes} | null, submission_id?}
    """
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({'success': False, 'error': 'Invalid request.'}), 400
    appt, vclinic, patient, pclinic, error = _visit_context(appt_id, data.get('patient_id'))
    if error:
        return jsonify({'success': False, 'error': error[0]}), error[1]
    if not patient:
        return jsonify({'success': False, 'error': 'Pick which patient this visit was for.'}), 400

    today = _today_str()
    link_ids = data.get('link') or []
    entry = data.get('treatment')
    if not isinstance(link_ids, list) or (entry is not None and not isinstance(entry, dict)):
        return jsonify({'success': False, 'error': 'Invalid request.'}), 400
    allowed = {str(t['_id']) for t in visit_links.link_candidates(appt, patient['_id'], today)}
    link_ids = list(dict.fromkeys(str(t) for t in link_ids))
    if any(t not in allowed for t in link_ids):
        return jsonify({'success': False,
                        'error': 'One of those records can no longer be linked. Reopen the visit.'}), 400

    new_doc = None
    if entry:
        values = {k: entry.get(k) for k in
                  ('procedure', 'tooth_numbers', 'amount_charged', 'amount_paid', 'notes')}
        values['date'] = appt['date']   # the record is for the day of the visit
        try:
            new_doc = treatment_records.new_treatment(
                values, patient['_id'], pclinic, session['user_id'],
                session.get('user_name', ''), can_confirm_price(), today)
        except treatment_records.TreatmentInputError as e:
            return jsonify({'success': False, 'error': str(e)}), 400
    if not link_ids and not new_doc:
        return jsonify({'success': False,
                        'error': 'Tick a record above or enter what was done.'}), 400

    try:
        if new_doc:
            new_doc['appointment_id'] = appt['_id']
            sid = submission_id(data)
            if sid:
                new_doc['submission_id'] = sid
            tid, created = submissions_repo.create_once(
                'treatment_records', sid, session['user_id'],
                lambda: treatment_repo.insert(new_doc))
            if created:
                audit('create', 'treatment', tid, clinic=pclinic)
                if not new_doc['price_confirmed']:
                    audit('price_proposed', 'treatment', tid, clinic=pclinic)
        if link_ids:
            treatment_repo.link_to_appointment(link_ids, appt['_id'], patient['_id'])
            for tid in link_ids:
                audit('link_visit', 'treatment', tid, clinic=pclinic)
        visit_links.complete(appt, patient, vclinic)
        appt = appt_repo.get(appt_id)
        visit = _visits_for([appt], today)[str(appt['_id'])]
        return jsonify({'success': True, 'visit': _visit_json(visit, appt)})
    except Exception:
        log.exception("Record visit failed")
        return jsonify({'success': False, 'error': 'Could not save the visit. Try again.'}), 500


# ── Visit history (list view) ────────────────────────────────────────────
def _parse_day(value):
    try:
        return datetime.strptime(value or '', '%Y-%m-%d').date()
    except ValueError:
        return None


def _history_range(args, today):
    """(start, end) 'YYYY-MM-DD' from the query string; defaults to the last
    HISTORY_DEFAULT_DAYS, swapped if reversed, capped at HISTORY_MAX_DAYS."""
    end = _parse_day(args.get('end')) or _parse_day(today)
    start = _parse_day(args.get('start')) or (end - timedelta(days=HISTORY_DEFAULT_DAYS))
    if start > end:
        start, end = end, start
    if (end - start).days > HISTORY_MAX_DAYS:
        start = end - timedelta(days=HISTORY_MAX_DAYS)
    return start.isoformat(), end.isoformat()


def _page_number(value):
    try:
        return max(int(value), 1)
    except (TypeError, ValueError):
        return 1


@appointments_bp.route('/appointments/history')
@login_required
def history():
    """Visit history: appointments in a date range as a filterable list with
    procedures and amounts. Read-only; scoped to the user's accessible clinics
    (a ?clinic_id= filter can only narrow that scope)."""
    try:
        user_clinics = clinic_repo.accessible_active(session['user_id'])
        clinics_by_id = {c['_id']: c for c in user_clinics}
        today = _today_str()
        start, end = _history_range(request.args, today)
        status_filter = request.args.get('status', '')
        if status_filter not in HISTORY_STATUS_FILTERS:
            status_filter = ''
        query = (request.args.get('q') or '').strip()[:100]
        clinic_ids = scoped_clinic_ids(request.args.get('clinic_id'))

        appts = []
        if clinic_ids:
            appts = appt_repo.find_history(
                clinic_ids, start, end,
                statuses=HISTORY_STATUS_FILTERS[status_filter],
                name_pattern=re.escape(query) if query else None,
            )
        visit_by_id = _visits_for(appts, today)
        rows = []
        for a in appts:
            visit = visit_by_id[str(a['_id'])]
            if status_filter == 'attention' and visit.state != visits.STATE_ATTENTION:
                continue
            clinic = clinics_by_id.get(a['clinic_id'], {})
            rows.append({'appt': a, 'visit': visit, 'url': _visit_url(a),
                         'clinic_name': clinic.get('name', ''),
                         'currency': clinic.get('currency', 'PHP')})

        pages = max((len(rows) + HISTORY_PAGE_SIZE - 1) // HISTORY_PAGE_SIZE, 1)
        page = min(_page_number(request.args.get('page')), pages)
        page_rows = rows[(page - 1) * HISTORY_PAGE_SIZE: page * HISTORY_PAGE_SIZE]

        filters = {'start': start, 'end': end, 'status': status_filter, 'q': query,
                   'clinic_id': request.args.get('clinic_id', '')}
        return render_template(
            'appointments/history.html',
            rows=page_rows, total=len(rows), page=page, pages=pages,
            filters=filters, clinics=user_clinics,
        )
    except Exception:
        log.exception("Visit history failed")
        flash('Could not load visit history.', 'error')
        return redirect(url_for('appointments.appointments'))


# ── API: delete ──────────────────────────────────────────────────────────
@appointments_bp.route('/appointments/api/<appt_id>', methods=['DELETE'])
@login_required
def delete_appointment(appt_id):
    try:
        appt = appt_repo.get(appt_id)
        if not appt:
            return jsonify({'success': False, 'error': 'Not found'}), 404

        clinic = clinic_repo.get_accessible(appt['clinic_id'], session['user_id'])
        if not clinic:
            return jsonify({'success': False, 'error': 'Access denied'}), 403

        appt_repo.soft_delete(appt_id)
        audit('delete', 'appointment', appt_id, clinic=clinic)
        return jsonify({'success': True, 'message': 'Deleted'})
    except Exception:
        log.exception("Delete appointment failed")
        return jsonify({'success': False, 'error': 'Delete failed'}), 500
