"""Visit history: appointment <-> treatment link, visit outcome, calendar data,
the list view, and the backfill script.

Every "nothing changed" negative test has a positive twin with the same shape
of payload, so it can't pass just because the payload was wrong.
"""
import importlib.util
import pathlib

import pytest
from bson.objectid import ObjectId

from blueprints import visits
from blueprints.clock import utcnow

PAST = "2026-01-10"
FUTURE = "2099-03-01"
TODAY = "2026-06-15"   # for pure summarize() tests only


# ── visits.summarize (pure) ──────────────────────────────────────────────────

def _t(charged=1000.0, paid=1000.0, **extra):
    return {"procedure": "Oral Prophylaxis", "amount_charged": charged,
            "amount_paid": paid, **extra}


def test_completed_paid_confirmed_is_done():
    v = visits.summarize({"status": "completed", "date": PAST}, [_t(price_confirmed=True)], TODAY)
    assert v.state == visits.STATE_DONE and v.reasons == [] and v.procedures == ["Oral Prophylaxis"]


def test_legacy_treatment_without_price_field_counts_as_confirmed():
    v = visits.summarize({"status": "completed", "date": PAST}, [_t()], TODAY)
    assert v.state == visits.STATE_DONE


@pytest.mark.parametrize("treatments, reason", [
    ([], visits.REASON_NO_TREATMENT),
    ([_t(paid=400.0)], visits.REASON_BALANCE),
    ([_t(price_confirmed=False)], visits.REASON_PRICE_PENDING),
])
def test_completed_with_a_gap_needs_attention(treatments, reason):
    v = visits.summarize({"status": "completed", "date": PAST}, treatments, TODAY)
    assert v.state == visits.STATE_ATTENTION and reason in v.reasons


def test_balance_sums_visit_and_ignores_overpayment():
    v = visits.summarize({"status": "completed", "date": PAST},
                         [_t(1000.0, 400.0), _t(500.0, 900.0)], TODAY)
    assert v.charged == 1500.0 and v.balance == 600.0


def test_balance_uses_charged_minus_paid_not_stale_field():
    v = visits.summarize({"status": "completed", "date": PAST},
                         [_t(1000.0, 1000.0, balance=999.0)], TODAY)
    assert v.state == visits.STATE_DONE and v.balance == 0.0


@pytest.mark.parametrize("status, label", [("cancelled", "Cancelled"), ("no-show", "No-show")])
def test_cancelled_and_no_show_share_state_but_keep_labels(status, label):
    v = visits.summarize({"status": status, "date": PAST}, [], TODAY)
    assert v.state == visits.STATE_CANCELLED and v.status_label == label


def test_past_scheduled_is_not_marked():
    v = visits.summarize({"status": "scheduled", "date": PAST}, [], TODAY)
    assert v.state == visits.STATE_ATTENTION and v.reasons == [visits.REASON_NOT_MARKED]


@pytest.mark.parametrize("date", [TODAY, FUTURE])
def test_today_and_future_scheduled_stay_upcoming(date):
    v = visits.summarize({"status": "scheduled", "date": date}, [], TODAY)
    assert v.state == visits.STATE_UPCOMING and not v.has_banner


# ── fixtures ─────────────────────────────────────────────────────────────────

def _appt(db, clinic, patient=None, date=PAST, status="scheduled", name="Alicemarker Alpha"):
    doc = {"clinic_id": clinic, "patient_name": name, "date": date, "time": "10:00",
           "duration": 30, "type": "checkup", "status": status, "is_active": True,
           "created_at": utcnow()}
    if patient is not None:
        doc["patient_id"] = patient
    return db.appointments.insert_one(doc).inserted_id


def _treatment_form(appointment_id=None, **extra):
    form = {"date": PAST, "procedure": "Tooth Extraction", "amount_charged": "800",
            "amount_paid": "800"}
    if appointment_id is not None:
        form["appointment_id"] = str(appointment_id)
    form.update(extra)
    return form


def _actions(db):
    return [a["action"] for a in db.audit_log.find({}, {"action": 1})]


# ── Add Treatment opened for a visit ──────────────────────────────────────────

def test_add_form_prefills_visit(real_client, as_user, world, db):
    appt = _appt(db, world.clinic_a, world.patient_a)
    as_user("dentist")
    html = real_client.get(f"/patients/{world.patient_a}/treatments/add?appointment_id={appt}").get_data(as_text=True)
    assert f'name="appointment_id" value="{appt}"' in html
    assert f'value="{PAST}"' in html and "visit-link-banner" in html


# ── Complete visit: saving the linked treatment ──────────────────────────────

