"""Templates keep their JavaScript in static/js (2026-09-26).

Guards the extraction: no executable inline <script> (the prerequisite for a
CSP without 'unsafe-inline'), and server data reaches scripts through JSON
islands / data-* attributes — never pasted into code, where names with quotes
used to render as HTML entities (O&#39;Brien) or break the script.
"""
import glob
import json
import re


# The SACRED dental chart keeps its inline script (CLAUDE.md: don't touch chart
# JS); it will get a CSP hash instead.
INLINE_ALLOWED = {"templates/charts/dental_chart.html"}
EXECUTABLE_INLINE = re.compile(r"<script(?![^>]*\b(?:src|type)=)[^>]*>")


def test_no_executable_inline_scripts_in_templates():
    offenders = []
    for path in glob.glob("templates/**/*.html", recursive=True):
        path = path.replace("\\", "/")
        if path in INLINE_ALLOWED:
            continue
        with open(path, encoding="utf-8") as fh:
            if EXECUTABLE_INLINE.search(fh.read()):
                offenders.append(path)
    assert offenders == []


def _island(html, element_id):
    m = re.search(rf'<script type="application/json" id="{element_id}">(.*?)</script>', html, re.S)
    assert m, element_id
    return json.loads(m.group(1))


def test_appointments_data_island_carries_names_verbatim(real_client, as_user, world, db):
    db.clinics.update_one({"_id": world.clinic_a}, {"$set": {"name": "O'Neil \"Dental\" \ Care"}})
    as_user("dentist")
    html = real_client.get("/appointments").get_data(as_text=True)
    data = _island(html, "appointments-data")
    assert data["clinics"][0]["name"] == "O'Neil \"Dental\" \ Care"
    assert data["clinics"][0]["id"] == str(world.clinic_a)
    assert any(p["name"].startswith("Alicemarker") for p in data["patients"])


def test_reports_data_island(real_client, as_user, world):
    as_user("dentist")
    html = real_client.get("/reports").get_data(as_text=True)
    assert isinstance(_island(html, "reports-data"), dict)


def test_next_appointment_modal_passes_patient_name_as_attribute(real_client, as_user, world, db):
    db.patients.update_one({"_id": world.patient_a},
                           {"$set": {"personal_info.first_name": "Ma'ria"}})
    as_user("dentist")
    html = real_client.get(f"/patients/{world.patient_a}/treatments/add").get_data(as_text=True)
    # HTML-escaped in the attribute (the browser decodes it back to Ma'ria).
    assert 'data-patient-name="Ma&#39;ria Alpha"' in html
    assert f'data-patient-id="{world.patient_a}"' in html
    assert "next-appointment-modal.js" in html


def test_extracted_scripts_are_served(real_client):
    for path in glob.glob("static/js/*.js"):
        name = path.replace("\\", "/").split("/")[-1]
        assert real_client.get(f"/static/js/{name}").status_code == 200, name




def test_resilient_submit_is_not_deferred():
    """Page scripts call ResilientSubmit.attach() during parsing; a deferred
    resilient-submit.js isn't defined yet at that point (regression from #42)."""
    with open("templates/base.html", encoding="utf-8") as fh:
        tag = re.search(r"<script[^>]*resilient-submit\.js[^>]*>", fh.read()).group(0)
    assert "defer" not in tag and "async" not in tag
