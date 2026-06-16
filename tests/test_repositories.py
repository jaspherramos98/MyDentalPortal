"""Unit tests for the thin data-access layer (blueprints/repositories).

These hit mongomock directly — no Flask context needed, since repository
functions take explicit args (no hidden session reads).
"""
from bson.objectid import ObjectId

from blueprints.repositories import patients as patient_repo
from blueprints.repositories import clinics as clinic_repo
from blueprints.repositories import charts as charts_repo
from blueprints.repositories import appointments as appt_repo
from blueprints.repositories import treatments as treatment_repo


# ── patients repo ───────────────────────────────────────────────────────────
def test_patients_get_found_and_missing(db, seed_patient):
    patient_id, _ = seed_patient(owner_id=str(ObjectId()))
    assert patient_repo.get(str(patient_id))["_id"] == patient_id
    assert patient_repo.get(str(ObjectId())) is None


def test_patients_get_invalid_id_returns_none(db):
    assert patient_repo.get("not-an-object-id") is None


def test_patients_get_for_owner_grants_owner(db, seed_patient):
    owner = str(ObjectId())
    patient_id, clinic_id = seed_patient(owner)
    patient, clinic = patient_repo.get_for_owner(str(patient_id), owner)
    assert patient["_id"] == patient_id
    assert clinic["_id"] == clinic_id


def test_patients_get_for_owner_denies_other(db, seed_patient):
    patient_id, _ = seed_patient(owner_id=str(ObjectId()))
    patient, clinic = patient_repo.get_for_owner(str(patient_id), str(ObjectId()))
    assert patient is not None       # patient exists...
    assert clinic is None            # ...but access is denied


def test_patients_get_for_owner_missing(db):
    assert patient_repo.get_for_owner(str(ObjectId()), str(ObjectId())) == (None, None)


def test_ensure_nested_fills_and_preserves():
    patient = {"medical_history": {"allergies": {"penicillin": True}}}
    out = patient_repo.ensure_nested(patient)
    # Missing top-level sections created as empty dicts.
    assert out["personal_info"] == {}
    assert out["insurance_info"] == {}
    # Existing nested data preserved, missing sub-dicts created.
    assert out["medical_history"]["allergies"] == {"penicillin": True}
    assert out["medical_history"]["women_health"] == {}
    # Regression: detail.html reads medical_history.conditions — ensure_nested
    # must backfill THAT key (not the dead 'medical_conditions') so a patient
    # missing it doesn't break the detail page.
    assert out["medical_history"]["conditions"] == {}
    assert "medical_conditions" not in out["medical_history"]


def test_ensure_nested_replaces_non_dict():
    out = patient_repo.ensure_nested({"personal_info": "oops-a-string"})
    assert out["personal_info"] == {}


# ── clinics repo ────────────────────────────────────────────────────────────
def test_clinics_owned_filters(db):
    owner = str(ObjectId())
    active = ObjectId()
    db.clinics.insert_many([
        {"_id": active, "owner_id": owner, "is_active": True},
        {"_id": ObjectId(), "owner_id": owner, "is_active": False},
        {"_id": ObjectId(), "owner_id": str(ObjectId()), "is_active": True},
    ])
    assert clinic_repo.owned_ids(owner) == [active]
    assert {c["_id"] for c in clinic_repo.owned_by(owner)} == {active}
    assert len(clinic_repo.owned_by(owner, active_only=False)) == 2
    assert clinic_repo.get_owned(active, owner)["_id"] == active
    assert clinic_repo.get_owned(active, str(ObjectId())) is None


# ── charts repo ─────────────────────────────────────────────────────────────
def test_charts_insert_get_and_upsert(db):
    patient_id = ObjectId()
    assert charts_repo.get_by_patient(str(patient_id)) is None

    charts_repo.insert({"patient_id": patient_id, "teeth_status": {"11": {"notes": ""}}})
    assert charts_repo.get_by_patient(str(patient_id)) is not None

    charts_repo.upsert(str(patient_id), {"teeth_status": {"11": {"notes": "caries"}}}, "actor-1")
    saved = charts_repo.get_by_patient(str(patient_id))
    assert saved["teeth_status"]["11"]["notes"] == "caries"
    assert saved["updated_by"] == "actor-1"
    assert "updated_at" in saved


def test_charts_upsert_creates_when_absent(db):
    patient_id = ObjectId()
    charts_repo.upsert(str(patient_id), {"teeth_status": {}}, "actor-1")
    assert db.dental_charts.count_documents({"patient_id": patient_id}) == 1