@pytest.mark.parametrize("who", ["dentist", "staff"])
def test_saving_linked_treatment_completes_the_visit(real_client, as_user, world, db, who):
    appt = _appt(db, world.clinic_a, world.patient_a)
    as_user(who)
    res = real_client.post(f"/patients/{world.patient_a}/treatments/add", data=_treatment_form(appt))
    assert res.status_code == 302 and f"visit={appt}" in res.location
    t = db.treatment_records.find_one({"procedure": "Tooth Extraction"})
    assert t["appointment_id"] == appt
    stored = db.appointments.find_one({"_id": appt})
    assert stored["status"] == "completed" and stored.get("completed_at")
    assert "complete" in _actions(db)


def test_second_procedure_joins_completed_visit(real_client, as_user, world, db):
    appt = _appt(db, world.clinic_a, world.patient_a, status="completed")
    as_user("dentist")
    real_client.post(f"/patients/{world.patient_a}/treatments/add", data=_treatment_form(appt))
    assert db.treatment_records.count_documents({"appointment_id": appt}) == 1
    assert "complete" not in _actions(db)   # already completed: no second status change


def test_walk_in_completion_links_the_patient(real_client, as_user, world, db):
    appt = _appt(db, world.clinic_a, name="Walk In")
    as_user("dentist")
    real_client.post(f"/patients/{world.patient_a}/treatments/add", data=_treatment_form(appt))
    stored = db.appointments.find_one({"_id": appt})
    assert stored["status"] == "completed" and stored["patient_id"] == world.patient_a


def _other_patient_in_clinic_a(db, world):
    return db.patients.insert_one({"clinic_id": world.clinic_a, "is_active": True,
                                   "personal_info": {"first_name": "Carl", "last_name": "C"}}).inserted_id


@pytest.mark.parametrize("make_appt", [
    pytest.param(lambda db, w: _appt(db, w.clinic_b, w.patient_b, name="Bobmarker Bravo"), id="foreign-clinic"),
    pytest.param(lambda db, w: _appt(db, w.clinic_a, w.patient_a, date=FUTURE), id="future"),
    pytest.param(lambda db, w: _appt(db, w.clinic_a, w.patient_a, status="cancelled"), id="cancelled"),
    pytest.param(lambda db, w: _appt(db, w.clinic_a, _other_patient_in_clinic_a(db, w)), id="other-patient"),
    pytest.param(lambda db, w: "not-an-id", id="malformed"),
])
def test_unlinkable_appointment_saves_treatment_unlinked(real_client, as_user, world, db, make_appt):
    appt = make_appt(db, world)
    before = db.appointments.find_one({"_id": appt}) if isinstance(appt, ObjectId) else None
    as_user("dentist")
    real_client.post(f"/patients/{world.patient_a}/treatments/add", data=_treatment_form(appt))
    t = db.treatment_records.find_one({"procedure": "Tooth Extraction"})
    assert t is not None and "appointment_id" not in t   # record kept, link refused
    if before:
        assert db.appointments.find_one({"_id": appt})["status"] == before["status"]


def test_editing_treatment_keeps_its_visit_link(real_client, as_user, world, db):
    appt = _appt(db, world.clinic_a, world.patient_a)
    as_user("dentist")
    real_client.post(f"/patients/{world.patient_a}/treatments/add", data=_treatment_form(appt))
    t = db.treatment_records.find_one({"appointment_id": appt})
    real_client.post(f"/treatments/{t['_id']}/edit", data=_treatment_form(procedure="Crown / Bridge"))
    assert db.treatment_records.find_one({"_id": t["_id"]})["appointment_id"] == appt


# ── Status changes from the calendar ─────────────────────────────────────────

def test_no_show_on_past_visit(real_client, as_user, world, db):
    appt = _appt(db, world.clinic_a, world.patient_a)
    as_user("staff")
    res = real_client.put(f"/appointments/api/{appt}", json={"status": "no-show"})
    assert res.get_json()["success"] is True
    assert db.appointments.find_one({"_id": appt})["status"] == "no-show"
    assert "no_show" in _actions(db)


def test_no_show_refused_for_future_visit(real_client, as_user, world, db):
    appt = _appt(db, world.clinic_a, world.patient_a, date=FUTURE)
    as_user("dentist")
    res = real_client.put(f"/appointments/api/{appt}", json={"status": "no-show"})
    assert res.status_code == 400
    assert db.appointments.find_one({"_id": appt})["status"] == "scheduled"


def test_completed_cannot_be_set_directly(real_client, as_user, world, db):
    appt = _appt(db, world.clinic_a, world.patient_a)
    as_user("dentist")
    res = real_client.put(f"/appointments/api/{appt}", json={"status": "completed"})
    assert res.status_code == 400
    assert db.appointments.find_one({"_id": appt})["status"] == "scheduled"


