# File: MyDentalPortal/app/routes/main.py
# Dashboard and landing page routes

from flask import (
    Blueprint, render_template, session,
    redirect, url_for, request, flash,
)
from werkzeug.security import generate_password_hash, check_password_hash
from bson.objectid import ObjectId
from datetime import datetime, timedelta

from extensions import mongo
from blueprints.utils import login_required
from blueprints.repositories import users as user_repo

main_bp = Blueprint('main', __name__)


@main_bp.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('main.dashboard'))
    return redirect(url_for('auth.login'))


@main_bp.route('/dashboard')
@login_required
def dashboard():
    try:
        user_id = session['user_id']

        user_clinics = list(
            mongo.db.clinics.find({'owner_id': user_id, 'is_active': True})
            .sort('name', 1)
        )
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
            from blueprints.repositories import patients as patient_repo
            recent_patients = list(
                mongo.db.patients.find({'clinic_id': {'$in': clinic_ids}, 'is_active': True})
                .sort('created_at', -1).limit(10)
            )
            for rp in recent_patients:
                patient_repo.ensure_nested(rp)
            stats['total_patients'] = mongo.db.patients.count_documents(
                {'clinic_id': {'$in': clinic_ids}, 'is_active': True}
            )

            today_str = datetime.now().strftime('%Y-%m-%d')
            today_appointments = list(
                mongo.db.appointments.find({
                    'clinic_id': {'$in': clinic_ids},
                    'date': today_str,
                    'is_active': True,
                    'status': {'$ne': 'cancelled'},
                }).sort('time', 1)
            )

            end_date = (datetime.now() + timedelta(days=7)).strftime('%Y-%m-%d')
            upcoming_appointments = list(
                mongo.db.appointments.find({
                    'clinic_id': {'$in': clinic_ids},
                    'date': {'$gte': today_str, '$lte': end_date},
                    'is_active': True,
                    'status': {'$ne': 'cancelled'},
                }).sort([('date', 1), ('time', 1)]).limit(10)
            )

            now = datetime.utcnow()
            month_start = datetime(now.year, now.month, 1)
            stats['patients_this_month'] = mongo.db.patients.count_documents({
                'clinic_id': {'$in': clinic_ids},
                'is_active': True,
                'created_at': {'$gte': month_start},
            })
            # "This Week" = the calendar week (Sunday–Saturday) containing today,
            # to match the Appointments week view. Dates are stored as
            # 'YYYY-MM-DD' strings, so lexicographic range comparison is valid.
            today_dt = datetime.now()
            days_since_sunday = (today_dt.weekday() + 1) % 7  # Mon=0..Sun=6 -> Sun=0
            week_start = today_dt - timedelta(days=days_since_sunday)
            week_end = week_start + timedelta(days=6)
            stats['appointments_this_week'] = mongo.db.appointments.count_documents({
                'clinic_id': {'$in': clinic_ids},
                'date': {
                    '$gte': week_start.strftime('%Y-%m-%d'),
                    '$lte': week_end.strftime('%Y-%m-%d'),
                },
                'is_active': True,
                'status': {'$ne': 'cancelled'},
            })
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
