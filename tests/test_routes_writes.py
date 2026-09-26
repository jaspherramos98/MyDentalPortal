"""Characterization tests for the write paths, on the REAL app.

Each test drives a real POST/PUT/DELETE as a given role and asserts the
database outcome plus the audit trail — the behaviour the Phase 1-3 refactors
must keep. Tenant layout: ``world`` in conftest.py.
"""
import io

import pytest
from bson.objectid import ObjectId
from PIL import Image

from blueprints.repositories import access_codes as access_code_repo


def _patient(db, patient_id):
    return db.patients.find_one({"_id": ObjectId(patient_id)})


def _audit_actions(db):
    return [a["action"] for a in db.audit_log.find({}, {"action": 1})]


# ── Auth ─────────────────────────────────────────────────────────────────────

def test_login_success_starts_session(real_client, world, db):
    res = real_client.post("/login", data={"email": "dentist.a@dental.com", "password": "pw-dentist"})
    assert res.status_code == 302 and res.headers["Location"].endswith("/dashboard")
    with real_client.session_transaction() as sess:
        assert sess["user_id"] == world.dentist and sess["user_role"] == "dentist"
    assert "login" in _audit_actions(db)


def test_login_wrong_password_rejected_and_audited(real_client, world, db):
    res = real_client.post("/login", data={"email": "dentist.a@dental.com", "password": "nope"})
    assert res.status_code == 200
    with real_client.session_transaction() as sess:
        assert "user_id" not in sess
    assert "login_failed" in _audit_actions(db)


def test_login_failure_audit_holds_no_raw_email(real_client, world, db):
    real_client.post("/login", data={"email": "dentist.a@dental.com", "password": "nope"})
    for entry in db.audit_log.find({}):
        assert "dentist.a@dental.com" not in str(entry)


def test_deactivated_user_cannot_log_in(real_client, world, db):
    db.users.update_one({"_id": ObjectId(world.dentist)}, {"$set": {"is_active": False}})
    real_client.post("/login", data={"email": "dentist.a@dental.com", "password": "pw-dentist"})
    with real_client.session_transaction() as sess:
        assert "user_id" not in sess


def test_logout_clears_session(real_client, as_user, world):
    as_user("dentist")
    res = real_client.post("/logout")
    assert res.status_code == 302
    with real_client.session_transaction() as sess:
        assert "user_id" not in sess


def test_register_creates_pending_account_that_cannot_log_in(real_client, world, db):
    real_client.post("/register", data={
        "name": "New Dentist", "email": "new@dental.com", "license_number": "LIC-NEW",
        "specialty": "General", "password": "Str0ngPass!word", "confirm_password": "Str0ngPass!word",
    })
    user = db.users.find_one({"email": "new@dental.com"})
    assert user is not None and user["status"] == "pending"
    real_client.post("/login", data={"email": "new@dental.com", "password": "Str0ngPass!word"})
    with real_client.session_transaction() as sess:
        assert "user_id" not in sess


def test_admin_approves_registration(real_client, as_user, world, db):
    pending = db.users.insert_one({"name": "P", "email": "p@dental.com", "status": "pending",
                                   "role": "dentist", "password": "x"}).inserted_id
    as_user("admin")
    real_client.post(f"/admin/registrations/{pending}/approve")
    assert db.users.find_one({"_id": pending})["status"] == "approved"


def test_join_with_access_code_creates_linked_staff(real_client, world, db):
    code = access_code_repo.generate(world.dentist, world.dentist)
    real_client.post("/join", data={
        "access_code": code, "name": "New Staff", "email": "newstaff@dental.com",
        "password": "Str0ngPass!word", "confirm_password": "Str0ngPass!word",
    })
    user = db.users.find_one({"email": "newstaff@dental.com"})
    assert user["role"] == "staff" and user["status"] == "approved"
    assert db.memberships.find_one({"user_id": str(user["_id"]), "dentist_id": world.dentist,
                                    "is_active": True})
    assert db.access_codes.find_one({})["used"] is True


def test_join_with_bad_code_leaves_no_account(real_client, world, db):
    real_client.post("/join", data={
        "access_code": "not-a-real-code", "name": "X", "email": "x@dental.com",
        "password": "Str0ngPass!word", "confirm_password": "Str0ngPass!word",
    })
    assert db.users.find_one({"email": "x@dental.com"}) is None


# ── Clinics ──────────────────────────────────────────────────────────────────

def test_dentist_creates_clinic(real_client, as_user, world, db):
    as_user("dentist")
    real_client.post("/clinics/create", data={"name": "Clinic Charlie", "address": "Bulacan",
                                              "currency": "PHP"})
    assert db.clinics.find_one({"name": "Clinic Charlie", "owner_id": world.dentist})


