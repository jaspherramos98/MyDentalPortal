r"""One-off backfill: link past appointments to the treatments done at them.

Before "Complete visit" existed, appointments were never marked done and had
no link to treatment_records. This links them where the match is EXACT and
UNAMBIGUOUS, so old visits show up correctly on the calendar and in the
visit-history list:

  * the appointment is active, status scheduled/completed, has a patient_id,
    and its date is before today (clinic time, Asia/Manila);
  * it is the ONLY such appointment for that clinic + patient + date;
  * there is at least one treatment for the same clinic + patient + date that
    is not linked to any appointment yet.

Then every such treatment gets ``appointment_id`` and a scheduled appointment
becomes ``completed`` (``completed_at`` = now, ``backfilled: True``).
Everything else is left alone and shows as "Not marked" (🟠) in the app:
two appointments on the same day (ambiguous), walk-ins booked by typed name
(no patient_id), cancelled/no-show visits, and visits with no treatment.

SAFETY
  * Dry run by default: prints counts only (never names or other PHI).
  * --apply writes; against a prod-looking DB it also needs --allow-prod.
    TAKE A VERIFIED BACKUP FIRST (scripts/backup_data.py).
  * Idempotent: linked appointments are skipped on the next run, and the
    treatment update only touches records that are still unlinked.

Usage:
    python scripts/backfill_visit_links.py [env-file] [database] [--apply] [--allow-prod]
    (defaults: .env.atlas-admin, dental_portal_prod)
"""
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone

from pymongo import MongoClient

CANDIDATE_STATUSES = ('scheduled', 'completed')


@dataclass
class Plan:
    links: list = field(default_factory=list)   # [{'appointment_id', 'treatment_ids', 'status'}]
    ambiguous: int = 0                           # same patient+day booked twice, treatments present
    without_treatment: int = 0                   # unambiguous, but nothing to link


def clinic_today():
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo('Asia/Manila')).strftime('%Y-%m-%d')
    except Exception:
        return datetime.now().strftime('%Y-%m-%d')


def looks_like_prod(db_name):
    return 'prod' in (db_name or '').lower()


def _key(doc):
    return (doc.get('clinic_id'), doc.get('patient_id'), doc.get('date'))


def plan_links(db, today=None):
    """Work out which links to make. Reads only."""
    today = today or clinic_today()
    appts = list(db.appointments.find({
        'is_active': True,
        'status': {'$in': list(CANDIDATE_STATUSES)},
        'patient_id': {'$exists': True, '$ne': None},
        'date': {'$lt': today},
    }, {'clinic_id': 1, 'patient_id': 1, 'date': 1, 'status': 1}))

    already_linked = set(db.treatment_records.distinct(
        'appointment_id', {'appointment_id': {'$exists': True, '$ne': None}}))

    unlinked = {}
    for t in db.treatment_records.find(
            {'$or': [{'appointment_id': {'$exists': False}}, {'appointment_id': None}]},
            {'clinic_id': 1, 'patient_id': 1, 'date': 1}):
        unlinked.setdefault(_key(t), []).append(t['_id'])

    by_key = {}
    for a in appts:
        by_key.setdefault(_key(a), []).append(a)

    plan = Plan()
    for key, group in by_key.items():
        treatment_ids = unlinked.get(key, [])
        if len(group) > 1:
            if treatment_ids:
                plan.ambiguous += 1
            continue
        appt = group[0]
        if appt['_id'] in already_linked:
            continue
        if not treatment_ids:
            plan.without_treatment += 1
            continue
        plan.links.append({'appointment_id': appt['_id'], 'treatment_ids': treatment_ids,
                           'status': appt.get('status')})
    plan.links.sort(key=lambda link: str(link['appointment_id']))
    return plan


def apply_links(db, links):
    """Write the planned links. Returns (treatments_linked, appointments_completed)."""
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    linked = completed = 0
    for link in links:
        res = db.treatment_records.update_many(
            {'_id': {'$in': link['treatment_ids']},
             '$or': [{'appointment_id': {'$exists': False}}, {'appointment_id': None}]},
            {'$set': {'appointment_id': link['appointment_id']}},
        )
        linked += res.modified_count
        res = db.appointments.update_one(
            {'_id': link['appointment_id'], 'status': 'scheduled'},
            {'$set': {'status': 'completed', 'completed_at': now,
                      'updated_at': now, 'backfilled': True}},
        )
        completed += res.modified_count
    return linked, completed


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
    if apply and looks_like_prod(db_name) and '--allow-prod' not in flags:
        raise SystemExit('REFUSING: --apply on a prod database also needs --allow-prod '
                         '(take a verified backup first: scripts/backup_data.py).')
    uri = re.sub(r'(mongodb(?:\+srv)?://[^/]+)/[^?]*', r'\1/', _load_uri(env_path))
    db = MongoClient(uri, serverSelectionTimeoutMS=15000)[db_name]

    plan = plan_links(db)
    n_treatments = sum(len(link['treatment_ids']) for link in plan.links)
    n_to_complete = sum(1 for link in plan.links if link['status'] == 'scheduled')
    print(f"{'APPLYING' if apply else 'DRY RUN (no writes)'} on {db_name}")
    print(f"  visits to link          {len(plan.links):>5}  ({n_treatments} treatments, "
          f"{n_to_complete} to mark completed)")
    print(f"  skipped: ambiguous      {plan.ambiguous:>5}  (same patient booked twice that day)")
    print(f"  skipped: no treatment   {plan.without_treatment:>5}  (stay 'Not marked')")
    if apply:
        linked, completed = apply_links(db, plan.links)
        print(f"  DONE: {linked} treatments linked, {completed} appointments marked completed")


if __name__ == '__main__':
    main(sys.argv[1:])
