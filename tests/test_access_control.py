"""Tests for the centralised access-control utils in blueprints/utils.

These guard the highest-risk-to-regress security logic for a PHI app:
who is an admin, and who may touch a given patient.
"""
from bson.objectid import ObjectId
from flask import session

from blueprints.utils import is_admin, verify_patient_access, user_clinic_ids


# ── is_admin ────────────────────────────────────────────────────────────────
def test_is_admin_true_by_email(app):
    with app.test_request_context():
        session["user_email"] = "boss@dental.com"  # in ADMIN_EMAILS
        session["user_role"] = "dentist"
        assert is_admin() is True


def test_is_admin_email_is_case_insensitive(app):
    with app.test_request_context():
        session["user_email"] = "BOSS@DENTAL.COM"
        assert is_admin() is True


def test_is_admin_true_by_role(app):
    with app.test_request_context():
        session["user_email"] = "nobody@dental.com"
        session["user_role"] = "admin"
        assert is_admin() is True


def test_is_admin_false_for_regular_dentist(app):
    with app.test_request_context():
        session["user_email"] = "dentist@dental.com"
        session["user_role"] = "dentist"
        assert is_admin() is False


def test_is_admin_false_when_anonymous(app):
    with app.test_request_context():
        assert is_admin() is False


# ── verify_patient_access ───────────────────────────────────────────────────
def test_verify_patient_access_owner_granted(app, db, seed_patient):
    owner = str(ObjectId())
    patient_id, clinic_id = seed_patient(owner)
    with app.test_request_context():
        session["user_id"] = owner
        patient, clinic = verify_patient_access(str(patient_id))
    assert patient is not None and patient["_id"] == patient_id
    assert clinic is not None and clinic["_id"] == clinic_id


def test_verify_patient_access_other_users_clinic_denied(app, db, seed_patient):
    patient_id, _ = seed_patient(owner_id=str(ObjectId()))  # owned by someone else
    with app.test_request_context():
        session["user_id"] = str(ObjectId())  # a different user
        patient, clinic = verify_patient_access(str(patient_id))
    # Security contract: clinic is None => caller must deny access.
    assert clinic is None


def test_verify_patient_access_missing_patient(app, db):
    with app.test_request_context():
        session["user_id"] = str(ObjectId())
        assert verify_patient_access(str(ObjectId())) == (None, None)


def test_verify_patient_access_invalid_id(app, db):
    with app.test_request_context():
        session["user_id"] = str(ObjectId())
        assert verify_patient_access("not-an-object-id") == (None, None)


# ── user_clinic_ids ─────────────────────────────────────────────────────────
def test_user_clinic_ids_returns_only_active_owned(app, db):
    owner = str(ObjectId())
    mine_active = ObjectId()
    db.clinics.insert_many([
        {"_id": mine_active, "owner_id": owner, "is_active": True},
        {"_id": ObjectId(), "owner_id": owner, "is_active": False},        # inactive
        {"_id": ObjectId(), "owner_id": str(ObjectId()), "is_active": True},  # other owner
    ])
    with app.test_request_context():
        session["user_id"] = owner
        ids = user_clinic_ids()
    assert ids == [mine_active]


# ── decorators ──────────────────────────────────────────────────────────────
def test_login_required_redirects_when_anonymous(client):
    resp = client.get("/_login_guarded")
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_login_required_allows_authenticated(client, login):
    login()
    assert client.get("/_login_guarded").status_code == 200


def test_admin_required_forbids_non_admin(client, login):
    login(role="dentist", email="dentist@dental.com")
    assert client.get("/_admin_guarded").status_code == 403


def test_admin_required_allows_admin(client, login):
    login(role="admin")
    assert client.get("/_admin_guarded").status_code == 200


def test_admin_required_redirects_anonymous(client):
    resp = client.get("/_admin_guarded")
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]
