"""Record visit: the calendar's one-step dialog (GET/POST /appointments/api/<id>/visit),
the relaxed clinic rule (a dentist's patient booked at their OTHER clinic), and the
Add Treatment form's "Is this for a booked visit?" picker.

Every "nothing changed" negative test has a positive twin with the same payload
shape, so it can't pass just because the payload was wrong.
"""
import pytest
from bson.objectid import ObjectId

from blueprints.clock import utcnow

PAST = "2026-01-10"
LATER = "2026-01-11"      # a record entered the day after the visit
FUTURE = "2099-03-01"


def _appt(db, clinic, patient=None, date=PAST, status="scheduled", name="Alicemarker Alpha"):
    doc = {"clinic_id": clinic, "patient_name": name, "date": date, "time": "10:00",
           "duration": 30, "type": "checkup", "status": status, "is_active": True,
           "created_at": utcnow()}
    if patient is not None:
        doc["patient_id"] = patient
    return db.appointments.insert_one(doc).inserted_id


def _record(db, world, date=LATER, patient=None, clinic=None, **extra):
    """A treatment entered from the patient page (not linked to any visit)."""
    doc = {"patient_id": patient or world.patient_a, "clinic_id": clinic or world.clinic_a,
           "date": date, "procedure": "antirabies", "amount_charged": 300.0,
           "amount_paid": 300.0, "balance": 0.0, "price_confirmed": True,
           "created_at": utcnow(), **extra}
    return db.treatment_records.insert_one(doc).inserted_id


def _second_clinic(db, world):
    """Another clinic owned by the same dentist (the real JRAMOS setup)."""
    return db.clinics.insert_one({"owner_id": world.dentist, "name": "Clinic Annex",
                                  "is_active": True, "currency": "PHP"}).inserted_id


def _url(appt):
    return f"/appointments/api/{appt}/visit"


def _post(client, appt, **body):
    return client.post(_url(appt), json=body)


def _entry(**extra):
    return {"procedure": "Tooth Extraction", "tooth_numbers": "11, 12",
            "amount_charged": "800", "amount_paid": "800", "notes": "", **extra}


def _actions(db):
    return [a["action"] for a in db.audit_log.find({}, {"action": 1})]


# ── GET: what the dialog shows ───────────────────────────────────────────────

def test_details_offer_unlinked_records_from_after_the_visit(real_client, as_user, world, db):
    appt = _appt(db, world.clinic_a, world.patient_a)
    rec = _record(db, world)
    _record(db, world, date="2025-12-01")            # before the visit: not offered
    as_user("staff")
    data = real_client.get(_url(appt)).get_json()
    assert data["success"] and data["patient"]["name"] == "Alicemarker Alpha"
    assert [c["id"] for c in data["candidates"]] == [str(rec)]
    assert data["price_needs_confirmation"] is True
    assert "Tooth Extraction" in data["procedures"]


def test_details_skip_records_already_linked_elsewhere(real_client, as_user, world, db):
    appt = _appt(db, world.clinic_a, world.patient_a)
    _record(db, world, appointment_id=ObjectId())
    as_user("dentist")
    assert real_client.get(_url(appt)).get_json()["candidates"] == []


def test_details_carry_no_amounts(real_client, as_user, world, db):
    appt = _appt(db, world.clinic_a, world.patient_a)
    _record(db, world, amount_charged=4321.0)
    as_user("dentist")
    body = real_client.get(_url(appt)).get_data(as_text=True)
    assert "4321" not in body


def test_outsider_gets_404_for_clinic_a_visit(real_client, as_user, world, db):
    appt = _appt(db, world.clinic_a, world.patient_a)
    _record(db, world)
    as_user("outsider")
    res = real_client.get(_url(appt))
    assert res.status_code == 404 and "antirabies" not in res.get_data(as_text=True)


