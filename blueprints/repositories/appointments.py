# File: MyDentalPortal/blueprints/repositories/appointments.py
# Appointment reads/writes. Thin wrapper over mongo.db — no behaviour change.
# Access control (does this owner own the clinic?) stays in the route via
# clinics_repo; this module only holds the raw appointment queries.


from bson.objectid import ObjectId
from bson.errors import InvalidId

from extensions import mongo
from blueprints.clock import utcnow


def get(appt_id):
    """Find one appointment by id. Returns None for a missing/malformed id."""
    try:
        return mongo.db.appointments.find_one({'_id': ObjectId(appt_id)})
    except (InvalidId, TypeError):
        return None


def find_in_range(clinic_ids, start, end):
    """Active appointments in `clinic_ids` for the calendar, sorted by (date, time).

    Callers narrow `clinic_ids` themselves (``utils.scoped_clinic_ids``) — this
    never widens scope from request input. `start`/`end` are 'YYYY-MM-DD' strings.
    """
    query = {
        'is_active': True,
        'clinic_id': {'$in': clinic_ids},
        'date': {'$gte': start, '$lte': end},
    }
    return list(mongo.db.appointments.find(query).sort([('date', 1), ('time', 1)]))


def find_history(clinic_ids, start, end, statuses=None, name_pattern=None):
    """Active appointments in `clinic_ids` within ['YYYY-MM-DD' start, end] for
    the visit-history list, newest first.

    `statuses` optionally narrows to those status values; `name_pattern` is an
    ALREADY-ESCAPED regex (callers ``re.escape`` user input) matched
    case-insensitively against ``patient_name``. Callers bound the date range,
    so the result size stays small at clinic volume.
    """
    query = {
        'is_active': True,
        'clinic_id': {'$in': clinic_ids},
        'date': {'$gte': start, '$lte': end},
    }
    if statuses:
        query['status'] = {'$in': list(statuses)}
    if name_pattern:
        query['patient_name'] = {'$regex': name_pattern, '$options': 'i'}
    return list(mongo.db.appointments.find(query).sort([('date', -1), ('time', -1)]))


def find_active_on_day(clinic_id, date, exclude_id=None):
    """Active, non-cancelled appointments in one clinic on one day.

    Used by the route's overlap check (the interval math stays in the route).
    """
    query = {
        'clinic_id': clinic_id if isinstance(clinic_id, ObjectId) else ObjectId(clinic_id),
        'date': date,
        'is_active': True,
        'status': {'$ne': 'cancelled'},
    }
    if exclude_id:
        query['_id'] = {'$ne': ObjectId(exclude_id)}
    return list(mongo.db.appointments.find(query))


def find_active_on_date(clinic_ids, date):
    """Active, non-cancelled appointments across `clinic_ids` on one day,
    sorted by time (dashboard "today")."""
    return list(
        mongo.db.appointments.find({
            'clinic_id': {'$in': clinic_ids},
            'date': date,
            'is_active': True,
            'status': {'$ne': 'cancelled'},
        }).sort('time', 1)
    )


def find_upcoming(clinic_ids, start, end, limit=10):
    """Active, non-cancelled appointments across `clinic_ids` in the date range
    ['YYYY-MM-DD' start, end], sorted by (date, time), capped at `limit`
    (dashboard "upcoming")."""
    return list(
        mongo.db.appointments.find({
            'clinic_id': {'$in': clinic_ids},
            'date': {'$gte': start, '$lte': end},
            'is_active': True,
            'status': {'$ne': 'cancelled'},
        }).sort([('date', 1), ('time', 1)]).limit(limit)
    )


def count_active_in_range(clinic_ids, start, end):
    """Count active, non-cancelled appointments across `clinic_ids` in the date
    range ['YYYY-MM-DD' start, end] (dashboard "this week")."""
    return mongo.db.appointments.count_documents({
        'clinic_id': {'$in': clinic_ids},
        'date': {'$gte': start, '$lte': end},
        'is_active': True,
        'status': {'$ne': 'cancelled'},
    })


def insert(doc):
    """Insert an appointment document; return the new _id (str)."""
    return str(mongo.db.appointments.insert_one(doc).inserted_id)


def update_set(appt_id, fields):
    """Apply a ``$set`` to one appointment."""
    return mongo.db.appointments.update_one(
        {'_id': ObjectId(appt_id)},
        {'$set': fields},
    )


def mark_completed(appt_id, patient_id=None):
    """Set an appointment ``completed`` (the visit happened). `patient_id` links
    a typed-in walk-in to the registered patient it turned out to be."""
    fields = {'status': 'completed', 'completed_at': utcnow(), 'updated_at': utcnow()}
    if patient_id is not None:
        fields['patient_id'] = patient_id if isinstance(patient_id, ObjectId) else ObjectId(patient_id)
    return update_set(appt_id, fields)


def soft_delete(appt_id):
    """Soft-delete: mark inactive + stamp deleted_at (keeps the record)."""
    return mongo.db.appointments.update_one(
        {'_id': ObjectId(appt_id)},
        {'$set': {'is_active': False, 'deleted_at': utcnow()}},
    )


def active_for_patient(patient_id, limit=10):
    """A patient's active appointments, most recent first (detail page)."""
    return list(
        mongo.db.appointments
        .find({'patient_id': ObjectId(patient_id), 'is_active': True})
        .sort([('date', -1), ('time', -1)])
        .limit(limit)
    )


def open_for_patient(patient_id, clinic_ids, start, end):
    """A patient's still-'scheduled' active visits dated start..end in the given
    clinics, most recent first (Add Treatment offers to complete one)."""
    return list(
        mongo.db.appointments
        .find({'patient_id': ObjectId(patient_id), 'is_active': True,
               'status': {'$in': ['scheduled', None]},  # None = legacy, no status
               'clinic_id': {'$in': list(clinic_ids)},
               'date': {'$gte': start, '$lte': end}})
        .sort([('date', -1), ('time', -1)])
    )
