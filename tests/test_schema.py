"""Tests for the patient boundary schema (blueprints/models/patient.py) and the
validated repository write path.
"""
import pytest
from bson.objectid import ObjectId
from pydantic import ValidationError

from blueprints.models import validate_patient
from blueprints.repositories import patients as patient_repo


# ── validate_patient ────────────────────────────────────────────────────────
def test_requires_clinic_id():
    with pytest.raises(ValidationError):
        validate_patient({"personal_info": {"first_name": "A"}})


def test_rejects_invalid_clinic_id():
    with pytest.raises(ValidationError):
        validate_patient({"clinic_id": "not-an-object-id"})


def test_coerces_clinic_id_string_to_objectid():
    cid = ObjectId()
    out = validate_patient({"clinic_id": str(cid)})
    assert out["clinic_id"] == cid and isinstance(out["clinic_id"], ObjectId)


def test_fills_missing_sections_and_defaults():
    out = validate_patient({"clinic_id": ObjectId()})
    for section in ("personal_info", "contact_info", "medical_history",
                    "guardian_info", "minor_info", "insurance_info"):
        assert out[section] == {}
    assert out["is_active"] is True


def test_preserves_extra_and_nested_fields():
    cid = ObjectId()
    out = validate_patient({
        "clinic_id": cid,
        "created_by": "user-1",                       # extra field, must survive
        "medical_history": {"allergies": {"penicillin": True}},  # nested, must survive
    })
    assert out["created_by"] == "user-1"
    assert out["medical_history"]["allergies"]["penicillin"] is True


def test_rejects_non_dict_section():
    with pytest.raises(ValidationError):
        validate_patient({"clinic_id": ObjectId(), "personal_info": "oops"})


# ── repository write path ───────────────────────────────────────────────────
def test_create_inserts_validated_doc(db):
    cid = ObjectId()
    pid = patient_repo.create({
        "clinic_id": cid,
        "personal_info": {"first_name": "Jane", "last_name": "Doe"},
        "created_by": "user-1",
    })
    saved = db.patients.find_one({"_id": pid})
    assert saved["clinic_id"] == cid
    assert saved["is_active"] is True
    assert saved["personal_info"]["first_name"] == "Jane"


def test_create_rejects_malformed(db):
    with pytest.raises(ValidationError):
        patient_repo.create({"personal_info": {"first_name": "NoClinic"}})
    assert db.patients.count_documents({}) == 0


def test_update_set_applies_dotted_fields(db, seed_patient):
    patient_id, _ = seed_patient(owner_id=str(ObjectId()))
    patient_repo.update_set(str(patient_id), {"personal_info.first_name": "Renamed"})
    assert db.patients.find_one({"_id": patient_id})["personal_info"]["first_name"] == "Renamed"
