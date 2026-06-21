# File: MyDentalPortal/blueprints/repositories/deletion_requests.py
# The `deletion_requests` collection: staff can REQUEST deletion of a record;
# only a dentist/admin actually deletes (approve) or rejects. Same "propose ->
# confirm" shape as pricing + payments. Generic across entity types
# (patient | treatment | prescription | file | photo), keyed by (entity_type,
# entity_id). `dentist_id` is denormalised so the review queue scopes cheaply
# (dentist sees their clinics' requests; admin sees all).

from datetime import datetime

from bson.objectid import ObjectId
from bson.errors import InvalidId

from extensions import mongo


def has_pending(entity_type, entity_id):
    """True if there's already a pending request for this exact record."""
    return mongo.db.deletion_requests.count_documents({
        'entity_type': entity_type, 'entity_id': str(entity_id), 'status': 'pending',
    }) > 0


def create(entity_type, entity_id, clinic_id, dentist_id, requested_by):
    """Create a pending deletion request unless one already exists for the record.
    Returns the _id (new or existing) — never stacks duplicate pendings."""
    entity_id = str(entity_id)
    existing = mongo.db.deletion_requests.find_one({
        'entity_type': entity_type, 'entity_id': entity_id, 'status': 'pending',
    })
    if existing:
        return existing['_id']
    return mongo.db.deletion_requests.insert_one({
        'entity_type': entity_type,
        'entity_id': entity_id,
        'clinic_id': clinic_id,
        'dentist_id': dentist_id,
        'requested_by': requested_by,
        'requested_at': datetime.utcnow(),
        'status': 'pending',
        'resolved_by': None,
        'resolved_at': None,
    }).inserted_id


def get(request_id):
    """One deletion request by id, or None for a missing/malformed id."""
    try:
        return mongo.db.deletion_requests.find_one({'_id': ObjectId(request_id)})
    except (InvalidId, TypeError):
        return None


def list_pending_for_dentist(dentist_id):
    """Pending requests for a dentist's clinics, newest first (their queue)."""
    return list(
        mongo.db.deletion_requests
        .find({'dentist_id': dentist_id, 'status': 'pending'})
        .sort('requested_at', -1)
    )


def list_pending_all():
    """All pending requests, newest first (app-admin queue)."""
    return list(
        mongo.db.deletion_requests.find({'status': 'pending'}).sort('requested_at', -1)
    )


def resolve(request_id, status, resolved_by):
    """Move a *pending* request to approved/rejected. The `status: pending` filter
    means a request is never resolved twice. Returns the UpdateResult."""
    try:
        oid = ObjectId(request_id)
    except (InvalidId, TypeError):
        return None
    return mongo.db.deletion_requests.update_one(
        {'_id': oid, 'status': 'pending'},
        {'$set': {'status': status, 'resolved_by': resolved_by,
                  'resolved_at': datetime.utcnow()}},
    )
