"""Unit tests for the thin data-access layer (blueprints/repositories).

These hit mongomock directly — no Flask context needed, since repository
functions take explicit args (no hidden session reads).
"""
from bson.objectid import ObjectId

from blueprints.repositories import patients as patient_repo
from blueprints.repositories import clinics as clinic_repo
from blueprints.repositories import charts as charts_repo


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