def test_staff_cannot_create_clinic(real_client, as_user, world, db):
    as_user("staff")
    res = real_client.post("/clinics/create", data={"name": "Staff Clinic"})
    assert res.status_code == 302 and res.headers["Location"].endswith("/dashboard")
    assert db.clinics.find_one({"name": "Staff Clinic"}) is None


def test_outsider_cannot_edit_or_delete_clinic_a(real_client, as_user, world, db):
    as_user("outsider")
    real_client.post(f"/clinics/{world.clinic_a}/edit", data={"name": "Hijacked"})
    real_client.post(f"/clinics/{world.clinic_a}/delete")
    clinic = db.clinics.find_one({"_id": world.clinic_a})
    assert clinic["name"] == "Clinic Alpha" and clinic["is_active"] is True


def test_dentist_edits_own_clinic(real_client, as_user, world, db):
    # Positive twin of the outsider test above: proves that payload really edits.
    as_user("dentist")
    real_client.post(f"/clinics/{world.clinic_a}/edit", data={"name": "Hijacked"})
    assert db.clinics.find_one({"_id": world.clinic_a})["name"] == "Hijacked"


def test_dentist_soft_deletes_own_clinic(real_client, as_user, world, db):
    as_user("dentist")
    real_client.post(f"/clinics/{world.clinic_a}/delete")
    assert db.clinics.find_one({"_id": world.clinic_a})["is_active"] is False


# ── Patients ─────────────────────────────────────────────────────────────────

def _edit_form(**extra):
    form = {"first_name": "Alicemarker", "last_name": "Edited", "cell_phone": "09171111111"}
    form.update(extra)
    return form


@pytest.mark.parametrize("who", ["dentist", "staff"])
def test_clinic_team_can_edit_patient(real_client, as_user, world, db, who):
    as_user(who)
    real_client.post(f"/patients/{world.patient_a}/edit", data=_edit_form())
    assert _patient(db, world.patient_a)["personal_info"]["last_name"] == "Edited"
    assert "update" in _audit_actions(db)


def test_outsider_cannot_edit_patient(real_client, as_user, world, db):
    as_user("outsider")
    real_client.post(f"/patients/{world.patient_a}/edit", data=_edit_form())
    assert _patient(db, world.patient_a)["personal_info"]["last_name"] == "Alpha"


def test_audit_entries_hold_no_patient_data(real_client, as_user, world, db):
    as_user("dentist")
    real_client.post(f"/patients/{world.patient_a}/edit", data=_edit_form())
    for entry in db.audit_log.find({}):
        assert "Alicemarker" not in str(entry) and "09171111111" not in str(entry)


def test_create_patient_in_foreign_clinic_is_refused(real_client, as_user, world, db):
    as_user("dentist")
    real_client.post("/patients/create", data={
        "clinic_id": str(world.clinic_b), "first_name": "Sneaky", "last_name": "Insert",
        "cell_phone": "09170000000", "privacy_consent": "yes",
    })
    assert db.patients.find_one({"personal_info.first_name": "Sneaky"}) is None


def test_create_patient_requires_privacy_consent(real_client, as_user, world, db):
    as_user("dentist")
    real_client.post("/patients/create", data={
        "clinic_id": str(world.clinic_a), "first_name": "NoConsent", "last_name": "X",
        "cell_phone": "09170000000",
    })
    assert db.patients.find_one({"personal_info.first_name": "NoConsent"}) is None


def test_create_patient_records_consent(real_client, as_user, world, db):
    as_user("dentist")
    real_client.post("/patients/create", data={
        "clinic_id": str(world.clinic_a), "first_name": "Consenting", "last_name": "X",
        "cell_phone": "09170000000", "privacy_consent": "yes",
    })
    consent = db.patients.find_one({"personal_info.first_name": "Consenting"})["privacy_consent"]
    assert consent["given"] is True and consent["by_user_id"] == world.dentist


def test_dentist_soft_deletes_patient(real_client, as_user, world, db):
    as_user("dentist")
    real_client.post(f"/patients/{world.patient_a}/delete")
    assert _patient(db, world.patient_a)["is_active"] is False


@pytest.mark.parametrize("who", ["staff", "outsider"])
def test_non_owner_cannot_delete_patient(real_client, as_user, world, db, who):
    as_user(who)
    real_client.post(f"/patients/{world.patient_a}/delete")
    assert _patient(db, world.patient_a)["is_active"] is True


# ── Treatments + pricing ─────────────────────────────────────────────────────

def _treatment_form(**extra):
    form = {"procedure": "Extraction", "date": "2026-09-20", "amount_charged": "2000",
            "amount_paid": "0", "status": "completed"}
    form.update(extra)
    return form


def test_dentist_price_is_confirmed(real_client, as_user, world, db):
    as_user("dentist")
    real_client.post(f"/patients/{world.patient_a}/treatments/add", data=_treatment_form())
    t = db.treatment_records.find_one({"procedure": "Extraction"})
    assert t["price_confirmed"] is True and t["amount_charged"] == 2000.0