def test_walk_in_details_wait_for_a_patient_pick(real_client, as_user, world, db):
    appt = _appt(db, world.clinic_a, name="Walk In")
    _record(db, world)
    as_user("dentist")
    data = real_client.get(_url(appt)).get_json()
    assert data["patient"] is None and data["candidates"] == []
    picked = real_client.get(_url(appt) + f"?patient_id={world.patient_a}").get_json()
    assert picked["patient"]["id"] == str(world.patient_a) and len(picked["candidates"]) == 1


def test_walk_in_cannot_pick_another_tenants_patient(real_client, as_user, world, db):
    appt = _appt(db, world.clinic_a, name="Walk In")
    as_user("dentist")
    res = real_client.get(_url(appt) + f"?patient_id={world.patient_b}")
    assert res.status_code == 404 and "Bobmarker" not in res.get_data(as_text=True)


# ── POST: link existing records / add one ────────────────────────────────────

def test_link_existing_record_completes_visit(real_client, as_user, world, db):
    """The Bretney case: treatment entered from the patient page, next day."""
    appt = _appt(db, world.clinic_a, world.patient_a)
    rec = _record(db, world)
    as_user("dentist")
    res = _post(real_client, appt, link=[str(rec)])
    data = res.get_json()
    assert res.status_code == 200 and data["visit"]["state"] == "done"
    assert db.treatment_records.find_one({"_id": rec})["appointment_id"] == appt
    assert db.appointments.find_one({"_id": appt})["status"] == "completed"
    assert {"link_visit", "complete"} <= set(_actions(db))


def test_new_entry_is_dated_on_the_visit_and_linked(real_client, as_user, world, db):
    appt = _appt(db, world.clinic_a, world.patient_a)
    as_user("dentist")
    res = _post(real_client, appt, treatment=_entry())
    assert res.status_code == 200
    t = db.treatment_records.find_one({"procedure": "Tooth Extraction"})
    assert t["appointment_id"] == appt and t["date"] == PAST
    assert t["tooth_numbers"] == ["11", "12"] and t["price_confirmed"] is True
    assert db.appointments.find_one({"_id": appt})["status"] == "completed"


def test_staff_entry_price_is_pending(real_client, as_user, world, db):
    appt = _appt(db, world.clinic_a, world.patient_a)
    as_user("staff")
    data = _post(real_client, appt, treatment=_entry()).get_json()
    assert data["visit"]["state"] == "attention" and "Price pending" in data["visit"]["reasons"]
    assert "price_proposed" in _actions(db)


def test_link_and_add_in_one_save(real_client, as_user, world, db):
    appt = _appt(db, world.clinic_a, world.patient_a)
    rec = _record(db, world)
    as_user("dentist")
    _post(real_client, appt, link=[str(rec)], treatment=_entry())
    assert db.treatment_records.count_documents({"appointment_id": appt}) == 2


def test_retry_with_same_submission_id_saves_once(real_client, as_user, world, db):
    appt = _appt(db, world.clinic_a, world.patient_a)
    as_user("dentist")
    sid = "a" * 32
    for _ in range(2):
        assert _post(real_client, appt, treatment=_entry(), submission_id=sid).status_code == 200
    assert db.treatment_records.count_documents({"procedure": "Tooth Extraction"}) == 1


def test_walk_in_save_links_the_picked_patient(real_client, as_user, world, db):
    appt = _appt(db, world.clinic_a, name="Walk In")
    as_user("dentist")
    assert _post(real_client, appt, treatment=_entry()).status_code == 400    # no patient yet
    assert _post(real_client, appt, patient_id=str(world.patient_a),
                 treatment=_entry()).status_code == 200
    assert db.appointments.find_one({"_id": appt})["patient_id"] == world.patient_a


