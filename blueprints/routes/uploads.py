# File: MyDentalPortal/blueprints/routes/uploads.py
# Prescriptions + patient file attachments.
#
# SECURITY NOTES (this app stores PHI — treat uploads as hostile):
#   * Files are stored in MongoDB GridFS, never on the filesystem and never
#     under /static. They are only retrievable through an authenticated,
#     clinic-ownership-checked download route.
#   * Every upload is validated by BOTH extension allowlist AND magic-byte
#     sniffing; raster images are additionally decode-verified with Pillow.
#   * Downloads are forced as attachments with X-Content-Type-Options: nosniff
#     so the browser will never execute an uploaded file as a script.

import io

from flask import (
    Blueprint, request, session, redirect, url_for, flash, send_file, abort,
)
from bson.objectid import ObjectId
from datetime import datetime
from werkzeug.utils import secure_filename
from PIL import Image

from blueprints.utils import login_required, verify_patient_access as _verify_patient_access
from blueprints.repositories import uploads as uploads_repo
from blueprints.repositories import patients as patient_repo

uploads_bp = Blueprint('uploads', __name__)


# ── allowlists ─────────────────────────────────────────────────────────────
IMAGE_EXTS = {'png', 'jpg', 'jpeg', 'webp', 'heic'}
FILE_EXTS = IMAGE_EXTS | {'pdf', 'docx', 'pages', 'numbers', 'key'}

# Human-friendly description of what's accepted (used in flash messages).
FILE_EXTS_LABEL = 'PNG, JPG, JPEG, WEBP, HEIC, PDF, DOCX, Pages, Numbers, Keynote'
IMAGE_EXTS_LABEL = 'PNG, JPG, JPEG, WEBP, HEIC'

# Content types we are willing to hand back to the browser. Anything not in
# here is downloaded as a generic binary attachment.
CONTENT_TYPES = {
    'png': 'image/png',
    'jpg': 'image/jpeg',
    'jpeg': 'image/jpeg',
    'webp': 'image/webp',
    'heic': 'image/heic',
    'pdf': 'application/pdf',
    'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'pages': 'application/x-iwork-pages-sffpages',
    'numbers': 'application/x-iwork-numbers-sffnumbers',
    'key': 'application/x-iwork-keynote-sffkey',
}


# ── upload validation ────────────────────────────────────────────────────────
def _ext(filename):
    return filename.rsplit('.', 1)[1].lower() if '.' in (filename or '') else ''


def _magic_ok(data, ext):
    """Confirm the file's leading bytes match the claimed extension."""
    sig = data[:16]
    if ext == 'png':
        return sig.startswith(b'\x89PNG\r\n\x1a\n')
    if ext in ('jpg', 'jpeg'):
        return sig.startswith(b'\xff\xd8\xff')
    if ext == 'webp':
        return sig[:4] == b'RIFF' and data[8:12] == b'WEBP'
    if ext == 'heic':
        # ISO-BMFF container: bytes 4-8 are 'ftyp'
        return data[4:8] == b'ftyp'
    if ext == 'pdf':
        return sig.startswith(b'%PDF')
    if ext in ('docx', 'pages', 'numbers', 'key'):
        # OOXML and iWork bundles are ZIP archives.
        return sig.startswith((b'PK\x03\x04', b'PK\x05\x06', b'PK\x07\x08'))
    return False


def _validate(data, ext, allowed):
    """Return (ok, error_message). Validates extension + magic bytes + image decode."""
    if not data:
        return False, 'The uploaded file is empty.'
    if ext not in allowed:
        return False, 'File type not allowed.'
    if not _magic_ok(data, ext):
        return False, "The file contents don't match its extension."
    # Decode-verify true raster images (HEIC needs an extra lib to decode, so
    # we rely on its magic-byte check above).
    if ext in ('png', 'jpg', 'jpeg', 'webp'):
        try:
            Image.open(io.BytesIO(data)).verify()
        except Exception:
            return False, 'The image file is corrupt or not a real image.'
    return True, ''


def _store(data, original_name, ext):
    """Persist bytes to GridFS, return the GridFS id."""
    safe = secure_filename(original_name) or f'upload.{ext}'
    return uploads_repo.put_blob(
        data, safe, CONTENT_TYPES.get(ext, 'application/octet-stream'),
    )


