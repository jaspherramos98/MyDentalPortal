# File: MyDentalPortal/blueprints/repositories/patients.py
# Patient reads + the patient-access seam. Thin wrapper over mongo.db.

from bson.objectid import ObjectId
from bson.errors import InvalidId

from extensions import mongo
from blueprints.models import validate_patient
from blueprints.repositories import memberships as _membership_repo


# Every nested dict the detail/list templates may access — keep in sync with
# templates so a patient missing any section never 500s. (Guardian fields live
# under `minor_info`; there is no separate `guardian_info` section.)
_NESTED_TOP_LEVEL = (
    'personal_info', 'contact_info', 'emergency_contact', 'dental_history',
    'medical_history', 'referral_info', 'minor_info', 'insurance_info',
)
# `conditions` is the key the create/edit forms write and detail.html reads
# (was mistakenly 'medical_conditions' here, which nothing else used — so a
# patient missing the conditions sub-dict could break the detail page).
_MEDICAL_HISTORY_SUBS = (
    'allergies', 'women_health', 'conditions',
    'general_health', 'physician_info', 'vital_signs',
)


def ensure_nested(patient):
    """Ensure all nested dicts exist so templates don't crash on missing keys."""
    for key in _NESTED_TOP_LEVEL:
        if key not in patient or not isinstance(patient[key], dict):
            patient[key] = {}
    mh = patient['medical_history']
    for sub in _MEDICAL_HISTORY_SUBS:
        if sub not in mh or not isinstance(mh.get(sub), dict):
            mh[sub] = {}
    return patient


def get(patient_id):
    """Find a patient by id. Returns None for a missing or malformed id."""
    try:
        return mongo.db.patients.find_one({'_id': ObjectId(patient_id)})
    except (InvalidId, TypeError):
        return None


def active_in_clinics(clinic_ids, sort_field='personal_info.first_name'):
    """Active patients across the given clinics, sorted by `sort_field`."""
    return list(
        mongo.db.patients
        .find({'clinic_id': {'$in': clinic_ids}, 'is_active': True})
        .sort(sort_field, 1)
    )


def get_for_accessor(patient_id, user_id):
    """Return (patient, clinic) if user_id may access the patient — the access seam.

    Access = the patient's clinic is owned by the user (dentist) OR by a dentist
    the user is a staff member of (membership). This is THE single multi-staff
    access check; routes call it via ``utils.verify_patient_access``.

    * (None, None)        -> patient missing or id malformed.
    * (patient, None)     -> patient exists but the user may NOT access its clinic;
                             the caller must treat this as access denied.
    * (patient, clinic)   -> access granted.
    """
    patient = get(patient_id)
    if not patient:
        return None, None
    clinic = mongo.db.clinics.find_one({
        '_id': patient['clinic_id'],
        'owner_id': {'$in': _membership_repo.accessible_owner_ids(user_id)},
    })
    return patient, clinic


def create(data):
    """Validate a patient document at the write boundary, then insert it.

    Raises pydantic ValidationError if the document is malformed (e.g. missing
    or invalid clinic_id). Returns the inserted _id.
    """
    doc = validate_patient(data)
    return mongo.db.patients.insert_one(doc).inserted_id


def update_set(patient_id, fields):
    """Apply a targeted ``$set`` (dot-notation keys) to one patient."""
    return mongo.db.patients.update_one(
        {'_id': ObjectId(patient_id)},
        {'$set': fields},
    )


def unset(patient_id, keys):
    """Remove fields (list of dot-notation keys) from one patient (e.g. photo)."""
    return mongo.db.patients.update_one(
        {'_id': ObjectId(patient_id)},
        {'$unset': {k: '' for k in keys}},
    )


def recent_in_clinics(clinic_ids, limit=10):
    """Active patients across the given clinics, newest first (dashboard)."""
    return list(
        mongo.db.patients
        .find({'clinic_id': {'$in': clinic_ids}, 'is_active': True})
        .sort('created_at', -1)
        .limit(limit)
    )


def count_active_in_clinics(clinic_ids, created_since=None):
    """Count active patients in the given clinics, optionally created on/after
    `created_since` (a datetime). Used by the dashboard stats."""
    query = {'clinic_id': {'$in': clinic_ids}, 'is_active': True}
    if created_since is not None:
        query['created_at'] = {'$gte': created_since}
    return mongo.db.patients.count_documents(query)


def find_active_in_clinics(clinic_ids, created_since=None, fields=None):
    """Active patients in the given clinics, optionally created on/after
    `created_since` (a datetime). `fields` is an optional projection. Used by
    reports (patient-growth time series)."""
    query = {'clinic_id': {'$in': clinic_ids}, 'is_active': True}
    if created_since is not None:
        query['created_at'] = {'$gte': created_since}
    return list(mongo.db.patients.find(query, fields))