# ── patients.active_in_clinics ───────────────────────────────────────────────
def test_patients_active_in_clinics_scopes_and_sorts(db):
    c1, c2, other = ObjectId(), ObjectId(), ObjectId()
    db.patients.insert_many([
        {"_id": ObjectId(), "clinic_id": c1, "is_active": True,
         "personal_info": {"first_name": "Bob"}},
        {"_id": ObjectId(), "clinic_id": c2, "is_active": True,
         "personal_info": {"first_name": "Ann"}},
        {"_id": ObjectId(), "clinic_id": c1, "is_active": False,   # inactive -> excluded
         "personal_info": {"first_name": "Zed"}},
        {"_id": ObjectId(), "clinic_id": other, "is_active": True,  # other clinic -> excluded
         "personal_info": {"first_name": "Cat"}},
    ])
    out = patient_repo.active_in_clinics([c1, c2])
    names = [p["personal_info"]["first_name"] for p in out]
    assert names == ["Ann", "Bob"]  # scoped to c1+c2, active only, sorted by first_name


# ── appointments repo ────────────────────────────────────────────────────────
def _appt(clinic_id, date="2026-07-01", time="10:00", **extra):
    doc = {"clinic_id": clinic_id, "date": date, "time": time, "duration": 30,
           "is_active": True, "status": "scheduled"}
    doc.update(extra)
    return doc


def test_appt_insert_get_and_invalid_id(db):
    clinic_id = ObjectId()
    appt_id = appt_repo.insert(_appt(clinic_id, patient_name="X"))
    assert isinstance(appt_id, str)
    got = appt_repo.get(appt_id)
    assert got["patient_name"] == "X"
    assert appt_repo.get("not-an-id") is None
    assert appt_repo.get(str(ObjectId())) is None


def test_appt_find_in_range_scopes_filters_and_sorts(db):
    c1, c2 = ObjectId(), ObjectId()
    appt_repo.insert(_appt(c1, date="2026-07-02", time="09:00", tag="b"))
    appt_repo.insert(_appt(c1, date="2026-07-01", time="11:00", tag="a"))
    appt_repo.insert(_appt(c2, date="2026-07-01", time="08:00", tag="c"))
    appt_repo.insert(_appt(c1, date="2026-08-01", time="08:00", tag="out"))  # out of range
    appt_repo.insert(_appt(c1, date="2026-07-01", time="07:00", tag="inactive", is_active=False))

    # All owner clinics, sorted by (date, time):
    #   c = 07-01 08:00, a = 07-01 11:00, b = 07-02 09:00
    rows = appt_repo.find_in_range([c1, c2], None, "2026-07-01", "2026-07-31")
    assert [r["tag"] for r in rows] == ["c", "a", "b"]
    # Narrow to a single clinic.
    only_c1 = appt_repo.find_in_range([c1, c2], str(c1), "2026-07-01", "2026-07-31")
    assert {r["clinic_id"] for r in only_c1} == {c1}


def test_appt_find_active_on_day_excludes_cancelled_and_self(db):
    clinic_id = ObjectId()
    keep = appt_repo.insert(_appt(clinic_id, time="10:00"))
    appt_repo.insert(_appt(clinic_id, time="11:00", status="cancelled"))  # excluded
    skip = appt_repo.insert(_appt(clinic_id, time="12:00"))
    rows = appt_repo.find_active_on_day(clinic_id, "2026-07-01", exclude_id=skip)
    ids = {str(r["_id"]) for r in rows}
    assert keep in ids and skip not in ids
    assert all(r["status"] != "cancelled" for r in rows)


def test_appt_update_set_and_soft_delete(db):
    clinic_id = ObjectId()
    appt_id = appt_repo.insert(_appt(clinic_id))
    appt_repo.update_set(appt_id, {"status": "completed", "notes": "done"})
    got = appt_repo.get(appt_id)
    assert got["status"] == "completed" and got["notes"] == "done"

    appt_repo.soft_delete(appt_id)
    gone = appt_repo.get(appt_id)
    assert gone["is_active"] is False and "deleted_at" in gone


# ── treatments repo ──────────────────────────────────────────────────────────
def test_treatment_insert_get_and_invalid_id(db):
    pid = ObjectId()
    tid = treatment_repo.insert({"patient_id": pid, "procedure": "filling", "date": "2026-07-01"})
    assert isinstance(tid, str)
    assert treatment_repo.get(tid)["procedure"] == "filling"
    assert treatment_repo.get("not-an-id") is None
    assert treatment_repo.get(str(ObjectId())) is None


def test_treatment_list_for_patient_scopes_and_sorts(db):
    p1, p2 = ObjectId(), ObjectId()
    treatment_repo.insert({"patient_id": p1, "date": "2026-07-01", "tag": "old"})
    treatment_repo.insert({"patient_id": p1, "date": "2026-07-05", "tag": "new"})
    treatment_repo.insert({"patient_id": p2, "date": "2026-07-09", "tag": "other"})
    rows = treatment_repo.list_for_patient(str(p1))
    assert [r["tag"] for r in rows] == ["new", "old"]  # this patient only, newest first


def test_treatment_update_set_and_delete(db):
    tid = treatment_repo.insert({"patient_id": ObjectId(), "balance": 500.0})
    treatment_repo.update_set(tid, {"amount_paid": 500.0, "balance": 0.0})
    assert treatment_repo.get(tid)["balance"] == 0.0

    treatment_repo.delete(tid)
    assert treatment_repo.get(tid) is None  # hard delete