def test_completed_visit_with_treatments_cannot_be_reopened(real_client, as_user, world, db):
    appt = _appt(db, world.clinic_a, world.patient_a)
    as_user("dentist")
    real_client.post(f"/patients/{world.patient_a}/treatments/add", data=_treatment_form(appt))
    res = real_client.put(f"/appointments/api/{appt}", json={"status": "cancelled"})
    assert res.status_code == 400
    assert db.appointments.find_one({"_id": appt})["status"] == "completed"


def test_completed_visit_without_treatments_can_be_reopened(real_client, as_user, world, db):
    appt = _appt(db, world.clinic_a, world.patient_a, status="completed")
    as_user("dentist")
    res = real_client.put(f"/appointments/api/{appt}", json={"status": "scheduled"})
    assert res.get_json()["success"] is True
    assert db.appointments.find_one({"_id": appt})["status"] == "scheduled"
    assert "reopen" in _actions(db)


def test_cancel_still_audited_as_cancel(real_client, as_user, world, db):
    as_user("dentist")
    real_client.put(f"/appointments/api/{world.appointment_a}", json={"status": "cancelled"})
    assert "cancel" in _actions(db)


# ── Calendar API carries the visit (but no amounts) ──────────────────────────

def test_calendar_api_sends_visit_without_amounts(real_client, as_user, world, db):
    appt = _appt(db, world.clinic_a, world.patient_a)
    as_user("dentist")
    real_client.post(f"/patients/{world.patient_a}/treatments/add",
                     data=_treatment_form(appt, amount_paid="300"))
    data = real_client.get("/appointments/api?start_date=2026-01-01&end_date=2026-01-31").get_json()
    [row] = [a for a in data["appointments"] if a["id"] == str(appt)]
    assert row["visit"]["state"] == visits.STATE_ATTENTION
    assert row["visit"]["procedures"] == ["Tooth Extraction"]
    assert visits.REASON_BALANCE in row["visit"]["reasons"]
    assert f"visit={appt}" in row["visit"]["url"]
    body = real_client.get("/appointments/api?start_date=2026-01-01&end_date=2026-01-31").get_data(as_text=True)
    assert "800" not in body and "charged" not in body and "balance\"" not in body


def test_calendar_api_flags_unmarked_past_visit(real_client, as_user, world, db):
    appt = _appt(db, world.clinic_a, world.patient_a)
    as_user("dentist")
    data = real_client.get("/appointments/api?start_date=2026-01-01&end_date=2026-01-31").get_json()
    [row] = [a for a in data["appointments"] if a["id"] == str(appt)]
    assert row["visit"]["reasons"] == [visits.REASON_NOT_MARKED] and row["can_complete"] is True


# ── Visit history list ───────────────────────────────────────────────────────

def _history(real_client, **params):
    query = "&".join(f"{k}={v}" for k, v in params.items())
    return real_client.get(f"/appointments/history?start=2026-01-01&end=2026-01-31&{query}")


def test_history_lists_visit_with_amounts(real_client, as_user, world, db):
    appt = _appt(db, world.clinic_a, world.patient_a)
    as_user("staff")
    real_client.post(f"/patients/{world.patient_a}/treatments/add",
                     data=_treatment_form(appt, amount_paid="300"))
    html = _history(real_client).get_data(as_text=True)
    assert "Alicemarker Alpha" in html and "Tooth Extraction" in html
    assert "PHP 800.00" in html and "PHP 500.00" in html
    assert f"visit={appt}" in html


def test_history_does_not_leak_other_tenants(real_client, as_user, world, db):
    _appt(db, world.clinic_a, world.patient_a)
    as_user("outsider")
    res = _history(real_client)
    assert res.status_code == 200 and "Alicemarker" not in res.get_data(as_text=True)


def test_history_foreign_clinic_filter_fails_closed(real_client, as_user, world, db):
    _appt(db, world.clinic_b, world.patient_b, name="Bobmarker Bravo")
    as_user("dentist")
    html = _history(real_client, clinic_id=str(world.clinic_b)).get_data(as_text=True)
    assert "Bobmarker" not in html


def test_history_attention_filter(real_client, as_user, world, db):
    _appt(db, world.clinic_a, world.patient_a, name="Unmarked Person")
    _appt(db, world.clinic_a, world.patient_a, status="cancelled", name="Cancelled Person")
    as_user("dentist")
    html = _history(real_client, status="attention").get_data(as_text=True)
    assert "Unmarked Person" in html and "Cancelled Person" not in html
    html = _history(real_client, status="cancelled").get_data(as_text=True)
    assert "Cancelled Person" in html and "Unmarked Person" not in html


