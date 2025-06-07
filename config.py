# config.py - Configuration file for Flask app
import os
from datetime import timedelta

class Config:
    """Base configuration"""
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'
    MONGO_URI = os.environ.get('MONGO_URI') or 'mongodb://localhost:27017/dental_portal'
    
    # Session configuration
    PERMANENT_SESSION_LIFETIME = timedelta(hours=24)
    SESSION_COOKIE_SECURE = False  # Set to True in production with HTTPS
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    
    # Upload configuration
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max file size
    UPLOAD_FOLDER = 'uploads'
    ALLOWED_EXTENSIONS = {'txt', 'pdf', 'png', 'jpg', 'jpeg', 'gif', 'doc', 'docx'}
    
    # Pagination
    PATIENTS_PER_PAGE = 20
    TREATMENTS_PER_PAGE = 10
    
    # Email configuration (if implementing email features)
    MAIL_SERVER = os.environ.get('MAIL_SERVER')
    MAIL_PORT = int(os.environ.get('MAIL_PORT') or 587)
    MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS', 'true').lower() in ['true', 'on', '1']
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')

class DevelopmentConfig(Config):
    """Development configuration"""
    DEBUG = True
    MONGO_URI = os.environ.get('MONGO_URI') or 'mongodb://localhost:27017/dental_portal_dev'

class TestingConfig(Config):
    """Testing configuration"""
    TESTING = True
    MONGO_URI = os.environ.get('MONGO_URI') or 'mongodb://localhost:27017/dental_portal_test'

class ProductionConfig(Config):
    """Production configuration"""
    DEBUG = False
    SECRET_KEY = os.environ.get('SECRET_KEY')
    MONGO_URI = os.environ.get('MONGO_URI')
    SESSION_COOKIE_SECURE = True  # Enable in production with HTTPS
    
    if not SECRET_KEY:
        raise ValueError("No SECRET_KEY set for production environment")
    if not MONGO_URI:
        raise ValueError("No MONGO_URI set for production environment")

config = {
    'development': DevelopmentConfig,
    'testing': TestingConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}

# Database configuration
class DatabaseConfig:
    """Database-specific configuration"""
    
    # Collection names
    USERS_COLLECTION = 'users'
    CLINICS_COLLECTION = 'clinics'
    PATIENTS_COLLECTION = 'patients'
    DENTAL_CHARTS_COLLECTION = 'dental_charts'
    TREATMENT_RECORDS_COLLECTION = 'treatment_records'
    INFORMED_CONSENTS_COLLECTION = 'informed_consents'
    
    # Validation rules
    PASSWORD_MIN_LENGTH = 8
    PASSWORD_REQUIRE_SPECIAL = True
    EMAIL_VALIDATION_REGEX = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    PHONE_VALIDATION_REGEX = r'^[\d\-\(\)\+\s]+$'
    
    # Data retention policies
    BACKUP_RETENTION_DAYS = 365
    LOG_RETENTION_DAYS = 90
    SESSION_RETENTION_DAYS = 30

# Application constants
class AppConstants:
    """Application-wide constants"""
    
    # Tooth numbering system
    ADULT_TEETH = list(range(1, 33))  # 1-32
    TEMPORARY_TEETH = {
        'upper_right': list(range(51, 56)),  # 51-55
        'upper_left': list(range(61, 66)),   # 61-65
        'lower_left': list(range(71, 76)),   # 71-75
        'lower_right': list(range(81, 86))   # 81-85
    }
    
    # Dental conditions
    TOOTH_CONDITIONS = [
        'present', 'decayed', 'missing_caries', 'missing_other',
        'impacted', 'supernumerary', 'root_fragment', 'unerupted'
    ]
    
    RESTORATION_TYPES = [
        'amalgam', 'composite', 'jacket_crown', 'abutment',
        'attachment', 'pontic', 'inlay', 'implant', 'sealants',
        'removable_denture'
    ]
    
    # Treatment categories
    TREATMENT_CATEGORIES = [
        'Preventive', 'Restorative', 'Endodontic', 'Periodontic',
        'Oral Surgery', 'Orthodontic', 'Prosthodontic', 'Cosmetic',
        'Emergency', 'Consultation'
    ]
    
    # User roles
    USER_ROLES = ['dentist', 'hygienist', 'assistant', 'admin']
    
    # Gender options
    GENDER_OPTIONS = ['M', 'F']
    
    # Blood types
    BLOOD_TYPES = ['A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-']

# Environment-specific settings
def get_config():
    """Get configuration based on environment"""
    config_name = os.environ.get('FLASK_ENV', 'development')
    return config.get(config_name, config['default'])