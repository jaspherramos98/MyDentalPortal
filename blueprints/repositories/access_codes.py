# File: MyDentalPortal/blueprints/repositories/access_codes.py
# Staff access codes: a dentist generates a single-use, expiring code and shares
# it with a new staff member, who consumes it at registration to be linked
# (membership) to that dentist. The code IS the vetting for staff (no separate
# admin approval) — so treat it like a secret.
#
# Codes are stored HASHED (sha256). The plaintext is shown to the dentist exactly
# once, at generation, and is never recoverable. sha256 (unsalted) is appropriate
# here precisely because the code is a high-entropy random token, not a
# user-chosen password — it stays queryable for a fast single-use lookup.

import hashlib
import secrets
from datetime import datetime, timedelta

from bson.objectid import ObjectId
from bson.errors import InvalidId

from extensions import mongo

DEFAULT_TTL_DAYS = 7


def _hash(code):
    return hashlib.sha256(code.strip().encode('utf-8')).hexdigest()


def generate(dentist_id, created_by, ttl_days=DEFAULT_TTL_DAYS):
    """Create a single-use staff code for a dentist. Returns the PLAINTEXT code
    (show it once — only its hash is stored)."""
    code = secrets.token_urlsafe(9)
    mongo.db.access_codes.insert_one({
        'code_hash': _hash(code),
        'dentist_id': dentist_id,
        'role': 'staff',
        'expires_at': datetime.utcnow() + timedelta(days=ttl_days),
        'used': False,
        'used_by': None,
        'used_at': None,
        'revoked': False,
        'created_by': created_by,
        'created_at': datetime.utcnow(),
    })
    return code


def consume(code, used_by):
    """Atomically validate + spend a code. Returns the code doc (incl. dentist_id)
    if it was valid (unused, unrevoked, unexpired); None otherwise. Single-use:
    the same code can never be consumed twice."""
    return mongo.db.access_codes.find_one_and_update(
        {
            'code_hash': _hash(code),
            'used': False,
            'revoked': {'$ne': True},
            'expires_at': {'$gt': datetime.utcnow()},
        },
        {'$set': {'used': True, 'used_by': used_by, 'used_at': datetime.utcnow()}},
        return_document=True,
    )


def list_for_dentist(dentist_id):
    """All of a dentist's codes, newest first (metadata only — never the code)."""
    return list(
        mongo.db.access_codes.find({'dentist_id': dentist_id}).sort('created_at', -1)
    )


def revoke(code_id, dentist_id):
    """Revoke an unused code owned by this dentist. Returns the UpdateResult."""
    try:
        oid = ObjectId(code_id)
    except (InvalidId, TypeError):
        return None
    return mongo.db.access_codes.update_one(
        {'_id': oid, 'dentist_id': dentist_id, 'used': False},
        {'$set': {'revoked': True, 'revoked_at': datetime.utcnow()}},
    )
