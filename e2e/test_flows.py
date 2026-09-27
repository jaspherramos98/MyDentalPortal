"""User journeys through the real app, per role. See conftest.py for safety/setup."""
import re
from pathlib import Path

import pytest

from conftest import BASE_URL, USERS

ASSETS = Path(__file__).resolve().parent / "assets"
PDF = ASSETS / "report.pdf"
PNG = ASSETS / "photo.png"

FILL_REQUIRED = """(marker) => {
    const f = document.querySelector('form.needs-validation');
    const seen = new Set();
    f.querySelectorAll('input, select, textarea').forEach(el => {
        if (el.type === 'hidden') return;
        if (el.type === 'radio') {
            if (!seen.has(el.name)) {
                (f.querySelector(`input[name="${el.name}"][value="no"]`) || el).checked = true;
                seen.add(el.name);
            }
            return;
        }
        if (el.type === 'checkbox') { if (el.required) el.checked = true; return; }
        if (el.tagName === 'SELECT') { if (!el.value && el.options.length > 1) el.selectedIndex = 1; return; }
        if (!el.required) return;
        el.value = el.type === 'date' ? '1990-01-01' : el.type === 'tel' ? '09170000000'
                 : el.type === 'email' ? 'e2e@example.com' : el.type === 'number' ? '30' : 'E2E';
    });
    f.querySelector('[name=first_name]').value = marker;
    f.querySelector('[name=last_name]').value = 'Tester';
    f.querySelector('[name=cell_phone]').value = '09170000000';
    f.querySelector('[name=privacy_consent]').checked = true;
}"""


def _detail_path(patient):
    return f"/patients/{patient['_id']}"


# ── Auth ─────────────────────────────────────────────────────────────────────

def test_wrong_password_is_rejected(open_as):
    s = open_as()
    s.goto("/login")
    s.page.fill("input[name=email]", USERS["staff"][0])
    s.page.fill("input[name=password]", "not-the-password")
    s.page.click("button[type=submit]")
    s.page.wait_for_load_state()
    assert s.page.url.endswith("/login")


@pytest.mark.parametrize("role", ["admin", "staff", "outsider"])
def test_each_role_reaches_dashboard(open_as, role):
    s = open_as(role)
    s.goto("/dashboard")
    assert s.page.url.endswith("/dashboard")
    assert s.page.locator("nav.navbar").is_visible()


# ── Patients ─────────────────────────────────────────────────────────────────

def test_patient_create_edit_and_pdf(open_as, db):
    s = open_as("staff")
    s.goto("/patients/create")
    s.page.evaluate(FILL_REQUIRED, "E2ECreate")
    s.page.click("form.needs-validation button[type=submit]")
    s.page.wait_for_url(re.compile(r"/patients/[0-9a-f]{24}$"))
    assert db.patients.count_documents({"personal_info.first_name": "E2ECreate"}) == 1
    patient_url = s.page.url

    s.page.goto(patient_url + "/edit")
    s.page.fill("input[name=nickname]", "E2E-Nick")
    s.page.click("#editPatientForm button[type=submit]")
    s.page.wait_for_url(patient_url)
    assert db.patients.find_one({"personal_info.first_name": "E2ECreate"})[
        "personal_info"]["nickname"] == "E2E-Nick"

    pdf = s.context.request.get(patient_url + "/pdf")
    assert pdf.status == 200 and pdf.body()[:5] == b"%PDF-"


def test_outsider_cannot_open_another_clinics_patient(open_as, seeded):
    s = open_as("outsider")
    s.goto(_detail_path(seeded["patient"]))
    assert s.page.url.endswith("/patients")          # bounced to their own list
    assert seeded["patient"]["personal_info"]["first_name"] not in s.page.content()


# ── Dental chart (behaviour only — the chart itself is SACRED) ───────────────

def test_chart_segment_click_and_save(open_as, seeded, db):
    s = open_as("staff")
    s.goto(f"/chart/patient/{seeded['patient']['_id']}")
    s.page.locator(".tooth-segment").first.click()
    with s.page.expect_response(lambda r: "/update/" in r.url and r.request.method == "POST") as resp:
        s.page.click(".save-btn")
    assert resp.value.json()["success"] is True
    assert db.dental_charts.find_one({"patient_id": seeded["patient"]["_id"]}) is not None


