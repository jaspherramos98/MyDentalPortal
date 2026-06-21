# File: MyDentalPortal/blueprints/repositories/memberships.py
# The `memberships` collection: links a staff user to a dentist (clinic owner).
#
# This is the multi-staff access primitive. A staff member linked to a dentist
# gets access to ALL clinics that dentist owns (per-clinic scoping is a later
# extension). `clinics.accessible_ids` and `patients.get_for_accessor` build on
# `accessible_owner_ids` below — that's the single place "who can I act as?" is
# computed, so widening/narrowing access later happens here.
#
# IDs are stored as strings to match the rest of the app (session['user_id'] and
# clinics.owner_id are str(ObjectId), not ObjectId).

from datetime import datetime

from bson.objectid import ObjectId
from bson.errors import InvalidId

from extensions import mongo


def dentist_ids_for(user_id):
    """Dentist (owner) ids this user is an ACTIVE staff member of."""
    return [
        m['dentist_id'] for m in
        mongo.db.memberships.find(
            {'user_id': user_id, 'is_active': True}, {'dentist_id': 1}
        )
    ]


def accessible_owner_ids(user_id):
    """Clinic-owner ids whose clinics this user may access: themselves (as a
    dentist over their own clinics) plus every dentist they're an active staff
    member of. With no memberships this is just ``[user_id]`` — so existing
    single-dentist behaviour is unchanged."""
    return [user_id, *dentist_ids_for(user_id)]


def create(user_id, dentist_id, role='staff', created_by=None):
    """Link a staff user to a dentist; returns the new _id."""
    return mongo.db.memberships.insert_one({
        'user_id': user_id,
        'dentist_id': dentist_id,
        'role': role,
        'is_active': True,
        'created_by': created_by,
        'created_at': datetime.utcnow(),
    }).inserted_id


def list_for_dentist(dentist_id, active_only=True):
    """All memberships linked to a dentist (staff list / admin panel)."""
    query = {'dentist_id': dentist_id}
    if active_only:
        query['is_active'] = True
    return list(mongo.db.memberships.find(query))


def deactivate(user_id, dentist_id):
    """Soft-revoke a staff link (keep the row for the audit trail)."""
    return mongo.db.memberships.update_one(
        {'user_id': user_id, 'dentist_id': dentist_id},
        {'$set': {'is_active': False, 'revoked_at': datetime.utcnow()}},
    )


def get(membership_id):
    """One membership by id, or None for a missing/malformed id."""
    try:
        return mongo.db.memberships.find_one({'_id': ObjectId(membership_id)})
    except (InvalidId, TypeError):
        return None


def revoke_by_id(membership_id):
    """Soft-revoke a membership by its _id (admin panel). Returns UpdateResult."""
    try:
        oid = ObjectId(membership_id)
    except (InvalidId, TypeError):
        return None
    return mongo.db.memberships.update_one(
        {'_id': oid},
        {'$set': {'is_active': False, 'revoked_at': datetime.utcnow()}},
    )
