# File: MyDentalPortal/app/routes/clinics.py
# Clinic management routes

from flask import (
    Blueprint, render_template, request, session,
    redirect, url_for, flash, jsonify,
)
from bson.objectid import ObjectId
from datetime import datetime
import traceback

from extensions import mongo
from blueprints.utils import login_required, role_required, ROLE_DENTIST

clinics_bp = Blueprint('clinics', __name__)


@clinics_bp.route('/clinics')
@login_required
def list_clinics():
    try:
        search_query = request.args.get('search', '')
        query = {'owner_id': session['user_id'], 'is_active': True}

        if search_query:
            query['$or'] = [
                {'name': {'$regex': search_query, '$options': 'i'}},
                {'address': {'$regex': search_query, '$options': 'i'}},
            ]

        clinics = list(mongo.db.clinics.find(query).sort('name', 1))

        # Attach patient count per clinic
        for clinic in clinics:
            clinic['patient_count'] = mongo.db.patients.count_documents({
                'clinic_id': clinic['_id'], 'is_active': True,
            })

        return render_template(
            'clinics/list.html',
            clinics=clinics,
            search_query=search_query,
        )
    except Exception as e:
        print(f"[ERROR] Clinics list: {e}")
        traceback.print_exc()
        flash('Error loading clinics', 'error')
        return render_template('clinics/list.html', clinics=[], search_query='')


@clinics_bp.route('/clinics/create', methods=['GET', 'POST'])
@role_required(ROLE_DENTIST)  # clinic management is dentist/admin only (staff can't)
def create_clinic():
    if request.method == 'POST':
        name = (request.form.get('name') or '').strip()
        address = (request.form.get('address') or '').strip()
        phone = (request.form.get('phone') or '').strip()
        email = (request.form.get('email') or '').strip().lower()
        operating_hours = (request.form.get('operating_hours') or '').strip()
        currency = request.form.get('currency', 'PHP')

        if not name:
            flash('Clinic name is required', 'error')
            return render_template('clinics/create.html')

        try:
            clinic_data = {
                'name': name,
                'address': address,
                'phone': phone,
                'email': email,
                'operating_hours': operating_hours,
                'currency': currency,
                'owner_id': session['user_id'],
                'is_active': True,
                'created_at': datetime.utcnow(),
                'updated_at': datetime.utcnow(),
            }
            mongo.db.clinics.insert_one(clinic_data)
            flash(f'Clinic "{name}" created successfully!', 'success')
            return redirect(url_for('clinics.list_clinics'))
        except Exception as e:
            print(f"[ERROR] Create clinic: {e}")
            traceback.print_exc()
            flash('Error creating clinic', 'error')

    return render_template('clinics/create.html')


@clinics_bp.route('/clinics/<clinic_id>/edit', methods=['GET', 'POST'])
@role_required(ROLE_DENTIST)  # clinic settings = dentist/admin only
def edit_clinic(clinic_id):
    try:
        clinic = mongo.db.clinics.find_one({
            '_id': ObjectId(clinic_id),
            'owner_id': session['user_id'],
        })
        if not clinic:
            flash('Clinic not found', 'error')
            return redirect(url_for('clinics.list_clinics'))

        if request.method == 'POST':
            mongo.db.clinics.update_one(
                {'_id': ObjectId(clinic_id)},
                {'$set': {
                    'name': (request.form.get('name') or '').strip(),
                    'address': (request.form.get('address') or '').strip(),
                    'phone': (request.form.get('phone') or '').strip(),
                    'email': (request.form.get('email') or '').strip().lower(),
                    'operating_hours': (request.form.get('operating_hours') or '').strip(),
                    'currency': request.form.get('currency', 'PHP'),
                    'updated_at': datetime.utcnow(),
                }},
            )
            flash('Clinic updated successfully!', 'success')
            return redirect(url_for('clinics.list_clinics'))

        return render_template('clinics/edit.html', clinic=clinic)
    except Exception as e:
        print(f"Edit clinic error: {e}")
        flash('Error editing clinic', 'error')
        return redirect(url_for('clinics.list_clinics'))


@clinics_bp.route('/clinics/<clinic_id>/delete', methods=['POST'])
@role_required(ROLE_DENTIST)  # clinic management is dentist/admin only
def delete_clinic(clinic_id):
    try:
        mongo.db.clinics.update_one(
            {'_id': ObjectId(clinic_id), 'owner_id': session['user_id']},
            {'$set': {'is_active': False, 'updated_at': datetime.utcnow()}},
        )
        flash('Clinic deleted successfully', 'success')
    except Exception as e:
        print(f"Delete clinic error: {e}")
        flash('Error deleting clinic', 'error')
    return redirect(url_for('clinics.list_clinics'))
