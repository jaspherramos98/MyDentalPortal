# File: MyDentalPortal/blueprints/repositories/clinics.py
# Clinic reads. Thin wrapper over mongo.db.
#
# Two scoping concepts, kept distinct on purpose:
#   * owned_*  -> clinics a user OWNS (dentist). Use for clinic management
#                 (create/edit/delete, settings) — staff must NOT widen this.
#   * accessible_ids -> clinics a user may WORK IN: owned + via staff membership.
#                 Use for patient/appointment listing scope (the access seam).

import re

from bson.errors import InvalidId
from bson.objectid import ObjectId

from extensions import mongo
from blueprints.repositories import memberships as _membership_repo
from blueprints.clock import utcnow


def owned_by(owner_id, active_only=True):
    """All clinics owned by owner_id (active only by default)."""
    query = {'owner_id': owner_id}
    if active_only:
        query['is_active'] = True
    return list(mongo.db.clinics.find(query))


def owned_ids(owner_id):
    """ObjectIds of the owner's active clinics."""
    return [
        c['_id'] for c in
        mongo.db.clinics.find({'owner_id': owner_id, 'is_active': True}, {'_id': 1})
    ]


def accessible_ids(user_id):
    """ObjectIds of all active clinics this user may work in: the ones they own
    (dentist) PLUS the ones owned by any dentist they're a staff member of.

    The multi-staff listing seam (``utils.user_clinic_ids`` delegates here). With
    no memberships this equals ``owned_ids(user_id)`` — existing single-dentist
    behaviour is unchanged."""
    owner_ids = _membership_repo.accessible_owner_ids(user_id)
    return [
        c['_id'] for c in
        mongo.db.clinics.find(
            {'owner_id': {'$in': owner_ids}, 'is_active': True}, {'_id': 1}
        )
    ]


def _oid(value):
    """ObjectId from an ObjectId or its string form; None if malformed."""
    if isinstance(value, ObjectId):
        return value
    try:
        return ObjectId(value)
    except (InvalidId, TypeError):
        return None


def get_owned(clinic_id, owner_id):
    """A single clinic only if owner_id owns it; else None (also for a malformed id).

    True-OWNERSHIP check — use for clinic management. For "may this user work in
    this clinic?" (patients/appointments), use get_accessible."""
    oid = _oid(clinic_id)
    if oid is None:
        return None
    return mongo.db.clinics.find_one({'_id': oid, 'owner_id': owner_id})


def get_accessible(clinic_id, user_id):
    """A single clinic only if the user may WORK IN it — owns it (dentist) or is a
    staff member of its owning dentist. The accessible counterpart to get_owned.
    With no memberships this equals get_owned (so existing behaviour is unchanged)."""
    return mongo.db.clinics.find_one({
        '_id': clinic_id,
        'owner_id': {'$in': _membership_repo.accessible_owner_ids(user_id)},
    })


def accessible_active(user_id):
    """Active clinics the user may work in (owned + via membership), sorted by name.
    The accessible counterpart to search_owned (listings + dropdowns)."""
    owner_ids = _membership_repo.accessible_owner_ids(user_id)
    return list(
        mongo.db.clinics
        .find({'owner_id': {'$in': owner_ids}, 'is_active': True})
        .sort('name', 1)
    )


def search_owned(owner_id, search=''):
    """The owner's active clinics, name-sorted, optionally filtered by a literal
    (re.escape) match on name or address."""
    query = {'owner_id': owner_id, 'is_active': True}
    if search:
        safe_q = re.escape(search)
        query['$or'] = [
            {'name': {'$regex': safe_q, '$options': 'i'}},
            {'address': {'$regex': safe_q, '$options': 'i'}},
        ]
    return list(mongo.db.clinics.find(query).sort('name', 1))


def insert(doc):
    """Insert a clinic document; returns its ObjectId."""
    return mongo.db.clinics.insert_one(doc).inserted_id


def update_owned(clinic_id, owner_id, fields):
    """$set ``fields`` on a clinic the owner owns. True if it matched."""
    oid = _oid(clinic_id)
    if oid is None:
        return False
    result = mongo.db.clinics.update_one(
        {'_id': oid, 'owner_id': owner_id},
        {'$set': dict(fields, updated_at=utcnow())},
    )
    return result.matched_count == 1


def deactivate_owned(clinic_id, owner_id):
    """Soft-delete a clinic the owner owns. True if it matched."""
    return update_owned(clinic_id, owner_id, {'is_active': False})
