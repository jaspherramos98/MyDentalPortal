"""Tests for the SACRED dental chart: default structure + save/load contract.

The chart template and JS depend on an exact data shape (FDI numbering, the
assessment sections) and on the save route's field-stripping/upsert behaviour.
Nothing else guards these against a silent regression, so these tests lock the
*observable contract* without touching the chart's internals.
"""
from bson.objectid import ObjectId
from flask import session

from blueprints.routes.charts import create_default_dental_chart


PERMANENT = [18, 17, 16, 15, 14, 13, 12, 11, 21, 22, 23, 24, 25, 26, 27, 28,
             38, 37, 36, 35, 34, 33, 32, 31, 41, 42, 43, 44, 45, 46, 47, 48]
DECIDUOUS = [55, 54, 53, 52, 51, 61, 62, 63, 64, 65,
             85, 84, 83, 82, 81, 71, 72, 73, 74, 75]


# ── default structure (FDI numbering) ───────────────────────────────────────
def test_default_chart_has_all_fdi_teeth(app):
    with app.test_request_context():
        session["user_id"] = str(ObjectId())
        chart = create_default_dental_chart(str(ObjectId()))

    teeth = chart["teeth_status"]
    for t in PERMANENT:
        assert str(t) in teeth, f"missing permanent tooth {t}"
    for t in DECIDUOUS:
        assert f"temp_{t}" in teeth, f"missing deciduous tooth {t}"
    # Exactly 32 permanent + 20 deciduous, nothing extra.
    assert len(teeth) == len(PERMANENT) + len(DECIDUOUS) == 52
    # Each tooth carries the notes/colors shape the template reads.
    sample = teeth["11"]
    assert sample == {"notes": "", "colors": {}}


def test_default_chart_has_assessment_sections(app):
    with app.test_request_context():
        session["user_id"] = str(ObjectId())
        chart = create_default_dental_chart(str(ObjectId()))
    for section in ("periodontal_screening", "occlusion", "appliances",
                    "tmd_assessment", "xray_taken"):
        assert section in chart
    assert isinstance(chart["patient_id"], ObjectId)


# ── save route: access control ──────────────────────────────────────────────
def _payload():
    return {"teeth_status": {"11": {"notes": "caries", "colors": {"top": "red"}}}}


def test_update_chart_requires_login(client):
    resp = client.post(f"/charts/update/{ObjectId()}", json=_payload())
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_update_chart_404_for_missing_patient(client, login, db):
    login()
    resp = client.post(f"/charts/update/{ObjectId()}", json=_payload())
    assert resp.status_code == 404
    assert resp.get_json()["success"] is False


def test_update_chart_403_for_other_users_patient(client, login, db, seed_patient):
    login()  # session user is NOT the owner
    patient_id, _ = seed_patient(owner_id=str(ObjectId()))
    resp = client.post(f"/charts/update/{patient_id}", json=_payload())
    assert resp.status_code == 403
    assert resp.get_json()["success"] is False
    # Nothing should have been written.
    assert db.dental_charts.count_documents({"patient_id": patient_id}) == 0


# ── save route: persistence + field-stripping ───────────────────────────────
def test_update_chart_saves_and_round_trips(client, login, db, seed_patient):
    owner = login()
    patient_id, _ = seed_patient(owner)

    resp = client.post(f"/charts/update/{patient_id}", json=_payload())
    assert resp.status_code == 200
    assert resp.get_json()["success"] is True

    saved = db.dental_charts.find_one({"patient_id": patient_id})
    assert saved["teeth_status"]["11"]["notes"] == "caries"
    assert saved["updated_by"] == owner
    assert "updated_at" in saved


def test_update_chart_strips_readonly_fields(client, login, db, seed_patient):
    owner = login()
    patient_id, _ = seed_patient(owner)

    forged = {
        "_id": str(ObjectId()),
        "patient_id": str(ObjectId()),       # attempt to repoint the chart
        "created_by": "somebody-else",
        "created_at": "1999-01-01",
        "teeth_status": {"21": {"notes": "ok", "colors": {}}},
    }
    resp = client.post(f"/charts/update/{patient_id}", json=forged)
    assert resp.status_code == 200

    saved = db.dental_charts.find_one({"patient_id": patient_id})
    # patient_id must remain the real one, not the forged value.
    assert saved["patient_id"] == patient_id
    assert saved.get("created_by") != "somebody-else"
    assert saved["teeth_status"]["21"]["notes"] == "ok"


def test_update_chart_alias_route_works(client, login, db, seed_patient):
    owner = login()
    patient_id, _ = seed_patient(owner)
    # The other registered alias must behave identically.
    resp = client.post(f"/chart/update/{patient_id}", json=_payload())
    assert resp.status_code == 200
    assert db.dental_charts.count_documents({"patient_id": patient_id}) == 1
