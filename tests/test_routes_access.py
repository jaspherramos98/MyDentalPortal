"""Characterization tests: who can open which page, on the REAL app.

Pins the current access behaviour of every GET page for five callers
(anonymous, admin, dentist, staff, outsider) so the Phase 1-3 refactors can't
change it silently. See ``world`` in conftest.py for the tenant layout.

Known bugs are ``xfail(strict=True)`` describing the CORRECT behaviour: when a
fix lands the test starts passing, strict turns that into a failure, and the
marker must be removed — the fix can't go unnoticed.
"""
import pytest

MARKER_A = "Alicemarker"   # patient_a's first name (clinic_a / dentist)
MARKER_B = "Bobmarker"     # patient_b's first name (clinic_b / outsider)

ROLES = ["anon", "admin", "dentist", "staff", "outsider"]

# Expected outcome per role, in ROLES order:
#   200         rendered
#   "login"     302 -> /login
#   "dash"      302 -> /dashboard  (403 handler for a logged-in user, or already logged in)
#   "patients"  302 -> /patients   (patient not found / not accessible)
#   "clinics"   302 -> /clinics    (clinic not found / not owned)
#   "new"       302 -> /clinics/create (user has no clinic yet)
#   403         bare 403 (JSON APIs)
#   404         not found
PAGES = [
    # path template                                   anon     admin       dentist staff       outsider
    ("/",                                             ["login", "dash",     "dash", "dash",     "dash"]),
    ("/dashboard",                                    ["login", 200,        200,    200,        200]),
    ("/patients",                                     ["login", 200,        200,    200,        200]),
    ("/patients/create",                              ["login", "new",      200,    200,        200]),
    ("/patients/{patient_a}",                         ["login", "patients", 200,    "patients", "patients"]),
    ("/patients/{patient_a}/edit",                    ["login", "patients", 200,    200,        "patients"]),
    ("/patients/{patient_a}/pdf",                     ["login", "patients", 200,    200,        "patients"]),
    ("/chart/patient/{patient_a}",                    ["login", "patients", 200,    200,        "patients"]),
    ("/chart/patient/{patient_a}/pdf",                ["login", "patients", 200,    200,        "patients"]),
    ("/patients/{patient_a}/treatments/add",          ["login", "patients", 200,    200,        "patients"]),
    ("/treatments/{treatment_a}/edit",                ["login", "patients", 200,    200,        "patients"]),
    ("/api/patients/{patient_a}/treatments",          ["login", 403,        200,    200,        403]),
    ("/appointments",                                 ["login", "new",      200,    200,        200]),
    ("/appointments/api?start=2099-01-01&end=2099-02-01",
                                                      ["login", 403,        200,    200,        200]),
    ("/clinics",                                      ["login", 200,        200,    200,        200]),
    ("/clinics/create",                               ["login", 200,        200,    "dash",     200]),
    ("/clinics/{clinic_a}/edit",                      ["login", "clinics",  200,    "dash",     "clinics"]),
    ("/reports",                                      ["login", 200,        200,    200,        200]),
    ("/settings",                                     ["login", 200,        200,    200,        200]),
    ("/staff",                                        ["login", 200,        200,    "dash",     200]),
    ("/deletions",                                    ["login", 200,        200,    "dash",     200]),
    ("/treatments/pending-prices",                    ["login", 200,        200,    "dash",     200]),
    ("/activity",                                     ["login", 200,        200,    "dash",     200]),
    ("/admin/panel",                                  ["login", 200,        "dash", "dash",     "dash"]),
    ("/admin/users",                                  ["login", 200,        "dash", "dash",     "dash"]),
    ("/admin/registrations",                          ["login", 200,        "dash", "dash",     "dash"]),
    ("/session/keepalive",                            ["login", 200,        200,    200,        200]),
    ("/privacy",                                      [200,     200,        200,    200,        200]),
    ("/login",                                        [200,     "dash",     "dash", "dash",     "dash"]),
    ("/register",                                     [200,     "dash",     "dash", "dash",     "dash"]),
    ("/join",                                         [200,     "dash",     "dash", "dash",     "dash"]),
    ("/health",                                       [200,     200,        200,    200,        200]),
    ("/manifest.webmanifest",                         [200,     200,        200,    200,        200]),
    ("/sw.js",                                        [200,     200,        200,    200,        200]),
    ("/definitely-not-a-page",                        [404,     404,        404,    404,        404]),
]

