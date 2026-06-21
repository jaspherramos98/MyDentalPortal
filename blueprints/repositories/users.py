# File: MyDentalPortal/blueprints/repositories/users.py
# User-account reads/writes. Thin wrapper over mongo.db — no behaviour change.
# This is the `users` collection seam: auth (login/register), admin (approvals +
# user management), and account settings all go through here. Multi-staff/roles
# work will extend THIS module (membership, role changes) rather than re-querying
# the driver across blueprints.

from bson.objectid import ObjectId
from bson.errors import InvalidId

from extensions import mongo


def get(user_id):
    """Find a user by id. Returns None for a missing/malformed id."""
    try:
        return mongo.db.users.find_one({'_id': ObjectId(user_id)})
    except (InvalidId, TypeError):
        return None


def get_by_email(email):
    """Find a user by email (exact match), or None."""
    return mongo.db.users.find_one({'email': email})


def create(doc):
    """Insert a user document; return the new _id (str)."""
    return str(mongo.db.users.insert_one(doc).inserted_id)


def delete(user_id):
    """Hard-delete a user (used to roll back a half-finished staff signup when the
    access code turns out invalid). Returns the DeleteResult."""
    try:
        return mongo.db.users.delete_one({'_id': ObjectId(user_id)})
    except (InvalidId, TypeError):
        return None


def update_set(user_id, fields):
    """Apply a ``$set`` to one user (by _id). Returns the UpdateResult so callers
    can inspect matched_count (e.g. admin password reset)."""
    return mongo.db.users.update_one(
        {'_id': ObjectId(user_id)},
        {'$set': fields},
    )


def list_by_status(status):
    """Users with the given lifecycle status, newest first (admin approvals)."""
    return list(mongo.db.users.find({'status': status}).sort('created_at', -1))


def list_all_no_password():
    """All users with the password field projected out, newest first (admin)."""
    return list(mongo.db.users.find({}, {'password': 0}).sort('created_at', -1))


def set_status_if_pending(user_id, new_status, extra=None):
    """Move a *pending* account to new_status (approve/reject).

    The `status: 'pending'` filter preserves the route's guard: a non-pending
    account is never re-approved/re-rejected. Returns the UpdateResult.
    """
    fields = {'status': new_status}
    if extra:
        fields.update(extra)
    return mongo.db.users.update_one(
        {'_id': ObjectId(user_id), 'status': 'pending'},
        {'$set': fields},
    )
