r"""Restore a MyDentalPortal MongoDB database from a backup_data.py archive.

This is the other half of the backup/restore drill: backup_data.py proves a
backup exists; this proves it is *recoverable*. An untested backup doesn't count.

It reads a backup produced by scripts/backup_data.py (either the .zip or an
already-unzipped folder) and writes every collection back into a target
database. Because GridFS is just the fs.files / fs.chunks collections, restoring
those collections restores patient photos / documents / prescriptions too.

⚠️  WRITES to the target database. By default it REFUSES a prod-looking target
    (db name contains "prod") so a drill can't clobber real PHI; pass
    --allow-prod only for a genuine production recovery. Use --drop to replace
    existing collections (clean restore) instead of adding to them.

Usage:
    # Restore into a throwaway DB for a drill (target db is in the URI path):
    python scripts/restore_data.py backups/dental_portal_showcase-XXES.zip \
        --uri "mongodb+srv://.../dental_portal_restore_test?..." --drop --yes

    # Genuine production recovery (be sure!):
    python scripts/restore_data.py backups/dental_portal_prod-XXES.zip \
        --uri "mongodb+srv://.../dental_portal_prod?..." --drop --yes --allow-prod

Exit code 0 on success, non-zero on any error or verification mismatch.
"""

import argparse
import json
import os
import sys
import tempfile
import zipfile
import shutil

from bson import json_util
from pymongo import MongoClient


def _load_backup_dir(path):
    """Return (dir_path, cleanup_fn). Accepts a .zip or an unzipped folder."""
    if os.path.isdir(path):
        return path, (lambda: None)
    if zipfile.is_zipfile(path):
        tmp = tempfile.mkdtemp(prefix='restore-')
        with zipfile.ZipFile(path) as zf:
            zf.extractall(tmp)
        return tmp, (lambda: shutil.rmtree(tmp, ignore_errors=True))
    raise SystemExit(f'ERROR: {path} is neither a folder nor a .zip backup.')


def _restore(args):
    backup_dir, cleanup = _load_backup_dir(args.backup)
    try:
        client = MongoClient(args.uri, serverSelectionTimeoutMS=15000)
        db = client.get_default_database()
        if db is None:
            print('ERROR: the --uri has no default database (no /dbname in the path).')
            return 2
        client.admin.command('ping')

        # Safety: never write into a prod-looking DB unless explicitly allowed.
        if 'prod' in db.name.lower() and not args.allow_prod:
            print(f'REFUSING to restore into "{db.name}" (looks like production).')
            print('Pass --allow-prod ONLY for a genuine production recovery.')
            return 2

        # Read the manifest (per-collection expected counts) for verification.
        manifest_path = os.path.join(backup_dir, 'manifest.json')
        expected = {}
        if os.path.exists(manifest_path):
            with open(manifest_path, encoding='utf-8') as fh:
                expected = json.loads(fh.read()).get('collections', {})

        coll_files = sorted(
            f for f in os.listdir(backup_dir)
            if f.endswith('.json') and f != 'manifest.json'
        )
        if not coll_files:
            print(f'ERROR: no collection .json files found in {args.backup}.')
            return 2

        if not args.yes:
            print(f'About to restore {len(coll_files)} collection(s) into "{db.name}".')
            print('Re-run with --yes to proceed (non-interactive).')
            return 1

        print(f'Restoring into "{db.name}" (drop={args.drop})')
        restored = {}
        for fname in coll_files:
            coll_name = fname[:-len('.json')]
            with open(os.path.join(backup_dir, fname), encoding='utf-8') as fh:
                docs = json_util.loads(fh.read())
            coll = db[coll_name]
            if args.drop:
                coll.drop()
            if docs:
                coll.insert_many(docs, ordered=False)
            restored[coll_name] = coll.count_documents({})
            print(f'  {coll_name}: {restored[coll_name]} documents')

        # ── verify against the manifest counts ──
        ok = True
        if expected:
            print('\nVerification (restored vs. backup manifest):')
            for name, exp in sorted(expected.items()):
                got = restored.get(name, 0)
                mark = 'OK' if got == exp else 'MISMATCH'
                if got != exp:
                    ok = False
                print(f'  {name:<20} expected {exp:>6} | restored {got:>6}  {mark}')
        else:
            print('\nNo manifest.json in backup — skipped count verification.')

        if not ok:
            print('\nFAILED: at least one collection count does not match the backup.')
            return 1
        print('\nDone. Restore verified against the backup manifest.')
        return 0
    finally:
        cleanup()


def main():
    parser = argparse.ArgumentParser(description='Restore a MyDentalPortal backup.')
    parser.add_argument('backup', help='Path to the backup .zip or unzipped folder.')
    parser.add_argument('--uri', required=True,
                        help='Target MongoDB URI WITH a /dbname in the path.')
    parser.add_argument('--drop', action='store_true',
                        help='Drop each collection before restoring (clean restore).')
    parser.add_argument('--yes', action='store_true',
                        help='Proceed without the confirmation gate (non-interactive).')
    parser.add_argument('--allow-prod', action='store_true',
                        help='Permit a prod-looking target DB (genuine recovery only).')
    return _restore(parser.parse_args())


if __name__ == '__main__':
    sys.exit(main())
