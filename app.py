# File: MyDentalPortal/app.py
# Application entry point — slim orchestrator.
# All route logic lives in app/routes/*.py

import os

from flask import Flask, url_for, session, request
from flask_wtf.csrf import CSRFProtect, CSRFError
from werkzeug.security import generate_password_hash
from datetime import datetime
from dotenv import load_dotenv

from extensions import mongo, limiter
from config import get_config
from observability import init_sentry

load_dotenv()

# Error tracking. Must run before the Flask app is created so Sentry can hook
# into it. No-op unless SENTRY_DSN is set (prod-only); PHI-safe (see observability.py).
init_sentry()

# ---------------------------------------------------------------------------
# Create app
# ---------------------------------------------------------------------------
app = Flask(__name__)

config_class = get_config()
app.config.from_object(config_class)
config_class.init_app(app)

mongo.init_app(app)

# CSRF protection for all state-changing requests (POST/PUT/PATCH/DELETE).
# Form posts carry a hidden csrf_token field; fetch() calls send it via the
# X-CSRFToken header (see the meta tag + fetch wrapper in templates).
csrf = CSRFProtect(app)
limiter.init_app(app)

# ---------------------------------------------------------------------------
# Register blueprints
# ---------------------------------------------------------------------------
from blueprints.routes.auth import auth_bp
from blueprints.routes.main import main_bp
from blueprints.routes.clinics import clinics_bp
from blueprints.routes.patients import patients_bp
from blueprints.routes.charts import charts_bp
from blueprints.routes.treatments import treatments_bp
from blueprints.routes.appointments import appointments_bp
from blueprints.routes.uploads import uploads_bp
from blueprints.routes.admin import admin_bp
from blueprints.routes.reports import reports_bp
from blueprints.routes.staff import staff_bp
from blueprints.utils import is_admin

app.register_blueprint(auth_bp)
app.register_blueprint(main_bp)
app.register_blueprint(clinics_bp)
app.register_blueprint(patients_bp)
app.register_blueprint(charts_bp)
app.register_blueprint(treatments_bp)
app.register_blueprint(appointments_bp)
app.register_blueprint(uploads_bp)
app.register_blueprint(admin_bp)
app.register_blueprint(reports_bp)
app.register_blueprint(staff_bp)

# ---------------------------------------------------------------------------
# Template helpers
# ---------------------------------------------------------------------------
@app.context_processor
def inject_helpers():
    """Make utility functions available in every template."""

    def safe_url_for(endpoint, **values):
        try:
            return url_for(endpoint, **values)
        except Exception:
            return '#'

    # "today" (in the clinic's timezone) for date-input min/max bounds.
    try:
        from zoneinfo import ZoneInfo
        _today = datetime.now(ZoneInfo(app.config.get('TIMEZONE', 'Asia/Manila'))).strftime('%Y-%m-%d')
    except Exception:
        _today = datetime.now().strftime('%Y-%m-%d')

    return dict(
        safe_url_for=safe_url_for,
        current_year=datetime.utcnow().year,
        is_admin=is_admin(),
        today=_today,
        min_birth_date='1900-01-01',
    )


@app.template_filter('datefmt')
def datefmt(value, fmt='%B %d, %Y'):
    """Format a date value that may be a datetime, an ISO/date string, or None.

    MongoDB stores some records with native datetimes and older/seed records
    with plain strings. Calling .strftime() directly in templates crashes on
    the string ones, so route everything through this tolerant filter.
    """
    if value is None or value == '':
        return 'N/A'
    if isinstance(value, datetime):
        return value.strftime(fmt)
    if isinstance(value, str):
        for parse_fmt in (
            '%Y-%m-%dT%H:%M:%S.%f',
            '%Y-%m-%dT%H:%M:%S',
            '%Y-%m-%d %H:%M:%S',
            '%Y-%m-%d',
        ):
            try:
                return datetime.strptime(value, parse_fmt).strftime(fmt)
            except ValueError:
                continue
        return value  # unparseable string — show it raw rather than crash
    return str(value)

@app.after_request
def add_security_headers(response):
    """Security headers + no-cache for authenticated pages."""
    # Applies to every response. nosniff stops MIME-confusion attacks on any
    # served file; DENY blocks clickjacking via framing.
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    # Content-Security-Policy. 'unsafe-inline' is currently required because the
    # templates use inline <script>/onclick handlers and inline styles; the CDN
    # host is allowed for Bootstrap/Font Awesome/jQuery. Tightening to remove
    # 'unsafe-inline' requires moving inline JS to static files (future work).
    response.headers['Content-Security-Policy'] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com; "
        "style-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com; "
        "font-src 'self' https://cdnjs.cloudflare.com; "
        "img-src 'self' data:; "
        "object-src 'none'; base-uri 'self'; frame-ancestors 'none'"
    )
    # Authenticated pages must not be cached (back-button-after-logout fix).
    # The patient-photo route is the one exception: it sets its own private,
    # short-lived cache header so the detail page doesn't re-stream the full
    # image on every view — don't clobber it here.
    if 'user_id' in session and request.endpoint != 'uploads.patient_photo':
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
    return response

# ---------------------------------------------------------------------------
# Error handlers
# ---------------------------------------------------------------------------
def _safe_referrer_redirect():
    """Redirect back to the referring page only if it is same-origin.

    Prevents an open-redirect: request.referrer is attacker-controllable, so we
    only honour it when its host matches ours, otherwise fall back to a safe page.
    """
    from urllib.parse import urlparse
    from flask import request, redirect, url_for, session
    ref = request.referrer
    if ref and urlparse(ref).netloc == urlparse(request.host_url).netloc:
        return redirect(ref)
    fallback = 'main.dashboard' if 'user_id' in session else 'auth.login'
    return redirect(url_for(fallback))