# ── Treatments + price confirmation + Next Visit ─────────────────────────────

def test_staff_price_pending_until_dentist_confirms(open_as, seeded, db):
    staff = open_as("staff")
    staff.goto(f"/patients/{seeded['patient']['_id']}/treatments/add")
    proc = staff.page.locator("#procedure")
    if proc.evaluate("e => e.tagName") == "SELECT":
        proc.select_option(index=1)
    else:
        proc.fill("E2E Filling")
    staff.page.fill("#amount_charged", "1234")
    staff.page.fill("#next_visit", "e2e-next-visit")
    staff.page.click("form[data-resilient-submit] button[type=submit]")
    staff.page.wait_for_url(re.compile(_detail_path(seeded["patient"]) + "$"))
    t = db.treatment_records.find_one({"next_visit": "e2e-next-visit"})
    assert t["price_confirmed"] is False

    dentist = open_as("admin")
    dentist.goto(_detail_path(seeded["patient"]))
    dentist.page.click("[data-bs-target='#treatment-history']")
    assert dentist.page.get_by_text("e2e-next-visit").is_visible()
    dentist.page.locator(f"form[action$='/treatments/{t['_id']}/confirm-price'] button").click()
    dentist.page.wait_for_load_state()
    assert db.treatment_records.find_one({"_id": t["_id"]})["price_confirmed"] is True


def test_dropped_connection_on_treatment_add_saves_once(open_as, seeded, db):
    s = open_as("staff")
    s.goto(f"/patients/{seeded['patient']['_id']}/treatments/add")
    proc = s.page.locator("#procedure")
    if proc.evaluate("e => e.tagName") == "SELECT":
        proc.select_option(index=1)
    else:
        proc.fill("E2E Retry")
    s.page.fill("#next_visit", "e2e-dropped")
    drops = {"n": 0}

    def flaky(route):
        if route.request.method == "POST" and drops["n"] < 2:
            drops["n"] += 1
            return route.abort("connectionclosed")
        return route.continue_()
    s.page.route("**/treatments/add", flaky)
    s.page.click("form[data-resilient-submit] button[type=submit]")
    s.page.wait_for_url(re.compile(_detail_path(seeded["patient"]) + "$"), timeout=20000)
    assert drops["n"] == 2
    assert db.treatment_records.count_documents({"next_visit": "e2e-dropped"}) == 1


# ── Appointments calendar ────────────────────────────────────────────────────

def test_calendar_create_appointment(open_as, seeded, db):
    s = open_as("staff")
    s.goto("/appointments")
    s.page.click("button:has(i.fa-plus)[onclick*='openNewAppointment']")
    s.page.select_option("#modalClinicSelect", str(seeded["clinic"]["_id"]))
    s.page.fill("#modalPatientName", "E2E Walk-in")
    s.page.fill("#modalAppointmentDate", "2099-03-03")
    s.page.fill("#modalAppointmentTime", "09:30")
    with s.page.expect_response(lambda r: r.url.endswith("/appointments/api")
                                and r.request.method == "POST") as resp:
        s.page.click("#appointmentModal button[onclick='saveAppointment()']")
    assert resp.value.json()["success"] is True
    assert db.appointments.count_documents({"patient_name": "E2E Walk-in", "date": "2099-03-03"}) == 1


# ── Uploads ──────────────────────────────────────────────────────────────────

