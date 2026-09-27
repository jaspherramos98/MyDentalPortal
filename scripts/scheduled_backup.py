r"""Daily prod backup for the local machine (Atlas M0 has NO automated backups).

Run by Windows Task Scheduler (see CLAUDE.md "Recurring prod backups"), or by hand:
    venv\Scripts\python.exe scripts\scheduled_backup.py

Each run:
  1. reads the connection string from .env.backup (a READ-ONLY user — preferred)
     or, failing that, .env.atlas-admin; never prints it;
  2. backs up dental_portal_prod to backups/prod-daily/ (scripts/backup_data.py);
  3. VERIFIES the zip: archive integrity + every collection's document count and
     the GridFS file count match its manifest;
  4. ENCRYPTS it to .zip.enc with the backup PUBLIC key (.backup-public-key.pem;
     scripts/backup_crypto.py) and deletes the plaintext zip. No key -> the job
     refuses to run. Restoring needs the PRIVATE key, kept OFF this machine;
  5. keeps the newest KEEP backups in backups/prod-daily/ and deletes older ones
     (manual backups elsewhere in backups/ are never touched);
  6. appends one line to backups/prod-daily/backup.log — counts and sizes only,
     never data or credentials. Exit code 0 = OK, 1 = failed (Task Scheduler
     shows it as "Last Run Result").

backups/ is gitignored and holds PHI: keep this machine's disk encrypted.
"""
import json
import re
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from bson import json_util

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from backup_data import backup  # noqa: E402
from backup_crypto import encrypt_file  # noqa: E402

DB_NAME = "dental_portal_prod"
DEST = ROOT / "backups" / "prod-daily"
LOG = DEST / "backup.log"
KEEP = 14
ENV_FILES = (".env.backup", ".env.atlas-admin")     # read-only user first
# Public half of the backup keypair (not secret; gitignored as machine-specific).
# Without it the job REFUSES to run rather than write an unencrypted backup.
PUBLIC_KEY = ROOT / ".backup-public-key.pem"


def load_uri():
    """(uri, source file name) — URI pointed at DB_NAME. Raises if none found."""
    for name in ENV_FILES:
        path = ROOT / name
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("MONGO_URI="):
                uri = line.split("=", 1)[1].strip()
                return re.sub(r"(mongodb(?:\+srv)?://[^/]+)/[^?]*", rf"\1/{DB_NAME}", uri), name
    raise FileNotFoundError(f"no MONGO_URI in any of {ENV_FILES}")


def verify(archive):
    """Raise unless the zip is intact and matches its own manifest. Returns the manifest."""
    with zipfile.ZipFile(archive) as zf:
        bad = zf.testzip()
        if bad:
            raise ValueError(f"corrupt member in archive: {bad}")
        manifest = json.loads(zf.read("manifest.json"))
        for coll, expected in manifest["collections"].items():
            docs = json_util.loads(zf.read(f"{coll}.json"))
            if len(docs) != expected:
                raise ValueError(f"{coll}: {len(docs)} docs in file, manifest says {expected}")
        files = [n for n in zf.namelist() if n.startswith("files/") and not n.endswith("/")]
        if len(files) != manifest.get("gridfs_files_extracted", 0):
            raise ValueError("GridFS file count does not match manifest")
    return manifest


def prune(folder, keep=KEEP):
    """Delete all but the newest `keep` backup zips in `folder`. Returns deleted names."""
    zips = sorted(folder.glob(f"{DB_NAME}-*.zip.enc"))      # names sort by UTC stamp
    doomed = zips[:-keep] if len(zips) > keep else []
    for z in doomed:
        z.unlink()
    return [z.name for z in doomed]


def log(line):
    DEST.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    with open(LOG, "a", encoding="utf-8") as fh:
        fh.write(f"{stamp}  {line}\n")


def main():
    try:
        if not PUBLIC_KEY.exists():
            raise FileNotFoundError("backup public key missing")   # never write plaintext
        uri, source = load_uri()
        DEST.mkdir(parents=True, exist_ok=True)
        plain = Path(backup(uri, root=str(DEST)))
        manifest = verify(plain)                   # verify BEFORE encrypting
        archive = encrypt_file(plain, PUBLIC_KEY)  # writes .zip.enc, deletes the .zip
        pruned = prune(DEST)
        docs = sum(manifest["collections"].values())
        log(f"OK    {archive.name}  {archive.stat().st_size / 1_048_576:.2f} MB  "
            f"{docs} docs / {manifest.get('gridfs_files_extracted', 0)} files  "
            f"creds={source}  pruned={len(pruned)}")
        return 0
    except Exception as exc:                      # log the TYPE only: messages can carry URIs
        log(f"FAIL  {type(exc).__name__}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
