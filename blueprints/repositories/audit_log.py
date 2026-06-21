# File: MyDentalPortal/blueprints/repositories/audit_log.py
# The `audit_log` collection: a DB-backed, PHI-free trail of who did what to
# which record. The source of truth for accountability (NOT Render stdout, which
# is ephemeral / not user-scoped).
#
# PHI HYGIENE — the hard rule: store the *action* and *identifiers*, never the
# values. action/entity_type/entity_id/clinic/actor only. NEVER a patient name,
# medical value, file contents, or free-text note.
#
# `dentist_id` (the owning clinic's owner) is denormalised onto each entry so the
# nested viewer (PR F) can group by dentist cheaply: staff see none, a dentist
# sees their own clinics' activity, an admin sees all grouped by dentist.

from datetime import datetime

from extensions import mongo


def record(action, entity_type, entity_id=None, actor_user_id=None,
           actor_role=None, clinic_id=None, dentist_id=None):
    """Insert one audit entry; returns the new _id. Callers pass explicit args
    (no hidden session reads here — `utils.audit` is the session-aware wrapper)."""
    return mongo.db.audit_log.insert_one({
        'actor_user_id': actor_user_id,
        'actor_role': actor_role,
        'action': action,
        'entity_type': entity_type,
        'entity_id': str(entity_id) if entity_id is not None else None,
        'clinic_id': clinic_id,
        'dentist_id': dentist_id,
        'timestamp': datetime.utcnow(),
    }).inserted_id


def find_for_dentist(dentist_id, limit=100, skip=0):
    """Audit entries owned by a dentist (their clinics), newest first."""
    return list(
        mongo.db.audit_log.find({'dentist_id': dentist_id})
        .sort('timestamp', -1).skip(skip).limit(limit)
    )


def find_all(limit=100, skip=0):
    """All audit entries, newest first (app-admin view)."""
    return list(
        mongo.db.audit_log.find({}).sort('timestamp', -1).skip(skip).limit(limit)
    )
