# File: MyDentalPortal/blueprints/repositories/submissions.py
# Idempotent creates for resilient form submits.
#
# static/js/resilient-submit.js retries a POST whose response was lost, and
# every create form carries a client-generated `submission_id`. Storing it on
# the new record (unique partial index) turns a retry into "return the record
# the first attempt already made" instead of a duplicate patient/treatment/file.

from pymongo.errors import DuplicateKeyError

from extensions import mongo

# Collections whose create routes accept a submission_id.
COLLECTIONS = ('patients', 'treatment_records', 'clinics', 'prescriptions', 'patient_files')


def ensure_indexes():
    """Unique on submission_id where present (legacy docs without it are fine)."""
    for name in COLLECTIONS:
        mongo.db[name].create_index(
            'submission_id', unique=True,
            partialFilterExpression={'submission_id': {'$type': 'string'}},
        )


def find(collection, submission_id, created_by):
    """The record this submission already created ({'_id'} only), or None.
    Scoped to the creator so an id can never reach someone else's record."""
    if not submission_id:
        return None
    return mongo.db[collection].find_one(
        {'submission_id': submission_id, 'created_by': created_by}, {'_id': 1},
    )


def create_once(collection, submission_id, created_by, insert):
    """Run ``insert()`` (which must store ``submission_id`` on the doc) unless this
    submission already created a record. Returns ``(record_id, created)``.

    A concurrent duplicate (two copies of one retry racing) hits the unique
    index; the loser returns the winner's id with ``created=False``.
    """
    existing = find(collection, submission_id, created_by)
    if existing:
        return existing['_id'], False
    try:
        return insert(), True
    except DuplicateKeyError:
        existing = find(collection, submission_id, created_by)
        if not existing:
            raise
        return existing['_id'], False
