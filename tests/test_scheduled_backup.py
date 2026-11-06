"""scripts/scheduled_backup.py: verification + retention (no database needed)."""
import importlib.util
import json
import pathlib
import zipfile

import pytest
from bson import json_util

_path = pathlib.Path(__file__).resolve().parent.parent / "scripts" / "scheduled_backup.py"
_spec = importlib.util.spec_from_file_location("scheduled_backup", _path)
sb = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sb)


def _zip(path, manifest, members):
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("manifest.json", json.dumps(manifest))
        for name, data in members.items():
            zf.writestr(name, data)
    return path


def _good(tmp_path):
    return _zip(tmp_path / "b.zip",
                {"collections": {"patients": 2, "users": 1}, "gridfs_files_extracted": 1},
                {"patients.json": json_util.dumps([{"a": 1}, {"a": 2}]),
                 "users.json": json_util.dumps([{"u": 1}]),
                 "files/abc_photo.jpg": b"\xff\xd8\xff"})


def test_verify_accepts_a_consistent_backup(tmp_path):
    assert sb.verify(_good(tmp_path))["collections"]["patients"] == 2


def test_verify_rejects_count_mismatch(tmp_path):
    z = _zip(tmp_path / "b.zip", {"collections": {"patients": 3}, "gridfs_files_extracted": 0},
             {"patients.json": json_util.dumps([{"a": 1}])})
    with pytest.raises(ValueError, match="patients"):
        sb.verify(z)


def test_verify_rejects_missing_gridfs_files(tmp_path):
    z = _zip(tmp_path / "b.zip", {"collections": {}, "gridfs_files_extracted": 2},
             {"files/one.jpg": b"x"})
    with pytest.raises(ValueError, match="GridFS"):
        sb.verify(z)


def test_prune_keeps_newest_and_ignores_other_files(tmp_path):
    for day in range(1, 18):
        (tmp_path / f"dental_portal_prod-202609{day:02d}-030000.zip.enc").write_bytes(b"z")
    (tmp_path / "manual-keep-me.zip").write_bytes(b"z")
    (tmp_path / "backup.log").write_text("log")
    deleted = sb.prune(tmp_path, keep=14)
    assert deleted == [f"dental_portal_prod-202609{d:02d}-030000.zip.enc" for d in (1, 2, 3)]
    left = sorted(p.name for p in tmp_path.glob("dental_portal_prod-*.zip.enc"))
    assert len(left) == 14 and left[0].endswith("0904-030000.zip.enc")
    assert (tmp_path / "manual-keep-me.zip").exists() and (tmp_path / "backup.log").exists()


def test_failure_log_line_never_contains_the_uri(tmp_path, monkeypatch):
    monkeypatch.setattr(sb, "DEST", tmp_path)
    monkeypatch.setattr(sb, "LOG", tmp_path / "backup.log")
    (tmp_path / "pub.pem").write_text("x")
    monkeypatch.setattr(sb, "PUBLIC_KEY", tmp_path / "pub.pem")
    secret = "mongodb+srv://user:SuperSecret@cluster.example.net/dental_portal_prod"
    monkeypatch.setattr(sb, "load_uri", lambda: (secret, ".env.backup"))

    def boom(uri, root):
        raise RuntimeError(f"cannot connect to {uri}")
    monkeypatch.setattr(sb, "backup", boom)
    assert sb.main() == 1
    text = (tmp_path / "backup.log").read_text()
    assert "FAIL  RuntimeError" in text and "SuperSecret" not in text


def test_job_refuses_to_run_without_public_key(tmp_path, monkeypatch):
    """No key -> no backup at all (never a plaintext one)."""
    monkeypatch.setattr(sb, "DEST", tmp_path)
    monkeypatch.setattr(sb, "LOG", tmp_path / "backup.log")
    monkeypatch.setattr(sb, "PUBLIC_KEY", tmp_path / "missing.pem")
    called = []
    monkeypatch.setattr(sb, "backup", lambda *a, **k: called.append(1))
    assert sb.main() == 1 and called == []
    assert "FAIL  FileNotFoundError" in (tmp_path / "backup.log").read_text()
    assert list(tmp_path.glob("*.zip*")) == []
