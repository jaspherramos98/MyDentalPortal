# File: MyDentalPortal/app/routes/__init__.py
# Blueprint registry — clean imports, no silent failures.

from .auth import auth_bp
from .main import main_bp
from .clinics import clinics_bp
from .patients import patients_bp
from .charts import charts_bp
from .treatments import treatments_bp
from .appointments import appointments_bp

__all__ = [
    'auth_bp',
    'main_bp',
    'clinics_bp',
    'patients_bp',
    'charts_bp',
    'treatments_bp',
    'appointments_bp',
]