def test_photo_file_and_prescription_uploads(open_as, seeded, db):
    s = open_as("staff")
    path = _detail_path(seeded["patient"])
    s.goto(path)
    # Auto-submits on file choice; wait for the save itself (we're already on `path`).
    # Auto-submits on file choice, then the page reloads itself on success.
    with s.page.expect_navigation():
        s.page.set_input_files("#patientPhotoInput", str(PNG))
    assert s.context.request.get(path + "/photo").status == 200

    s.goto(path)
    s.page.click("[data-bs-target='#files']")
    s.page.set_input_files("#file_upload", str(PDF))
    s.page.fill("#file_display_name", "e2e-report")
    with s.page.expect_navigation():                # same URL: wait for the reload
        s.page.click("form[action$='/files/add'] button[type=submit]")
    doc = db.patient_files.find_one({"display_name": "e2e-report"})
    assert s.context.request.get(f"/files/{doc['_id']}/download").body() == PDF.read_bytes()

    s.goto(path)
    s.page.click("[data-bs-target='#prescriptions']")
    s.page.fill("#presc_description", "e2e amoxicillin 500mg")
    with s.page.expect_navigation():                # same URL: wait for the reload
        s.page.click("form[action$='/prescriptions/add'] button[type=submit]")
    assert db.prescriptions.count_documents({"description": "e2e amoxicillin 500mg"}) == 1


# ── Deletion requests ────────────────────────────────────────────────────────

def test_staff_requests_and_dentist_approves_deletion(open_as, seeded, db):
    victim = db.patients.find_one({"clinic_id": seeded["clinic"]["_id"], "is_active": True,
                                   "_id": {"$ne": seeded["patient"]["_id"]}})
    staff = open_as("staff")
    staff.goto(_detail_path(victim))
    staff.page.locator("form[action$='/deletions/request']:has(input[value='patient']) button").first.click()
    staff.page.wait_for_load_state()
    req = db.deletion_requests.find_one({"entity_id": str(victim["_id"])})
    assert req["status"] == "pending"

    dentist = open_as("admin")
    dentist.goto("/deletions")
    dentist.page.locator(f"form[action$='/deletions/{req['_id']}/approve'] button").click()
    dentist.page.wait_for_load_state()
    assert db.patients.find_one({"_id": victim["_id"]})["is_active"] is False


# ── Staff onboarding: invite code -> /join -> works in the dentist's clinics ─

def test_invite_code_join_and_access(open_as, browser, seeded):
    dentist = open_as("admin")
    dentist.goto("/staff")
    dentist.page.click("form[action$='/staff/codes/generate'] button")
    dentist.page.wait_for_load_state()
    flash = dentist.page.locator(".alert-success").first.inner_text()
    code = flash.rsplit(":", 1)[1].strip()

    newbie = open_as()
    newbie.goto("/join")
    newbie.page.fill("input[name=access_code]", code)
    newbie.page.fill("input[name=name]", "E2E Newbie")
    newbie.page.fill("input[name=email]", "e2e.newbie@example.com")
    newbie.page.fill("input[name=password]", "Str0ng!E2E-pass")
    newbie.page.fill("input[name=confirm_password]", "Str0ng!E2E-pass")
    newbie.page.click("button[type=submit]")
    newbie.page.wait_for_load_state()

    newbie.goto("/login")
    newbie.page.fill("input[name=email]", "e2e.newbie@example.com")
    newbie.page.fill("input[name=password]", "Str0ng!E2E-pass")
    newbie.page.click("button[type=submit]")
    newbie.page.wait_for_url(re.compile("/dashboard$"))
    newbie.goto(_detail_path(seeded["patient"]))
    assert newbie.page.url.endswith(str(seeded["patient"]["_id"]))     # linked access works


# ── Admin + oversight pages ──────────────────────────────────────────────────

def test_admin_panel_and_activity_log(open_as):
    s = open_as("admin")
    for path in ("/admin/panel", "/admin/users", "/admin/registrations", "/activity",
                 "/treatments/pending-prices", "/deletions", "/staff", "/reports"):
        resp = s.goto(path)
        assert resp.status == 200 and s.page.url.endswith(path), path
    s.goto("/activity")
    assert s.page.locator("table tbody tr").count() > 0


def test_staff_is_kept_out_of_management_pages(open_as):
    s = open_as("staff")
    for path in ("/admin/panel", "/activity", "/staff", "/clinics/create"):
        s.goto(path)
        assert s.page.url.endswith("/dashboard"), path


def test_service_worker_registers(open_as):
    s = open_as("staff")
    s.goto("/dashboard")
    assert s.page.evaluate("async () => !!(await navigator.serviceWorker.ready)")


assert BASE_URL.startswith("http://127.0.0.1")   # local only
