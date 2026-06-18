# File: MyDentalPortal/blueprints/repositories/uploads.py
# Upload storage: GridFS blobs + the `prescriptions` and `patient_files`
# metadata collections. Thin wrapper over mongo.db / GridFS — no behaviour change.
#
# Validation (extension/magic-byte/decode) and access control
# (verify_patient_access) stay in the route; this module only holds the raw
# storage + collection queries that used to be inline.

from bson.objectid import ObjectId
from bson.errors import InvalidId
from gridfs import GridFS

from extensions import mongo


# ── GridFS blob storage ──────────────────────────────────────────────────────
def _fs():
    return GridFS(mongo.db)


def put_blob(data, filename, content_type):
    """Persist bytes to GridFS; return the new GridFS id."""
    return _fs().put(data, filename=filename, contentType=content_type)


def get_blob(file_id):
    """Return the GridFS file object for streaming, or None if it's missing."""
    try:
        return _fs().get(file_id)
    except Exception:
        return None


def delete_blob(file_id):
    """Best-effort delete of a GridFS blob — never raises (orphan cleanup)."""
    if not file_id:
        return
    try:
        _fs().delete(file_id)
    except Exception:
        pass


# ── prescriptions ────────────────────────────────────────────────────────────
def get_prescription(prescription_id):
    """Find one prescription by id. None for a missing/malformed id."""
    try:
        return mongo.db.prescriptions.find_one({'_id': ObjectId(prescription_id)})
    except (InvalidId, TypeError):
        return None


def insert_prescription(doc):
    """Insert a prescription document; return the new _id (str)."""
    return str(mongo.db.prescriptions.insert_one(doc).inserted_id)


def delete_prescription(prescription_id):
    """Hard-delete one prescription record."""
    return mongo.db.prescriptions.delete_one({'_id': ObjectId(prescription_id)})


# ── patient files ────────────────────────────────────────────────────────────
def get_file(file_doc_id):
    """Find one patient-file metadata doc by id. None for a missing/malformed id."""
    try:
        return mongo.db.patient_files.find_one({'_id': ObjectId(file_doc_id)})
    except (InvalidId, TypeError):
        return None


def insert_file(doc):
    """Insert a patient-file metadata document; return the new _id (str)."""
    return str(mongo.db.patient_files.insert_one(doc).inserted_id)


def update_file_set(file_doc_id, fields):
    """Apply a ``$set`` to one patient-file metadata doc (e.g. rename)."""
    return mongo.db.patient_files.update_one(
        {'_id': ObjectId(file_doc_id)},
        {'$set': fields},
    )


def delete_file(file_doc_id):
    """Hard-delete one patient-file metadata record."""
    return mongo.db.patient_files.delete_one({'_id': ObjectId(file_doc_id)})
