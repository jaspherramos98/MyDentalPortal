"""The application factory: building an app must not touch the database, and
init_database() must be safe to run on every boot."""
from config import DevelopmentConfig, ProductionConfig
from factory import create_app, init_database


def test_create_app_has_no_database_side_effects(db):
    create_app(DevelopmentConfig, overrides={"TESTING": True}, init_mongo=False)
    assert db.list_collection_names() == []


def test_overrides_win_over_config_class(db):
    app = create_app(DevelopmentConfig, overrides={"IDLE_TIMEOUT_SECONDS": 5}, init_mongo=False)
    assert app.config["IDLE_TIMEOUT_SECONDS"] == 5


def test_production_refuses_the_dev_secret_key(db):
    import pytest
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        create_app(ProductionConfig,
                   overrides={"SECRET_KEY": "dev-fallback-key-change-in-production"},
                   init_mongo=False)


def test_production_forces_secure_cookie(db):
    app = create_app(ProductionConfig, overrides={"SECRET_KEY": "x" * 32}, init_mongo=False)
    assert app.config["SESSION_COOKIE_SECURE"] is True


def test_init_database_seeds_admin_once(real_app, db):
    with real_app.app_context():
        init_database()
        init_database()
    admins = list(db.users.find({"email": "admin@dental.com"}))
    assert len(admins) == 1 and admins[0]["role"] == "admin"
    assert admins[0]["password"] != "admin123"          # stored hashed


def test_init_database_skips_seed_when_users_exist(real_app, db):
    db.users.insert_one({"email": "someone@dental.com"})
    with real_app.app_context():
        init_database()
    assert db.users.find_one({"email": "admin@dental.com"}) is None


def test_init_database_creates_submission_id_index(real_app, db):
    with real_app.app_context():
        init_database()
    index = db.patients.index_information()["submission_id_1"]
    assert index["unique"] is True


def test_pwa_icons_are_real_pngs():
    """Icons are served (and declared in the manifest) as image/png. JPEG bytes
    under a .png name slipped in once (2026-09-26) — browsers can reject
    install icons whose content doesn't match their declared type."""
    import glob
    for path in glob.glob("static/icons/*.png"):
        with open(path, "rb") as fh:
            assert fh.read(8) == b"\x89PNG\r\n\x1a\n", path
