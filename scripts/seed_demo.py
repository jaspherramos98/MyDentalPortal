r"""Seed the DEMO database with a realistic-looking clinic, patients, treatments
and appointments so the portfolio site (AWS EB) doesn't look empty.

SAFE-GUARDS:
  * Refuses to run unless the target database name contains "demo" — so it can
    never accidentally write fake records into the real `dental_portal` data.
  * Idempotent: every document it creates is tagged {'seed_tag': 'demo'} and
    re-running first deletes anything with that tag, then re-inserts. Real,
    hand-entered records (no tag) are never touched.

Usage:
    MONGO_URI="mongodb+srv://.../dental_portal_demo?..." python scripts/seed_demo.py
"""

import os
import random
import sys
from datetime import datetime, timedelta

from pymongo import MongoClient
from werkzeug.security import generate_password_hash

SEED_TAG = 'demo'
random.seed(42)  # reproducible

FIRST_NAMES = [
    'Maria', 'Jose', 'Juan', 'Ana', 'Antonio', 'Rosario', 'Andres', 'Carmen',
    'Ramon', 'Luz', 'Eduardo', 'Teresita', 'Manuel', 'Corazon', 'Ricardo',
    'Lourdes', 'Roberto', 'Elena', 'Danilo', 'Cristina', 'Kevin', 'Bianca',
    'Angelo', 'Patricia', 'Mark', 'Jasmine', 'Paolo', 'Grace',
]
LAST_NAMES = [
    'Santos', 'Reyes', 'Cruz', 'Bautista', 'Ocampo', 'Garcia', 'Mendoza',
    'Torres', 'Flores', 'Ramos', 'Aquino', 'Castillo', 'Villanueva',
    'Del Rosario', 'Gonzales', 'Navarro', 'Domingo', 'Salazar',
]
OCCUPATIONS = ['Teacher', 'Nurse', 'Engineer', 'Student', 'Driver', 'Vendor',
               'Accountant', 'OFW', 'Call Center Agent', 'Government Employee']
BARANGAYS = ['Hulo', 'Paco', 'Catanghalan', 'Lawa', 'Salambao', 'San Pascual',
             'Tawiran', 'Binuangan', 'Pag-asa', 'Poblacion']

# (procedure, min_price, max_price) in PHP
PROCEDURES = [
    ('Consultation', 300, 600),
    ('Oral Prophylaxis (Cleaning)', 800, 1500),
    ('Composite Filling', 1000, 2500),
    ('Tooth Extraction', 1200, 3000),
    ('Root Canal Treatment', 8000, 15000),
    ('Dental Crown', 9000, 20000),
    ('Teeth Whitening', 7000, 9000),
    ('Braces Adjustment', 1200, 1800),
    ('Complete Denture', 6000, 15000),
    ('Wisdom Tooth Surgery', 5000, 12000),
]
APPT_TYPES = ['checkup', 'cleaning', 'extraction', 'consultation', 'followup']


