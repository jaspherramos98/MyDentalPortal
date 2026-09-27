"""Shared pytest fixtures for MyDentalPortal.

Design notes
------------
We deliberately do NOT import the real ``app.py``: it runs ``init_database()``
(real index/admin writes) at import time, which would touch a live cluster.
Instead each test builds a minimal Flask app and points the shared ``mongo``
singleton at an in-memory ``mongomock`` database. That keeps tests:

* hermetic — no MongoDB server required, no network, no real PHI touched;
* fast — in-memory;
* honest — they exercise the *real* blueprint code (e.g. ``charts_bp``) and the
  *real* access-control utils, only the storage is faked.

The stub ``auth``/``patients`` blueprints exist solely so ``url_for(...)`` calls
inside the code under test (redirects on the access-denied paths) can resolve.
"""
import mongomock
import mongomock.gridfs
import pytest
from bson.objectid import ObjectId
from flask import Flask, Blueprint

from extensions import mongo
from blueprints.clock import utcnow

# Let the real gridfs package run against mongomock (patient photos/files).
mongomock.gridfs.enable_gridfs_integration()


@pytest.fixture
def db():
    """Point the shared mongo singleton at a fresh in-memory database."""
    client = mongomock.MongoClient()
    database = client["dental_portal_test"]
    # PyMongo() exposes cx/db as plain attributes; set them directly so we never
    # open a real connection.
    mongo.cx = client
    mongo.db = database
    yield database
    client.close()


def _make_app():
    app = Flask(__name__)
    app.config.update(
        TESTING=True,
        SECRET_KEY="test-secret",
        WTF_CSRF_ENABLED=False,
        ADMIN_EMAILS=["boss@dental.com"],
    )

    # Stubs so url_for() targets in the code under test resolve.
    auth = Blueprint("auth", __name__)

    @auth.route("/login")
    def login():
        return "login", 200

    patients = Blueprint("patients", __name__)

    @patients.route("/patients")
    def list_patients():
        return "patients", 200

    @patients.route("/patients/<patient_id>")
    def patient_detail(patient_id):
        return "detail", 200

    app.register_blueprint(auth)
    app.register_blueprint(patients)

    # Test-only routes to exercise the access-control decorators directly.
    from blueprints.utils import login_required, admin_required, role_required, ROLE_DENTIST

    @app.route("/_login_guarded")
    @login_required
    def _login_guarded():
        return "ok", 200

    @app.route("/_admin_guarded")
    @admin_required
    def _admin_guarded():
        return "ok", 200

    @app.route("/_dentist_guarded")
    @role_required(ROLE_DENTIST)
    def _dentist_guarded():
        return "ok", 200

    return app


@pytest.fixture
def app():
    """Minimal app with the real charts blueprint + stubs + guarded test routes."""
    application = _make_app()
    from blueprints.routes.charts import charts_bp
    application.register_blueprint(charts_bp)
    return application


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def login(client):
    """Return a helper that writes an authenticated session for the test client."""
    def _login(user_id=None, email="dentist@dental.com", role="dentist"):
        user_id = user_id or str(ObjectId())
        with client.session_transaction() as sess:
            sess["user_id"] = user_id
            sess["user_email"] = email
            sess["user_role"] = role
            sess["user_name"] = "Test Dentist"
        return user_id
    return _login


@pytest.fixture
def seed_patient(db):
    """Insert a clinic + patient owned by ``owner_id``; return (patient_id, clinic_id)."""
    def _seed(owner_id):
        clinic_id = ObjectId()
        db.clinics.insert_one({
            "_id": clinic_id, "owner_id": owner_id,
            "name": "Test Clinic", "is_active": True,
        })
        patient_id = ObjectId()
        db.patients.insert_one({
            "_id": patient_id, "clinic_id": clinic_id,
            "personal_info": {"first_name": "Test", "last_name": "Patient"},
            "is_active": True,
        })
        return patient_id, clinic_id
    return _seed


# ── Real application (Phase 0) ──────────────────────────────────────────────
# The fixtures above build a minimal stub app for unit-level tests. The ones
# below build the REAL app via factory.create_app() — every blueprint, hook,
# error handler and template — still on mongomock, so route tests exercise
# exactly what gunicorn serves. init_mongo=False keeps the shared ``mongo``
# singleton pointed at the in-memory DB from the ``db`` fixture.

from types import SimpleNamespace
import time

from werkzeug.security import generate_password_hash