@pytest.mark.parametrize("body, why", [
    pytest.param({}, "nothing", id="empty"),
    pytest.param({"treatment": _entry(procedure="")}, "no-procedure", id="no-procedure"),
    pytest.param({"treatment": _entry(amount_charged="-5")}, "negative", id="negative"),
    pytest.param({"treatment": _entry(amount_paid="abc")}, "nan", id="not-a-number"),
    pytest.param({"treatment": _entry(amount_charged="inf")}, "inf", id="infinite"),
    pytest.param({"link": "not-a-list"}, "shape", id="bad-link-shape"),
    pytest.param({"treatment": "oops"}, "shape", id="bad-entry-shape"),
])
def test_bad_input_is_refused_and_changes_nothing(real_client, as_user, world, db, body, why):
    appt = _appt(db, world.clinic_a, world.patient_a)
    as_user("dentist")
    res = _post(real_client, appt, **body)
    assert res.status_code == 400 and res.get_json()["error"]
    assert db.appointments.find_one({"_id": appt})["status"] == "scheduled"
    assert db.treatment_records.count_documents({"appointment_id": appt}) == 0


def test_cannot_link_another_patients_record(real_client, as_user, world, db):
    appt = _appt(db, world.clinic_a, world.patient_a)
    foreign = _record(db, world, patient=world.patient_b, clinic=world.clinic_b)
    as_user("dentist")
    res = _post(real_client, appt, link=[str(foreign)])
    assert res.status_code == 400
    assert "appointment_id" not in db.treatment_records.find_one({"_id": foreign})


@pytest.mark.parametrize("date", ["2025-12-01", "2026-03-01"], ids=["before-visit", "past-window"])
def test_cannot_link_record_outside_the_window(real_client, as_user, world, db, date):
    appt = _appt(db, world.clinic_a, world.patient_a)
    rec = _record(db, world, date=date)
    as_user("dentist")
    assert _post(real_client, appt, link=[str(rec)]).status_code == 400
    assert "appointment_id" not in db.treatment_records.find_one({"_id": rec})


@pytest.mark.parametrize("make_appt, status", [
    pytest.param(lambda db, w: _appt(db, w.clinic_a, w.patient_a, date=FUTURE), 400, id="future"),
    pytest.param(lambda db, w: _appt(db, w.clinic_a, w.patient_a, status="cancelled"), 400, id="cancelled"),
    pytest.param(lambda db, w: _appt(db, w.clinic_b, w.patient_b), 404, id="foreign-clinic"),
    pytest.param(lambda db, w: "not-an-id", 404, id="malformed"),
])
def test_unrecordable_visits_are_refused(real_client, as_user, world, db, make_appt, status):
    appt = make_appt(db, world)
    as_user("dentist")
    res = _post(real_client, appt, treatment=_entry())
    assert res.status_code == status
    assert db.treatment_records.count_documents({"procedure": "Tooth Extraction"}) == 0


def test_patient_id_cannot_override_the_booked_patient(real_client, as_user, world, db):
    appt = _appt(db, world.clinic_a, world.patient_a)
    other = db.patients.insert_one({"clinic_id": world.clinic_a, "is_active": True,
                                    "personal_info": {"first_name": "Carl", "last_name": "C"}}).inserted_id
    as_user("dentist")
    assert _post(real_client, appt, patient_id=str(other), treatment=_entry()).status_code == 400
    assert _post(real_client, appt, patient_id=str(world.patient_a), treatment=_entry()).status_code == 200


def test_post_requires_login(real_client, world, db):
    appt = _appt(db, world.clinic_a, world.patient_a)
    res = _post(real_client, appt, treatment=_entry())
    assert res.status_code in (302, 401)
    assert db.treatment_records.count_documents({"procedure": "Tooth Extraction"}) == 0


# ── Relaxed clinic rule: patient registered at clinic A, booked at the annex ──

def test_visit_at_owners_other_clinic_can_be_recorded(real_client, as_user, world, db):
    annex = _second_clinic(db, world)
    appt = _appt(db, annex, world.patient_a)
    rec = _record(db, world)
    as_user("staff")
    assert _post(real_client, appt, link=[str(rec)]).status_code == 200
    assert db.appointments.find_one({"_id": appt})["status"] == "completed"


