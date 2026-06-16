#!/usr/bin/env python3
"""Post-refactor HTTP smoke test (Phase 3 gate). Stdlib only.

Exercises the real WSGI stack against a running instance: login, the main READ
pages, and the key WRITE paths that go through the refactored repository/schema
layer — chart save (SACRED) and appointment create -> cancel -> delete. Any
non-2xx, any 5xx, or any {"success": false} fails the run.

PHI SAFETY: refuses a production-looking BASE_URL. Run against LOCAL only.
Usage: [BASE_URL=...] [EMAIL=...] [PASSWORD=...] python scripts/smoke_test.py
"""
import http.cookiejar
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta

BASE = os.environ.get("BASE_URL", "http://localhost:5000").rstrip("/")
EMAIL = os.environ.get("EMAIL", "admin@dental.com")
PASSWORD = os.environ.get("PASSWORD", "admin123")

if "onrender.com" in BASE or "dental_portal_prod" in BASE:
    sys.exit(f"REFUSING: BASE_URL ({BASE}) looks like production.")

jar = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
results = []  # (name, ok, detail)


def record(name, ok, detail=""):
    results.append((name, ok, detail))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}{(' — ' + detail) if detail else ''}")


def req(method, path, body=None, csrf=None):
    headers = {}
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
        if csrf:
            headers["X-CSRFToken"] = csrf
    r = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    try:
        with opener.open(r, timeout=15) as resp:
            return resp.status, resp.read().decode("utf-8", "replace"), resp.geturl()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace"), e.geturl()


def get_page(name, path, expect_login_ok=False):
    code, body, landed = req("GET", path)
    ok = code == 200 and (expect_login_ok or "/login" not in landed)
    record(name, ok, f"{code}" + ("" if ok else f" landed={landed}"))
    return body


# ── login ──────────────────────────────────────────────────────────────
print(f">>> Smoke test against {BASE} as {EMAIL}")
login_html = get_page("GET /login", "/login", expect_login_ok=True)
m = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', login_html)
csrf = m.group(1) if m else None
code, _, landed = req("POST", "/login", None)  # placeholder to keep opener warm
# real login (form post)
payload = urllib.parse.urlencode(
    {"email": EMAIL, "password": PASSWORD, **({"csrf_token": csrf} if csrf else {})}
).encode()
lr = urllib.request.Request(BASE + "/login", data=payload,
                            headers={"Referer": BASE + "/login",
                                     "Content-Type": "application/x-www-form-urlencoded"})
try:
    opener.open(lr, timeout=15).read()
except urllib.error.HTTPError as e:
    e.read()
_, dash_body, dash_landed = req("GET", "/dashboard")
record("login -> /dashboard authenticated", "/login" not in dash_landed,
       "ok" if "/login" not in dash_landed else "redirected to login")
if "/login" in dash_landed:
    print("\nLogin failed — aborting smoke test."); sys.exit(1)

# ── read paths ───────────────────────────────────────────────────────────
get_page("GET /patients", "/patients")
appts_html = get_page("GET /appointments", "/appointments")
get_page("GET /reports", "/reports")

pid = None
pl = req("GET", "/patients")[1]
mp = re.search(r"/patients/([0-9a-fA-F]{24})", pl)
if mp:
    pid = mp.group(1)
    get_page("GET /patients/<id> (detail)", f"/patients/{pid}")
    get_page("GET /chart/patient/<id>", f"/chart/patient/{pid}")
else:
    record("patient detail + chart", False, "no patient id found in /patients")

# ── write path: chart save (SACRED) ──────────────────────────────────────
if pid:
    code, body, _ = req("POST", f"/charts/update/{pid}",
                        body={"teeth": {}, "smoke_marker": datetime.utcnow().isoformat()},
                        csrf=csrf)
    ok = code == 200 and '"success":true' in body.replace(" ", "")
    record("POST /charts/update/<id> (chart save)", ok, f"{code} {body[:80]}")

# ── write path: appointment create -> cancel -> delete ───────────────────
clinic_id = None
# Clinics are rendered into a JS array as `id: '<24-hex>'`, not an option value.
mc = re.search(r"id:\s*'([0-9a-fA-F]{24})'", appts_html)
if mc:
    clinic_id = mc.group(1)
if clinic_id:
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    code, body, _ = req("POST", "/appointments/api",
                        body={"patient_name": "SMOKE TEST (delete me)",
                              "date": tomorrow, "time": "10:00",
                              "duration": 30, "clinic_id": clinic_id,
                              "type": "checkup"},
                        csrf=csrf)
    created = json.loads(body) if body.strip().startswith("{") else {}
    appt_id = created.get("appointment_id")
    record("POST /appointments/api (create)", code == 200 and created.get("success") is True,
           f"{code} id={appt_id}")
    if appt_id:
        code, body, _ = req("PUT", f"/appointments/api/{appt_id}",
                            body={"status": "cancelled"}, csrf=csrf)
        record("PUT /appointments/api/<id> (cancel)",
               code == 200 and json.loads(body).get("success") is True, str(code))
        code, body, _ = req("DELETE", f"/appointments/api/{appt_id}", body={}, csrf=csrf)
        record("DELETE /appointments/api/<id> (cleanup)",
               code == 200 and json.loads(body).get("success") is True, str(code))
else:
    record("appointment create/cancel/delete", False, "no clinic id found")

# ── summary ──────────────────────────────────────────────────────────────
failed = [n for n, ok, _ in results if not ok]
print(f"\n>>> {len(results) - len(failed)}/{len(results)} passed.")
if failed:
    print(">>> FAILED:", ", ".join(failed)); sys.exit(1)
print(">>> SMOKE TEST PASS — zero 5xx, all flows OK.")
