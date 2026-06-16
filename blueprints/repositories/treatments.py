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


def list_for_patient(patient_id):
    """All treatments for a patient, newest first (by date)."""
    return list(
        mongo.db.treatment_records
        .find({'patient_id': ObjectId(patient_id)})
        .sort('date', -1)
    )


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
