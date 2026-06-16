#!/usr/bin/env python3
"""Log in once, then write loadtest/targets-authed.txt with the session cookie baked in.

Authenticated routes use a Flask session cookie + CSRF on POST. Vegeta can't do the
login dance itself, so this script:
  1. GETs /login to grab the CSRF token from the form.
  2. POSTs credentials (form-encoded) to obtain the `session` cookie.
  3. Discovers a real patient id (via the patients list HTML) so detail pages get hit.
  4. Writes a Vegeta targets file of READ-ONLY GETs with `Cookie: session=...`.

Standard library only (no pip installs). PHI SAFETY: read-only GETs only, and it
refuses a production-looking BASE_URL.
Usage: [BASE_URL=...] [EMAIL=...] [PASSWORD=...] python loadtest/login.py
"""
import http.cookiejar
import os
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

BASE_URL = os.environ.get("BASE_URL", "http://localhost:5000").rstrip("/")
EMAIL = os.environ.get("EMAIL", "admin@dental.com")
PASSWORD = os.environ.get("PASSWORD", "admin123")

if "onrender.com" in BASE_URL or "dental_portal_prod" in BASE_URL:
    sys.exit(f"REFUSING: BASE_URL ({BASE_URL}) looks like production. Use local or AWS showcase.")

jar = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))


def get(path):
    with opener.open(f"{BASE_URL}{path}", timeout=10) as r:
        return r.read().decode("utf-8", "replace")


# 1. CSRF token from the login form.
login_html = get("/login")
m = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', login_html)
csrf = m.group(1) if m else None

# 2. Authenticate (form post; carries the CSRF token + Referer for Flask-WTF).
payload = {"email": EMAIL, "password": PASSWORD}
if csrf:
    payload["csrf_token"] = csrf
req = urllib.request.Request(
    f"{BASE_URL}/login",
    data=urllib.parse.urlencode(payload).encode(),
    headers={"Referer": f"{BASE_URL}/login",
             "Content-Type": "application/x-www-form-urlencoded"},
)
try:
    opener.open(req, timeout=10).read()
except urllib.error.HTTPError as e:
    e.read()  # consume; cookie may still have been set

cookie = next((c.value for c in jar if c.name == "session"), None)
if not cookie:
    sys.exit("Login failed — no session cookie. Check that the app is up.")

# A session cookie is set even before auth (it holds the CSRF token), so prove we
# are actually logged in: a protected page must return 200, not redirect to /login.
auth_req = urllib.request.Request(f"{BASE_URL}/dashboard")
try:
    with opener.open(auth_req, timeout=10) as r:
        landed = r.geturl()
except urllib.error.HTTPError as e:
    landed = e.geturl()
if "/login" in landed:
    sys.exit(f"Login failed — /dashboard redirected to {landed}. "
             f"Check EMAIL/PASSWORD and that the account is approved + active.")
# Refresh the cookie (it may have been rotated on successful login).
cookie = next((c.value for c in jar if c.name == "session"), cookie)
print(f">>> Logged in as {EMAIL}; authenticated session confirmed.")

# 3. Find one patient id so detail pages are exercised (best-effort).
targets = ["/dashboard", "/patients", "/appointments"]
try:
    pid = re.search(r"/patients/([0-9a-fA-F]{24})", get("/patients"))
    if pid:
        targets.append(f"/patients/{pid.group(1)}")
        print(f">>> Including patient detail: /patients/{pid.group(1)}")
except Exception:
    pass

# 4. Write the Vegeta targets file (HTTP-request format with a header line).
out = Path(__file__).parent / "targets-authed.txt"
lines = []
for i, path in enumerate(targets):
    lines.append(f"GET {BASE_URL}{path}")
    lines.append(f"Cookie: session={cookie}")
    if i != len(targets) - 1:
        lines.append("")  # blank line separates targets
out.write_text("\n".join(lines) + "\n", encoding="utf-8")
print(f">>> Wrote {out} ({len(targets)} read-only targets).")
