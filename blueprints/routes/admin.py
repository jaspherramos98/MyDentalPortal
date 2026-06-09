# File: MyDentalPortal/blueprints/routes/admin.py
# Admin-only screens. Currently: review + approve/reject new registrations.

from flask import (
    Blueprint, render_template, redirect, url_for,
    session, flash, abort,
)
from bson.objectid import ObjectId
from bson.errors import InvalidId
from datetime import datetime

from extensions import mongo
from blueprints.utils import admin_required

admin_bp = Blueprint('admin', __name__)


@admin_bp.route('/admin/registrations')
@admin_required
def registrations():
    pending = list(
        mongo.db.users.find({'status': 'pending'}).sort('created_at', -1)
    )
    return render_template('admin/registrations.html', pending=pending)


@admin_bp.route('/admin/registrations/<user_id>/approve', methods=['POST'])
@admin_required
def approve(user_id):
    try:
        oid = ObjectId(user_id)
    except (InvalidId, TypeError):
        abort(404)
    mongo.db.users.update_one(
        {'_id': oid, 'status': 'pending'},
        {'$set': {'status': 'approved', 'updated_at': datetime.utcnow(),
                  'approved_by': session['user_id']}},
    )
    flash('Account approved — the user can now log in.', 'success')
    return redirect(url_for('admin.registrations'))


@admin_bp.route('/admin/registrations/<user_id>/reject', methods=['POST'])
@admin_required
def reject(user_id):
    try:
        oid = ObjectId(user_id)
    except (InvalidId, TypeError):
        abort(404)
    mongo.db.users.update_one(
        {'_id': oid, 'status': 'pending'},
        {'$set': {'status': 'rejected', 'updated_at': datetime.utcnow(),
                  'rejected_by': session['user_id']}},
    )
    flash('Registration rejected.', 'warning')
    return redirect(url_for('admin.registrations'))
