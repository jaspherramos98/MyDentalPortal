# File: MyDentalPortal/blueprints/routes/deletions.py
# Deletion-request workflow: staff (who can't delete directly — see PR B) can
# REQUEST deletion of a record; a dentist/admin reviews the queue and approves
# (performs the delete) or rejects. Generic across patient/treatment/prescription/
# file/photo. Everything is audited.

from datetime import datetime

from flask import (
    Blueprint, render_template, request, session, redirect, url_for, flash,
)

from blueprints.utils import (
    login_required, role_required, ROLE_DENTIST, is_admin,
    verify_patient_access, audit,
)
from blueprints.repositories import deletion_requests as dr_repo
from blueprints.repositories import patients as patient_repo
from blueprints.repositories import treatments as treatment_repo
from blueprints.repositories import uploads as uploads_repo
from blueprints.repositories import users as user_repo

deletions_bp = Blueprint('deletions', __name__)

ALLOWED_ENTITIES = {'patient', 'treatment', 'prescription', 'file', 'photo'}
ENTITY_LABEL = {
    'patient': 'Patient record', 'treatment': 'Treatment record',
    'prescription': 'Prescription', 'file': 'Patient file', 'photo': 'Patient photo',
}


def _resolve(entity_type, entity_id):
    """Return (clinic, patient_id) for an entity the CURRENT user may access (via
    the membership-aware verify_patient_access), or (None, None) if missing/denied."""
    pid = None
    if entity_type in ('patient', 'photo'):
        pid = entity_id
    elif entity_type == 'treatment':
        t = treatment_repo.get(entity_id)
        pid = str(t['patient_id']) if t else None
    elif entity_type == 'prescription':
        p = uploads_repo.get_prescription(entity_id)
        pid = str(p['patient_id']) if p else None
    elif entity_type == 'file':
        m = uploads_repo.get_file(entity_id)
        pid = str(m['patient_id']) if m else None
    if not pid:
        return None, None
    _, clinic = verify_patient_access(pid)
    return clinic, pid


def _perform_delete(entity_type, entity_id):
    """Actually delete the entity — mirrors the direct delete routes' behaviour."""
    if entity_type == 'patient':
        patient_repo.update_set(entity_id, {'is_active': False, 'updated_at': datetime.utcnow()})
    elif entity_type == 'photo':
        patient = patient_repo.get(entity_id)
        if patient:
            uploads_repo.delete_blob(patient.get('photo_file_id'))
            patient_repo.unset(entity_id, ['photo_file_id', 'photo_ext', 'photo_content_type'])
    elif entity_type == 'treatment':
        treatment_repo.delete(entity_id)
    elif entity_type == 'prescription':
        p = uploads_repo.get_prescription(entity_id)
        if p:
            uploads_repo.delete_blob(p.get('image_file_id'))
            uploads_repo.delete_prescription(p['_id'])
    elif entity_type == 'file':
        m = uploads_repo.get_file(entity_id)
        if m:
            uploads_repo.delete_blob(m['file_id'])
            uploads_repo.delete_file(m['_id'])


@deletions_bp.route('/deletions/request', methods=['POST'])
@login_required
def request_deletion():
    """Staff (or anyone with access) requests deletion of a record."""
    entity_type = (request.form.get('entity_type') or '').strip()
    entity_id = (request.form.get('entity_id') or '').strip()
    if entity_type not in ALLOWED_ENTITIES or not entity_id:
        flash('Invalid deletion request.', 'error')
        return redirect(url_for('patients.list_patients'))

    clinic, patient_id = _resolve(entity_type, entity_id)
    if not clinic:
        flash('Access denied or record not found.', 'error')
        return redirect(url_for('patients.list_patients'))

    dr_repo.create(entity_type, entity_id, clinic['_id'], clinic.get('owner_id'),
                   session['user_id'])
    audit('request_deletion', entity_type, entity_id, clinic=clinic)
    flash('Deletion requested. A dentist will review it.', 'success')
    return redirect(url_for('patients.patient_detail', patient_id=patient_id))


@deletions_bp.route('/deletions')
@role_required(ROLE_DENTIST)
def queue():
    """Dentist/admin review queue. Dentist sees their clinics' pending requests;
    admin sees all."""
    rows = dr_repo.list_pending_all() if is_admin() \
        else dr_repo.list_pending_for_dentist(session['user_id'])
    name_cache = {}

    def name_of(uid):
        if uid not in name_cache:
            u = user_repo.get(uid)
            name_cache[uid] = (u.get('name') or u.get('email') or uid) if u else uid
        return name_cache[uid]

    for r in rows:
        r['label'] = ENTITY_LABEL.get(r['entity_type'], r['entity_type'])
        r['requested_by_name'] = name_of(r.get('requested_by'))
    return render_template('deletions/queue.html', requests=rows)


def _owns_request(req):
    """A dentist may only resolve requests for their own clinics; admin: any."""
    return is_admin() or req.get('dentist_id') == session['user_id']


@deletions_bp.route('/deletions/<request_id>/approve', methods=['POST'])
@role_required(ROLE_DENTIST)
def approve(request_id):
    req = dr_repo.get(request_id)
    if not req or not _owns_request(req):
        flash('Request not found or access denied.', 'error')
        return redirect(url_for('deletions.queue'))
    result = dr_repo.resolve(request_id, 'approved', session['user_id'])
    if result and result.modified_count:
        _perform_delete(req['entity_type'], req['entity_id'])
        audit('approve_deletion', req['entity_type'], req['entity_id'],
              clinic={'_id': req.get('clinic_id'), 'owner_id': req.get('dentist_id')})
        audit('delete', req['entity_type'], req['entity_id'],
              clinic={'_id': req.get('clinic_id'), 'owner_id': req.get('dentist_id')})
        flash('Deletion approved and applied.', 'success')
    else:
        flash('Request already resolved.', 'warning')
    return redirect(url_for('deletions.queue'))


@deletions_bp.route('/deletions/<request_id>/reject', methods=['POST'])
@role_required(ROLE_DENTIST)
def reject(request_id):
    req = dr_repo.get(request_id)
    if not req or not _owns_request(req):
        flash('Request not found or access denied.', 'error')
        return redirect(url_for('deletions.queue'))
    result = dr_repo.resolve(request_id, 'rejected', session['user_id'])
    if result and result.modified_count:
        audit('reject_deletion', req['entity_type'], req['entity_id'],
              clinic={'_id': req.get('clinic_id'), 'owner_id': req.get('dentist_id')})
        flash('Deletion request rejected.', 'info')
    else:
        flash('Request already resolved.', 'warning')
    return redirect(url_for('deletions.queue'))
