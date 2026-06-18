# File: MyDentalPortal/blueprints/repositories/clinics.py
# Clinic reads scoped to an owner. Thin wrapper over mongo.db.

from extensions import mongo


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


def owned_active_by_name(owner_id):
    """The owner's active clinics, sorted by name (dashboard + reports)."""
    return list(
        mongo.db.clinics
        .find({'owner_id': owner_id, 'is_active': True})
        .sort('name', 1)
    )


def get_owned(clinic_id, owner_id):
    """A single clinic only if owner_id owns it; else None."""
    return mongo.db.clinics.find_one({'_id': clinic_id, 'owner_id': owner_id})
