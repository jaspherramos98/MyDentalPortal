# Routes package initialization
from flask import Blueprint

# Import all blueprints to make them available
try:
    from .main import main_bp
except ImportError:
    main_bp = None

try:
    from .auth import auth_bp
except ImportError:
    auth_bp = None

try:
    from .appointments import appointments_bp
except ImportError:
    appointments_bp = None

try:
    from .clinics import clinics_bp
except ImportError:
    clinics_bp = None

try:
    from .patients import patients_bp
except ImportError:
    patients_bp = None

try:
    from .treatments import treatments_bp
except ImportError:
    treatments_bp = None

try:
    from .charts import charts_bp
except ImportError:
    charts_bp = None

__all__ = [
    'main_bp',
    'auth_bp', 
    'appointments_bp',
    'clinics_bp',
    'patients_bp',
    'treatments_bp',
    'charts_bp'
]