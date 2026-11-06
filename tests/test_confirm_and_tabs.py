"""The app's own confirm popup (no native confirm()) and patient-page actions
returning to the tab they came from."""
import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
SACRED = {"dental_chart.html"}          # chart code is off-limits (CLAUDE.md)


def _sources():
    for path in list((ROOT / "templates").rglob("*.html")) + list((ROOT / "static" / "js").glob("*.js")):
        if path.name not in SACRED:
            yield path


def test_no_native_confirm_dialogs():
    """Use data-confirm on forms or AppConfirm() in JS — never the browser's confirm()."""
    offenders = []
    for path in _sources():
        text = path.read_text(encoding="utf-8")
        for m in re.finditer(r"(?<![\w.])confirm\(", text):
            line = text.count("\n", 0, m.start()) + 1
            offenders.append(f"{path.relative_to(ROOT)}:{line}")
    assert offenders == []


def test_confirm_script_is_on_every_page(real_client, as_user):
    as_user("dentist")
    for page in ("/dashboard", "/appointments"):
        assert "js/confirm-dialog.js" in real_client.get(page).get_data(as_text=True), page


def test_delete_treatment_form_uses_app_popup(real_client, as_user, world):
    as_user("dentist")
    html = real_client.get(f"/patients/{world.patient_a}").get_data(as_text=True)
    form = re.search(r'<form[^>]*action="/treatments/%s/delete"[^>]*>' % world.treatment_a, html).group(0)
    assert 'data-confirm="Delete Oral prophylaxis (Sep 01, 2026)?' in form
    assert "data-confirm-danger" in form and "onsubmit" not in form


def test_confirm_message_is_attribute_escaped(real_client, as_user, world, db):
    db.treatment_records.update_one({"_id": world.treatment_a},
                                    {"$set": {"procedure": 'X" onmouseover="alert(1)'}})
    as_user("dentist")
    html = real_client.get(f"/patients/{world.patient_a}").get_data(as_text=True)
    assert 'onmouseover="alert(1)' not in html


def test_header_actions_are_separate_buttons(real_client, as_user, world):
    as_user("dentist")
    html = real_client.get(f"/patients/{world.patient_a}").get_data(as_text=True)
    assert 'class="d-flex flex-wrap gap-2 patient-actions"' in html
    assert "btn-group patient-actions" not in html


# ── staying on the tab ───────────────────────────────────────────────────────

@pytest.mark.parametrize("tab, pane", [
    ("medical", "medical-history"), ("dental", "dental-history"),
    ("treatment", "treatment-history"), ("prescriptions", "prescriptions"),
    ("files", "files"), ("personal", "personal-info"),
])
def test_any_tab_can_be_opened_by_url(real_client, as_user, world, tab, pane):
    as_user("dentist")
    html = real_client.get(f"/patients/{world.patient_a}?tab={tab}").get_data(as_text=True)
    assert f'class="tab-pane fade show active" id="{pane}"' in html
    assert html.count("tab-pane fade show active") == 1


def test_unknown_tab_falls_back_to_medical(real_client, as_user, world):
    as_user("dentist")
    html = real_client.get(f"/patients/{world.patient_a}?tab=<script>").get_data(as_text=True)
    assert 'class="tab-pane fade show active" id="medical-history"' in html


def test_tab_forms_report_their_tab(real_client, as_user, world):
    as_user("dentist")
    html = real_client.get(f"/patients/{world.patient_a}").get_data(as_text=True)
    form = re.search(r'<form[^>]*action="/treatments/%s/delete".*?</form>' % world.treatment_a,
                     html, re.S).group(0)
    assert 'name="return_tab" value="treatment"' in form


def test_delete_treatment_returns_to_treatment_tab(real_client, as_user, world, db):
    as_user("dentist")
    res = real_client.post(f"/treatments/{world.treatment_a}/delete", data={"return_tab": "treatment"})
    assert res.status_code == 302
    assert res.location.endswith(f"/patients/{world.patient_a}?tab=treatment#treatment-history")
    assert db.treatment_records.find_one({"_id": world.treatment_a}) is None


def test_treatment_actions_default_to_treatment_tab(real_client, as_user, world):
    as_user("dentist")
    res = real_client.post(f"/treatments/{world.treatment_a}/mark-paid")
    assert res.location.endswith("?tab=treatment#treatment-history")


def test_return_tab_is_whitelisted(real_client, as_user, world):
    as_user("dentist")
    res = real_client.post(f"/treatments/{world.treatment_a}/mark-paid",
                           data={"return_tab": "https://evil.example/#x"})
    assert "evil" not in res.location
    assert res.location.endswith("?tab=treatment#treatment-history")     # falls back to default


def test_file_delete_returns_to_files_tab(real_client, as_user, world, db):
    from blueprints.clock import utcnow
    import gridfs
    fid = gridfs.GridFS(db).put(b"x", filename="a.txt")
    doc = db.patient_files.insert_one({"patient_id": world.patient_a, "clinic_id": world.clinic_a,
                                       "file_id": fid, "filename": "a.txt",
                                       "uploaded_at": utcnow()}).inserted_id
    as_user("dentist")
    res = real_client.post(f"/files/{doc}/delete", data={"return_tab": "files"})
    assert res.location.endswith(f"/patients/{world.patient_a}?tab=files#files")
    assert db.patient_files.find_one({"_id": doc}) is None


def test_upload_actions_without_tab_keep_plain_url(real_client, as_user, world, db):
    """No return_tab and no default -> the plain patient URL (old behaviour)."""
    as_user("dentist")
    res = real_client.post(f"/patients/{world.patient_a}/photo/delete")
    assert res.status_code == 302 and res.location.endswith(f"/patients/{world.patient_a}")
