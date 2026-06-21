"""Tests for staff access codes (single-use, expiring, hashed-at-rest)."""
from bson.objectid import ObjectId

from blueprints.repositories import access_codes as code_repo


def test_generate_returns_plaintext_and_stores_hash_only(db):
    dentist = str(ObjectId())
    code = code_repo.generate(dentist, created_by=dentist)
    assert isinstance(code, str) and len(code) >= 8
    doc = db.access_codes.find_one({'dentist_id': dentist})
    assert doc['code_hash'] != code   # stored hashed, never plaintext
    assert 'code' not in doc
    assert doc['used'] is False


def test_consume_valid_then_single_use(db):
    dentist, staff = str(ObjectId()), str(ObjectId())
    code = code_repo.generate(dentist, created_by=dentist)
    doc = code_repo.consume(code, used_by=staff)
    assert doc is not None and doc['dentist_id'] == dentist
    # Single-use: a second consume of the same code fails.
    assert code_repo.consume(code, used_by=str(ObjectId())) is None
    stored = db.access_codes.find_one({'dentist_id': dentist})
    assert stored['used'] is True and stored['used_by'] == staff


def test_consume_expired_returns_none(db):
    dentist = str(ObjectId())
    code = code_repo.generate(dentist, created_by=dentist, ttl_days=-1)  # already expired
    assert code_repo.consume(code, used_by=str(ObjectId())) is None


def test_consume_unknown_code_returns_none(db):
    code_repo.generate(str(ObjectId()), created_by='x')
    assert code_repo.consume('not-a-real-code', used_by='y') is None


def test_revoke_blocks_consume(db):
    dentist = str(ObjectId())
    code = code_repo.generate(dentist, created_by=dentist)
    cid = db.access_codes.find_one({'dentist_id': dentist})['_id']
    res = code_repo.revoke(str(cid), dentist)
    assert res.modified_count == 1
    assert code_repo.consume(code, used_by=str(ObjectId())) is None


def test_revoke_by_other_dentist_denied(db):
    dentist = str(ObjectId())
    code_repo.generate(dentist, created_by=dentist)
    cid = db.access_codes.find_one({'dentist_id': dentist})['_id']
    res = code_repo.revoke(str(cid), str(ObjectId()))  # not the owner
    assert res.modified_count == 0


def test_list_for_dentist(db):
    dentist = str(ObjectId())
    code_repo.generate(dentist, created_by=dentist)
    code_repo.generate(dentist, created_by=dentist)
    assert len(code_repo.list_for_dentist(dentist)) == 2
