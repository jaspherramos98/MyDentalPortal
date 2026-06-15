# File: MyDentalPortal/blueprints/models/__init__.py
# Boundary schemas (pydantic) — validate/normalise documents at the write edge.

from blueprints.models.patient import PatientDoc, validate_patient

__all__ = ["PatientDoc", "validate_patient"]