def test_add_treatment_links_visit_at_other_clinic(real_client, as_user, world, db):
    annex = _second_clinic(db, world)
    appt = _appt(db, annex, world.patient_a)
    as_user("dentist")
    res = real_client.post(f"/patients/{world.patient_a}/treatments/add",
                           data={"date": PAST, "procedure": "Tooth Extraction",
                                 "appointment_id": str(appt)})
    assert f"visit={appt}" in res.location
    t = db.treatment_records.find_one({"procedure": "Tooth Extraction"})
    assert t["appointment_id"] == appt and t["clinic_id"] == world.clinic_a


# ── Add Treatment: "Is this for a booked visit?" ─────────────────────────────

def test_add_form_offers_open_visits(real_client, as_user, world, db, monkeypatch):
    from blueprints.routes import treatments as troutes
    monkeypatch.setattr(troutes, "_today", lambda: "2026-01-15")
    annex = _second_clinic(db, world)
    recent = _appt(db, annex, world.patient_a, date="2026-01-14")
    older = _appt(db, world.clinic_a, world.patient_a, date="2026-01-05")
    _appt(db, world.clinic_a, world.patient_a, date="2026-01-20")              # future
    _appt(db, world.clinic_a, world.patient_a, date="2025-11-01")              # too old
    _appt(db, world.clinic_a, world.patient_a, date="2026-01-13", status="cancelled")
    as_user("dentist")
    html = real_client.get(f"/patients/{world.patient_a}/treatments/add").get_data(as_text=True)
    assert "open-visit-picker" in html
    assert html.index(str(recent)) < html.index(str(older))                     # most recent first
    assert f'value="{recent}" selected' in html and "(Clinic Annex)" in html
    assert html.count("Yes — visit on") == 2


def test_add_form_without_open_visits_has_no_picker(real_client, as_user, world, db):
    as_user("dentist")
    html = real_client.get(f"/patients/{world.patient_a}/treatments/add").get_data(as_text=True)
    assert "open-visit-picker" not in html


def test_add_form_never_offers_another_tenants_visit(real_client, as_user, world, db, monkeypatch):
    from blueprints.routes import treatments as troutes
    monkeypatch.setattr(troutes, "_today", lambda: "2026-01-15")
    # patient_b's visit in clinic_b, viewed by the outsider: offered to them only.
    theirs = _appt(db, world.clinic_b, world.patient_b, date="2026-01-14", name="Bobmarker Bravo")
    as_user("outsider")
    assert str(theirs) in real_client.get(
        f"/patients/{world.patient_b}/treatments/add").get_data(as_text=True)
    as_user("dentist")
    assert real_client.get(f"/patients/{world.patient_b}/treatments/add").status_code == 302


def test_choosing_no_saves_unlinked_without_warning(real_client, as_user, world, db):
    appt = _appt(db, world.clinic_a, world.patient_a)
    as_user("dentist")
    real_client.post(f"/patients/{world.patient_a}/treatments/add",
                     data={"date": PAST, "procedure": "Tooth Extraction", "appointment_id": ""})
    assert "appointment_id" not in db.treatment_records.find_one({"procedure": "Tooth Extraction"})
    assert db.appointments.find_one({"_id": appt})["status"] == "scheduled"


def test_add_treatment_refuses_negative_amount(real_client, as_user, world, db):
    as_user("dentist")
    real_client.post(f"/patients/{world.patient_a}/treatments/add",
                     data={"date": PAST, "procedure": "Tooth Extraction", "amount_charged": "-1"})
    assert db.treatment_records.count_documents({"procedure": "Tooth Extraction"}) == 0
    real_client.post(f"/patients/{world.patient_a}/treatments/add",
                     data={"date": PAST, "procedure": "Tooth Extraction", "amount_charged": "1"})
    assert db.treatment_records.count_documents({"procedure": "Tooth Extraction"}) == 1
