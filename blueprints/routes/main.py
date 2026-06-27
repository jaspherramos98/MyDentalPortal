# File: MyDentalPortal/app/routes/main.py
# Dashboard and landing page routes

from flask import (
    Blueprint, render_template, session,
    redirect, url_for, request, flash,
)
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta

from blueprints.utils import login_required, role_required, ROLE_DENTIST, is_admin
from blueprints.repositories import users as user_repo
from blueprints.repositories import clinics as clinic_repo
from blueprints.repositories import patients as patient_repo
from blueprints.repositories import appointments as appt_repo
from blueprints.repositories import audit_log as audit_repo

main_bp = Blueprint('main', __name__)

AUDIT_PAGE_SIZE = 50


@main_bp.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('main.dashboard'))
    return redirect(url_for('auth.login'))


@main_bp.route('/privacy')
def privacy():
    """Public privacy notice (RA 10173 right-to-be-informed). Static content;
    clinic-specific details (DPO name/contact) are placeholders to fill in."""
    return render_template('privacy.html')


@main_bp.route('/activity')
@role_required(ROLE_DENTIST)
def activity():
    """Audit-log viewer (nested scope): staff get 403 (role gate); a dentist sees
    their own clinics' activity (self + their staff); an app admin sees everything,
    grouped by owning dentist. Entries are PHI-free (see audit_log repo)."""
    page = max(1, request.args.get('page', 1, type=int))
    skip = (page - 1) * AUDIT_PAGE_SIZE
    admin = is_admin()

    if admin:
        entries = audit_repo.find_all(AUDIT_PAGE_SIZE, skip)
        total = audit_repo.count_all()
    else:
        dentist_id = session['user_id']
        entries = audit_repo.find_for_dentist(dentist_id, AUDIT_PAGE_SIZE, skip)
        total = audit_repo.count_for_dentist(dentist_id)

    # Resolve actor/dentist ids to display names (cached). Names of *users* (staff/
    # dentists), never patient PHI — the entries themselves carry no patient data.
    name_cache = {}

    def name_of(uid):
        if not uid:
            return '—'
        if uid not in name_cache:
            u = user_repo.get(uid)
            name_cache[uid] = (u.get('name') or u.get('email') or uid) if u else uid
        return name_cache[uid]

    for e in entries:
        e['actor_name'] = name_of(e.get('actor_user_id'))
        e['dentist_name'] = name_of(e.get('dentist_id'))

    # Admin view groups by owning dentist; dentist view is a flat list.
    grouped = None
    if admin:
        grouped = {}
        for e in entries:
            key = e.get('dentist_id') or '—'
            grouped.setdefault(key, {'dentist_name': e['dentist_name'], 'entries': []})
            grouped[key]['entries'].append(e)

    total_pages = max(1, (total + AUDIT_PAGE_SIZE - 1) // AUDIT_PAGE_SIZE)
    return render_template(
        'audit/activity.html',
        entries=entries, grouped=grouped, admin=admin,
        page=page, total_pages=total_pages, total=total,
    )


@main_bp.route('/dashboard')
@login_required
def dashboard():
    try:
        user_id = session['user_id']

        user_clinics = clinic_repo.owned_active_by_name(user_id)
        clinic_ids = [c['_id'] for c in user_clinics]

        recent_patients = []
        today_appointments = []
        upcoming_appointments = []
        stats = {
            'total_clinics': len(user_clinics),
            'total_patients': 0,
            'patients_this_month': 0,
            'appointments_this_week': 0,
            'today_appointments': 0,
            'upcoming_appointments': 0,
        }

        if clinic_ids:
            recent_patients = patient_repo.recent_in_clinics(clinic_ids, limit=10)
            for rp in recent_patients:
                patient_repo.ensure_nested(rp)
            stats['total_patients'] = patient_repo.count_active_in_clinics(clinic_ids)

            today_str = datetime.now().strftime('%Y-%m-%d')
            today_appointments = appt_repo.find_active_on_date(clinic_ids, today_str)

            end_date = (datetime.now() + timedelta(days=7)).strftime('%Y-%m-%d')
            upcoming_appointments = appt_repo.find_upcoming(
                clinic_ids, today_str, end_date, limit=10,
            )

            now = datetime.utcnow()
            month_start = datetime(now.year, now.month, 1)
            stats['patients_this_month'] = patient_repo.count_active_in_clinics(
                clinic_ids, created_since=month_start,
            )
            # "This Week" = the calendar week (Sunday–Saturday) containing today,
            # to match the Appointments week view. Dates are stored as
            # 'YYYY-MM-DD' strings, so lexicographic range comparison is valid.
            today_dt = datetime.now()
            days_since_sunday = (today_dt.weekday() + 1) % 7  # Mon=0..Sun=6 -> Sun=0
            week_start = today_dt - timedelta(days=days_since_sunday)
            week_end = week_start + timedelta(days=6)
            stats['appointments_this_week'] = appt_repo.count_active_in_range(
                clinic_ids,
                week_start.strftime('%Y-%m-%d'),
                week_end.strftime('%Y-%m-%d'),
            )
            stats['today_appointments'] = len(today_appointments)
            stats['upcoming_appointments'] = len(upcoming_appointments)

        return render_template(
            'dashboard/index.html',
            clinics=user_clinics,
            recent_patients=recent_patients,
            today_appointments=today_appointments,
            upcoming_appointments=upcoming_appointments,
            stats=stats,
        )

    except Exception as e:
        print(f"Dashboard error: {e}")
        empty = {
            'total_clinics': 0, 'total_patients': 0,
            'patients_this_month': 0, 'appointments_this_week': 0,
            'today_appointments': 0, 'upcoming_appointments': 0,
        }
        return render_template(
            'dashboard/index.html',
            clinics=[], recent_patients=[],
            today_appointments=[], upcoming_appointments=[],
            stats=empty,
        )


# ── SETTINGS ───────────────────────────────────────────────────────────────
@main_bp.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    """Account settings: view account info, update profile, change password."""
    user = user_repo.get(session['user_id'])
    if not user:
        session.clear()
        return redirect(url_for('auth.login'))

    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'profile':
            name = (request.form.get('name') or '').strip()
            specialty = (request.form.get('specialty') or '').strip()
            if not name:
                flash('Name cannot be empty', 'error')
            else:
                user_repo.update_set(user['_id'], {
                    'name': name,
                    'specialty': specialty,
                    'updated_at': datetime.utcnow(),
                })
                session['user_name'] = name
                flash('Profile updated successfully', 'success')
            return redirect(url_for('main.settings'))

        if action == 'password':
            current = request.form.get('current_password') or ''
            new = request.form.get('new_password') or ''
            confirm = request.form.get('confirm_password') or ''

            if not check_password_hash(user['password'], current):
                flash('Current password is incorrect', 'error')
            elif len(new) < 8:
                flash('New password must be at least 8 characters long', 'error')
            elif new != confirm:
                flash('New passwords do not match', 'error')
            else:
                user_repo.update_set(user['_id'], {
                    'password': generate_password_hash(new),
                    'updated_at': datetime.utcnow(),
                })
                flash('Password changed successfully', 'success')
            return redirect(url_for('main.settings'))

    return render_template('settings.html', user=user)
