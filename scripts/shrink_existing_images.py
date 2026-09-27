r"""One-off backfill: shrink images uploaded before upload-time shrinking existed.

Applies the SAME rules as new uploads (blueprints/utils/images.py): profile
photos to 800px, prescription images + image attachments to 2000px, metadata
(incl. GPS) dropped, format unchanged. Prints counts and sizes only.

SAFETY
  * Dry run by default — reports projected savings, writes nothing.
  * --apply performs the rewrite; against a prod-looking DB it also needs
    --allow-prod. TAKE A BACKUP FIRST (scripts/backup_data.py).
  * Idempotent: images already within the size limit and carrying no metadata
    are skipped, so a re-run never re-compresses (no generation loss).
  * Per image: store the new blob -> repoint the record (only if it still
    references the old blob) -> delete the old blob. An interruption leaves at
    worst an orphaned blob, never a record pointing at nothing.

Usage:
    python scripts/shrink_existing_images.py [env-file] [database] [--apply] [--allow-prod]
    (defaults: .env.atlas-admin, dental_portal_prod)
"""
import io
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gridfs import GridFS  # noqa: E402
from PIL import Image  # noqa: E402
from pymongo import MongoClient  # noqa: E402

from blueprints.utils.images import (  # noqa: E402
    DOCUMENT_MAX_SIDE, PHOTO_MAX_SIDE, shrink_image,
)

MB = 1024 * 1024
IMAGE_EXTS = {'jpg', 'jpeg', 'png', 'webp'}

# (collection, blob-reference field, extension field or None, max side, label)
TARGETS = [
    ('patients', 'photo_file_id', 'photo_ext', PHOTO_MAX_SIDE, 'profile photos'),
    ('prescriptions', 'image_file_id', 'image_name', DOCUMENT_MAX_SIDE, 'prescription images'),
    ('patient_files', 'file_id', 'ext', DOCUMENT_MAX_SIDE, 'image attachments'),
]


def _ext_of(value):
    value = (value or '').lower()
    return value.rsplit('.', 1)[-1] if '.' in value else value


def _needs_shrink(data, max_side):
    """True unless the image is already within the limit and metadata-free."""
    try:
        with Image.open(io.BytesIO(data)) as img:
            return max(img.size) > max_side or len(img.getexif()) > 0 or bool(img.info.get('exif'))
    except Exception:
        return False                      # undecodable: leave it alone


def shrink_all(db, apply=False):
    """Shrink every referenced image. Returns {label: stats}."""
    fs = GridFS(db)
    report = {}
    for coll, field, ext_field, max_side, label in TARGETS:
        stats = {'seen': 0, 'shrunk': 0, 'skipped': 0, 'before': 0, 'after': 0}
        for doc in db[coll].find({field: {'$ne': None}}, {field: 1, ext_field: 1}):
            ext = _ext_of(doc.get(ext_field))
            if ext not in IMAGE_EXTS:
                continue
            old_id = doc[field]
            try:
                blob = fs.get(old_id)
            except Exception:
                continue                  # dangling reference: not ours to fix here
            data = blob.read()
            stats['seen'] += 1
            if not _needs_shrink(data, max_side):
                stats['skipped'] += 1
                continue
            new = shrink_image(data, ext, max_side)
            if len(new) >= len(data):
                stats['skipped'] += 1
                continue
            stats['shrunk'] += 1
            stats['before'] += len(data)
            stats['after'] += len(new)
            if not apply:
                continue
            new_id = fs.put(new, filename=blob.filename, contentType=blob.content_type)
            update = {'$set': {field: new_id}}
            if coll == 'patient_files':
                update['$set']['size'] = len(new)
            result = db[coll].update_one({'_id': doc['_id'], field: old_id}, update)
            if result.modified_count == 1:
                fs.delete(old_id)
            else:
                fs.delete(new_id)         # record changed meanwhile: keep the original
                stats['shrunk'] -= 1
        report[label] = stats
    return report


def _load_uri(env_path):
    with open(env_path, 'r', encoding='utf-8') as fh:
        for line in fh:
            if line.strip().startswith('MONGO_URI='):
                return line.strip().split('=', 1)[1].strip()
    raise SystemExit(f'No MONGO_URI in {env_path}')


def main(argv):
    flags = {a for a in argv if a.startswith('--')}
    args = [a for a in argv if not a.startswith('--')]
    env_path = args[0] if args else '.env.atlas-admin'
    db_name = args[1] if len(args) > 1 else 'dental_portal_prod'
    apply = '--apply' in flags
    if apply and 'prod' in db_name.lower() and '--allow-prod' not in flags:
        raise SystemExit('REFUSING: --apply on a prod database also needs --allow-prod '
                         '(take a backup first: scripts/backup_data.py).')
    uri = re.sub(r'(mongodb(?:\+srv)?://[^/]+)/[^?]*', r'\1/', _load_uri(env_path))
    db = MongoClient(uri, serverSelectionTimeoutMS=15000)[db_name]
    print(f"{'APPLYING' if apply else 'DRY RUN (no writes)'} on {db_name}")
    total_before = total_after = 0
    for label, s in shrink_all(db, apply=apply).items():
        total_before += s['before']
        total_after += s['after']
        print(f"  {label:<20} seen {s['seen']:>3}  shrink {s['shrunk']:>3}  skip {s['skipped']:>3}  "
              f"{s['before'] / MB:7.2f} MB -> {s['after'] / MB:6.2f} MB")
    print(f"  TOTAL {'saved' if apply else 'would save'}: "
          f"{(total_before - total_after) / MB:.2f} MB")


if __name__ == '__main__':
    main(sys.argv[1:])