def _money(lo, hi):
    return float(random.randint(lo, hi) // 50 * 50)  # round to nearest 50


def main():
    uri = os.environ.get('MONGO_URI')
    if not uri:
        print('ERROR: MONGO_URI not set.')
        return 2

    client = MongoClient(uri, serverSelectionTimeoutMS=10000)
    db = client.get_default_database()
    if db is None:
        print('ERROR: no database name in MONGO_URI.')
        return 2

    if 'demo' not in db.name.lower():
        print(f"REFUSING: database '{db.name}' does not look like a demo DB. "
              "This script only seeds a *demo* database to protect real data.")
        return 3

    print(f'Seeding demo data into database: {db.name}')

    # ── ensure the admin user exists (owner of the demo clinics) ──
    admin = db.users.find_one({'email': 'admin@dental.com'})
    if not admin:
        admin_id = db.users.insert_one({
            'name': 'Admin User', 'email': 'admin@dental.com',
            'password': generate_password_hash('admin123'),
            'license_number': 'ADMIN001', 'specialty': 'General Dentistry',
            'role': 'admin', 'status': 'approved',
            'created_at': datetime.utcnow(), 'updated_at': datetime.utcnow(),
            'is_active': True,
        }).inserted_id
        print('  created admin@dental.com / admin123')
    else:
        admin_id = admin['_id']
    owner_id = str(admin_id)  # clinics store owner_id as the session string id

    # ── wipe any previous demo-tagged docs (idempotent) ──
    for coll in ('clinics', 'patients', 'treatment_records', 'appointments'):
        deleted = db[coll].delete_many({'seed_tag': SEED_TAG}).deleted_count
        if deleted:
            print(f'  cleared {deleted} previous demo {coll}')

    now = datetime.utcnow()

    # ── clinics ──
    clinics = [
        {'name': 'JRAMOS Dental Hub — Obando', 'address': 'Hulo, Obando, Bulacan',
         'phone': '0917-555-0100', 'email': 'obando@jramosdental.ph',
         'operating_hours': 'Mon-Sat 9:00 AM - 6:00 PM'},
        {'name': 'JRAMOS Dental — Valenzuela Branch', 'address': 'Malanday, Valenzuela City',
         'phone': '0917-555-0200', 'email': 'valenzuela@jramosdental.ph',
         'operating_hours': 'Mon-Fri 10:00 AM - 7:00 PM'},
    ]
    clinic_ids = []
    for c in clinics:
        c.update({'currency': 'PHP', 'owner_id': owner_id, 'is_active': True,
                  'seed_tag': SEED_TAG, 'created_at': now, 'updated_at': now})
        clinic_ids.append(db.clinics.insert_one(c).inserted_id)
    print(f'  inserted {len(clinic_ids)} clinics')

    # ── patients (spread created_at over the last ~12 months) ──
    patient_ids = []
    n_patients = 18
    for i in range(n_patients):
        fn, ln = random.choice(FIRST_NAMES), random.choice(LAST_NAMES)
        gender = random.choice(['Male', 'Female'])
        age = random.randint(8, 70)
        birth_year = now.year - age
        created = now - timedelta(days=random.randint(0, 360))
        clinic_id = random.choice(clinic_ids)
        patient = {
            'clinic_id': clinic_id,
            'personal_info': {
                'first_name': fn, 'last_name': ln, 'middle_name': random.choice(LAST_NAMES),
                'nickname': fn[:3], 'gender': gender,
                'birthday': f'{birth_year}-{random.randint(1,12):02d}-{random.randint(1,28):02d}',
                'age': str(age), 'religion': 'Roman Catholic', 'nationality': 'Filipino',
                'occupation': random.choice(OCCUPATIONS),
            },
            'contact_info': {
                'home_address': f'{random.randint(1,999)} {random.choice(BARANGAYS)} St., Bulacan',
                'landline': '', 'cell_phone': f'09{random.randint(10**8, 10**9 - 1)}',
                'office_number': '', 'email': f'{fn.lower()}.{ln.lower().replace(" ", "")}@example.com',
            },
            'emergency_contact': {'name': f'{random.choice(FIRST_NAMES)} {ln}',
                                  'relationship': random.choice(['Spouse', 'Parent', 'Sibling']),
                                  'phone': f'09{random.randint(10**8, 10**9 - 1)}'},
            'insurance_info': {'dental_insurance': random.choice(['', '', 'Maxicare', 'Intellicare'])},
            'minor_info': {'guardian_name': '', 'guardian_occupation': ''},
            'referral_info': {'referred_by': random.choice(['', 'Walk-in', 'Facebook', 'Friend']),
                              'consultation_reason': random.choice(
                                  ['Toothache', 'Routine cleaning', 'Check-up', 'Braces inquiry'])},
            'dental_history': {'previous_dentist': '', 'last_visit': ''},
            'medical_history': {
                'physician_name': '', 'physician_specialty': '', 'physician_address': '',
                'current_medications': '', 'blood_type': random.choice(['O+', 'A+', 'B+', 'AB+']),
                'blood_pressure': '', 'bleeding_time': '',
                'allergies': {'local_anesthesia': False, 'penicillin': False, 'sulfa_drugs': False,
                              'aspirin': False, 'latex': False, 'other': ''},
                'women_health': {'pregnant': 'no', 'nursing': 'no', 'birth_control': 'no'},
                'conditions': {k: False for k in (
                    'high_blood_pressure', 'heart_disease', 'diabetes', 'asthma', 'cancer_tumors',
                    'heart_murmur', 'epilepsy_convulsions', 'hepatitis_liver', 'kidney_disease',
                    'arthritis_rheumatism', 'thyroid_problem', 'bleeding_problems')},
            },
            'created_by': owner_id, 'created_at': created, 'updated_at': created,
            'is_active': True, 'seed_tag': SEED_TAG,
            '_clinic_id_ref': clinic_id,  # convenience for treatment seeding below
        }
        patient_ids.append((db.patients.insert_one(patient).inserted_id, clinic_id, f'{fn} {ln}'))
    print(f'  inserted {len(patient_ids)} patients')

    # ── treatments (1-5 per patient, dated across the last year) ──
    t_count = 0
    for pid, clinic_id, _name in patient_ids:
        for _ in range(random.randint(1, 5)):
            proc, lo, hi = random.choice(PROCEDURES)
            charged = _money(lo, hi)
            # ~30% leave an outstanding balance; rest fully paid
            if random.random() < 0.3:
                paid = _money(0, int(charged))
            else:
                paid = charged
            d = now - timedelta(days=random.randint(0, 360))
            db.treatment_records.insert_one({
                'patient_id': pid, 'clinic_id': clinic_id,
                'date': d.strftime('%Y-%m-%d'),
                'tooth_numbers': [str(random.choice([11, 12, 16, 21, 26, 36, 46]))],
                'procedure': proc, 'description': '', 'dentist': 'Dr. J. Ramos',
                'amount_charged': charged, 'amount_paid': float(paid),
                'balance': float(charged - paid), 'currency': 'PHP',
                'status': 'completed', 'notes': '', 'next_appointment': '',
                'created_by': owner_id, 'created_at': d, 'updated_at': d,
                'seed_tag': SEED_TAG,
            })
            t_count += 1
    print(f'  inserted {t_count} treatment records')

    # ── appointments (upcoming + a few recent past) ──
    a_count = 0
    for pid, clinic_id, name in random.sample(patient_ids, k=min(12, len(patient_ids))):
        offset = random.randint(-10, 14)  # past few days .. next 2 weeks
        d = now + timedelta(days=offset)
        db.appointments.insert_one({
            'clinic_id': clinic_id, 'patient_id': pid, 'patient_name': name,
            'date': d.strftime('%Y-%m-%d'),
            'time': f'{random.randint(9, 16):02d}:{random.choice(["00", "30"])}',
            'duration': random.choice([30, 30, 60]),
            'type': random.choice(APPT_TYPES), 'priority': 'normal', 'notes': '',
            'status': 'scheduled', 'created_by': owner_id,
            'created_at': now, 'updated_at': now, 'is_active': True, 'seed_tag': SEED_TAG,
        })
        a_count += 1
    print(f'  inserted {a_count} appointments')

    # tidy the convenience ref off patient docs
    db.patients.update_many({'seed_tag': SEED_TAG}, {'$unset': {'_clinic_id_ref': ''}})

    print('Done. Demo data seeded successfully.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
