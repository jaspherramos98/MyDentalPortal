"""scripts/seed_dev.py must never be able to write fake records into a deployed DB."""
import importlib.util
import pathlib

import pytest

_spec = importlib.util.spec_from_file_location(
    "seed_dev", pathlib.Path(__file__).resolve().parent.parent / "scripts" / "seed_dev.py")
seed_dev = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(seed_dev)


@pytest.mark.parametrize("uri", [
    "mongodb://localhost:27017/dental_portal",
    "mongodb://127.0.0.1/dental_portal_dev",
    "mongodb://user:pw@localhost:27017/dental_portal",
    "mongodb://[::1]:27017/dental_portal",
])
def test_local_uris_are_allowed(uri):
    assert seed_dev.local_only_reason(uri) is None


@pytest.mark.parametrize("uri", [
    "mongodb+srv://u:p@dental-portal-cluster.abcde.mongodb.net/dental_portal_prod",
    "mongodb+srv://u:p@dental-portal-cluster.abcde.mongodb.net/dental_portal_showcase",
    "mongodb://db.example.com:27017/dental_portal",
    "mongodb://localhost:27017,db.example.com:27017/dental_portal",
    "mongodb://localhost:27017/dental_portal_prod",
    "mongodb://localhost.evil.com:27017/dental_portal",
])
def test_remote_or_prod_uris_are_refused(uri):
    assert seed_dev.local_only_reason(uri) is not None