@app.errorhandler(404)
def not_found(error):
    from flask import render_template
    return render_template('errors/404.html'), 404

@app.errorhandler(403)
def forbidden(error):
    from flask import flash, redirect, url_for, session
    if 'user_id' in session:
        flash('You do not have permission to access that page.', 'error')
        return redirect(url_for('main.dashboard'))
    return redirect(url_for('auth.login'))

@app.errorhandler(500)
def internal_error(error):
    from flask import render_template
    return render_template('errors/500.html'), 500

@app.errorhandler(CSRFError)
def handle_csrf_error(error):
    """Invalid/missing CSRF token — JSON for fetch calls, redirect for form posts."""
    from flask import request, jsonify, flash
    if request.is_json:
        return jsonify({'success': False, 'error': 'CSRF token missing or invalid'}), 400
    flash('Your session expired or the form was invalid. Please try again.', 'error')
    return _safe_referrer_redirect(), 303

@app.errorhandler(413)
def request_too_large(error):
    """Uploaded file exceeded MAX_CONTENT_LENGTH — return to the form with a message."""
    from flask import flash
    mb = app.config.get('MAX_CONTENT_LENGTH', 0) // (1024 * 1024)
    flash(f'File too large. The maximum upload size is {mb} MB.', 'error')
    return _safe_referrer_redirect(), 303

# ---------------------------------------------------------------------------
# Health check (used by Render to confirm the service is up)
# ---------------------------------------------------------------------------
@app.route('/health')
def health_check():
    from flask import jsonify
    try:
        mongo.db.command('ping')
        return jsonify({"status": "healthy", "database": "connected"}), 200
    except Exception as e:
        return jsonify({"status": "unhealthy", "error": str(e)}), 500


# ---------------------------------------------------------------------------
# PWA (installable, online-first). The service worker caches only the static
# app shell — never authenticated HTML or patient data (single source of truth).
# ---------------------------------------------------------------------------
@app.route('/manifest.webmanifest')
def web_manifest():
    from flask import send_from_directory, make_response
    resp = make_response(send_from_directory(app.static_folder, 'manifest.webmanifest'))
    resp.headers['Content-Type'] = 'application/manifest+json'
    return resp


@app.route('/sw.js')
def service_worker():
    # Served from root so its scope covers the whole app (a SW under /static/
    # could only control /static/). Service-Worker-Allowed makes that explicit.
    from flask import send_from_directory, make_response
    resp = make_response(send_from_directory(app.static_folder, 'sw.js'))
    resp.headers['Content-Type'] = 'application/javascript'
    resp.headers['Service-Worker-Allowed'] = '/'
    return resp

# ---------------------------------------------------------------------------
# Database initialisation
# ---------------------------------------------------------------------------
def init_database():
    """Create indexes and a default admin user (first run only)."""
    try:
        mongo.db.users.create_index("email", unique=True)
        mongo.db.users.create_index("license_number")
        mongo.db.clinics.create_index("owner_id")
        mongo.db.patients.create_index("clinic_id")
        mongo.db.dental_charts.create_index("patient_id")
        mongo.db.treatment_records.create_index("patient_id")
        mongo.db.prescriptions.create_index("patient_id")
        mongo.db.patient_files.create_index("patient_id")
        mongo.db.appointments.create_index([("clinic_id", 1), ("date", 1)])
        mongo.db.appointments.create_index("patient_id")
        # Multi-staff: staff<->dentist links (access seam reads by user_id).
        mongo.db.memberships.create_index([("user_id", 1), ("is_active", 1)])
        mongo.db.memberships.create_index("dentist_id")
        # Audit trail: nested viewer reads by dentist, newest-first.
        mongo.db.audit_log.create_index([("dentist_id", 1), ("timestamp", -1)])
        mongo.db.audit_log.create_index("timestamp")
        # Staff access codes: single-use lookup by hash.
        mongo.db.access_codes.create_index("code_hash")
        mongo.db.access_codes.create_index("dentist_id")

        if mongo.db.users.count_documents({}) == 0:
            mongo.db.users.insert_one({
                "name": "Admin User",
                "email": "admin@dental.com",
                "password": generate_password_hash("admin123"),
                "license_number": "ADMIN001",
                "specialty": "General Dentistry",
                "role": "admin",
                "status": "approved",
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
                "is_active": True,
            })
            print(">>> Default admin created  |  admin@dental.com / admin123")
    except Exception as e:
        print(f"Database init error: {e}")


# ---------------------------------------------------------------------------
# Startup seeding — runs on import so it executes under gunicorn too
# (gunicorn imports `app:app`; it never runs this file as __main__).
# init_database() is idempotent: indexes are no-ops if they exist, and the
# default admin is created only when the users collection is empty.
# ---------------------------------------------------------------------------
with app.app_context():
    init_database()

# ---------------------------------------------------------------------------
# Main (local development server only)
# ---------------------------------------------------------------------------
if __name__ == '__main__':
    # Debug is opt-out via env and force-disabled in production, so the
    # interactive Werkzeug debugger can never accidentally run on a prod host.
    debug = (
        os.environ.get('FLASK_DEBUG', '1') == '1'
        and os.environ.get('FLASK_ENV', 'development') != 'production'
    )
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=debug, host='0.0.0.0', port=port)
