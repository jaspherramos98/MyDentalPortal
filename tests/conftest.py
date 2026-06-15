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
import pytest
from bson.objectid import ObjectId
from flask import Flask, Blueprint

from extensions import mongo


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
    from blueprints.utils import login_required, admin_required

    @app.route("/_login_guarded")
    @login_required
    def _login_guarded():
        return "ok", 200

    @app.route("/_admin_guarded")
    @admin_required
    def _admin_guarded():
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
