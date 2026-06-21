"""Tests for the audit-log writer (repo + session-aware helper).

Guards the accountability trail and its PHI-hygiene contract: only structured
identifiers are stored, and an audit failure must never break the user's action.
"""
from bson.objectid import ObjectId
from flask import session

from blueprints.repositories import audit_log as audit_repo
from blueprints.utils import audit


# ── repo ──────────────────────────────────────────────────────────────────────
def test_record_stores_structured_fields_only(db):
    actor, dentist, clinic_id = str(ObjectId()), str(ObjectId()), ObjectId()
    eid = audit_repo.record(
        'update', 'patient', 'pid123', actor_user_id=actor, actor_role='staff',
        clinic_id=clinic_id, dentist_id=dentist,
    )
    doc = db.audit_log.find_one({'_id': eid})
    assert doc['action'] == 'update'
    assert doc['entity_type'] == 'patient'
    assert doc['entity_id'] == 'pid123'
    assert doc['actor_user_id'] == actor
    assert doc['actor_role'] == 'staff'
    assert doc['dentist_id'] == dentist
    assert 'timestamp' in doc
    # PHI hygiene: ONLY these keys may ever be stored — no names/values/notes.
    assert set(doc.keys()) == {
        '_id', 'actor_user_id', 'actor_role', 'action',
        'entity_type', 'entity_id', 'clinic_id', 'dentist_id', 'timestamp',
    }


def test_entity_id_coerced_to_str(db):
    oid = ObjectId()
    eid = audit_repo.record('create', 'treatment', oid)
    assert db.audit_log.find_one({'_id': eid})['entity_id'] == str(oid)


def test_find_for_dentist_and_find_all(db):
    d1, d2 = str(ObjectId()), str(ObjectId())
    audit_repo.record('create', 'patient', 'a', dentist_id=d1)
    audit_repo.record('create', 'patient', 'b', dentist_id=d2)
    assert len(audit_repo.find_for_dentist(d1)) == 1
    assert len(audit_repo.find_all()) == 2


def test_count_helpers(db):
    d1 = str(ObjectId())
    audit_repo.record('create', 'patient', 'a', dentist_id=d1)
    audit_repo.record('create', 'patient', 'b', dentist_id=d1)
    audit_repo.record('login', 'auth', 'x')  # no dentist
    assert audit_repo.count_for_dentist(d1) == 2
    assert audit_repo.count_all() == 3


def test_find_pagination_skip_limit(db):
    d = str(ObjectId())
    for i in range(5):
        audit_repo.record('create', 'patient', str(i), dentist_id=d)
    page1 = audit_repo.find_for_dentist(d, limit=2, skip=0)
    page2 = audit_repo.find_for_dentist(d, limit=2, skip=2)
    assert len(page1) == 2 and len(page2) == 2
    ids1 = {e['entity_id'] for e in page1}
    ids2 = {e['entity_id'] for e in page2}
    assert ids1.isdisjoint(ids2)  # newest-first pages don't overlap


# ── session-aware helper ──────────────────────────────────────────────────────
def test_audit_helper_reads_session_and_derives_dentist(app, db):
    actor, dentist, clinic_id = str(ObjectId()), str(ObjectId()), ObjectId()
    clinic = {'_id': clinic_id, 'owner_id': dentist}
    with app.test_request_context():
        session['user_id'] = actor
        session['user_role'] = 'staff'
        audit('update', 'patient', 'pid', clinic=clinic)
    doc = db.audit_log.find_one({})
    assert doc['actor_user_id'] == actor
    assert doc['actor_role'] == 'staff'
    assert doc['clinic_id'] == clinic_id
    assert doc['dentist_id'] == dentist  # derived from clinic.owner_id


def test_audit_helper_never_raises(app, db, monkeypatch):
    """A repo failure must be swallowed — audit must not break the request."""
    import blueprints.utils as utils

    def boom(*a, **k):
        raise RuntimeError('db down')

    monkeypatch.setattr(utils._audit_repo, 'record', boom)
    with app.test_request_context():
        session['user_id'] = 'x'
        audit('create', 'patient', 'pid')  # must not raise
