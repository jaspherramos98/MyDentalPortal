"""Tests for the deletion-request workflow repo (staff request -> dentist resolve)."""
from bson.objectid import ObjectId

from blueprints.repositories import deletion_requests as dr


def test_create_and_has_pending(db):
    cid, dentist = ObjectId(), str(ObjectId())
    rid = dr.create('treatment', 't1', cid, dentist, requested_by='staff1')
    assert dr.has_pending('treatment', 't1') is True
    doc = dr.get(rid)
    assert doc['status'] == 'pending'
    assert doc['dentist_id'] == dentist and doc['requested_by'] == 'staff1'


def test_create_dedupes_pending(db):
    cid, dentist = ObjectId(), str(ObjectId())
    r1 = dr.create('file', 'f1', cid, dentist, 's')
    r2 = dr.create('file', 'f1', cid, dentist, 's')  # same record, still pending
    assert r1 == r2
    assert db.deletion_requests.count_documents({'entity_type': 'file', 'entity_id': 'f1'}) == 1


def test_list_pending_scopes(db):
    d1, d2 = str(ObjectId()), str(ObjectId())
    dr.create('patient', 'p1', ObjectId(), d1, 's')
    dr.create('patient', 'p2', ObjectId(), d2, 's')
    assert len(dr.list_pending_for_dentist(d1)) == 1
    assert len(dr.list_pending_all()) == 2


def test_resolve_is_single_shot(db):
    rid = dr.create('treatment', 't', ObjectId(), str(ObjectId()), 's')
    assert dr.resolve(rid, 'approved', 'dentist1').modified_count == 1
    assert dr.get(rid)['status'] == 'approved'
    # A resolved request can't be resolved again, and is no longer pending.
    assert dr.resolve(rid, 'rejected', 'dentist1').modified_count == 0
    assert dr.has_pending('treatment', 't') is False
