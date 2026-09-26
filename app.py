# File: MyDentalPortal/app.py
# Entry point: `gunicorn app:app` (Procfile / render.yaml) and `python app.py`
# for local development. The app itself is built in factory.py.

import os

from dotenv import load_dotenv

load_dotenv()

from observability import init_sentry  # noqa: E402
from factory import create_app, init_database  # noqa: E402

# Error tracking. Must run before the Flask app is created so Sentry can hook
# into it. No-op unless SENTRY_DSN is set (prod-only); PHI-safe (see observability.py).
init_sentry()

app = create_app()

# Startup seeding — runs on import so it executes under gunicorn too (gunicorn
# imports `app:app`; it never runs this file as __main__). Idempotent: indexes
# are no-ops if they exist, and the default admin is created only when the
# users collection is empty.
with app.app_context():
    init_database()

if __name__ == '__main__':
    # Debug is opt-out via env and force-disabled in production, so the
    # interactive Werkzeug debugger can never accidentally run on a prod host.
    debug = (
        os.environ.get('FLASK_DEBUG', '1') == '1'
        and os.environ.get('FLASK_ENV', 'development') != 'production'
    )
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=debug, host='0.0.0.0', port=port)