REDIRECTS = {
    "login": "/login", "dash": "/dashboard", "patients": "/patients",
    "clinics": "/clinics", "new": "/clinics/create",
}

CASES = [
    pytest.param(path, role, expected, id=f"{role}:{path}")
    for path, expected_by_role in PAGES
    for role, expected in zip(ROLES, expected_by_role)
]


def _body(res):
    return res.get_data().decode("utf-8", "replace")   # PDFs are binary


def _fill(path, world):
    return path.format(**{k: v for k, v in vars(world).items()})


@pytest.mark.parametrize("path, role, expected", CASES)
def test_page_access(real_client, as_user, world, path, role, expected):
    as_user(None if role == "anon" else role)
    res = real_client.get(_fill(path, world))
    if isinstance(expected, int):
        assert res.status_code == expected
    else:
        assert res.status_code == 302
        assert res.headers["Location"].split("?")[0].endswith(REDIRECTS[expected])


@pytest.mark.parametrize("path", [p for p, _ in PAGES])
def test_outsider_never_sees_other_tenants_patient(real_client, as_user, world, path):
    """Tenant isolation: nothing dentist B can open renders clinic_a's patient."""
    as_user("outsider")
    res = real_client.get(_fill(path, world))
    assert MARKER_A not in _body(res)


@pytest.mark.parametrize("who", ["dentist", "staff"])
@pytest.mark.parametrize("path", [p for p, _ in PAGES])
def test_clinic_a_team_never_sees_outsider_patient(real_client, as_user, world, who, path):
    as_user(who)
    res = real_client.get(_fill(path, world))
    assert MARKER_B not in _body(res)


def test_dentist_sees_own_patient_in_list_and_dashboard(real_client, as_user, world):
    as_user("dentist")
    assert MARKER_A in _body(real_client.get("/patients"))
    assert MARKER_A in _body(real_client.get("/dashboard"))


# ── Known bugs (Phase 1). These describe the CORRECT behaviour. ─────────────

STAFF_PATIENT_BUG = (
    "Phase 1: list_patients / patient_detail / dashboard use owner-only clinic "
    "queries instead of the membership seam, so linked staff can't see patients"
)


@pytest.mark.xfail(strict=True, reason=STAFF_PATIENT_BUG)
def test_staff_sees_dentists_patient_in_list(real_client, as_user, world):
    as_user("staff")
    assert MARKER_A in _body(real_client.get("/patients"))


@pytest.mark.xfail(strict=True, reason=STAFF_PATIENT_BUG)
def test_staff_can_open_dentists_patient(real_client, as_user, world):
    as_user("staff")
    res = real_client.get(f"/patients/{world.patient_a}")
    assert res.status_code == 200 and MARKER_A in _body(res)


@pytest.mark.xfail(strict=True, reason=STAFF_PATIENT_BUG)
def test_staff_dashboard_shows_dentists_patients(real_client, as_user, world):
    as_user("staff")
    assert MARKER_A in _body(real_client.get("/dashboard"))


# ── Cross-cutting response behaviour ─────────────────────────────────────────

def test_security_headers_on_every_response(real_client):
    res = real_client.get("/login")
    assert res.headers["X-Content-Type-Options"] == "nosniff"
    assert res.headers["X-Frame-Options"] == "DENY"
    assert "default-src 'self'" in res.headers["Content-Security-Policy"]
    assert "Strict-Transport-Security" not in res.headers   # plain-HTTP request


def test_hsts_only_on_https(real_client):
    res = real_client.get("/login", base_url="https://localhost")
    assert res.headers["Strict-Transport-Security"].startswith("max-age=31536000")


def test_authenticated_pages_are_not_cached(real_client, as_user, world):
    as_user("dentist")
    assert "no-store" in real_client.get("/dashboard").headers["Cache-Control"]


def test_service_worker_scope_header(real_client):
    res = real_client.get("/sw.js")
    assert res.headers["Service-Worker-Allowed"] == "/"
    assert res.headers["Content-Type"].startswith("application/javascript")


def test_static_urls_are_cache_busted(real_client):
    assert "main.css?v=" in _body(real_client.get("/login"))


def test_health_reports_database(real_client):
    assert real_client.get("/health").get_json()["database"] == "connected"
