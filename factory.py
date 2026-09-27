# File: MyDentalPortal/factory.py
# Application factory. Builds the Flask app; ``app.py`` calls it for gunicorn
# (``gunicorn app:app``) and the test suite calls it against an in-memory DB.
#
# Deliberately side-effect free: creating an app never touches the database.
# Index creation + the default-admin seed live in ``init_database()``, which
# only ``app.py`` runs at startup.

import logging
import os
from datetime import datetime

from urllib.parse import urlparse

from flask import (
    Flask, url_for, session, request, redirect, flash, jsonify,
    render_template, send_from_directory, make_response,
)
from flask_wtf.csrf import CSRFProtect, CSRFError
from werkzeug.security import generate_password_hash

from extensions import mongo, limiter
from blueprints.utils import enforce_idle_timeout, wants_json_submit, is_admin
from blueprints.clock import utcnow
from config import get_config
from observability import configure_logging
from blueprints.repositories import submissions as submissions_repo

log = logging.getLogger(__name__)


def create_app(config_class=None, overrides=None, init_mongo=True):
    """Build the Flask app.

    config_class: a ``config.py`` class; defaults to the one FLASK_ENV selects.
    overrides:    dict applied after the config class (tests use this).
    init_mongo:   False leaves the shared ``mongo`` singleton alone, so tests can
                  point it at mongomock without a real client being created.
    """
    configure_logging()
    app = Flask(__name__)

    config_class = config_class or get_config()
    app.config.from_object(config_class)
    if overrides:
        app.config.update(overrides)
    config_class.init_app(app)

    # Trust the reverse proxy/proxies in front of us so request.remote_addr is the
    # REAL client IP (from X-Forwarded-For), not the proxy's. Without this, the
    # per-IP rate limiter buckets ALL clients together. Gated on TRUSTED_PROXY_COUNT
    # so local/dev (0) is unchanged. ⚠️ Set it to the EXACT number of trusted proxies
    # in the chain — too high lets clients spoof their IP. On Render set 1; behind
    # Cloudflare->Render set 2.
    _trusted_proxies = int(os.environ.get('TRUSTED_PROXY_COUNT', '0') or 0)
    if _trusted_proxies > 0:
        from werkzeug.middleware.proxy_fix import ProxyFix
        app.wsgi_app = ProxyFix(
            app.wsgi_app, x_for=_trusted_proxies, x_proto=_trusted_proxies,
            x_host=_trusted_proxies,
        )

    if init_mongo:
        mongo.init_app(app)

    # CSRF protection for all state-changing requests (POST/PUT/PATCH/DELETE).
    # Form posts carry a hidden csrf_token field; fetch() calls send it via the
    # X-CSRFToken header (see the meta tag + fetch wrapper in templates).
    CSRFProtect(app)
    limiter.init_app(app)

    _register_blueprints(app)
    _register_template_helpers(app)
    _register_request_hooks(app)
    _register_error_handlers(app)
    _register_core_routes(app)
    return app


def _register_blueprints(app):
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
    from blueprints.routes.deletions import deletions_bp

    for bp in (auth_bp, main_bp, clinics_bp, patients_bp, charts_bp,
               treatments_bp, appointments_bp, uploads_bp, admin_bp,
               reports_bp, staff_bp, deletions_bp):
        app.register_blueprint(bp)


def _register_template_helpers(app):
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
            current_year=utcnow().year,
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

    @app.url_defaults
    def _static_cache_bust(endpoint, values):
        """Append ?v=<file mtime> to url_for('static', ...) URLs.

        sw.js serves /static/* cache-first, so without a changing URL an installed
        PWA keeps running the OLD copy of a JS/CSS file after a deploy — a shipped
        fix would never reach the device. The query string is part of the cache key,
        so a new deploy (new mtime) means a fresh fetch.
        """
        if endpoint != 'static' or 'v' in values or 'filename' not in values:
            return
        try:
            values['v'] = int(os.stat(os.path.join(app.static_folder, values['filename'])).st_mtime)
        except OSError:
            pass  # missing file: leave the URL alone, the request will 404 normally


def _register_request_hooks(app):
    # Idle logout (PHI on an unattended screen).
    app.before_request(enforce_idle_timeout)

    @app.after_request
    def add_security_headers(response):
        """Security headers + no-cache for authenticated pages."""
        # Applies to every response. nosniff stops MIME-confusion attacks on any
        # served file; DENY blocks clickjacking via framing.
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        # HSTS: force HTTPS for a year on any TLS connection (Render). Only sent on
        # secure requests so local/dev HTTP is unaffected. No 'preload' yet — that's
        # a hard-to-reverse browser-list commitment; revisit before opting in.
        if request.is_secure:
            response.headers['Strict-Transport-Security'] = (
                'max-age=31536000; includeSubDomains'
            )
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


