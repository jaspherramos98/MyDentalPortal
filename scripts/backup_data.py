r"""Full, restorable backup of a MyDentalPortal MongoDB database.

READ-ONLY: this only reads from the database, so it is safe to run against the
live production database at any time without interfering with the running app.

What it saves (into a timestamped folder, then zips it):
  * Every collection -> <collection>.json in MongoDB Extended JSON (canonical),
    which preserves ObjectIds, dates and binary so it round-trips exactly.
    This INCLUDES the GridFS collections (fs.files / fs.chunks), so patient
    photos, uploaded documents and prescriptions are fully captured and the
    backup is restorable with mongoimport / a pymongo restore.
  * A human-friendly copy of every GridFS file extracted into files/, so you
    can open them directly without restoring anything.
  * manifest.json with per-collection counts and metadata.

Restore later with either:
  * mongoimport --uri "<uri>" --collection <name> --file <name>.json, or
  * a small pymongo loop using bson.json_util.loads + insert_many.

⚠️  Backups contain PHI. Store them securely (encrypted), keep a copy OFF the
    free tier, and never commit them (backups/ is gitignored).

Usage:
    # database is taken from MONGO_URI (its path), or pass a URI as arg 1
    MONGO_URI="mongodb+srv://.../dental_portal?..." python scripts/backup_data.py
    python scripts/backup_data.py "mongodb+srv://.../dental_portal?..."

    # via Docker (mount a host folder so the zip lands on your machine):
    docker run --rm -e MONGO_URI="<uri>" -v "%cd%/backups:/app/backups" \
        mydentalportal python scripts/backup_data.py
"""

import os
import sys
import shutil
from datetime import datetime, timezone

from bson import json_util
from gridfs import GridFS
from pymongo import MongoClient
from werkzeug.utils import secure_filename

BACKUP_ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'backups')


def main():
    uri = sys.argv[1] if len(sys.argv) > 1 else os.environ.get('MONGO_URI')
    if not uri:
        print('ERROR: pass a MongoDB URI as the first argument or set MONGO_URI.')
        return 2

    client = MongoClient(uri, serverSelectionTimeoutMS=15000)
    db = client.get_default_database()
    if db is None:
        print('ERROR: the URI has no default database (no /dbname in the path).')
        return 2

    # ping first so we fail fast with a clear message
    client.admin.command('ping')

    stamp = datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')
    name = f'{db.name}-{stamp}'
    out_dir = os.path.join(BACKUP_ROOT, name)
    files_dir = os.path.join(out_dir, 'files')
    os.makedirs(files_dir, exist_ok=True)

    print(f'Backing up database "{db.name}" -> {out_dir}')
    manifest = {
        'database': db.name,
        'created_utc': stamp,
        'collections': {},
        'gridfs_files_extracted': 0,
    }

    # ── dump every collection as Extended JSON (fully restorable) ──
    for coll_name in sorted(db.list_collection_names()):
        docs = list(db[coll_name].find({}))
        path = os.path.join(out_dir, f'{coll_name}.json')
        with open(path, 'w', encoding='utf-8') as fh:
            fh.write(json_util.dumps(docs, indent=2))
        manifest['collections'][coll_name] = len(docs)
        print(f'  {coll_name}: {len(docs)} documents')

    # ── extract GridFS files for easy viewing (default "fs" bucket) ──
    if 'fs.files' in manifest['collections']:
        fs = GridFS(db)
        extracted = 0
        for gridout in fs.find():
            safe = secure_filename(gridout.filename or 'file') or 'file'
            dest = os.path.join(files_dir, f'{gridout._id}_{safe}')
            with open(dest, 'wb') as fh:
                fh.write(gridout.read())
            extracted += 1
        manifest['gridfs_files_extracted'] = extracted
        print(f'  extracted {extracted} GridFS file(s) -> files/')

    with open(os.path.join(out_dir, 'manifest.json'), 'w', encoding='utf-8') as fh:
        fh.write(json_util.dumps(manifest, indent=2))

    # ── zip it up ──
    zip_base = os.path.join(BACKUP_ROOT, name)
    archive = shutil.make_archive(zip_base, 'zip', out_dir)
    # remove the unzipped folder, keep only the .zip
    shutil.rmtree(out_dir, ignore_errors=True)

    size_mb = os.path.getsize(archive) / (1024 * 1024)
    print(f'\nDone. Backup written to:\n  {archive}  ({size_mb:.2f} MB)')
    print('Keep this somewhere safe and OFF the free tier. It contains PHI.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