def test_staff_price_is_pending_until_dentist_confirms(real_client, as_user, world, db):
    as_user("staff")
    real_client.post(f"/patients/{world.patient_a}/treatments/add", data=_treatment_form())
    t = db.treatment_records.find_one({"procedure": "Extraction"})
    assert t["price_confirmed"] is False
    as_user("staff")
    real_client.post(f"/treatments/{t['_id']}/confirm-price")
    assert db.treatment_records.find_one({"_id": t["_id"]})["price_confirmed"] is False
    as_user("dentist")
    real_client.post(f"/treatments/{t['_id']}/confirm-price")
    assert db.treatment_records.find_one({"_id": t["_id"]})["price_confirmed"] is True


def test_outsider_cannot_add_treatment(real_client, as_user, world, db):
    as_user("outsider")
    real_client.post(f"/patients/{world.patient_a}/treatments/add", data=_treatment_form())
    assert db.treatment_records.find_one({"procedure": "Extraction"}) is None


def test_mark_paid_clears_balance(real_client, as_user, world, db):
    as_user("staff")
    real_client.post(f"/treatments/{world.treatment_a}/mark-paid")
    t = db.treatment_records.find_one({"_id": world.treatment_a})
    assert t["balance"] == 0 and t["amount_paid"] == t["amount_charged"]


@pytest.mark.parametrize("who, survives", [("dentist", False), ("staff", True), ("outsider", True)])
def test_treatment_delete_is_dentist_only(real_client, as_user, world, db, who, survives):
    as_user(who)
    real_client.post(f"/treatments/{world.treatment_a}/delete")
    assert (db.treatment_records.find_one({"_id": world.treatment_a}) is not None) == survives


# ── Appointments (JSON API) ──────────────────────────────────────────────────

def _appt(world, **extra):
    body = {"clinic_id": str(world.clinic_a), "patient_id": str(world.patient_a),
            "patient_name": "Alicemarker Alpha", "date": "2099-02-01", "time": "09:00",
            "duration": 30}
    body.update(extra)
    return body


@pytest.mark.parametrize("who", ["dentist", "staff"])
def test_clinic_team_creates_appointment(real_client, as_user, world, db, who):
    as_user(who)
    res = real_client.post("/appointments/api", json=_appt(world))
    assert res.status_code in (200, 201) and res.get_json()["success"] is True
    assert db.appointments.count_documents({"date": "2099-02-01"}) == 1


def test_double_booking_is_rejected(real_client, as_user, world, db):
    as_user("dentist")
    real_client.post("/appointments/api", json=_appt(world))
    res = real_client.post("/appointments/api", json=_appt(world))
    assert res.get_json()["success"] is False
    assert db.appointments.count_documents({"date": "2099-02-01"}) == 1


def test_past_date_is_rejected(real_client, as_user, world, db):
    as_user("dentist")
    res = real_client.post("/appointments/api", json=_appt(world, date="2000-01-01"))
    assert res.get_json()["success"] is False


def test_outsider_cannot_book_in_clinic_a(real_client, as_user, world, db):
    as_user("outsider")
    real_client.post("/appointments/api", json=_appt(world))
    assert db.appointments.count_documents({"date": "2099-02-01"}) == 0


def test_outsider_cannot_change_or_delete_clinic_a_appointment(real_client, as_user, world, db):
    as_user("outsider")
    real_client.put(f"/appointments/api/{world.appointment_a}", json={"time": "15:00"})
    real_client.delete(f"/appointments/api/{world.appointment_a}")
    appt = db.appointments.find_one({"_id": world.appointment_a})
    assert appt["time"] == "10:00" and appt["is_active"] is True


def test_dentist_updates_and_deletes_appointment(real_client, as_user, world, db):
    as_user("dentist")
    real_client.put(f"/appointments/api/{world.appointment_a}", json={"time": "15:00"})
    assert db.appointments.find_one({"_id": world.appointment_a})["time"] == "15:00"
    real_client.delete(f"/appointments/api/{world.appointment_a}")
    assert db.appointments.find_one({"_id": world.appointment_a})["is_active"] is False


# ── Chart (SACRED — behaviour only, via the real app) ────────────────────────

def test_staff_can_save_chart(real_client, as_user, world, db):
    as_user("staff")
    res = real_client.post(f"/chart/update/{world.patient_a}", json={"notes": "staff note"})
    assert res.status_code == 200
    assert db.dental_charts.find_one({"patient_id": world.patient_a}) is not None


def test_outsider_cannot_save_chart(real_client, as_user, world, db):
    as_user("outsider")
    res = real_client.post(f"/chart/update/{world.patient_a}", json={"notes": "x"})
    assert res.status_code in (403, 404)
    assert db.dental_charts.find_one({"patient_id": world.patient_a}) is None