# ── PATIENT PHOTO ────────────────────────────────────────────────────────────
# A single profile photo per patient. Stored in GridFS like every other upload
# (validated image only) and referenced by patient.photo_file_id. Served inline
# but locked to its image content-type with nosniff so it can never execute.
@uploads_bp.route('/patients/<patient_id>/photo', methods=['POST'])
@login_required
def set_photo(patient_id):
    patient, clinic = _verify_patient_access(patient_id)
    if not clinic:
        flash('Access denied or patient not found', 'error')
        return redirect(url_for('patients.list_patients'))

    upload = request.files.get('photo')
    if not upload or not upload.filename:
        flash('Choose an image to upload.', 'error')
        return redirect(url_for('patients.patient_detail', patient_id=patient_id))

    ext = _ext(upload.filename)
    data = upload.read()
    ok, err = _validate(data, ext, IMAGE_EXTS)
    if not ok:
        flash(f'{err} Allowed image types: {IMAGE_EXTS_LABEL}.', 'error')
        return redirect(url_for('patients.patient_detail', patient_id=patient_id))

    # Replace any existing photo (delete the old GridFS blob first).
    uploads_repo.delete_blob(patient.get('photo_file_id'))

    patient_repo.update_set(patient_id, {
        'photo_file_id': _store(data, upload.filename, ext),
        'photo_ext': ext,
        'photo_content_type': CONTENT_TYPES.get(ext, 'application/octet-stream'),
    })
    flash('Patient photo updated.', 'success')
    return redirect(url_for('patients.patient_detail', patient_id=patient_id))


@uploads_bp.route('/patients/<patient_id>/photo')
@login_required
def patient_photo(patient_id):
    _, clinic = _verify_patient_access(patient_id)
    if not clinic:
        abort(403)
    patient = patient_repo.get(patient_id)
    if not patient or not patient.get('photo_file_id'):
        abort(404)
    gf = uploads_repo.get_blob(patient['photo_file_id'])
    if gf is None:
        abort(404)
    # Stream the GridFS object directly instead of buffering the whole file into
    # memory (io.BytesIO(gf.read())). A 2.4 MB iPad photo loaded fully into RAM
    # on every request is what was OOM-killing workers on the 512 MB instance.
    resp = send_file(
        gf,
        mimetype=patient.get('photo_content_type') or getattr(gf, 'contentType', 'image/jpeg'),
        as_attachment=False,
        download_name='patient_photo',
    )
    resp.headers['X-Content-Type-Options'] = 'nosniff'
    # The photo is stable until it's replaced, so let the browser cache it
    # privately. Without this, the patient-detail page re-downloads the full
    # image on every view. PHI -> private (never shared/proxy caches).
    resp.headers['Cache-Control'] = 'private, max-age=300'
    return resp


@uploads_bp.route('/patients/<patient_id>/photo/delete', methods=['POST'])
@login_required
def delete_photo(patient_id):
    patient, clinic = _verify_patient_access(patient_id)
    if not clinic:
        flash('Access denied or patient not found', 'error')
        return redirect(url_for('patients.list_patients'))
    uploads_repo.delete_blob(patient.get('photo_file_id'))
    patient_repo.unset(patient_id, ['photo_file_id', 'photo_ext', 'photo_content_type'])
    flash('Patient photo removed.', 'success')
    return redirect(url_for('patients.patient_detail', patient_id=patient_id))


# ── PRESCRIPTIONS ────────────────────────────────────────────────────────────
@uploads_bp.route('/patients/<patient_id>/prescriptions/add', methods=['POST'])
@login_required
def add_prescription(patient_id):
    patient, clinic = _verify_patient_access(patient_id)
    if not clinic:
        flash('Access denied or patient not found', 'error')
        return redirect(url_for('patients.list_patients'))

    description = (request.form.get('description') or '').strip()
    upload = request.files.get('image')

    if not description and not (upload and upload.filename):
        flash('Add a description or an image for the prescription.', 'error')
        return redirect(url_for('patients.patient_detail', patient_id=patient_id))

    doc = {
        'patient_id': ObjectId(patient_id),
        'clinic_id': clinic['_id'],
        'description': description,
        'image_file_id': None,
        'image_name': None,
        'created_by': session['user_id'],
        'created_at': datetime.utcnow(),
    }

    if upload and upload.filename:
        ext = _ext(upload.filename)
        data = upload.read()
        ok, err = _validate(data, ext, IMAGE_EXTS)
        if not ok:
            flash(f'{err} Allowed image types: {IMAGE_EXTS_LABEL}.', 'error')
            return redirect(url_for('patients.patient_detail', patient_id=patient_id))
        doc['image_file_id'] = _store(data, upload.filename, ext)
        doc['image_name'] = secure_filename(upload.filename)

    uploads_repo.insert_prescription(doc)
    flash('Prescription saved.', 'success')
    return redirect(url_for('patients.patient_detail', patient_id=patient_id))


@uploads_bp.route('/prescriptions/<prescription_id>/image')
@login_required
def prescription_image(prescription_id):
    pres = uploads_repo.get_prescription(prescription_id)
    if not pres or not pres.get('image_file_id'):
        abort(404)
    _, clinic = _verify_patient_access(str(pres['patient_id']))
    if not clinic:
        abort(403)
    gf = uploads_repo.get_blob(pres['image_file_id'])
    if gf is None:
        abort(404)
    # Image preview is inline, but locked to a known image content-type with
    # nosniff so the browser can't be tricked into executing it.
    resp = send_file(
        io.BytesIO(gf.read()),
        mimetype=getattr(gf, 'contentType', 'application/octet-stream'),
        as_attachment=False,
        download_name=pres.get('image_name') or 'image',
    )
    resp.headers['X-Content-Type-Options'] = 'nosniff'
    return resp