REAL_APP_OVERRIDES = {
    "TESTING": True,
    "SECRET_KEY": "test-secret",
    "WTF_CSRF_ENABLED": False,
    "RATELIMIT_ENABLED": False,
    "ADMIN_EMAILS": ["admin@dental.com"],
}


@pytest.fixture
def real_app(db):
    from config import DevelopmentConfig
    from factory import create_app
    return create_app(DevelopmentConfig, overrides=REAL_APP_OVERRIDES, init_mongo=False)


@pytest.fixture
def real_client(real_app):
    return real_app.test_client()


_PASSWORD_HASHES = {}


def _password_hash(password):
    # PBKDF2 is deliberately slow (~0.3s); hash each test password once per run.
    if password not in _PASSWORD_HASHES:
        _PASSWORD_HASHES[password] = generate_password_hash(password)
    return _PASSWORD_HASHES[password]


def _user(db, name, email, role):
    user_id = db.users.insert_one({
        "name": name, "email": email, "role": role,
        "password": _password_hash("pw-" + role),
        "license_number": "LIC-" + name.replace(" ", ""),
        "status": "approved", "is_active": True,
        "created_at": utcnow(),
    }).inserted_id
    return str(user_id)


def _clinic(db, owner_id, name):
    return db.clinics.insert_one({
        "owner_id": owner_id, "name": name, "is_active": True,
        "currency": "PHP", "address": "Obando, Bulacan",
    }).inserted_id


def _patient(db, clinic_id, first, last):
    return db.patients.insert_one({
        "clinic_id": clinic_id,
        "personal_info": {"first_name": first, "last_name": last},
        "contact_info": {"cell_phone": "09170000000"},
        "is_active": True,
        "created_at": utcnow(), "updated_at": utcnow(),
    }).inserted_id


@pytest.fixture
def world(db):
    """A small, realistic tenant layout for route tests.

    * admin            — app admin
    * dentist          — owns clinic_a with patient_a (+ treatment, appointment)
    * staff            — linked to ``dentist`` via an active membership
    * outsider         — another dentist owning clinic_b / patient_b; must
                         never see clinic_a's data (and vice versa)

    Patient names are unique marker strings so tests can assert a page did (or
    did NOT) render that patient's data.
    """
    w = SimpleNamespace()
    w.admin = _user(db, "Admin User", "admin@dental.com", "admin")
    w.dentist = _user(db, "Dentist A", "dentist.a@dental.com", "dentist")
    w.staff = _user(db, "Staff S", "staff.s@dental.com", "staff")
    w.outsider = _user(db, "Dentist B", "dentist.b@dental.com", "dentist")

    w.clinic_a = _clinic(db, w.dentist, "Clinic Alpha")
    w.clinic_b = _clinic(db, w.outsider, "Clinic Bravo")
    w.patient_a = _patient(db, w.clinic_a, "Alicemarker", "Alpha")
    w.patient_b = _patient(db, w.clinic_b, "Bobmarker", "Bravo")

    db.memberships.insert_one({
        "user_id": w.staff, "dentist_id": w.dentist, "role": "staff",
        "is_active": True, "created_at": utcnow(),
    })
    w.treatment_a = db.treatment_records.insert_one({
        "patient_id": w.patient_a, "clinic_id": w.clinic_a,
        "date": "2026-09-01", "procedure": "Oral prophylaxis", "description": "",
        "dentist": "Dentist A", "amount_charged": 1500.0, "amount_paid": 500.0,
        "balance": 1000.0, "currency": "PHP", "status": "completed",
        "price_confirmed": True, "created_by": w.dentist,
        "created_at": utcnow(), "updated_at": utcnow(),
    }).inserted_id
    w.appointment_a = db.appointments.insert_one({
        "clinic_id": w.clinic_a, "patient_id": w.patient_a,
        "patient_name": "Alicemarker Alpha", "date": "2099-01-15", "time": "10:00",
        "duration": 30, "status": "scheduled", "is_active": True,
        "created_by": w.dentist, "created_at": utcnow(),
    }).inserted_id
    return w


@pytest.fixture
def as_user(real_client, world, db):
    """Log the real client in as one of the ``world`` users (or log out with None)."""
    def _as(who):
        with real_client.session_transaction() as sess:
            sess.clear()
            if who is None:
                return None
            user_id = getattr(world, who)
            user = db.users.find_one({"_id": ObjectId(user_id)})
            sess["user_id"] = user_id
            sess["user_email"] = user["email"]
            sess["user_role"] = user["role"]
            sess["user_name"] = user["name"]
            sess["last_activity"] = int(time.time())
        return user_id
    return _as