def test_history_search_is_regex_escaped(real_client, as_user, world, db):
    _appt(db, world.clinic_a, world.patient_a)
    as_user("dentist")
    assert "Alicemarker Alpha" not in _history(real_client, q=".*").get_data(as_text=True)
    assert "Alicemarker Alpha" in _history(real_client, q="alicemarker").get_data(as_text=True)


def test_history_tolerates_garbage_params(real_client, as_user, world, db):
    as_user("dentist")
    res = real_client.get("/appointments/history?start=nope&end=2026-13-45&page=x&status=evil")
    assert res.status_code == 200


def test_history_caps_the_date_range(real_client, as_user, world, db):
    as_user("dentist")
    html = real_client.get("/appointments/history?start=2000-01-01&end=2026-01-31").get_data(as_text=True)
    assert 'value="2000-01-01"' not in html and 'value="2025-01-30"' in html


# ── Patient detail opened from a visit ───────────────────────────────────────

def test_patient_detail_highlights_visit_rows(real_client, as_user, world, db):
    appt = _appt(db, world.clinic_a, world.patient_a)
    as_user("dentist")
    real_client.post(f"/patients/{world.patient_a}/treatments/add", data=_treatment_form(appt))
    html = real_client.get(f"/patients/{world.patient_a}?tab=treatment&visit={appt}").get_data(as_text=True)
    assert html.count("visit-highlight") == 1
    assert 'id="add-treatment-to-visit"' in html
    assert 'class="tab-pane fade show active" id="treatment-history"' in html


def test_patient_detail_default_tab_unchanged(real_client, as_user, world, db):
    as_user("dentist")
    html = real_client.get(f"/patients/{world.patient_a}").get_data(as_text=True)
    assert 'class="tab-pane fade show active" id="medical-history"' in html
    assert "visit-highlight" not in html


def test_patient_detail_ignores_malformed_visit(real_client, as_user, world, db):
    as_user("dentist")
    res = real_client.get(f"/patients/{world.patient_a}?tab=treatment&visit=garbage")
    assert res.status_code == 200 and "visit-highlight" not in res.get_data(as_text=True)


# ── Backfill script ──────────────────────────────────────────────────────────

def _backfill_module():
    path = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "backfill_visit_links.py"
    spec = importlib.util.spec_from_file_location("backfill_visit_links", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _plain_treatment(db, world, date=PAST, patient=None):
    return db.treatment_records.insert_one({
        "patient_id": patient or world.patient_a, "clinic_id": world.clinic_a, "date": date,
        "procedure": "Consultation", "amount_charged": 0.0, "amount_paid": 0.0,
        "created_at": utcnow(),
    }).inserted_id


def test_backfill_links_unambiguous_match(world, db):
    bf = _backfill_module()
    appt = _appt(db, world.clinic_a, world.patient_a)
    t = _plain_treatment(db, world)
    plan = bf.plan_links(db, today="2026-06-15")
    assert [(p["appointment_id"], p["treatment_ids"]) for p in plan.links] == [(appt, [t])]
    assert "appointment_id" not in db.treatment_records.find_one({"_id": t})   # dry run: no writes

    bf.apply_links(db, plan.links)
    assert db.treatment_records.find_one({"_id": t})["appointment_id"] == appt
    assert db.appointments.find_one({"_id": appt})["status"] == "completed"
    assert bf.plan_links(db, today="2026-06-15").links == []   # idempotent


def test_backfill_skips_ambiguous_and_unsafe_cases(world, db):
    bf = _backfill_module()
    # two appointments, same patient + day -> ambiguous
    _appt(db, world.clinic_a, world.patient_a, date="2026-01-11")
    _appt(db, world.clinic_a, world.patient_a, date="2026-01-11")
    _plain_treatment(db, world, date="2026-01-11")
    # cancelled appointment -> never touched
    _appt(db, world.clinic_a, world.patient_a, date="2026-01-12", status="cancelled")
    _plain_treatment(db, world, date="2026-01-12")
    # walk-in without patient_id -> no exact key
    _appt(db, world.clinic_a, date="2026-01-13", name="Walk In")
    _plain_treatment(db, world, date="2026-01-13")
    # treatment already linked elsewhere -> left alone
    other = _appt(db, world.clinic_a, world.patient_a, date="2026-01-14")
    db.treatment_records.insert_one({"patient_id": world.patient_a, "clinic_id": world.clinic_a,
                                     "date": "2026-01-14", "appointment_id": ObjectId()})
    plan = bf.plan_links(db, today="2026-06-15")
    assert plan.links == []
    assert plan.ambiguous == 1
    assert db.appointments.find_one({"_id": other})["status"] == "scheduled"


def test_backfill_refuses_prod_without_flag():
    bf = _backfill_module()
    assert bf.looks_like_prod("dental_portal_prod")
    assert not bf.looks_like_prod("dental_portal")