# ── Deletion requests ────────────────────────────────────────────────────────

def test_staff_requests_and_dentist_approves_patient_deletion(real_client, as_user, world, db):
    as_user("staff")
    real_client.post("/deletions/request", data={"entity_type": "patient",
                                                 "entity_id": str(world.patient_a)})
    req = db.deletion_requests.find_one({"entity_id": str(world.patient_a)})
    assert req["status"] == "pending"
    assert _patient(db, world.patient_a)["is_active"] is True

    as_user("dentist")
    real_client.post(f"/deletions/{req['_id']}/approve")
    assert db.deletion_requests.find_one({"_id": req["_id"]})["status"] == "approved"
    assert _patient(db, world.patient_a)["is_active"] is False


def test_outsider_cannot_approve_clinic_a_request(real_client, as_user, world, db):
    as_user("staff")
    real_client.post("/deletions/request", data={"entity_type": "patient",
                                                 "entity_id": str(world.patient_a)})
    req = db.deletion_requests.find_one({})
    as_user("outsider")
    real_client.post(f"/deletions/{req['_id']}/approve")
    assert db.deletion_requests.find_one({"_id": req["_id"]})["status"] == "pending"
    assert _patient(db, world.patient_a)["is_active"] is True


# ── Staff codes + admin panel ────────────────────────────────────────────────

def test_dentist_generates_and_revokes_code(real_client, as_user, world, db):
    as_user("dentist")
    real_client.post("/staff/codes/generate")
    code = db.access_codes.find_one({"dentist_id": world.dentist})
    assert code is not None and "code" not in code          # only the hash is stored
    real_client.post(f"/staff/codes/{code['_id']}/revoke")
    assert db.access_codes.find_one({"_id": code["_id"]})["revoked"] is True


def test_staff_cannot_generate_codes(real_client, as_user, world, db):
    as_user("staff")
    real_client.post("/staff/codes/generate")
    assert db.access_codes.count_documents({}) == 0


def test_admin_changes_role_and_deactivates(real_client, as_user, world, db):
    as_user("admin")
    real_client.post(f"/admin/users/{world.outsider}/role", data={"role": "staff"})
    real_client.post(f"/admin/users/{world.outsider}/active", data={"active": "0"})
    user = db.users.find_one({"_id": ObjectId(world.outsider)})
    assert user["role"] == "staff" and user["is_active"] is False


def test_admin_cannot_lock_themselves_out(real_client, as_user, world, db):
    as_user("admin")
    real_client.post(f"/admin/users/{world.admin}/role", data={"role": "dentist"})
    real_client.post(f"/admin/users/{world.admin}/active", data={"active": "0"})
    admin = db.users.find_one({"_id": ObjectId(world.admin)})
    assert admin["role"] == "admin" and admin["is_active"] is True


def test_dentist_cannot_use_admin_actions(real_client, as_user, world, db):
    as_user("dentist")
    real_client.post(f"/admin/users/{world.dentist}/role", data={"role": "admin"})
    assert db.users.find_one({"_id": ObjectId(world.dentist)})["role"] == "dentist"


# ── Uploads (GridFS) ─────────────────────────────────────────────────────────

def _png_bytes():
    buf = io.BytesIO()
    Image.new("RGB", (2, 2), "white").save(buf, format="PNG")
    return buf.getvalue()


PNG_1PX = _png_bytes()


def test_staff_uploads_and_reads_back_a_file(real_client, as_user, world, db):
    as_user("staff")
    real_client.post(f"/patients/{world.patient_a}/files/add",
                     data={"file": (io.BytesIO(PNG_1PX), "xray.png"), "description": "xray"},
                     content_type="multipart/form-data")
    doc = db.patient_files.find_one({"patient_id": world.patient_a})
    assert doc is not None
    res = real_client.get(f"/files/{doc['_id']}/download")
    assert res.status_code == 200 and res.data == PNG_1PX


def test_outsider_cannot_download_clinic_a_file(real_client, as_user, world, db):
    as_user("staff")
    real_client.post(f"/patients/{world.patient_a}/files/add",
                     data={"file": (io.BytesIO(PNG_1PX), "xray.png")},
                     content_type="multipart/form-data")
    doc = db.patient_files.find_one({})
    as_user("outsider")
    res = real_client.get(f"/files/{doc['_id']}/download")
    assert res.status_code != 200 or res.data != PNG_1PX


def test_upload_rejects_non_image_content(real_client, as_user, world, db):
    as_user("dentist")
    real_client.post(f"/patients/{world.patient_a}/files/add",
                     data={"file": (io.BytesIO(b"MZ\x90\x00 not an image"), "evil.png")},
                     content_type="multipart/form-data")
    assert db.patient_files.count_documents({}) == 0
