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
    from blueprints.repositories import submissions
    db.patients.insert_one({"submission_id": SUBMISSION_ID, "created_by": "user-a"})
    assert submissions.find("patients", SUBMISSION_ID, "user-a") is not None
    assert submissions.find("patients", SUBMISSION_ID, "user-b") is None
    assert submissions.find("patients", None, "user-a") is None


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


# ── Every create/edit form (2026-09-26): JSON success + idempotent retries ───
import io as _io

from PIL import Image as _Image

SID2 = "fedcba9876543210fedcba9876543210"


def _png():
    buf = _io.BytesIO()
    _Image.new("RGB", (4, 4), "white").save(buf, "PNG")
    return buf.getvalue()


def _real(real_client, as_user, who="dentist"):
    as_user(who)
    return real_client


def test_treatment_add_json_success_and_retry_is_idempotent(real_client, as_user, world, db):
    c = _real(real_client, as_user)
    form = {"procedure": "Filling", "date": "2026-09-20", "amount_charged": "800",
            "amount_paid": "0", "submission_id": SID2}
    first = c.post(f"/patients/{world.patient_a}/treatments/add", data=form, headers=JSON_MODE)
    retry = c.post(f"/patients/{world.patient_a}/treatments/add", data=form, headers=JSON_MODE)
    assert first.get_json() == retry.get_json() == {
        "ok": True, "redirect": f"/patients/{world.patient_a}"}
    assert db.treatment_records.count_documents({"procedure": "Filling"}) == 1
    assert db.audit_log.count_documents({"action": "create", "entity_type": "treatment"}) == 1


def test_treatment_edit_json_success(real_client, as_user, world):
    c = _real(real_client, as_user)
    res = c.post(f"/treatments/{world.treatment_a}/edit",
                 data={"procedure": "Cleaning", "date": "2026-09-01", "amount_charged": "1500",
                       "amount_paid": "500"}, headers=JSON_MODE)
    assert res.get_json() == {"ok": True, "redirect": f"/patients/{world.patient_a}"}


def test_clinic_create_retry_is_idempotent(real_client, as_user, world, db):
    c = _real(real_client, as_user)
    form = {"name": "Clinic Echo", "submission_id": SID2}
    assert c.post("/clinics/create", data=form, headers=JSON_MODE).get_json()["ok"] is True
    c.post("/clinics/create", data=form, headers=JSON_MODE)
    assert db.clinics.count_documents({"name": "Clinic Echo"}) == 1
    assert db.clinics.find_one({"name": "Clinic Echo"})["created_by"] == world.dentist


def test_clinic_edit_json_success(real_client, as_user, world):
    c = _real(real_client, as_user)
    res = c.post(f"/clinics/{world.clinic_a}/edit", data={"name": "Clinic Alpha"}, headers=JSON_MODE)
    assert res.get_json() == {"ok": True, "redirect": "/clinics"}


def test_file_upload_retry_stores_the_file_once(real_client, as_user, world, db):
    c = _real(real_client, as_user, "staff")
    for _ in range(2):
        res = c.post(f"/patients/{world.patient_a}/files/add",
                     data={"file": (_io.BytesIO(b"%PDF-1.4 report"), "r.pdf"),
                           "submission_id": SID2},
                     content_type="multipart/form-data", headers=JSON_MODE)
        assert res.get_json()["ok"] is True
    assert db.patient_files.count_documents({}) == 1
    assert db["fs.files"].count_documents({}) == 1          # no orphaned second copy


def test_prescription_retry_stores_the_image_once(real_client, as_user, world, db):
    c = _real(real_client, as_user, "staff")
    for _ in range(2):
        c.post(f"/patients/{world.patient_a}/prescriptions/add",
               data={"description": "Amoxicillin", "image": (_io.BytesIO(_png()), "rx.png"),
                     "submission_id": SID2},
               content_type="multipart/form-data", headers=JSON_MODE)
    assert db.prescriptions.count_documents({}) == 1
    assert db["fs.files"].count_documents({}) == 1


def test_photo_upload_json_success(real_client, as_user, world, db):
    c = _real(real_client, as_user, "staff")
    res = c.post(f"/patients/{world.patient_a}/photo",
                 data={"photo": (_io.BytesIO(_png()), "p.png")},
                 content_type="multipart/form-data", headers=JSON_MODE)
    assert res.get_json() == {"ok": True, "redirect": f"/patients/{world.patient_a}"}


def test_create_once_returns_race_winner(db, monkeypatch):
    """Two copies of one retry race: ours misses in find(), then loses on the
    unique index — create_once must return the winner's id, not raise."""
    from pymongo.errors import DuplicateKeyError
    from blueprints.repositories import submissions
    winner = {"_id": "winner-id"}
    lookups = iter([None, winner])                  # before insert, after the clash
    monkeypatch.setattr(submissions, "find", lambda *_a: next(lookups))

    def insert():
        raise DuplicateKeyError("E11000 duplicate key")
    assert submissions.create_once("treatment_records", SID2, "u", insert) == ("winner-id", False)


def test_create_once_reraises_unrelated_duplicates(db, monkeypatch):
    """A DuplicateKeyError that isn't our submission (e.g. another unique key)
    must surface, not be swallowed."""
    import pytest
    from pymongo.errors import DuplicateKeyError
    from blueprints.repositories import submissions
    monkeypatch.setattr(submissions, "find", lambda *_a: None)

    def insert():
        raise DuplicateKeyError("E11000 duplicate key on email")
    with pytest.raises(DuplicateKeyError):
        submissions.create_once("clinics", SID2, "u", insert)


def test_plain_posts_still_redirect_everywhere(real_client, as_user, world):
    c = _real(real_client, as_user)
    res = c.post("/clinics/create", data={"name": "Clinic Foxtrot"})
    assert res.status_code == 302 and res.headers["Location"].endswith("/clinics")
