# File: MyDentalPortal/blueprints/repositories/clinics.py
# Clinic reads. Thin wrapper over mongo.db.
#
# Two scoping concepts, kept distinct on purpose:
#   * owned_*  -> clinics a user OWNS (dentist). Use for clinic management
#                 (create/edit/delete, settings) — staff must NOT widen this.
#   * accessible_ids -> clinics a user may WORK IN: owned + via staff membership.
#                 Use for patient/appointment listing scope (the access seam).

from extensions import mongo
from blueprints.repositories import memberships as _membership_repo


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


def owned_active_by_name(owner_id):
    """The owner's active clinics, sorted by name (dashboard + reports)."""
    return list(
        mongo.db.clinics
        .find({'owner_id': owner_id, 'is_active': True})
        .sort('name', 1)
    )


def get_owned(clinic_id, owner_id):
    """A single clinic only if owner_id owns it; else None.

    True-OWNERSHIP check — use for clinic management. For "may this user work in
    this clinic?" (patients/appointments), use get_accessible."""
    return mongo.db.clinics.find_one({'_id': clinic_id, 'owner_id': owner_id})


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
    The accessible counterpart to owned_active_by_name (listings + dropdowns)."""
    owner_ids = _membership_repo.accessible_owner_ids(user_id)
    return list(
        mongo.db.clinics
        .find({'owner_id': {'$in': owner_ids}, 'is_active': True})
        .sort('name', 1)
    )