def _register_error_handlers(app):
    def _safe_referrer_redirect():
        """Redirect back to the referring page only if it is same-origin.

        Prevents an open-redirect: request.referrer is attacker-controllable, so we
        only honour it when its host matches ours, otherwise fall back to a safe page.
        """
        ref = request.referrer
        if ref and urlparse(ref).netloc == urlparse(request.host_url).netloc:
            return redirect(ref)
        fallback = 'main.dashboard' if 'user_id' in session else 'auth.login'
        return redirect(url_for(fallback))

    @app.errorhandler(404)
    def not_found(error):
        return render_template('errors/404.html'), 404

    @app.errorhandler(403)
    def forbidden(error):
        if 'user_id' in session:
            flash('You do not have permission to access that page.', 'error')
            return redirect(url_for('main.dashboard'))
        return redirect(url_for('auth.login'))

    @app.errorhandler(500)
    def internal_error(error):
        return render_template('errors/500.html'), 500

    @app.errorhandler(CSRFError)
    def handle_csrf_error(error):
        """Invalid/missing CSRF token — JSON for fetch calls, redirect for form posts."""
        if wants_json_submit():
            # Resilient form submit: it refreshes the token and retries, keeping
            # the typed form (a redirect here would throw it away).
            return jsonify({'ok': False, 'error': 'csrf'}), 400
        if request.is_json:
            return jsonify({'success': False, 'error': 'CSRF token missing or invalid'}), 400
        flash('Your session expired or the form was invalid. Please try again.', 'error')
        return _safe_referrer_redirect(), 303

    @app.errorhandler(413)
    def request_too_large(error):
        """Uploaded file exceeded MAX_CONTENT_LENGTH — return to the form with a message."""
        mb = app.config.get('MAX_CONTENT_LENGTH', 0) // (1024 * 1024)
        flash(f'File too large. The maximum upload size is {mb} MB.', 'error')
        return _safe_referrer_redirect(), 303


def _register_core_routes(app):
    @app.route('/health')
    def health_check():
        try:
            mongo.db.command('ping')
            return jsonify({"status": "healthy", "database": "connected"}), 200
        except Exception:
            # Public endpoint: never echo the driver error (it can name cluster
            # hosts). Render only needs the status code; details go to the log.
            log.exception("Health check failed")
            return jsonify({"status": "unhealthy", "database": "unavailable"}), 500


    # ---------------------------------------------------------------------------
    # PWA (installable, online-first). The service worker caches only the static
    # app shell — never authenticated HTML or patient data (single source of truth).
    # ---------------------------------------------------------------------------
    @app.route('/manifest.webmanifest')
    def web_manifest():
        resp = make_response(send_from_directory(app.static_folder, 'manifest.webmanifest'))
        resp.headers['Content-Type'] = 'application/manifest+json'
        return resp


    @app.route('/sw.js')
    def service_worker():
        # Served from root so its scope covers the whole app (a SW under /static/
        # could only control /static/). Service-Worker-Allowed makes that explicit.
        resp = make_response(send_from_directory(app.static_folder, 'sw.js'))
        resp.headers['Content-Type'] = 'application/javascript'
        resp.headers['Service-Worker-Allowed'] = '/'
        return resp


def init_database():
    """Create indexes and a default admin user (first run only)."""
    try:
        mongo.db.users.create_index("email", unique=True)
        mongo.db.users.create_index("license_number")
        mongo.db.clinics.create_index("owner_id")
        mongo.db.patients.create_index("clinic_id")
        # Idempotent creates (resilient submit): unique submission_id per
        # create collection, so a retried POST can't create a duplicate.
        submissions_repo.ensure_indexes()
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
        # Deletion requests: review queue reads by dentist + status.
        mongo.db.deletion_requests.create_index([("dentist_id", 1), ("status", 1)])
        mongo.db.deletion_requests.create_index([("entity_type", 1), ("entity_id", 1)])

        if mongo.db.users.count_documents({}) == 0:
            mongo.db.users.insert_one({
                "name": "Admin User",
                "email": "admin@dental.com",
                "password": generate_password_hash("admin123"),
                "license_number": "ADMIN001",
                "specialty": "General Dentistry",
                "role": "admin",
                "status": "approved",
                "created_at": utcnow(),
                "updated_at": utcnow(),
                "is_active": True,
            })
            log.warning("Default admin account created (admin@dental.com) — change its password")
    except Exception:
        log.exception("Database init failed")
