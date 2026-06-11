# File: MyDentalPortal/config.py
# Configuration settings for Dental Portal

import os
from dotenv import load_dotenv

load_dotenv()


DEV_FALLBACK_SECRET = 'dev-fallback-key-change-in-production'


class Config:
    """Base configuration"""
    SECRET_KEY = os.environ.get('SECRET_KEY') or DEV_FALLBACK_SECRET
    MONGO_URI = os.environ.get('MONGO_URI') or 'mongodb://localhost:27017/dental_portal'

    # Session
    PERMANENT_SESSION_LIFETIME = 86400  # 24 hours
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'

    # Uploads
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16 MB
    UPLOAD_FOLDER = 'uploads'

    # App defaults
    TIMEZONE = os.environ.get('TIMEZONE') or 'Asia/Manila'
    DEFAULT_CURRENCY = os.environ.get('DEFAULT_CURRENCY') or 'PHP'
    RECORDS_PER_PAGE = 20

    # Accounts whose email is listed here are treated as administrators
    # (can approve/reject new registrations). Comma-separated env var.
    ADMIN_EMAILS = [
        e.strip().lower()
        for e in (os.environ.get('ADMIN_EMAILS') or 'admin@dental.com').split(',')
        if e.strip()
    ]

    @staticmethod
    def init_app(app):
        pass


class DevelopmentConfig(Config):
    DEBUG = True


class ProductionConfig(Config):
    DEBUG = False
    # Secure cookies require HTTPS. Default ON so HTTPS deploys (Render) stay
    # locked down. Can be disabled with SESSION_COOKIE_SECURE=false for an
    # HTTP-only portfolio demo (AWS EB single instance) that uses a non-PHI
    # demo database — never disable this against real patient data.
    SESSION_COOKIE_SECURE = os.environ.get('SESSION_COOKIE_SECURE', 'true').lower() != 'false'

    @classmethod
    def init_app(cls, app):
        Config.init_app(app)

        # Refuse to run in production with the known dev key — it would let
        # anyone forge session cookies for this PHI app.
        if app.config.get('SECRET_KEY') == DEV_FALLBACK_SECRET:
            raise RuntimeError(
                'SECRET_KEY is not set. Set a strong, random SECRET_KEY '
                'environment variable before running in production.'
            )

        import logging
        import sys
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(logging.INFO)
        app.logger.addHandler(handler)


# Map env name -> config class
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig,
}


def get_config():
    env = os.environ.get('FLASK_ENV', 'development')
    return config.get(env, config['default'])
