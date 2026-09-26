"""Resilient patient-form submit: the server side of static/js/resilient-submit.js.

Guards the contract the client relies on (Incidents 2026-08-07 / 2026-09-26):
* a JSON-mode save answers with an explicit ``{"ok": true, "redirect": ...}``,
  never an ambiguous redirect;
* create is idempotent per ``submission_id`` so a retried POST can't duplicate
  a patient;
* an expired / missing session answers 401 JSON instead of redirecting away
  from the typed form;
* ``/session/keepalive`` refreshes the session and hands back a CSRF token.
"""
import time

import pytest
from bson.objectid import ObjectId
from flask import Flask, Blueprint

from blueprints.repositories import patients as patient_repo
from blueprints.utils import enforce_idle_timeout

JSON_MODE = {"X-Resilient-Submit": "1"}
SUBMISSION_ID = "0123456789abcdef0123456789abcdef"


@pytest.fixture
def app(db):
    application = Flask(__name__)
    application.config.update(
        TESTING=True, SECRET_KEY="test-secret", WTF_CSRF_ENABLED=False,
        IDLE_TIMEOUT_SECONDS=1800,
    )
    auth = Blueprint("auth", __name__)

    @auth.route("/login")
    def login():
        return "login", 200

    from blueprints.routes.patients import patients_bp
    from blueprints.routes.main import main_bp
    application.register_blueprint(auth)
    application.register_blueprint(patients_bp)
    application.register_blueprint(main_bp)
    application.before_request(enforce_idle_timeout)
    return application


@pytest.fixture
def clinic(db):
    """An active clinic owned by a fresh dentist id; returns (owner_id, clinic_id)."""
    owner_id = str(ObjectId())
    clinic_id = ObjectId()
    db.clinics.insert_one({"_id": clinic_id, "owner_id": owner_id,
                           "name": "Test Clinic", "is_active": True})
    return owner_id, clinic_id


def _create_form(clinic_id, **extra):
    form = {
        "clinic_id": str(clinic_id), "first_name": "Ana", "last_name": "Cruz",
        "cell_phone": "09170000000", "privacy_consent": "yes",
    }
    form.update(extra)
    return form


def test_json_mode_create_returns_explicit_success(client, login, clinic, db):
    owner_id, clinic_id = clinic
    login(user_id=owner_id)
    res = client.post("/patients/create", data=_create_form(clinic_id), headers=JSON_MODE)
    assert res.status_code == 200
    body = res.get_json()
    patient = db.patients.find_one({})
    assert body == {"ok": True, "redirect": f"/patients/{patient['_id']}"}


def test_plain_form_create_still_redirects(client, login, clinic):
    owner_id, clinic_id = clinic
    login(user_id=owner_id)
    res = client.post("/patients/create", data=_create_form(clinic_id))
    assert res.status_code == 302
    assert "/patients/" in res.headers["Location"]


def test_retried_submission_does_not_duplicate(client, login, clinic, db):
    owner_id, clinic_id = clinic
    login(user_id=owner_id)
    form = _create_form(clinic_id, submission_id=SUBMISSION_ID)
    first = client.post("/patients/create", data=form, headers=JSON_MODE).get_json()
    retry = client.post("/patients/create", data=form, headers=JSON_MODE).get_json()
    assert first == retry
    assert db.patients.count_documents({}) == 1
    assert db.patients.find_one({})["submission_id"] == SUBMISSION_ID


def test_malformed_submission_id_is_ignored(client, login, clinic, db):
    owner_id, clinic_id = clinic
    login(user_id=owner_id)
    client.post("/patients/create",
                data=_create_form(clinic_id, submission_id='{"$ne": null}'),
                headers=JSON_MODE)
    assert "submission_id" not in db.patients.find_one({})


def test_submission_lookup_is_scoped_to_creator(db):
    db.patients.insert_one({"submission_id": SUBMISSION_ID, "created_by": "user-a"})
    assert patient_repo.find_by_submission(SUBMISSION_ID, "user-a") is not None
    assert patient_repo.find_by_submission(SUBMISSION_ID, "user-b") is None


def test_json_mode_edit_returns_explicit_success(client, login, seed_patient):
    owner_id = str(ObjectId())
    patient_id, _ = seed_patient(owner_id)
    login(user_id=owner_id)
    res = client.post(f"/patients/{patient_id}/edit",
                      data={"first_name": "Ana", "last_name": "Cruz",
                            "cell_phone": "09170000000"},
                      headers=JSON_MODE)
    assert res.get_json() == {"ok": True, "redirect": f"/patients/{patient_id}"}


def test_no_session_is_401_json_in_json_mode(client, clinic):
    _, clinic_id = clinic
    res = client.post("/patients/create", data=_create_form(clinic_id), headers=JSON_MODE)
    assert res.status_code == 401
    assert res.get_json() == {"ok": False, "error": "session_expired"}


def test_no_session_still_redirects_for_plain_requests(client):
    res = client.get("/patients/create")
    assert res.status_code == 302
    assert res.headers["Location"].endswith("/login")


def test_idle_timeout_is_401_json_and_keeps_form(client, login, clinic, db):
    owner_id, clinic_id = clinic
    login(user_id=owner_id)
    with client.session_transaction() as sess:
        sess["last_activity"] = int(time.time()) - 3600
    res = client.post("/patients/create", data=_create_form(clinic_id), headers=JSON_MODE)
    assert res.status_code == 401
    assert res.get_json()["error"] == "session_expired"
    assert db.patients.count_documents({}) == 0


def test_idle_timeout_redirects_plain_requests(client, login):
    login()
    with client.session_transaction() as sess:
        sess["last_activity"] = int(time.time()) - 3600
    res = client.get("/session/keepalive")
    assert res.status_code == 302
    assert res.headers["Location"].endswith("/login")


def test_keepalive_refreshes_activity_and_returns_csrf(client, login):
    login()
    with client.session_transaction() as sess:
        sess["last_activity"] = int(time.time()) - 600
    res = client.get("/session/keepalive", headers=JSON_MODE)
    assert res.status_code == 200
    body = res.get_json()
    assert body["ok"] is True and body["csrf_token"]
    with client.session_transaction() as sess:
        assert int(time.time()) - sess["last_activity"] < 5


def test_keepalive_without_session_is_401(client):
    res = client.get("/session/keepalive", headers=JSON_MODE)
    assert res.status_code == 401