@uploads_bp.route('/prescriptions/<prescription_id>/delete', methods=['POST'])
@login_required
def delete_prescription(prescription_id):
    pres = uploads_repo.get_prescription(prescription_id)
    if pres:
        _, clinic = _verify_patient_access(str(pres['patient_id']))
        if clinic:
            uploads_repo.delete_blob(pres.get('image_file_id'))
            uploads_repo.delete_prescription(pres['_id'])
            flash('Prescription deleted.', 'success')
            return redirect(url_for('patients.patient_detail',
                                    patient_id=str(pres['patient_id'])))
    flash('Access denied or prescription not found', 'error')
    return redirect(url_for('patients.list_patients'))


# ── PATIENT FILES ──────────────────────────────────────────────────────────--
@uploads_bp.route('/patients/<patient_id>/files/add', methods=['POST'])
@login_required
def add_file(patient_id):
    patient, clinic = _verify_patient_access(patient_id)
    if not clinic:
        flash('Access denied or patient not found', 'error')
        return redirect(url_for('patients.list_patients'))

    upload = request.files.get('file')
    if not upload or not upload.filename:
        flash('Choose a file to upload.', 'error')
        return redirect(url_for('patients.patient_detail', patient_id=patient_id))

    ext = _ext(upload.filename)
    data = upload.read()
    ok, err = _validate(data, ext, FILE_EXTS)
    if not ok:
        flash(f'{err} Allowed types: {FILE_EXTS_LABEL}.', 'error')
        return redirect(url_for('patients.patient_detail', patient_id=patient_id))

    display_name = (request.form.get('display_name') or '').strip() or upload.filename

    uploads_repo.insert_file({
        'patient_id': ObjectId(patient_id),
        'clinic_id': clinic['_id'],
        'file_id': _store(data, upload.filename, ext),
        'display_name': display_name,
        'ext': ext,
        'size': len(data),
        'content_type': CONTENT_TYPES.get(ext, 'application/octet-stream'),
        'created_by': session['user_id'],
        'created_at': datetime.utcnow(),
    })
    flash('File uploaded.', 'success')
    return redirect(url_for('patients.patient_detail', patient_id=patient_id))


@uploads_bp.route('/files/<file_doc_id>/download')
@login_required
def download_file(file_doc_id):
    meta = uploads_repo.get_file(file_doc_id)
    if not meta:
        abort(404)
    _, clinic = _verify_patient_access(str(meta['patient_id']))
    if not clinic:
        abort(403)
    gf = uploads_repo.get_blob(meta['file_id'])
    if gf is None:
        abort(404)

    # Force a download (never inline) so nothing the user uploaded can run in
    # the browser context. Keep the user's display name + correct extension.
    name = meta.get('display_name') or 'file'
    if not name.lower().endswith('.' + meta['ext']):
        name = f"{name}.{meta['ext']}"
    resp = send_file(
        io.BytesIO(gf.read()),
        mimetype=meta.get('content_type', 'application/octet-stream'),
        as_attachment=True,
        download_name=secure_filename(name),
    )
    resp.headers['X-Content-Type-Options'] = 'nosniff'
    return resp


@uploads_bp.route('/files/<file_doc_id>/rename', methods=['POST'])
@login_required
def rename_file(file_doc_id):
    meta = uploads_repo.get_file(file_doc_id)
    if meta:
        _, clinic = _verify_patient_access(str(meta['patient_id']))
        if clinic:
            new_name = (request.form.get('display_name') or '').strip()
            if new_name:
                uploads_repo.update_file_set(meta['_id'], {'display_name': new_name[:200]})
                flash('File renamed.', 'success')
            else:
                flash('New name cannot be empty.', 'error')
            return redirect(url_for('patients.patient_detail',
                                    patient_id=str(meta['patient_id'])))
    flash('Access denied or file not found', 'error')
    return redirect(url_for('patients.list_patients'))


@uploads_bp.route('/files/<file_doc_id>/delete', methods=['POST'])
@login_required
def delete_file(file_doc_id):
    meta = uploads_repo.get_file(file_doc_id)
    if meta:
        _, clinic = _verify_patient_access(str(meta['patient_id']))
        if clinic:
            uploads_repo.delete_blob(meta['file_id'])
            uploads_repo.delete_file(meta['_id'])
            flash('File deleted.', 'success')
            return redirect(url_for('patients.patient_detail',
                                    patient_id=str(meta['patient_id'])))
    flash('Access denied or file not found', 'error')
    return redirect(url_for('patients.list_patients'))
