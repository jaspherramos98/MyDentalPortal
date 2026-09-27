"""End-to-end browser tests — the REAL app, a REAL browser, a THROWAWAY database.

Run (local only, never CI, never prod):
    pip install -r requirements-e2e.txt && python -m playwright install chromium
    pytest e2e                 # ~1-2 min; add --headed to watch

Safety: boots its own app server on 127.0.0.1:5055 against `dental_portal_e2e`
(refuses any other name), drops and re-seeds that DB, and drops it at the end.
Your dev DB and prod are never touched. Each role logs in ONCE per session and
the session is reused — login is rate-limited (10/min) and the suite must not
trip its own brute-force protection.
"""
import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright
from pymongo import MongoClient

ROOT = Path(__file__).resolve().parent.parent
HOST, PORT = "127.0.0.1", 5055
BASE_URL = f"http://{HOST}:{PORT}"
DB_NAME = "dental_portal_e2e"
MONGO_URI = f"mongodb://localhost:27017/{DB_NAME}"

# Credentials created by app.py's first-run seed + scripts/seed_dev.py (local only).
USERS = {
    "admin": ("admin@dental.com", "admin123"),          # owns the seeded clinics
    "staff": ("staff@dev.local", "devpass123"),         # linked staff of admin
    "outsider": ("dentist2@dev.local", "devpass123"),   # separate dentist + clinic
}
VIEWPORTS = {
    "desktop": {"width": 1366, "height": 900},
    "ipad": {"width": 1024, "height": 768},
    "phone": {"width": 390, "height": 844},
}

assert "e2e" in DB_NAME and "prod" not in DB_NAME     # never point this at real data


def _port_free(port):
    with socket.socket() as s:
        return s.connect_ex((HOST, port)) != 0


def _wait_healthy(timeout=60):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"{BASE_URL}/health", timeout=2) as r:
                if r.status == 200:
                    return
        except OSError:
            time.sleep(0.5)
    raise RuntimeError("e2e app server did not become healthy")


@pytest.fixture(scope="session")
def server():
    """A fresh, seeded app server for the whole session."""
    assert _port_free(PORT), f"port {PORT} is busy — stop whatever is using it"
    client = MongoClient("mongodb://localhost:27017", serverSelectionTimeoutMS=5000)
    client.drop_database(DB_NAME)
    env = dict(os.environ, MONGO_URI=MONGO_URI, PORT=str(PORT), FLASK_ENV="development",
               FLASK_DEBUG="0", SENTRY_DSN="", PYTHONUNBUFFERED="1")
    log = open(ROOT / "e2e" / "server.log", "w", encoding="utf-8")
    proc = subprocess.Popen([sys.executable, "app.py"], cwd=ROOT, env=env,
                            stdout=log, stderr=subprocess.STDOUT)
    try:
        _wait_healthy()
        subprocess.run([sys.executable, "scripts/seed_dev.py"], cwd=ROOT, env=env,
                       check=True, capture_output=True)
        yield {"db": client[DB_NAME]}
    finally:
        proc.terminate()
        proc.wait(timeout=15)
        log.close()
        client.drop_database(DB_NAME)
        client.close()


@pytest.fixture(scope="session")
def browser(server):
    with sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()


@pytest.fixture(scope="session")
def auth_state(browser):
    """role -> storage state (cookies) from one real login per role."""
    states = {}

    def get(role):
        if role not in states:
            ctx = browser.new_context()
            page = ctx.new_page()
            email, password = USERS[role]
            page.goto(f"{BASE_URL}/login")
            page.fill("input[name=email]", email)
            page.fill("input[name=password]", password)
            with page.expect_navigation():
                page.click("button[type=submit]")
            assert page.url.endswith("/dashboard"), f"{role} login failed: {page.url}"
            states[role] = ctx.storage_state()
            ctx.close()
        return states[role]
    return get


@pytest.fixture
def db(server):
    return server["db"]


class Session:
    """A logged-in browser page that records JavaScript errors."""

    def __init__(self, context, page):
        self.context, self.page, self.errors = context, page, []
        page.on("pageerror", lambda e: self.errors.append(f"{page.url}: {e}"))
        page.on("console", lambda m: self.errors.append(f"{page.url}: {m.text}")
                if m.type == "error" and "Failed to load resource" not in m.text else None)
        page.on("dialog", lambda d: d.accept())       # confirm() on delete etc.

    def goto(self, path):
        return self.page.goto(BASE_URL + path)


@pytest.fixture
def open_as(browser, auth_state):
    """open_as('staff', viewport='phone') -> Session. Fails the test on any JS error."""
    sessions = []

    def _open(role=None, viewport="desktop"):
        kwargs = {"viewport": VIEWPORTS[viewport], "base_url": BASE_URL}
        if role:
            kwargs["storage_state"] = auth_state(role)
        ctx = browser.new_context(**kwargs)
        s = Session(ctx, ctx.new_page())
        sessions.append(s)
        return s

    yield _open
    errors = [e for s in sessions for e in s.errors]
    for s in sessions:
        s.context.close()
    assert errors == [], "JavaScript errors:\n" + "\n".join(errors)


@pytest.fixture
def seeded(db):
    """Handles to seeded records (admin's clinic + a patient, the outsider's patient)."""
    admin = db.users.find_one({"email": USERS["admin"][0]})
    clinic = db.clinics.find_one({"owner_id": str(admin["_id"]), "is_active": True})
    patient = db.patients.find_one({"clinic_id": clinic["_id"], "is_active": True,
                                    "seed_tag": "dev"})
    outsider = db.users.find_one({"email": USERS["outsider"][0]})
    other_clinic = db.clinics.find_one({"owner_id": str(outsider["_id"])})
    other_patient = db.patients.find_one({"clinic_id": other_clinic["_id"]})
    return {"admin": admin, "clinic": clinic, "patient": patient,
            "other_patient": other_patient}
