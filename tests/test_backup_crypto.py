"""scripts/backup_crypto.py: public-key encryption of backup archives."""
import importlib.util
import pathlib

import pytest
from cryptography.exceptions import InvalidTag

_path = pathlib.Path(__file__).resolve().parent.parent / "scripts" / "backup_crypto.py"
_spec = importlib.util.spec_from_file_location("backup_crypto", _path)
bc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bc)

PLAIN = b"PK\x03\x04 fake zip with patient data " * 1000


@pytest.fixture(scope="module")
def keys(tmp_path_factory):
    d = tmp_path_factory.mktemp("keys")
    bc.generate_keypair(d / "pub.pem", d / "priv.pem")
    return d / "pub.pem", d / "priv.pem"


def test_round_trip_and_plaintext_removed(tmp_path, keys):
    pub, priv = keys
    src = tmp_path / "b.zip"
    src.write_bytes(PLAIN)
    enc = bc.encrypt_file(src, pub)
    assert not src.exists() and enc.name == "b.zip.enc"
    assert b"patient data" not in enc.read_bytes()            # actually encrypted
    assert bc.decrypt_file(enc, priv, tmp_path / "out.zip").read_bytes() == PLAIN


def test_each_file_gets_a_fresh_key_and_nonce(keys):
    pub, _ = keys
    assert bc.encrypt_bytes(PLAIN, pub.read_bytes()) != bc.encrypt_bytes(PLAIN, pub.read_bytes())


def test_tampering_is_detected(keys):
    pub, priv = keys
    blob = bytearray(bc.encrypt_bytes(PLAIN, pub.read_bytes()))
    blob[-20] ^= 0x01
    with pytest.raises(InvalidTag):
        bc.decrypt_bytes(bytes(blob), priv.read_bytes())


def test_a_different_private_key_cannot_decrypt(tmp_path, keys):
    pub, _ = keys
    bc.generate_keypair(tmp_path / "p2.pem", tmp_path / "k2.pem")
    blob = bc.encrypt_bytes(PLAIN, pub.read_bytes())
    with pytest.raises(ValueError):
        bc.decrypt_bytes(blob, (tmp_path / "k2.pem").read_bytes())


def test_generate_never_overwrites_an_existing_private_key(tmp_path, keys):
    (tmp_path / "priv.pem").write_text("existing")
    with pytest.raises(FileExistsError):
        bc.generate_keypair(tmp_path / "pub.pem", tmp_path / "priv.pem")
    assert (tmp_path / "priv.pem").read_text() == "existing"


def test_non_backup_file_is_rejected(keys):
    with pytest.raises(ValueError, match="not a MyDentalPortal"):
        bc.decrypt_bytes(b"random bytes", keys[1].read_bytes())
