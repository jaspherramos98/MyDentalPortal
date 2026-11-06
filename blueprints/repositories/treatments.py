# File: MyDentalPortal/blueprints/repositories/treatments.py
# Treatment-record reads/writes. Thin wrapper over mongo.db — no behaviour change.
# Patient access control stays in the route (verify_patient_access); this module
# only holds the raw treatment_records queries.

from bson.objectid import ObjectId
from bson.errors import InvalidId

from extensions import mongo


def get(treatment_id):
    """Find one treatment by id. Returns None for a missing/malformed id."""
    try:
        return mongo.db.treatment_records.find_one({'_id': ObjectId(treatment_id)})
    except (InvalidId, TypeError):
        return None


def list_for_patient(patient_id, limit=0):
    """Treatments for a patient, newest first (by date). ``limit=0`` means all."""
    return list(
        mongo.db.treatment_records
        .find({'patient_id': ObjectId(patient_id)})
        .sort('date', -1)
        .limit(limit)
    )


def find_for_clinics(clinic_ids, start_date=None, fields=None):
    """Treatments across the given clinics, optionally on/after `start_date`
    (a 'YYYY-MM-DD' string — `date` is stored as that format, so the comparison
    is lexicographic). `fields` is an optional projection. Used by reports."""
    query = {'clinic_id': {'$in': clinic_ids}}
    if start_date:
        query['date'] = {'$gte': start_date}
    return list(mongo.db.treatment_records.find(query, fields))


def find_pending_prices(clinic_ids=None):
    """Treatments whose price is awaiting dentist confirmation (price_confirmed ==
    False). `clinic_ids=None` = all clinics (admin); otherwise scope to those.
    Legacy records (no field) are treated as confirmed, so `== False` deliberately
    excludes them. Newest first."""
    query = {'price_confirmed': False}
    if clinic_ids is not None:
        query['clinic_id'] = {'$in': clinic_ids}
    return list(mongo.db.treatment_records.find(query).sort('date', -1))


def by_appointment(appointment_ids):
    """Treatments linked to the given appointments (``appointment_id``), grouped
    as ``{appointment_id_str: [treatment, ...]}``. One query for a whole
    calendar range / list page. Appointments with no treatments are absent;
    malformed ids (e.g. from a query string) are skipped, not raised."""
    ids = []
    for a in appointment_ids:
        try:
            ids.append(a if isinstance(a, ObjectId) else ObjectId(a))
        except (InvalidId, TypeError):
            continue
    grouped = {}
    if not ids:
        return grouped
    for t in mongo.db.treatment_records.find({'appointment_id': {'$in': ids}}).sort('created_at', 1):
        grouped.setdefault(str(t['appointment_id']), []).append(t)
    return grouped


def insert(doc):
    """Insert a treatment document; return the new _id (str)."""
    return str(mongo.db.treatment_records.insert_one(doc).inserted_id)


def update_set(treatment_id, fields):
    """Apply a ``$set`` to one treatment."""
    return mongo.db.treatment_records.update_one(
        {'_id': ObjectId(treatment_id)},
        {'$set': fields},
    )


def delete(treatment_id):
    """Hard-delete one treatment record."""
    return mongo.db.treatment_records.delete_one({'_id': ObjectId(treatment_id)})
